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

    assigned_email = (getattr(submittal, 'assigned_contact_email', None) or '').strip().lower()
    user_email = (getattr(user, 'email', None) or '').strip().lower()
    if assigned_email and user_email and assigned_email == user_email:
        return True

    if assigned_name and user_cname:
        if assigned_name in user_cname.lower() or user_cname.lower() in assigned_name:
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
    from submittal_persistence import submittal_is_approved_locked
    if submittal_is_approved_locked(submittal):
        raise PermissionError('This submittal is approved and locked; comments cannot be added.')
    if _is_privileged(user):
        return
    assert_submittal_read_allowed(user)
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        if not submittal_assigned_to_user(submittal, user, Company=Company, db=db):
            raise PermissionError('This submittal is not assigned to your company or contact.')


def assert_submittal_review_submission_allowed(user, submittal, *, Company=None, db=None) -> None:
    """Formal review submissions use the same visibility rules as review comments."""
    assert_submittal_comment_allowed(user, submittal, Company=Company, db=db)


def assert_rfi_comment_allowed(user, rfi) -> None:
    """Anyone who can read an RFI may post review discussion comments."""
    if _is_privileged(user):
        return
    assert_rfi_read_allowed(user)


def assert_submittal_attachment_delete_allowed(user, submittal, attachment, *, Company=None, db=None) -> None:
    """Uploader may delete their attachment; staff assignees may delete on editable submittals."""
    if _is_privileged(user):
        return
    if not attachment or not isinstance(attachment, dict):
        raise PermissionError('Attachment not found.')
    uid = getattr(user, 'id', None)
    uploaded_id = attachment.get('uploaded_by_id')
    if uploaded_id is not None and uid is not None and int(uploaded_id) == int(uid):
        return
    uploaded_name = (attachment.get('uploaded_by') or '').strip().lower()
    user_name = ''
    for part in (getattr(user, 'first_name', None), getattr(user, 'last_name', None)):
        if part:
            user_name = f'{user_name} {part}'.strip() if user_name else str(part).strip()
    if not user_name:
        user_name = (getattr(user, 'email', None) or '').strip()
    if uploaded_name and user_name and uploaded_name == user_name.lower():
        return
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        raise PermissionError('You may only remove attachments you uploaded.')
    assert_submittal_edit_allowed(user, submittal, Company=Company, db=db)


def assert_submittal_spec_book_read_allowed(user) -> None:
    """Read spec book metadata/PDF when submittals module is readable (staff entry or assigned subs)."""
    if _is_privileged(user):
        return
    assert_submittal_read_allowed(user)
    if is_sub_portal_user(user) and not is_staff_portal_user(user):
        return
    assert_submittal_log_manage_allowed(user)


def assert_submittal_signature_allowed(user, submittal, *, Company=None, db=None) -> None:
    """Anyone who can view the submittal may apply their own profile signature."""
    if _is_privileged(user):
        return
    assert_submittal_read_allowed(user)
    if not submittal_visible_to_user(submittal, user, Company=Company, db=db):
        raise PermissionError('Permission denied')


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
