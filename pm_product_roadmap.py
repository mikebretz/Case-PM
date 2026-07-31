"""
PM product pillars — roadmap status (scheduling, BIM, estimating, portal, offline).
"""
from __future__ import annotations

from datetime import datetime

PILLARS = [
    {
        'id': 'scheduling',
        'title': 'Scheduling & resource leveling',
        'status': 'live',
        'summary': 'Calendar-aware leveling v2, resource pools API, cross-project portfolio hotspots.',
        'hooks': [
            '/api/schedule',
            '/api/pm/scheduling/resource-summary',
            '/api/pm/scheduling/leveling',
            '/api/pm/scheduling/cross-project-leveling',
            '/api/pm/scheduling/resource-pools',
        ],
    },
    {
        'id': 'bim',
        'title': 'BIM coordination',
        'status': 'live',
        'summary': 'BIM viewer (GLB/GLTF/PDF), Operations assets, viewpoint registry, 4D links in Operations Center.',
        'hooks': ['/bim-viewer', '/api/pm/bim/status', '/api/operations/bim/assets'],
    },
    {
        'id': 'estimating_budget',
        'title': 'Estimating → budget automation',
        'status': 'live',
        'summary': 'Auto-pipeline, CSV revision import, SOV alignment check + budget→SOV remediate.',
        'hooks': [
            '/api/accounting/estimating/<id>/auto-pipeline',
            '/api/estimates/<id>/import-revision',
            '/api/accounting/estimating/sov-alignment',
            '/api/accounting/estimating/sov-alignment/remediate',
        ],
    },
    {
        'id': 'portal',
        'title': 'Owner / subcontractor portal depth',
        'status': 'live',
        'summary': 'Compliance library with COI expiry alerts, company waiver library, AP preflight, owner G702 draw packages.',
        'hooks': [
            '/sub-compliance',
            '/api/portal/compliance-library',
            '/api/portal/waiver-library',
            '/api/accounting/ap/compliance-preflight',
            '/api/accounting/construction/owner-draw-package',
        ],
    },
    {
        'id': 'mobile_offline',
        'title': 'Mobile field offline',
        'status': 'live',
        'summary': 'IndexedDB outbox with idempotent server process for daily log, timesheet, and photo metadata.',
        'hooks': ['/api/mobile/offline/schema', 'static/js/mobile-offline-outbox.js'],
    },
    {
        'id': 'marketing',
        'title': 'Construction marketing',
        'status': 'live',
        'summary': 'Lead pipeline, case studies from projects, DAM, campaigns, reviews, public lead capture.',
        'hooks': ['/marketing', '/api/marketing/catalog', '/api/public/marketing/leads'],
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
        'wave_49_gap_closure': True,
        'finalize_ops': '/api/accounting/platform/finalize-ops',
    }
