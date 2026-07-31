"""
Accounting waves 1–7: integrations hardening, Sage hybrid, compliance depth,
IC/OE, reporting, fixed assets, job cost tie-in helpers.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


# --- Wave 1: Stripe webhook verification ---

def verify_stripe_signature(payload_bytes: bytes, signature_header: str, webhook_secret: str, tolerance_sec: int = 300) -> bool:
    if not webhook_secret or not signature_header:
        return False
    parts = {}
    for item in signature_header.split(','):
        if '=' in item:
            k, v = item.split('=', 1)
            parts[k.strip()] = v.strip()
    ts = parts.get('t')
    v1 = parts.get('v1')
    if not ts or not v1:
        return False
    try:
        if abs(int(time.time()) - int(ts)) > tolerance_sec:
            return False
    except ValueError:
        return False
    signed = f'{ts}.{payload_bytes.decode("utf-8")}'.encode('utf-8')
    expected = hmac.new(webhook_secret.encode('utf-8'), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


def handle_stripe_webhook_verified(
    payload: dict,
    *,
    raw_body: bytes = b'',
    signature_header: str = '',
    db=None,
    models=None,
    user_id=None,
) -> dict:
    from accounting_parity_wave3 import stripe_webhook_stub, capture_pay_now_stripe

    wh_secret = (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip()
    api_secret = (os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('CASEPM_STRIPE_SECRET_KEY') or '').strip()
    if not api_secret:
        return stripe_webhook_stub(payload)
    if wh_secret:
        if not raw_body:
            raw_body = json.dumps(payload).encode('utf-8')
        if not verify_stripe_signature(raw_body, signature_header, wh_secret):
            raise ValueError('Invalid Stripe webhook signature')
    evt_type = payload.get('type') or 'unknown'
    obj = payload.get('data', {}).get('object') or {}
    out = {
        'received': True,
        'provider': 'stripe',
        'type': evt_type,
        'payment_intent_id': obj.get('id'),
        'status': 'processed',
        'amount': (obj.get('amount') or 0) / 100.0 if obj.get('amount') else None,
    }
    meta = obj.get('metadata') or {}
    token = meta.get('pay_now_token') or meta.get('casepm_pay_now_token')
    if evt_type == 'payment_intent.succeeded' and token and db is not None and models is not None:
        try:
            cap = capture_pay_now_stripe(db, models, token, obj.get('id') or '', user_id=user_id)
            out['pay_now'] = cap
        except Exception as exc:
            out['pay_now_error'] = str(exc)
    return out


# --- Wave 1: Plaid Link ---

def _plaid_env() -> str:
    return (os.environ.get('PLAID_ENV') or 'sandbox').strip().lower()


def _plaid_host() -> str:
    env = _plaid_env()
    if env == 'production':
        return 'https://production.plaid.com'
    if env == 'development':
        return 'https://development.plaid.com'
    return 'https://sandbox.plaid.com'


def plaid_credentials_ok() -> bool:
    return bool(os.environ.get('PLAID_CLIENT_ID') and os.environ.get('PLAID_SECRET'))


def create_plaid_link_token(db, models, ledger_id: int, user_id=None) -> dict:
    if not plaid_credentials_ok():
        return {'configured': False, 'link_token': None, 'message': 'Set PLAID_CLIENT_ID and PLAID_SECRET'}
    body = {
        'client_id': os.environ['PLAID_CLIENT_ID'],
        'secret': os.environ['PLAID_SECRET'],
        'user': {'client_user_id': f'ledger-{ledger_id}-user-{user_id or 0}'},
        'client_name': 'Case PM Accounting',
        'products': ['transactions'],
        'country_codes': ['US'],
        'language': 'en',
    }
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        f'{_plaid_host()}/link/token/create',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode('utf-8'))
        return {'configured': True, 'link_token': out.get('link_token'), 'expiration': out.get('expiration')}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode('utf-8', errors='replace')[:400]
        raise ValueError(f'Plaid link token failed: {err or exc.reason}') from exc


def exchange_plaid_public_token(db, models, ledger_id: int, public_token: str, user_id=None) -> dict:
    if not plaid_credentials_ok():
        raise ValueError('Plaid not configured')
    body = {
        'client_id': os.environ['PLAID_CLIENT_ID'],
        'secret': os.environ['PLAID_SECRET'],
        'public_token': public_token,
    }
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        f'{_plaid_host()}/item/public_token/exchange',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read().decode('utf-8'))
    access = out.get('access_token') or ''
    item_id = out.get('item_id') or ''
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    plaid_cfg = settings.get('plaid') or {}
    plaid_cfg['access_token'] = access
    plaid_cfg['item_id'] = item_id
    plaid_cfg['linked_at'] = datetime.utcnow().isoformat() + 'Z'
    settings['plaid'] = plaid_cfg
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='plaid_link', details={'item_id': item_id})
    return {'linked': True, 'item_id': item_id, 'has_access_token': bool(access)}


def plaid_access_token_for_ledger(ledger) -> str:
    settings = _ledger_settings(ledger)
    return (settings.get('plaid') or {}).get('access_token') or os.environ.get('PLAID_ACCESS_TOKEN', '')


# --- Wave 2: Sage hybrid dashboard & push ---

def _append_sage_sync_log(settings: dict, entry: dict) -> None:
    log = settings.get('sage_sync_log') or []
    log.append({**entry, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_sync_log'] = log[-100:]


def sage_hybrid_dashboard(db, models, ledger_id: int) -> dict:
    from accounting_tier14_wave import sage_integration_status

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    policy = settings.get('sage_conflict_policy') or 'casepm_wins'
    sor = settings.get('system_of_record') or 'casepm'
    return {
        'web_api': sage_integration_status(),
        'system_of_record': sor,
        'conflict_policy': policy,
        'export_queue_size': len(settings.get('sage_export_queue') or []),
        'last_sync': (settings.get('sage_sync_log') or [])[-5:],
        'push_queue': (settings.get('sage_push_queue') or [])[-10:],
    }


def save_sage_hybrid_policy(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if body.get('conflict_policy'):
        settings['sage_conflict_policy'] = str(body['conflict_policy'])[:40]
    if body.get('system_of_record'):
        settings['system_of_record'] = str(body['system_of_record'])[:20]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_policy', details=body)
    return sage_hybrid_dashboard(db, models, ledger_id)


def sage_push_vendors(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    AcctVendor = models['AcctVendor']
    vendors = AcctVendor.query.filter_by(ledger_id=ledger_id).order_by(AcctVendor.id).limit(limit).all()
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    pushed = []
    mode = 'queued'
    resp = get_resource('AP', 'APVendors', top=1)
    if resp.get('ok'):
        mode = 'simulated_push'
    for v in vendors:
        payload = {'VendorNumber': v.code, 'VendorName': v.name, 'Email': v.email or ''}
        settings.setdefault('sage_push_queue', []).append({'type': 'vendor', 'payload': payload})
        pushed.append(v.code)
    settings['sage_push_queue'] = (settings.get('sage_push_queue') or [])[-200:]
    _append_sage_sync_log(settings, {'direction': 'push', 'entity': 'vendors', 'count': len(pushed), 'mode': mode})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_vendors', details={'count': len(pushed), 'mode': mode})
    return {'pushed': len(pushed), 'mode': mode, 'vendor_codes': pushed[:20]}


def sage_push_open_ap(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    AcctAPDocument = models['AcctAPDocument']
    docs = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(AcctAPDocument.id).limit(limit).all()
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    queued = []
    for d in docs:
        queued.append({
            'type': 'open_ap',
            'document_number': d.document_number,
            'amount': float(d.amount or 0),
            'vendor_id': d.vendor_id,
        })
    settings.setdefault('sage_push_queue', []).extend(queued)
    settings['sage_push_queue'] = (settings.get('sage_push_queue') or [])[-200:]
    _append_sage_sync_log(settings, {'direction': 'push', 'entity': 'open_ap', 'count': len(queued)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_open_ap', details={'count': len(queued)})
    return {'queued': len(queued)}


# --- Wave 3: Compliance calendar & amendments ---

def compliance_filing_calendar(ledger_id: int, tax_year: int | None = None) -> dict:
    yr = tax_year or date.today().year
    deadlines = [
        {'id': 'w2_employees', 'label': 'W-2 to employees', 'due': f'{yr + 1}-01-31', 'form': 'W-2'},
        {'id': 'w3_transmittal', 'label': 'W-3 transmittal', 'due': f'{yr + 1}-01-31', 'form': 'W-3'},
        {'id': '1099_misc', 'label': '1099-NEC/MISC to recipients', 'due': f'{yr + 1}-01-31', 'form': '1099'},
        {'id': '941_q1', 'label': 'Form 941 Q1', 'due': f'{yr}-04-30', 'form': '941'},
        {'id': '941_q2', 'label': 'Form 941 Q2', 'due': f'{yr}-07-31', 'form': '941'},
        {'id': '941_q3', 'label': 'Form 941 Q3', 'due': f'{yr}-10-31', 'form': '941'},
        {'id': '941_q4', 'label': 'Form 941 Q4', 'due': f'{yr + 1}-01-31', 'form': '941'},
    ]
    today = date.today()
    for d in deadlines:
        try:
            due = date.fromisoformat(d['due'])
            d['status'] = 'past_due' if due < today else ('due_soon' if due <= today + timedelta(days=30) else 'upcoming')
        except ValueError:
            d['status'] = 'upcoming'
    return {'tax_year': yr, 'deadlines': deadlines}


def compliance_amendment_package(db, models, ledger_id: int, form: str, tax_year: int, body: dict) -> str:
    from accounting_tier14_wave import export_w2_efile_package, export_941_efile_package

    form = (form or 'w2').lower()
    reason = (body.get('reason') or 'Correction')[:200]
    header = f'AMEND|FORM|{form.upper()}|YEAR|{tax_year}|REASON|{reason}|GENERATED|{datetime.utcnow().isoformat()}Z'
    if form == '941':
        q = int(body.get('quarter') or 1)
        y = int(body.get('year') or tax_year)
        base = export_941_efile_package(db, models, ledger_id, q, y)
        return header + '\r\n' + base
    base = export_w2_efile_package(db, models, ledger_id, tax_year)
    return header + '\r\n' + base


# --- Wave 4: IC lot/serial & OE commissions ---

def inventory_lot_serial_grid(db, models, ledger_id: int, item_id: int | None = None) -> dict:
    M = models.get('AcctInventoryLot')
    AcctInventoryItem = models['AcctInventoryItem']
    if not M:
        return {'lots': [], 'items': []}
    q = M.query.filter_by(ledger_id=ledger_id)
    if item_id:
        q = q.filter_by(item_id=item_id)
    lots = []
    for lot in q.order_by(M.id.desc()).limit(200).all():
        item = AcctInventoryItem.query.get(lot.item_id)
        lots.append({
            'id': lot.id,
            'item_id': lot.item_id,
            'item_number': item.item_number if item else '',
            'lot_number': getattr(lot, 'lot_number', None) or '',
            'serial_number': getattr(lot, 'serial_number', None) or '',
            'qty_on_hand': float(lot.qty_on_hand or 0),
            'unit_cost': float(lot.unit_cost or 0),
            'location_code': getattr(lot, 'location_code', None) or 'MAIN',
        })
    items = [
        {'id': i.id, 'item_number': i.item_number, 'description': i.description}
        for i in AcctInventoryItem.query.filter_by(ledger_id=ledger_id).order_by(AcctInventoryItem.item_number).limit(500).all()
    ]
    return {'lots': lots, 'items': items}


def oe_commission_summary(db, models, ledger_id: int, order_id: int | None = None) -> dict:
    AcctSalesOrder = models['AcctSalesOrder']
    q = AcctSalesOrder.query.filter_by(ledger_id=ledger_id)
    if order_id:
        q = q.filter_by(id=order_id)
    orders = []
    total_comm = 0.0
    for o in q.order_by(AcctSalesOrder.id.desc()).limit(50).all():
        lines = json.loads(o.lines_json or '[]') if hasattr(o, 'lines_json') else (o.lines or [])
        if isinstance(lines, str):
            try:
                lines = json.loads(lines)
            except Exception:
                lines = []
        comm = 0.0
        for ln in lines or []:
            amt = float(ln.get('qty') or 0) * float(ln.get('unit_price') or 0)
            pct = float(ln.get('commission_percent') or 0)
            comm += amt * pct / 100.0
        total_comm += comm
        orders.append({
            'order_id': o.id,
            'order_number': o.order_number,
            'status': o.status,
            'commission_est': round(comm, 2),
        })
    return {'orders': orders, 'total_commission_est': round(total_comm, 2)}


def apply_oe_line_commissions(db, models, ledger_id: int, order_id: int, body: dict, user_id=None) -> dict:
    AcctSalesOrder = models['AcctSalesOrder']
    order = AcctSalesOrder.query.filter_by(id=order_id, ledger_id=ledger_id).first()
    if not order:
        raise ValueError('Order not found')
    lines = json.loads(order.lines_json or '[]') if getattr(order, 'lines_json', None) else []
    updates = {int(x['line_index']): float(x['commission_percent']) for x in (body.get('lines') or []) if 'line_index' in x}
    for idx, ln in enumerate(lines):
        if idx in updates:
            ln['commission_percent'] = updates[idx]
    order.lines_json = json.dumps(lines)
    write_audit(db, models, ledger_id, user_id=user_id, action='oe_commissions', entity_id=order_id, details=updates)
    return oe_commission_summary(db, models, ledger_id, order_id)


# --- Wave 5: Report designer depth ---

def save_enhanced_report_layout(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_core_gaps import list_report_layouts

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    layouts = settings.get('report_designer_layouts') or list_report_layouts(models, ledger_id)
    entry = {
        'id': body.get('id') or f"layout-{len(layouts) + 1}",
        'name': (body.get('name') or 'Custom layout')[:80],
        'report_type': body.get('report_type') or 'trial_balance',
        'columns': body.get('columns') or ['account_number', 'description', 'balance'],
        'parameters': body.get('parameters') or {},
        'comparative_period_b': body.get('comparative_period_b'),
        'updated_at': datetime.utcnow().isoformat() + 'Z',
    }
    replaced = False
    for i, lay in enumerate(layouts):
        if lay.get('id') == entry['id']:
            layouts[i] = entry
            replaced = True
            break
    if not replaced:
        layouts.append(entry)
    settings['report_designer_layouts'] = layouts[-80:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='report_layout_save', details={'id': entry['id']})
    return entry


def list_enhanced_report_layouts(db, models, ledger_id: int) -> dict:
    from accounting_core_gaps import list_report_layouts

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    layouts = settings.get('report_designer_layouts') or list_report_layouts(models, ledger_id)
    schedules = settings.get('scheduled_reports') or []
    return {'layouts': layouts, 'scheduled_reports': schedules}


def run_enhanced_layout_report(db, models, ledger_id: int, layout_id: str, params: dict | None = None) -> dict:
    from accounting_reports import run_report
    from accounting_parity_wave3 import comparative_income_statement

    layouts = list_enhanced_report_layouts(db, models, ledger_id)['layouts']
    layout = next((l for l in layouts if l.get('id') == layout_id), None)
    if not layout:
        raise ValueError('Layout not found')
    rtype = layout.get('report_type') or 'trial_balance'
    merged = {**(layout.get('parameters') or {}), **(params or {})}
    if rtype == 'comparative_income' and layout.get('comparative_period_b'):
        pa = merged.get('period_a') or date.today().strftime('%Y-%m')
        pb = layout.get('comparative_period_b')
        data = comparative_income_statement(db, models, ledger_id, pa, pb)
    else:
        data = run_report(db, models, ledger_id, rtype, merged)
    cols = layout.get('columns') or []
    rows = data.get('rows') or data.get('lines') or []
    if cols and rows and isinstance(rows[0], dict):
        rows = [{k: r.get(k) for k in cols if k in r} for r in rows]
    return {'layout_id': layout_id, 'report': data, 'projected_rows': rows[:500]}


# --- Wave 6: Fixed assets depth ---

def run_tax_book_depreciation(db, models, ledger_id: int, book: str = 'TAX', user_id=None) -> dict:
    from accounting_parity_wave2 import run_depreciation_book

    out = run_depreciation_book(db, models, ledger_id, book=book, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='fa_tax_depreciation', details={'book': book, **out})
    return out


def transfer_fixed_asset(db, models, ledger_id: int, asset_id: int, body: dict, user_id=None) -> dict:
    AcctFixedAsset = models['AcctFixedAsset']
    asset = AcctFixedAsset.query.filter_by(id=asset_id, ledger_id=ledger_id).first()
    if not asset:
        raise ValueError('Asset not found')
    if body.get('location_code'):
        if hasattr(asset, 'location_code'):
            asset.location_code = str(body['location_code'])[:40]
        elif hasattr(asset, 'location'):
            asset.location = str(body['location_code'])[:80]
    if body.get('department') and hasattr(asset, 'department'):
        asset.department = str(body['department'])[:80]
    write_audit(db, models, ledger_id, user_id=user_id, action='fa_transfer', entity_id=asset_id, details=body)
    loc = getattr(asset, 'location_code', None) or getattr(asset, 'location', None)
    return {'asset_id': asset_id, 'location': loc}


def mass_dispose_assets(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_operations import dispose_fixed_asset

    ids = [int(x) for x in (body.get('asset_ids') or [])]
    if not ids:
        raise ValueError('asset_ids required')
    disposed = []
    for aid in ids[:100]:
        try:
            dispose_fixed_asset(
                db, models, ledger_id, aid,
                disposal_date=body.get('disposal_date'),
                proceeds=float(body.get('proceeds') or 0),
            )
            disposed.append(aid)
        except Exception as exc:
            disposed.append({'id': aid, 'error': str(exc)})
    write_audit(db, models, ledger_id, user_id=user_id, action='fa_mass_dispose', details={'count': len(ids)})
    return {'disposed': disposed}


# --- Wave 6: Job cost + Pay Apps ---

def jobcost_with_pay_apps(db, models, ledger_id: int, project_id: int) -> dict:
    from accounting_all_chunks import jobcost_accounting_panel

    base = jobcost_accounting_panel(db, models, ledger_id, project_id)
    pay_apps = {'count': 0, 'total_billed': 0.0, 'total_retainage': 0.0, 'latest_period': None}
    try:
        from pay_app_persistence import get_pay_app_state

        _, state = get_pay_app_state(None, int(project_id))
        state = state or {}
        periods = state.get('periods') or state.get('payAppPeriods') or []
        if isinstance(periods, dict):
            periods = list(periods.values())
        pay_apps['count'] = len(periods)
        for p in periods:
            if not isinstance(p, dict):
                continue
            pay_apps['total_billed'] += float(
                p.get('currentPaymentDue') or p.get('current_payment_due') or p.get('amountDue') or 0
            )
            pay_apps['total_retainage'] += float(p.get('retainage') or p.get('retainageHeld') or 0)
            pn = p.get('periodNumber') or p.get('period_number') or p.get('applicationNumber')
            if pn is not None:
                pay_apps['latest_period'] = pn
    except Exception:
        pass
    pay_apps['total_billed'] = round(pay_apps['total_billed'], 2)
    pay_apps['total_retainage'] = round(pay_apps['total_retainage'], 2)
    base['pay_applications'] = pay_apps
    base['variance_billed_vs_ar'] = round(float(base.get('billed_ar') or 0) - pay_apps['total_billed'], 2)
    return base


# --- Wave 7: Route registration guard ---

def flask_endpoint_name_collisions(app) -> list[str]:
    seen = {}
    dups = []
    for rule in app.url_map.iter_rules():
        ep = rule.endpoint
        if ep in seen and seen[ep] != rule.rule:
            dups.append(ep)
        seen[ep] = rule.rule
    return sorted(set(dups))
