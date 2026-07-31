"""GL / AP / AR gap closure — match grids, recurring run-due, 1099 FIRE export, subledger fix drafts."""
from __future__ import annotations

import json
from datetime import date

from accounting_platform import write_audit


def build_match_line_grid(db, models, ledger_id: int, invoice_id: int) -> dict:
    from accounting_ap_extended import three_way_match
    from accounting_operations import _parse_lines

    match = three_way_match(db, models, ledger_id, invoice_id)
    AcctAPDocument = models['AcctAPDocument']
    doc = AcctAPDocument.query.filter_by(id=int(invoice_id), ledger_id=ledger_id).first()
    po_lines = match.get('lines') or []
    if doc and doc.purchase_order_id:
        po = models['AcctPurchaseOrder'].query.get(doc.purchase_order_id)
        if po and po.lines_json:
            po_lines = _parse_lines(po.lines_json)
    grid = []
    inv_amt = float(match.get('invoice_amount') or (doc.amount if doc else 0) or 0)
    po_line_total = 0.0
    for idx, pl in enumerate(po_lines, start=1):
        ordered = float(pl.get('qty') or pl.get('quantity') or 0)
        received = float(pl.get('qty_received') or pl.get('received_qty') or 0)
        unit = float(pl.get('unit_cost') or pl.get('price') or 0)
        line_total = round(ordered * unit, 2) if unit else float(pl.get('amount') or 0)
        po_line_total += line_total
        qty_ok = ordered <= 0 or received >= ordered * 0.99
        grid.append({
            'line_number': idx,
            'item': (pl.get('item_code') or pl.get('description') or f'Line {idx}')[:80],
            'qty_ordered': ordered,
            'qty_received': received,
            'unit_cost': unit,
            'po_line_amount': line_total,
            'qty_match': qty_ok,
            'variance_qty': round(max(0, ordered - received), 4),
        })
    if not grid and doc:
        grid.append({
            'line_number': 1,
            'item': doc.document_number or 'Invoice total',
            'qty_ordered': 1,
            'qty_received': 1 if match.get('matched') else 0,
            'unit_cost': inv_amt,
            'po_line_amount': inv_amt,
            'qty_match': bool(match.get('matched')),
            'variance_qty': 0,
        })
    tol = match.get('tolerance') or {}
    amount_var = round(inv_amt - (match.get('po_total') or po_line_total or 0), 2)
    return {
        'invoice_id': int(invoice_id),
        'document_number': doc.document_number if doc else '',
        'match': match,
        'line_grid': grid,
        'summary': {
            'invoice_amount': round(inv_amt, 2),
            'po_total': round(float(match.get('po_total') or po_line_total or 0), 2),
            'amount_variance': amount_var,
            'tolerance_amount': tol.get('amount'),
            'tolerance_percent': tol.get('percent'),
        },
    }


