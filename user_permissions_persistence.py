"""Load/save user permissions_json with normalization."""
from __future__ import annotations

import json

from permissions_catalog import (
    ACCESS_RANK,
    APPROVE_RANK,
    ROLE_TEMPLATES,
    catalog_for_ui,
    merge_permissions,
    permissions_from_role,
)


def _actor_is_platform_admin(actor) -> bool:
    if not actor:
        return False
    role = (getattr(actor, 'role', None) or '').strip()
    if role == 'Admin':
        return True
    try:
        from developer_tools import is_admin_or_developer
        return is_admin_or_developer(actor)
    except Exception:
        return False


PORTAL_RANK = {'client': 0, 'sub': 1, 'consultant': 2, 'field': 3, 'staff': 4}

RESTRICTIVE_GLOBAL_FLAGS = (
    'hide_financials',
    'client_portal_only',
    'sub_vendor_portal_only',
    'email_internal_only',
)


def _cap_access_level(requested: str, ceiling: str) -> str:
    req_rank = ACCESS_RANK.get(requested or 'none', 0)
    ceil_rank = ACCESS_RANK.get(ceiling or 'none', 0)
    if req_rank <= ceil_rank:
        return requested or 'none'
    return ceiling or 'none'


def _cap_approve_level(requested: str, ceiling: str) -> str:
    req_rank = APPROVE_RANK.get(requested or 'none', 0)
    ceil_rank = APPROVE_RANK.get(ceiling or 'none', 0)
    if req_rank <= ceil_rank:
        return requested or 'none'
    return ceiling or 'none'


def sanitize_permissions_for_actor(actor, payload: dict) -> dict:
    """Cap a permissions payload to what the actor may grant another user."""
    import copy

    if not isinstance(payload, dict) or payload.get('version') != 2:
        raise ValueError('Permissions must be version 2')

    if _actor_is_platform_admin(actor):
        return copy.deepcopy(payload)

    actor_perms = merge_permissions(
        getattr(actor, 'role', None),
        getattr(actor, 'permissions_json', None),
    )
    actor_modules = actor_perms.get('modules') or {}
    actor_global = actor_perms.get('global') or {}
    out = copy.deepcopy(payload)

    actor_portal = actor_perms.get('portal') or 'staff'
    target_portal = out.get('portal') or actor_portal
    if PORTAL_RANK.get(target_portal, 0) > PORTAL_RANK.get(actor_portal, 0):
        out['portal'] = actor_portal

    out_global = dict(out.get('global') or {})
    for flag in RESTRICTIVE_GLOBAL_FLAGS:
        if actor_global.get(flag):
            out_global[flag] = True
    out['global'] = out_global

    sanitized_modules = {}
    requested_modules = out.get('modules') or {}
    for mod_key, mod_val in requested_modules.items():
        if not isinstance(mod_val, dict):
            continue
        actor_mod = actor_modules.get(mod_key) or {'access': 'none', 'approve': 'none'}
        sanitized_modules[mod_key] = {
            'access': _cap_access_level(mod_val.get('access'), actor_mod.get('access')),
            'approve': _cap_approve_level(mod_val.get('approve'), actor_mod.get('approve')),
        }

    out['modules'] = sanitized_modules
    return out


def get_user_permissions(user):
    return merge_permissions(getattr(user, 'role', None), getattr(user, 'permissions_json', None))


def save_user_permissions(user, payload, db, *, actor=None):
    if not isinstance(payload, dict):
        raise ValueError('Invalid permissions payload')
    if payload.get('version') != 2:
        raise ValueError('Permissions must be version 2')
    if actor is not None:
        payload = sanitize_permissions_for_actor(actor, payload)
    user.permissions_json = json.dumps(payload)
    db.session.add(user)
    return payload


def apply_role_template(role):
    return permissions_from_role(role)


def serialize_user_permissions(user):
    perms = get_user_permissions(user)
    return {
        'user_id': user.id,
        'role': user.role,
        'permissions': perms,
        'is_customized': bool(getattr(user, 'permissions_json', None)),
    }


def catalog_payload():
    return catalog_for_ui()
