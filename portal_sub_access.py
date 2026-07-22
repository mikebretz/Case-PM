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
    role = (getattr(user, 'role', None) or '').strip()
    if role in ('Subcontractor Accountant', 'Subcontractor Contact'):
        return True
    try:
        from user_permissions_persistence import get_user_permissions
        from permissions_catalog import ACCESS_RANK
        perms = get_user_permissions(user)
        portal = perms.get('portal') or ''
        if portal not in ('sub', '') and role not in ('Subcontractor', 'Company User'):
            return False
        modules = perms.get('modules') or {}

        def _rank(mod):
            entry = modules.get(mod) or {}
            if isinstance(entry, dict):
                return ACCESS_RANK.get(entry.get('access', 'none'), 0)
            return 0

        if _rank('pay_applications_gc') >= ACCESS_RANK.get('view', 1):
            return False
        return _rank('pay_applications_sub') >= ACCESS_RANK.get('view', 1)
    except Exception:
        return role in ('Subcontractor Accountant', 'Subcontractor Contact', 'Subcontractor')


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
        except Exception:
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


def _normalize_company_map(block) -> dict:
    """Pay-app company buckets must be dicts; tolerate legacy/corrupt list values."""
    return block if isinstance(block, dict) else {}


def _allowed_key_variants(allowed: set[str]) -> set[str]:
    variants: set[str] = set()
    for key in allowed:
        sk = str(key).strip()
        if not sk:
            continue
        variants.add(sk)
        variants.add(sk.lower())
    return variants


def _discover_sov_keys_from_data(data: dict | None, company_id=None, company_name=None, user=None) -> set[str]:
    """Last-resort SOV key discovery when strict id/name matching fails."""
    keys: set[str] = set()
    if not isinstance(data, dict):
        return keys
    sub_status = data.get('subSOVStatus') or {}
    if not isinstance(sub_status, dict):
        sub_status = {}
    names: set[str] = set()
    for raw in (company_name, getattr(user, 'company', None) if user else None):
        name = (raw or '').strip().lower()
        if name:
            names.add(name)
    cid_s = str(company_id) if company_id is not None else ''
    for field in ('subcontractorSOV', 'subSOVStatus'):
        block = data.get(field) or {}
        if not isinstance(block, dict):
            continue
        for key, val in block.items():
            sk = str(key).strip()
            if not sk:
                continue
            st_entry = sub_status.get(key) or sub_status.get(sk) or {}
            if not (isinstance(st_entry, dict) and st_entry.get('status')):
                continue
            sk_lower = sk.lower()
            if cid_s and sk == cid_s:
                keys.add(sk)
                continue
            if sk_lower in names:
                keys.add(sk)
                continue
            if isinstance(val, dict):
                st_name = (val.get('companyName') or val.get('company_name') or '').strip().lower()
                st_cid = str(val.get('companyId') or val.get('company_id') or '').strip()
                if st_cid and cid_s and st_cid == cid_s:
                    keys.add(sk)
                elif st_name and (st_name in names or any(n in st_name or st_name in n for n in names)):
                    keys.add(sk)
            elif isinstance(val, list) and val and names and sk_lower in names:
                keys.add(sk)
    return keys


