"""Project-scoped access guards for uploads and field-module APIs."""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from flask import jsonify, request, send_from_directory

# APIs that accept project_id via query/body and must enforce membership.
_PROJECT_QUERY_PREFIXES = (
    '/api/rfis',
    '/api/punch-items',
    '/api/daily-logs',
    '/api/schedule',
    '/api/safety/',
    '/api/weekly-reports',
    '/api/deliveries',
    '/api/documents/search',
    '/api/documents/folders',
    '/api/documents/trash',
)

_ENTITY_PATH_RULES = (
    (re.compile(r'^/api/rfis/(\d+)(?:/|$)'), 'RFI'),
    (re.compile(r'^/api/punch-items/(\d+)(?:/|$)'), 'PunchItem'),
    (re.compile(r'^/api/daily-logs/(\d+)(?:/|$)'), 'DailyLog'),
    (re.compile(r'^/api/safety/reports/(\d+)(?:/|$)'), 'SafetyReport'),
    (re.compile(r'^/api/safety/certifications/(\d+)(?:/|$)'), 'SafetyCertification'),
    (re.compile(r'^/api/safety/training-events/(\d+)(?:/|$)'), 'SafetyTrainingEvent'),
    (re.compile(r'^/api/weekly-reports/(\d+)(?:/|$)'), 'WeeklyReport'),
    (re.compile(r'^/api/documents/(\d+)(?:/|$)'), 'Document'),
    (re.compile(r'^/api/commitments/(\d+)(?:/|$)'), 'Commitment'),
    (re.compile(r'^/api/change-orders/(\d+)(?:/|$)'), 'ChangeOrder'),
    (re.compile(r'^/api/pcos/(\d+)(?:/|$)'), 'PotentialChangeOrder'),
    (re.compile(r'^/api/projects/(\d+)(?:/|$)'), '__project__'),
)

_UPLOAD_RULES = (
    (re.compile(r'^/uploads/rfis/(?P<eid>\d+)/'), 'RFI'),
    (re.compile(r'^/uploads/daily_logs/(?P<eid>\d+)/'), 'DailyLog'),
    (re.compile(r'^/uploads/punch/(?P<eid>\d+)/'), 'PunchItem'),
    (re.compile(r'^/uploads/safety/(?P<eid>\d+)/'), 'SafetyReport'),
    (re.compile(r'^/uploads/submittals/(?P<eid>\d+)/'), 'Submittal'),
    (re.compile(r'^/uploads/documents/(?P<pid>\d+)/'), '__project__'),
    (re.compile(r'^/uploads/photos/(?P<pid>\d+)/'), '__project__'),
    (re.compile(r'^/uploads/projects/(?P<pid>\d+)/'), '__project__'),
    (re.compile(r'^/uploads/contracts/(?P<pid>\d+)/'), '__project__'),
    (re.compile(r'^/uploads/spec_books/(?P<pid>\d+)/'), '__project__'),
    (re.compile(r'^/uploads/commitments/(?P<eid>\d+)/'), 'Commitment'),
    (re.compile(r'^/uploads/change_orders/pco_(?P<eid>\d+)/'), 'PotentialChangeOrder'),
    (re.compile(r'^/uploads/change_orders/(?P<eid>\d+)/'), 'ChangeOrder'),
)

_SKIP_API_PROJECT_GUARD = (
    '/api/session/touch',
    '/api/presence/',
    '/api/developer/',
    '/api/notifications',
    '/api/users/me',
    '/api/version',
    '/api/schedules/portfolio',
    '/api/projects/financial-summary',
    '/api/projects/validate-number',
    '/api/email/',
    '/api/internal-messages',
    '/api/workflow/',
    '/api/integrations/',
    '/api/sage/',
)


def safe_relative_redirect_url(url: str | None, default: str) -> str:
    """Allow only same-site relative paths (blocks open redirects)."""
    candidate = (url or '').strip()
    if not candidate:
        return default
    if not candidate.startswith('/') or candidate.startswith('//'):
        return default
    if '://' in candidate or candidate.startswith('\\'):
        return default
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    return candidate


