"""
PM–accounting polish: PJ cost-code reconcile, commitment PO one-step, AP compliance v2, deploy v14.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def sage_pj_cost_code_reconcile_report(
    db,
    models,
    ledger_id: int,
    project_id: int,
    *,
    BudgetProjectState=None,
    Commitment=None,
    CommitmentAllocation=None,
    user_id=None,
    pull_sage: bool = True,
) -> dict:
    """Sage PJ vs budget vs GL-ish job cost by cost code for one project."""
    from accounting_waves_44 import sage_pj_transactions_pull_v2
    from accounting_waves_22 import _gl_job_cost_to_date
    from budget_persistence import get_budget_state, normalize_cost_code

    pid = int(project_id)
    if pull_sage:
        sage_pj_transactions_pull_v2(db, models, ledger_id, project_id=pid, user_id=user_id, limit=100)

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    cache_key = str(pid)
    cache_rows = (settings.get('sage_pj_transactions_cache') or {}).get(cache_key, {}).get('rows') or []

    sage_by_code: dict[str, float] = {}
    for row in cache_rows:
        code = normalize_cost_code(
            row.get('CostCode') or row.get('cost_code') or row.get('Phase') or row.get('Account') or 'UNASSIGNED',
        ) or 'UNASSIGNED'
        amt = float(row.get('Amount') or row.get('TransactionAmount') or row.get('amount') or 0)
        sage_by_code[code] = round(sage_by_code.get(code, 0) + amt, 2)

    budget_by_code: dict[str, float] = {}
    if BudgetProjectState:
        _, state = get_budget_state(BudgetProjectState, pid)
        for ln in (state or {}).get('budgetLines') or []:
            code = normalize_cost_code(ln.get('cost_code') or '') or 'UNASSIGNED'
            val = float(ln.get('revised_budget') or ln.get('original_budget') or 0)
            budget_by_code[code] = round(budget_by_code.get(code, 0) + val, 2)

    committed_by_code: dict[str, float] = {}
    if Commitment and CommitmentAllocation:
        approved = {'Approved', 'Executed', 'Complete', 'Active'}
        for c in Commitment.query.filter_by(project_id=pid).all():
            if (c.status or '') not in approved:
                continue
            for alloc in CommitmentAllocation.query.filter_by(commitment_id=c.id).all():
                code = normalize_cost_code(getattr(alloc, 'cost_code', None) or '') or 'UNASSIGNED'
                amt = float(getattr(alloc, 'amount', None) or 0)
                committed_by_code[code] = round(committed_by_code.get(code, 0) + amt, 2)

    gl_by_code: dict[str, float] = {}
    code_re = re.compile(r'\d{2}-\d{4}')
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctGLAccount = models['AcctGLAccount']
    for ln in AcctJournalLine.query.filter_by(project_id=pid).all():
        batch = AcctJournalBatch.query.get(ln.batch_id)
        if not batch or batch.ledger_id != ledger_id or batch.status != 'Posted':
            continue
        acct = AcctGLAccount.query.get(ln.account_id)
        if not acct:
            continue
        atype = (acct.account_type or '').lower()
        if atype not in ('expense', 'cost', 'cost of goods sold', 'cogs'):
            continue
        net = float(ln.debit or 0) - float(ln.credit or 0)
        if net == 0:
            continue
        hint = (ln.reference or '') + ' ' + (ln.description or '') + ' ' + (batch.description or '')
        m = code_re.search(hint)
        code = normalize_cost_code(m.group(0)) if m else 'UNALLOCATED'
        gl_by_code[code] = round(gl_by_code.get(code, 0) + net, 2)

    codes = sorted(set(budget_by_code) | set(sage_by_code) | set(committed_by_code) | set(gl_by_code))
    lines = []
    for code in codes:
        budget = budget_by_code.get(code, 0)
        sage = sage_by_code.get(code, 0)
        committed = committed_by_code.get(code, 0)
        gl = gl_by_code.get(code, 0)
        lines.append({
            'cost_code': code,
            'budget_revised': budget,
            'committed': committed,
            'sage_pj': sage,
            'gl_job_cost': gl,
            'variance_sage_vs_budget': round(sage - budget, 2),
            'variance_gl_vs_budget': round(gl - budget, 2),
        })

    report = {
        'project_id': pid,
        'at': datetime.utcnow().isoformat() + 'Z',
        'sage_row_count': len(cache_rows),
        'gl_job_cost_total': _gl_job_cost_to_date(db, models, ledger_id, pid),
        'lines': lines,
    }
    settings['sage_pj_cost_code_reconcile'] = {str(pid): report}
    _save_ledger_settings(ledger, settings)
    write_audit(
        db, models, ledger_id, user_id=user_id,
        action='sage_pj_cost_code_reconcile', details={'project_id': pid, 'lines': len(lines)},
    )
    return report


def ensure_commitment_po_on_approve(
    db,
    models,
    ledger_id: int,
    commitment,
    post_out: dict | None,
    *,
    user_id=None,
    Commitment=None,
    CommitmentAllocation=None,
    Project=None,
    Company=None,
) -> dict:
    """Ensure accounting PO exists after commitment approval (one-step)."""
    from program_settings_persistence import load_accounting_defaults

    if str(load_accounting_defaults().get('commitment_po_one_step_on_approve', '1')) == '0':
        return {'skipped': 'policy_disabled', **(post_out or {})}

    out = dict(post_out or {})
    if out.get('purchase_order_id'):
        return out
    if out.get('skipped') == 'already_posted':
        AcctPostLink = models['AcctPostLink']
        link = AcctPostLink.query.filter_by(
            ledger_id=ledger_id,
            source_key=f'CommitmentApproved:{commitment.id}',
        ).first()
        if link and link.purchase_order_id:
            out['purchase_order_id'] = link.purchase_order_id
            return out

    from accounting_waves_21 import sync_commitment_to_accounting

    synced = sync_commitment_to_accounting(
        db, models, ledger_id, commitment.id, user_id=user_id,
        Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
        Project=Project, Company=Company,
    )
    out.update(synced)
    if str(load_accounting_defaults().get('commitment_po_queue_sage_distribution', '0')) == '1':
        try:
            from accounting_waves_24 import sage_queue_distribution_exports

            out['sage_distribution_queue'] = sage_queue_distribution_exports(
                db, models, ledger_id, user_id=user_id, limit=10,
            )
        except Exception as exc:
            out['sage_distribution_queue'] = {'error': str(exc)}
    return out


def _company_has_valid_coi(db, company_id, COI=None) -> bool:
    if not company_id or not COI:
        return True
    today = date.today()
    rows = COI.query.filter_by(company_id=int(company_id)).all()
    if not rows:
        return False
    for row in rows:
        exp = getattr(row, 'expiration_date', None) or getattr(row, 'expiration', None)
        if exp and exp >= today:
            return True
    return False


def _resolve_vendor_company_id(db, models, ledger_id: int, vendor_id: int) -> int | None:
    AcctVendor = models['AcctVendor']
    v = AcctVendor.query.filter_by(id=int(vendor_id), ledger_id=ledger_id).first()
    if v and getattr(v, 'company_id', None):
        return int(v.company_id)
    return None


def ap_payment_compliance_hold(
    db,
    models,
    ledger_id: int,
    vendor_id: int,
    applications: list,
    *,
    PayAppProjectState=None,
    Project=None,
    Company=None,
    COI=None,
    company_id: int | None = None,
) -> dict:
    """Lien waiver (vendor + company keys) and optional COI gate before AP payment."""
    from accounting_waves_43 import ap_payment_compliance_hold as _lien_hold
    from program_settings_persistence import load_accounting_defaults

    holds = []
    resolved_company = company_id or _resolve_vendor_company_id(db, models, ledger_id, vendor_id)
    defaults = load_accounting_defaults()
    if str(defaults.get('ap_require_valid_coi', '0')) == '1' and resolved_company:
        if not _company_has_valid_coi(db, resolved_company, COI=COI):
            holds.append({
                'reason': 'expired_or_missing_coi',
                'company_id': resolved_company,
                'vendor_id': vendor_id,
            })

    lien = _lien_hold(
        db, models, ledger_id, vendor_id, applications,
        PayAppProjectState=PayAppProjectState, Project=Project,
    )
    if lien.get('held'):
        for h in lien.get('holds') or []:
            h['company_id'] = h.get('company_id') or resolved_company
            holds.append(h)
    elif resolved_company and PayAppProjectState:
        from accounting_waves_43 import _vendor_has_waiver_for_period
        from pay_app_persistence import get_pay_app_state

        for app in applications or []:
            doc_id = app.get('ap_document_id')
            if not doc_id:
                continue
            doc = models['AcctAPDocument'].query.filter_by(id=int(doc_id), ledger_id=ledger_id).first()
            if not doc or not doc.project_id:
                continue
            _, state = get_pay_app_state(PayAppProjectState, int(doc.project_id))
            waivers = (state or {}).get('subLienWaivers') or {}
            company_key = str(resolved_company)
            if not _vendor_has_waiver_for_period(waivers, company_key, doc):
                if not _vendor_has_waiver_for_period(waivers, str(vendor_id), doc):
                    holds.append({
                        'ap_document_id': doc.id,
                        'project_id': int(doc.project_id),
                        'company_id': resolved_company,
                        'reason': 'missing_sub_lien_waiver',
                        'document_number': doc.document_number,
                    })

    if holds:
        ledger = models['AcctLedger'].query.get(ledger_id)
        settings = _ledger_settings(ledger)
        settings['ap_compliance_holds'] = holds[-30:]
        _save_ledger_settings(ledger, settings)
        return {'held': True, 'holds': holds}
    return {'held': False}


def set_sage_enforce_fiscal_close(db, models, ledger_id: int, enabled: bool, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_enforce_fiscal_close'] = '1' if enabled else '0'
    _save_ledger_settings(ledger, settings)
    write_audit(
        db, models, ledger_id, user_id=user_id,
        action='sage_enforce_fiscal_close', details={'enabled': enabled},
    )
    return {'sage_enforce_fiscal_close': settings['sage_enforce_fiscal_close']}


def sage_mirror_deploy_check_v14() -> dict:
    from accounting_waves_44 import sage_mirror_deploy_check_v13

    base = sage_mirror_deploy_check_v13()
    checks = {
        'pj_cost_code_reconcile': True,
        'commitment_po_one_step': True,
        'ap_compliance_v2': True,
        'pm_roadmap': True,
    }
    try:
        assert callable(sage_pj_cost_code_reconcile_report)
        assert callable(ensure_commitment_po_on_approve)
        assert callable(ap_payment_compliance_hold)
        import pm_product_roadmap  # noqa: F401
    except Exception:
        checks = {k: False for k in checks}
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v13': base, 'wave_checks': checks}
