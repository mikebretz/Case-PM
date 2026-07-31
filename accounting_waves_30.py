"""
Waves 41–44 — CRE bridge depth, GL/consolidation, optional fields & report packs, ops & deploy v6.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_sync_get
from accounting_waves_27 import flush_construction_mirror_queue
from accounting_waves_28 import load_fixture_row, sage_sync_health_score


# --- Wave 41: CRE bridge ---

def construction_mirror_queue_inspect(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_construction_mirror_queue') or []
    stuck_days = int(os.environ.get('CASEPM_CRE_QUEUE_STUCK_DAYS') or '7')
    cutoff = datetime.utcnow() - timedelta(days=stuck_days)
    stuck = []
    for i, entry in enumerate(q):
        at = (entry.get('at') or '')[:19]
        try:
            ts = datetime.fromisoformat(at) if at else datetime.utcnow()
        except ValueError:
            ts = datetime.utcnow()
        if ts < cutoff and not entry.get('error'):
            stuck.append({'index': i, **entry})
    return {'queue_size': len(q), 'items': q[-25:], 'stuck_count': len(stuck), 'stuck': stuck[:15]}


def construction_mirror_queue_discard(db, models, ledger_id: int, index: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = list(settings.get('sage_construction_mirror_queue') or [])
    if index < 0 or index >= len(q):
        raise ValueError('Invalid queue index')
    removed = q.pop(index)
    settings['sage_construction_mirror_queue'] = q
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='cre_queue_discard', details={'index': index, 'type': removed.get('type')})
    return {'discarded': True, 'type': removed.get('type'), 'queue_size': len(q)}


def construction_mirror_queue_retry(db, models, ledger_id: int, index: int, user_id=None) -> dict:
    """Retry one queue entry via standard flush (re-orders entry to front)."""
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = list(settings.get('sage_construction_mirror_queue') or [])
    if index < 0 or index >= len(q):
        raise ValueError('Invalid queue index')
    entry = q.pop(index)
    entry.pop('error', None)
    q.insert(0, entry)
    settings['sage_construction_mirror_queue'] = q
    _save_ledger_settings(ledger, settings)
    out = flush_construction_mirror_queue(db, models, ledger_id, user_id=user_id, limit=1)
    return {'retried': True, 'entry_type': entry.get('type'), 'flush': out}


def g702_ar_external_key_report(db, models, ledger_id: int, project_id: int, PayAppProjectState=None) -> dict:
    from accounting_waves_19 import g702_pending_ar_sync

    if not PayAppProjectState:
        return {'project_id': project_id, 'error': 'PayAppProjectState model unavailable'}
    sync = g702_pending_ar_sync(db, models, ledger_id, project_id, PayAppProjectState)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    mismatches = []
    AcctARDocument = models['AcctARDocument']
    for row in sync.get('posted') or []:
        doc_id = row.get('ar_document_id')
        if not doc_id:
            continue
        doc = AcctARDocument.query.get(doc_id)
        if not doc:
            mismatches.append({'period': row.get('period'), 'issue': 'missing_ar_document'})
            continue
        ext = sage_sync_get(doc, 'external_key') or ''
        idem = row.get('idempotency_key') or ''
        if idem and ext and idem not in ext and ext not in idem:
            mismatches.append({'period': row.get('period'), 'ar_document_id': doc_id, 'external_key': ext, 'idempotency_key': idem})
    return {**sync, 'mismatch_count': len(mismatches), 'mismatches': mismatches}


def pco_promotion_audit_trail(db, models, ledger_id: int, limit: int = 40) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_construction_mirror_queue') or []
    events = [e for e in q if (e.get('type') or '') in (
        'PCOPromoted', 'ChangeOrderApproved', 'CORApproved', 'CPCOPromoted',
    )]
    audit = settings.get('sage_pco_audit') or []
    combined = (events + audit)[-limit:]
    return {'count': len(combined), 'events': combined}


def cron_cre_bridge_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    results = []
    for ledger in AcctLedger.query.limit(10).all():
        inspect = construction_mirror_queue_inspect(db, models, ledger.id)
        flush = {'skipped': True}
        if inspect.get('stuck_count', 0) > 0 or inspect.get('queue_size', 0) > 0:
            flush = flush_construction_mirror_queue(db, models, ledger.id, limit=10)
        settings = _ledger_settings(ledger)
        settings['sage_cre_cron_last'] = datetime.utcnow().isoformat() + 'Z'
        _save_ledger_settings(ledger, settings)
        results.append({'ledger_id': ledger.id, 'inspect': inspect, 'flush': flush})
    return {'ledgers': results}


# --- Wave 42: GL platform & consolidation ---

def sage_sync_gl_security_groups_v2(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    resp = get_resource('GL', 'GLSecurityGroups', top=50)
    mode = resp.get('mode') or 'live'
    groups = []
    if resp.get('ok'):
        mode = resp.get('mode') or 'live'
        for row in (resp.get('data') or {}).get('value') or []:
            code = (row.get('GroupCode') or row.get('SecurityGroup') or row.get('Code') or '').strip()
            if code:
                groups.append({
                    'code': code[:20],
                    'name': (row.get('Description') or row.get('Name') or code)[:80],
                    'allow_all': bool(row.get('AllowAllAccounts') or row.get('AllowAll')),
                })
    if not groups:
        from accounting_waves_26 import sage_sync_gl_security_groups
        fallback = sage_sync_gl_security_groups(db, models, ledger_id, user_id=user_id)
        groups = fallback.get('groups') or []
        mode = fallback.get('mode') or 'stub'
    settings['sage_gl_security_groups'] = groups
    settings['sage_gl_security_sync_mode'] = mode
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_gl_security_sync_v2', details={'groups': len(groups), 'mode': mode})
    return {'groups': groups, 'mode': mode}


def sage_consolidation_import_ack(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    last = settings.get('sage_last_consolidation_export') or settings.get('sage_consolidation_last') or {}
    ack = {
        'acknowledged_at': datetime.utcnow().isoformat() + 'Z',
        'export_snapshot': last,
        'status': 'imported' if last else 'no_export',
    }
    settings['sage_consolidation_ack'] = ack
    imports = settings.get('sage_consolidation_import_log') or []
    imports.append(ack)
    settings['sage_consolidation_import_log'] = imports[-20:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_consolidation_ack', details={'status': ack['status']})
    return ack


def save_intercompany_routing_map(db, models, ledger_id: int, routes: list, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    cleaned = []
    for r in (routes or [])[:30]:
        if not isinstance(r, dict):
            continue
        cleaned.append({
            'from_company': str(r.get('from_company') or '')[:20],
            'to_company': str(r.get('to_company') or '')[:20],
            'due_from_account': str(r.get('due_from_account') or '')[:40],
            'due_to_account': str(r.get('due_to_account') or '')[:40],
            'elimination_account': str(r.get('elimination_account') or '')[:40],
        })
    settings['sage_intercompany_routes'] = cleaned
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='ic_routing_map', details={'routes': len(cleaned)})
    return {'routes': cleaned}


def intercompany_routing_map(db, models, ledger_id: int) -> dict:
    from accounting_waves_27 import intercompany_ledger_routing_preview

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    preview = intercompany_ledger_routing_preview(db, models, ledger_id)
    return {
        **preview,
        'routes': settings.get('sage_intercompany_routes') or [],
    }


def fiscal_periods_unified_view(db, models, ledger_id: int) -> dict:
    from accounting_waves_24 import assert_fiscal_period_open

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    locked = (settings.get('sage_fiscal_locked_through') or '')[:10]
    calendar = settings.get('sage_fiscal_calendar') or []
    test_date = date.today()
    open_ok = True
    try:
        assert_fiscal_period_open(settings, test_date)
    except PermissionError:
        open_ok = False
    return {
        'locked_through': locked,
        'calendar_periods': calendar[:12],
        'today_postable': open_ok,
        'sage_companies': settings.get('sage_companies') or [],
    }


def sage_consolidation_round_trip_v2(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_26 import sage_consolidation_round_trip

    export = sage_consolidation_round_trip(db, models, ledger_id, user_id=user_id)
    ack = sage_consolidation_import_ack(db, models, ledger_id, user_id=user_id)
    return {'export': export, 'ack': ack}


# --- Wave 43: optional fields & report packs ---

def list_optional_field_profiles(db, models, ledger_id: int) -> dict:
    from sage300_profile_packs import list_profile_packs, get_pack

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    pack_id = settings.get('sage_schema_profile_id') or 'sage300_cre_2024'
    pack = get_pack(pack_id)
    return {
        'active_pack': pack_id,
        'packs': list_profile_packs(),
        'optional_fields': pack.get('optional_fields') or {},
    }


def apply_optional_fields_to_entity_meta(settings: dict, entity_type: str, meta: dict, sage_row: dict | None = None) -> dict:
    from sage300_profile_packs import get_pack

    pack_id = settings.get('sage_schema_profile_id') or 'sage300_cre_2024'
    pack = get_pack(pack_id)
    keys = (pack.get('optional_fields') or {}).get(entity_type) or []
    out = dict(meta or {})
    udf = out.setdefault('sage_optional', {})
    if sage_row:
        for k in keys:
            if k in sage_row:
                udf[k] = sage_row[k]
    return out


def merge_optional_fields_into_vendor_payload(settings: dict, payload: dict, vendor) -> dict:
    meta = {}
    if vendor and getattr(vendor, 'details_json', None):
        try:
            meta = json.loads(vendor.details_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
    udf = meta.get('sage_optional') or {}
    out = dict(payload)
    for k, v in list(udf.items())[:10]:
        out[k] = v
    return out


def schedule_report_pack(db, models, ledger_id: int, pack_id: str, user_id=None) -> dict:
    from accounting_parity_wave2 import schedule_report
    from sage300_profile_packs import get_report_pack

    pack = get_report_pack(pack_id)
    scheduled = []
    for spec in pack.get('reports') or []:
        try:
            scheduled.append(schedule_report(db, models, ledger_id, dict(spec), user_id=user_id))
        except Exception as exc:
            scheduled.append({'report_type': spec.get('report_type'), 'error': str(exc)[:120]})
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_report_pack_last'] = {'pack_id': pack_id, 'at': datetime.utcnow().isoformat() + 'Z', 'count': len(scheduled)}
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='report_pack_schedule', details={'pack_id': pack_id})
    return {'pack_id': pack_id, 'scheduled': scheduled}


def list_sage_report_packs() -> dict:
    from sage300_profile_packs import list_report_packs

    return {'packs': list_report_packs()}


# --- Wave 44: ops & deploy v6 ---

def sage_ops_runbook_dashboard(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    health = sage_sync_health_score(db, models, ledger_id)
    cre = construction_mirror_queue_inspect(db, models, ledger_id)
    return {
        'health': health,
        'construction_queue': cre,
        'cron_last': {
            'cre': settings.get('sage_cre_cron_last'),
            'enterprise': settings.get('sage_last_auto_retry_at'),
            'consolidation': (settings.get('sage_consolidation_ack') or {}).get('acknowledged_at'),
            'report_pack': (settings.get('sage_report_pack_last') or {}).get('at'),
        },
        'gl_security_mode': settings.get('sage_gl_security_sync_mode'),
        'consolidation_status': (settings.get('sage_consolidation_ack') or {}).get('status'),
        'intercompany_routes': len(settings.get('sage_intercompany_routes') or []),
    }


def validate_cre_fixture() -> dict:
    data = load_fixture_row('cre_mirror_event_sample.json')
    rows = data.get('value') or []
    if not rows:
        return {'ok': False, 'error': 'empty fixture'}
    row = rows[0]
    ok = bool(row.get('type') and row.get('payload'))
    return {'ok': ok, 'sample_type': row.get('type')}


def sage_mirror_deploy_check_v6() -> dict:
    from accounting_waves_29 import sage_mirror_deploy_check_v5
    from sage300_profile_packs import get_pack

    base = sage_mirror_deploy_check_v5()
    cre = validate_cre_fixture()
    pack = get_pack('sage300_cre_2024')
    opt = bool(pack.get('optional_fields'))
    reports = bool(list_sage_report_packs().get('packs'))
    ok = base.get('ok') and cre.get('ok') and opt and reports
    return {'ok': ok, 'v5': base, 'cre_fixture': cre, 'optional_fields_pack': opt, 'report_packs': reports}


def cron_waves_41_44_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_29 import cron_waves_37_40_maintenance

    parity = cron_waves_37_40_maintenance(db, models, secret, Project=Project)
    cre = cron_cre_bridge_maintenance(db, models, secret, Project=Project)
    cons = []
    sec = []
    AcctLedger = models['AcctLedger']
    for ledger in AcctLedger.query.limit(5).all():
        sec.append(sage_sync_gl_security_groups_v2(db, models, ledger.id))
        cons.append(sage_consolidation_round_trip_v2(db, models, ledger.id))
        settings = _ledger_settings(ledger)
        settings['sage_platform_cron_last'] = datetime.utcnow().isoformat() + 'Z'
        _save_ledger_settings(ledger, settings)
    paces = {'skipped': True}
    try:
        from accounting_waves_25 import sage_run_paces_deploy_check
        paces = sage_run_paces_deploy_check()
    except Exception as exc:
        paces = {'ok': False, 'error': str(exc)[:120]}
    return {
        'parity': parity,
        'cre': cre,
        'consolidation': cons,
        'gl_security': sec,
        'paces': paces,
        'deploy_v6': sage_mirror_deploy_check_v6(),
    }
