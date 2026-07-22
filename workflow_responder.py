"""Unified approval responder — context, permissions, and actions for RFIs, COs, etc."""
from __future__ import annotations

from datetime import datetime

import case_workflow as cw

RFI_ROLE_APPROVERS = {
    'Assignee': ('Architect', 'Admin', 'Project Manager', 'Superintendent'),
    'RFI Manager': ('Project Manager', 'Admin', 'Superintendent'),
}

ACTION_META = {
    'respond': {
        'label': 'Add Comment',
        'requires_comment': True,
        'style': 'secondary',
    },
    'submit_answer': {
        'label': 'Submit Answer',
        'requires_comment': True,
        'style': 'primary',
        'is_official': True,
    },
    'submit': {
        'label': 'Send for Review',
        'requires_comment': False,
        'style': 'primary',
    },
    'close': {
        'label': 'Close RFI',
        'requires_comment': False,
        'style': 'primary',
    },
    'return_to_assignee': {
        'label': 'Send Back for Revision',
        'requires_comment': False,
        'style': 'secondary',
    },
    'return_to_manager': {
        'label': 'Return to RFI Manager',
        'requires_comment': False,
        'style': 'secondary',
    },
    'approve': {
        'label': 'Approve',
        'requires_comment': False,
        'style': 'primary',
    },
    'reject': {
        'label': 'Reject',
        'requires_comment': True,
        'style': 'danger',
    },
}


def user_can_access_documents(user):
    if not user:
        return False
    if user.role == 'Admin':
        return True
    return cw.user_portal_type(user) == 'staff'


def rfi_deep_link(project_id, rfi_id):
    return f'/rfis?project_id={project_id}&open=1&respond=1&rfi_id={rfi_id}'


def co_deep_link(project_id, co_id):
    return f'/change-orders?project_id={project_id}&open=1&respond=1&co_id={co_id}'


def pay_app_deep_link(project_id, period_number):
    return f'/pay-applications?project_id={project_id}&open=1&respond=1&pay_entity=g702&period={period_number}'


def user_can_act_on_rfi_ball(user, role):
    if not user or not role:
        return False
    if user.role == 'Admin':
        return True
    allowed = RFI_ROLE_APPROVERS.get(role, (role,))
    return user.role in allowed


def _action_dict(action_key):
    meta = ACTION_META.get(action_key, {})
    return {
        'action': action_key,
        'label': meta.get('label', action_key.replace('_', ' ').title()),
        'requires_comment': bool(meta.get('requires_comment')),
        'style': meta.get('style', 'secondary'),
        'is_official': bool(meta.get('is_official')),
    }


def get_rfi_allowed_actions(rfi, user):
    from rfi_persistence import BALL_IN_COURT_BY_STATUS

    actions = []
    status = rfi.status or 'Open'
    ball = getattr(rfi, 'ball_in_court_role', None) or BALL_IN_COURT_BY_STATUS.get(status)
    can_act = user_can_act_on_rfi_ball(user, ball)
    is_staff = cw.user_portal_type(user) == 'staff' or user.role == 'Admin'

    if status == 'Draft' and (can_act or is_staff):
        actions.append('submit')

    if status in ('Open', 'Under Review', 'Awaiting Response') and ball == 'Assignee' and can_act:
        actions.append('submit_answer')
        actions.append('respond')

    if status == 'Answered' and ball == 'RFI Manager' and can_act:
        actions.append('close')
        actions.append('return_to_assignee')

    if is_staff and status not in ('Closed', 'Void', 'Draft'):
        if ball == 'Assignee' and 'return_to_manager' not in actions:
            actions.append('return_to_manager')
        if status not in ('Answered',) and ball == 'RFI Manager' and 'return_to_assignee' not in actions:
            if status in ('Under Review',):
                actions.append('return_to_assignee')

    seen = set()
    ordered = []
    for key in actions:
        if key not in seen:
            seen.add(key)
            ordered.append(_action_dict(key))
    return ordered


def _rfi_thread(rfi):
    from rfi_persistence import _parse_json

    thread = []
    for resp in _parse_json(getattr(rfi, 'responses_json', None), []):
        thread.append({
            'id': resp.get('id'),
            'author': resp.get('user_name', 'User'),
            'body': resp.get('body', ''),
            'is_official': bool(resp.get('is_official')),
            'created_at': resp.get('created_at', ''),
            'attachments': resp.get('attachments') or [],
        })
    return thread


