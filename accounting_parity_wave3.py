"""Accounting parity wave 3 — compliance exports, payments depth, reports, inventory FIFO, auditor pack."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime

from accounting_platform import write_audit


def export_form_941_summary(db, models, ledger_id: int, quarter: int, year: int) -> dict:
    """Employer quarterly federal return — summary fields for export (not IRS e-file)."""
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    q = int(quarter)
    y = int(year)
    runs = [
        r for r in AcctPayrollRun.query.filter_by(ledger_id=ledger_id, status='Posted').all()
        if r.period_end and r.period_end.year == y and ((r.period_end.month - 1) // 3 + 1) == q
    ]
    wages = 0.0
    fed_wh = 0.0
    fica = 0.0
    for run in runs:
        for ln in AcctPayrollRunLine.query.filter_by(run_id=run.id).all():
            wages += float(ln.gross_pay or 0)
            fed_wh += float(ln.federal_wh or 0)
            fica += float(ln.fica_employee or 0) + float(ln.medicare_employee or 0)
    return {
        'form': '941',
        'year': y,
        'quarter': q,
        'wages_tips_other': round(wages, 2),
        'federal_income_tax_withheld': round(fed_wh, 2),
        'social_security_medicare_tax': round(fica, 2),
        'total_taxes': round(fed_wh + fica, 2),
        'pay_runs_included': len(runs),
    }


def export_form_941_csv(db, models, ledger_id: int, quarter: int, year: int) -> str:
    data = export_form_941_summary(db, models, ledger_id, quarter, year)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Field', 'Value'])
    for k, v in data.items():
        w.writerow([k, v])
    return out.getvalue()


def export_w2_summary(db, models, ledger_id: int, tax_year: int) -> dict:
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    AcctPayrollRun = models['AcctPayrollRun']
    y = int(tax_year)
    employees = []
    for emp in AcctPayrollEmployee.query.filter_by(ledger_id=ledger_id, status='Active').all():
        wages = 0.0
        fed = 0.0
        fica = 0.0
        for run in AcctPayrollRun.query.filter_by(ledger_id=ledger_id, status='Posted').all():
            if not run.period_end or run.period_end.year != y:
                continue
            for ln in AcctPayrollRunLine.query.filter_by(run_id=run.id, employee_id=emp.id).all():
                wages += float(ln.gross_pay or 0)
                fed += float(ln.federal_wh or 0)
                fica += float(ln.fica_employee or 0) + float(ln.medicare_employee or 0)
        if wages <= 0:
            continue
        employees.append({
            'employee_number': emp.employee_number,
            'name': f'{emp.last_name}, {emp.first_name}',
            'wages': round(wages, 2),
            'federal_withheld': round(fed, 2),
            'fica_withheld': round(fica, 2),
            'ssn_last4': emp.bank_account_last4 or '****',
        })
    return {'tax_year': y, 'employees': employees}


def certified_payroll_wh347(db, models, ledger_id: int, project_id: int, week_ending: str) -> str:
    """DOL WH-347 style certified payroll CSV stub."""
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    AcctPayrollRun = models['AcctPayrollRun']
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['WH347', 'Case PM', week_ending, f'project_{project_id}'])
    w.writerow(['Employee', 'Classification', 'Hours', 'Rate', 'Gross', 'Deductions', 'Net'])
    we = date.fromisoformat(week_ending) if week_ending else date.today()
    for run in AcctPayrollRun.query.filter_by(ledger_id=ledger_id, status='Posted').all():
        if run.period_end and abs((run.period_end - we).days) > 7:
            continue
        for ln in AcctPayrollRunLine.query.filter_by(run_id=run.id).all():
            if project_id and getattr(ln, 'project_id', None) and int(ln.project_id) != int(project_id):
                continue
            emp = AcctPayrollEmployee.query.get(ln.employee_id)
            hrs = float(ln.hours_regular or 0) + float(ln.hours_overtime or 0)
            rate = round(float(ln.gross_pay or 0) / hrs, 2) if hrs else 0
            w.writerow([
                f'{emp.last_name}, {emp.first_name}' if emp else ln.employee_id,
                'Journeyman',
                round(hrs, 2),
                rate,
                round(float(ln.gross_pay or 0), 2),
                round(float(ln.other_deductions or 0), 2),
                round(float(ln.net_pay or 0), 2),
            ])
    return out.getvalue()


def form_1099_official_html(db, models, ledger_id: int, tax_year: int, vendor_id: int) -> str:
    from accounting_ap_extended import report_1099

    data = report_1099(db, models, ledger_id, tax_year)
    row = next((v for v in data.get('vendors') or [] if v['vendor_id'] == int(vendor_id)), None)
    if not row:
        raise ValueError('Vendor not found on 1099 report')
    amt = row.get('payments') or 0
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Form 1099-NEC {tax_year}</title>
    <style>body{{font-family:Arial,sans-serif;margin:40px}} .box{{border:2px solid #000;padding:12px;margin:8px 0}}
    h1{{font-size:18px}}</style></head><body>
    <h1>Form 1099-NEC — {tax_year} (Case PM printable)</h1>
    <div class="box"><strong>PAYER</strong><br>Case PM Accounting · Ledger {ledger_id}</div>
    <div class="box"><strong>RECIPIENT</strong><br>{row.get('vendor_name')}<br>TIN: {row.get('tax_id') or 'Applied for'}</div>
    <div class="box"><strong>Box 1 — Nonemployee compensation</strong><br>${amt:,.2f}</div>
    <p class="text-muted" style="color:#666;font-size:11px">Not an official IRS form. Use for review; file via FIRE export or your tax software.</p>
    </body></html>"""


