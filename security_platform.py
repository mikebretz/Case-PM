"""
Case PM platform security — secret key, CSRF, HTTPS/proxy, response headers.
Supports on-premises (company server) and cloud (reverse proxy / load balancer) deployments.
"""
from __future__ import annotations

import os
import secrets
from functools import wraps

from flask import abort, jsonify, request, session

SECRET_KEY_FILE = os.path.join('instance', '.secret_key')
CSRF_SESSION_KEY = 'casepm_csrf_token'
CSRF_HEADER = 'X-CSRF-Token'
TWO_FA_VERIFIED_KEY = 'casepm_2fa_verified'
PENDING_2FA_USER_KEY = 'casepm_pending_2fa_user_id'

CSRF_EXEMPT_PREFIXES = (
    '/login',
    '/logout',
    '/recovery',
    '/static/',
    '/favicon',
    '/verify-2fa',
    '/force-change-password',
    '/download/',
    '/api/presence/heartbeat',
)

CSRF_EXEMPT_ENDPOINTS = frozenset({
    'login', 'logout', 'recovery_login', 'recovery_enter', 'force_change_password',
    'verify_2fa', 'static', 'favicon', 'download_casepm_connector',
    'download_casepm_connector_vbs',
})


def resolve_secret_key() -> str:
    """Env var > instance file > generate and persist a new random key."""
    env = os.environ.get('CASEPM_SECRET_KEY') or os.environ.get('SECRET_KEY')
    if env and env.strip():
        return env.strip()
    if os.path.isfile(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, encoding='utf-8') as fh:
                key = fh.read().strip()
            if len(key) >= 32:
                return key
        except OSError:
            pass
    key = secrets.token_hex(48)
    try:
        os.makedirs('instance', exist_ok=True)
        with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as fh:
            fh.write(key + '\n')
        try:
            os.chmod(SECRET_KEY_FILE, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return key


def load_deployment_settings():
    try:
        from program_settings_persistence import load_security_settings
        sec = load_security_settings()
    except Exception:
        sec = {}
    mode = (sec.get('deployment_mode') or os.environ.get('CASEPM_DEPLOYMENT', 'on_prem')).strip().lower()
    if mode not in ('on_prem', 'cloud'):
        mode = 'on_prem'
    behind_proxy = sec.get('behind_reverse_proxy')
    if behind_proxy is None:
        behind_proxy = (
            mode == 'cloud'
            or os.environ.get('CASEPM_BEHIND_PROXY', '').lower() in ('1', 'true', 'yes')
            or os.environ.get('CASEPM_REMOTE', '').lower() in ('1', 'true', 'yes')
        )
    force_https = sec.get('force_https')
    if force_https is None:
        force_https = os.environ.get('CASEPM_HTTPS', '').lower() in ('1', 'true', 'yes')
    trust_proto = sec.get('trust_x_forwarded_proto')
    if trust_proto is None:
        trust_proto = bool(behind_proxy)
    hsts = int(sec.get('hsts_max_age') or 0)
    if hsts <= 0 and force_https:
        hsts = 31536000
    allowed = sec.get('allowed_hosts') or os.environ.get('CASEPM_ALLOWED_HOSTS', '')
    if isinstance(allowed, str):
        allowed_hosts = [h.strip().lower() for h in allowed.split(',') if h.strip()]
    else:
        allowed_hosts = [str(h).strip().lower() for h in (allowed or []) if str(h).strip()]
    return {
        'deployment_mode': mode,
        'behind_reverse_proxy': bool(behind_proxy),
        'force_https': bool(force_https),
        'trust_x_forwarded_proto': bool(trust_proto),
        'hsts_max_age': max(0, hsts),
        'allowed_hosts': allowed_hosts,
        'enforce_project_membership': bool(sec.get('enforce_project_membership', False)),
        'require_2fa_for_admins': bool(sec.get('require_2fa_for_admins', False)),
    }


def request_is_secure(deploy=None):
    deploy = deploy or load_deployment_settings()
    if deploy.get('trust_x_forwarded_proto'):
        xf = (request.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip().lower()
        if xf == 'https':
            return True
    return request.is_secure


def configure_app_security(app):
    """Session cookies, secret key, optional ProxyFix for cloud / on-prem SSL terminator."""
    app.config['SECRET_KEY'] = resolve_secret_key()
    deploy = load_deployment_settings()

    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
    if deploy['force_https'] or os.environ.get('CASEPM_HTTPS', '').lower() in ('1', 'true', 'yes'):
        app.config['SESSION_COOKIE_SECURE'] = True

    lifetime = int(os.environ.get('CASEPM_SESSION_HOURS', '12'))
    app.config['PERMANENT_SESSION_LIFETIME'] = lifetime * 3600

    if deploy['behind_reverse_proxy']:
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        except ImportError:
            pass

    app.config['CASEPM_DEPLOYMENT'] = deploy


def ensure_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
        session.modified = True
    return token


def validate_csrf_token() -> bool:
    expected = session.get(CSRF_SESSION_KEY)
    if not expected:
        return False
    supplied = (
        request.headers.get(CSRF_HEADER)
        or request.form.get('csrf_token')
        or (request.get_json(silent=True) or {}).get('csrf_token')
    )
    if not supplied:
        return False
    import hmac
    return hmac.compare_digest(str(supplied), str(expected))


def csrf_exempt_for_request(endpoint: str | None, path: str) -> bool:
    if endpoint in CSRF_EXEMPT_ENDPOINTS:
        return True
    for prefix in CSRF_EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def guard_csrf(endpoint: str | None = None):
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None
    path = request.path or ''
    if csrf_exempt_for_request(endpoint or '', path):
        return None
    if validate_csrf_token():
        return None
    return jsonify({'error': 'CSRF validation failed. Refresh the page and try again.'}), 403


def guard_host_header(deploy=None):
    deploy = deploy or load_deployment_settings()
    hosts = deploy.get('allowed_hosts') or []
    host = (request.host or '').split(':')[0].lower()
    # Cloudflare quick-tunnel hostnames (START-INTERNET-TUNNEL.bat)
    if host.endswith('.trycloudflare.com'):
        return None
    if not hosts:
        return None
    if host in hosts or 'localhost' in hosts and host in ('localhost', '127.0.0.1'):
        return None
    if host in ('localhost', '127.0.0.1') and not hosts:
        return None
    if host not in hosts:
        return jsonify({'error': 'Invalid host header.'}), 400
    return None


def guard_https_redirect(deploy=None):
    deploy = deploy or load_deployment_settings()
    if not deploy.get('force_https'):
        return None
    if request.method == 'GET' and not request_is_secure(deploy):
        from flask import redirect
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)
    return None


def apply_security_headers(response, deploy=None):
    deploy = deploy or load_deployment_settings()
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    if deploy.get('hsts_max_age') and request_is_secure(deploy):
        response.headers['Strict-Transport-Security'] = f"max-age={deploy['hsts_max_age']}; includeSubDomains"
    return response


def mark_2fa_verified(verified: bool = True):
    session[TWO_FA_VERIFIED_KEY] = bool(verified)
    session.pop(PENDING_2FA_USER_KEY, None)
    session.modified = True


def is_2fa_verified() -> bool:
    return bool(session.get(TWO_FA_VERIFIED_KEY))


def set_pending_2fa_user(user_id: int):
    session[PENDING_2FA_USER_KEY] = int(user_id)
    session[TWO_FA_VERIFIED_KEY] = False
    session.modified = True


def get_pending_2fa_user_id():
    val = session.get(PENDING_2FA_USER_KEY)
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None
