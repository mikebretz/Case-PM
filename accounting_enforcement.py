"""Enforce G/L security, optional fields, and posting guards across accounting."""
from __future__ import annotations

import json

from accounting_platform import check_gl_account_access


def _role_key_for_user(user):
    if not user:
        return None
    for attr in ('role', 'accounting_role', 'system_role'):
        v = getattr(user, attr, None)
        if v:
            return str(v)[:40]
    if getattr(user, 'is_admin', False):
        return 'admin'
    return 'accounting_user'


def enforce_gl_security_on_batch(models, ledger_id, batch, *, user_id=None, role_key=None):
    AcctJournalLine = models['AcctJournalLine']
    lines = AcctJournalLine.query.filter_by(batch_id=batch.id).all()
    for ln in lines:
        if not check_gl_account_access(
            models, ledger_id, ln.account_id,
            user_id=user_id, role_key=role_key, need='post',
        ):
            AcctGLAccount = models['AcctGLAccount']
            acct = AcctGLAccount.query.get(ln.account_id)
            num = acct.account_number if acct else str(ln.account_id)
            raise ValueError(f'Not authorized to post to G/L account {num}')


def merge_optional_fields(details_json, entity_type, values, models, ledger_id):
    """Validate and merge optional field values into details_json."""
    AcctOptionalFieldDef = models['AcctOptionalFieldDef']
    defs = AcctOptionalFieldDef.query.filter_by(ledger_id=ledger_id, entity_type=entity_type).all()
    def_by_key = {d.field_key: d for d in defs}
    try:
        meta = json.loads(details_json or '{}') if details_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        meta = {}
    opt = meta.get('optional_fields') or {}
    if not isinstance(opt, dict):
        opt = {}
    for key, val in (values or {}).items():
        d = def_by_key.get(key)
        if defs and key not in def_by_key:
            continue
        if d and d.is_required and (val is None or str(val).strip() == ''):
            raise ValueError(f'Required optional field: {d.label}')
        opt[key] = val
    if defs:
        for d in defs:
            if d.is_required and d.field_key not in opt:
                raise ValueError(f'Required optional field: {d.label}')
    meta['optional_fields'] = opt
    return json.dumps(meta)


def optional_fields_from_entity(row):
    try:
        meta = json.loads(row.details_json or '{}') if getattr(row, 'details_json', None) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        meta = {}
    return meta.get('optional_fields') or {}


def posting_context(user):
    uid = getattr(user, 'id', None) if user else None
    return {'user_id': uid, 'role_key': _role_key_for_user(user)}


def assert_screen_access(ledger, screen: str):
    """Raise PermissionError if flat screen_permissions disables this route."""
    if not ledger or not screen:
        return
    from accounting_gl_service import _parse_settings
    settings = _parse_settings(ledger)
    perms = settings.get('screen_permissions') or {}
    if not perms:
        return
    if screen in perms and perms[screen] is False:
        raise PermissionError(f'Access denied to accounting module: {screen}')
    # nested role map: { role: { gl: 'full' } } — allow if any role grants
    if screen not in perms and isinstance(next(iter(perms.values()), None), dict):
        return


def screen_access_for_request(ledger, path: str, method: str):
    if method == 'GET' and ('/catalog' in path or path.endswith('/dashboard') or '/i18n' in path):
        return
    from accounting_all_chunks import screen_for_api_path
    screen = screen_for_api_path(path)
    if screen:
        assert_screen_access(ledger, screen)