def run_due_recurring_payables(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_ap_extended import generate_recurring_ap_invoice

    AcctAPRecurringPayable = models['AcctAPRecurringPayable']
    today = date.today()
    runs = []
    for r in AcctAPRecurringPayable.query.filter_by(ledger_id=ledger_id, is_active=True).all():
        if r.next_run_date and r.next_run_date <= today:
            doc = generate_recurring_ap_invoice(db, models, r)
            runs.append({'recurring_id': r.id, 'document_id': doc.id, 'document_number': doc.document_number})
    if runs:
        write_audit(db, models, ledger_id, user_id=user_id, action='ap_recurring_run_due', details={'count': len(runs)})
    db.session.flush()
    return {'ran': len(runs), 'documents': runs}


def run_due_recurring_ar_invoices(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_ar_extended import generate_recurring_ar_invoice

    AcctARRecurringInvoice = models['AcctARRecurringInvoice']
    today = date.today()
    runs = []
    for r in AcctARRecurringInvoice.query.filter_by(ledger_id=ledger_id, is_active=True).all():
        if r.next_run_date and r.next_run_date <= today:
            doc = generate_recurring_ar_invoice(db, models, r)
            runs.append({'recurring_id': r.id, 'document_id': doc.id, 'document_number': doc.document_number})
    if runs:
        write_audit(db, models, ledger_id, user_id=user_id, action='ar_recurring_run_due', details={'count': len(runs)})
    db.session.flush()
    return {'ran': len(runs), 'documents': runs}


def export_1099_fire_transmission(db, models, ledger_id: int, tax_year: int, *, payer_tin='000000000', payer_name='CASE PM LLC') -> str:
    """IRS FIRE–style fixed-width transmission (simplified T/A/B/F records)."""
    from accounting_ap_extended import report_1099

    data = report_1099(db, models, ledger_id, tax_year)
    vendors = data.get('vendors') or []
    y = int(tax_year)
    lines = []
    lines.append(f"T{y:4d}{payer_tin[:9]:0>9}{payer_name[:40]:<40}00000001")
    for i, v in enumerate(vendors, start=1):
        tin = (v.get('tax_id') or '').replace('-', '')[:9]
        name = (v.get('vendor_name') or '')[:40]
        amt = int(round(float(v.get('payments') or 0) * 100))
        form = (v.get('form_type') or 'NEC')[:3]
        lines.append(f"A{i:07d}{tin:0>9}{name:<40}{amt:012d}{form:<3}")
    lines.append(f"F{len(vendors):07d}{len(vendors):07d}")
    return '\r\n'.join(lines)


def subledger_reconcile_suggestion(db, models, ledger_id: int) -> dict:
    from accounting_gl_extended import subledger_control_reconcile

    sub = subledger_control_reconcile(db, models, ledger_id)
    suggestions = []
    ap = sub.get('ap') or {}
    ar = sub.get('ar') or {}
    ap_diff = float(ap.get('difference') or 0)
    if abs(ap_diff) > 0.02:
        suggestions.append({
            'module': 'ap',
            'control_account': ap.get('gl_account'),
            'difference': ap_diff,
            'action': 'Post adjusting entry: debit A/P control if difference positive (subledger lower than G/L), else credit.',
            'suggested_debit_account': ap.get('gl_account'),
            'amount': round(abs(ap_diff), 2),
        })
    ar_diff = float(ar.get('difference') or 0)
    if abs(ar_diff) > 0.02:
        suggestions.append({
            'module': 'ar',
            'control_account': ar.get('gl_account'),
            'difference': ar_diff,
            'action': 'Post adjusting entry to align A/R control with open subledger.',
            'suggested_debit_account': ar.get('gl_account'),
            'amount': round(abs(ar_diff), 2),
        })
    return {'subledger': sub, 'suggestions': suggestions, 'balanced': not suggestions}


def post_subledger_adjustment(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    """Post a balancing entry for AP or AR control vs subledger (accounting role required)."""
    from accounting_gl_extended import subledger_control_reconcile
    from accounting_posting import load_accounting_options, _account_by_number
    from accounting_persistence import next_batch_number, post_journal_batch

    module = (body.get('module') or '').lower()
    if module not in ('ap', 'ar'):
        raise ValueError('module must be ap or ar')
    sub = subledger_control_reconcile(db, models, ledger_id)
    block = sub.get(module) or {}
    diff = float(block.get('difference') or 0)
    if abs(diff) <= 0.02:
        raise ValueError('Subledger already in balance')
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(ledger_id)
    control = _account_by_number(
        AcctGLAccount, ledger_id,
        opts['ap_account'] if module == 'ap' else opts['ar_account'],
    )
    offset = _account_by_number(AcctGLAccount, ledger_id, opts.get('retained_earnings_account') or '3900')
    amt = round(abs(diff), 2)
    batch = AcctJournalBatch(
        ledger_id=ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, ledger_id),
        source='SL-ADJ',
        description=f'Subledger tie-out adjustment ({module.upper()})',
        batch_date=date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    if module == 'ap':
        if diff > 0:
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=control.id, debit=amt, credit=0, description='A/P tie-out'))
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=offset.id, debit=0, credit=amt, description='A/P tie-out'))
        else:
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=offset.id, debit=amt, credit=0, description='A/P tie-out'))
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=control.id, debit=0, credit=amt, description='A/P tie-out'))
    else:
        if diff > 0:
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=offset.id, debit=amt, credit=0, description='A/R tie-out'))
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=control.id, debit=0, credit=amt, description='A/R tie-out'))
        else:
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=control.id, debit=amt, credit=0, description='A/R tie-out'))
            db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=offset.id, debit=0, credit=amt, description='A/R tie-out'))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='subledger_adjust', details={'module': module, 'batch_id': batch.id, 'amount': amt})
    db.session.flush()
    return {'batch_id': batch.id, 'module': module, 'amount': amt}
