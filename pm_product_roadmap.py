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
        'summary': 'Resource summary + leveling v1 heuristics (GET /api/pm/scheduling/leveling).',
        'hooks': ['/api/schedule', '/api/pm/scheduling/resource-summary', '/api/pm/scheduling/leveling'],
    },
    {
        'id': 'bim',
        'title': 'BIM coordination',
        'status': 'partial',
        'summary': 'BIM viewer page + Operations assets + viewpoint registry.',
        'hooks': ['/bim-viewer', '/api/pm/bim/status', '/api/operations/bim/assets'],
    },
    {
        'id': 'estimating_budget',
        'title': 'Estimating → budget automation',
        'status': 'live',
        'summary': 'Estimating UI: Roll to budget + accounting pipeline button.',
        'hooks': ['/api/accounting/estimating/<id>/auto-pipeline'],
    },
    {
        'id': 'portal',
        'title': 'Owner / subcontractor portal depth',
        'status': 'partial',
        'summary': 'Sub compliance portal uploads (COI + lien waiver) + compliance library API.',
        'hooks': ['/sub-compliance', '/api/portal/compliance-library'],
    },
    {
        'id': 'mobile_offline',
        'title': 'Mobile field offline',
        'status': 'partial',
        'summary': 'IndexedDB outbox + server queue process; service worker v5.',
        'hooks': ['/api/mobile/offline/schema', 'static/js/mobile-offline-outbox.js'],
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
            'cutover_checklist': '/api/accounting/sage/cutover-checklist',
            'parity_matrix': '/api/accounting/sage/parity-matrix',
            'construction_sync_module': 'accounting → Construction sync',
        },
    }
