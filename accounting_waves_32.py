"""
Waves 53–56 — CRE bridge completion: G702, sub billing, PCO, PJ job ledger.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_sync_get, sage_sync_set
from accounting_waves_25 import sage_queue_construction_mirror_event
from accounting_waves_28 import load_fixture_row


# --- Wave 53: Progress billing ---

def g702_ar_lifecycle_report(db, models, ledger_id: int, project_id: int, PayAppProjectState=None) -> dict:
    from accounting_waves_19 import g702_pending_ar_sync
    from accounting_waves_30 import g702_ar_external_key_report

    if not PayAppProjectState:
        return {'error': 'PayAppProjectState unavailable'}
    sync = g702_pending_ar_sync(db, models, ledger_id, project_id, PayAppProjectState)
    keys = g702_ar_external_key_report(db, models, ledger_id, project_id, PayAppProjectState=PayAppProjectState)
    retainage = []
    AcctARDocument = models['AcctARDocument']
    for row in sync.get('posted') or []:
        doc = AcctARDocument.query.get(row.get('ar_document_id')) if row.get('ar_document_id') else None
        if not doc:
            continue
        meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
        retainage.append({
            'period': row.get('period'),
            'document_id': doc.id,
            'retainage': meta.get('retainage_amount') or meta.get('sage', {}).get('retainage'),
            'sage_state': sage_sync_get(doc, 'sync_state'),
        })
    return {
        'project_id': project_id,
        'pending': sync.get('pending'),
        'posted_count': len(sync.get('posted') or []),
        'key_mismatches': keys.get('mismatch_count', 0),
        'retainage_rows': retainage,
    }


def g702_void_mirror_queue(db, models, ledger_id: int, project_id: int, period_number, user_id=None) -> dict:
    sage_queue_construction_mirror_event(
        db, models, ledger_id, 'G702Voided',
        {'project_id': project_id, 'period_number': period_number},
        user_id=user_id,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='g702_void_queue', details={'project_id': project_id, 'period': period_number})
    return {'queued': True, 'type': 'G702Voided'}


# --- Wave 54: Subcontractor billing ---

def sub_pay_app_ap_bridge_report(db, models, ledger_id: int, project_id: int, PayAppProjectState=None) -> dict:
    from accounting_waves_21 import sub_pay_app_pending_ap_sync

    if not PayAppProjectState:
        return {'error': 'PayAppProjectState unavailable'}
    pending = sub_pay_app_pending_ap_sync(db, models, ledger_id, project_id, PayAppProjectState)
    AcctAPDocument = models['AcctAPDocument']
    linked = []
    for row in pending.get('pending') or []:
        linked.append({**row, 'sage_sync': None})
    for row in pending.get('posted') or []:
        doc = AcctAPDocument.query.get(row.get('ap_document_id')) if row.get('ap_document_id') else None
        linked.append({
            **row,
            'sage_sync': sage_sync_get(doc, 'sync_state') if doc else None,
        })
    return {'project_id': project_id, 'pending_count': len(pending.get('pending') or []), 'rows': linked[:40]}


def sub_compliance_hold_state(db, models, ledger_id: int, project_id: int, PayAppProjectState=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    holds = (settings.get('sage_sub_compliance_holds') or {}).get(str(project_id)) or []
    blocked = bool(holds)
    return {'project_id': project_id, 'holds': holds, 'ap_post_blocked': blocked}


def set_sub_compliance_hold(db, models, ledger_id: int, project_id: int, reason: str, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.setdefault('sage_sub_compliance_holds', {})
    reg[str(project_id)] = reg.get(str(project_id), []) + [
        {'reason': reason[:200], 'at': datetime.utcnow().isoformat() + 'Z'},
    ]
    reg[str(project_id)] = reg[str(project_id)][-10:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sub_compliance_hold', details={'project_id': project_id})
    return {'project_id': project_id, 'holds': reg[str(project_id)]}


# --- Wave 55: PCO / change orders ---

def pco_bidirectional_audit(db, models, ledger_id: int, limit: int = 50) -> dict:
    from accounting_waves_30 import pco_promotion_audit_trail

    trail = pco_promotion_audit_trail(db, models, ledger_id, limit=limit)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    resolutions = settings.get('sage_pco_resolutions') or []
    return {'trail': trail, 'resolutions': resolutions[-20:]}


def record_pco_sage_resolution(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    entry = {
        'pco_id': body.get('pco_id'),
        'winner': body.get('winner', 'casepm'),
        'sage_key': (body.get('sage_key') or '')[:80],
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    res = settings.get('sage_pco_resolutions') or []
    res.append(entry)
    settings['sage_pco_resolutions'] = res[-100:]
    _save_ledger_settings(ledger, settings)
    sage_queue_construction_mirror_event(db, models, ledger_id, 'PCOResolved', entry, user_id=user_id)
    return entry


# --- Wave 56: PJ job cost ---

def pj_mirror_queue_status(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_construction_mirror_queue') or []
    pj_events = [e for e in q if (e.get('type') or '') in (
        'BudgetSageSync', 'ChangeOrderApproved', 'TimesheetPosted', 'DirectCostPosted', 'ManualSync',
    )]
    return {'queue_size': len(q), 'pj_related': len(pj_events), 'sample': pj_events[-10:]}


def portfolio_job_variance_v2(db, models, ledger_id: int, Project=None, limit: int = 20) -> dict:
    from accounting_waves_22 import contractual_wip_analysis

    if not Project:
        return {'projects': []}
    rows = []
    for p in Project.query.filter_by(status='Active').limit(limit).all():
        try:
            wip = contractual_wip_analysis(db, models, ledger_id, p.id, Project=Project)
            rows.append({'project_id': p.id, 'name': getattr(p, 'name', ''), 'wip': wip})
        except Exception as exc:
            rows.append({'project_id': p.id, 'error': str(exc)[:80]})
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_portfolio_variance_v2'] = {'at': datetime.utcnow().isoformat() + 'Z', 'count': len(rows)}
    _save_ledger_settings(ledger, settings)
    return {
        'projects': rows,
        'warning_count': sum(
            1 for r in rows
            if (r.get('wip') or {}).get('status') in ('overbilled', 'underbilled')
        ),
    }


def validate_g702_lifecycle_fixture() -> dict:
    data = load_fixture_row('g702_lifecycle_sample.json')
    rows = data.get('value') or []
    if not rows:
        return {'ok': False}
    row = rows[0]
    p = row.get('payload') or {}
    ok = row.get('type') == 'G702Approved' and p.get('period_number') is not None
    return {'ok': ok, 'type': row.get('type')}


def cron_waves_53_56_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_30 import cron_cre_bridge_maintenance

    cre = cron_cre_bridge_maintenance(db, models, secret, Project=Project)
    portfolio = []
    AcctLedger = models['AcctLedger']
    for ledger in AcctLedger.query.limit(5).all():
        entry = {'ledger_id': ledger.id, 'pj_queue': pj_mirror_queue_status(db, models, ledger.id)}
        if Project:
            entry['variance'] = portfolio_job_variance_v2(db, models, ledger.id, Project=Project)
        portfolio.append(entry)
    return {'cre_cron': cre, 'portfolio': portfolio}
