"""
PM product pillars — roadmap status (scheduling, BIM, estimating, portal, offline).
"""
from __future__ import annotations

from datetime import datetime

PILLARS = [
    {
        'id': 'scheduling',
        'title': 'Scheduling & resource leveling',
        'status': 'partial',
        'summary': 'Schedule sync plus GET /api/pm/scheduling/resource-summary for crew/task buckets.',
        'hooks': ['/api/schedule', '/api/pm/scheduling/resource-summary'],
    },
    {
        'id': 'bim',
        'title': 'BIM coordination',
        'status': 'foundation',
        'summary': 'Viewpoint registry API; IFC viewer planned.',
        'hooks': ['/api/pm/bim/status', '/api/pm/bim/viewpoints'],
    },
    {
        'id': 'estimating_budget',
        'title': 'Estimating → budget automation',
        'status': 'partial',
        'summary': 'POST /api/accounting/estimating/<id>/auto-pipeline rolls estimate to budget and accounting publish.',
        'hooks': ['/api/accounting/estimating/<id>/auto-pipeline', '/api/budget/publish'],
    },
    {
        'id': 'portal',
        'title': 'Owner / sub portal depth',
        'status': 'partial',
        'summary': 'GET /api/portal/compliance-library lists COI validity for AP compliance.',
        'hooks': ['/api/portal/compliance-library', '/api/pay-apps'],
    },
    {
        'id': 'mobile_offline',
        'title': 'Mobile field offline',
        'status': 'foundation',
        'summary': 'Offline queue schema, sync batch, and process endpoints on ledger settings.',
        'hooks': ['/api/mobile/offline/schema', '/api/mobile/offline/sync', '/api/mobile/offline/process'],
    },
]


def pm_roadmap_status() -> dict:
    return {
        'at': datetime.utcnow().isoformat() + 'Z',
        'pillars': PILLARS,
        'doc': 'docs/PM_PRODUCT_ROADMAP.md',
        'accounting_integration': {
            'pending_dashboard': '/api/accounting/construction/pending-dashboard',
            'sync_all': '/api/accounting/construction/sync-all-pending',
            'sage_go_live_alerts': '/api/accounting/sage/go-live-alerts',
            'field_silent_auto_post': 'program_settings.field_auto_post_silent',
        },
    }
