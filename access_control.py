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

FINANCIAL_MODULES = frozenset({
    'budget', 'forecast', 'commitments', 'pay_applications',
})

# Longest prefixes first so specific rules win over general ones.
API_PREFIX_MODULE = [
    ('/api/rfis', 'rfis'),
    ('/api/submittals', 'submittals'),
    ('/api/change-orders', 'change_orders'),
    ('/api/co/', 'change_orders'),
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


def configure_app_security(app):
    """Apply production-oriented Flask session and cookie settings."""
    secret = os.environ.get('CASEPM_SECRET_KEY') or os.environ.get('SECRET_KEY')
    if secret:
        app.config['SECRET_KEY'] = secret

    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
    if os.environ.get('CASEPM_HTTPS', '').lower() in ('1', 'true', 'yes'):
        app.config['SESSION_COOKIE_SECURE'] = True

    lifetime = int(os.environ.get('CASEPM_SESSION_HOURS', '12'))
    app.config['PERMANENT_SESSION_LIFETIME'] = lifetime * 3600


def _client_key(email: str) -> str:
    ip = (request.headers.get('X-Forwarded-For') or request.remote_addr or 'unknown').split(',')[0].strip()
    return f'{ip}:{(email or "").strip().lower()}'


def check_login_allowed(email: str) -> tuple[bool, int]:
    """Return (allowed, seconds_until_retry)."""
    key = _client_key(email)
    now = time.time()
    with _login_lock:
        attempts = _login_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        _login_attempts[key] = attempts
        if len(attempts) >= MAX_LOGIN_ATTEMPTS:
            oldest = min(attempts)
            retry = int(LOGIN_LOCKOUT_SECONDS - (now - oldest))
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
        return None
    return None


def users_module_admin(user) -> bool:
    if user_is_privileged(user):
        return True
    try:
        from case_workflow import user_has_module_access
        return user_has_module_access(user, 'users', 'admin')
    except Exception:
        return False
