"""
Waves 45–48 — bank & cash: BK Sage round-trip, reconciliation, AR cash apply, AP disbursements.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import (
    SAGE_MIRROR_CAPABILITIES,
    _ledger_settings,
    _save_ledger_settings,
    sage_write_guard,
)
from accounting_waves_27 import (
    external_key_register,
    external_key_seen,
    get_schema_profile,
    multi_invoice_cash_application,
    sage_pull_ap_payments_from_batches,
    sage_pull_bank_transactions,
    sor_guard_extended,
)
from accounting_waves_28 import load_fixture_row, get_pack_profile


# --- Wave 45: BK ↔ Sage ---

def sage_pull_bk_transactions_v2(db, models, ledger_id: int, user_id=None, limit: int = 100) -> dict:
    base = sage_pull_bank_transactions(db, models, ledger_id, user_id=user_id, limit=limit)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_bk_last_pull_at'] = datetime.utcnow().isoformat() + 'Z'
    settings['sage_bk_last_pull_count'] = base.get('imported', 0)
    _save_ledger_settings(ledger, settings)
    return {**base, 'version': 2}


def sage_push_bk_transactions_batch(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'bk', 'push')
    profile = get_schema_profile(settings)
    res = (profile.get('resources') or {}).get('bk_transactions', 'BKTransactions')
    AcctBankTransaction = models['AcctBankTransaction']
    AcctBankAccount = models['AcctBankAccount']
    pushed = errors = 0
    err_rows = []
    for bank in AcctBankAccount.query.filter_by(ledger_id=ledger_id).limit(5).all():
        for tx in AcctBankTransaction.query.filter_by(bank_account_id=bank.id, reconciled=False).order_by(
            AcctBankTransaction.id.desc(),
        ).limit(limit):
            ref = (tx.reference or f'CPM-{tx.id}')[:40]
            if external_key_seen(settings, 'bk_tx_push', ref):
                continue
            payload = {
                'Reference': ref,
                'Amount': float(tx.amount or 0),
                'Description': (tx.description or 'Case PM import')[:60],
                'TransactionDate': (tx.transaction_date or date.today()).isoformat(),
            }
            resp = post_resource('BK', res, payload)
            if resp.get('ok'):
                pushed += 1
                settings = external_key_register(settings, 'bk_tx_push', tx.id, ref)
            else:
                errors += 1
                err_rows.append({'tx_id': tx.id, **resp})
    db.session.flush()
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_bk', details={'pushed': pushed, 'errors': errors})
    return {'pushed': pushed, 'errors': errors, 'error_rows': err_rows[:8]}


def sync_bank_period_close_metadata(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctBankAccount = models['AcctBankAccount']
    banks = []
    for bank in AcctBankAccount.query.filter_by(ledger_id=ledger_id).all():
        banks.append({
            'id': bank.id,
            'name': bank.name,
            'last_reconciled': bank.last_reconciled_date.isoformat() if bank.last_reconciled_date else None,
        })
    meta = {
        'banks': banks,
        'sage_bk_last_pull': settings.get('sage_bk_last_pull_at'),
        'updated_at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['sage_bank_period_close'] = meta
    _save_ledger_settings(ledger, settings)
    return meta


# --- Wave 46: Reconciliation workspace ---

def bank_sage_reconciliation_match_scores(db, models, ledger_id: int, bank_account_id: int) -> dict:
    from accounting_waves_22 import bank_reconciliation_workspace

    ws = bank_reconciliation_workspace(db, models, ledger_id, bank_account_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.get('sage_external_keys') or {}
    scored = []
    for tx in ws.get('open_transactions') or []:
        ref = (tx.get('reference') or '').strip()
        sage_hit = bool(ref and f'sage:bk_tx:{ref[:80]}' in reg)
        amt = float(tx.get('amount') or 0)
        score = 50
        if sage_hit:
            score += 40
        if any(abs(float(s.get('amount', 0) or 0) - amt) < 0.02 for s in (ws.get('suggestions') or []) if isinstance(s, dict)):
            score += 10
        scored.append({**tx, 'sage_matched': sage_hit, 'match_score': min(100, score)})
    return {**ws, 'scored_transactions': scored, 'exception_count': sum(1 for s in scored if s['match_score'] < 60)}


def bank_reconciliation_exception_inbox(db, models, ledger_id: int) -> dict:
    AcctBankAccount = models['AcctBankAccount']
    exceptions = []
    for bank in AcctBankAccount.query.filter_by(ledger_id=ledger_id).limit(10).all():
        box = bank_sage_reconciliation_match_scores(db, models, ledger_id, bank.id)
        for row in box.get('scored_transactions') or []:
            if row.get('match_score', 100) < 60:
                exceptions.append({'bank_account_id': bank.id, **row})
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_bk_recon_exceptions'] = exceptions[-50:]
    _save_ledger_settings(ledger, settings)
    return {'count': len(exceptions), 'exceptions': exceptions[:25]}


def apply_sage_bank_auto_matches(db, models, ledger_id: int, bank_account_id: int, user_id=None) -> dict:
    from accounting_waves_22 import apply_bank_auto_matches

    scores = bank_sage_reconciliation_match_scores(db, models, ledger_id, bank_account_id)
    out = apply_bank_auto_matches(db, models, ledger_id, bank_account_id, user_id=user_id)
    return {'match_scores': scores.get('exception_count'), 'apply': out}


# --- Wave 47: AR cash application ---

def ar_unapplied_cash_summary(db, models, ledger_id: int) -> dict:
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    rows = []
    for doc in AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').limit(200).all():
        paid = float(doc.amount_paid or 0)
        amt = float(doc.amount or 0)
        if paid > amt + 0.01:
            cust = AcctCustomer.query.get(doc.customer_id) if doc.customer_id else None
            rows.append({
                'document_id': doc.id,
                'number': doc.document_number,
                'customer': cust.code if cust else None,
                'overpayment': round(paid - amt, 2),
            })
    return {'unapplied_count': len(rows), 'items': rows[:30]}


def ar_cash_application_sage_round_trip(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_waves_27 import sage_pull_ar_receipts_v2

    sor_guard_extended(_ledger_settings(models['AcctLedger'].query.get(ledger_id)), 'ar', 'casepm_write')
    pull = sage_pull_ar_receipts_v2(db, models, ledger_id, user_id=user_id)
    apply = multi_invoice_cash_application(db, models, ledger_id, body, user_id=user_id)
    return {'pull': pull, 'apply': apply}


def ar_writeoff_nsf_register(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    """Record write-off or NSF intent on AR doc metadata (Case PM ledger)."""
    AcctARDocument = models['AcctARDocument']
    doc_id = int(body.get('document_id') or 0)
    doc = AcctARDocument.query.filter_by(id=doc_id, ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('AR document not found')
    meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
    entry = {
        'type': (body.get('type') or 'writeoff')[:20],
        'amount': float(body.get('amount') or 0),
        'reason': (body.get('reason') or '')[:200],
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    meta.setdefault('ar_adjustments', []).append(entry)
    doc.details_json = json.dumps(meta)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='ar_adjustment', details=entry)
    return {'document_id': doc.id, 'adjustment': entry}


# --- Wave 48: AP disbursements ---

def sage_ap_payment_batch_ack(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    pull = sage_pull_ap_payments_from_batches(db, models, ledger_id, user_id=user_id, limit=limit)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    ack = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'updated': pull.get('updated', 0),
        'mode': pull.get('mode'),
    }
    settings['sage_ap_payment_last_ack'] = ack
    log = settings.get('sage_ap_payment_ack_log') or []
    log.append(ack)
    settings['sage_ap_payment_ack_log'] = log[-20:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_ap_payment_ack', details=ack)
    return {**pull, 'ack': ack}


def ap_void_payment_sage_mirror(db, models, ledger_id: int, payment_id: int, reason: str = '', user_id=None) -> dict:
    from accounting_ap_extended import void_ap_payment

    AcctAPPayment = models['AcctAPPayment']
    payment = AcctAPPayment.query.filter_by(id=int(payment_id), ledger_id=ledger_id).first()
    if not payment:
        raise ValueError('Payment not found')
    local = void_ap_payment(db, models, payment, reason=reason, user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_ap_void_queue') or []
    q.append({
        'payment_id': payment.id,
        'amount': float(payment.amount or 0),
        'reason': reason[:120],
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['sage_ap_void_queue'] = q[-30:]
    _save_ledger_settings(ledger, settings)
    return {'voided': True, 'local': local, 'queued_for_sage': True}


def ap_payment_distribution_codes(db, models, ledger_id: int, payment_id: int, codes: dict, user_id=None) -> dict:
    AcctAPPayment = models['AcctAPPayment']
    payment = AcctAPPayment.query.filter_by(id=int(payment_id), ledger_id=ledger_id).first()
    if not payment:
        raise ValueError('Payment not found')
    meta = {}
    if getattr(payment, 'details_json', None):
        try:
            meta = json.loads(payment.details_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
    meta['distribution'] = {
        'eft_code': (codes.get('eft_code') or '')[:20],
        'check_code': (codes.get('check_code') or '')[:20],
        'bank_code': (codes.get('bank_code') or '')[:20],
    }
    if hasattr(payment, 'details_json'):
        payment.details_json = json.dumps(meta)
    else:
        ledger = models['AcctLedger'].query.get(ledger_id)
        settings = _ledger_settings(ledger)
        pmap = settings.setdefault('ap_payment_distribution', {})
        pmap[str(payment.id)] = meta['distribution']
        _save_ledger_settings(ledger, settings)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='ap_payment_distribution', details=meta['distribution'])
    return {'payment_id': payment.id, 'distribution': meta['distribution']}


def validate_bk_fixture() -> dict:
    data = load_fixture_row('bk_transaction_sample.json')
    rows = data.get('value') or []
    if not rows:
        return {'ok': False, 'error': 'empty fixture'}
    row = rows[0]
    ok = bool(row.get('Reference') and (row.get('Amount') is not None or row.get('TransactionAmount') is not None))
    return {'ok': ok, 'reference': row.get('Reference')}


def validate_cre_fixture_reexport() -> dict:
    from accounting_waves_30 import validate_cre_fixture
    return validate_cre_fixture()


def update_mirror_capabilities_wave_45_48() -> None:
    SAGE_MIRROR_CAPABILITIES['bk'] = {
        **SAGE_MIRROR_CAPABILITIES.get('bk', {}),
        'pull': True,
        'push': True,
        'notes': 'BK pull v2; push unreconciled txs; period close metadata',
    }


update_mirror_capabilities_wave_45_48()


def sage_mirror_deploy_check_v7() -> dict:
    from accounting_waves_30 import sage_mirror_deploy_check_v6

    base = sage_mirror_deploy_check_v6()
    profile = get_pack_profile()
    profile = {**profile, 'fields': {**(profile.get('fields') or {}), 'receipt_number': ['Reference', 'BatchNumber']}}
    bk = validate_bk_fixture()
    cre = validate_cre_fixture_reexport()
    ok = base.get('ok') and bk.get('ok') and cre.get('ok')
    return {'ok': ok, 'v6': base, 'bk_fixture': bk}


def cron_waves_45_48_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_30 import cron_waves_41_44_maintenance

    platform = cron_waves_41_44_maintenance(db, models, secret, Project=Project)
    AcctLedger = models['AcctLedger']
    bk_runs = []
    ap_acks = []
    for ledger in AcctLedger.query.limit(5).all():
        bk_runs.append(sage_pull_bk_transactions_v2(db, models, ledger.id))
        sync_bank_period_close_metadata(db, models, ledger.id)
        bank_reconciliation_exception_inbox(db, models, ledger.id)
        ap_acks.append(sage_ap_payment_batch_ack(db, models, ledger.id))
        settings = _ledger_settings(ledger)
        settings['sage_bank_cash_cron_last'] = datetime.utcnow().isoformat() + 'Z'
        _save_ledger_settings(ledger, settings)
    return {
        'platform': platform,
        'bk_pulls': bk_runs,
        'ap_acks': ap_acks,
        'deploy_v7': sage_mirror_deploy_check_v7(),
    }
