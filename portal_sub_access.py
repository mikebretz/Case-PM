"""Sub/vendor portal — limited modules, company-scoped pay apps and projects."""
from __future__ import annotations


SUB_VENDOR_ALLOWED_MODULES = frozenset({
    'pay_applications',
    'pay_applications_sub',
    'pay_applications_lien_waivers',
    'change_orders_rfq',
    'estimating',
    'email',
    'notifications',
})


def user_global_flags(user) -> dict:
    try:
        from access_control import user_global_flags as _flags
        return _flags(user)
    except Exception:
        return {}


def is_sub_vendor_portal_user(user) -> bool:
    """Sub users with pay-app portal only (no GC pay app / job-wide financials)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    flags = user_global_flags(user)
    if flags.get('sub_vendor_portal_only'):
        return True
    try:
        from case_workflow import is_sub_user, user_has_module_access
        if not is_sub_user(user):
            return False
        if user_has_module_access(user, 'pay_applications_gc', 'view'):
            return False
        return user_has_module_access(user, 'pay_applications_sub', 'view')
    except Exception:
        return False


def resolve_sub_vendor_company(user, Company=None, db=None, persist_link: bool = False):
    """
    Resolve a sub/vendor's company from company_id, primary/financial contact, or name.
    Returns (company_id, company_name, company_row) — any field may be None.
    """
    if not user:
        return None, None, None
    if Company is None:
        try:
            from app import Company as CompanyModel
            Company = CompanyModel
        except Exception:
            Company = None
    if Company is None:
        return None, None, None

    uid = getattr(user, 'id', None)
    company = None

    cid = getattr(user, 'company_id', None)
    if cid is not None:
        try:
            company = Company.query.get(int(cid))
        except (TypeError, ValueError):
            company = None

    if company is None and uid is not None:
        try:
            company = Company.query.filter(
                (Company.primary_contact_user_id == int(uid))
                | (Company.financial_contact_user_id == int(uid))
            ).first()
        except Exception:
            company = None

    cname = (getattr(user, 'company', None) or '').strip()
    if company is None and cname:
        try:
            from sqlalchemy import func
            company = Company.query.filter(func.lower(Company.name) == cname.lower()).first()
        except Exception:
            company = None

    if company is None:
        return None, None, None

    if persist_link and db is not None:
        changed = False
        if getattr(user, 'company_id', None) != company.id:
            user.company_id = company.id
            changed = True
        if (getattr(user, 'company', None) or '').strip() != (company.name or '').strip():
            user.company = company.name
            changed = True
        if changed:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    return company.id, company.name, company


def user_has_linked_vendor_company(user, Company=None, db=None, persist_link: bool = False) -> bool:
    if not is_sub_vendor_portal_user(user):
        return True
    cid, _, _ = resolve_sub_vendor_company(user, Company, db, persist_link=persist_link)
    return cid is not None


def sub_vendor_company_id(user) -> int | None:
    cid, _, _ = resolve_sub_vendor_company(user)
    if cid is not None:
        try:
            return int(cid)
        except (TypeError, ValueError):
            pass
    return None


def sub_vendor_company_keys(user) -> set[str]:
    """Keys used in pay app state dicts for this vendor."""
    keys: set[str] = set()
    cid, cname, _ = resolve_sub_vendor_company(user)
    if cid is not None:
        keys.add(str(cid))
    if cname:
        keys.add(cname)
        keys.add(cname.strip())
    name = (getattr(user, 'company', None) or '').strip()
    if name:
        keys.add(name)
    return keys


def _allowed_key_variants(allowed: set[str]) -> set[str]:
    variants: set[str] = set()
    for key in allowed:
        sk = str(key).strip()
        if not sk:
            continue
        variants.add(sk)
        variants.add(sk.lower())
    return variants


def resolve_sub_vendor_sov_keys(user, data: dict | None) -> set[str]:
    """All pay-app dict keys that belong to this sub vendor (id vs name tolerant)."""
    if not data:
        return set()
    cid, cname, _ = resolve_sub_vendor_company(user)
    allowed = sub_vendor_company_keys(user)
    allowed_variants = _allowed_key_variants(allowed)
    name_lower = (cname or (getattr(user, 'company', None) or '')).strip().lower()
    keys: set[str] = set()

    sub_sov = data.get('subcontractorSOV') or {}
    sub_status = data.get('subSOVStatus') or {}

    try:
        from pay_app_persistence import _find_sub_sov_keys_for_company
        for key in _find_sub_sov_keys_for_company(sub_sov, cid, cname):
            keys.add(str(key))
    except Exception:
        pass

    for map_data in (sub_sov, sub_status):
        if not isinstance(map_data, dict):
            continue
        for key, val in map_data.items():
            sk = str(key).strip()
            if not sk:
                continue
            sk_lower = sk.lower()
            if sk in allowed or sk_lower in allowed_variants:
                keys.add(str(key))
                continue
            if name_lower and sk_lower == name_lower:
                keys.add(str(key))
                continue
            if isinstance(val, dict):
                st_cid = val.get('companyId') or val.get('company_id')
                st_name = (val.get('companyName') or val.get('company_name') or '').strip()
                st_name_lower = st_name.lower()
                if st_cid is not None and (
                    str(st_cid) in allowed or str(st_cid).lower() in allowed_variants
                ):
                    keys.add(str(key))
                elif st_name and (
                    st_name in allowed or st_name_lower in allowed_variants
                    or (name_lower and st_name_lower == name_lower)
                ):
                    keys.add(str(key))
    return keys


def _filter_company_dict(data: dict | None, allowed: set[str], sov_keys: set[str] | None = None) -> dict:
    if not isinstance(data, dict):
        return {}
    match_keys = set(sov_keys or ())
    if not match_keys:
        if not allowed:
            return {}
        allowed_variants = _allowed_key_variants(allowed)
        for key, val in data.items():
            sk = str(key).strip()
            if sk in allowed or sk.lower() in allowed_variants:
                match_keys.add(str(key))
                continue
            if isinstance(val, dict):
                cid = val.get('companyId') or val.get('company_id')
                cname = (val.get('companyName') or val.get('company_name') or '').strip()
                if cid is not None and (
                    str(cid) in allowed or str(cid).lower() in allowed_variants
                ):
                    match_keys.add(str(key))
                elif cname and (
                    cname in allowed or cname.lower() in allowed_variants
                ):
                    match_keys.add(str(key))
    if not match_keys:
        return {}
    return {k: data[k] for k in match_keys if k in data}


def filter_pay_app_state_for_sub_vendor(user, data: dict | None) -> dict | None:
    """Return pay app state limited to the sub vendor's company."""
    if not is_sub_vendor_portal_user(user):
        return data
    allowed = sub_vendor_company_keys(user)
    if not data:
        return data
    out = dict(data)
    sov_keys = resolve_sub_vendor_sov_keys(user, out)
    for field in (
        'subcontractorSOV', 'subSOVStatus', 'subPayAppHistory',
        'subPendingSubmissions', 'subPayAppNumbers',
    ):
        if field in out:
            out[field] = _filter_company_dict(out.get(field), allowed, sov_keys)
    out.pop('contractorSOV', None)
    out.pop('currentPayAppPeriod', None)
    out.pop('payAppHistory', None)
    out.pop('previousPayApps', None)
    return out


