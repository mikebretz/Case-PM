"""
PM product pillars — roadmap status (scheduling, BIM, estimating, portal, offline).
"""
from __future__ import annotations

from datetime import datetime

PILLARS = [
    {
        'id': 'scheduling',
        'title': 'Scheduling & resource leveling',
        'status': 'foundation',
        'summary': 'Schedule sync exists (deliveries, permits); CPM leveling and multi-crew constraints are planned.',
        'hooks': ['/api/schedule', '/api/deliveries/push-to-schedule'],
    },
    {
        'id': 'bim',
        'title': 'BIM coordination',
        'status': 'planned',
        'summary': 'IFC/BCF ingest, clash buckets tied to RFIs and punch — not yet in production UI.',
        'hooks': ['/api/documents', '/api/rfis'],
    },
    {
        'id': 'estimating_budget',
        'title': 'Estimating → budget automation',
        'status': 'partial',
        'summary': 'Budget publish accounting wizard and commitment budget sync; full estimate takeoff roll-forward is next.',
        'hooks': ['/api/budget/publish', '/api/accounting/budget/publish-accounting'],
    },
    {
        'id': 'portal',
        'title': 'Owner / sub portal depth',
        'status': 'partial',
        'summary': 'Pay apps, commitments, DocuSign; expanded self-service COI and lien waiver uploads planned.',
        'hooks': ['/api/pay-apps', '/api/commitments'],
    },
    {
        'id': 'mobile_offline',
        'title': 'Mobile field offline',
        'status': 'planned',
        'summary': 'Daily log and photos online-first; service-worker queue for logs and timesheets in roadmap.',
        'hooks': ['/api/daily-logs', '/api/timesheets'],
    },
]


def pm_roadmap_status() -> dict:
    return {
        'at': datetime.utcnow().isoformat() + 'Z',
        'pillars': PILLARS,
        'doc': 'docs/PM_PRODUCT_ROADMAP.md',
    }
