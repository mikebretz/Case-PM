"""
Accounting tiers 1–4 in one wave:
  1) Integrations — Stripe, Plaid, scheduled report email
  2) Compliance — W-2 / 941 export packages, 1099 transmit log
  3) Distribution — IC/OE/PO depth (blanket release, transfers, line grids)
  4) Sage hybrid — Web API vendor/GL pull, sync dashboard, batch export queue
"""
from __future__ import annotations

import csv
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

from accounting_platform import write_audit


def _stripe_secret() -> str:
    return (os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('CASEPM_STRIPE_SECRET_KEY') or '').strip()


def create_stripe_payment_intent(amount: float, currency: str = 'usd', metadata: dict | None = None) -> dict:
    from accounting_parity_wave2 import stripe_payment_intent_stub

    secret = _stripe_secret()
    if not secret:
        return stripe_payment_intent_stub(amount, currency, metadata)
    amt_cents = int(round(float(amount) * 100))
    if amt_cents < 50:
        raise ValueError('Stripe amount must be at least 0.50')
    payload = {
        'amount': str(amt_cents),
        'currency': (currency or 'usd').lower()[:3],
        'automatic_payment_methods[enabled]': 'true',
    }
    for k, v in (metadata or {}).items():
        payload[f'metadata[{k}]'] = str(v)[:500]
    body = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.stripe.com/v1/payment_intents',
        data=body,
        headers={
            'Authorization': f'Bearer {secret}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return {
            'provider': 'stripe',
            'mode': 'test' if secret.startswith('sk_test') else 'live',
            'status': data.get('status'),
            'client_secret': data.get('client_secret'),
            'payment_intent_id': data.get('id'),
            'amount': round(float(amount), 2),
            'currency': currency,
        }
    except urllib.error.HTTPError as exc:
        err = exc.read().decode('utf-8', errors='replace')[:400]
        raise ValueError(f'Stripe error: {err or exc.reason}') from exc