def resolve_sub_vendor_sov_keys(user, data: dict | None) -> set[str]:
    """All pay-app dict keys that belong to this sub vendor (id vs name tolerant)."""
    if not data:
        return set()
    try:
        cid, cname, _ = resolve_sub_vendor_company(user)
    except Exception:
        cid, cname = None, (getattr(user, 'company', None) or '').strip() or None
    allowed = sub_vendor_company_keys(user)
    allowed_variants = _allowed_key_variants(allowed)
    name_lower = (cname or (getattr(user, 'company', None) or '')).strip().lower()
    cid_s = str(cid) if cid is not None else ''
    keys: set[str] = set()

    sub_sov = _normalize_company_map(data.get('subcontractorSOV'))
    sub_status = _normalize_company_map(data.get('subSOVStatus'))

    try:
        from pay_app_persistence import _find_sub_sov_keys_for_company
        for key in _find_sub_sov_keys_for_company(sub_sov, cid, cname):
            keys.add(str(key))
    except Exception:
        pass

    def _entry_matches_vendor(st_entry, sk: str) -> bool:
        if not isinstance(st_entry, dict) or not st_entry.get('status'):
            return False
        sk_lower = sk.lower()
        if sk in allowed or sk_lower in allowed_variants:
            return True
        if name_lower and sk_lower == name_lower:
            return True
        st_name = (st_entry.get('companyName') or st_entry.get('company_name') or '').strip()
        st_name_lower = st_name.lower()
        if st_name and (
            st_name in allowed or st_name_lower in allowed_variants
            or (name_lower and (st_name_lower == name_lower or name_lower in st_name_lower or st_name_lower in name_lower))
        ):
            return True
        for field in ('companyId', 'company_id', 'localCompanyId', 'commitmentCompanyId'):
            raw = st_entry.get(field)
            if raw is None:
                continue
            raw_s = str(raw).strip()
            if not raw_s:
                continue
            if raw_s in allowed or raw_s.lower() in allowed_variants:
                return True
            if cid_s and raw_s == cid_s:
                return True
        return False

    for map_data in (sub_sov, sub_status):
        if not isinstance(map_data, dict):
            continue
        for key, val in map_data.items():
            sk = str(key).strip()
            if not sk:
                continue
            st_entry = sub_status.get(key) or sub_status.get(sk) or val or {}
            if _entry_matches_vendor(st_entry, sk):
                keys.add(str(key))
                continue
            if isinstance(val, dict):
                st_cid = val.get('companyId') or val.get('company_id')
                st_name = (val.get('companyName') or val.get('company_name') or '').strip()
                st_name_lower = st_name.lower()
                if st_cid is not None and (
                    str(st_cid) in allowed or str(st_cid).lower() in allowed_variants
                    or (cid_s and str(st_cid) == cid_s)
                ):
                    keys.add(str(key))
                elif st_name and (
                    st_name in allowed or st_name_lower in allowed_variants
                    or (name_lower and st_name_lower == name_lower)
                ):
                    keys.add(str(key))
    if not keys:
        keys = _discover_sov_keys_from_data(
            {'subcontractorSOV': sub_sov, 'subSOVStatus': sub_status},
            cid, cname, user,
        )
    if cid is not None:
        cid_s = str(cid)
        try:
            from pay_app_persistence import _sov_status_vendor_ids
            for key, entry in (sub_status or {}).items():
                if not isinstance(entry, dict) or not entry.get('status'):
                    continue
                sk = str(key).strip()
                if not sk:
                    continue
                if cid_s in _sov_status_vendor_ids(key, entry):
                    keys.add(sk)
        except Exception:
            pass
        for block in (sub_sov, sub_status):
            if not isinstance(block, dict):
                continue
            for key, val in block.items():
                sk = str(key).strip()
                if not sk:
                    continue
                st_entry = sub_status.get(key) or sub_status.get(sk) or {}
                if not (isinstance(st_entry, dict) and st_entry.get('status')):
                    continue
                if sk == cid_s:
                    keys.add(sk)
                    continue
                if isinstance(val, dict):
                    st_cid = str(val.get('companyId') or val.get('company_id') or '').strip()
                    if st_cid and st_cid == cid_s:
                        keys.add(sk)
    if not keys and isinstance(sub_status, dict):
        registered = [
            str(k).strip() for k, entry in sub_status.items()
            if str(k).strip() and isinstance(entry, dict) and entry.get('status')
        ]
        if len(registered) == 1:
            only_key = registered[0]
            entry = sub_status.get(only_key) or {}
            st_name = (entry.get('companyName') or entry.get('company_name') or '').strip().lower()
            st_cid = str(entry.get('companyId') or entry.get('company_id') or '').strip()
            matched = False
            if cid is not None:
                cid_s = str(cid)
                if only_key == cid_s or st_cid == cid_s:
                    matched = True
            if not matched and name_lower and (st_name == name_lower or name_lower in st_name or st_name in name_lower):
                matched = True
            if matched:
                keys.add(only_key)
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
    try:
        if not is_sub_vendor_portal_user(user):
            return data
        from pay_app_persistence import coerce_pay_app_state
        data = coerce_pay_app_state(data)
        if not data:
            return data
        allowed = sub_vendor_company_keys(user)
        out = dict(data)
        for field in ('subcontractorSOV', 'subSOVStatus', 'subPayAppHistory', 'subPendingSubmissions', 'subPayAppNumbers', 'subLienWaivers', 'subLienWaiverArchive'):
            if field in out:
                out[field] = _normalize_company_map(out.get(field))
        sov_keys = resolve_sub_vendor_sov_keys(user, out)
        if not sov_keys:
            cid, cname, _ = resolve_sub_vendor_company(user)
            sov_keys = _discover_sov_keys_from_data(out, cid, cname, user)
        if not sov_keys:
            try:
                from pay_app_persistence import _sov_status_vendor_ids
                cid, cname, _ = resolve_sub_vendor_company(user)
                cid_s = str(cid) if cid is not None else ''
                cname_l = (cname or '').strip().lower()
                sub_status = _normalize_company_map(out.get('subSOVStatus'))
                for key, entry in sub_status.items():
                    if not isinstance(entry, dict) or not entry.get('status'):
                        continue
                    sk = str(key).strip()
                    if not sk:
                        continue
                    if cid_s and cid_s in _sov_status_vendor_ids(sk, entry):
                        sov_keys.add(sk)
                        continue
                    st_name = (entry.get('companyName') or entry.get('company_name') or '').strip().lower()
                    if cname_l and st_name and (st_name == cname_l or cname_l in st_name or st_name in cname_l):
                        sov_keys.add(sk)
            except Exception:
                pass
        if not sov_keys and pay_app_state_includes_user(user, out):
            sub_status = _normalize_company_map(out.get('subSOVStatus'))
            for key, entry in sub_status.items():
                if isinstance(entry, dict) and entry.get('status'):
                    sk = str(key).strip()
                    if sk:
                        sov_keys.add(sk)
        for field in (
            'subcontractorSOV', 'subSOVStatus', 'subPayAppHistory',
            'subPendingSubmissions', 'subPayAppNumbers', 'subLienWaivers', 'subLienWaiverArchive',
        ):
            if field in out:
                out[field] = _filter_company_dict(out.get(field), allowed, sov_keys)
        try:
            from pay_app_persistence import build_g703_cost_code_index
            out['g703CostCodes'] = build_g703_cost_code_index(data)
        except Exception:
            out['g703CostCodes'] = []
        out.pop('contractorSOV', None)
        out.pop('currentPayAppPeriod', None)
        out.pop('payAppHistory', None)
        out.pop('previousPayApps', None)
        return out
    except Exception:
        from pay_app_persistence import coerce_pay_app_state
        return coerce_pay_app_state(data)


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
                found = _find_sub_sov_keys_for_company(sub_sov, cid, getattr(company, 'name', None))
                sov_key_set = {str(k) for k in sub_sov.keys()}
                if found and any(str(k) in sov_key_set for k in found):
                    pid = getattr(record, 'project_id', None)
                    if pid is not None:
                        ids.add(int(pid))
        except Exception:
            pass
    return ids