def get_rfi_responder_context(rfi, user, linked_cos=None, linked_pcos=None):
    from rfi_persistence import rfi_to_dict

    data = rfi_to_dict(rfi, linked_cos, linked_pcos)
    ball = data.get('ball_in_court_role')
    return {
        'module': 'RFIs',
        'entity_type': 'RFI',
        'entity_id': rfi.id,
        'project_id': rfi.project_id,
        'title': f'{data.get("number") or "RFI"} — {data.get("subject") or ""}'.strip(' —'),
        'status': data.get('status'),
        'ball_in_court_role': ball,
        'summary': {
            'number': data.get('number'),
            'subject': data.get('subject'),
            'question': data.get('question'),
            'due_date': data.get('due_date'),
            'drawing_reference': data.get('drawing_reference'),
            'spec_reference': data.get('spec_reference'),
            'from_party': data.get('received_from_company') or data.get('from_party'),
            'assignees': data.get('assignees'),
            'rfi_manager_name': data.get('rfi_manager_name'),
            'official_answer': data.get('official_answer'),
            'priority': data.get('priority'),
            'is_overdue': data.get('is_overdue'),
        },
        'attachments': data.get('attachments') or [],
        'thread': _rfi_thread(rfi),
        'allowed_actions': get_rfi_allowed_actions(rfi, user),
        'can_act': bool(get_rfi_allowed_actions(rfi, user)),
        'can_access_documents': user_can_access_documents(user),
        'action_url': rfi_deep_link(rfi.project_id, rfi.id),
        'portal': cw.user_portal_type(user),
    }


def get_co_responder_context(co, user, allocations=None):
    from co_persistence import co_to_dict, user_can_act_on_ball_in_court, co_approvable_statuses, is_subcontract_co

    data = co_to_dict(co, allocations=allocations or [])
    ball = data.get('ball_in_court_role')
    can_act = user_can_act_on_ball_in_court(user, ball)
    actions = []
    if data.get('status') in co_approvable_statuses(co) and can_act:
        actions.append(_action_dict('approve'))
        actions.append(_action_dict('reject'))
    requires_esign = ball in ('Owner', 'Architect')
    return {
        'module': 'Change Orders',
        'entity_type': 'ChangeOrder',
        'entity_id': co.id,
        'project_id': co.project_id,
        'title': f'{data.get("number") or "CO"} — {data.get("title") or data.get("description") or ""}'.strip(' —'),
        'status': data.get('status'),
        'ball_in_court_role': ball,
        'is_subcontract': is_subcontract_co(co),
        'summary': {
            'number': data.get('number'),
            'title': data.get('title') or data.get('description'),
            'amount': data.get('amount'),
            'reason_code': data.get('reason_code'),
            'schedule_impact_days': data.get('schedule_impact_days'),
            'sub_co_kind': data.get('sub_co_kind'),
            'allocations': data.get('allocations') or [],
        },
        'attachments': data.get('attachments') or [],
        'thread': data.get('approval_history') or [],
        'allowed_actions': actions,
        'can_act': bool(actions),
        'can_access_documents': user_can_access_documents(user),
        'requires_esign': requires_esign,
        'action_url': co_deep_link(co.project_id, co.id),
        'portal': cw.user_portal_type(user),
    }


def _collect_rfi_notify_users(rfi, User, exclude_user_id=None):
    from rfi_persistence import _parse_json

    user_ids = set()
    if rfi.created_by_id:
        user_ids.add(rfi.created_by_id)
    distribution = _parse_json(getattr(rfi, 'distribution_json', None), [])
    for entry in distribution:
        if isinstance(entry, dict) and entry.get('user_id'):
            user_ids.add(int(entry['user_id']))
        elif isinstance(entry, int):
            user_ids.add(entry)
    assignees = _parse_json(getattr(rfi, 'assignees_json', None), [])
    for name in assignees:
        if isinstance(name, str):
            for u in User.query.filter_by(status='Active').all():
                full = f'{u.first_name} {u.last_name}'.strip()
                if full == name or u.email == name:
                    user_ids.add(u.id)
    ball = getattr(rfi, 'ball_in_court_role', None)
    if ball:
        for u in User.query.filter_by(status='Active').all():
            if user_can_act_on_rfi_ball(u, ball):
                user_ids.add(u.id)
    if exclude_user_id:
        user_ids.discard(exclude_user_id)
    return [User.query.get(uid) for uid in user_ids if User.query.get(uid)]


