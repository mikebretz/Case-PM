"""Server-side user management — CRUD, password reset, serialization."""
from __future__ import annotations

import json
import secrets
import string
from datetime import datetime

from werkzeug.security import generate_password_hash

from permissions_catalog import permissions_from_role
from user_permissions_persistence import save_user_permissions

DEVELOPER_ROLE = 'Developer'


def _actor_can_see_developer_users(actor) -> bool:
    try:
        from developer_tools import is_developer
        return is_developer(actor)
    except Exception:
        return False


def _validate_role_change(actor, role: str | None, existing_role: str | None = None):
    role = (role or '').strip()
    if role == DEVELOPER_ROLE:
        try:
            from developer_tools import can_assign_developer_role
            if not can_assign_developer_role(actor):
                raise ValueError('Only a developer can assign the Developer role.')
        except ValueError:
            raise
        except Exception:
            raise ValueError('Only a developer can assign the Developer role.')
    if existing_role == DEVELOPER_ROLE and role and role != DEVELOPER_ROLE:
        try:
            from developer_tools import can_assign_developer_role
            if not can_assign_developer_role(actor):
                raise ValueError('Only a developer can change a Developer account.')
        except ValueError:
            raise
        except Exception:
            raise ValueError('Only a developer can change a Developer account.')


def filter_users_for_actor(users, actor):
    if _actor_can_see_developer_users(actor):
        return users
    return [u for u in users if (getattr(u, 'role', None) or '') != DEVELOPER_ROLE]


def ensure_user_admin_schema(db):
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('user')}
    additions = {
        'phones_json': 'TEXT',
        'notes': 'TEXT',
        'access_enabled': 'BOOLEAN DEFAULT 1',
    }
    for col, ddl in additions.items():
        if col not in cols:
            db.session.execute(text(f'ALTER TABLE user ADD COLUMN {col} {ddl}'))
    db.session.commit()


def _parse_phones(user) -> list[dict]:
    raw = getattr(user, 'phones_json', None)
    if not raw:
        phone = getattr(user, 'phone', None)
        return [{'type': 'Mobile', 'number': phone}] if phone else []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _phones_to_json(phones: list | None) -> str | None:
    if not phones:
        return None
    cleaned = []
    for p in phones:
        if isinstance(p, dict):
            number = (p.get('number') or '').strip()
            if number:
                cleaned.append({'type': p.get('type') or 'Mobile', 'number': number})
        elif isinstance(p, str) and p.strip():
            cleaned.append({'type': 'Mobile', 'number': p.strip()})
    return json.dumps(cleaned) if cleaned else None


def serialize_user(user, *, include_permissions: bool = False, actor=None) -> dict:
    role = user.role or 'Viewer'
    if actor and not _actor_can_see_developer_users(actor) and role == DEVELOPER_ROLE:
        return None
    phones = _parse_phones(user)
    access_enabled = getattr(user, 'access_enabled', None)
    if access_enabled is None:
        access_enabled = user.status == 'Active'
    payload = {
        'id': user.id,
        'server_id': user.id,
        'firstName': user.first_name,
        'lastName': user.last_name,
        'email': user.email,
        'phone': phones[0]['number'] if phones else (user.phone or ''),
        'phones': phones,
        'jobTitle': getattr(user, 'job_title', None) or '',
        'address': getattr(user, 'address', None) or '',
        'role': user.role or 'Viewer',
        'company': user.company or '',
        'company_id': user.company_id,
        'status': user.status or 'Active',
        'accessEnabled': bool(access_enabled) and user.status == 'Active',
        'twoFactorEnabled': bool(getattr(user, 'require_2fa', False)),
        'must_change_password': bool(getattr(user, 'must_change_password', False)),
        'notes': getattr(user, 'notes', None) or '',
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'has_custom_permissions': bool(user.permissions_json),
    }
    if include_permissions:
        from user_permissions_persistence import get_user_permissions
        payload['permissions'] = get_user_permissions(user)
        payload['permissions_v2'] = payload['permissions']
    return payload


def _resolve_company(db, Company, company_name: str | None, company_id: int | None):
    if company_id:
        return Company.query.get(company_id)
    name = (company_name or '').strip()
    if not name:
        return None
    from sqlalchemy import func
    return Company.query.filter(func.lower(Company.name) == name.lower()).first()


def generate_temp_password(length: int = 14) -> str:
    from password_policy import MIN_LENGTH
    length = max(length, MIN_LENGTH)
    special = '!@#$%&*'
    alphabet = string.ascii_letters + string.digits + special
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)
                and any(c in special for c in pwd)):
            return pwd