def resolve_company_from_sov_key(key, Company=None, state=None):
    """Resolve a subcontractorSOV dict key to a Company row (id or name)."""
    if Company is None:
        try:
            from app import Company as CompanyModel
            Company = CompanyModel
        except Exception:
            return None
    sk = str(key or '').strip()
    if not sk:
        return None

    if isinstance(state, dict):
        status_map = state.get('subSOVStatus') or {}
        entry = status_map.get(sk) or status_map.get(key)
        if isinstance(entry, dict):
            st_cid = entry.get('companyId') or entry.get('company_id')
            st_name = (entry.get('companyName') or entry.get('company_name') or '').strip()
            if st_cid is not None:
                try:
                    company = Company.query.get(int(st_cid))
                    if company:
                        return company
                except (TypeError, ValueError):
                    pass
            if st_name:
                try:
                    from sqlalchemy import func
                    company = Company.query.filter(func.lower(Company.name) == st_name.lower()).first()
                    if company:
                        return company
                except Exception:
                    pass

    try:
        company = Company.query.get(int(sk))
        if company:
            return company
    except (TypeError, ValueError):
        pass
    try:
        from sqlalchemy import func
        company = Company.query.filter(func.lower(Company.name) == sk.lower()).first()
        if company:
            return company
    except Exception:
        pass
    return None