def notify_rfi_update(rfi, User, *, title, description, actor_id=None, event='update'):
    action_url = rfi_deep_link(rfi.project_id, rfi.id)
    targets = _collect_rfi_notify_users(rfi, User, exclude_user_id=actor_id)
    for u in targets:
        cw.notify_user(u.id, title, description, action_url)
        cw.create_internal_message(
            u.id,
            folder='action-required' if event in ('submit', 'ball') else 'team',
            msg_type='alert',
            subject=title,
            preview=description[:500],
            body=f'<p>{description}</p>',
            project_id=rfi.project_id,
            from_label='RFIs',
            module='RFIs',
            action_url=action_url,
            action_label='Review RFI',
            priority='high' if event == 'submit' else 'normal',
            requires_action=event in ('submit', 'ball'),
        )


def notify_rfi_ball_in_court(rfi, User, title=None, description=None):
    ball = getattr(rfi, 'ball_in_court_role', None)
    if not ball:
        return
    title = title or f'{rfi.number} — your review is needed'
    description = description or (rfi.question or rfi.subject or '')
    notify_rfi_update(rfi, User, title=title, description=description, event='ball')


def execute_rfi_action(rfi, action, user, User, body=None):
    from rfi_persistence import add_response, workflow_rfi, get_linked_records

    body = body or {}
    action = (action or '').lower()
    user_name = f'{user.first_name} {user.last_name}'.strip() or user.email
    allowed = {a['action'] for a in get_rfi_allowed_actions(rfi, user)}
    is_staff = cw.user_portal_type(user) == 'staff' or user.role == 'Admin'

    if action == 'submit_answer':
        action = 'respond'
        body = {**body, 'is_official': True}

    if action == 'respond':
        comment = (body.get('comment') or body.get('body') or '').strip()
        if not comment:
            raise ValueError('A comment is required.')
        if body.get('is_official') and 'submit_answer' not in allowed and not is_staff:
            raise ValueError('You cannot submit the official answer right now.')
        if not body.get('is_official') and 'respond' not in allowed and 'submit_answer' not in allowed:
            if not is_staff:
                raise ValueError('You cannot add comments on this RFI right now.')
        add_response(rfi, {
            'body': comment,
            'is_official': bool(body.get('is_official')),
            'attachments': body.get('attachments') or [],
        }, user.id, user_name)
        if body.get('is_official'):
            notify_rfi_update(
                rfi, User,
                title=f'{rfi.number} — official answer submitted',
                description=comment[:500],
                actor_id=user.id,
                event='ball',
            )
            notify_rfi_ball_in_court(
                rfi, User,
                title=f'{rfi.number} — review answer and close',
                description='An official answer was submitted. Please review and close the RFI when complete.',
            )
        else:
            notify_rfi_update(
                rfi, User,
                title=f'{rfi.number} — new comment',
                description=comment[:500],
                actor_id=user.id,
            )
        return 'respond'

    if action not in allowed and not (is_staff and action in (
        'submit', 'close', 'return_to_assignee', 'return_to_manager', 'reopen',
    )):
        raise ValueError('This action is not available for your role.')

    old_ball = getattr(rfi, 'ball_in_court_role', None)
    workflow_rfi(rfi, action, user_name)

    if action == 'submit':
        notify_rfi_ball_in_court(
            rfi, User,
            title=f'{rfi.number} — response needed',
            description=rfi.question or rfi.subject or 'Please review and respond to this RFI.',
        )
        notify_rfi_update(
            rfi, User,
            title=f'{rfi.number} — submitted for review',
            description='This RFI was sent for review.',
            actor_id=user.id,
            event='submit',
        )
    elif action == 'close':
        notify_rfi_update(
            rfi, User,
            title=f'{rfi.number} — closed',
            description=rfi.official_answer or 'This RFI has been closed.',
            actor_id=user.id,
        )
    elif action in ('return_to_assignee', 'return_to_manager'):
        notify_rfi_ball_in_court(rfi, User)

    if getattr(rfi, 'ball_in_court_role', None) != old_ball and action != 'submit':
        notify_rfi_ball_in_court(rfi, User)

    return action


def submittal_deep_link(project_id, submittal_id):
    return f'/submittals?project_id={project_id}&submittal_id={submittal_id}'


def _collect_submittal_notify_users(submittal, User, *, exclude_user_id=None, roles=None):
    """Notify PM, assigned contact, and role holders for ball-in-court."""
    user_ids = set()
    assigned_uid = getattr(submittal, 'assigned_contact_user_id', None)
    if assigned_uid:
        user_ids.add(int(assigned_uid))
    ball = (getattr(submittal, 'ball_in_court', None) or '').strip()
    if ball:
        try:
            from co_persistence import ROLE_APPROVERS
            for role in ROLE_APPROVERS.get(ball, ()):
                for u in User.query.filter_by(role=role, status='Active').all():
                    user_ids.add(u.id)
        except Exception:
            pass
    if exclude_user_id:
        user_ids.discard(int(exclude_user_id))
    return [User.query.get(uid) for uid in user_ids if User.query.get(uid)]


