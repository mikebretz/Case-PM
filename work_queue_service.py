"""Unified cross-module work queue — items awaiting the current user's action."""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import or_

PENDING_CO_STATUSES = (
    'Submitted', 'Under Review', 'Pending', 'Pending PM',
    'Pending Owner', 'Pending Architect', 'Pending Accounting',
)
OPEN_RFI_STATUSES = ('Open', 'Awaiting Response', 'Under Review', 'Draft')
OPEN_SUBMITTAL_STATUSES = (
    'Open', 'Submitted', 'In Review', 'Pending', 'Revise and Resubmit',
    'Under Review', 'Pending Architect', 'Pending Contractor',
)
PAY_APP_ACTION_STATUSES = (
    'Submitted', 'Pending PM', 'Pending Owner', 'Pending Accounting', 'Under Review',
)


def _iso(dt):
    if not dt:
        return ''
    if isinstance(dt, datetime):
        return dt.isoformat() + ('Z' if dt.tzinfo is None else '')
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _sort_key(item: dict) -> tuple:
    overdue = 1 if item.get('overdue') else 0
    priority = {'critical': 3, 'high': 2, 'normal': 1, 'low': 0}.get(item.get('priority') or 'normal', 1)
    due = item.get('due_date') or '9999-99-99'
    updated = item.get('sort_date') or ''
    return (-overdue, -priority, due, updated)


def _project_ids_for_user(user, Project) -> set[int] | None:
    """None means all projects (staff without strict membership)."""
    try:
        from project_access import enforcement_enabled, get_assigned_project_ids, user_bypasses_project_scope
        if user_bypasses_project_scope(user):
            return None
        if not enforcement_enabled():
            return None
        return get_assigned_project_ids(user, Project=Project)
    except Exception:
        return None


def _allowed_project_filter(q, model, project_ids):
    if project_ids is None:
        return q
    if not project_ids:
        return q.filter(False)
    return q.filter(model.project_id.in_(list(project_ids)))