def iter_sub_vendor_users_for_company(company, User=None):
    """Yield portal sub/vendor users linked to a company."""
    if not company:
        return
    if User is None:
        try:
            from app import User as UserModel
            User = UserModel
        except Exception:
            return
    seen: set[int] = set()
    candidates = []
    for uid in (
        getattr(company, 'primary_contact_user_id', None),
        getattr(company, 'financial_contact_user_id', None),
    ):
        if uid is None:
            continue
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        user = User.query.get(uid)
        if user:
            candidates.append(user)
            seen.add(uid)
    try:
        for user in User.query.filter_by(company_id=company.id).all():
            if user.id not in seen:
                candidates.append(user)
                seen.add(int(user.id))
    except Exception:
        pass
    cname = (getattr(company, 'name', None) or '').strip()
    if cname:
        try:
            from sqlalchemy import func
            for user in User.query.filter(func.lower(User.company) == cname.lower()).all():
                if user.id not in seen:
                    candidates.append(user)
                    seen.add(int(user.id))
        except Exception:
            pass
    for user in candidates:
        if is_sub_vendor_portal_user(user):
            yield user
    # Role-based fallback: sub accountants linked by company name only
    cname = (getattr(company, 'name', None) or '').strip().lower()
    if cname:
        try:
            roles = ('Subcontractor Accountant', 'Subcontractor Contact', 'Subcontractor')
            for user in User.query.filter(User.role.in_(roles)).all():
                if user.id in seen:
                    continue
                uname = (getattr(user, 'company', None) or '').strip().lower()
                if uname and (uname == cname or cname in uname or uname in cname):
                    if is_sub_vendor_portal_user(user):
                        yield user
                        seen.add(int(user.id))
        except Exception:
            pass


def grant_project_membership(project_id, user, db, ProjectMembership=None, role='Subcontractor') -> bool:
    """Add a single project membership row if missing. Returns True when added."""
    if not project_id or not user or not db:
        return False
    PM = ProjectMembership
    if PM is None:
        try:
            from case_workflow import ProjectMembership as PMModel
            PM = PMModel
        except Exception:
            return False
    if PM is None:
        return False
    try:
        pid = int(project_id)
        uid = int(user.id)
    except (TypeError, ValueError):
        return False
    existing = PM.query.filter_by(project_id=pid, user_id=uid).first()
    if existing:
        return False
    db.session.add(PM(project_id=pid, user_id=uid, role=role))
    return True


def sync_sub_vendor_memberships_from_pay_app_state(
    project_id,
    state,
    db,
    Company=None,
    User=None,
    ProjectMembership=None,
) -> set[int]:
    """
    When subcontractors are added to a job's SOV, grant their portal users
    membership on that project so it appears in the current-project list.
    """
    if not project_id or not isinstance(state, dict) or not db:
        return set()
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return set()
    if Company is None:
        try:
            from app import Company as CompanyModel
            Company = CompanyModel
        except Exception:
            return set()
    if User is None:
        try:
            from app import User as UserModel
            User = UserModel
        except Exception:
            return set()

    keys: set[str] = set()
    for field in ('subcontractorSOV', 'subSOVStatus'):
        block = state.get(field) or {}
        if not isinstance(block, dict):
            continue
        for key in block.keys():
            sk = str(key).strip()
            if sk:
                keys.add(sk)

    company_ids: set[int] = set()
    companies = []
    for key in keys:
        company = resolve_company_from_sov_key(key, Company, state)
        if company and company.id not in company_ids:
            company_ids.add(int(company.id))
            companies.append(company)

    granted_users: set[int] = set()
    changed = False
    for key in keys:
        company = resolve_company_from_sov_key(key, Company, state)
        users_for_key = []
        if company:
            users_for_key.extend(iter_sub_vendor_users_for_company(company, User))
        users_for_key.extend(iter_sub_vendor_users_for_sov_key(key, state, User))
        seen_uids: set[int] = set()
        for user in users_for_key:
            uid = int(user.id)
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            if grant_project_membership(pid, user, db, ProjectMembership):
                granted_users.add(uid)
                changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return set()
    return granted_users


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