def create_user(db, User, Company, body: dict, *, actor_id: int | None = None, actor=None) -> tuple[object, str | None]:
    """Create user. Returns (user, temp_password_if_set)."""
    first = (body.get('firstName') or body.get('first_name') or '').strip()
    last = (body.get('lastName') or body.get('last_name') or '').strip()
    email = (body.get('email') or '').strip().lower()
    if not first or not last or not email:
        raise ValueError('First name, last name, and email are required.')
    if '@' not in email:
        raise ValueError('A valid email address is required.')
    if User.query.filter_by(email=email).first():
        raise ValueError('A user with this email already exists.')

    role = body.get('role') or 'Viewer'
    _validate_role_change(actor, role)
    access_enabled = body.get('accessEnabled', True)
    status = body.get('status') or ('Active' if access_enabled else 'Inactive')
    if not access_enabled:
        status = 'Inactive'

    temp_password = (body.get('tempPassword') or body.get('temp_password') or '').strip()
    generated = None
    if not temp_password:
        temp_password = generate_temp_password()
        generated = temp_password
    from password_policy import validate_temporary_password
    ok, msg = validate_temporary_password(temp_password)
    if not ok:
        raise ValueError(msg)

    company = _resolve_company(db, Company, body.get('company'), body.get('company_id'))
    phones = body.get('phones') or []

    user = User(
        first_name=first,
        last_name=last,
        email=email,
        role=role,
        company=company.name if company else (body.get('company') or ''),
        company_id=company.id if company else body.get('company_id'),
        job_title=(body.get('jobTitle') or body.get('job_title') or '').strip() or None,
        address=(body.get('address') or '').strip() or None,
        phone=phones[0]['number'] if phones else (body.get('phone') or '').strip() or None,
        status=status,
        must_change_password=True,
        require_2fa=bool(body.get('twoFactorEnabled') or body.get('require_2fa')),
    )
    user.set_password(temp_password)
    if hasattr(user, 'phones_json'):
        user.phones_json = _phones_to_json(phones)
    if hasattr(user, 'notes'):
        user.notes = (body.get('notes') or '').strip() or None
    if hasattr(user, 'access_enabled'):
        user.access_enabled = bool(access_enabled)

    perms = body.get('permissions') or body.get('permissions_v2')
    if perms and perms.get('version') == 2:
        save_user_permissions(user, perms, db)
    else:
        save_user_permissions(user, permissions_from_role(role), db)

    db.session.add(user)
    return user, generated


def update_user(db, User, Company, user, body: dict, *, actor=None) -> object:
    if 'role' in body and body['role']:
        _validate_role_change(actor, body['role'], getattr(user, 'role', None))
    if 'firstName' in body or 'first_name' in body:
        user.first_name = (body.get('firstName') or body.get('first_name') or user.first_name).strip()
    if 'lastName' in body or 'last_name' in body:
        user.last_name = (body.get('lastName') or body.get('last_name') or user.last_name).strip()
    if 'email' in body:
        email = (body.get('email') or '').strip().lower()
        if email and email != user.email:
            if User.query.filter(User.email == email, User.id != user.id).first():
                raise ValueError('Another user already uses that email.')
            user.email = email
    if 'role' in body and body['role']:
        user.role = body['role']
    if 'jobTitle' in body or 'job_title' in body:
        user.job_title = (body.get('jobTitle') or body.get('job_title') or '').strip() or None
    if 'address' in body:
        user.address = (body.get('address') or '').strip() or None
    if 'phones' in body:
        phones = body['phones'] or []
        user.phone = phones[0]['number'] if phones else user.phone
        if hasattr(user, 'phones_json'):
            user.phones_json = _phones_to_json(phones)
    if 'company' in body or 'company_id' in body:
        company = _resolve_company(db, Company, body.get('company'), body.get('company_id'))
        user.company = company.name if company else (body.get('company') or '')
        user.company_id = company.id if company else body.get('company_id')
    if 'twoFactorEnabled' in body or 'require_2fa' in body:
        user.require_2fa = bool(body.get('twoFactorEnabled', body.get('require_2fa')))
    if 'notes' in body and hasattr(user, 'notes'):
        user.notes = (body.get('notes') or '').strip() or None

    access_enabled = body.get('accessEnabled')
    if access_enabled is not None:
        if hasattr(user, 'access_enabled'):
            user.access_enabled = bool(access_enabled)
        user.status = 'Active' if access_enabled else 'Inactive'
    elif 'status' in body and body['status']:
        user.status = body['status']
        if hasattr(user, 'access_enabled'):
            user.access_enabled = user.status == 'Active'

    temp_password = (body.get('tempPassword') or body.get('temp_password') or '').strip()
    if temp_password:
        from password_policy import validate_temporary_password
        ok, msg = validate_temporary_password(temp_password)
        if not ok:
            raise ValueError(msg)
        user.set_password(temp_password)
        user.must_change_password = True

    perms = body.get('permissions') or body.get('permissions_v2')
    if perms and perms.get('version') == 2:
        save_user_permissions(user, perms, db)
    elif 'role' in body and body['role'] and not user.permissions_json:
        save_user_permissions(user, permissions_from_role(body['role']), db)

    db.session.add(user)
    return user


def reset_user_password(user, password: str | None = None) -> str:
    pwd = (password or '').strip() or generate_temp_password()
    from password_policy import validate_temporary_password
    ok, msg = validate_temporary_password(pwd)
    if not ok:
        raise ValueError(msg)
    user.set_password(pwd)
    user.must_change_password = True
    return pwd
