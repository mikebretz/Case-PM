"""Project membership enforcement for remote multi-user access."""
from __future__ import annotations


def _membership_model():
    try:
        from case_workflow import ProjectMembership
        return ProjectMembership
    except Exception:
        return None


def enforcement_enabled() -> bool:
    try:
        from program_settings_persistence import load_security_settings
        return bool(load_security_settings().get('enforce_project_membership', False))
    except Exception:
        return False


def user_bypasses_project_scope(user) -> bool:
    if not user:
        return False
    role = getattr(user, 'role', None)
    if role in ('Admin', 'Developer'):
        return True
    try:
        from developer_tools import is_developer
        if is_developer(user):
            return True
    except Exception:
        pass
    return False


def get_assigned_project_ids(user, Project=None, ProjectMembership=None) -> set[int]:
    PM = ProjectMembership or _membership_model()
    ids: set[int] = set()
    if PM is not None:
        try:
            for row in PM.query.filter_by(user_id=user.id).all():
                ids.add(int(row.project_id))
        except Exception:
            pass
    company_id = getattr(user, 'company_id', None)
    if company_id and Project is not None:
        try:
            for p in Project.query.filter_by(client_company_id=company_id).all():
                ids.add(int(p.id))
        except Exception:
            pass
    return ids


def user_can_access_project(user, project_id, Project=None, ProjectMembership=None) -> bool:
    if not user or project_id is None:
        return False
    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return False
    if user_bypasses_project_scope(user):
        return True
    if not enforcement_enabled():
        if Project is not None:
            return Project.query.get(project_id) is not None
        return True
    allowed = get_assigned_project_ids(user, Project, ProjectMembership)
    return project_id in allowed


def filter_projects_for_user(user, projects, Project=None, ProjectMembership=None):
    if user_bypasses_project_scope(user):
        return list(projects)
    if not enforcement_enabled():
        return list(projects)
    allowed = get_assigned_project_ids(user, Project, ProjectMembership)
    return [p for p in projects if int(p.id) in allowed]


def list_memberships_for_user(user_id, ProjectMembership=None):
    PM = ProjectMembership or _membership_model()
    if PM is None:
        return []
    rows = PM.query.filter_by(user_id=int(user_id)).all()
    return [{'project_id': r.project_id, 'role': r.role or 'Viewer'} for r in rows]


def save_memberships_for_user(user_id, project_ids, db, ProjectMembership=None, default_role='Viewer'):
    PM = ProjectMembership or _membership_model()
    if PM is None:
        raise RuntimeError('Project membership model not available')
    uid = int(user_id)
    clean_ids = sorted({int(x) for x in (project_ids or []) if x is not None})
    PM.query.filter_by(user_id=uid).delete()
    for pid in clean_ids:
        db.session.add(PM(project_id=pid, user_id=uid, role=default_role))
    db.session.flush()
    return clean_ids