def stripe_webhook_stub(payload: dict) -> dict:
    evt = payload.get('type') or 'payment_intent.succeeded'
    return {'received': True, 'type': evt, 'status': 'processed_test_mode', 'id': payload.get('id') or 'evt_test'}


def capture_pay_now_stripe(db, models, token: str, payment_intent_id: str, user_id=None):
    from accounting_payment_processing import complete_pay_now_link

    AcctPayNowLink = models['AcctPayNowLink']
    AcctARDocument = models['AcctARDocument']
    link = AcctPayNowLink.query.filter_by(token=token).first()
    if not link:
        raise ValueError('Pay Now link not found')
    doc = AcctARDocument.query.get(link.ar_document_id)
    ledger_id = doc.ledger_id if doc else None
    out = complete_pay_now_link(db, models, token, user_id=user_id)
    if ledger_id:
        write_audit(db, models, ledger_id, user_id=user_id, action='stripe_capture', details={'intent': payment_intent_id})
    return out


def comparative_income_statement(db, models, ledger_id: int, period_a: str, period_b: str) -> dict:
    from accounting_reports import run_report

    a = run_report(db, models, ledger_id, 'income_statement', {'start_date': f'{period_a}-01', 'end_date': f'{period_a}-28'})
    b = run_report(db, models, ledger_id, 'income_statement', {'start_date': f'{period_b}-01', 'end_date': f'{period_b}-28'})
    return {
        'period_a': period_a,
        'period_b': period_b,
        'net_income_a': a.get('net_income'),
        'net_income_b': b.get('net_income'),
        'revenue_a': a.get('total_revenue'),
        'revenue_b': b.get('total_revenue'),
        'variance': round(float(a.get('net_income') or 0) - float(b.get('net_income') or 0), 2),
        'detail_a': a,
        'detail_b': b,
    }


def inventory_fifo_issue(db, models, ledger_id: int, item_id: int, qty: float, reference: str = ''):
    """Issue inventory using FIFO lot layers."""
    M = models['AcctInventoryLot']
    AcctInventoryItem = models['AcctInventoryItem']
    AcctInventoryTransaction = models['AcctInventoryTransaction']
    item = AcctInventoryItem.query.filter_by(id=item_id, ledger_id=ledger_id).first()
    if not item:
        raise ValueError('Item not found')
    need = float(qty)
    if need <= 0:
        raise ValueError('qty must be positive')
    lots = M.query.filter_by(ledger_id=ledger_id, item_id=item_id).order_by(M.id).all()
    cost = 0.0
    remaining = need
    for lot in lots:
        if remaining <= 0:
            break
        avail = float(lot.qty_on_hand or 0)
        if avail <= 0:
            continue
        take = min(avail, remaining)
        lot.qty_on_hand = avail - take
        cost += take * float(lot.unit_cost or item.unit_cost or 0)
        remaining -= take
    if remaining > 0.0001:
        raise ValueError('Insufficient lot quantity for FIFO issue')
    item.qty_on_hand = float(item.qty_on_hand or 0) - need
    db.session.add(AcctInventoryTransaction(
        ledger_id=ledger_id,
        item_id=item_id,
        txn_type='issue_fifo',
        qty_delta=-need,
        unit_cost=round(cost / need, 4) if need else 0,
        reference=(reference or 'FIFO issue')[:80],
    ))
    db.session.flush()
    return {'item_id': item_id, 'qty_issued': need, 'cogs': round(cost, 2)}


