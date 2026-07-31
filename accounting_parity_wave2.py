"""
Accounting parity wave 2 — broad gap closure across BK, TX, FA, IC, OE, PO, AR, AP, GL, CON, PR, PP, BI, ADM.

Implements workable depth on top of existing Case PM accounting architecture (not literal Sage 300 clone).
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    if not ledger or not getattr(ledger, 'settings_json', None):
        return {}
    try:
        return json.loads(ledger.settings_json) or {}
    except Exception:
        return {}


def _save_ledger_settings(ledger, settings: dict):
    ledger.settings_json = json.dumps(settings)


# --- Dashboard / BI KPIs ---

def extended_dashboard_kpis(db, models, ledger_id: int) -> dict:
    AcctJournalBatch = models['AcctJournalBatch']
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    AcctPayrollRun = models['AcctPayrollRun']
    AcctConsolidationRun = models['AcctConsolidationRun']
    AcctInventoryItem = models['AcctInventoryItem']
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    AcctSalesOrder = models['AcctSalesOrder']
    AcctCreditReview = models.get('AcctCreditReview')

    open_ap = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    open_ar = AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    credit_reviews = 0
    if AcctCreditReview:
        credit_reviews = AcctCreditReview.query.filter_by(ledger_id=ledger_id, status='Open').count()

    return {
        'open_ap_documents': open_ap,
        'open_ar_documents': open_ar,
        'posted_payroll_runs': AcctPayrollRun.query.filter_by(ledger_id=ledger_id, status='Posted').count(),
        'consolidation_runs': AcctConsolidationRun.query.filter_by(parent_ledger_id=ledger_id).count(),
        'inventory_skus': AcctInventoryItem.query.filter_by(ledger_id=ledger_id).count(),
        'open_pos': AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id, status='Open').count(),
        'open_sales_orders': AcctSalesOrder.query.filter_by(ledger_id=ledger_id, status='Open').count(),
        'credit_reviews_open': credit_reviews,
        'cash_ratio': round(open_ar / max(open_ap, 1), 2),
    }


def kpi_dashboard(db, models, ledger_id: int) -> dict:
    from accounting_persistence import ap_aging, ar_aging, trial_balance
    from accounting_module_service import build_company_dashboard

    base = build_company_dashboard(db, models)
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    tb = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    ap = ap_aging(models['AcctAPDocument'], ledger_id)
    ar = ar_aging(models['AcctARDocument'], ledger_id)

    revenue = sum(r['balance'] for r in tb if (r.get('account_type') or '').lower() == 'revenue')
    expense = sum(r['balance'] for r in tb if (r.get('account_type') or '').lower() == 'expense')
    tiles = [
        {'id': 'open_ap', 'label': 'Open A/P', 'value': round(sum(ap['buckets'].values()), 2), 'format': 'money'},
        {'id': 'open_ar', 'label': 'Open A/R', 'value': round(sum(ar['buckets'].values()), 2), 'format': 'money'},
        {'id': 'net_income_tb', 'label': 'Net income (TB)', 'value': round(-revenue - expense, 2), 'format': 'money'},
        {'id': 'open_batches', 'label': 'Open J/E batches', 'value': base['kpis'].get('open_batches', 0), 'format': 'int'},
    ]
    tiles.extend(
        {'id': k, 'label': k.replace('_', ' ').title(), 'value': v, 'format': 'int' if isinstance(v, int) else 'number'}
        for k, v in extended_dashboard_kpis(db, models, ledger_id).items()
        if k != 'cash_ratio'
    )
    return {'tiles': tiles, 'generated_at': datetime.utcnow().isoformat() + 'Z'}


# --- Bank ---

def list_distribution_codes(models, ledger_id: int):
    M = models['AcctBankDistributionCode']
    rows = M.query.filter_by(ledger_id=ledger_id).order_by(M.code).all()
    return [
        {
            'id': r.id,
            'code': r.code,
            'name': r.name,
            'lines': json.loads(r.lines_json or '[]'),
            'is_active': bool(r.is_active),
        }
        for r in rows
    ]


def save_distribution_code(db, models, ledger_id: int, body: dict, code_id=None):
    M = models['AcctBankDistributionCode']
    code = (body.get('code') or '').strip().upper()
    if not code:
        raise ValueError('code required')
    row = M.query.filter_by(id=code_id, ledger_id=ledger_id).first() if code_id else None
    if not row:
        row = M(ledger_id=ledger_id, code=code)
        db.session.add(row)
    row.code = code
    row.name = (body.get('name') or code)[:120]
    row.lines_json = json.dumps(body.get('lines') or [])
    row.is_active = 1 if body.get('is_active', True) else 0
    db.session.flush()
    return row.id


def apply_distribution_to_deposit(db, models, ledger_id: int, bank_account_id: int, amount: float, dist_code: str, **kwargs):
    from accounting_bank_service import record_manual_bank_transaction

    M = models['AcctBankDistributionCode']
    row = M.query.filter_by(ledger_id=ledger_id, code=dist_code.strip().upper(), is_active=1).first()
    if not row:
        raise ValueError('Distribution code not found')
    lines = json.loads(row.lines_json or '[]')
    if not lines:
        raise ValueError('Distribution code has no lines')
    AcctGLAccount = models['AcctGLAccount']
    total_pct = sum(float(ln.get('percent') or 0) for ln in lines)
    if total_pct <= 0:
        raise ValueError('Distribution percents must sum > 0')
    amt = float(amount)
    batch_ids = []
    for ln in lines:
        pct = float(ln.get('percent') or 0) / total_pct
        piece = round(amt * pct, 2)
        acct_id = ln.get('account_id')
        if not acct_id:
            num = (ln.get('account_number') or '').strip()
            acct = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number=num).first()
            acct_id = acct.id if acct else None
        if not acct_id:
            continue
        out = record_manual_bank_transaction(
            db, models,
            ledger_id=ledger_id,
            bank_account_id=bank_account_id,
            amount=piece,
            description=f"Dist {dist_code}: {row.name}",
            transaction_type='Deposit',
            post_gl=True,
            offset_account_id=int(acct_id),
            user_id=kwargs.get('user_id'),
        )
        if out.get('journal_batch_id'):
            batch_ids.append(out['journal_batch_id'])
    return {'distribution_code': dist_code, 'journal_batch_ids': batch_ids}


def parse_ofx_simple(text: str) -> list[dict]:
    """Minimal OFX/QFX transaction extract (STMTTRN blocks)."""
    txs = []
    for block in re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, re.I | re.S):
        def tag(name):
            m = re.search(rf'<{name}>([^<\n]+)', block, re.I)
            return (m.group(1).strip() if m else '')

        amt = tag('TRNAMT')
        if not amt:
            continue
        dt = tag('DTPOSTED')[:8]
        try:
            tdate = date(int(dt[0:4]), int(dt[4:6]), int(dt[6:8])) if len(dt) >= 8 else date.today()
        except Exception:
            tdate = date.today()
        txs.append({
            'amount': float(amt),
            'transaction_date': tdate.isoformat(),
            'description': tag('NAME') or tag('MEMO') or 'OFX import',
            'reference': tag('FITID') or tag('CHECKNUM') or '',
        })
    return txs


def import_bank_ofx(db, models, ledger_id: int, bank_account_id: int, ofx_text: str, user_id=None):
    from accounting_bank_service import record_manual_bank_transaction

    imported = 0
    for row in parse_ofx_simple(ofx_text or ''):
        record_manual_bank_transaction(
            db, models,
            ledger_id=ledger_id,
            bank_account_id=bank_account_id,
            amount=row['amount'],
            description=row['description'],
            reference=row['reference'],
            transaction_type='OFX',
            transaction_date=date.fromisoformat(row['transaction_date']),
            post_gl=False,
            user_id=user_id,
        )
        imported += 1
    write_audit(db, models, ledger_id, user_id=user_id, action='bank_ofx_import', details={'count': imported})
    return {'imported': imported}


def record_nsf(db, models, ledger_id: int, body: dict, user_id=None):
    """Mark receipt reversed, fee, and optional customer charge."""
    AcctBankTransaction = models['AcctBankTransaction']
    AcctARReceipt = models['AcctARReceipt']
    AcctNSFRecord = models['AcctNSFRecord']
    tx_id = body.get('bank_transaction_id')
    fee = float(body.get('nsf_fee') or 0)
    receipt_id = body.get('receipt_id')
    tx = AcctBankTransaction.query.get(int(tx_id)) if tx_id else None
    if not tx:
        raise ValueError('bank_transaction_id required')
    bank = models['AcctBankAccount'].query.get(tx.bank_account_id)
    if not bank or bank.ledger_id != ledger_id:
        raise ValueError('Invalid bank transaction')

    rec = AcctNSFRecord(
        ledger_id=ledger_id,
        bank_transaction_id=tx.id,
        receipt_id=int(receipt_id) if receipt_id else None,
        nsf_fee=fee,
        status='Open',
        notes=(body.get('notes') or '')[:500],
    )
    db.session.add(rec)
    tx.transaction_type = 'NSF'
    tx.description = (tx.description or '')[:250] + ' [NSF]'
    if receipt_id:
        r = AcctARReceipt.query.filter_by(id=int(receipt_id), ledger_id=ledger_id).first()
        if r:
            r.status = 'NSF'
    if fee:
        from accounting_bank_service import record_manual_bank_transaction
        record_manual_bank_transaction(
            db, models,
            ledger_id=ledger_id,
            bank_account_id=bank.id,
            amount=-abs(fee),
            description='NSF fee',
            transaction_type='NSF',
            post_gl=bool(body.get('post_gl', True)),
            user_id=user_id,
        )
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='nsf_record', entity_type='nsf', entity_id=rec.id)
    return {'nsf_id': rec.id}


# --- Tax ---

def tax_group_with_components(tg) -> dict:
    comps = []
    try:
        comps = json.loads(getattr(tg, 'components_json', None) or '[]')
    except Exception:
        comps = []
    return {
        'id': tg.id,
        'code': tg.code,
        'description': tg.description,
        'rate_percent': tg.rate_percent,
        'tax_type': tg.tax_type,
        'applies_to': tg.applies_to,
        'authority': tg.authority,
        'is_active': bool(tg.is_active),
        'components': comps,
        'effective_rate': sum(float(c.get('rate_percent') or 0) for c in comps) or float(tg.rate_percent or 0),
    }


def save_tax_components(db, models, ledger_id: int, group_id: int, components: list):
    AcctTaxGroup = models['AcctTaxGroup']
    tg = AcctTaxGroup.query.filter_by(id=group_id, ledger_id=ledger_id).first()
    if not tg:
        raise ValueError('Tax group not found')
    tg.components_json = json.dumps(components or [])
    total = sum(float(c.get('rate_percent') or 0) for c in (components or []))
    if total > 0:
        tg.rate_percent = round(total, 4)
    db.session.flush()
    return tax_group_with_components(tg)


def calculate_line_taxes(amount: float, tax_group, qty: float = 1) -> dict:
    base = float(amount or 0) * float(qty or 1)
    comps = []
    try:
        comps = json.loads(getattr(tax_group, 'components_json', None) or '[]')
    except Exception:
        comps = []
    lines = []
    if comps:
        for c in comps:
            rate = float(c.get('rate_percent') or 0)
            tax_amt = round(base * rate / 100.0, 2)
            lines.append({'name': c.get('name') or 'Tax', 'rate_percent': rate, 'tax_amount': tax_amt})
    else:
        rate = float(getattr(tax_group, 'rate_percent', 0) or 0)
        lines.append({'name': 'Tax', 'rate_percent': rate, 'tax_amount': round(base * rate / 100.0, 2)})
    total_tax = round(sum(l['tax_amount'] for l in lines), 2)
    return {'taxable_amount': base, 'tax_lines': lines, 'total_tax': total_tax, 'total_with_tax': round(base + total_tax, 2)}


def tax_filing_prep(db, models, ledger_id: int, period_key: str) -> dict:
    """Summarize collected tax by group for a YYYY-MM period."""
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    AcctTaxGroup = models['AcctTaxGroup']
    groups = {g.code: tax_group_with_components(g) for g in AcctTaxGroup.query.filter_by(ledger_id=ledger_id).all()}
    summary = {code: {'collected': 0.0, 'paid': 0.0} for code in groups}

    def bump(doc, sign=1):
        try:
            det = json.loads(doc.details_json or '{}')
        except Exception:
            det = {}
        code = det.get('tax_group_code')
        tax_amt = float(det.get('tax_amount') or 0)
        if code and code in summary:
            key = 'collected' if sign > 0 else 'paid'
            summary[code][key] += tax_amt

    pk = period_key or date.today().strftime('%Y-%m')
    for doc in AcctARDocument.query.filter_by(ledger_id=ledger_id).all():
        if doc.document_date and doc.document_date.strftime('%Y-%m') == pk:
            bump(doc, 1)
    for doc in AcctAPDocument.query.filter_by(ledger_id=ledger_id).all():
        if doc.document_date and doc.document_date.strftime('%Y-%m') == pk:
            bump(doc, -1)

    return {'period_key': pk, 'jurisdictions': summary, 'groups': list(groups.values())}


def apply_tax_to_document(db, models, ledger_id: int, doc_type: str, doc_id: int, tax_group_code: str):
    AcctTaxGroup = models['AcctTaxGroup']
    tg = AcctTaxGroup.query.filter_by(ledger_id=ledger_id, code=tax_group_code.strip().upper()).first()
    if not tg:
        raise ValueError('Tax group not found')
    Model = models['AcctARDocument'] if doc_type.lower() == 'ar' else models['AcctAPDocument']
    doc = Model.query.filter_by(id=doc_id, ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Document not found')
    calc = calculate_line_taxes(float(doc.amount or 0), tg)
    det = {}
    try:
        det = json.loads(doc.details_json or '{}')
    except Exception:
        det = {}
    det['tax_group_code'] = tg.code
    det['tax_amount'] = calc['total_tax']
    det['tax_lines'] = calc['tax_lines']
    doc.details_json = json.dumps(det)
    if hasattr(doc, 'gross_amount'):
        doc.gross_amount = float(doc.amount or 0) + calc['total_tax']
    db.session.flush()
    return {'document_id': doc.id, **calc}


# --- Fixed assets ---

def depreciation_amount(cost: float, salvage: float, life_months: int, method: str, months_elapsed: int) -> float:
    depreciable = max(float(cost) - float(salvage or 0), 0)
    life = max(int(life_months or 1), 1)
    method = (method or 'straight_line').lower()
    if method in ('ddb', 'double_declining'):
        rate = 2.0 / life
        book = depreciable
        dep = 0.0
        for _ in range(min(months_elapsed, life)):
            period = min(book * rate, book - float(salvage or 0))
            dep += period
            book -= period
        return round(dep, 2)
    if method in ('syd', 'sum_of_years'):
        n = life
        syd = n * (n + 1) / 2
        dep = 0.0
        for m in range(min(months_elapsed, life)):
            year_fraction = (n - (m // 12)) / syd
            dep += depreciable * year_fraction / 12
        return round(dep, 2)
    monthly = depreciable / life
    return round(monthly * min(months_elapsed, life), 2)


def run_depreciation_book(db, models, ledger_id: int, book: str = 'GAAP', user_id=None):
    """Post depreciation for assets in a given book."""
    from accounting_posting import run_depreciation

    AcctFixedAsset = models['AcctFixedAsset']
    AcctFixedAsset.query.filter_by(ledger_id=ledger_id, book=(book or 'GAAP')[:20], status='Active').count()
    return run_depreciation(db, models, user_id=user_id)


# --- Inventory ---

def list_lots(models, ledger_id: int, item_id: int = None):
    M = models['AcctInventoryLot']
    q = M.query.filter_by(ledger_id=ledger_id)
    if item_id:
        q = q.filter_by(item_id=item_id)
    return [
        {
            'id': r.id,
            'item_id': r.item_id,
            'lot_number': r.lot_number,
            'serial_number': r.serial_number,
            'qty_on_hand': r.qty_on_hand,
            'unit_cost': r.unit_cost,
        }
        for r in q.all()
    ]


def receive_lot(db, models, ledger_id: int, item_id: int, qty: float, lot_number: str = '', serial_number: str = '', unit_cost: float = 0):
    M = models['AcctInventoryLot']
    AcctInventoryItem = models['AcctInventoryItem']
    item = AcctInventoryItem.query.filter_by(id=item_id, ledger_id=ledger_id).first()
    if not item:
        raise ValueError('Item not found')
    lot = M.query.filter_by(ledger_id=ledger_id, item_id=item_id, lot_number=(lot_number or 'DEFAULT')[:40]).first()
    if not lot:
        lot = M(ledger_id=ledger_id, item_id=item_id, lot_number=(lot_number or 'DEFAULT')[:40], serial_number=(serial_number or '')[:80])
        db.session.add(lot)
    lot.qty_on_hand = float(lot.qty_on_hand or 0) + float(qty)
    if unit_cost:
        lot.unit_cost = float(unit_cost)
    item.qty_on_hand = float(item.qty_on_hand or 0) + float(qty)
    if unit_cost and (item.costing_method or 'average') == 'average':
        old = float(item.unit_cost or 0)
        old_q = float(item.qty_on_hand or 0) - float(qty)
        if old_q + float(qty) > 0:
            item.unit_cost = round((old * old_q + float(unit_cost) * float(qty)) / (old_q + float(qty)), 4)
    db.session.flush()
    return {'lot_id': lot.id, 'qty_on_hand': lot.qty_on_hand}


# --- PO / OE ---

def create_blanket_po(db, models, ledger_id: int, body: dict):
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    po = AcctPurchaseOrder(
        ledger_id=ledger_id,
        vendor_id=body.get('vendor_id'),
        po_number=(body.get('po_number') or f'BL-{datetime.utcnow().strftime("%H%M%S")}')[:40],
        status='Open',
        order_date=date.today(),
        total_amount=float(body.get('blanket_limit') or 0),
        lines_json=json.dumps(body.get('lines') or []),
    )
    po.po_type = 'Blanket'
    po.blanket_limit = float(body.get('blanket_limit') or 0)
    po.drop_ship = 1 if body.get('drop_ship') else 0
    db.session.add(po)
    db.session.flush()
    return po


def release_blanket_po(db, models, ledger_id: int, po_id: int, amount: float, lines: list):
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    parent = AcctPurchaseOrder.query.filter_by(id=po_id, ledger_id=ledger_id).first()
    if not parent or getattr(parent, 'po_type', '') != 'Blanket':
        raise ValueError('Blanket PO not found')
    released = float(amount or 0)
    if released + sum(float(x.get('amount') or 0) for x in json.loads(parent.releases_json or '[]')) > float(parent.blanket_limit or parent.total_amount or 0):
        raise ValueError('Release exceeds blanket limit')
    rels = json.loads(parent.releases_json or '[]')
    rels.append({'date': date.today().isoformat(), 'amount': released, 'lines': lines or []})
    parent.releases_json = json.dumps(rels)
    child = AcctPurchaseOrder(
        ledger_id=ledger_id,
        vendor_id=parent.vendor_id,
        po_number=f"{parent.po_number}-R{len(rels)}",
        status='Open',
        order_date=date.today(),
        total_amount=released,
        lines_json=json.dumps(lines or []),
        parent_po_id=parent.id,
    )
    child.po_type = 'Release'
    db.session.add(child)
    db.session.flush()
    return {'release_po_id': child.id, 'release_number': len(rels)}


def create_quote(db, models, ledger_id: int, body: dict):
    AcctSalesOrder = models['AcctSalesOrder']
    so = AcctSalesOrder(
        ledger_id=ledger_id,
        customer_id=body.get('customer_id'),
        order_number=(body.get('order_number') or f'Q-{datetime.utcnow().strftime("%H%M%S")}')[:40],
        status='Quote',
        order_date=date.today(),
        total_amount=float(body.get('total_amount') or 0),
        lines_json=json.dumps(body.get('lines') or []),
    )
    so.order_type = 'Quote'
    db.session.add(so)
    db.session.flush()
    return so


def convert_quote_to_order(db, models, ledger_id: int, quote_id: int):
    AcctSalesOrder = models['AcctSalesOrder']
    q = AcctSalesOrder.query.filter_by(id=quote_id, ledger_id=ledger_id).first()
    if not q or getattr(q, 'order_type', '') != 'Quote':
        raise ValueError('Quote not found')
    q.status = 'Open'
    q.order_type = 'Order'
    q.order_number = q.order_number.replace('Q-', 'SO-', 1) if q.order_number.startswith('Q-') else f"SO-{q.order_number}"
    db.session.flush()
    return q


def create_sales_return(db, models, ledger_id: int, body: dict):
    AcctSalesOrder = models['AcctSalesOrder']
    so = AcctSalesOrder(
        ledger_id=ledger_id,
        customer_id=body.get('customer_id'),
        order_number=(body.get('order_number') or f'RT-{datetime.utcnow().strftime("%H%M%S")}')[:40],
        status='Open',
        order_date=date.today(),
        total_amount=-abs(float(body.get('total_amount') or 0)),
        lines_json=json.dumps(body.get('lines') or []),
    )
    so.order_type = 'Return'
    db.session.add(so)
    db.session.flush()
    return so


# --- AR ---

def summary_billing_invoice(db, models, ledger_id: int, parent_customer_id: int, child_customer_ids: list, user_id=None):
    """Roll open child invoices into one parent summary invoice."""
    AcctCustomer = models['AcctCustomer']
    AcctARDocument = models['AcctARDocument']
    parent = AcctCustomer.query.filter_by(id=parent_customer_id, ledger_id=ledger_id).first()
    if not parent:
        raise ValueError('Parent customer not found')
    total = 0.0
    refs = []
    for cid in child_customer_ids or []:
        for doc in AcctARDocument.query.filter_by(ledger_id=ledger_id, customer_id=int(cid), status='Open').all():
            total += float(doc.amount or 0)
            refs.append(doc.id)
            doc.status = 'Summarized'
    if total <= 0:
        raise ValueError('No open amounts to summarize')
    inv = AcctARDocument(
        ledger_id=ledger_id,
        customer_id=parent.id,
        document_number=f"SUM-{date.today().strftime('%Y%m%d')}-{parent.code}"[:40],
        document_type='Summary Invoice',
        document_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        amount=round(total, 2),
        status='Open',
        parent_document_id=None,
    )
    inv.details_json = json.dumps({'summary_child_doc_ids': refs, 'national_account': parent.national_account_code})
    db.session.add(inv)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='summary_billing', entity_type='ar_invoice', entity_id=inv.id)
    return {'invoice_id': inv.id, 'amount': inv.amount, 'consolidated_count': len(refs)}


def credit_review_queue(db, models, ledger_id: int):
    M = models['AcctCreditReview']
    AcctCustomer = models['AcctCustomer']
    rows = M.query.filter_by(ledger_id=ledger_id).order_by(M.created_at.desc()).limit(200).all()
    out = []
    for r in rows:
        c = AcctCustomer.query.get(r.customer_id)
        out.append({
            'id': r.id,
            'customer_id': r.customer_id,
            'customer_code': c.code if c else '',
            'status': r.status,
            'reason': r.reason,
            'requested_limit': r.requested_limit,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        })
    return out


def submit_credit_review(db, models, ledger_id: int, body: dict, user_id=None):
    M = models['AcctCreditReview']
    row = M(
        ledger_id=ledger_id,
        customer_id=int(body['customer_id']),
        status='Open',
        reason=(body.get('reason') or '')[:300],
        requested_limit=float(body.get('requested_limit') or 0),
    )
    db.session.add(row)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='credit_review_submit', entity_id=row.id)
    return {'review_id': row.id}


def resolve_credit_review(db, models, ledger_id: int, review_id: int, body: dict, user_id=None):
    M = models['AcctCreditReview']
    AcctCustomer = models['AcctCustomer']
    row = M.query.filter_by(id=review_id, ledger_id=ledger_id).first()
    if not row:
        raise ValueError('Review not found')
    approved = bool(body.get('approved'))
    row.status = 'Approved' if approved else 'Denied'
    row.resolution_notes = (body.get('notes') or '')[:500]
    c = AcctCustomer.query.get(row.customer_id)
    if c and approved:
        if body.get('credit_limit') is not None:
            c.credit_limit = float(body['credit_limit'])
        if body.get('clear_hold'):
            c.credit_hold = 0
    db.session.flush()
    return {'review_id': row.id, 'status': row.status}


def cash_workbench(db, models, ledger_id: int, customer_id: int):
    from accounting_ar_extended import cash_application_workbench

    return cash_application_workbench(db, models, ledger_id, customer_id)


# --- AP ---

def match_workbench_grid(db, models, ledger_id: int, invoice_id: int):
    from accounting_ap_extended import three_way_match

    inv = models['AcctAPDocument'].query.filter_by(id=invoice_id, ledger_id=ledger_id).first()
    if not inv:
        raise ValueError('Invoice not found')
    match = three_way_match(db, models, ledger_id, invoice_id)
    po_lines = []
    if inv.purchase_order_id:
        po = models['AcctPurchaseOrder'].query.get(inv.purchase_order_id)
        if po and po.lines_json:
            po_lines = json.loads(po.lines_json)
    return {'invoice_id': invoice_id, 'match': match, 'po_lines': po_lines}


def export_t5018(db, models, ledger_id: int, tax_year: int) -> str:
    AcctVendor = models['AcctVendor']
    AcctAPDocument = models['AcctAPDocument']
    lines = ['T5018|CasePM|Export']
    for v in AcctVendor.query.filter_by(ledger_id=ledger_id).all():
        total = sum(
            float(d.amount or 0) for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, vendor_id=v.id).all()
            if d.document_date and d.document_date.year == int(tax_year)
        )
        if total <= 0:
            continue
        lines.append(f"{v.tax_id or ''}|{v.name}|{round(total, 2)}|{tax_year}")
    return '\n'.join(lines)


def export_1099_fire(db, models, ledger_id: int, tax_year: int) -> dict:
    from accounting_ap_extended import report_1099

    data = report_1099(db, models, ledger_id, tax_year)
    records = []
    for v in data.get('vendors') or []:
        records.append({
            'TIN': v.get('tax_id') or '',
            'NAME': v.get('vendor_name') or '',
            'AMOUNT': v.get('payments') or 0,
            'TYPE': v.get('form_type') or 'NEC',
        })
    return {'tax_year': int(tax_year), 'format': 'fire_json', 'transmitter': 'CASEPM', 'records': records}


# --- GL ---

def budget_approval_submit(db, models, ledger_id: int, budget_id: int, user_id=None):
    AcctGLBudget = models['AcctGLBudget']
    b = AcctGLBudget.query.filter_by(id=budget_id, ledger_id=ledger_id).first()
    if not b:
        raise ValueError('Budget not found')
    b.status = 'Pending Approval'
    write_audit(db, models, ledger_id, user_id=user_id, action='budget_submit', entity_type='budget', entity_id=b.id)
    return b


def budget_approval_decide(db, models, ledger_id: int, budget_id: int, approved: bool, user_id=None):
    AcctGLBudget = models['AcctGLBudget']
    b = AcctGLBudget.query.filter_by(id=budget_id, ledger_id=ledger_id).first()
    if not b:
        raise ValueError('Budget not found')
    b.status = 'Active' if approved else 'Rejected'
    write_audit(db, models, ledger_id, user_id=user_id, action='budget_approve' if approved else 'budget_reject', entity_id=b.id)
    return b


def fiscal_archive_snapshot(db, models, ledger_id: int, fiscal_year: int) -> dict:
    from accounting_persistence import trial_balance

    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    periods = AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id, fiscal_year=int(fiscal_year)).all()
    tb = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    return {
        'fiscal_year': int(fiscal_year),
        'periods': [{'period_key': p.period_key, 'status': p.status} for p in periods],
        'trial_balance': tb,
        'archived_at': datetime.utcnow().isoformat() + 'Z',
        'read_only': True,
    }


# --- Consolidation ---

def auto_suggest_and_post_eliminations(db, models, parent_ledger_id: int, run_id: int, user_id=None):
    from accounting_consolidation import suggest_auto_eliminations, post_consolidation_eliminations

    AcctConsolidationRun = models['AcctConsolidationRun']
    run = AcctConsolidationRun.query.get(int(run_id))
    if not run:
        raise ValueError('Consolidation run not found')
    suggestions = suggest_auto_eliminations(db, models, parent_ledger_id, run)
    lines = suggestions.get('suggestions') or []
    if not lines:
        return {'suggested': 0, 'posted': False, 'message': 'No elimination suggestions'}
    out = post_consolidation_eliminations(db, models, run, {'lines': lines}, user_id=user_id)
    return {'suggested': len(lines), **out}


# --- Payroll ---

STATE_WITHHOLDING_TABLE = {
    'CA': 0.06,
    'NY': 0.065,
    'TX': 0.0,
    'FL': 0.0,
    'WA': 0.0,
    'default': 0.05,
}


def payroll_eft_file(db, models, ledger_id: int, run_id: int) -> str:
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    run = AcctPayrollRun.query.filter_by(id=run_id, ledger_id=ledger_id).first()
    if not run:
        raise ValueError('Pay run not found')
    lines = AcctPayrollRunLine.query.filter_by(run_id=run.id).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Employee', 'NetPay', 'Routing', 'Account'])
    for ln in lines:
        emp = AcctPayrollEmployee.query.get(ln.employee_id)
        w.writerow([
            f"{emp.last_name}, {emp.first_name}" if emp else ln.employee_id,
            round(float(ln.net_pay or 0), 2),
            getattr(emp, 'routing_number', None) or '',
            getattr(emp, 'account_number', None) or emp.bank_account_last4 if emp else '',
        ])
    return out.getvalue()


def enhanced_payroll_calculate_line(gross: float, state: str) -> dict:
    st = (state or '').upper()[:2]
    rate = STATE_WITHHOLDING_TABLE.get(st, STATE_WITHHOLDING_TABLE['default'])
    federal = round(gross * 0.12, 2)
    state_tax = round(gross * rate, 2)
    fica = round(gross * 0.0765, 2)
    return {'federal': federal, 'state': state_tax, 'fica': fica, 'total_taxes': round(federal + state_tax + fica, 2)}


# --- Payment processing ---

def stripe_payment_intent_stub(amount: float, currency: str = 'usd', metadata: dict | None = None) -> dict:
    return {
        'provider': 'stripe_test',
        'status': 'requires_payment_method',
        'client_secret': f"pi_test_{int(amount * 100)}_secret",
        'amount': round(float(amount), 2),
        'currency': currency,
        'metadata': metadata or {},
        'note': 'Configure live Stripe keys in program settings for production capture.',
    }


# --- Report designer ---

def report_designer_list(models, ledger_id: int):
    AcctReportDefinition = models['AcctReportDefinition']
    rows = AcctReportDefinition.query.filter_by(ledger_id=ledger_id).order_by(AcctReportDefinition.name).all()
    return [
        {
            'id': r.id,
            'name': r.name,
            'report_type': r.report_type,
            'definition': json.loads(r.definition_json or '{}'),
        }
        for r in rows
    ]


def report_designer_save(db, models, ledger_id: int, body: dict, user_id=None):
    AcctReportDefinition = models['AcctReportDefinition']
    rid = body.get('id')
    row = AcctReportDefinition.query.filter_by(id=rid, ledger_id=ledger_id).first() if rid else None
    if not row:
        row = AcctReportDefinition(ledger_id=ledger_id, name=(body.get('name') or 'Custom')[:80], report_type=(body.get('report_type') or 'custom')[:40])
        db.session.add(row)
    row.name = (body.get('name') or row.name)[:80]
    row.report_type = (body.get('report_type') or row.report_type)[:40]
    row.definition_json = json.dumps(body.get('definition') or {'rows': [], 'columns': []})
    db.session.flush()
    return row.id


# --- Job cost revenue recognition ---

def revenue_recognition_schedule(db, models, ledger_id: int, project_id: int) -> dict:
    """Percent-complete style schedule from open AR and budget hints."""
    AcctARDocument = models['AcctARDocument']
    billed = sum(
        float(d.amount or 0) for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, project_id=project_id).all()
    )
    contract = float(max(billed * 1.25, 1))
    pct = min(round(billed / contract * 100, 2), 100.0)
    return {
        'project_id': project_id,
        'contract_value_est': contract,
        'billed_to_date': round(billed, 2),
        'percent_complete': pct,
        'revenue_to_recognize': round(contract * pct / 100.0, 2),
        'method': 'percent_complete_estimated',
    }


# --- Scheduled reports ---

def schedule_report(db, models, ledger_id: int, body: dict, user_id=None):
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    schedules = settings.get('scheduled_reports') or []
    schedules.append({
        'id': len(schedules) + 1,
        'report_type': body.get('report_type'),
        'cron': body.get('cron') or '0 6 * * 1',
        'email': body.get('email'),
        'created_at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['scheduled_reports'] = schedules[-50:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='schedule_report', details=schedules[-1])
    return schedules[-1]
