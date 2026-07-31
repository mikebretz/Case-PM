"""
Wave 12 — contract/budget WIP, CO↔accounting hooks, bank rec workspace,
year-end tax bundles, Sage ops + deploy checks.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime, timedelta

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


def _flag(key: str, default: str = '1') -> bool:
    from program_settings_persistence import load_accounting_defaults

    return str(load_accounting_defaults().get(key, default)) != '0'


def _project_contract_amount(project) -> float:
    if not project:
        return 0.0
    try:
        details = project.get_details() if hasattr(project, 'get_details') else {}
        raw = details.get('original_contract_amount')
        if raw is not None:
            return float(raw)
    except Exception:
        pass
    return float(getattr(project, 'contract_value', None) or 0)


def _approved_co_total(ChangeOrder, ChangeOrderAllocation, project_id: int) -> float:
    if not ChangeOrder:
        return 0.0
    total = 0.0
    for co in ChangeOrder.query.filter_by(project_id=int(project_id), status='Approved').all():
        if ChangeOrderAllocation:
            allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
            if allocs:
                total += sum(float(a.amount or 0) for a in allocs)
                continue
        total += float(co.amount or 0)
    return round(total, 2)


def _budget_totals(BudgetProjectState, project_id: int) -> dict:
    if not BudgetProjectState:
        return {'original': 0.0, 'revised': 0.0, 'cost_to_date': 0.0}
    try:
        from budget_persistence import get_budget_state

        _, state = get_budget_state(BudgetProjectState, int(project_id))
        state = state or {}
        lines = state.get('budgetLines') or []
        original = revised = 0.0
        for ln in lines:
            if not isinstance(ln, dict):
                continue
            ob = float(ln.get('original_budget') or 0)
            ac = float(ln.get('approved_changes') or 0)
            original += ob
            revised += ob + ac
        return {'original': round(original, 2), 'revised': round(revised, 2)}
    except Exception:
        return {'original': 0.0, 'revised': 0.0}


def _gl_job_cost_to_date(db, models, ledger_id: int, project_id: int) -> float:
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctGLAccount = models['AcctGLAccount']
    net = 0.0
    for ln in AcctJournalLine.query.filter_by(project_id=int(project_id)).all():
        batch = AcctJournalBatch.query.get(ln.batch_id)
        if not batch or batch.ledger_id != ledger_id or batch.status != 'Posted':
            continue
        acct = AcctGLAccount.query.get(ln.account_id)
        if not acct:
            continue
        atype = (acct.account_type or '').lower()
        if atype not in ('expense', 'cost', 'cost of goods sold', 'cogs'):
            continue
        net += float(ln.debit or 0) - float(ln.credit or 0)
    return round(net, 2)


# --- 1: Contract / budget WIP ---

def contractual_wip_analysis(
    db,
    models,
    ledger_id: int,
    project_id: int,
    *,
    Project=None,
    ChangeOrder=None,
    ChangeOrderAllocation=None,
    BudgetProjectState=None,
    PayAppProjectState=None,
) -> dict:
    from accounting_waves_20 import jobcost_variance_breakdown
    from accounting_waves_21 import sub_pay_app_pending_ap_sync

    project = Project.query.get(int(project_id)) if Project else None
    base_contract = _project_contract_amount(project)
    co_total = _approved_co_total(ChangeOrder, ChangeOrderAllocation, project_id)
    contract = round(base_contract + co_total, 2)
    budget = _budget_totals(BudgetProjectState, project_id)
    cost_to_date = _gl_job_cost_to_date(db, models, ledger_id, project_id)
    revised_budget = budget['revised'] or budget['original'] or 0.0

    if revised_budget > 0 and cost_to_date >= 0:
        pct = min(round(cost_to_date / revised_budget * 100.0, 2), 100.0)
        method = 'cost_to_cost'
    elif contract > 0:
        var = jobcost_variance_breakdown(db, models, ledger_id, project_id, PayAppProjectState)
        billed = float(var.get('billed_ar') or 0)
        pct = min(round(billed / contract * 100.0, 2), 100.0)
        method = 'billings_to_contract'
    else:
        pct = 0.0
        method = 'none'

    earned = round(contract * pct / 100.0, 2)
    var = jobcost_variance_breakdown(db, models, ledger_id, project_id, PayAppProjectState)
    billed_ar = float(var.get('billed_ar') or 0)
    over_under = round(billed_ar - earned, 2)
    ledger = models['AcctLedger'].query.get(ledger_id)
    threshold = float((_ledger_settings(ledger) or {}).get('wip_alert_threshold') or 5000)

    return {
        'project_id': int(project_id),
        'contract_base': base_contract,
        'approved_change_orders': co_total,
        'contract_value': contract,
        'budget_revised': revised_budget,
        'cost_to_date': cost_to_date,
        'percent_complete': pct,
        'completion_method': method,
        'earned_revenue': earned,
        'billed_ar': billed_ar,
        'over_under_billing': over_under,
        'status': 'overbilled' if over_under > threshold else ('underbilled' if over_under < -threshold else 'ok'),
        'wip_alert_threshold': threshold,
        'g702_pending': var.get('g702_pending_sync') or [],
        'sub_ap_pending': (
            sub_pay_app_pending_ap_sync(db, models, ledger_id, project_id, PayAppProjectState).get('pending')
            if PayAppProjectState else []
        ),
    }


def maybe_auto_wip_adjustment(db, models, ledger_id: int, project_id: int, user_id=None) -> dict | None:
    if not _flag('auto_wip_on_billing_sync', '0'):
        return None
    analysis = contractual_wip_analysis(db, models, ledger_id, project_id)
    if analysis['status'] == 'ok':
        return None
    if abs(analysis['over_under_billing']) < analysis['wip_alert_threshold']:
        return None
    from accounting_waves_21 import post_wip_billing_adjustment

    return post_wip_billing_adjustment(
        db, models, ledger_id, project_id, user_id=user_id, amount=analysis['over_under_billing'],
    )


# --- 2: Change orders & budget variance ---

def change_order_pending_accounting(db, models, ledger_id: int, project_id: int, ChangeOrder) -> dict:
    AcctPostLink = models['AcctPostLink']
    pending = []
    posted = []
    for co in ChangeOrder.query.filter_by(project_id=int(project_id), status='Approved').all():
        idem = f'ChangeOrderApproved:{co.id}'
        link = AcctPostLink.query.filter_by(ledger_id=ledger_id, source_key=idem).first()
        amt = float(co.amount or 0)
        row = {'change_order_id': co.id, 'number': co.number, 'amount': round(amt, 2), 'idempotency_key': idem}
        if link:
            posted.append({**row, 'journal_batch_id': link.journal_batch_id})
        elif amt > 0:
            pending.append(row)
    return {'project_id': project_id, 'pending': pending, 'posted': posted}


def sync_change_order_to_accounting(
    db, models, ledger_id: int, change_order_id: int, user_id=None, ChangeOrder=None, ChangeOrderAllocation=None, Project=None,
) -> dict:
    from accounting_posting import process_construction_event

    co = ChangeOrder.query.get(int(change_order_id))
    if not co:
        raise ValueError('Change order not found')
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all() if ChangeOrderAllocation else []
    amt = float(co.amount or 0)
    if allocs:
        amt = sum(float(a.amount or 0) for a in allocs) or amt
    payload = {
        'change_order_id': co.id,
        'co_number': co.number,
        'amount': amt,
        'idempotency_key': f'ChangeOrderApproved:{co.id}',
        'force_builtin_post': True,
    }
    out = process_construction_event(
        'ChangeOrderApproved',
        co.project_id,
        payload,
        db=db,
        models=models,
        user_id=user_id,
        Project=Project,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='co_accounting_sync', entity_id=co.id, details=out)
    return out


def sync_all_change_orders_pending(
    db, models, ledger_id: int, project_id: int, user_id=None, ChangeOrder=None, ChangeOrderAllocation=None, Project=None,
) -> dict:
    pending = change_order_pending_accounting(db, models, ledger_id, project_id, ChangeOrder)
    posted = []
    errors = []
    for row in pending.get('pending') or []:
        try:
            out = sync_change_order_to_accounting(
                db, models, ledger_id, row['change_order_id'], user_id=user_id,
                ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation, Project=Project,
            )
            if out.get('posted'):
                posted.append({**row, **out})
        except Exception as exc:
            errors.append({**row, 'error': str(exc)})
    return {'posted_count': len(posted), 'posted': posted, 'errors': errors}


def process_co_approval_accounting(co, db, *, user_id=None, ChangeOrderAllocation=None, Commitment=None, Project=None) -> dict:
    """Hook from change order workflow on final approval."""
    import app as app_mod

    models = app_mod._acct_models
    from accounting_persistence import get_or_create_default_ledger

    ledger = get_or_create_default_ledger(db, models['AcctLedger'])
    lid = ledger.id
    if not _flag('co_post_on_approve', '1'):
        return {'skipped': 'co_post_on_approve_disabled'}
    try:
        from co_persistence import is_subcontract_co

        if is_subcontract_co(co) and Commitment is not None and getattr(co, 'linked_commitment_ref', None):
            com = Commitment.query.filter_by(project_id=co.project_id, number=co.linked_commitment_ref).first()
            if com:
                from accounting_waves_21 import post_commitment_change_order

                amt = float(co.amount or 0)
                if ChangeOrderAllocation:
                    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
                    if allocs:
                        amt = sum(float(a.amount or 0) for a in allocs)
                return post_commitment_change_order(
                    db, models, lid,
                    {'commitment_id': com.id, 'change_order_id': co.id, 'amount': amt, 'co_number': co.number},
                    user_id=user_id, Commitment=Commitment, Project=Project, Company=app_mod.Company,
                )
        return sync_change_order_to_accounting(
            db, models, lid, co.id, user_id=user_id,
            ChangeOrder=app_mod.ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation, Project=Project,
        )
    except Exception as exc:
        return {'error': str(exc)}


def budget_cost_gl_variance(db, models, ledger_id: int, project_id: int, BudgetProjectState) -> dict:
    budget = _budget_totals(BudgetProjectState, project_id)
    gl_cost = _gl_job_cost_to_date(db, models, ledger_id, project_id)
    try:
        from pay_app_persistence import get_pay_app_state

        _, pay_state = get_pay_app_state(None, int(project_id))
        pay_billed = 0.0
        for p in (pay_state or {}).get('periods') or []:
            if isinstance(p, dict):
                pay_billed += float(p.get('currentPaymentDue') or p.get('amountDue') or 0)
    except Exception:
        pay_billed = 0.0
    AcctAPDocument = models['AcctAPDocument']
    ap_open = sum(
        float(d.amount or 0) for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, project_id=int(project_id), status='Open').all()
    )
    return {
        'project_id': int(project_id),
        'budget_revised': budget['revised'],
        'gl_cost_to_date': gl_cost,
        'budget_vs_gl': round(budget['revised'] - gl_cost, 2),
        'pay_app_billed_total': round(pay_billed, 2),
        'open_ap_on_job': round(ap_open, 2),
    }


# --- 3: Bank reconciliation ---

def bank_reconciliation_workspace(db, models, ledger_id: int, bank_account_id: int) -> dict:
    from accounting_all_chunks import bank_auto_match_suggestions

    AcctBankTransaction = models['AcctBankTransaction']
    AcctBankAccount = models['AcctBankAccount']
    bank = AcctBankAccount.query.filter_by(id=int(bank_account_id), ledger_id=ledger_id).first()
    if not bank:
        raise ValueError('Bank account not found')
    txs = AcctBankTransaction.query.filter_by(bank_account_id=bank.id).order_by(AcctBankTransaction.id.desc()).limit(500).all()
    cleared = [t for t in txs if t.reconciled]
    open_tx = [t for t in txs if not t.reconciled]
    suggestions = bank_auto_match_suggestions(db, models, ledger_id, bank.id)
    return {
        'bank_account_id': bank.id,
        'name': bank.name,
        'last_reconciled_date': bank.last_reconciled_date.isoformat() if bank.last_reconciled_date else None,
        'cleared_count': len(cleared),
        'open_count': len(open_tx),
        'open_transactions': [
            {
                'id': t.id,
                'date': t.transaction_date.isoformat() if t.transaction_date else None,
                'amount': float(t.amount or 0),
                'description': (t.description or '')[:80],
                'reference': t.reference,
            }
            for t in open_tx[:40]
        ],
        'suggestions': suggestions.get('suggestions') or [],
    }


def apply_bank_auto_matches(db, models, ledger_id: int, bank_account_id: int, user_id=None) -> dict:
    from accounting_posting import reconcile_bank_transactions

    ws = bank_reconciliation_workspace(db, models, ledger_id, bank_account_id)
    ids = [s['bank_transaction_id'] for s in (ws.get('suggestions') or [])]
    out = reconcile_bank_transactions(db, models, bank_account_id, ids, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='bank_auto_match_apply', details={'matched': len(ids)})
    return {**out, 'matched_suggestions': len(ids)}


def pay_now_deposit_hints(db, models, ledger_id: int) -> dict:
    AcctPayNowLink = models['AcctPayNowLink']
    AcctBankTransaction = models['AcctBankTransaction']
    links = AcctPayNowLink.query.filter_by(status='Paid').order_by(AcctPayNowLink.id.desc()).limit(30).all()
    hints = []
    for link in links:
        amt = round(float(link.amount or 0), 2)
        if amt <= 0:
            continue
        tx = AcctBankTransaction.query.filter(
            AcctBankTransaction.amount == amt,
            AcctBankTransaction.reconciled.is_(False),
        ).order_by(AcctBankTransaction.id.desc()).first()
        hints.append({
            'pay_now_link_id': link.id,
            'token': link.token,
            'amount': amt,
            'suggested_bank_transaction_id': tx.id if tx else None,
        })
    return {'hints': hints}


# --- 4: Year-end tax ---

def validate_941_quarters(db, models, ledger_id: int, year: int) -> dict:
    from accounting_parity_wave3 import export_form_941_summary

    issues = []
    quarters = []
    for q in range(1, 5):
        data = export_form_941_summary(db, models, ledger_id, q, year)
        quarters.append(data)
        if data.get('pay_runs_included', 0) == 0 and data.get('wages_tips_other', 0) == 0:
            issues.append(f'Q{q}: no posted payroll runs in quarter')
    return {'year': year, 'quarters': quarters, 'issues': issues, 'ok': not issues}


def year_end_tax_package(db, models, ledger_id: int, tax_year: int) -> dict:
    from accounting_parity_wave3 import export_form_941_summary, export_w2_summary
    from accounting_parity_wave2 import export_1099_fire

    y = int(tax_year)
    v941 = validate_941_quarters(db, models, ledger_id, y)
    w2 = export_w2_summary(db, models, ledger_id, y)
    fire = export_1099_fire(db, models, ledger_id, y)
    return {
        'tax_year': y,
        'form_941': v941,
        'w2': w2,
        'form_1099_fire_preview': fire[:2000] if isinstance(fire, str) else fire,
        'disclaimer': 'CPA review required before agency filing.',
    }


def prevailing_wage_compare_report(db, models, ledger_id: int, project_id: int, week_ending: str, Project=None) -> dict:
    from accounting_waves_20 import certified_payroll_prevailing_daily_log

    base = certified_payroll_prevailing_daily_log(db, models, ledger_id, project_id, week_ending, Project=Project)
    rate = base.get('prevailing_wage_rate')
    warnings = []
    if rate is not None:
        try:
            r = float(rate)
            for line in (base.get('csv') or '').splitlines()[1:6]:
                parts = line.split(',')
                if len(parts) >= 4:
                    gross = float(parts[3]) if parts[3] else 0
                    hrs = float(parts[2]) if parts[2] else 0
                    if hrs > 0 and gross / hrs < r * 0.98:
                        warnings.append(f'Possible under-rate line: {line[:60]}')
        except Exception:
            pass
    base['prevailing_compare_warnings'] = warnings
    return base


# --- 5: Sage ops + deploy ---

def sage_pull_open_ar(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    resp = get_resource('AR', 'ARInvoices', top=limit)
    if not resp.get('ok'):
        return {'created': 0, 'message': resp.get('error') or resp.get('mode')}
    rows = (resp.get('data') or {}).get('value') or []
    created = skipped = 0
    for row in rows:
        inv = (row.get('InvoiceNumber') or row.get('DocumentNumber') or '').strip()
        if not inv:
            continue
        if AcctARDocument.query.filter_by(ledger_id=ledger_id, document_number=inv[:40]).first():
            skipped += 1
            continue
        ccode = (row.get('CustomerNumber') or '').strip().upper()
        cust = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=ccode).first() if ccode else None
        if not cust:
            skipped += 1
            continue
        amt = float(row.get('InvoiceAmount') or row.get('Amount') or 0)
        doc = AcctARDocument(
            ledger_id=ledger_id,
            customer_id=cust.id,
            document_number=inv[:40],
            document_type='SageImport',
            document_date=date.today(),
            amount=amt,
            status='Open',
        )
        db.session.add(doc)
        created += 1
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_open_ar', details={'created': created})
    return {'created': created, 'skipped': skipped, 'mode': resp.get('mode')}


def sage_ops_dashboard(db, models, ledger_id: int) -> dict:
    from accounting_waves_21 import sage_hybrid_exception_inbox

    inbox = sage_hybrid_exception_inbox(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {
        **inbox,
        'last_wave11_cron': settings.get('last_wave11_cron'),
        'last_wave12_cron': settings.get('last_wave12_cron'),
    }


def cron_wave12_maintenance(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_21 import cron_wave11_maintenance
    from accounting_waves_20 import notify_admin_schedule_failures

    wave11 = cron_wave11_maintenance(db, models, secret)
    AcctLedger = models['AcctLedger']
    extras = []
    for ledger in AcctLedger.query.limit(20).all():
        settings = _ledger_settings(ledger)
        settings['last_wave12_cron'] = datetime.utcnow().isoformat() + 'Z'
        _save_ledger_settings(ledger, settings)
        inbox = sage_ops_dashboard(db, models, ledger.id)
        err_count = len(inbox.get('ap_push_errors') or []) + len(inbox.get('vendor_conflicts') or [])
        notify = None
        if err_count > 0:
            try:
                from program_settings_persistence import load_program_settings
                from email_notifications import send_workflow_email

                email = (load_program_settings().get('email') or {}).get('admin_notification_email') or ''
                if email.strip():
                    body = f'Sage ops alert: {err_count} issue(s) on ledger {ledger.id}. Review Accounting → Sage exception inbox.'
                    send_workflow_email(email.strip(), 'Case PM — Sage ops alert', f'<p>{body}</p>', body)
                    notify = True
            except Exception:
                notify = False
        extras.append({'ledger_id': ledger.id, 'sage_issues': err_count, 'admin_notified': notify})
    return {'wave11': wave11, 'sage_ops': extras}


def deploy_accounting_check(app_root: str | None = None) -> dict:
    root = app_root or os.path.abspath(os.path.dirname(__file__) or '.')
    results = []
    for label, cmd in (
        ('smoke', [os.environ.get('PYTHON', 'python3'), 'scripts/test_accounting_smoke.py']),
        ('startup_guard', [os.environ.get('PYTHON', 'python3'), 'scripts/accounting_startup_guard.py']),
    ):
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120, env={**os.environ, 'PYTHONPATH': root})
            results.append({'check': label, 'ok': proc.returncode == 0, 'detail': (proc.stdout or proc.stderr or '')[-500:]})
        except Exception as exc:
            results.append({'check': label, 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_24 import sage_mirror_deploy_check
        mirror = sage_mirror_deploy_check()
        results.append({'check': 'sage_mirror', 'ok': mirror.get('ok'), 'detail': str(mirror)})
    except Exception as exc:
        results.append({'check': 'sage_mirror', 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_27 import sage_mirror_deploy_check_v3
        mirror = sage_mirror_deploy_check_v3()
        results.append({'check': 'sage_mirror_v3', 'ok': mirror.get('ok'), 'detail': str(mirror)[:600]})
    except Exception as exc:
        results.append({'check': 'sage_mirror_v3', 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_28 import sage_mirror_deploy_check_v4
        mirror = sage_mirror_deploy_check_v4()
        results.append({'check': 'sage_mirror_v4', 'ok': mirror.get('ok'), 'detail': str(mirror)[:600]})
    except Exception as exc:
        results.append({'check': 'sage_mirror_v4', 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_29 import sage_mirror_deploy_check_v5
        mirror = sage_mirror_deploy_check_v5()
        results.append({'check': 'sage_mirror_v5', 'ok': mirror.get('ok'), 'detail': str(mirror)[:600]})
    except Exception as exc:
        results.append({'check': 'sage_mirror_v5', 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_30 import sage_mirror_deploy_check_v6
        mirror = sage_mirror_deploy_check_v6()
        results.append({'check': 'sage_mirror_v6', 'ok': mirror.get('ok'), 'detail': str(mirror)[:600]})
    except Exception as exc:
        results.append({'check': 'sage_mirror_v6', 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_31 import sage_mirror_deploy_check_v7
        mirror = sage_mirror_deploy_check_v7()
        results.append({'check': 'sage_mirror_v7', 'ok': mirror.get('ok'), 'detail': str(mirror)[:600]})
    except Exception as exc:
        results.append({'check': 'sage_mirror_v7', 'ok': False, 'detail': str(exc)})
    try:
        from accounting_waves_33 import sage_mirror_deploy_check_v8
        mirror = sage_mirror_deploy_check_v8()
        results.append({'check': 'sage_mirror_v8', 'ok': mirror.get('ok'), 'detail': str(mirror)[:600]})
    except Exception as exc:
        results.append({'check': 'sage_mirror_v8', 'ok': False, 'detail': str(exc)})
    return {'ok': all(r['ok'] for r in results), 'results': results}