def plaid_feed_stub(transactions: list) -> list:
    """Normalize Plaid-style transaction dicts to bank import rows."""
    out = []
    for t in transactions or []:
        out.append({
            'amount': float(t.get('amount') or 0),
            'transaction_date': (t.get('date') or date.today().isoformat())[:10],
            'description': (t.get('name') or t.get('merchant_name') or 'Plaid')[:300],
            'reference': (t.get('transaction_id') or '')[:80],
        })
    return out


def import_plaid_transactions(db, models, ledger_id: int, bank_account_id: int, transactions: list, user_id=None):
    from accounting_bank_service import record_manual_bank_transaction

    rows = plaid_feed_stub(transactions)
    n = 0
    for row in rows:
        record_manual_bank_transaction(
            db, models,
            ledger_id=ledger_id,
            bank_account_id=bank_account_id,
            amount=row['amount'],
            description=row['description'],
            reference=row['reference'],
            transaction_type='Plaid',
            transaction_date=date.fromisoformat(row['transaction_date']),
            post_gl=False,
            user_id=user_id,
        )
        n += 1
    return {'imported': n}


def validate_journal_batch_segments(db, models, ledger_id: int, batch_id: int) -> dict:
    from accounting_gl_extended import validate_account_number_segments
    from accounting_gl_service import ledger_gl_options

    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctGLAccount = models['AcctGLAccount']
    ledger = models['AcctLedger'].query.get(ledger_id)
    opts = ledger_gl_options(ledger)
    batch = AcctJournalBatch.query.filter_by(id=batch_id, ledger_id=ledger_id).first()
    if not batch:
        raise ValueError('Batch not found')
    errors = []
    for ln in AcctJournalLine.query.filter_by(batch_id=batch.id).all():
        acct = AcctGLAccount.query.get(ln.account_id)
        if not acct:
            continue
        try:
            validate_account_number_segments(acct.account_number, opts['segment_count'])
        except ValueError as exc:
            errors.append({'line': ln.line_number, 'account': acct.account_number, 'error': str(exc)})
        if ln.segments_json:
            try:
                seg = json.loads(ln.segments_json).get('segments') or []
                if len(seg) < opts['segment_count']:
                    errors.append({'line': ln.line_number, 'error': 'segment count mismatch on line'})
            except Exception:
                errors.append({'line': ln.line_number, 'error': 'invalid segments_json'})
    return {'batch_id': batch_id, 'valid': not errors, 'errors': errors}


def auditor_package(db, models, parent_ledger_id: int, as_of: str = None) -> dict:
    from accounting_consolidation import consolidated_trial_balance, indirect_cash_flow_statement
    from accounting_parity_wave2 import fiscal_archive_snapshot

    as_of_d = as_of or date.today().isoformat()
    fy = int(as_of_d[:4])
    return {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'as_of': as_of_d,
        'consolidated_trial_balance': consolidated_trial_balance(db, models, parent_ledger_id, include_parent=True),
        'cash_flow': indirect_cash_flow_statement(db, models, parent_ledger_id, as_of=as_of_d),
        'fiscal_archive': fiscal_archive_snapshot(db, models, parent_ledger_id, fy),
    }


def run_due_scheduled_reports(db, models, ledger_id: int, user_id=None):
    from accounting_tier14_wave import run_scheduled_reports_with_email

    return run_scheduled_reports_with_email(db, models, ledger_id, user_id=user_id)


def ap_match_line_grid_enriched(db, models, ledger_id: int, invoice_id: int) -> dict:
    from accounting_parity_wave2 import match_workbench_grid

    base = match_workbench_grid(db, models, ledger_id, invoice_id)
    inv_lines = []
    match = base.get('match') or {}
    for i, pl in enumerate(base.get('po_lines') or []):
        inv_lines.append({
            'line': i + 1,
            'po_qty': pl.get('qty'),
            'po_amount': pl.get('amount'),
            'received_qty': pl.get('received_qty', pl.get('qty')),
            'invoice_qty': pl.get('qty'),
            'variance': round(float(match.get('invoice_amount') or 0) - float(match.get('po_total') or 0), 2),
            'within_tolerance': match.get('amount_within_tolerance'),
        })
    base['line_grid'] = inv_lines
    return base
