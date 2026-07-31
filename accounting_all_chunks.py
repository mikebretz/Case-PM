"""
All priority accounting chunks — core-5 depth, bank/payments, distribution, payroll, construction.

Built on parity wave 2/3; extends behavior without replacing existing modules.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import date, datetime

from accounting_platform import write_audit


# --- Chunk 1: Core-5 helpers ---

def allowed_screens_for_ledger(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    settings = _parse_settings(ledger)
    perms = settings.get('screen_permissions') or {}
    if perms and all(isinstance(v, bool) for v in perms.values()):
        return perms
    # default: all module routes on
    routes = [
        'dashboard', 'gl', 'ap', 'ar', 'bank', 'tax', 'assets', 'inventory', 'oe', 'po',
        'jobcost', 'payroll', 'payments', 'reports', 'consolidation', 'admin',
    ]
    return {r: perms.get(r, True) if isinstance(perms.get(r), bool) else True for r in routes}


def screen_for_api_path(path: str) -> str | None:
    if not path.startswith('/api/accounting/'):
        return None
    rest = path[len('/api/accounting/'):]
    if rest.startswith('platform/') or rest.startswith('settings'):
        return 'admin'
    prefix = rest.split('/')[0]
    mapping = {
        'gl': 'gl', 'ap': 'ap', 'ar': 'ar', 'bank': 'bank', 'tax': 'tax', 'assets': 'assets',
        'inventory': 'inventory', 'oe': 'oe', 'po': 'po', 'payroll': 'payroll', 'payments': 'payments',
        'reports': 'reports', 'bi': 'reports', 'consolidation': 'consolidation', 'jobcost': 'jobcost',
        'dashboard': 'dashboard',
    }
    return mapping.get(prefix)


def download_auditor_package_bytes(db, models, parent_ledger_id: int, as_of: str = None) -> bytes:
    from accounting_parity_wave3 import auditor_package

    payload = auditor_package(db, models, parent_ledger_id, as_of=as_of)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('auditor_package.json', json.dumps(payload, indent=2))
        zf.writestr('readme.txt', 'Case PM consolidated auditor package — import JSON into your workpapers tool.')
    return buf.getvalue()


# --- Chunk 2: Bank + payments ---

def stripe_runtime_config(ledger) -> dict:
    from accounting_payment_processing import payment_processor_settings

    pp = payment_processor_settings(ledger)
    secret = (os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('CASEPM_STRIPE_SECRET_KEY') or '').strip()
    publishable = (os.environ.get('STRIPE_PUBLISHABLE_KEY') or os.environ.get('CASEPM_STRIPE_PUBLISHABLE_KEY') or '').strip()
    live = bool(secret and not secret.startswith('sk_test'))
    return {
        'processor': pp.get('processor') or ('stripe' if secret else 'none'),
        'stripe_configured': bool(secret),
        'publishable_key': publishable[:12] + '…' if publishable else '',
        'mode': 'live' if live else ('test' if secret else 'off'),
        'webhook_path': '/api/accounting/payments/stripe-webhook',
    }


def bank_auto_match_suggestions(db, models, ledger_id: int, bank_account_id: int) -> dict:
    """Suggest bank tx ↔ AP payment / AR receipt matches by amount."""
    AcctBankTransaction = models['AcctBankTransaction']
    AcctAPPayment = models['AcctAPPayment']
    AcctARReceipt = models['AcctARReceipt']
    txs = AcctBankTransaction.query.filter_by(bank_account_id=int(bank_account_id), reconciled=False).all()
    suggestions = []
    for tx in txs[:100]:
        amt = round(float(tx.amount or 0), 2)
        if amt == 0:
            continue
        if amt < 0:
            pay = AcctAPPayment.query.filter_by(ledger_id=ledger_id, status='Posted').order_by(
                AcctAPPayment.id.desc(),
            ).limit(200).all()
            for p in pay:
                if abs(round(float(p.amount or 0), 2) + amt) < 0.02:
                    suggestions.append({
                        'bank_transaction_id': tx.id,
                        'match_type': 'ap_payment',
                        'match_id': p.id,
                        'confidence': 'amount',
                    })
                    break
        else:
            rec = AcctARReceipt.query.filter_by(ledger_id=ledger_id, status='Posted').order_by(
                AcctARReceipt.id.desc(),
            ).limit(200).all()
            for r in rec:
                if abs(round(float(r.amount or 0), 2) - amt) < 0.02:
                    suggestions.append({
                        'bank_transaction_id': tx.id,
                        'match_type': 'ar_receipt',
                        'match_id': r.id,
                        'confidence': 'amount',
                    })
                    break
    return {'suggestions': suggestions}


def positive_pay_export(db, models, ledger_id: int, payment_batch_id: int) -> str:
    from accounting_payment_processing import batch_lines

    AcctPaymentBatch = models['AcctPaymentBatch']
    AcctVendor = models['AcctVendor']
    batch = AcctPaymentBatch.query.filter_by(id=payment_batch_id, ledger_id=ledger_id).first()
    if not batch:
        raise ValueError('Payment batch not found')
    lines = batch_lines(models['AcctPaymentBatchLine'], batch.id)
    out = io.StringIO()
    out.write('PositivePay|CasePM\n')
    check_no = batch.check_number_start or '1000'
    try:
        num = int(check_no)
    except ValueError:
        num = 1000
    for ln in lines:
        v = AcctVendor.query.get(ln.vendor_id)
        out.write(f"{num}|{round(float(ln.amount or 0), 2)}|{v.name if v else ''}\n")
        num += 1
    return out.getvalue()


# --- Chunk 3: Distribution IC/OE/PO → GL ---

def set_item_costing(db, models, ledger_id: int, item_id: int, method: str):
    AcctInventoryItem = models['AcctInventoryItem']
    item = AcctInventoryItem.query.filter_by(id=item_id, ledger_id=ledger_id).first()
    if not item:
        raise ValueError('Item not found')
    m = (method or 'average').lower()
    if m not in ('average', 'fifo', 'standard'):
        raise ValueError('costing_method must be average, fifo, or standard')
    item.costing_method = m
    db.session.flush()
    return {'item_id': item.id, 'costing_method': item.costing_method}


def po_receive_create_ap_invoice(db, models, ledger_id: int, po_id: int, user_id=None):
    """After PO receive, create open AP invoice linked to PO."""
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    AcctAPDocument = models['AcctAPDocument']
    po = AcctPurchaseOrder.query.filter_by(id=po_id, ledger_id=ledger_id).first()
    if not po:
        raise ValueError('PO not found')
    amt = float(po.total_amount or 0)
    if amt <= 0:
        raise ValueError('PO has no amount')
    existing = AcctAPDocument.query.filter_by(ledger_id=ledger_id, purchase_order_id=po.id, status='Open').first()
    if existing:
        return {'invoice_id': existing.id, 'created': False}
    inv = AcctAPDocument(
        ledger_id=ledger_id,
        vendor_id=po.vendor_id,
        document_number=f'PO-{po.po_number}'[:40],
        document_type='Invoice',
        document_date=date.today(),
        due_date=date.today(),
        amount=amt,
        gross_amount=amt,
        status='Open',
        purchase_order_id=po.id,
    )
    db.session.add(inv)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='po_voucher', entity_type='ap_invoice', entity_id=inv.id)
    return {'invoice_id': inv.id, 'created': True}


def oe_ship_post_cogs(db, models, ledger_id: int, order_id: int, user_id=None):
    """Post COGS / inventory relief journal for shipped OE (simplified)."""
    from accounting_parity_wave3 import inventory_fifo_issue
    from accounting_posting import load_accounting_options, _account_by_number
    from accounting_persistence import next_batch_number, post_journal_batch

    AcctSalesOrder = models['AcctSalesOrder']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctGLAccount = models['AcctGLAccount']
    AcctLedger = models['AcctLedger']

    order = AcctSalesOrder.query.filter_by(id=order_id, ledger_id=ledger_id).first()
    if not order:
        raise ValueError('Sales order not found')
    lines = json.loads(order.lines_json or '[]')
    total_cogs = 0.0
    for ln in lines:
        iid = ln.get('item_id')
        qty = float(ln.get('qty') or 0)
        if iid and qty > 0:
            try:
                out = inventory_fifo_issue(db, models, ledger_id, int(iid), qty, reference=order.order_number)
                total_cogs += float(out.get('cogs') or 0)
            except ValueError:
                total_cogs += qty * float(ln.get('unit_cost') or 0)
    if total_cogs <= 0:
        total_cogs = float(order.total_amount or 0) * 0.6
    opts = load_accounting_options()
    cogs = _account_by_number(AcctGLAccount, ledger_id, opts.get('materials_expense', '5000'))
    inv = _account_by_number(AcctGLAccount, ledger_id, opts.get('inventory_account', '1200'))
    batch = AcctJournalBatch(
        ledger_id=ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, ledger_id),
        source='OE',
        description=f'COGS ship {order.order_number}'[:300],
        batch_date=date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=1, account_id=cogs.id,
        debit=total_cogs, credit=0, description='COGS',
    ))
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=2, account_id=inv.id,
        debit=0, credit=total_cogs, description='Inventory relief',
    ))
    ledger = AcctLedger.query.get(ledger_id)
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
    order.status = 'Shipped'
    db.session.flush()
    return {'journal_batch_id': batch.id, 'cogs': round(total_cogs, 2)}


# --- Chunk 4: Payroll + tax depth ---

STATE_INCOME_TAX = {
    'AL': 0.05, 'AK': 0.0, 'AZ': 0.025, 'AR': 0.044, 'CA': 0.08, 'CO': 0.045, 'CT': 0.05,
    'DE': 0.055, 'FL': 0.0, 'GA': 0.055, 'HI': 0.08, 'ID': 0.058, 'IL': 0.0495, 'IN': 0.0323,
    'IA': 0.06, 'KS': 0.057, 'KY': 0.045, 'LA': 0.0425, 'ME': 0.07, 'MD': 0.05, 'MA': 0.05,
    'MI': 0.0425, 'MN': 0.07, 'MS': 0.05, 'MO': 0.05, 'MT': 0.06, 'NE': 0.05, 'NV': 0.0,
    'NH': 0.0, 'NJ': 0.06, 'NM': 0.05, 'NY': 0.065, 'NC': 0.0475, 'ND': 0.025, 'OH': 0.035,
    'OK': 0.0475, 'OR': 0.08, 'PA': 0.0307, 'RI': 0.06, 'SC': 0.065, 'SD': 0.0, 'TN': 0.0,
    'TX': 0.0, 'UT': 0.0485, 'VT': 0.06, 'VA': 0.0575, 'WA': 0.0, 'WV': 0.06, 'WI': 0.06, 'WY': 0.0,
}


def payroll_tax_package(db, models, ledger_id: int, tax_year: int) -> dict:
    from accounting_parity_wave3 import export_form_941_summary, export_w2_summary

    y = int(tax_year)
    return {
        'tax_year': y,
        'form_941_by_quarter': [
            export_form_941_summary(db, models, ledger_id, q, y) for q in range(1, 5)
        ],
        'w2': export_w2_summary(db, models, ledger_id, y),
        'state_withholding_table': STATE_INCOME_TAX,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'disclaimer': 'CPA review required before agency filing.',
    }


def garnishment_stub_deduction(db, models, ledger_id: int, employee_id: int, amount: float, case_number: str):
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    emp = AcctPayrollEmployee.query.filter_by(id=employee_id, ledger_id=ledger_id).first()
    if not emp:
        raise ValueError('Employee not found')
    AcctPayrollDeduction = models['AcctPayrollDeduction']
    code = f'GARN-{case_number[:10]}'
    d = AcctPayrollDeduction.query.filter_by(ledger_id=ledger_id, code=code).first()
    if not d:
        d = AcctPayrollDeduction(ledger_id=ledger_id, code=code, description=f'Garnishment {case_number}', calc_method='fixed', amount=float(amount))
        db.session.add(d)
        db.session.flush()
    return {'deduction_id': d.id, 'code': d.code}


# --- Chunk 5: Construction-native accounting ---

def jobcost_accounting_panel(db, models, ledger_id: int, project_id: int) -> dict:
    from accounting_parity_wave2 import revenue_recognition_schedule

    AcctARDocument = models['AcctARDocument']
    AcctAPDocument = models['AcctAPDocument']
    AcctJournalLine = models['AcctJournalLine']
    pid = int(project_id)
    ar = sum(float(d.amount or 0) for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, project_id=pid).all())
    ap = sum(float(d.amount or 0) for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, project_id=pid).all())
    AcctJournalBatch = models['AcctJournalBatch']
    gl = 0.0
    for ln in AcctJournalLine.query.filter_by(project_id=pid).all():
        batch = AcctJournalBatch.query.get(ln.batch_id)
        if not batch or batch.ledger_id != ledger_id:
            continue
        gl += float(ln.debit or 0) - float(ln.credit or 0)
    rev = revenue_recognition_schedule(db, models, ledger_id, pid)
    return {
        'project_id': pid,
        'billed_ar': round(ar, 2),
        'committed_ap': round(ap, 2),
        'gl_job_cost_net': round(gl, 2),
        'revenue_recognition': rev,
        'links': {
            'budget': f'/budget?project_id={pid}',
            'pay_apps': f'/pay-applications?project_id={pid}',
            'commitments': f'/commitments?project_id={pid}',
        },
    }


def apply_progress_billing_to_ar(db, models, ledger_id: int, customer_id: int, amount: float, project_id: int, document_number: str, user_id=None):
    """Create AR invoice from progress billing amount (G702-style handoff)."""
    AcctARDocument = models['AcctARDocument']
    doc = AcctARDocument(
        ledger_id=ledger_id,
        customer_id=int(customer_id),
        document_number=(document_number or f'G702-{date.today().strftime("%Y%m%d")}')[:40],
        document_type='Progress Invoice',
        document_date=date.today(),
        due_date=date.today(),
        amount=float(amount),
        status='Open',
        project_id=int(project_id) if project_id else None,
    )
    doc.details_json = json.dumps({'source': 'progress_billing', 'project_id': project_id})
    db.session.add(doc)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='progress_billing_ar', entity_id=doc.id)
    return {'ar_document_id': doc.id}
