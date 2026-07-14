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
    name = (getattr(user, 'company', None) or '').strip()
    if name:
        keys.add(name)
    return keys


def _filter_company_dict(data: dict | None, allowed: set[str]) -> dict:
    if not isinstance(data, dict) or not allowed:
        return {}
    out = {}
    for key, val in data.items():
        sk = str(key)
        if sk in allowed:
            out[sk] = val
            continue
        if isinstance(val, dict):
            cid = val.get('companyId') or val.get('company_id')
            cname = val.get('companyName') or val.get('company_name')
            if cid is not None and str(cid) in allowed:
                out[sk] = val
            elif cname and cname in allowed:
                out[sk] = val
    return out


def filter_pay_app_state_for_sub_vendor(user, data: dict | None) -> dict | None:
    """Return pay app state limited to the sub vendor's company."""
    if not is_sub_vendor_portal_user(user):
        return data
    allowed = sub_vendor_company_keys(user)
    if not data:
        return data
    out = dict(data)
    for field in (
        'subcontractorSOV', 'subSOVStatus', 'subPayAppHistory',
        'subPendingSubmissions', 'subPayAppNumbers',
    ):
        if field in out:
            out[field] = _filter_company_dict(out.get(field), allowed)
    out.pop('contractorSOV', None)
    out.pop('currentPayAppPeriod', None)
    out.pop('payAppHistory', None)
    out.pop('previousPayApps', None)
    return out


def get_commitment_project_ids(user, Commitment=None) -> set[int]:
    cid = sub_vendor_company_id(user)
    if not cid or Commitment is None:
        return set()
    ids: set[int] = set()
    cid_s = str(cid)
    cname = (getattr(user, 'company', None) or '').strip().lower()
    try:
        for row in Commitment.query.all():
            row_cid = str(getattr(row, 'company_id', '') or '').strip()
            row_name = (getattr(row, 'company_name', '') or '').strip().lower()
            if row_cid == cid_s or (cname and row_name == cname):
                pid = getattr(row, 'project_id', None)
                if pid is not None:
                    ids.add(int(pid))
    except Exception:
        pass
    return ids


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
