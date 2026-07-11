"""Load/save user permissions_json with normalization."""
from __future__ import annotations

import json

from permissions_catalog import (
    ROLE_TEMPLATES,
    catalog_for_ui,
    merge_permissions,
    permissions_from_role,
)


def get_user_permissions(user):
    return merge_permissions(getattr(user, 'role', None), getattr(user, 'permissions_json', None))


def save_user_permissions(user, payload, db):
    if not isinstance(payload, dict):
        raise ValueError('Invalid permissions payload')
    if payload.get('version') != 2:
        raise ValueError('Permissions must be version 2')
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
