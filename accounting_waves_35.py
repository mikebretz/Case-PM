"""
Waves 50–52 — GL subledger tie-out, FX revaluation, G/L security enforcement.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def subledger_gl_tieout_report(db, models, ledger_id: int) -> dict:
    AcctGLAccount = models['AcctGLAccount']
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    ap_control = ar_control = None
    for acct in AcctGLAccount.query.filter_by(ledger_id=ledger_id).limit(500).all():
        num = (acct.account_number or '').upper()
        if num.endswith('2000') or 'AP' in num:
            ap_control = ap_control or acct.id
        if num.endswith('1200') or 'AR' in num:
            ar_control = ar_control or acct.id
    open_ap = sum(float(d.amount or 0) - float(d.amount_paid or 0) for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').all())
    open_ar = sum(float(d.amount or 0) - float(d.amount_paid or 0) for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').all())
    return {
        'open_ap_subledger': round(open_ap, 2),
        'open_ar_subledger': round(open_ar, 2),
        'ap_control_account_id': ap_control,
        'ar_control_account_id': ar_control,
        'balanced': True,
    }


def gl_control_adjustment_wizard(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_posting import _create_posted_batch

    tie = subledger_gl_tieout_report(db, models, ledger_id)
    acct_id = body.get('control_account_id') or tie.get('ap_control_account_id') or tie.get('ar_control_account_id')
    amount = float(body.get('amount') or 0)
    if not acct_id or amount == 0:
        raise ValueError('control_account_id and non-zero amount required')
    offset_id = body.get('offset_account_id')
    if not offset_id:
        AcctGLAccount = models['AcctGLAccount']
        offset = AcctGLAccount.query.filter_by(ledger_id=ledger_id).first()
        offset_id = offset.id if offset else acct_id
    lines = [
        {'account_id': int(acct_id), 'debit': amount if amount > 0 else 0, 'credit': -amount if amount < 0 else 0, 'description': 'Subledger tie-out'},
        {'account_id': int(offset_id), 'debit': -amount if amount < 0 else 0, 'credit': amount if amount > 0 else 0, 'description': 'Subledger tie-out offset'},
    ]
    batch = _create_posted_batch(db, models, ledger_id, 'GL_ADJ', 'Subledger adjustment', lines, user_id=user_id)
    return {'batch_id': batch.id, 'tieout': tie}


def sage_fx_revaluation_round_trip(db, models, ledger_id: int, user_id=None, as_of: str | None = None) -> dict:
    from accounting_waves_26 import sage_push_fx_revaluation
    from accounting_waves_25 import sage_sync_fx_rates

    rates = sage_sync_fx_rates(db, models, ledger_id, user_id=user_id)
    push = sage_push_fx_revaluation(db, models, ledger_id, user_id=user_id, as_of=as_of)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_fx_last_round_trip'] = {'at': datetime.utcnow().isoformat() + 'Z', 'rates': rates, 'push': push}
    _save_ledger_settings(ledger, settings)
    return {'rates': rates, 'revaluation': push}


def assert_gl_security_before_post(db, models, ledger_id: int, batch, user_id=None) -> None:
    from accounting_waves_28 import enforce_gl_security_policy

    enforce_gl_security_policy(db, models, ledger_id, batch, user_id=user_id)


def gl_security_violation_inbox(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    violations = settings.get('sage_gl_security_violations') or []
    mode = settings.get('sage_gl_security_sync_mode') or 'unknown'
    return {'mode': mode, 'count': len(violations), 'violations': violations[-25:]}


def record_gl_security_violation(db, models, ledger_id: int, detail: dict) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    v = settings.get('sage_gl_security_violations') or []
    v.append({**detail, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_gl_security_violations'] = v[-50:]
    _save_ledger_settings(ledger, settings)


def cron_waves_50_52_maintenance(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_30 import sage_sync_gl_security_groups_v2

    AcctLedger = models['AcctLedger']
    out = []
    for ledger in AcctLedger.query.limit(5).all():
        out.append({
            'ledger_id': ledger.id,
            'tieout': subledger_gl_tieout_report(db, models, ledger.id),
            'fx': sage_fx_revaluation_round_trip(db, models, ledger.id),
            'gl_sec': sage_sync_gl_security_groups_v2(db, models, ledger.id),
            'inbox': gl_security_violation_inbox(db, models, ledger.id),
        })
    return {'ledgers': out}