def pay_app_state_includes_user(user, payload) -> bool:
    """True when this vendor appears on a job's sub SOV (empty line list is OK)."""
    if not isinstance(payload, dict):
        return False
    if resolve_sub_vendor_sov_keys(user, payload):
        return True
    sub_sov = payload.get('subcontractorSOV') or {}
    sub_status = payload.get('subSOVStatus') or {}
    if not isinstance(sub_sov, dict) and not isinstance(sub_status, dict):
        return False
    if not sub_sov and not sub_status:
        return False
    allowed = _allowed_key_variants(sub_vendor_company_keys(user))
    cid, cname, company = resolve_sub_vendor_company(user)
    names: set[str] = set()
    for raw in (cname, getattr(user, 'company', None), getattr(company, 'name', None) if company else None):
        name = (raw or '').strip().lower()
        if name:
            names.add(name)
    cid_s = str(cid) if cid is not None else ''
    if not isinstance(sub_status, dict):
        sub_status = {}
    for block in (sub_sov, sub_status):
        if not isinstance(block, dict):
            continue
        for key, val in block.items():
            sk = str(key).strip()
            if not sk:
                continue
            st_entry = sub_status.get(key) or sub_status.get(sk) or {}
            if not (isinstance(st_entry, dict) and st_entry.get('status')):
                continue
            sk_lower = sk.lower()
            st_name = ''
            if isinstance(val, dict):
                st_name = (val.get('companyName') or val.get('company_name') or '').strip().lower()
            if sk in allowed or sk_lower in allowed:
                return True
            if cid_s and sk == cid_s:
                return True
            if sk_lower in names:
                return True
            if st_name and st_name in names:
                return True
            for name in names:
                if not name:
                    continue
                if sk_lower == name or name in sk_lower or sk_lower in name:
                    return True
                if st_name and (st_name == name or name in st_name or st_name in name):
                    return True
    return False


def iter_sub_vendor_users_for_sov_key(key, state=None, User=None):
    """Find portal users when Company lookup fails but SOV key matches profile."""
    if User is None:
        try:
            from app import User as UserModel
            User = UserModel
        except Exception:
            return
    sk = str(key or '').strip()
    if not sk:
        return
    sk_lower = sk.lower()
    status_name = ''
    if isinstance(state, dict):
        entry = (state.get('subSOVStatus') or {}).get(sk) or (state.get('subSOVStatus') or {}).get(key)
        if isinstance(entry, dict):
            status_name = (entry.get('companyName') or entry.get('company_name') or '').strip().lower()
    roles = ('Subcontractor Accountant', 'Subcontractor Contact', 'Subcontractor')
    seen: set[int] = set()
    try:
        for user in User.query.filter(User.role.in_(roles)).all():
            if user.id in seen or not is_sub_vendor_portal_user(user):
                continue
            uid_cid = str(getattr(user, 'company_id', '') or '').strip()
            if uid_cid and uid_cid == sk:
                seen.add(int(user.id))
                yield user
                continue
            uname = (getattr(user, 'company', '') or '').strip().lower()
            if uname and (uname == sk_lower or sk_lower in uname or uname in sk_lower):
                seen.add(int(user.id))
                yield user
                continue
            if status_name and uname and (uname == status_name or status_name in uname or uname in status_name):
                seen.add(int(user.id))
                yield user
                continue
            cid, cname, _ = resolve_sub_vendor_company(user)
            if cid is not None and str(cid) == sk:
                seen.add(int(user.id))
                yield user
                continue
            cname_l = (cname or '').strip().lower()
            if cname_l and (cname_l == sk_lower or sk_lower in cname_l or cname_l in sk_lower):
                seen.add(int(user.id))
                yield user
    except Exception:
        return


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
            if pay_app_state_includes_user(user, payload):
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
    PayAppProjectState = Commitment = None
    try:
        from app import PayAppProjectState as PState, Commitment as CModel
        PayAppProjectState = PState
        Commitment = CModel
    except Exception:
        pass
    project_ids = get_sub_vendor_project_ids(user, Project, PM, Commitment, PayAppProjectState)
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