def get_company_job_project_ids(company, Commitment=None, PayAppProjectState=None) -> set[int]:
    """Projects where a company has commitments or subcontractor SOV lines."""
    if not company:
        return set()
    if Commitment is None:
        try:
            from app import Commitment as CommitmentModel
            Commitment = CommitmentModel
        except Exception:
            Commitment = None
    if PayAppProjectState is None:
        try:
            from app import PayAppProjectState as PayAppModel
            PayAppProjectState = PayAppModel
        except Exception:
            PayAppProjectState = None
    ids: set[int] = set()
    cid = getattr(company, 'id', None)
    cname = (getattr(company, 'name', None) or '').strip().lower()
    cid_s = str(cid) if cid is not None else ''
    if Commitment is not None:
        try:
            for row in Commitment.query.all():
                row_cid = str(getattr(row, 'company_id', '') or '').strip()
                row_name = (getattr(row, 'company_name', '') or '').strip().lower()
                matched = False
                if cid_s and row_cid and row_cid == cid_s:
                    matched = True
                elif cname and row_name and (row_name == cname or cname in row_name or row_name in cname):
                    matched = True
                if matched:
                    pid = getattr(row, 'project_id', None)
                    if pid is not None:
                        ids.add(int(pid))
        except Exception:
            pass
    if PayAppProjectState is not None:
        try:
            from pay_app_persistence import _parse_state, _find_sub_sov_keys_for_company
            for record in PayAppProjectState.query.all():
                payload = _parse_state(record)
                sub_sov = payload.get('subcontractorSOV') or {}
                if _find_sub_sov_keys_for_company(sub_sov, cid, getattr(company, 'name', None)):
                    pid = getattr(record, 'project_id', None)
                    if pid is not None:
                        ids.add(int(pid))
        except Exception:
            pass
    return ids


def grant_company_contact_project_memberships(user, company, db, ProjectMembership=None) -> set[int]:
    """Ensure a company contact can access every job site linked to that company."""
    if not user or not company or not db:
        return set()
    PM = ProjectMembership
    if PM is None:
        try:
            from case_workflow import ProjectMembership as PMModel
            PM = PMModel
        except Exception:
            return set()
    if PM is None:
        return set()
    project_ids = get_company_job_project_ids(company)
    if not project_ids:
        return set()
    uid = int(user.id)
    existing = {int(row.project_id) for row in PM.query.filter_by(user_id=uid).all()}
    changed = False
    for pid in sorted(project_ids):
        if pid in existing:
            continue
        db.session.add(PM(project_id=pid, user_id=uid, role='Subcontractor'))
        changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return project_ids