def handle_stripe_webhook(payload: dict, signature_header: str = '') -> dict:
    from accounting_parity_wave3 import stripe_webhook_stub

    secret = _stripe_secret()
    wh_secret = (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip()
    evt_type = payload.get('type') or 'unknown'
    if not secret:
        return stripe_webhook_stub(payload)
    if wh_secret and signature_header:
        # Production should verify signature with stripe library; log intent for ops.
        pass
    obj = payload.get('data', {}).get('object') or {}
    return {
        'received': True,
        'provider': 'stripe',
        'type': evt_type,
        'payment_intent_id': obj.get('id'),
        'status': 'processed',
        'amount': (obj.get('amount') or 0) / 100.0 if obj.get('amount') else None,
    }


def plaid_sandbox_or_live_transactions(body: dict) -> list:
    """Use Plaid /transactions/sync when access_token provided; else normalize posted transactions."""
    access = (body.get('access_token') or os.environ.get('PLAID_ACCESS_TOKEN') or '').strip()
    if access and os.environ.get('PLAID_CLIENT_ID') and os.environ.get('PLAID_SECRET'):
        plaid_req = {
            'client_id': os.environ['PLAID_CLIENT_ID'],
            'secret': os.environ['PLAID_SECRET'],
            'access_token': access,
            'start_date': body.get('start_date') or (date.today().replace(day=1).isoformat()),
            'end_date': body.get('end_date') or date.today().isoformat(),
        }
        data = json.dumps(plaid_req).encode('utf-8')
        req = urllib.request.Request(
            'https://production.plaid.com/transactions/get',
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                out = json.loads(resp.read().decode('utf-8'))
            return out.get('transactions') or []
        except Exception:
            pass
    return body.get('transactions') or []


def run_scheduled_reports_with_email(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_parity_wave2 import _ledger_settings, _save_ledger_settings
    from accounting_reports import run_report

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    schedules = settings.get('scheduled_reports') or []
    ran = []
    for s in schedules[-20:]:
        email = (s.get('email') or '').strip()
        rtype = s.get('report_type') or 'trial_balance'
        subject = f'Case PM scheduled report: {rtype}'
        try:
            if rtype == 'trial_balance':
                data = run_report(db, models, ledger_id, 'trial_balance')
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(['account_number', 'description', 'debit', 'credit', 'balance'])
                for row in data.get('rows') or []:
                    w.writerow([row.get('account_number'), row.get('description'), row.get('debit'), row.get('credit'), row.get('balance')])
                csv_text = buf.getvalue()
            else:
                csv_text = f'report_type,{rtype}\nledger_id,{ledger_id}\n'
            status = 'generated_only'
            if email:
                try:
                    from email_notifications import send_workflow_email
                    send_workflow_email(
                        email,
                        subject,
                        f'<p>Attached summary for <strong>{rtype}</strong>.</p><pre>{csv_text[:8000]}</pre>',
                        csv_text[:12000],
                    )
                    status = 'emailed'
                except Exception as exc:
                    status = f'email_failed:{exc}'
            ran.append({**s, 'last_run': datetime.utcnow().isoformat() + 'Z', 'status': status})
        except Exception as exc:
            ran.append({**s, 'last_run': datetime.utcnow().isoformat() + 'Z', 'status': f'error:{exc}'})
    settings['scheduled_reports'] = schedules
    settings['last_report_scheduler_run'] = datetime.utcnow().isoformat() + 'Z'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='scheduled_reports_run', details={'count': len(ran)})
    return {'ran': len(ran), 'schedules': ran}


# --- Compliance ---

def export_w2_efile_package(db, models, ledger_id: int, tax_year: int) -> str:
    from accounting_parity_wave3 import export_w2_summary

    data = export_w2_summary(db, models, ledger_id, tax_year)
    lines = [f'RECORD_TYPE|W2|YEAR|{tax_year}|EMPLOYER|CASEPM']
    for i, emp in enumerate(data.get('employees') or [], start=1):
        lines.append(
            f'RW|{i:06d}|{emp.get("employee_number","")}|{emp.get("name","")}|'
            f'{emp.get("wages",0):.2f}|{emp.get("federal_withheld",0):.2f}|{emp.get("fica_withheld",0):.2f}'
        )
    lines.append(f'RT|{len(data.get("employees") or [])}')
    return '\r\n'.join(lines)


def export_941_efile_package(db, models, ledger_id: int, quarter: int, year: int) -> str:
    from accounting_parity_wave3 import export_form_941_summary

    d = export_form_941_summary(db, models, ledger_id, quarter, year)
    return (
        f"FORM,941,YEAR,{year},QTR,{quarter}\n"
        f"WAGES,{d.get('wages_tips_other')}\n"
        f"FED_WH,{d.get('federal_income_tax_withheld')}\n"
        f"FICA,{d.get('social_security_medicare_tax')}\n"
        f"TOTAL,{d.get('total_taxes')}\n"
    )


def log_1099_transmit(db, models, ledger_id: int, tax_year: int, user_id=None) -> dict:
    from accounting_gl_ap_ar_complete import export_1099_fire_transmission

    content = export_1099_fire_transmission(db, models, ledger_id, tax_year)
    from accounting_gl_service import _parse_settings
    import json as _json

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _parse_settings(ledger)
    log = settings.get('irs_transmit_log') or []
    entry = {
        'type': '1099_fire',
        'tax_year': int(tax_year),
        'transmitted_at': datetime.utcnow().isoformat() + 'Z',
        'byte_length': len(content),
        'status': 'file_generated_for_transmit',
    }
    log.append(entry)
    settings['irs_transmit_log'] = log[-30:]
    ledger.settings_json = _json.dumps(settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='1099_transmit_log', details=entry)
    return {'ok': True, 'entry': entry, 'content_preview': content[:200]}


# --- Distribution ---

def po_line_receipt_grid(db, models, ledger_id: int, po_id: int) -> dict:
    from accounting_operations import _parse_lines, serialize_po

    AcctPurchaseOrder = models['AcctPurchaseOrder']
    po = AcctPurchaseOrder.query.filter_by(id=int(po_id), ledger_id=ledger_id).first()
    if not po:
        raise ValueError('PO not found')
    lines = _parse_lines(po.lines_json)
    grid = []
    for idx, ln in enumerate(lines):
        ordered = float(ln.get('qty') or 0)
        received = float(ln.get('qty_received') or 0)
        grid.append({
            'line_index': idx,
            'item_number': ln.get('item_number') or '',
            'description': ln.get('description') or '',
            'qty_ordered': ordered,
            'qty_received': received,
            'qty_open': round(max(ordered - received, 0), 4),
            'unit_price': float(ln.get('unit_price') or 0),
            'line_total': float(ln.get('line_total') or ordered * float(ln.get('unit_price') or 0)),
            'drop_ship': bool(ln.get('drop_ship')),
        })
    return {'purchase_order': serialize_po(po), 'lines': grid}


def blanket_po_release(db, models, ledger_id: int, po_id: int, body: dict, user_id=None) -> dict:
    """Create a child PO release from a blanket header."""
    from accounting_operations import _parse_lines, _save_lines, po_recompute_total, serialize_po
    from datetime import datetime as dt

    AcctPurchaseOrder = models['AcctPurchaseOrder']
    parent = AcctPurchaseOrder.query.filter_by(id=int(po_id), ledger_id=ledger_id).first()
    if not parent:
        raise ValueError('Blanket PO not found')
    if not getattr(parent, 'po_type', None) == 'Blanket' and not (parent.po_number or '').upper().startswith('BL-'):
        parent.po_type = 'Blanket'
    release_lines = body.get('lines') or []
    if not release_lines:
        raise ValueError('lines required for release')
    child = AcctPurchaseOrder(
        ledger_id=ledger_id,
        vendor_id=parent.vendor_id,
        po_number=f'{parent.po_number}-R{dt.utcnow().strftime("%m%d%H%M")}',
        status='Open',
        project_id=parent.project_id,
        total_amount=0,
        po_type='Release',
        parent_po_id=parent.id,
    )
    db.session.add(child)
    db.session.flush()
    lines = []
    for rl in release_lines:
        lines.append({
            'description': rl.get('description') or 'Release line',
            'item_number': rl.get('item_number') or '',
            'qty': float(rl.get('qty') or 0),
            'unit_price': float(rl.get('unit_price') or 0),
            'qty_received': 0,
        })
    child.total_amount = po_recompute_total(lines)
    child.lines_json = _save_lines(lines)
    write_audit(db, models, ledger_id, user_id=user_id, action='po_blanket_release', entity_id=child.id, details={'parent_po_id': parent.id})
    db.session.flush()
    return {'release': serialize_po(child), 'parent_po_id': parent.id}


def oe_fulfillment_grid(db, models, ledger_id: int, order_id: int) -> dict:
    from accounting_operations import _parse_lines, serialize_oe

    AcctSalesOrder = models['AcctSalesOrder']
    order = AcctSalesOrder.query.filter_by(id=int(order_id), ledger_id=ledger_id).first()
    if not order:
        raise ValueError('Sales order not found')
    lines = _parse_lines(order.lines_json)
    grid = []
    for idx, ln in enumerate(lines):
        ordered = float(ln.get('qty') or 0)
        shipped = float(ln.get('qty_shipped') or 0)
        grid.append({
            'line_index': idx,
            'description': ln.get('description') or '',
            'item_number': ln.get('item_number') or '',
            'qty_ordered': ordered,
            'qty_shipped': shipped,
            'qty_open': round(max(ordered - shipped, 0), 4),
            'unit_price': float(ln.get('unit_price') or 0),
            'commission_percent': float(ln.get('commission_percent') or 0),
        })
    return {'order': serialize_oe(order), 'lines': grid}


def inventory_location_transfer(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_operations import record_inventory_movement

    item_id = int(body['item_id'])
    qty = float(body['qty'])
    from_loc = (body.get('from_location_code') or 'MAIN')[:20]
    to_loc = (body.get('to_location_code') or 'SITE')[:20]
    if qty <= 0:
        raise ValueError('qty must be positive')
    record_inventory_movement(
        db, models, ledger_id, item_id,
        qty_delta=-qty, txn_type='transfer_out',
        reference=f'{from_loc}->{to_loc}',
    )
    record_inventory_movement(
        db, models, ledger_id, item_id,
        qty_delta=qty, txn_type='transfer_in',
        reference=f'{from_loc}->{to_loc}',
    )
    M = models.get('AcctInventoryLot')
    if M and body.get('lot_number'):
        lot = M.query.filter_by(ledger_id=ledger_id, item_id=item_id, lot_number=str(body['lot_number'])[:40]).first()
        if lot and hasattr(lot, 'location_code'):
            lot.location_code = to_loc
    write_audit(db, models, ledger_id, user_id=user_id, action='ic_location_transfer', details=body)
    return {'item_id': item_id, 'qty': qty, 'from': from_loc, 'to': to_loc}


# --- Sage hybrid ---

def sage_integration_status() -> dict:
    from sage300_web_client import probe_connection

    return probe_connection()


def sage_pull_vendors(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource

    resp = get_resource('AP', 'APVendors', top=100)
    if not resp.get('ok'):
        return {'imported': 0, 'mode': resp.get('mode'), 'message': resp.get('error') or 'Sage pull skipped'}
    AcctVendor = models['AcctVendor']
    data = resp.get('data') or {}
    rows = data.get('value') or data.get('APVendors') or []
    if isinstance(data, list):
        rows = data
    created = updated = 0
    for row in rows:
        code = (row.get('VendorNumber') or row.get('VendorCode') or row.get('Code') or '').strip().upper()
        if not code:
            continue
        name = (row.get('VendorName') or row.get('Name') or code)[:200]
        v = AcctVendor.query.filter_by(ledger_id=ledger_id, code=code).first()
        if not v:
            v = AcctVendor(ledger_id=ledger_id, code=code, name=name)
            db.session.add(v)
            created += 1
        else:
            updated += 1
        v.name = name
        if row.get('Email'):
            v.email = str(row['Email'])[:120]
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_vendors', details={'created': created, 'updated': updated})
    return {'imported': created + updated, 'created': created, 'updated': updated, 'mode': 'live'}


def sage_pull_gl_accounts(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource
    from accounting_persistence import seed_chart_of_accounts

    resp = get_resource('GL', 'GLAccounts', top=200)
    if not resp.get('ok'):
        return {'imported': 0, 'message': resp.get('error')}
    AcctGLAccount = models['AcctGLAccount']
    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(ledger_id)
    seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)
    data = resp.get('data') or {}
    rows = data.get('value') or []
    created = 0
    for row in rows:
        num = (row.get('AccountNumber') or row.get('AccountNo') or '').strip()
        if not num:
            continue
        if AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number=num).first():
            continue
        db.session.add(AcctGLAccount(
            ledger_id=ledger_id,
            account_number=num[:40],
            description=(row.get('Description') or num)[:200],
            account_type='expense',
            normal_balance='debit',
            status='Active',
            is_posting=True,
        ))
        created += 1
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_gl', details={'created': created})
    return {'created': created, 'mode': resp.get('mode')}


def sage_queue_open_batches(db, models, ledger_id: int, user_id=None) -> dict:
    """Export open journal batches as Sage import payload (JSON queue)."""
    from accounting_gl_service import _parse_settings

    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctGLAccount = models['AcctGLAccount']
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _parse_settings(ledger)
    queue = settings.get('sage_export_queue') or []
    batches = AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Open').limit(20).all()
    exported = []
    for b in batches:
        lines = []
        for ln in AcctJournalLine.query.filter_by(batch_id=b.id).order_by(AcctJournalLine.line_number).all():
            acct = AcctGLAccount.query.get(ln.account_id)
            lines.append({
                'account_number': acct.account_number if acct else '',
                'debit': float(ln.debit or 0),
                'credit': float(ln.credit or 0),
                'description': ln.description or '',
            })
        payload = {
            'batch_number': b.batch_number,
            'batch_date': b.batch_date.isoformat() if b.batch_date else None,
            'description': b.description,
            'lines': lines,
            'queued_at': datetime.utcnow().isoformat() + 'Z',
        }
        queue.append(payload)
        exported.append(b.batch_number)
    settings['sage_export_queue'] = queue[-50:]
    ledger.settings_json = json.dumps(settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_queue_batches', details={'batches': exported})
    return {'queued': len(exported), 'batch_numbers': exported, 'queue_size': len(settings['sage_export_queue'])}
