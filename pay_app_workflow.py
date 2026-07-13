"""Unified pay application workflow — G702, sub pay apps, and sub SOV setup."""
from __future__ import annotations

import json
from datetime import datetime

from co_persistence import OWNER_CO_APPROVAL_THRESHOLD, user_can_act_on_ball_in_court

G702_STATUSES = (
    'Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Accounting',
    'Approved', 'Rejected', 'Void',
)
G702_BALL_IN_COURT = {
    'Draft': 'Creator',
    'Submitted': 'Project Manager',
    'Under Review': 'Project Manager',
    'Pending Owner': 'Owner',
    'Pending Accounting': 'Contractor Accounting',
    'Approved': None,
    'Rejected': None,
    'Void': None,
}
G702_APPROVAL_CHAIN = (
    {'from_status': 'Submitted', 'role': 'Project Manager', 'next_status': 'Pending Owner'},
    {'from_status': 'Under Review', 'role': 'Project Manager', 'next_status': 'Pending Owner'},
    {'from_status': 'Pending Owner', 'role': 'Owner', 'next_status': 'Pending Accounting'},
    {'from_status': 'Pending Accounting', 'role': 'Contractor Accounting', 'next_status': 'Approved'},
)

SUB_PAY_APP_STATUSES = ('Draft', 'Pending Approval', 'Approved', 'Rejected', 'Void')
SUB_PAY_APP_BALL = {
    'Draft': 'Subcontractor',
    'Pending Approval': 'Project Manager',
    'Approved': None,
    'Rejected': 'Subcontractor',
}

SUB_SOV_STATUSES = ('Draft', 'Pending Approval', 'Approved', 'Rejected', 'Void')
SUB_SOV_BALL = {
    'Draft': 'Subcontractor',
    'Pending Approval': 'Project Manager',
    'Approved': None,
    'Rejected': 'Subcontractor',
}


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return default