def notify_submittal_update(submittal, User, *, title, description, actor_id=None, event='update'):
    action_url = submittal_deep_link(submittal.project_id, submittal.id)
    targets = _collect_submittal_notify_users(submittal, User, exclude_user_id=actor_id)
    for u in targets:
        cw.notify_user(u.id, title, description, action_url)
        cw.create_internal_message(
            u.id,
            folder='action-required' if event in ('submit', 'ball', 'assigned') else 'team',
            msg_type='alert',
            subject=title,
            preview=description[:500],
            body=f'<p>{description}</p>',
            project_id=submittal.project_id,
            from_label='Submittals',
            module='Submittals',
            action_url=action_url,
            action_label='Open Submittal',
            priority='high' if event in ('submit', 'ball', 'assigned') else 'normal',
            requires_action=event in ('submit', 'ball', 'assigned'),
        )


def notify_submittal_ball_in_court(submittal, User, title=None, description=None):
    ball = getattr(submittal, 'ball_in_court', None)
    if not ball:
        return
    company = getattr(submittal, 'assigned_company_name', None) or ''
    title = title or f'{submittal.number} — action required ({ball})'
    description = description or (
        f'{submittal.description or "Submittal"}'
        + (f' — assigned to {company}' if company else '')
    )
    notify_submittal_update(submittal, User, title=title, description=description, event='ball')


def execute_co_action(co, action, user, User, body=None, ChangeOrderAllocation=None, workflow_deps=None):
    """Execute CO approve/reject via the unified workflow path (same as main CO API)."""
    from co_persistence import co_to_dict, user_can_act_on_ball_in_court, process_change_order_workflow

    body = body or {}
    action = (action or '').lower()
    if action not in ('approve', 'reject'):
        raise ValueError(f'Unsupported change order action: {action}')
    if not user_can_act_on_ball_in_court(user, co.ball_in_court_role):
        raise ValueError('You are not the current approver for this change order.')

    deps = workflow_deps or {}
    result = process_change_order_workflow(
        co, action, user, User, body,
        ChangeOrder=deps['ChangeOrder'],
        ChangeOrderAllocation=ChangeOrderAllocation or deps.get('ChangeOrderAllocation'),
        PayAppProjectState=deps['PayAppProjectState'],
        ScheduleData=deps['ScheduleData'],
        Project=deps['Project'],
        BudgetProjectState=deps['BudgetProjectState'],
        db=deps['db'],
        Commitment=deps['Commitment'],
        CommitmentAllocation=deps['CommitmentAllocation'],
        SageSyncEvent=deps['SageSyncEvent'],
        generate_next_number_fn=deps.get('generate_next_number_fn'),
        developer_unlock_bypass=deps.get('developer_unlock_bypass', False),
    )
    return action, co_to_dict(co, allocations=result.get('alloc_payload') or []), result


def get_pay_app_responder_context(project_id, period, user, state):
    from pay_app_workflow import get_g702_responder_context
    return get_g702_responder_context(project_id, period, user, state)


def execute_pay_app_action(project_id, period, action, user, User, body=None, workflow_deps=None):
    from pay_app_workflow import process_pay_app_workflow

    body = body or {}
    action = (action or '').lower()
    if action not in ('submit', 'approve', 'reject'):
        raise ValueError(f'Unsupported pay application action: {action}')

    deps = workflow_deps or {}
    record, state = deps.get('get_state')()
    if not state:
        state = {}
    period_num = (period or {}).get('periodNumber')
    result = process_pay_app_workflow(
        project_id,
        'g702',
        period_num,
        action,
        user,
        User,
        body,
        state,
        PayAppProjectState=deps['PayAppProjectState'],
        db=deps['db'],
        ChangeOrder=deps.get('ChangeOrder'),
        ChangeOrderAllocation=deps.get('ChangeOrderAllocation'),
        BudgetProjectState=deps.get('BudgetProjectState'),
        Commitment=deps.get('Commitment'),
        CommitmentAllocation=deps.get('CommitmentAllocation'),
        Project=deps.get('Project'),
        SageSyncEvent=deps.get('SageSyncEvent'),
    )
    from pay_app_persistence import save_pay_app_state
    save_pay_app_state(deps['PayAppProjectState'], deps['db'], project_id, result['state'], user.id)
    ctx = get_pay_app_responder_context(project_id, result['state'].get('currentPayAppPeriod'), user, result['state'])
    return action, ctx, result