def _portal_user_is_privileged(user) -> bool:
    """Admin or Developer — full override privileges in portal context."""
    if not user:
        return False
    try:
        from developer_tools import is_admin_or_developer
        return is_admin_or_developer(user)
    except Exception:
        return getattr(user, 'role', None) in ('Admin', 'Developer')


def build_portal_context_payload(user, Company, db, helpers: dict) -> dict:
    """Assemble JSON-safe payload for GET /api/portal/context."""
    import json

    try:
        from companies_persistence import ensure_company_schema
        if db is not None:
            ensure_company_schema(db)
    except Exception:
        pass

    get_role_permissions = helpers.get('get_role_permissions')
    user_portal_type = helpers.get('user_portal_type')
    is_sub_user = helpers.get('is_sub_user')
    is_architect_user = helpers.get('is_architect_user')
    user_can_approve = helpers.get('user_can_approve')

    perms = {}
    try:
        perms = (get_role_permissions(user) if get_role_permissions else {}) or {}
        perms = json.loads(json.dumps(perms, default=str))
    except Exception:
        perms = {}

    company_id, company_name, company = None, None, None
    try:
        company_id, company_name, company = resolve_sub_vendor_company(
            user, Company, db, persist_link=False,
        )
    except Exception:
        pass
    if company is None and getattr(user, 'company_id', None) and Company is not None:
        try:
            company = Company.query.get(int(user.company_id))
            if company:
                company_id = company.id
                company_name = company.name
        except Exception:
            company = None

    try:
        sub_vendor = is_sub_vendor_portal_user(user)
    except Exception:
        role = (getattr(user, 'role', None) or '').strip()
        sub_vendor = role in ('Subcontractor Accountant', 'Subcontractor Contact')

    linked = True
    if sub_vendor:
        linked = company_id is not None

    global_flags = perms.get('global') if isinstance(perms.get('global'), dict) else {}
    can_approve = {}
    for mod in ('Pay Applications', 'Change Orders', 'Submittals', 'RFIs', 'Budget'):
        try:
            can_approve[mod] = bool(user_can_approve(user, mod)) if user_can_approve else False
        except Exception:
            can_approve[mod] = False

    try:
        portal = user_portal_type(user) if user_portal_type else 'staff'
    except Exception:
        portal = perms.get('portal', 'staff')

    try:
        is_sub = is_sub_user(user) if is_sub_user else False
    except Exception:
        is_sub = portal == 'sub'

    try:
        is_arch = is_architect_user(user) if is_architect_user else False
    except Exception:
        is_arch = (getattr(user, 'role', None) or '') == 'Architect'

    return {
        'userId': getattr(user, 'id', None),
        'userName': getattr(user, 'full_name', None) or '',
        'userEmail': getattr(user, 'email', None) or '',
        'role': getattr(user, 'role', None) or '',
        'isAdmin': _portal_user_is_privileged(user),
        'portal': portal,
        'companyId': company_id,
        'companyName': company_name or (getattr(user, 'company', None) or ''),
        'companyType': (getattr(company, 'type', None) or '') if company else '',
        'vendorCompanyLinked': linked,
        'canApprove': can_approve,
        'permissions': perms,
        'isSub': is_sub,
        'isArchitect': is_arch,
        'isSubVendorPayPortal': sub_vendor,
        'emailInternalOnly': bool(
            (global_flags or {}).get('email_internal_only') or sub_vendor
        ),
    }