def append_pay_app_approval_history(state, entity_type, entity_key, action, user, comment='', old_status='', new_status=''):
    hist = state.get('_payAppWorkflowHistory') or []
    name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip() or getattr(user, 'email', 'User')
    hist.append({
        'entity_type': entity_type,
        'entity_key': str(entity_key),
        'action': action,
        'user_id': getattr(user, 'id', None),
        'user_name': name,
        'comment': comment,
        'old_status': old_status,
        'new_status': new_status,
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    state['_payAppWorkflowHistory'] = hist[-200:]
    audit = state.get('payAppAuditLog') or []
    audit.append({
        'event': f'{entity_type.upper()}_{action.upper()}',
        'entity_key': str(entity_key),
        'user': name,
        'user_id': getattr(user, 'id', None),
        'at': datetime.utcnow().isoformat() + 'Z',
        'details': {'old_status': old_status, 'new_status': new_status, 'comment': comment},
    })
    state['payAppAuditLog'] = audit[-500:]
    return state


def pay_app_deep_link(project_id, entity_type='g702', entity_key=None):
    base = f'/pay-applications?project_id={project_id}'
    if entity_type == 'g702' and entity_key is not None:
        return f'{base}&open=1&respond=1&pay_entity=g702&period={entity_key}'
    if entity_type == 'sub_pay_app' and entity_key:
        return f'{base}&tab=sub-pay-app-tracker&company_id={entity_key}'
    if entity_type == 'sub_sov' and entity_key:
        return f'{base}&tab=sub-sov&company_id={entity_key}'
    return base


def notify_pay_app_ball(project_id, role, *, title, description, entity_type, entity_key, User=None):
    if not role or not User:
        return
    action_url = pay_app_deep_link(project_id, entity_type, entity_key)
    try:
        from email_notifications import notify_role_workflow
        notify_role_workflow(
            User, role,
            title=title,
            description=description,
            action_url=action_url,
            project_id=project_id,
            module='Pay Applications',
            can_act_fn=user_can_act_on_ball_in_court,
        )
    except Exception:
        pass


def _g702_amount_from_state(state, body):
    body = body or {}
    if body.get('amount_due') is not None:
        return float(body.get('amount_due') or 0)
    rollup = body.get('rollup') or {}
    grand = rollup.get('grand') or {}
    try:
        return float(grand.get('thisPeriod') or 0) + float(grand.get('materials') or 0) + float(grand.get('changeOrders', {}).get('thisPeriod') or 0) - float(grand.get('retainage') or 0)
    except (TypeError, ValueError):
        return 0.0


def g702_workflow_action(period, action, user, amount=0):
    action = (action or '').lower()
    if action == 'submit':
        if (period.get('status') or 'Draft') != 'Draft':
            raise ValueError('Only draft pay applications can be submitted')
        period['status'] = 'Submitted'
        period['submitted_at'] = datetime.utcnow().isoformat() + 'Z'
        period['ball_in_court_role'] = G702_BALL_IN_COURT['Submitted']
        return period['status'], False
    if action == 'reject':
        role = period.get('ball_in_court_role') or 'Project Manager'
        if not user_can_act_on_ball_in_court(user, role) and user.role not in ('Admin', 'Developer'):
            raise ValueError(f'Cannot reject while ball is with {role}')
        period['status'] = 'Draft'
        period['ball_in_court_role'] = G702_BALL_IN_COURT['Draft']
        period.pop('submitted_at', None)
        return period['status'], False
    if action == 'approve':
        role = period.get('ball_in_court_role') or 'Project Manager'
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Cannot approve while ball is with {role}')
        status = period.get('status') or 'Submitted'
        for step in G702_APPROVAL_CHAIN:
            if step['from_status'] == status and step['role'] == role:
                next_status = step['next_status']
                if next_status == 'Pending Owner' and amount < OWNER_CO_APPROVAL_THRESHOLD:
                    next_status = 'Pending Accounting'
                if next_status == 'Pending Accounting' and amount < OWNER_CO_APPROVAL_THRESHOLD:
                    next_status = 'Approved'
                period['status'] = next_status
                period['ball_in_court_role'] = G702_BALL_IN_COURT.get(next_status)
                if next_status == 'Approved':
                    period['approved_at'] = datetime.utcnow().isoformat() + 'Z'
                    period['approved_by_id'] = getattr(user, 'id', None)
                    period['ball_in_court_role'] = None
                    return period['status'], True
                return period['status'], False
        raise ValueError('No approval step for current pay application status')
    raise ValueError('action must be submit, approve, or reject')


def _resolve_sub_sov_status(state, company_key):
    sub_sov_status = state.get('subSOVStatus') or {}
    key = str(company_key)
    entry = sub_sov_status.get(key) or sub_sov_status.get(company_key)
    if isinstance(entry, str):
        entry = {'status': entry}
    if not isinstance(entry, dict):
        entry = {'status': 'Draft'}
    return sub_sov_status, key, entry


def sub_sov_workflow_action(state, company_key, action, user):
    action = (action or '').lower()
    sub_sov_status, key, entry = _resolve_sub_sov_status(state, company_key)
    status = entry.get('status') or 'Draft'
    if action == 'submit':
        if status not in ('Draft', 'Rejected'):
            raise ValueError('Sub SOV can only be submitted from Draft or Rejected')
        entry['status'] = 'Pending Approval'
        entry['ball_in_court_role'] = SUB_SOV_BALL['Pending Approval']
        entry['submitted_at'] = datetime.utcnow().isoformat() + 'Z'
        sub_sov_status[key] = entry
        state['subSOVStatus'] = sub_sov_status
        return entry['status'], False
    if action == 'reject':
        if not user_can_act_on_ball_in_court(user, 'Project Manager'):
            raise ValueError('Only Project Manager can reject sub SOV setup')
        entry['status'] = 'Rejected'
        entry['ball_in_court_role'] = SUB_SOV_BALL['Rejected']
        sub_sov_status[key] = entry
        state['subSOVStatus'] = sub_sov_status
        return entry['status'], False
    if action == 'approve':
        if status != 'Pending Approval':
            raise ValueError('Sub SOV is not pending approval')
        if not user_can_act_on_ball_in_court(user, 'Project Manager'):
            raise ValueError('Only Project Manager can approve sub SOV setup')
        entry['status'] = 'Approved'
        entry['ball_in_court_role'] = None
        entry['approved_at'] = datetime.utcnow().isoformat() + 'Z'
        entry['approved_by_id'] = getattr(user, 'id', None)
        sub_sov_status[key] = entry
        state['subSOVStatus'] = sub_sov_status
        return entry['status'], True
    raise ValueError('action must be submit, approve, or reject')


def sub_pay_app_workflow_action(state, company_key, action, user, body=None):
    action = (action or '').lower()
    body = body or {}
    cid = str(company_key)
    pending = (state.get('subPendingSubmissions') or {}).get(cid) or (state.get('subPendingSubmissions') or {}).get(company_key)
    history = state.get('subPayAppHistory') or {}
    company_hist = history.get(cid) or history.get(company_key) or {}

    if action == 'submit':
        if not pending and not body.get('pending_entry'):
            raise ValueError('No pending sub pay app submission found')
        if body.get('pending_entry'):
            pend = state.setdefault('subPendingSubmissions', {})
            pend[cid] = body['pending_entry']
            state['subPendingSubmissions'] = pend
            hist_key = body.get('history_key') or str(body['pending_entry'].get('periodNumber', ''))
            if hist_key:
                ch = history.setdefault(cid, {})
                ch[hist_key] = body.get('history_entry') or {
                    **body['pending_entry'],
                    'status': 'Pending Approval',
                    'ball_in_court_role': 'Project Manager',
                }
                history[cid] = ch
                state['subPayAppHistory'] = history
        else:
            pending['ball_in_court_role'] = 'Project Manager'
        return 'Pending Approval', False

    if action == 'reject':
        if not user_can_act_on_ball_in_court(user, 'Project Manager'):
            raise ValueError('Only Project Manager can request revision on sub pay apps')
        pend = state.get('subPendingSubmissions') or {}
        pend.pop(cid, None)
        pend.pop(str(company_key), None)
        state['subPendingSubmissions'] = pend
        for hk, ent in list(company_hist.items()):
            if (ent or {}).get('status') == 'Pending Approval':
                ent['status'] = 'Rejected'
                ent['ball_in_court_role'] = 'Subcontractor'
                company_hist[hk] = ent
        history[cid] = company_hist
        state['subPayAppHistory'] = history
        return 'Rejected', False

    if action == 'approve':
        if not user_can_act_on_ball_in_court(user, 'Project Manager'):
            raise ValueError('Only Project Manager can approve sub pay apps')
        entry = pending or body.get('pending_entry')
        if not entry:
            raise ValueError('No sub pay app pending approval')
        hist_key = body.get('history_key')
        if hist_key and hist_key in company_hist:
            company_hist[hist_key]['status'] = 'Approved'
            company_hist[hist_key]['ball_in_court_role'] = None
            company_hist[hist_key]['approved_at'] = datetime.utcnow().isoformat() + 'Z'
        history[cid] = company_hist
        state['subPayAppHistory'] = history
        pend = state.get('subPendingSubmissions') or {}
        pend.pop(cid, None)
        state['subPendingSubmissions'] = pend
        return 'Approved', True

    raise ValueError('action must be submit, approve, or reject')


def run_pay_app_accounting_sync(
    project_id,
    user_id,
    *,
    event_type,
    message,
    payload,
    ChangeOrder,
    ChangeOrderAllocation,
    PayAppProjectState,
    BudgetProjectState,
    Commitment,
    CommitmentAllocation,
    Project,
    SageSyncEvent,
    db,
):
    """Reconcile accounting then queue Sage event (accounting review before post)."""
    result = {'reconcile_result': None, 'sage_event': None, 'errors': []}
    try:
        from accounting_reconcile import reconcile_project_accounting
        recon = reconcile_project_accounting(
            project_id,
            user_id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=PayAppProjectState,
            db=db,
        )
        result['reconcile_result'] = recon
    except Exception as exc:
        result['errors'].append({'target': 'reconcile', 'error': str(exc)})

    if SageSyncEvent is not None and event_type:
        try:
            from sage_service import create_and_process_sage_event
            pl = dict(payload or {})
            pl['sync'] = result.get('reconcile_result')
            pl['idempotency_key'] = pl.get('idempotency_key') or f'{event_type}:{project_id}:{pl.get("periodNumber") or pl.get("companyId")}:{datetime.utcnow().strftime("%Y%m")}'
            ev = create_and_process_sage_event(
                SageSyncEvent,
                Project,
                db,
                project_id,
                event_type,
                message=message,
                payload=pl,
                user_id=user_id,
                Commitment=Commitment,
            )
            result['sage_event'] = {'id': ev.id, 'status': ev.status, 'accounting_status': getattr(ev, 'accounting_status', None)}
        except Exception as exc:
            result['errors'].append({'target': 'sage', 'error': str(exc)})
    return result


def _sync_approval_request(project_id, entity_type, entity_id, user, action, title=None, description=None):
    try:
        import case_workflow as cw
        from case_workflow import ApprovalRequest, decide_approval
        pending = ApprovalRequest.query.filter_by(
            entity_type=entity_type,
            entity_id=str(entity_id),
            status='pending',
        ).order_by(ApprovalRequest.created_at.desc()).first()
        if action in ('approve', 'reject') and pending:
            decision = 'reject' if action == 'reject' else 'approve'
            decide_approval(pending.id, decision, '')
        elif action == 'submit':
            cw.create_approval(
                project_id=project_id,
                module='Pay Applications',
                entity_type=entity_type,
                entity_id=str(entity_id),
                title=title or 'Pay application submitted',
                description=description or '',
                action_url=pay_app_deep_link(project_id, entity_type.lower(), entity_id),
            )
    except Exception:
        pass


def process_pay_app_workflow(
    project_id,
    entity_type,
    entity_key,
    action,
    user,
    User,
    body,
    state,
    *,
    PayAppProjectState,
    db,
    ChangeOrder=None,
    ChangeOrderAllocation=None,
    BudgetProjectState=None,
    Commitment=None,
    CommitmentAllocation=None,
    Project=None,
    SageSyncEvent=None,
):
    """Unified pay app workflow for API + approval responder."""
    body = body or {}
    action = (action or '').lower()
    if action not in ('submit', 'approve', 'reject'):
        raise ValueError('action must be submit, approve, or reject')
    comments = (body.get('comments') or body.get('comment') or '').strip()
    if action == 'reject' and not comments:
        raise ValueError('Rejection requires a comment')

    entity_type = (entity_type or '').lower()
    state = dict(state or {})
    final_approved = False
    new_status = None
    sage_result = None

    if entity_type in ('g702', 'g702_period', 'pay_app'):
        period = dict(state.get('currentPayAppPeriod') or {})
        if entity_key and str(period.get('periodNumber')) != str(entity_key):
            raise ValueError('Pay application period mismatch')
        old_status = period.get('status') or 'Draft'
        amount = _g702_amount_from_state(state, body)
        new_status, final_approved = g702_workflow_action(period, action, user, amount=amount)
        state['currentPayAppPeriod'] = period
        append_pay_app_approval_history(
            state, 'g702', period.get('periodNumber'), action, user, comments, old_status, new_status,
        )
        entity_id = period.get('periodNumber')

        if action == 'submit':
            run_pay_app_accounting_sync(
                project_id, user.id,
                event_type='G702Submitted',
                message=f'G702 period {entity_id} submitted',
                payload={'periodNumber': entity_id, 'amount': amount, **(body.get('payload') or {})},
                ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState, BudgetProjectState=BudgetProjectState,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                Project=Project, SageSyncEvent=SageSyncEvent, db=db,
            )
            _sync_approval_request(
                project_id, 'G702', entity_id, user, 'submit',
                title=f'Pay Application #{entity_id} submitted',
                description=f'GC pay application period {entity_id} requires review.',
            )
            notify_pay_app_ball(
                project_id, period.get('ball_in_court_role'),
                title=f'G702 #{entity_id} — review required',
                description='A pay application was submitted for your review.',
                entity_type='g702', entity_key=entity_id, User=User,
            )
        elif action == 'approve' and final_approved:
            if body.get('state_patch') and isinstance(body['state_patch'], dict):
                for k, v in body['state_patch'].items():
                    state[k] = v
            sage_result = run_pay_app_accounting_sync(
                project_id, user.id,
                event_type='G702Approved',
                message=f'G702 period {entity_id} approved — accounting reconciled',
                payload={
                    'periodNumber': entity_id,
                    'amount': amount,
                    'grandTotal': (body.get('rollup') or {}).get('grand', {}).get('completed'),
                    'amountDue': amount,
                    **(body.get('payload') or {}),
                },
                ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState, BudgetProjectState=BudgetProjectState,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                Project=Project, SageSyncEvent=SageSyncEvent, db=db,
            )
            _sync_approval_request(project_id, 'G702', entity_id, user, 'approve')
        elif action == 'approve' and not final_approved:
            _sync_approval_request(project_id, 'G702', entity_id, user, 'submit',
                title=f'G702 #{entity_id} — {new_status}',
                description=f'Pay application advanced to {new_status}.',
            )
            notify_pay_app_ball(
                project_id, period.get('ball_in_court_role'),
                title=f'G702 #{entity_id} — your review is needed',
                description=f'Pay application is now {new_status}.',
                entity_type='g702', entity_key=entity_id, User=User,
            )
        elif action == 'reject':
            _sync_approval_request(project_id, 'G702', entity_id, user, 'reject')
            notify_pay_app_ball(
                project_id, 'Creator',
                title=f'G702 #{entity_id} — revision requested',
                description=comments or 'Please revise and resubmit.',
                entity_type='g702', entity_key=entity_id, User=User,
            )

    elif entity_type in ('sub_pay_app', 'subpayapp'):
        company_key = str(entity_key or body.get('company_id') or '')
        if not company_key:
            raise ValueError('company_id required for sub pay app workflow')
        old = 'Pending Approval' if action == 'approve' else (body.get('pending_entry') or {}).get('status', 'Draft')
        new_status, final_approved = sub_pay_app_workflow_action(state, company_key, action, user, body)
        append_pay_app_approval_history(state, 'sub_pay_app', company_key, action, user, comments, old, new_status)
        period_num = (body.get('pending_entry') or body.get('payload') or {}).get('periodNumber')
        if action == 'submit':
            total = (body.get('pending_entry') or {}).get('totalBilledThisPeriod', 0)
            run_pay_app_accounting_sync(
                project_id, user.id,
                event_type='SubPayAppSubmitted',
                message=f'Sub pay app submitted — company {company_key}',
                payload={'companyId': company_key, 'periodNumber': period_num, 'total': total},
                ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState, BudgetProjectState=BudgetProjectState,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                Project=Project, SageSyncEvent=SageSyncEvent, db=db,
            )
            notify_pay_app_ball(project_id, 'Project Manager',
                title=f'Sub pay app submitted — {company_key}',
                description='Subcontractor pay application requires PM approval.',
                entity_type='sub_pay_app', entity_key=company_key, User=User)
        elif action == 'approve' and final_approved:
            total = (body.get('pending_entry') or {}).get('totalBilledThisPeriod', 0)
            sage_result = run_pay_app_accounting_sync(
                project_id, user.id,
                event_type='SubPayAppApproved',
                message=f'Sub pay app approved — company {company_key}',
                payload={'companyId': company_key, 'periodNumber': period_num, 'total': total},
                ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState, BudgetProjectState=BudgetProjectState,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                Project=Project, SageSyncEvent=SageSyncEvent, db=db,
            )
        elif action == 'reject':
            notify_pay_app_ball(project_id, 'Subcontractor',
                title=f'Sub pay app revision requested',
                description=comments,
                entity_type='sub_pay_app', entity_key=company_key, User=User)

    elif entity_type in ('sub_sov', 'subsov'):
        company_key = str(entity_key or body.get('company_id') or '')
        if not company_key:
            raise ValueError('company_id required for sub SOV workflow')
        _, _, entry = _resolve_sub_sov_status(state, company_key)
        old_status = entry.get('status') or 'Draft'
        new_status, final_approved = sub_sov_workflow_action(state, company_key, action, user)
        append_pay_app_approval_history(state, 'sub_sov', company_key, action, user, comments, old_status, new_status)
        if action == 'submit':
            notify_pay_app_ball(project_id, 'Project Manager',
                title=f'Sub SOV submitted — {company_key}',
                description='Subcontractor SOV setup requires PM approval.',
                entity_type='sub_sov', entity_key=company_key, User=User)
        elif action == 'reject':
            notify_pay_app_ball(project_id, 'Subcontractor',
                title='Sub SOV revision requested',
                description=comments,
                entity_type='sub_sov', entity_key=company_key, User=User)
    else:
        raise ValueError(f'Unsupported entity_type: {entity_type}')

    return {
        'new_status': new_status,
        'final_approved': final_approved,
        'state': state,
        'sage_result': sage_result,
        'ball_in_court_role': (
            (state.get('currentPayAppPeriod') or {}).get('ball_in_court_role')
            if entity_type.startswith('g702') or entity_type == 'pay_app'
            else None
        ),
    }


def get_g702_responder_context(project_id, period, user, state):
    period = period or {}
    ball = period.get('ball_in_court_role')
    status = period.get('status') or 'Draft'
    can_act = user_can_act_on_ball_in_court(user, ball) if ball else False
    actions = []
    approvable = ('Submitted', 'Under Review', 'Pending Owner', 'Pending Accounting')
    if status in approvable and can_act:
        actions.append({'action': 'approve', 'label': 'Approve', 'requires_comment': False, 'style': 'primary'})
        actions.append({'action': 'reject', 'label': 'Request Revision', 'requires_comment': True, 'style': 'danger'})
    if status == 'Draft' and (user.role in ('Admin', 'Project Manager') or can_act):
        actions.append({'action': 'submit', 'label': 'Submit for Review', 'requires_comment': False, 'style': 'primary'})
    return {
        'module': 'Pay Applications',
        'entity_type': 'G702',
        'entity_id': period.get('periodNumber'),
        'project_id': project_id,
        'title': f'Pay Application #{period.get("periodNumber")} — Period {period.get("periodStart", "")} to {period.get("periodEnd", "")}',
        'status': status,
        'ball_in_court_role': ball,
        'summary': {
            'period_number': period.get('periodNumber'),
            'period_start': period.get('periodStart'),
            'period_end': period.get('periodEnd'),
            'amount_due': period.get('amount_due'),
        },
        'allowed_actions': actions,
        'can_act': bool([a for a in actions if a['action'] in ('approve', 'reject', 'submit')]),
        'action_url': pay_app_deep_link(project_id, 'g702', period.get('periodNumber')),
        'thread': (state or {}).get('_payAppWorkflowHistory') or [],
    }
