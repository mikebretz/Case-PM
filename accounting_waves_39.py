"""
Waves 62 (completion), 70–77 — intercompany, optional fields, BI, attachments, approvals, FX, segments.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_write_guard


# --- Wave 62 completion: 941 / 1099 / amendment transmit loop ---

def filing_941_1099_amendment_bundle(db, models, ledger_id: int, tax_year: int, user_id=None) -> dict:
    from accounting_parity_wave2 import export_1099_fire
    from accounting_waves_19 import efile_transmit, efile_transmit_log
    from accounting_waves_37 import filing_bundle_with_transmit_v2

    bundle = filing_bundle_with_transmit_v2(db, models, ledger_id, tax_year, user_id=user_id)
    try:
        fire = export_1099_fire(db, models, ledger_id, tax_year)
    except TypeError:
        fire = export_1099_fire(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    amendments = settings.get('compliance_filing_amendments') or []
    for form in ('941', '1099'):
        entry = efile_transmit(
            db, models, ledger_id,
            {'form': form, 'tax_year': tax_year, 'amendment': False, 'bundle': 'wave_62_complete'},
            user_id=user_id,
        )
        amendments.append(entry)
    settings['compliance_filing_amendments'] = amendments[-40:]
    settings['last_filing_bundle'] = {'tax_year': tax_year, 'at': datetime.utcnow().isoformat() + 'Z'}
    _save_ledger_settings(ledger, settings)
    log = efile_transmit_log(db, models, ledger_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='filing_941_1099_bundle', details={'tax_year': tax_year})
    return {'bundle': bundle, 'export_1099_preview': str(fire)[:400], 'transmit_log': log, 'forms_sent': ['941', '1099']}


def efile_amendment_retransmit_loop(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_waves_19 import efile_retry, efile_transmit

    form = (body.get('form') or '1099').upper()
    tax_year = int(body.get('tax_year') or date.today().year - 1)
    prior_id = body.get('prior_entry_id')
    if prior_id:
        retry = efile_retry(db, models, ledger_id, str(prior_id), user_id=user_id)
        return {'amendment': True, 'retry': retry}
    out = efile_transmit(
        db, models, ledger_id,
        {'form': form, 'tax_year': tax_year, 'amendment': True, 'reason': (body.get('reason') or 'Correction')[:120]},
        user_id=user_id,
    )
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    loop = settings.get('compliance_amendment_loop') or []
    loop.append({'form': form, 'tax_year': tax_year, 'entry': out, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['compliance_amendment_loop'] = loop[-30:]
    _save_ledger_settings(ledger, settings)
    return {'amendment': True, 'transmit': out}


# --- Wave 70 ---

def intercompany_settlement_round_trip(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_26 import sage_consolidation_round_trip
    from accounting_waves_30 import intercompany_routing_map

    routes = intercompany_routing_map(db, models, ledger_id)
    consol = sage_consolidation_round_trip(db, models, ledger_id, user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settlements = settings.get('sage_ic_settlements') or []
    settlements.append({
        'at': datetime.utcnow().isoformat() + 'Z',
        'route_count': len(routes.get('routes') or []),
        'consolidation': consol.get('export', consol),
    })
    settings['sage_ic_settlements'] = settlements[-25:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='ic_settlement_round_trip', details={'routes': len(routes.get('routes') or [])})
    return {'routes': routes, 'consolidation': consol}


# --- Wave 71 ---

def sage_optional_fields_sync(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_30 import apply_optional_fields_to_entity_meta, list_optional_field_profiles
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ap', 'pull')
    profiles = list_optional_field_profiles(db, models, ledger_id)
    resp = get_resource('AP', 'APVendors', top=15)
    synced = 0
    registry = settings.setdefault('sage_optional_field_registry', {})
    for row in (resp.get('data') or {}).get('value') or [] if resp.get('ok') else []:
        code = (row.get('VendorNumber') or row.get('VendorCode') or '')[:20]
        if not code:
            continue
        meta = apply_optional_fields_to_entity_meta(settings, 'vendor', {}, sage_row=row)
        registry[f'vendor:{code}'] = meta
        synced += 1
    settings['sage_optional_field_registry'] = registry
    settings['sage_optional_fields_last_sync'] = datetime.utcnow().isoformat() + 'Z'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_optional_fields_sync', details={'synced': synced})
    return {'profiles': profiles, 'synced_vendors': synced}


# --- Wave 72 ---

def report_pack_sage_export_bundle(db, models, ledger_id: int, pack_id: str = 'month_end_core', user_id=None) -> dict:
    from accounting_waves_30 import list_sage_report_packs, schedule_report_pack
    from accounting_waves_24 import sage_push_posted_gl_batches

    packs = list_sage_report_packs()
    scheduled = schedule_report_pack(db, models, ledger_id, pack_id, user_id=user_id)
    gl = sage_push_posted_gl_batches(db, models, ledger_id, user_id=user_id, limit=5)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    bundle = {
        'pack_id': pack_id,
        'scheduled': scheduled,
        'gl_push': {'processed': gl.get('processed')},
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['sage_report_export_bundle'] = bundle
    _save_ledger_settings(ledger, settings)
    return {'packs_available': packs, **bundle}


# --- Wave 73 ---

def accounting_bi_kpi_snapshot(db, models, ledger_id: int) -> dict:
    from accounting_waves_28 import sage_sync_health_score
    from accounting_waves_35 import subledger_gl_tieout_report

    health = sage_sync_health_score(db, models, ledger_id)
    tieout = subledger_gl_tieout_report(db, models, ledger_id)
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    open_ap = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    open_ar = AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    snapshot = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'sync_health': health,
        'open_ap': open_ap,
        'open_ar': open_ar,
        'tieout_delta_ap': tieout.get('open_ap_subledger'),
        'tieout_delta_ar': tieout.get('open_ar_subledger'),
    }
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['accounting_bi_kpi'] = snapshot
    _save_ledger_settings(ledger, settings)
    return snapshot


# --- Wave 74 ---

def document_attachment_mirror_manifest(db, models, ledger_id: int, entity_type: str, entity_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    manifest = {
        'entity_type': entity_type[:20],
        'entity_id': int(entity_id),
        'attachments': [],
        'sage_mirror': False,
    }
    if entity_type == 'ap':
        doc = models['AcctAPDocument'].query.filter_by(id=int(entity_id), ledger_id=ledger_id).first()
        if doc and getattr(doc, 'details_json', None):
            try:
                meta = json.loads(doc.details_json)
                manifest['attachments'] = meta.get('attachments') or meta.get('files') or []
            except (TypeError, json.JSONDecodeError):
                pass
    elif entity_type == 'ar':
        doc = models['AcctARDocument'].query.filter_by(id=int(entity_id), ledger_id=ledger_id).first()
        if doc and getattr(doc, 'details_json', None):
            try:
                meta = json.loads(doc.details_json)
                manifest['attachments'] = meta.get('attachments') or []
            except (TypeError, json.JSONDecodeError):
                pass
    reg = settings.setdefault('sage_attachment_manifest', {})
    reg[f'{entity_type}:{entity_id}'] = manifest
    settings['sage_attachment_manifest'] = reg
    _save_ledger_settings(ledger, settings)
    return manifest


# --- Wave 75 ---

def approval_rules_inbox(db, models, ledger_id: int) -> dict:
    from accounting_waves_21 import payment_exception_inbox

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    rules = settings.get('accounting_approval_rules') or [
        {'id': 'ap_over_limit', 'threshold': 25000, 'module': 'ap'},
        {'id': 'je_manual', 'threshold': 0, 'module': 'gl'},
    ]
    pending = []
    AcctAPDocument = models['AcctAPDocument']
    for doc in AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').limit(50).all():
        amt = float(doc.amount or 0)
        if amt >= float(rules[0].get('threshold') or 25000):
            pending.append({'type': 'ap', 'document_id': doc.id, 'amount': amt, 'rule': 'ap_over_limit'})
    payments = payment_exception_inbox(db, models, ledger_id)
    return {'rules': rules, 'pending_approvals': pending[:30], 'payment_exceptions': payments.get('exceptions') or []}


def record_approval_decision(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('approval_decisions') or []
    entry = {
        'item_type': (body.get('item_type') or 'ap')[:20],
        'item_id': body.get('item_id'),
        'decision': (body.get('decision') or 'approved')[:20],
        'by': user_id,
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    log.append(entry)
    settings['approval_decisions'] = log[-100:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='approval_decision', details=entry)
    return entry


# --- Wave 76 ---

def project_fx_revaluation_report(db, models, ledger_id: int, project_id: int | None = None) -> dict:
    from accounting_waves_35 import sage_fx_revaluation_round_trip

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    rates = settings.get('sage_fx_rates') or {'USD': 1.0}
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    rows = []
    q = AcctJournalLine.query
    if project_id is not None:
        q = q.filter_by(project_id=int(project_id))
    for ln in q.limit(200).all():
        batch = AcctJournalBatch.query.get(ln.batch_id)
        if not batch or batch.ledger_id != ledger_id or batch.status != 'Posted':
            continue
        ccy = (getattr(ln, 'currency_code', None) or settings.get('base_currency') or 'USD')[:3]
        if ccy == 'USD':
            continue
        rate = float(rates.get(ccy) or 1.0)
        base = (float(ln.debit or 0) - float(ln.credit or 0)) * rate
        rows.append({'line_id': ln.id, 'project_id': ln.project_id, 'currency': ccy, 'base_amount': round(base, 2)})
    fx = sage_fx_revaluation_round_trip(db, models, ledger_id, user_id=None)
    return {'project_id': project_id, 'revalued_lines': rows[:40], 'round_trip': fx}


# --- Wave 77 ---

def gl_segment_strict_validation(db, models, ledger_id: int) -> dict:
    from accounting_waves_27 import get_schema_profile

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    profile = get_schema_profile(settings)
    AcctGLAccount = models['AcctGLAccount']
    violations = []
    for acct in AcctGLAccount.query.filter_by(ledger_id=ledger_id).limit(300).all():
        num = (acct.account_number or '').strip()
        if not num:
            violations.append({'account_id': acct.id, 'issue': 'empty_number'})
        elif len(num) > 40:
            violations.append({'account_id': acct.id, 'issue': 'number_too_long'})
    strict = settings.get('gl_segment_strict') == '1'
    return {
        'strict_mode': strict,
        'profile_id': profile.get('id') or settings.get('sage_schema_profile_id'),
        'violation_count': len(violations),
        'violations': violations[:25],
    }


def save_gl_segment_strict_mode(db, models, ledger_id: int, enabled: bool, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['gl_segment_strict'] = '1' if enabled else '0'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='gl_segment_strict', details={'enabled': enabled})
    return gl_segment_strict_validation(db, models, ledger_id)
