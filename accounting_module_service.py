"""Case PM Accounting module — Sage 300 dashboard, ERP queue, and catalog services."""
from __future__ import annotations

import json
import os
from collections import Counter

from sage300_catalog import catalog_payload, casepm_linked_modules
from sage300_web_client import probe_connection, resolve_web_api_config


def _project_sage_context(Project, project_id):
    from program_settings_persistence import load_sage_defaults, merge_sage_context

    project = Project.query.get(project_id)
    if not project:
        return None
    details = {}
    if getattr(project, 'details_json', None):
        try:
            details = json.loads(project.details_json)
        except (TypeError, json.JSONDecodeError):
            details = {}
    sage = merge_sage_context(details, load_sage_defaults())
    return {
        'project_id': project_id,
        'project_name': project.name or '',
        'project_number': project.number or '',
        'sage_job_number': (
            (project.sage_job_number or project.accounting_project_number or '').strip()
        ),
        'sage_company_code': sage.get('sage_company_code', ''),
        'sage_sync_enabled': sage.get('sage_sync_enabled', '1') != '0',
        'sage_accounting_method': sage.get('sage_accounting_method', ''),
        'details': {
            'sage_contract_number': details.get('sage_contract_number', ''),
            'sage_ar_customer_code': details.get('sage_ar_customer_code', '') or sage.get('sage_ar_customer_code', ''),
        },
    }


def connection_status():
    web = resolve_web_api_config()
    bridge_url = os.environ.get('SAGE_API_URL', '').strip()
    bridge_key = bool(os.environ.get('SAGE_API_KEY', '').strip())
    mode = 'offline'
    if bridge_url:
        mode = 'cre_bridge'
    if web.get('configured') and web.get('user') and web.get('password'):
        mode = 'cre_bridge_and_web_api' if bridge_url else 'web_api'
    elif web.get('configured'):
        mode = 'web_api_partial' if bridge_url else 'web_api_partial'
    return {
        'mode': mode,
        'cre_bridge': {'url': bridge_url, 'has_api_key': bridge_key},
        'web_api': web,
        'probe': probe_connection(),
    }


def erp_queue_summary(SageSyncEvent, project_id: int) -> dict:
    events = (
        SageSyncEvent.query.filter_by(project_id=project_id)
        .order_by(SageSyncEvent.created_at.desc())
        .limit(500)
        .all()
    )
    status_counts = Counter()
    accounting_counts = Counter()
    pending_review = []
    for ev in events:
        status_counts[ev.status or 'unknown'] += 1
        acct = getattr(ev, 'accounting_status', None) or 'accepted'
        accounting_counts[acct] += 1
        if acct == 'pending_review' and len(pending_review) < 100:
            pending_review.append(ev)
    return {
        'total': len(events),
        'status_counts': dict(status_counts),
        'accounting_counts': dict(accounting_counts),
        'pending_review_count': accounting_counts.get('pending_review', 0),
    }


def serialize_erp_events(events, sage_event_to_dict):
    return [sage_event_to_dict(e) for e in events]


def build_dashboard(Project, SageSyncEvent, project_id: int) -> dict:
    from sage_service import latest_sage_events_by_project, project_sage_sync_status, sage_event_to_dict

    ctx = _project_sage_context(Project, project_id)
    if not ctx:
        return {'ok': False, 'error': 'project not found'}
    latest_map = latest_sage_events_by_project(SageSyncEvent, [project_id])
    latest = latest_map.get(project_id)
    project = Project.query.get(project_id)
    sync_status = project_sage_sync_status(project, latest)
    queue = erp_queue_summary(SageSyncEvent, project_id)
    linked = casepm_linked_modules()
    return {
        'ok': True,
        'project': ctx,
        'sage_sync_status': sync_status,
        'erp_queue': queue,
        'connection': connection_status(),
        'linked_sage_modules': [
            {'id': m['id'], 'name': m['name'], 'integration': m.get('integration'), 'events': (m.get('casepm') or {}).get('events', [])}
            for m in linked
        ],
        'recent_events': [
            sage_event_to_dict(e)
            for e in SageSyncEvent.query.filter_by(project_id=project_id)
            .order_by(SageSyncEvent.created_at.desc())
            .limit(15)
            .all()
        ],
    }


def get_catalog():
    return catalog_payload()
