"""Project membership enforcement for remote multi-user access."""
from __future__ import annotations


def _membership_model():
    try:
        from case_workflow import ProjectMembership
        return ProjectMembership
    except Exception:
        return None


def _workflow_session():
    try:
        from case_workflow import _workflow_session as workflow_session
        return workflow_session()
    except Exception:
        pass
    try:
        import sys
        app_mod = sys.modules.get('app')
        if app_mod is not None and getattr(app_mod, 'db', None) is not None:
            return app_mod.db.session
    except Exception:
        pass
    return None


def _membership_rows(PM, **filters):
    session = _workflow_session()
    if session is None or PM is None:
        return []
    query = session.query(PM)
    for key, value in filters.items():
        query = query.filter_by(**{key: value})
    return query.all()


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
            for row in _membership_rows(PM, user_id=user.id):
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
    try:
        from portal_sub_access import get_commitment_project_ids
        Commitment = None
        try:
            from app import Commitment as CommitmentModel
            Commitment = CommitmentModel
        except Exception:
            pass
        if Commitment is not None:
            ids |= get_commitment_project_ids(user, Commitment)
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
    try:
        from portal_sub_access import is_sub_vendor_portal_user, get_sub_vendor_project_ids
        if is_sub_vendor_portal_user(user):
            allowed = get_sub_vendor_project_ids(user, Project, ProjectMembership)
            return project_id in allowed
    except Exception:
        pass
    if not enforcement_enabled():
        if Project is not None:
            return Project.query.get(project_id) is not None
        return True
    allowed = get_assigned_project_ids(user, Project, ProjectMembership)
    return project_id in allowed


def filter_projects_for_user(user, projects, Project=None, ProjectMembership=None):
    if user_bypasses_project_scope(user):
        return list(projects)
    try:
        from portal_sub_access import is_sub_vendor_portal_user, get_sub_vendor_project_ids
        if is_sub_vendor_portal_user(user):
            allowed = get_sub_vendor_project_ids(user, Project, ProjectMembership)
            return [p for p in projects if int(p.id) in allowed]
    except Exception:
        pass
    if not enforcement_enabled():
        return list(projects)
    allowed = get_assigned_project_ids(user, Project, ProjectMembership)
    return [p for p in projects if int(p.id) in allowed]


def list_memberships_for_user(user_id, ProjectMembership=None):
    PM = ProjectMembership or _membership_model()
    if PM is None:
        return []
    rows = _membership_rows(PM, user_id=int(user_id))
    return [{'project_id': r.project_id, 'role': r.role or 'Viewer'} for r in rows]


def save_memberships_for_user(user_id, project_ids, db=None, ProjectMembership=None, default_role='Viewer'):
    PM = ProjectMembership or _membership_model()
    if PM is None:
        raise RuntimeError('Project membership model not available')
    session = _workflow_session()
    if session is None:
        raise RuntimeError('Database session not available')
    uid = int(user_id)
    clean_ids = sorted({int(x) for x in (project_ids or []) if x is not None})
    session.query(PM).filter_by(user_id=uid).delete()
    for pid in clean_ids:
        session.add(PM(project_id=pid, user_id=uid, role=default_role))
    session.flush()
    return clean_ids
