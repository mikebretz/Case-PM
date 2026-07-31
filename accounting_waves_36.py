"""
Waves 54–60 — CRE & distribution depth (extends waves 32–33).
"""
from __future__ import annotations

import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings
from accounting_waves_25 import sage_queue_construction_mirror_event


def sync_all_sub_pay_apps_for_project(db, models, ledger_id: int, project_id: int, PayAppProjectState=None, user_id=None) -> dict:
    from accounting_waves_21 import sync_all_sub_pay_apps_pending_to_ap

    if not PayAppProjectState:
        return {'synced': 0, 'error': 'PayAppProjectState unavailable'}
    return sync_all_sub_pay_apps_pending_to_ap(db, models, ledger_id, project_id, user_id=user_id, PayAppProjectState=PayAppProjectState)


def release_sub_compliance_hold(db, models, ledger_id: int, project_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.get('sage_sub_compliance_holds') or {}
    reg.pop(str(project_id), None)
    settings['sage_sub_compliance_holds'] = reg
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sub_compliance_release', details={'project_id': project_id})
    return {'released': True, 'project_id': project_id}


def pco_auto_resolve_from_queue(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_32 import pco_bidirectional_audit

    audit = pco_bidirectional_audit(db, models, ledger_id)
    resolved = 0
    for ev in (audit.get('trail') or {}).get('events') or []:
        if (ev.get('type') or '') == 'PCOPromoted':
            sage_queue_construction_mirror_event(db, models, ledger_id, 'PCOReplay', ev.get('payload') or {}, user_id=user_id)
            resolved += 1
    return {'replayed': resolved}


def pj_mirror_queue_push_batch(db, models, ledger_id: int, user_id=None, limit: int = 10) -> dict:
    from accounting_waves_27 import flush_construction_mirror_queue

    return flush_construction_mirror_queue(db, models, ledger_id, user_id=user_id, limit=limit)


def po_blanket_standing_flags(db, models, ledger_id: int) -> dict:
    from accounting_waves_33 import po_standing_blanket_summary

    return po_standing_blanket_summary(db, models, ledger_id)


def ic_transaction_ack_summary(db, models, ledger_id: int) -> dict:
    from accounting_waves_25 import sage_push_ic_transactions

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    push = sage_push_ic_transactions(db, models, ledger_id)
    return {'push': push, 'errors': (settings.get('sage_distribution_errors') or [])[-5:]}


def oe_invoice_chain_advance(db, models, ledger_id: int, order_number: str, user_id=None) -> dict:
    AcctSalesOrder = models.get('AcctSalesOrder')
    if not AcctSalesOrder:
        return {'updated': False}
    import json

    so = AcctSalesOrder.query.filter_by(ledger_id=ledger_id, order_number=order_number[:40]).first()
    if not so:
        raise ValueError('Order not found')
    meta = json.loads(so.details_json or '{}') if getattr(so, 'details_json', None) else {}
    meta['shipped'] = True
    meta['invoiced'] = True
    if hasattr(so, 'details_json'):
        so.details_json = json.dumps(meta)
    so.status = 'Invoiced'
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='oe_chain_advance', details={'order': order_number})
    return {'order_number': order_number, 'status': so.status}


def three_way_auto_hold_exceptions(db, models, ledger_id: int, limit: int = 20) -> dict:
    from accounting_waves_33 import three_way_vendor_tolerance_report

    report = three_way_vendor_tolerance_report(db, models, ledger_id, limit=limit)
    AcctAPDocument = models['AcctAPDocument']
    held = 0
    for ex in report.get('exceptions') or []:
        doc = AcctAPDocument.query.get(ex.get('invoice_id'))
        if doc and doc.status == 'Open':
            doc.status = 'On Hold'
            held += 1
    db.session.flush()
    return {**report, 'auto_held': held}


def cron_waves_54_60_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None, Commitment=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_33 import cron_waves_57_60_maintenance

    base = cron_waves_57_60_maintenance(db, models, secret, Commitment=Commitment)
    extras = []
    if Project:
        for p in Project.query.filter_by(status='Active').limit(10).all():
            if PayAppProjectState:
                extras.append(sync_all_sub_pay_apps_for_project(db, models, 1, p.id, PayAppProjectState))
    AcctLedger = models['AcctLedger']
    for ledger in AcctLedger.query.limit(3).all():
        extras.append(pco_auto_resolve_from_queue(db, models, ledger.id))
        extras.append(three_way_auto_hold_exceptions(db, models, ledger.id))
    return {'distribution_base': base, 'extras': extras}