def get_sub_vendor_pay_app_project_ids(user, PayAppProjectState=None) -> set[int]:
    """Projects where this vendor appears in subcontractor SOV / status maps."""
    if not is_sub_vendor_portal_user(user):
        return set()
    if PayAppProjectState is None:
        try:
            from app import PayAppProjectState as PayAppModel
            PayAppProjectState = PayAppModel
        except Exception:
            return set()
    ids: set[int] = set()
    try:
        from pay_app_persistence import _parse_state
        for record in PayAppProjectState.query.all():
            payload = _parse_state(record)
            if resolve_sub_vendor_sov_keys(user, payload):
                pid = getattr(record, 'project_id', None)
                if pid is not None:
                    ids.add(int(pid))
    except Exception:
        pass
    return ids


def get_sub_vendor_project_ids(user, Project=None, ProjectMembership=None, Commitment=None, PayAppProjectState=None) -> set[int]:
    """All projects a sub/vendor portal user may access."""
    if not is_sub_vendor_portal_user(user):
        return set()
    try:
        from project_access import get_assigned_project_ids
        ids = get_assigned_project_ids(user, Project, ProjectMembership)
    except Exception:
        ids = set()
    if Commitment is None:
        try:
            from app import Commitment as CommitmentModel
            Commitment = CommitmentModel
        except Exception:
            Commitment = None
    if PayAppProjectState is None:
        try:
            from app import PayAppProjectState as PayAppModel
            PayAppProjectState = PayAppModel
        except Exception:
            PayAppProjectState = None
    ids |= get_commitment_project_ids(user, Commitment)
    ids |= get_sub_vendor_pay_app_project_ids(user, PayAppProjectState)
    _, _, company = resolve_sub_vendor_company(user)
    if company is not None:
        ids |= get_company_job_project_ids(company, Commitment, PayAppProjectState)
    return ids


def portal_home_endpoint_for_user(user) -> str:
    """Default landing page after login or when a module is blocked."""
    if is_sub_vendor_portal_user(user):
        return 'pay_applications_page'
    return 'dashboard'


def portal_home_redirect(user):
    """Flask redirect to the appropriate home for this user."""
    from flask import redirect, url_for
    return redirect(url_for(portal_home_endpoint_for_user(user)))


def get_commitment_project_ids(user, Commitment=None) -> set[int]:
    cid, cname, company = resolve_sub_vendor_company(user)
    if Commitment is None:
        return set()
    names_to_match: set[str] = set()
    for raw in (cname, getattr(user, 'company', None), company.name if company else None):
        name = (raw or '').strip().lower()
        if name:
            names_to_match.add(name)
    ids: set[int] = set()
    cid_s = str(cid) if cid is not None else ''
    try:
        for row in Commitment.query.all():
            row_cid = str(getattr(row, 'company_id', '') or '').strip()
            row_name = (getattr(row, 'company_name', '') or '').strip().lower()
            matched = False
            if cid_s and row_cid and row_cid == cid_s:
                matched = True
            elif row_name and row_name in names_to_match:
                matched = True
            elif row_name and names_to_match:
                for name in names_to_match:
                    if name and (name in row_name or row_name in name):
                        matched = True
                        break
            if matched:
                pid = getattr(row, 'project_id', None)
                if pid is not None:
                    ids.add(int(pid))
    except Exception:
        pass
    return ids


def ensure_sub_vendor_project_memberships(user, db, ProjectMembership=None) -> set[int]:
    """Grant project membership rows for jobs this sub vendor is linked to."""
    if not is_sub_vendor_portal_user(user) or db is None:
        return set()
    PM = ProjectMembership
    if PM is None:
        try:
            from case_workflow import ProjectMembership as PMModel
            PM = PMModel
        except Exception:
            return set()
    if PM is None:
        return set()
    try:
        from app import Project
    except Exception:
        Project = None
    project_ids = get_sub_vendor_project_ids(user, Project, PM)
    if not project_ids:
        return set()
    uid = int(user.id)
    existing = {
        int(row.project_id)
        for row in PM.query.filter_by(user_id=uid).all()
    }
    changed = False
    for pid in sorted(project_ids):
        if pid in existing:
            continue
        db.session.add(PM(project_id=pid, user_id=uid, role='Subcontractor'))
        changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return project_ids


def user_is_company_contact(user, Company=None) -> bool:
    if not user or Company is None:
        return False
    cid, _, company = resolve_sub_vendor_company(user, Company)
    if not cid or not company:
        return False
    try:
        uid = int(user.id)
        return uid in {
            int(x) for x in (
                getattr(company, 'primary_contact_user_id', None),
                getattr(company, 'financial_contact_user_id', None),
            ) if x
        }
    except Exception:
        return False
