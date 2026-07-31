"""
Waves 66–68 — JC/CIP→FA capitalization, POC revenue & retainage release, WIP auto-JE + Sage GL.
"""
from __future__ import annotations

import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import (
    SAGE_MIRROR_CAPABILITIES,
    _ledger_settings,
    _save_ledger_settings,
    sage_write_guard,
)


def _project_cip_gl_balance(db, models, ledger_id: int, project_id: int) -> float:
    from accounting_posting import _account_by_number

    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctGLAccount = models['AcctGLAccount']
    try:
        cip = _account_by_number(AcctGLAccount, ledger_id, '1300')
    except ValueError:
        return 0.0
    net = 0.0
    for ln in AcctJournalLine.query.filter_by(project_id=int(project_id), account_id=cip.id).all():
        batch = AcctJournalBatch.query.get(ln.batch_id)
        if not batch or batch.ledger_id != ledger_id or batch.status != 'Posted':
            continue
        net += float(ln.debit or 0) - float(ln.credit or 0)
    return round(net, 2)


# --- Wave 66: JC → CIP → FA ---

def jc_cip_fa_capitalization_preview(
    db, models, ledger_id: int, project_id: int, *, Project=None,
) -> dict:
    from accounting_waves_22 import _gl_job_cost_to_date

    project = Project.query.get(int(project_id)) if Project else None
    job_cost = _gl_job_cost_to_date(db, models, ledger_id, project_id)
    cip_balance = _project_cip_gl_balance(db, models, ledger_id, project_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    transfers = [t for t in (settings.get('jc_fa_transfers') or []) if t.get('project_id') == int(project_id)]
    capitalized = round(sum(float(t.get('amount') or 0) for t in transfers), 2)
    ready = max(0.0, round(cip_balance or job_cost, 2) - capitalized)
    return {
        'project_id': int(project_id),
        'project_name': getattr(project, 'name', '') if project else '',
        'job_cost_to_date': job_cost,
        'cip_gl_balance': cip_balance,
        'already_capitalized': capitalized,
        'ready_to_capitalize': ready,
        'prior_transfers': transfers[-5:],
    }


def jc_capitalize_cip_to_fixed_asset(
    db,
    models,
    ledger_id: int,
    project_id: int,
    amount: float,
    *,
    description: str | None = None,
    user_id=None,
    Project=None,
) -> dict:
    from accounting_posting import _account_by_number, _create_posted_batch

    preview = jc_cip_fa_capitalization_preview(db, models, ledger_id, project_id, Project=Project)
    amt = round(float(amount or 0), 2)
    if amt <= 0:
        raise ValueError('Capitalization amount must be positive')
    if amt > preview['ready_to_capitalize'] + 0.01:
        raise ValueError('Amount exceeds ready-to-capitalize balance')
    AcctGLAccount = models['AcctGLAccount']
    cip = _account_by_number(AcctGLAccount, ledger_id, '1300')
    fa = _account_by_number(AcctGLAccount, ledger_id, '1700')
    desc = (description or f'JC CIP capitalization P{project_id}')[:120]
    batch = _create_posted_batch(
        db,
        models,
        ledger_id=ledger_id,
        source='JC-FA',
        description=desc,
        user_id=user_id,
        lines=[
            {'account_id': fa.id, 'debit': amt, 'credit': 0, 'project_id': project_id},
            {'account_id': cip.id, 'debit': 0, 'credit': amt, 'project_id': project_id},
        ],
    )
    AcctFixedAsset = models.get('AcctFixedAsset')
    asset_id = None
    if AcctFixedAsset:
        asset = AcctFixedAsset(
            ledger_id=ledger_id,
            asset_number=f'JC-{project_id}-{batch.id}'[:40],
            description=desc[:200],
            acquisition_cost=amt,
            status='Active',
        )
        if hasattr(asset, 'project_id'):
            asset.project_id = int(project_id)
        db.session.add(asset)
        db.session.flush()
        asset_id = asset.id
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    entry = {
        'project_id': int(project_id),
        'amount': amt,
        'journal_batch_id': batch.id,
        'asset_id': asset_id,
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['jc_fa_transfers'] = (settings.get('jc_fa_transfers') or [])[-50:] + [entry]
    _save_ledger_settings(ledger, settings)
    queue = sage_queue_fa_capitalization(db, models, ledger_id, entry, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='jc_cip_fa_capitalize', details=entry)
    return {'journal_batch_id': batch.id, 'asset_id': asset_id, 'amount': amt, 'sage_queue': queue}


def sage_queue_fa_capitalization(db, models, ledger_id: int, transfer: dict, user_id=None) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'fa', 'push')
    payload = {
        'AssetNumber': f"CPM-JC-{transfer.get('project_id')}-{transfer.get('journal_batch_id')}"[:40],
        'Description': 'CasePM JC capitalization',
        'AcquisitionCost': float(transfer.get('amount') or 0),
        'ProjectId': transfer.get('project_id'),
    }
    resp = post_resource('FA', 'FAAssets', payload)
    q = settings.get('sage_fa_capitalization_queue') or []
    q.append({**transfer, 'sage_ok': resp.get('ok'), 'mode': resp.get('mode')})
    settings['sage_fa_capitalization_queue'] = q[-40:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_fa_cap_queue', details={'ok': resp.get('ok')})
    return {'queued': True, 'sage': resp}


def project_fa_transfer_report(db, models, ledger_id: int, project_id: int | None = None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    rows = settings.get('jc_fa_transfers') or []
    if project_id is not None:
        rows = [r for r in rows if r.get('project_id') == int(project_id)]
    return {'transfers': rows[-30:], 'queue': (settings.get('sage_fa_capitalization_queue') or [])[-15:]}


# --- Wave 67: POC revenue & retainage release ---

def save_project_revenue_method(
    db, models, ledger_id: int, project_id: int, method: str, user_id=None,
) -> dict:
    allowed = {'poc_cost', 'poc_billing', 'completed_contract', 'cash'}
    m = (method or 'poc_cost').lower()[:30]
    if m not in allowed:
        raise ValueError(f'Unsupported revenue method: {method}')
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.setdefault('project_revenue_methods', {})
    reg[str(int(project_id))] = m
    settings['project_revenue_methods'] = reg
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='project_revenue_method', details={'project_id': project_id, 'method': m})
    return {'project_id': int(project_id), 'method': m}


def project_revenue_recognition_report(
    db, models, ledger_id: int, project_id: int, *, Project=None, PayAppProjectState=None,
) -> dict:
    from accounting_waves_22 import contractual_wip_analysis

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    method = (settings.get('project_revenue_methods') or {}).get(str(int(project_id))) or 'poc_cost'
    wip = contractual_wip_analysis(
        db, models, ledger_id, project_id, Project=Project, PayAppProjectState=PayAppProjectState,
    )
    earned = float(wip.get('earned_revenue') or 0)
    billed = float(wip.get('billed_ar') or 0)
    if method == 'poc_billing':
        earned = billed
    elif method == 'completed_contract':
        pct = wip.get('percent_complete') or 0
        earned = earned if pct >= 100 else 0.0
    elif method == 'cash':
        earned = billed
    from accounting_waves_23 import project_retainage_summary

    retainage = project_retainage_summary(db, models, ledger_id, project_id, PayAppProjectState=PayAppProjectState)
    return {
        'project_id': int(project_id),
        'revenue_method': method,
        'wip': wip,
        'recognized_revenue': round(earned, 2),
        'billed_ar': billed,
        'retainage': retainage,
    }


def automated_retainage_release_candidates(
    db, models, ledger_id: int, *, Project=None, PayAppProjectState=None, pct_threshold: float = 95.0,
) -> dict:
    if not Project:
        return {'candidates': []}
    candidates = []
    for p in Project.query.filter_by(status='Active').limit(50).all():
        report = project_revenue_recognition_report(
            db, models, ledger_id, p.id, Project=Project, PayAppProjectState=PayAppProjectState,
        )
        wip = report.get('wip') or {}
        pct = float(wip.get('percent_complete') or 0)
        ret = report.get('retainage') or {}
        releasable = round(float(ret.get('ar_retainage_held') or 0), 2)
        if pct >= pct_threshold and releasable > 0:
            candidates.append({
                'project_id': p.id,
                'name': getattr(p, 'name', ''),
                'percent_complete': pct,
                'releasable_ar_retainage': releasable,
            })
    return {'candidates': candidates, 'threshold_pct': pct_threshold}


def run_automated_retainage_release(
    db,
    models,
    ledger_id: int,
    project_id: int,
    *,
    customer_id: int | None = None,
    amount: float | None = None,
    push_sage: bool = True,
    user_id=None,
    PayAppProjectState=None,
    Project=None,
) -> dict:
    from accounting_waves_23 import project_retainage_summary, release_owner_retainage_to_ar
    from accounting_waves_26 import push_retainage_release_to_sage

    report = project_revenue_recognition_report(
        db, models, ledger_id, project_id, Project=Project, PayAppProjectState=PayAppProjectState,
    )
    ret = project_retainage_summary(db, models, ledger_id, project_id, PayAppProjectState=PayAppProjectState)
    amt = round(float(amount if amount is not None else ret.get('ar_retainage_held') or 0), 2)
    if amt <= 0:
        raise ValueError('No retainage available to release')
    cid = customer_id
    if not cid and Project:
        project = Project.query.get(int(project_id))
        cid = getattr(project, 'customer_id', None) or getattr(project, 'acct_customer_id', None)
    if not cid:
        raise ValueError('customer_id required for retainage release')
    release = release_owner_retainage_to_ar(db, models, ledger_id, project_id, amt, int(cid), user_id=user_id)
    sage = None
    if push_sage:
        sage = push_retainage_release_to_sage(db, models, ledger_id, release['ar_document_id'], user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('sage_auto_retainage_releases') or []
    log.append({
        'project_id': int(project_id),
        'amount': amt,
        'ar_document_id': release['ar_document_id'],
        'at': datetime.utcnow().isoformat() + 'Z',
        'revenue_report': {'method': report.get('revenue_method'), 'pct': (report.get('wip') or {}).get('percent_complete')},
    })
    settings['sage_auto_retainage_releases'] = log[-30:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='auto_retainage_release', details={'project_id': project_id, 'amount': amt})
    return {'release': release, 'sage_push': sage, 'revenue': report}


# --- Wave 68: WIP auto-JE, Sage GL, month-close gate ---

def wip_auto_je_with_sor_guard(db, models, ledger_id: int, project_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sor = (settings.get('system_of_record') or 'casepm').lower()
    if sor == 'sage' and settings.get('sage_read_only_mode') != '1':
        sage_write_guard(settings, 'gl', 'push')
    from accounting_waves_22 import contractual_wip_analysis, maybe_auto_wip_adjustment

    analysis = contractual_wip_analysis(db, models, ledger_id, project_id)
    auto = maybe_auto_wip_adjustment(db, models, ledger_id, project_id, user_id=user_id)
    if auto:
        return {'posted': True, 'sor': sor, **auto}
    from accounting_waves_21 import post_wip_billing_adjustment

    if analysis.get('status') == 'ok':
        return {'posted': False, 'reason': 'within_threshold', 'analysis': analysis, 'sor': sor}
    out = post_wip_billing_adjustment(
        db, models, ledger_id, project_id, user_id=user_id, amount=analysis.get('over_under_billing'),
    )
    return {'posted': True, 'sor': sor, **out}


def sage_push_wip_gl_batches(db, models, ledger_id: int, user_id=None, limit: int = 10) -> dict:
    from accounting_waves_24 import sage_push_posted_gl_batches

    AcctJournalBatch = models['AcctJournalBatch']
    wip_ids = [
        b.id
        for b in AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted', source='WIP').order_by(
            AcctJournalBatch.id.desc(),
        ).limit(limit).all()
    ]
    jc_ids = [
        b.id
        for b in AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted', source='JC-FA').order_by(
            AcctJournalBatch.id.desc(),
        ).limit(limit).all()
    ]
    push = sage_push_posted_gl_batches(db, models, ledger_id, user_id=user_id, limit=limit)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_wip_gl_push_last'] = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'wip_batch_ids': wip_ids,
        'jc_fa_batch_ids': jc_ids,
        'push': {'processed': push.get('processed')},
    }
    _save_ledger_settings(ledger, settings)
    return {'wip_batches': wip_ids, 'jc_fa_batches': jc_ids, **push}


def jc_financial_month_close_gate(db, models, ledger_id: int, *, Project=None) -> dict:
    from accounting_waves_28 import month_close_wizard_state
    from accounting_waves_32 import portfolio_job_variance_v2

    wizard = month_close_wizard_state(db, models, ledger_id)
    portfolio = portfolio_job_variance_v2(db, models, ledger_id, Project=Project) if Project else {'projects': []}
    wip_issues = []
    for row in portfolio.get('projects') or []:
        wip = row.get('wip') or {}
        if wip.get('status') in ('overbilled', 'underbilled'):
            wip_issues.append({'project_id': row.get('project_id'), 'status': wip.get('status'), 'over_under': wip.get('over_under_billing')})
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    fa_queue = len(settings.get('sage_fa_capitalization_queue') or [])
    retainage_pending = len(automated_retainage_release_candidates(db, models, ledger_id, Project=Project).get('candidates') or [])
    blockers = []
    if wip_issues:
        blockers.append({'type': 'wip_variance', 'count': len(wip_issues)})
    if retainage_pending:
        blockers.append({'type': 'retainage_release_pending', 'count': retainage_pending})
    if fa_queue > 20:
        blockers.append({'type': 'fa_cap_queue_depth', 'count': fa_queue})
    ready = wizard.get('ready') and not blockers
    return {
        'wizard': wizard,
        'wip_issues': wip_issues[:25],
        'blockers': blockers,
        'ready': ready,
        'portfolio_project_count': len(portfolio.get('projects') or []),
    }


def validate_jc_fa_cap_fixture() -> dict:
    from accounting_waves_28 import load_fixture_row

    data = load_fixture_row('gl_journal_batch_sample.json')
    rows = data.get('value') or []
    if not rows:
        return {'ok': False}
    row = rows[0]
    ok = bool(row.get('BatchNumber'))
    return {'ok': ok, 'batch': row.get('BatchNumber')}


def cron_waves_66_68_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    runs = []
    for ledger in AcctLedger.query.limit(5).all():
        entry = {
            'ledger_id': ledger.id,
            'month_close_gate': jc_financial_month_close_gate(db, models, ledger.id, Project=Project),
            'retainage_scan': automated_retainage_release_candidates(
                db, models, ledger.id, Project=Project, PayAppProjectState=PayAppProjectState,
            ),
            'wip_gl_push': sage_push_wip_gl_batches(db, models, ledger.id),
        }
        runs.append(entry)
    return {'ledgers': runs}


def cron_sage_jc_financial_batch(
    db, models, secret: str, Project=None, PayAppProjectState=None, Commitment=None,
) -> dict:
    from accounting_waves_37 import cron_waves_50_64_combined

    base = cron_waves_50_64_combined(
        db, models, secret, Project=Project, PayAppProjectState=PayAppProjectState, Commitment=Commitment,
    )
    jc = cron_waves_66_68_maintenance(db, models, secret, Project=Project, PayAppProjectState=PayAppProjectState)
    v11 = sage_mirror_deploy_check_v11()
    return {'advanced_batch': base, 'jc_financial_66_68': jc, 'deploy_v11': v11}


def sage_mirror_deploy_check_v11() -> dict:
    from accounting_waves_37 import sage_mirror_deploy_check_v10

    base = sage_mirror_deploy_check_v10()
    checks = {
        'wave_66_jc_fa': True,
        'wave_67_retainage': True,
        'wave_68_wip_gl': True,
    }
    try:
        assert callable(jc_capitalize_cip_to_fixed_asset)
        assert callable(run_automated_retainage_release)
        assert callable(wip_auto_je_with_sor_guard)
        fix = validate_jc_fa_cap_fixture()
        checks['wave_66_jc_fa'] = fix.get('ok', False)
    except Exception:
        checks['wave_66_jc_fa'] = False
        checks['wave_67_retainage'] = False
        checks['wave_68_wip_gl'] = False
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v10': base, 'wave_checks': checks}


SAGE_MIRROR_CAPABILITIES['fa'] = {
    **SAGE_MIRROR_CAPABILITIES.get('fa', {}),
    'jc_capitalization': True,
    'notes': (SAGE_MIRROR_CAPABILITIES.get('fa', {}).get('notes') or '') + '; JC CIP capitalization queue',
}
