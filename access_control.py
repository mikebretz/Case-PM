"""
Case PM access control — session hardening, login rate limiting, API module guards.
"""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from threading import Lock

from flask import jsonify, request, session

SESSION_ACTIVITY_KEY = 'casepm_last_activity'


def reset_session_activity():
    """Fresh activity timestamp — call after every successful login."""
    session[SESSION_ACTIVITY_KEY] = time.time()
    session.modified = True


def clear_session_activity():
    session.pop(SESSION_ACTIVITY_KEY, None)
    session.modified = True

FINANCIAL_MODULES = frozenset({
    'budget', 'forecast', 'commitments', 'pay_applications',
    'pay_applications_gc', 'pay_applications_sub', 'pay_applications_lien_waivers',
    'companies', 'estimating',
})

# Longest prefixes first so specific rules win over general ones.
API_PREFIX_MODULE = [
    ('/api/workflow/respond/pay_applications', 'pay_applications'),
    ('/api/workflow/respond/pay_app', 'pay_applications'),
    ('/api/workflow/respond/payapp', 'pay_applications'),
    ('/api/workflow/respond/g702', 'pay_applications'),
    ('/api/rfis', 'rfis'),
    ('/api/submittals', 'submittals'),
    ('/api/change-orders', 'change_orders'),
    ('/api/co/', 'change_orders'),
    ('/api/pcos', 'change_orders'),
    ('/api/change-events', 'change_orders'),
    ('/api/rfqs', 'change_orders'),
    ('/api/estimates', 'estimating'),
    ('/api/cors', 'change_orders'),
    ('/api/daily-logs', 'daily_log'),
    ('/api/weekly-reports', 'weekly_report'),
    ('/api/punch-items', 'punch_list'),
    ('/api/safety/', 'safety'),
    ('/api/photos', 'photos'),
    ('/api/inspections', 'inspections'),
    ('/api/deliveries', 'deliveries'),
    ('/api/meeting-minutes', 'meeting_minutes'),
    ('/api/documents', 'documents'),
    ('/api/document-folders', 'documents'),
    ('/api/drawings', 'drawings'),
    ('/api/budget', 'budget'),
    ('/api/forecast', 'forecast'),
    ('/api/commitments', 'commitments'),
    ('/api/pay-applications', 'pay_applications'),
    ('/api/pay_apps', 'pay_applications'),
    ('/api/companies', 'companies'),
    ('/api/sage/', 'budget'),
    ('/api/schedules', 'schedule'),
    ('/api/schedule', 'schedule'),
    ('/api/projects', 'projects'),
    ('/api/dashboard', 'dashboard'),
    ('/api/email', 'email'),
    ('/api/permissions', 'users'),
    ('/api/users', 'users'),
    ('/api/audit', 'audit_log'),
    ('/api/program-settings', 'program_settings'),
    ('/api/developer', 'developer'),
    ('/api/notifications', 'notifications'),
    ('/api/approvals', 'notifications'),
]

# Paths any authenticated user may call (own profile, project switcher, etc.)
API_AUTH_ONLY_PREFIXES = (
    '/api/users/me/',
    '/api/users/list',
    '/api/current-project',
    '/api/notifications',
    '/api/stats',
)

METHOD_MIN_ACCESS = {
    'GET': 'view',
    'HEAD': 'view',
    'OPTIONS': 'view',
    'POST': 'entry',
    'PUT': 'edit',
    'PATCH': 'edit',
    'DELETE': 'edit',
}

APPROVAL_PATH_RE = re.compile(r'^/api/approvals/\d+/(decide|approve|reject)', re.I)
USERS_ADMIN_PATH_RE = re.compile(r'^/api/users(?:/\d+)?(?:/permissions|/reset-password)?$', re.I)

_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()
MAX_LOGIN_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 900
LOGIN_LOCKOUT_SECONDS = 900


def _login_limits():
    try:
        from program_settings_persistence import load_security_settings
        sec = load_security_settings()
        return (
            int(sec.get('max_login_attempts') or MAX_LOGIN_ATTEMPTS),
            int(sec.get('lockout_minutes') or 15) * 60,
        )
    except Exception:
        return MAX_LOGIN_ATTEMPTS, LOGIN_LOCKOUT_SECONDS


def configure_app_security(app):
    """Legacy hook — session lifetime; secret key handled by security_platform."""
    lifetime = int(os.environ.get('CASEPM_SESSION_HOURS', '12'))
    app.config['PERMANENT_SESSION_LIFETIME'] = lifetime * 3600


def _client_key(email: str) -> str:
    ip = (request.headers.get('X-Forwarded-For') or request.remote_addr or 'unknown').split(',')[0].strip()
    return f'{ip}:{(email or "").strip().lower()}'