def build_my_work_queue(
    user,
    *,
    project_id: int | None = None,
    limit: int = 50,
    models: dict | None = None,
) -> dict:
    """
    Aggregate actionable items across RFIs, submittals, COs, PCOs, pay apps,
    approvals, and internal messages for the signed-in user.
    """
    if models is None:
        import app as app_module
        models = {
            'Project': app_module.Project,
            'RFI': app_module.RFI,
            'Submittal': app_module.Submittal,
            'ChangeOrder': app_module.ChangeOrder,
            'PotentialChangeOrder': app_module.PotentialChangeOrder,
            'PayAppProjectState': app_module.PayAppProjectState,
        }

    Project = models['Project']
    RFI = models['RFI']
    Submittal = models['Submittal']
    ChangeOrder = models['ChangeOrder']
    PotentialChangeOrder = models.get('PotentialChangeOrder')
    PayAppProjectState = models.get('PayAppProjectState')

    uid = getattr(user, 'id', None)
    role = (getattr(user, 'role', None) or '').strip()
    today = datetime.utcnow().date()
    items: list[dict] = []

    scope_ids = _project_ids_for_user(user, Project)
    if project_id:
        pid = int(project_id)
        # Explicit project filter from UI/API — allow even when membership set is empty.
        if scope_ids is not None and len(scope_ids) > 0 and pid not in scope_ids:
            return {'ok': True, 'items': [], 'counts': {}, 'project_id': pid}
        scope_ids = {pid}

    project_names: dict[int, str] = {}

    try:
        from co_persistence import user_can_act_on_ball_in_court
    except Exception:
        def user_can_act_on_ball_in_court(u, r):  # noqa: ARG001
            return False

    try:
        from case_workflow import user_can_approve, ApprovalRequest, InternalMessage
    except Exception:
        user_can_approve = lambda u, m, a='approve': False  # noqa: E731
        ApprovalRequest = None
        InternalMessage = None

    def add_item(**kwargs):
        items.append(kwargs)

    def project_name(pid) -> str:
        if not pid:
            return ''
        key = int(pid)
        if key not in project_names:
            project_names[key] = _project_name(Project, key)
        return project_names[key]

    # --- Internal messages (indexed filter — avoid full mailbox scan) ---
    if InternalMessage is not None and uid:
        msg_q = InternalMessage.query.filter(
            InternalMessage.user_id == uid,
            InternalMessage.archived.is_(False),
            or_(InternalMessage.requires_action.is_(True), InternalMessage.is_read.is_(False)),
        )
        if scope_ids is not None:
            msg_q = msg_q.filter(
                (InternalMessage.project_id.in_(list(scope_ids))) | (InternalMessage.project_id.is_(None))
            )
        for m in msg_q.order_by(InternalMessage.created_at.desc()).limit(30).all():
            add_item(
                kind='message',
                source='internal',
                id=f'msg-{m.id}',
                title=m.subject or 'Message',
                subtitle=m.module or m.preview or '',
                project_id=m.project_id,
                project_name=project_name(m.project_id),
                priority='high' if m.requires_action else 'normal',
                overdue=False,
                due_date='',
                sort_date=_iso(m.created_at),
                action_url=m.action_url or '/email?tab=internal',
                can_act=True,
            )

    # --- Approval requests ---
    if ApprovalRequest is not None:
        appr_q = ApprovalRequest.query.filter_by(status='pending')
        if scope_ids is not None:
            appr_q = appr_q.filter(ApprovalRequest.project_id.in_(list(scope_ids)))
        for a in appr_q.order_by(ApprovalRequest.created_at.desc()).limit(40).all():
            mod = a.module or ''
            if not user_can_approve(user, mod):
                continue
            add_item(
                kind='approval',
                source='approval',
                id=f'approval-{a.id}',
                title=a.title or 'Approval required',
                subtitle=mod.replace('_', ' ').title(),
                project_id=a.project_id,
                project_name=project_name(a.project_id),
                priority='high',
                overdue=False,
                due_date='',
                sort_date=_iso(a.created_at),
                action_url=a.action_url or '/email?tab=internal',
                can_act=True,
            )

    # --- RFIs ---
    if RFI is not None and uid:
        rfi_q = RFI.query.filter(RFI.status.in_(OPEN_RFI_STATUSES))
        rfi_q = _allowed_project_filter(rfi_q, RFI, scope_ids)
        for rfi in rfi_q.limit(200).all():
            ball_uid = getattr(rfi, 'ball_in_court_user_id', None)
            ball_role = getattr(rfi, 'ball_in_court_role', None)
            assigned = ball_uid is not None and int(ball_uid) == int(uid)
            role_act = user_can_act_on_ball_in_court(user, ball_role) if ball_role else False
            if not assigned and not role_act:
                continue
            due = _as_date(getattr(rfi, 'due_date', None))
            overdue = bool(due and due < today and rfi.status in OPEN_RFI_STATUSES)
            pid = rfi.project_id
            add_item(
                kind='rfi',
                source='rfi',
                id=f'rfi-{rfi.id}',
                title=f'RFI {rfi.number}: {rfi.subject or ""}'.strip(),
                subtitle=rfi.status or '',
                project_id=pid,
                project_name=project_name(pid),
                priority='high' if overdue else 'normal',
                overdue=overdue,
                due_date=_iso(due)[:10] if due else '',
                sort_date=_iso(getattr(rfi, 'updated_at', None) or rfi.created_at),
                action_url=f'/rfis?project_id={pid}&open={rfi.id}' if pid else f'/rfis?open={rfi.id}',
                can_act=True,
            )

    # --- Submittals ---
    if Submittal is not None:
        sub_q = Submittal.query.filter(~Submittal.status.in_(('Approved', 'Closed', 'Rejected', 'No Exceptions Taken')))
        sub_q = _allowed_project_filter(sub_q, Submittal, scope_ids)
        try:
            from document_module_security import submittal_assigned_to_user
        except Exception:
            submittal_assigned_to_user = lambda s, u, **k: False  # noqa: E731
        for sub in sub_q.limit(200).all():
            ball = getattr(sub, 'ball_in_court', None) or getattr(sub, 'ball_in_court_role', None)
            role_act = user_can_act_on_ball_in_court(user, ball) if ball else False
            assigned = submittal_assigned_to_user(sub, user)
            if not role_act and not assigned:
                continue
            pid = sub.project_id
            add_item(
                kind='submittal',
                source='submittal',
                id=f'sub-{sub.id}',
                title=f'Submittal {sub.number or sub.id}: {(sub.description or "")[:80]}'.strip(),
                subtitle=sub.status or '',
                project_id=pid,
                project_name=project_name(pid),
                priority='normal',
                overdue=False,
                due_date='',
                sort_date=_iso(getattr(sub, 'updated_at', None) or sub.created_at),
                action_url=f'/submittals?project_id={pid}&open={sub.id}' if pid else f'/submittals?open={sub.id}',
                can_act=True,
            )

    # --- Change orders ---
    if ChangeOrder is not None:
        co_q = ChangeOrder.query.filter(ChangeOrder.status.in_(PENDING_CO_STATUSES))
        co_q = _allowed_project_filter(co_q, ChangeOrder, scope_ids)
        for co in co_q.limit(150).all():
            ball = getattr(co, 'ball_in_court_role', None)
            if not ball or not user_can_act_on_ball_in_court(user, ball):
                continue
            pid = co.project_id
            add_item(
                kind='change_order',
                source='change_order',
                id=f'co-{co.id}',
                title=f'{co.number}: {co.title or co.description or "Change order"}'[:120],
                subtitle=f'{co.status} · Ball: {ball}',
                project_id=pid,
                project_name=project_name(pid),
                priority='high',
                overdue=False,
                due_date='',
                sort_date=_iso(getattr(co, 'updated_at', None) or co.created_at),
                action_url=f'/change-orders?project_id={pid}&open=1&co_id={co.id}',
                can_act=True,
            )

    # --- PCOs ---
    if PotentialChangeOrder is not None:
        pco_q = PotentialChangeOrder.query.filter(
            ~PotentialChangeOrder.status.in_(('Approved', 'Rejected', 'Void', 'Closed'))
        )
        pco_q = _allowed_project_filter(pco_q, PotentialChangeOrder, scope_ids)
        for pco in pco_q.limit(100).all():
            ball = getattr(pco, 'ball_in_court_role', None) or 'Project Manager'
            if not user_can_act_on_ball_in_court(user, ball):
                continue
            pid = pco.project_id
            add_item(
                kind='pco',
                source='change_order',
                id=f'pco-{pco.id}',
                title=f'PCO {pco.number or pco.id}: {pco.title or pco.description or ""}'[:120],
                subtitle=f'{pco.status} · Ball: {ball}',
                project_id=pid,
                project_name=project_name(pid),
                priority='normal',
                overdue=False,
                due_date='',
                sort_date=_iso(getattr(pco, 'updated_at', None) or pco.created_at),
                action_url=f'/change-orders?project_id={pid}&tab=pco&open={pco.id}',
                can_act=True,
            )

    # --- Pay application periods (G702 workflow) ---
    if PayAppProjectState is not None:
        pa_q = PayAppProjectState.query
        if scope_ids is not None:
            pa_q = pa_q.filter(PayAppProjectState.project_id.in_(list(scope_ids)))
        for row in pa_q.limit(80).all():
            state = _parse_json(getattr(row, 'data_json', None) or getattr(row, 'state_json', None))
            periods = state.get('periods') or state.get('payPeriods') or []
            if isinstance(periods, dict):
                periods = list(periods.values())
            for per in periods:
                if not isinstance(per, dict):
                    continue
                st = (per.get('status') or '').strip()
                if st not in PAY_APP_ACTION_STATUSES:
                    continue
                ball = per.get('ball_in_court_role') or per.get('ballInCourtRole') or _pay_app_ball_for_status(st)
                if not user_can_act_on_ball_in_court(user, ball):
                    continue
                period_num = per.get('period') or per.get('periodNumber') or per.get('number') or '?'
                pid = row.project_id
                add_item(
                    kind='pay_application',
                    source='pay_application',
                    id=f'pay-{pid}-{period_num}',
                    title=f'Pay App period {period_num} — {st}',
                    subtitle='G702 / G703 workflow',
                    project_id=pid,
                    project_name=project_name(pid),
                    priority='high' if st in ('Pending Owner', 'Pending Accounting') else 'normal',
                    overdue=False,
                    due_date='',
                    sort_date=_iso(per.get('updated_at') or per.get('submitted_at')),
                    action_url=f'/pay-applications?project_id={pid}&period={period_num}',
                    can_act=True,
                )

    items.sort(key=_sort_key)
    items = items[: max(1, min(int(limit or 50), 200))]

    counts: dict[str, int] = {}
    for it in items:
        k = it.get('kind') or 'other'
        counts[k] = counts.get(k, 0) + 1

    return {
        'ok': True,
        'items': items,
        'counts': counts,
        'total': len(items),
        'project_id': int(project_id) if project_id else None,
    }


def _project_name(Project, project_id) -> str:
    if not project_id or Project is None:
        return ''
    try:
        p = Project.query.get(int(project_id))
        return (p.name or '') if p else ''
    except Exception:
        return ''


def _parse_json(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _pay_app_ball_for_status(status: str) -> str:
    mapping = {
        'Submitted': 'Project Manager',
        'Pending PM': 'Project Manager',
        'Pending Owner': 'Owner',
        'Pending Accounting': 'Contractor Accounting',
        'Under Review': 'Project Manager',
    }
    return mapping.get(status, 'Project Manager')
