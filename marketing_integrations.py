"""External marketing integrations — Houzz, Dodge, ConstructConnect, CRM, BIM, webhooks."""
from __future__ import annotations

import json
import os
from datetime import datetime

from marketing_models import MARKETING_LEAD_SOURCES
from marketing_services import capture_public_lead, upsert_lead


INTEGRATION_KEYS = (
    'houzz', 'dodge', 'constructconnect', 'hubspot', 'salesforce', 'bim_push',
)


def integration_catalog() -> dict:
    return {
        'integrations': [
            {'id': 'houzz', 'name': 'Houzz Pro', 'mode': 'inbound_webhook', 'path': '/api/public/marketing/integrations/houzz'},
            {'id': 'dodge', 'name': 'Dodge / ConstructConnect', 'mode': 'inbound_webhook', 'path': '/api/public/marketing/integrations/dodge'},
            {'id': 'constructconnect', 'name': 'ConstructConnect', 'mode': 'inbound_webhook', 'path': '/api/public/marketing/integrations/constructconnect'},
            {'id': 'hubspot', 'name': 'HubSpot CRM', 'mode': 'outbound_webhook', 'env': 'CASEPM_CRM_WEBHOOK_URL'},
            {'id': 'salesforce', 'name': 'Salesforce', 'mode': 'outbound_webhook', 'env': 'CASEPM_CRM_WEBHOOK_URL'},
            {'id': 'bim_push', 'name': 'BIM assets → DAM', 'mode': 'internal', 'path': '/api/marketing/integrations/bim-sync'},
            {'id': 'accounting', 'name': 'Won job → revenue signal', 'mode': 'internal', 'path': '/api/marketing/integrations/accounting-sync'},
        ],
        'webhook_secret_env': 'CASEPM_MARKETING_WEBHOOK_SECRET',
    }


def _verify_webhook_secret(headers) -> bool:
    secret = (os.environ.get('CASEPM_MARKETING_WEBHOOK_SECRET') or '').strip()
    if not secret:
        return True
    if headers is None:
        return False
    got = (headers.get('X-CasePM-Marketing-Key') or headers.get('x-casepm-marketing-key') or '').strip()
    return got == secret


def _normalize_inbound(body: dict, source: str) -> dict:
    return {
        'contact_name': body.get('contact_name') or body.get('name') or body.get('homeowner_name'),
        'email': body.get('email'),
        'phone': body.get('phone'),
        'title': body.get('title') or body.get('project_name') or body.get('description') or f'{source} lead',
        'notes': body.get('notes') or body.get('message') or json.dumps(body)[:2000],
        'project_type': body.get('project_type') or body.get('trade'),
        'location_city': body.get('city') or body.get('location_city'),
        'location_state': body.get('state') or body.get('location_state'),
        'estimated_value': body.get('estimated_value') or body.get('budget'),
        'source': source if source in MARKETING_LEAD_SOURCES else 'other',
        'metadata': {'integration': source, 'raw': body},
    }


def ingest_integration_lead(db, MarketingLead, body: dict, source: str) -> dict:
    if source not in MARKETING_LEAD_SOURCES and source not in ('houzz', 'dodge', 'constructconnect'):
        source = 'other'
    payload = _normalize_inbound(body, source)
    payload['source'] = source if source in MARKETING_LEAD_SOURCES else 'other'
    if source == 'houzz':
        payload['source'] = 'houzz'
    elif source in ('dodge', 'constructconnect'):
        payload['source'] = source if source in MARKETING_LEAD_SOURCES else 'dodge'
    out = capture_public_lead(db, MarketingLead, payload)
    return out


def push_lead_to_crm(lead_dict: dict) -> dict:
    url = (os.environ.get('CASEPM_CRM_WEBHOOK_URL') or '').strip()
    if not url:
        return {'ok': False, 'skipped': True, 'reason': 'CASEPM_CRM_WEBHOOK_URL not set'}
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps({'lead': lead_dict, 'source': 'case_pm_marketing'}).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=20)
        return {'ok': True}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:200]}


def sync_bim_assets_to_dam(db, models, project_id: int, *, user_id=None) -> dict:
    from marketing_pillars import register_asset

    MarketingAsset = models['MarketingAsset']
    OperationsBimAsset = models.get('OperationsBimAsset')
    if not OperationsBimAsset:
        return {'synced': 0, 'note': 'BIM module not available'}
    created = 0
    for asset in OperationsBimAsset.query.filter_by(project_id=int(project_id)).limit(50).all():
        title = getattr(asset, 'title', None) or getattr(asset, 'name', None) or f'BIM {asset.id}'
        exists = MarketingAsset.query.filter_by(project_id=int(project_id), external_url=getattr(asset, 'file_path', None)).first()
        if exists:
            continue
        register_asset(db, MarketingAsset, {
            'project_id': int(project_id),
            'title': str(title)[:300],
            'asset_type': 'bim',
            'external_url': getattr(asset, 'file_path', None) or getattr(asset, 'storage_path', None),
            'phase': 'coordination',
            'use_cases': ['portfolio', 'proposal', 'awards'],
            'tags': ['bim', '3d'],
        }, user_id=user_id)
        created += 1
    return {'synced': created}


def sync_accounting_won_signal(db, MarketingLead, Project) -> dict:
    """Align won leads with active/complete projects for ROI."""
    updated = 0
    for L in MarketingLead.query.filter_by(stage='won').all():
        if L.project_id:
            continue
        if not (L.email or L.company_name):
            continue
        q = Project.query
        if L.company_name:
            q = q.filter(Project.client.ilike(f'%{L.company_name[:40]}%'))
        proj = q.order_by(Project.updated_at.desc()).first()
        if proj:
            L.project_id = proj.id
            updated += 1
    db.session.flush()
    return {'linked': updated, 'at': datetime.utcnow().isoformat() + 'Z'}