def check_login_allowed(email: str) -> tuple[bool, int]:
    """Return (allowed, seconds_until_retry)."""
    max_attempts, lockout_seconds = _login_limits()
    key = _client_key(email)
    now = time.time()
    with _login_lock:
        attempts = _login_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        _login_attempts[key] = attempts
        if len(attempts) >= max_attempts:
            oldest = min(attempts)
            retry = int(lockout_seconds - (now - oldest))
            return False, max(retry, 1)
    return True, 0


def record_login_failure(email: str) -> None:
    key = _client_key(email)
    with _login_lock:
        _login_attempts.setdefault(key, []).append(time.time())


def record_login_success(email: str) -> None:
    key = _client_key(email)
    with _login_lock:
        _login_attempts.pop(key, None)


def user_global_flags(user) -> dict:
    try:
        from user_permissions_persistence import get_user_permissions
        perms = get_user_permissions(user)
        global_flags = perms.get('global') or {}
        return {
            'client_portal_only': bool(global_flags.get('client_portal_only')),
            'hide_financials': bool(global_flags.get('hide_financials')),
        }
    except Exception:
        return {'client_portal_only': False, 'hide_financials': False}


def user_is_privileged(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'role', None) == 'Admin':
        return True
    try:
        from developer_tools import is_developer
        return is_developer(user)
    except Exception:
        return False


def resolve_api_module(path: str) -> str | None:
    for prefix, module_key in API_PREFIX_MODULE:
        if path.startswith(prefix):
            return module_key
    return None


def min_access_for_request(method: str, path: str) -> str:
    if APPROVAL_PATH_RE.search(path):
        return 'view'
    if USERS_ADMIN_PATH_RE.match(path.split('?')[0]):
        if method.upper() in ('GET', 'HEAD', 'OPTIONS'):
            return 'view'
        return 'admin'
    return METHOD_MIN_ACCESS.get((method or 'GET').upper(), 'edit')


def guard_api_request(current_user):
    """
    Enforce module permissions on /api/* routes.
    Returns a Flask response to short-circuit, or None to continue.
    """
    path = request.path or ''
    if not path.startswith('/api/'):
        return None
    if not getattr(current_user, 'is_authenticated', False):
        return None

    for prefix in API_AUTH_ONLY_PREFIXES:
        if path.startswith(prefix):
            return None

    # User self-service profile routes under /api/users/me are always allowed.
    if path.startswith('/api/users/me'):
        return None

    if user_is_privileged(current_user):
        return None

    module_key = resolve_api_module(path)
    if not module_key:
        return None

    try:
        from case_workflow import user_has_module_access, user_can_approve

        flags = user_global_flags(current_user)
        if flags.get('client_portal_only') and module_key not in (
            'dashboard', 'projects', 'documents', 'drawings', 'rfis', 'submittals',
            'change_orders', 'pay_applications', 'schedule', 'email', 'notifications',
        ):
            return jsonify({'error': 'Client portal access only — module not available.'}), 403

        if flags.get('hide_financials') and module_key in FINANCIAL_MODULES:
            return jsonify({'error': 'Financial data is not available for your account.'}), 403

        if APPROVAL_PATH_RE.search(path):
            m = re.search(r'/api/approvals/(\d+)', path)
            if m:
                from case_workflow import ApprovalRequest
                approval = ApprovalRequest.query.get(int(m.group(1)))
                if approval and not user_can_approve(current_user, approval.module):
                    return jsonify({'error': 'You are not allowed to approve this item.'}), 403
            return None

        min_access = min_access_for_request(request.method, path)
        if not user_has_module_access(current_user, module_key, min_access):
            return jsonify({
                'error': 'Permission denied.',
                'module': module_key,
                'required_access': min_access,
            }), 403
    except Exception:
        return jsonify({'error': 'Permission check failed. Access denied.'}), 403
    return None


def users_module_admin(user) -> bool:
    if getattr(user, 'role', None) == 'Admin':
        return True
    try:
        from developer_tools import is_developer
        if is_developer(user):
            return True
    except Exception:
        pass
    try:
        from case_workflow import user_has_module_access
        return user_has_module_access(user, 'users', 'admin')
    except Exception:
        return False


def enforce_session_idle_timeout(current_user, endpoint: str | None):
    """
    Log out authenticated users after configured inactivity.
    Returns (should_logout, timeout_minutes).
    """
    if not getattr(current_user, 'is_authenticated', False):
        return False, 0
    skip = {
        'login', 'logout', 'recovery_login', 'recovery_enter', 'force_change_password',
        'static', 'favicon',
    }
    if endpoint in skip:
        return False, 0
    try:
        from program_settings_persistence import load_security_settings
        timeout_min = int(load_security_settings().get('session_timeout_minutes') or 0)
    except Exception:
        timeout_min = 0
    now = time.time()
    if timeout_min <= 0:
        session[SESSION_ACTIVITY_KEY] = now
        session.modified = True
        return False, 0
    last = session.get(SESSION_ACTIVITY_KEY)
    if last is not None and now - float(last) > timeout_min * 60:
        return True, timeout_min
    session[SESSION_ACTIVITY_KEY] = now
    session.modified = True
    return False, timeout_min