def safe_upload_basename(filename: str | None) -> str:
    name = os.path.basename(str(filename or '').replace('\\', '/'))
    if not name or name in ('.', '..'):
        raise ValueError('Invalid filename')
    return name


def _load_model(name: str):
    import sys
    app_mod = sys.modules.get('app')
    if app_mod is None:
        return None
    return getattr(app_mod, name, None)


def _entity_project_id(model_name: str, entity_id: int):
    if model_name == '__project__':
        Project = _load_model('Project')
        if Project is None:
            return None
        return entity_id if Project.query.get(entity_id) else None
    Model = _load_model(model_name)
    if Model is None:
        return None
    row = Model.query.get(entity_id)
    if row is None:
        return None
    return getattr(row, 'project_id', None)


def resolve_upload_project_id(path: str | None) -> int | None:
    p = (path or '').split('?', 1)[0]
    for pattern, model_name in _UPLOAD_RULES:
        m = pattern.match(p)
        if not m:
            continue
        groups = m.groupdict()
        if 'pid' in groups:
            return _entity_project_id('__project__', int(groups['pid']))
        if 'eid' in groups:
            return _entity_project_id(model_name, int(groups['eid']))
    return None


def _request_project_id() -> int | None:
    pid = request.args.get('project_id', type=int)
    if pid:
        return int(pid)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        body = request.get_json(silent=True) or {}
        raw = body.get('project_id')
        if raw is not None and str(raw).strip() != '':
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    return None


def _resolve_api_entity_project_id(path: str) -> int | None:
    for pattern, model_name in _ENTITY_PATH_RULES:
        m = pattern.match(path)
        if not m:
            continue
        return _entity_project_id(model_name, int(m.group(1)))
    return None


def _check_project_access(user, project_id: int | None):
    from financial_security import require_financial_project_access
    Project = _load_model('Project')
    return require_financial_project_access(user, project_id, Project)


def guard_upload_request(user, path: str | None):
    """Return a Flask response tuple when access is denied, else None."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return jsonify({'error': 'Authentication required'}), 401
    project_id = resolve_upload_project_id(path)
    if project_id is None:
        return jsonify({'error': 'Not found'}), 404
    try:
        _check_project_access(user, project_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    return None


def guard_api_project_scope(user, path: str | None, method: str | None = None):
    """Enforce project membership on field-module APIs. Return response tuple or None."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    p = (path or '').split('?', 1)[0]
    if not p.startswith('/api/'):
        return None
    for skip in _SKIP_API_PROJECT_GUARD:
        if p.startswith(skip):
            return None
    try:
        from project_access import user_bypasses_project_scope
        if user_bypasses_project_scope(user):
            return None
    except Exception:
        pass

    entity_pid = _resolve_api_entity_project_id(p)
    if entity_pid is not None:
        try:
            _check_project_access(user, entity_pid)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        return None

    if p == '/projects' or p.startswith('/projects/'):
        if re.match(r'^/projects/\d+/status$', p) and (method or '').upper() == 'POST':
            try:
                _check_project_access(user, int(p.split('/')[2]))
            except (ValueError, PermissionError) as exc:
                return jsonify({'error': str(exc)}), 403
            except (TypeError, IndexError):
                return jsonify({'error': 'Invalid project'}), 400
        return None

    needs_query = any(p == prefix or p.startswith(prefix + '/') for prefix in _PROJECT_QUERY_PREFIXES)
    if not needs_query:
        return None
    project_id = _request_project_id()
    if not project_id:
        return None
    try:
        _check_project_access(user, project_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    return None


def send_protected_upload(user, project_id: int, directory: str, filename: str, **kwargs):
    """Send a file only when the user may access the project."""
    _check_project_access(user, project_id)
    safe_name = safe_upload_basename(filename)
    return send_from_directory(directory, safe_name, **kwargs)
