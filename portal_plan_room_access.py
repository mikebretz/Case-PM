"""Plan room / bidder network — restrict users to plan room surfaces only."""
from __future__ import annotations

PLAN_ROOM_BIDDER_ROLE = 'Plan Room Bidder'

# Pages and assets plan room bidders may load.
PLAN_ROOM_PAGE_PREFIXES = (
    '/plan-room',
    '/static/',
    '/favicon.ico',
    '/login',
    '/logout',
    '/verify_2fa',
    '/force-change-password',
    '/recovery-login',
    '/recovery-enter',
)

# APIs available to plan room portal users (no PM / accounting / project data).
PLAN_ROOM_API_PREFIXES = (
    '/api/bidder-network/',
    '/api/public/bidder-network/',
    '/api/users/me/',
    '/api/notifications',
    '/api/health',
)

ALLOWED_ENDPOINTS = frozenset({
    'static',
    'favicon',
    'login',
    'logout',
    'verify_2fa',
    'force_change_password',
    'recovery_login',
    'recovery_enter',
    'plan_room_public_page',
    'plan_room_projects_page',
    'plan_room_project_detail_page',
    'plan_room_package_detail_page',
    'plan_room_opportunities_redirect',
    'plan_room_document_view_page',
})


def _is_privileged_staff(user) -> bool:
    if not user:
        return False
    role = (getattr(user, 'role', None) or '').strip()
    if role in ('Admin', 'Developer'):
        return True
    try:
        from developer_tools import is_admin_or_developer
        return is_admin_or_developer(user)
    except Exception:
        return False


def _user_global_flags(user) -> dict:
    try:
        from access_control import user_global_flags
        return user_global_flags(user) or {}
    except Exception:
        return {}


def _has_approved_bidder_registration(user) -> bool:
    uid = getattr(user, 'id', None)
    if uid is None:
        return False
    try:
        from app import BidderNetworkRegistration
        row = BidderNetworkRegistration.query.filter_by(
            user_id=int(uid),
            status='approved',
        ).first()
        return row is not None
    except Exception:
        return False


def is_plan_room_portal_user(user) -> bool:
    """
    True for electronic plan room bidders — not GC staff, accounting, or sub PM portals.
    Privileged staff are never locked to plan room even if linked to a registration row.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if _is_privileged_staff(user):
        return False
    role = (getattr(user, 'role', None) or '').strip()
    if role == PLAN_ROOM_BIDDER_ROLE:
        return True
    flags = _user_global_flags(user)
    if flags.get('plan_room_portal_only'):
        return True
    if _has_approved_bidder_registration(user):
        return True
    return False


def plan_room_path_allowed(path: str) -> bool:
    base = (path or '').split('?')[0]
    if not base:
        return False
    if base.startswith('/plan-room/console'):
        return False
    for prefix in PLAN_ROOM_PAGE_PREFIXES:
        if base == prefix.rstrip('/') or base.startswith(prefix):
            return True
    return False


def plan_room_api_allowed(path: str, method: str) -> bool:
    base = (path or '').split('?')[0]
    if not base.startswith('/api/'):
        return False
    for prefix in PLAN_ROOM_API_PREFIXES:
        if base.startswith(prefix):
            if prefix == '/api/notifications' and method.upper() not in ('GET', 'HEAD', 'OPTIONS'):
                return False
            return True
    return False


def plan_room_home_redirect(user=None):
    from flask import redirect
    return redirect('/plan-room/projects')


def guard_plan_room_portal_request(current_user, request):
    """
    Block plan room bidders from PM, accounting, and other modules.
    Returns a Flask response to short-circuit, or None.
    """
    if not is_plan_room_portal_user(current_user):
        return None

    path = request.path or ''
    method = (request.method or 'GET').upper()
    endpoint = request.endpoint or ''

    if endpoint in ALLOWED_ENDPOINTS:
        return None
    if plan_room_path_allowed(path):
        return None
    if plan_room_api_allowed(path, method):
        return None

    from flask import flash, jsonify, redirect

    if path.startswith('/api/'):
        return jsonify({'error': 'Plan room access only — this module is not available.'}), 403

    flash('Your account is limited to the electronic plan room and bid opportunities.', 'error')
    return plan_room_home_redirect(current_user)


def guard_plan_room_api_request(current_user, request):
    """API-only guard (called from access_control.guard_api_request)."""
    if not is_plan_room_portal_user(current_user):
        return None
    path = request.path or ''
    method = (request.method or 'GET').upper()
    if plan_room_api_allowed(path, method):
        return None
    from flask import jsonify
    return jsonify({'error': 'Plan room access only — this API is not available.'}), 403


def normalize_approved_plan_room_user_accounts(db) -> int:
    """
    Legacy approved plan room registrations may have Subcontractor Contact roles.
    Re-lock those accounts to Plan Room Bidder permissions (idempotent).
    Returns count of users updated.
    """
    try:
        from app import BidderNetworkRegistration, User
        from user_permissions_persistence import save_user_permissions, permissions_from_role
    except Exception:
        return 0

    updated = 0
    rows = BidderNetworkRegistration.query.filter(
        BidderNetworkRegistration.status == 'approved',
        BidderNetworkRegistration.user_id.isnot(None),
    ).all()
    legacy_roles = frozenset({
        'Subcontractor Contact',
        'Subcontractor',
        'Subcontractor Accountant',
        'Company User',
        'Viewer',
    })
    for reg in rows:
        user = User.query.get(int(reg.user_id))
        if not user:
            continue
        role = (user.role or '').strip()
        if role == PLAN_ROOM_BIDDER_ROLE:
            continue
        if role not in legacy_roles and role:
            continue
        user.role = PLAN_ROOM_BIDDER_ROLE
        save_user_permissions(user, permissions_from_role(PLAN_ROOM_BIDDER_ROLE), db)
        updated += 1
    if updated:
        db.session.commit()
    return updated
