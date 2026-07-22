"""RFI and submittal permission enforcement — view vs entry vs edit, sub assignment."""
from __future__ import annotations


def _is_privileged(user) -> bool:
    try:
        from access_control import user_is_privileged
        return user_is_privileged(user)
    except Exception:
        return getattr(user, 'role', None) in ('Admin', 'Developer')


def _has_module(user, module: str, min_access: str = 'view') -> bool:
    try:
        from case_workflow import user_has_module_access
        return user_has_module_access(user, module, min_access)
    except Exception:
        return False


def require_module_access(user, module: str, min_access: str = 'view') -> None:
    if _is_privileged(user):
        return
    if not _has_module(user, module, min_access):
        raise PermissionError(
            f'Permission denied — {module.replace("_", " ")} requires {min_access} access.'
        )


def is_sub_portal_user(user) -> bool:
    try:
        from case_workflow import is_sub_user
        return bool(is_sub_user(user))
    except Exception:
        return (getattr(user, 'role', None) or '') in (
            'Subcontractor', 'Subcontractor Accountant', 'Subcontractor Contact', 'Company User',
        )


def is_staff_portal_user(user) -> bool:
    try:
        from case_workflow import user_portal_type
        return user_portal_type(user) == 'staff' or getattr(user, 'role', None) == 'Admin'
    except Exception:
        return not is_sub_portal_user(user)


def resolve_user_vendor_company(user, Company=None, db=None):
    """Return (company_id, company_name) for a sub/vendor user."""
    try:
        from portal_sub_access import resolve_sub_vendor_company
        cid, cname, _ = resolve_sub_vendor_company(user, Company, db, persist_link=False)
        if cid or cname:
            return cid, (cname or '').strip()
    except Exception:
        pass
    cid = getattr(user, 'company_id', None)
    cname = (getattr(user, 'company', None) or '').strip()
    return cid, cname


def submittal_assigned_to_user(submittal, user, Company=None, db=None) -> bool:
    """True when the submittal is assigned to this user or their vendor company."""
    if not submittal or not user:
        return False
    uid = getattr(user, 'id', None)
    assigned_uid = getattr(submittal, 'assigned_contact_user_id', None)
    if assigned_uid is not None and uid is not None and int(assigned_uid) == int(uid):
        return True

    assigned_cid = getattr(submittal, 'assigned_company_id', None)
    user_cid, user_cname = resolve_user_vendor_company(user, Company=Company, db=db)
    if assigned_cid is not None and user_cid is not None and int(assigned_cid) == int(user_cid):
        return True

    assigned_name = (getattr(submittal, 'assigned_company_name', None) or '').strip().lower()
    if assigned_name and user_cname and assigned_name == user_cname.lower():
        return True
    return False


def submittal_visible_to_user(submittal, user, Company=None, db=None) -> bool:
    """Staff see all readable submittals; subs/vendors only see items assigned to them."""
    if _is_privileged(user):
        return True
    try:
        assert_submittal_read_allowed(user)
    except PermissionError:
        return False
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        return submittal_assigned_to_user(submittal, user, Company=Company, db=db)
    return True


def assert_rfi_read_allowed(user) -> None:
    require_module_access(user, 'rfis', 'view')


def assert_rfi_create_allowed(user) -> None:
    require_module_access(user, 'rfis', 'entry')


def assert_rfi_edit_allowed(user) -> None:
    require_module_access(user, 'rfis', 'edit')


def assert_rfi_workflow_allowed(user) -> None:
    require_module_access(user, 'rfis', 'entry')


def assert_submittal_read_allowed(user) -> None:
    require_module_access(user, 'submittals', 'view')


def assert_submittal_log_manage_allowed(user) -> None:
    """Spec book upload, Excel import, and spec section management require entry access."""
    require_module_access(user, 'submittals', 'entry')


def assert_submittal_create_allowed(user) -> None:
    """Creating log items is a PM/staff capability."""
    if _is_privileged(user):
        return
    if is_sub_portal_user(user) and not _has_module(user, 'submittals', 'edit'):
        raise PermissionError('Subcontractors cannot create new submittal log items.')
    require_module_access(user, 'submittals', 'entry')


def assert_submittal_edit_allowed(user, submittal=None, *, Company=None, db=None) -> None:
    if _is_privileged(user):
        return
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        if submittal is None:
            raise PermissionError('Submittal record required for permission check.')
        if not _has_module(user, 'submittals', 'view'):
            raise PermissionError('Permission denied — submittals requires view access.')
        if not submittal_assigned_to_user(submittal, user, Company=Company, db=db):
            raise PermissionError('This submittal is not assigned to your company or contact.')
        status = (getattr(submittal, 'status', None) or '').strip()
        if status not in ('Draft', 'Sent to Subcontractor', 'Revise & Resubmit'):
            raise PermissionError(
                'You may only update submittals while they are assigned to you for submission.'
            )
        return
    if not _has_module(user, 'submittals', 'edit') and not _has_module(user, 'submittals', 'entry'):
        raise PermissionError('Permission denied — submittals requires entry access.')


def assert_submittal_comment_allowed(user, submittal, *, Company=None, db=None) -> None:
    """Anyone who can read a visible submittal may post review comments."""
    if _is_privileged(user):
        return
    assert_submittal_read_allowed(user)
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        if not submittal_assigned_to_user(submittal, user, Company=Company, db=db):
            raise PermissionError('This submittal is not assigned to your company or contact.')


def assert_submittal_spec_book_read_allowed(user) -> None:
    """Read spec book metadata/PDF when submittals module is readable (staff entry or assigned subs)."""
    if _is_privileged(user):
        return
    assert_submittal_read_allowed(user)
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        return
    assert_submittal_log_manage_allowed(user)


def assert_submittal_workflow_allowed(user, submittal, action: str, *, Company=None, db=None) -> None:
    if _is_privileged(user):
        return
    action = (action or '').lower()
    if action in ('return_from_sub',) and is_sub_portal_user(user) and not is_staff_portal_user(user):
        if submittal is None:
            raise PermissionError('Submittal record required for permission check.')
        assert_submittal_read_allowed(user)
        if not submittal_assigned_to_user(submittal, user, Company=Company, db=db):
            raise PermissionError('This submittal is not assigned to your company or contact.')
        status = (getattr(submittal, 'status', None) or '').strip()
        if status not in ('Draft', 'Sent to Subcontractor', 'Revise & Resubmit'):
            raise PermissionError('This submittal is not awaiting your submission.')
        return
    require_module_access(user, 'submittals', 'entry')
