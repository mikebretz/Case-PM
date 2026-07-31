"""
Wave 13 — retainage, cost-code profitability, labor→GL, month close, reversals & closeout.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


def _flag(key: str, default: str = '1') -> bool:
    from program_settings_persistence import load_accounting_defaults

    return str(load_accounting_defaults().get(key, default)) != '0'


def _retainage_rate_from_pay_state(state: dict) -> float:
    state = state or {}
    for key in ('payAppRetainagePercent', 'retainageRate', 'retainage_rate'):
        raw = state.get(key)
        if raw is not None:
            try:
                v = float(raw)
                return v / 100.0 if v > 1 else v
            except (TypeError, ValueError):
                pass
    return 0.10


# --- 1: Retainage ---

def project_retainage_summary(db, models, ledger_id: int, project_id: int, PayAppProjectState=None) -> dict:
    from pay_app_persistence import get_pay_app_state

    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    owner_held = sub_held = 0.0
    rate = 0.10
    if PayAppProjectState:
        _, state = get_pay_app_state(PayAppProjectState, int(project_id))
        state = state or {}
        rate = _retainage_rate_from_pay_state(state)
        periods = state.get('periods') or state.get('payAppPeriods') or []
        if isinstance(periods, dict):
            periods = list(periods.values())
        for p in periods:
            if not isinstance(p, dict):
                continue
            owner_held += float(p.get('retainage') or p.get('retainageHeld') or 0)
        hist = state.get('subPayAppHistory') or {}
        for ch in hist.values():
            if not isinstance(ch, dict):
                continue
            for ent in ch.values():
                if isinstance(ent, dict):
                    sub_held += float(ent.get('retainage') or ent.get('retainageHeld') or 0)
    ap_ret = sum(
        float(d.retainage_amount or 0)
        for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, project_id=int(project_id)).all()
    )
    ar_ret = sum(
        float(getattr(d, 'retainage_amount', 0) or 0)
        for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, project_id=int(project_id)).all()
    )
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    posted_holds = [h for h in (settings.get('retainage_holds') or []) if h.get('project_id') == int(project_id)]
    return {
        'project_id': int(project_id),
        'retainage_rate': round(rate, 4),
        'owner_retainage_pay_apps': round(owner_held, 2),
        'sub_retainage_pay_apps': round(sub_held, 2),
        'ap_retainage_held': round(ap_ret, 2),
        'ar_retainage_held': round(ar_ret, 2),
        'accounting_holds': posted_holds[-20:],
    }


def post_owner_retainage_hold(
    db, models, ledger_id: int, project_id: int, amount: float, user_id=None, *, period: str | None = None,
) -> dict:
    from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options

    amt = round(float(amount or 0), 2)
    if amt <= 0:
        raise ValueError('Retainage amount must be positive')
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    ret_ar = _account_by_number(AcctGLAccount, ledger_id, '1165') or _account_by_number(AcctGLAccount, ledger_id, opts['ar_account'])
    ret_liab = _account_by_number(AcctGLAccount, ledger_id, '2205') or _account_by_number(AcctGLAccount, ledger_id, opts['ap_account'])
    batch = _create_posted_batch(
        db, models, ledger_id=ledger_id, source='RET',
        description=f'Owner retainage hold P{project_id} {period or ""}'.strip(),
        user_id=user_id,
        lines=[
            {'account_id': ret_ar.id, 'debit': amt, 'credit': 0, 'project_id': project_id},
            {'account_id': ret_liab.id, 'debit': 0, 'credit': amt, 'project_id': project_id},
        ],
    )
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    holds = settings.get('retainage_holds') or []
    holds.append({
        'project_id': int(project_id),
        'side': 'owner',
        'amount': amt,
        'period': period,
        'journal_batch_id': batch.id,
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['retainage_holds'] = holds[-100:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='owner_retainage_hold', details={'amount': amt, 'batch_id': batch.id})
    return {'journal_batch_id': batch.id, 'amount': amt}


def release_owner_retainage_to_ar(
    db, models, ledger_id: int, project_id: int, amount: float, customer_id: int, user_id=None,
) -> dict:
    from accounting_all_chunks import apply_progress_billing_to_ar

    amt = round(float(amount or 0), 2)
    if amt <= 0:
        raise ValueError('Release amount must be positive')
    doc = apply_progress_billing_to_ar(
        db, models, ledger_id, int(customer_id), amt, int(project_id),
        document_number=f'RET-REL-{project_id}-{date.today().strftime("%Y%m%d")}',
        user_id=user_id,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='owner_retainage_release', entity_id=doc.id, details={'amount': amt})
    return {'ar_document_id': doc.id, 'amount': amt}


def apply_sub_pay_app_retainage_split(db, models, ledger_id: int, ap_document_id: int | None, gross: float, retainage_pct: float | None = None) -> dict:
    if not ap_document_id or not _flag('retainage_accounting_enabled', '1'):
        return {'skipped': True}
    from accounting_ap_extended import compute_ap_invoice_amounts

    AcctAPDocument = models['AcctAPDocument']
    doc = AcctAPDocument.query.filter_by(id=int(ap_document_id), ledger_id=ledger_id).first()
    if not doc:
        return {'skipped': True}
    pct = float(retainage_pct if retainage_pct is not None else 10)
    amounts = compute_ap_invoice_amounts(gross, retainage_percent=pct)
    doc.gross_amount = gross
    doc.retainage_amount = amounts['retainage_amount']
    doc.amount = amounts['net_before_withhold']
    db.session.flush()
    return {'ap_document_id': doc.id, 'retainage_amount': doc.retainage_amount, 'net_ap': doc.amount}


def sync_owner_retainage_from_pay_apps(
    db, models, ledger_id: int, project_id: int, user_id=None, PayAppProjectState=None,
) -> dict:
    from pay_app_persistence import get_pay_app_state

    if not PayAppProjectState:
        raise ValueError('Pay apps not available')
    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    rate = _retainage_rate_from_pay_state(state)
    periods = state.get('periods') or state.get('payAppPeriods') or []
    if isinstance(periods, dict):
        periods = list(periods.values())
    posted = []
    for p in periods:
        if not isinstance(p, dict):
            continue
        ret = float(p.get('retainage') or p.get('retainageHeld') or 0)
        if ret <= 0:
            bill = float(p.get('currentPaymentDue') or p.get('amountDue') or 0)
            ret = round(bill * rate, 2)
        if ret <= 0:
            continue
        period = p.get('periodNumber') or p.get('period_number')
        out = post_owner_retainage_hold(db, models, ledger_id, project_id, ret, user_id=user_id, period=str(period))
        posted.append({'period': period, **out})
    return {'posted_count': len(posted), 'posted': posted}


# --- 2: Cost code profitability ---

def cost_code_profitability_report(db, models, ledger_id: int, project_id: int, BudgetProjectState, Commitment=None) -> dict:
    from commitment_persistence import normalize_cost_code

    rows = []
    budget_lines = []
    if BudgetProjectState:
        try:
            from budget_persistence import get_budget_state

            _, state = get_budget_state(BudgetProjectState, int(project_id))
            budget_lines = (state or {}).get('budgetLines') or []
        except Exception:
            budget_lines = []
    committed_by_code: dict[str, float] = {}
    if Commitment:
        CommitmentAllocation = None
        try:
            import app as app_mod
            CommitmentAllocation = app_mod.CommitmentAllocation
        except Exception:
            CommitmentAllocation = None
        if CommitmentAllocation:
            for c in Commitment.query.filter_by(project_id=int(project_id)).all():
                for a in CommitmentAllocation.query.filter_by(commitment_id=c.id).all():
                    code = normalize_cost_code(a.cost_code or '')
                    if code:
                        committed_by_code[code] = committed_by_code.get(code, 0.0) + float(a.amount or 0)
    for ln in budget_lines:
        if not isinstance(ln, dict):
            continue
        code = normalize_cost_code(ln.get('cost_code') or '')
        if not code:
            continue
        ob = float(ln.get('original_budget') or 0)
        ac = float(ln.get('approved_changes') or 0)
        revised = ob + ac
        actual = float(ln.get('actual') or 0)
        committed = round(committed_by_code.get(code, 0.0), 2)
        rows.append({
            'cost_code': code,
            'budget_revised': round(revised, 2),
            'committed': committed,
            'budget_actual': round(actual, 2),
            'variance_budget_vs_actual': round(revised - actual, 2),
            'variance_committed_vs_actual': round(committed - actual, 2),
        })
    rows.sort(key=lambda r: r['cost_code'])
    return {'project_id': int(project_id), 'rows': rows, 'row_count': len(rows)}


# --- 3: Labor → G/L ---

def post_labor_journal_for_project(
    db, models, ledger_id: int, project_id: int, amount: float, user_id=None, *, reference: str = 'Labor',
) -> dict:
    from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options

    amt = round(float(amount or 0), 2)
    if amt <= 0:
        raise ValueError('Labor amount must be positive')
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    labor = _account_by_number(AcctGLAccount, ledger_id, opts['labor_expense'])
    clearing = _account_by_number(AcctGLAccount, ledger_id, opts['payroll_liability'])
    batch = _create_posted_batch(
        db, models, ledger_id=ledger_id, source='PAYROLL',
        description=f'{reference} — project {project_id}',
        user_id=user_id,
        lines=[
            {'account_id': labor.id, 'debit': amt, 'credit': 0, 'project_id': project_id},
            {'account_id': clearing.id, 'debit': 0, 'credit': amt, 'project_id': project_id},
        ],
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='labor_gl_post', details={'amount': amt, 'batch_id': batch.id})
    return {'journal_batch_id': batch.id, 'amount': amt}


def post_payroll_run_labor_to_gl(db, models, ledger_id: int, run_id: int, user_id=None) -> dict:
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    run = AcctPayrollRun.query.filter_by(id=int(run_id), ledger_id=ledger_id).first()
    if not run:
        raise ValueError('Payroll run not found')
    if run.status != 'Posted':
        raise ValueError('Payroll run must be posted before labor G/L distribution')
    posted = []
    for ln in AcctPayrollRunLine.query.filter_by(run_id=run.id).all():
        pid = ln.project_id
        if not pid:
            continue
        amt = round(float(ln.gross_pay or 0), 2)
        if amt <= 0:
            continue
        out = post_labor_journal_for_project(
            db, models, ledger_id, pid, amt, user_id=user_id,
            reference=f'Payroll run {run.run_number}',
        )
        posted.append({'employee_line_id': ln.id, 'project_id': pid, **out})
    return {'run_id': run.id, 'posted_count': len(posted), 'posted': posted}


def post_timesheet_labor_to_gl(db, models, ledger_id: int, project_id: int, labor_cost: float, user_id=None, *, timesheet_ref: str = '') -> dict:
    return post_labor_journal_for_project(
        db, models, ledger_id, int(project_id), labor_cost, user_id=user_id,
        reference=timesheet_ref or 'Timesheet',
    )


# --- 4: Month close ---

def close_bank_statement_period(
    db, models, ledger_id: int, bank_account_id: int, period_end: str, user_id=None, *, allow_open: bool = False,
) -> dict:
    AcctBankTransaction = models['AcctBankTransaction']
    AcctBankAccount = models['AcctBankAccount']
    bank = AcctBankAccount.query.filter_by(id=int(bank_account_id), ledger_id=ledger_id).first()
    if not bank:
        raise ValueError('Bank account not found')
    end = date.fromisoformat(period_end[:10])
    open_tx = [
        t for t in AcctBankTransaction.query.filter_by(bank_account_id=bank.id).all()
        if t.transaction_date and t.transaction_date <= end and not t.reconciled
    ]
    if open_tx and not allow_open:
        raise ValueError(f'{len(open_tx)} unreconciled transaction(s) on or before {period_end}')
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    closed = settings.get('bank_periods_closed') or []
    closed.append({
        'bank_account_id': bank.id,
        'period_end': end.isoformat(),
        'closed_at': datetime.utcnow().isoformat() + 'Z',
        'open_count': len(open_tx),
    })
    settings['bank_periods_closed'] = closed[-50:]
    bank.last_reconciled_date = end
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='bank_period_close', details={'bank_id': bank.id, 'period_end': period_end})
    return {'bank_account_id': bank.id, 'period_end': period_end, 'open_remaining': len(open_tx)}


def stripe_settlement_match_suggestions(db, models, ledger_id: int) -> dict:
    from accounting_waves_22 import pay_now_deposit_hints

    hints = pay_now_deposit_hints(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    webhooks = settings.get('stripe_webhook_log') or []
    settlements = []
    for w in webhooks[-30:]:
        if w.get('type') != 'payment_intent.succeeded':
            continue
        amt = (w.get('result') or {}).get('amount')
        if amt:
            settlements.append({'amount': amt, 'at': w.get('at'), 'matched_bank_tx': None})
    for h in hints.get('hints') or []:
        if h.get('suggested_bank_transaction_id'):
            settlements.append({
                'amount': h.get('amount'),
                'pay_now_link_id': h.get('pay_now_link_id'),
                'suggested_bank_transaction_id': h['suggested_bank_transaction_id'],
            })
    return {'settlements': settlements, 'hint_count': len(hints.get('hints') or [])}


def month_end_cash_checklist(db, models, ledger_id: int) -> dict:
    AcctBankAccount = models['AcctBankAccount']
    AcctARDocument = models['AcctARDocument']
    AcctAPDocument = models['AcctAPDocument']
    banks = AcctBankAccount.query.filter_by(ledger_id=ledger_id).all()
    open_ar = AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    open_ap = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    ledger = models['AcctLedger'].query.get(ledger_id)
    closed = (_ledger_settings(ledger).get('bank_periods_closed') or [])[-5:]
    return {
        'bank_accounts': len(banks),
        'open_ar_documents': open_ar,
        'open_ap_documents': open_ap,
        'recent_bank_closes': closed,
        'stripe_settlements': stripe_settlement_match_suggestions(db, models, ledger_id),
    }


# --- 5: Reversals & closeout ---

def reverse_construction_post(db, models, ledger_id: int, source_key: str, user_id=None, *, reason: str = '') -> dict:
    from accounting_posting import _account_by_number, _create_posted_batch

    AcctPostLink = models['AcctPostLink']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctARDocument = models['AcctARDocument']
    AcctAPDocument = models['AcctAPDocument']
    link = AcctPostLink.query.filter_by(ledger_id=ledger_id, source_key=source_key.strip()).first()
    if not link:
        raise ValueError('Construction post link not found')
    reversed_batches = []
    if link.journal_batch_id:
        batch = AcctJournalBatch.query.get(link.journal_batch_id)
        if batch and batch.status == 'Posted':
            lines = []
            for ln in AcctJournalLine.query.filter_by(batch_id=batch.id).all():
                lines.append({
                    'account_id': ln.account_id,
                    'debit': float(ln.credit or 0),
                    'credit': float(ln.debit or 0),
                    'project_id': ln.project_id,
                    'description': f'Reversal: {reason or source_key}'[:200],
                })
            rev = _create_posted_batch(
                db, models, ledger_id=ledger_id, source='REV',
                description=f'Reverse {source_key}',
                user_id=user_id,
                lines=lines,
            )
            reversed_batches.append(rev.id)
    if link.ar_document_id:
        doc = AcctARDocument.query.get(link.ar_document_id)
        if doc and doc.status == 'Open':
            doc.status = 'Void'
            meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
            meta['void_reason'] = reason or 'construction_reversal'
            doc.details_json = json.dumps(meta)
    if link.ap_document_id:
        doc = AcctAPDocument.query.get(link.ap_document_id)
        if doc and doc.status == 'Open':
            doc.status = 'Void'
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    revs = settings.get('construction_reversals') or []
    revs.append({
        'source_key': source_key,
        'at': datetime.utcnow().isoformat() + 'Z',
        'reason': reason[:200],
        'journal_batch_ids': reversed_batches,
    })
    settings['construction_reversals'] = revs[-50:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='construction_reverse', details={'source_key': source_key})
    return {'source_key': source_key, 'reversal_batches': reversed_batches}


def project_accounting_closeout_checklist(
    db, models, ledger_id: int, project_id: int, PayAppProjectState=None, Commitment=None,
) -> dict:
    from accounting_waves_19 import g702_pending_ar_sync
    from accounting_waves_21 import sub_pay_app_pending_ap_sync, commitment_pending_accounting
    from accounting_waves_22 import change_order_pending_accounting

    items = []
    if PayAppProjectState:
        g702 = g702_pending_ar_sync(db, models, ledger_id, project_id, PayAppProjectState)
        sub = sub_pay_app_pending_ap_sync(db, models, ledger_id, project_id, PayAppProjectState)
        if g702.get('pending'):
            items.append({'id': 'g702_pending', 'severity': 'warning', 'label': f'{len(g702["pending"])} G702 period(s) not in A/R'})
        if sub.get('pending'):
            items.append({'id': 'sub_ap_pending', 'severity': 'warning', 'label': f'{len(sub["pending"])} sub pay app(s) not in A/P'})
    if Commitment:
        cmt = commitment_pending_accounting(db, models, ledger_id, project_id, Commitment)
        if cmt.get('pending'):
            items.append({'id': 'commitment_pending', 'severity': 'warning', 'label': f'{len(cmt["pending"])} commitment(s) not posted'})
        import app as app_mod
        co = change_order_pending_accounting(db, models, ledger_id, project_id, app_mod.ChangeOrder)
        if co.get('pending'):
            items.append({'id': 'co_pending', 'severity': 'info', 'label': f'{len(co["pending"])} change order(s) not posted'})
    ret = project_retainage_summary(db, models, ledger_id, project_id, PayAppProjectState)
    if ret.get('owner_retainage_pay_apps', 0) > 0 and not ret.get('accounting_holds'):
        items.append({'id': 'retainage', 'severity': 'info', 'label': 'Owner retainage on pay apps — consider posting holds'})
    ok = not any(i['severity'] == 'warning' for i in items)
    return {'project_id': int(project_id), 'ready_to_close': ok, 'items': items}


def cron_wave13_summary_email(db, models, secret: str) -> dict:
    import os

    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_22 import cron_wave12_maintenance

    base = cron_wave12_maintenance(db, models, secret)
    return {'wave12': base, 'note': 'Wave 13 uses wave 12 cron; closeout is per-project via API.'}
