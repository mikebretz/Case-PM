"""Dashboard summary — aggregates live project data for dashboard tiles."""
from __future__ import annotations

import json
from datetime import datetime, timedelta


def _project_query(model, project_id):
    q = model.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    return q


def _sum_manpower_hours(log_ids, ManpowerEntry):
    if not log_ids:
        return 0.0
    total = 0.0
    for row in ManpowerEntry.query.filter(ManpowerEntry.daily_log_id.in_(log_ids)).all():
        total += float(row.hours or 0)
    return total


def _log_manpower_count(log_id, ManpowerEntry):
    rows = ManpowerEntry.query.filter_by(daily_log_id=log_id).all()
    return sum(int(r.personnel_count or 0) for r in rows)


def build_dashboard_summary(
    project_id,
    user_id,
    *,
    Project,
    DailyLog,
    ManpowerEntry,
    RFI,
    ChangeOrder,
    PunchItem,
    Submittal,
    SafetyReport,
    ScheduleTask,
    ScheduleData,
    Commitment,
    User,
    InternalMessage=None,
    ApprovalRequest=None,
    budget_state=None,
    pay_state=None,
    forecast_summary=None,
    commitment_stats=None,
    co_stats=None,
    SageSyncEvent=None,
    PayAppProjectState=None,
):
    """Return structured payload for all dashboard tiles (real DB data only)."""
    project = Project.query.get(int(project_id)) if project_id else None
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())

    active_projects = Project.query.filter(Project.status.in_(['Active', 'Pre-Construction'])).count()
    total_projects = Project.query.count()

    rfi_q = _project_query(RFI, project_id)
    open_rfi_statuses = ('Open', 'Awaiting Response', 'Under Review')
    open_rfis = rfi_q.filter(RFI.status.in_(open_rfi_statuses)).count()
    overdue_rfis = rfi_q.filter(
        RFI.due_date < today,
        RFI.status.in_(open_rfi_statuses),
    ).count()

    co_q = _project_query(ChangeOrder, project_id)
    pending_co_statuses = ('Pending', 'Submitted', 'Pending PM', 'Pending Owner', 'Pending Accounting')
    open_cos = co_q.filter(ChangeOrder.status.in_(pending_co_statuses)).count()
    pending_co_amount = sum(
        float(c.amount or 0)
        for c in co_q.filter(ChangeOrder.status.in_(pending_co_statuses)).all()
    )

    punch_q = _project_query(PunchItem, project_id)
    open_punch = punch_q.filter(PunchItem.status != 'Completed').count()
    high_punch = punch_q.filter(PunchItem.priority == 'High', PunchItem.status != 'Completed').count()

    sub_q = _project_query(Submittal, project_id)
    open_submittals = sub_q.filter(
        ~Submittal.status.in_(('Approved', 'Closed', 'Rejected'))
    ).count()

    log_q = _project_query(DailyLog, project_id)
    recent_logs = log_q.order_by(DailyLog.date.desc()).limit(6).all()
    week_logs = log_q.filter(DailyLog.date >= week_start).all()
    week_log_ids = [l.id for l in week_logs]
    week_hours = _sum_manpower_hours(week_log_ids, ManpowerEntry)

    daily_logs = []
    for log in recent_logs:
        author = User.query.get(log.user_id) if log.user_id else None
        daily_logs.append({
            'id': log.id,
            'date': log.date.isoformat() if log.date else '',
            'work_performed': (log.work_performed or '')[:120],
            'user_name': f'{author.first_name} {author.last_name}'.strip() if author else 'Unknown',
            'manpower_count': _log_manpower_count(log.id, ManpowerEntry),
            'hours': _sum_manpower_hours([log.id], ManpowerEntry),
            'weather': log.weather or '',
        })

    task_q = _project_query(ScheduleTask, project_id)
    upcoming_tasks = task_q.filter(
        ScheduleTask.status.in_(('Not Started', 'In Progress')),
        ScheduleTask.end_date >= today,
    ).order_by(ScheduleTask.end_date.asc()).limit(8).all()
    tasks = [{
        'id': t.id,
        'description': t.description,
        'phase': t.phase or '',
        'status': t.status,
        'end_date': t.end_date.isoformat() if t.end_date else '',
        'percent_complete': t.percent_complete or 0,
    } for t in upcoming_tasks]

    safety_q = _project_query(SafetyReport, project_id)
    week_safety = safety_q.filter(SafetyReport.created_at >= datetime.combine(week_start, datetime.min.time())).all()
    incidents = sum(1 for r in week_safety if (r.type or '').lower() in ('incident', 'injury', 'recordable'))
    near_misses = sum(1 for r in week_safety if (r.type or '').lower() in ('near miss', 'near_miss', 'near-miss'))
    observations = sum(1 for r in week_safety if (r.type or '').lower() in ('observation', 'positive observation', 'safety observation'))

    assigned_items = []
    if InternalMessage is not None:
        msg_q = InternalMessage.query.filter_by(user_id=user_id, archived=False)
        if project_id:
            msg_q = msg_q.filter(
                (InternalMessage.project_id == int(project_id)) | (InternalMessage.project_id.is_(None))
            )
        messages = msg_q.order_by(InternalMessage.created_at.desc()).limit(12).all()
        for m in messages:
            if not m.requires_action and m.is_read:
                continue
            assigned_items.append({
                'id': m.id,
                'source': 'internal',
                'subject': m.subject,
                'preview': m.preview or '',
                'module': m.module or '',
                'priority': m.priority or 'normal',
                'requires_action': m.requires_action,
                'unread': not m.is_read,
                'action_url': m.action_url or '/email',
                'date': m.created_at.isoformat() if m.created_at else '',
            })

    if ApprovalRequest is not None:
        appr_q = ApprovalRequest.query.filter_by(status='pending')
        if project_id:
            appr_q = appr_q.filter_by(project_id=int(project_id))
        for a in appr_q.order_by(ApprovalRequest.created_at.desc()).limit(8).all():
            assigned_items.append({
                'id': f'approval-{a.id}',
                'source': 'approval',
                'subject': a.title,
                'preview': a.description or '',
                'module': a.module or '',
                'priority': 'high',
                'requires_action': True,
                'unread': True,
                'action_url': a.action_url or '/email',
                'date': a.created_at.isoformat() if a.created_at else '',
            })

    assigned_items.sort(key=lambda x: x.get('date') or '', reverse=True)
    assigned_items = assigned_items[:10]

    activity = []
    for rfi in rfi_q.order_by(RFI.created_at.desc()).limit(5).all():
        activity.append({
            'type': 'rfi',
            'message': f'RFI {rfi.number}: {rfi.subject}',
            'timestamp': rfi.created_at.isoformat() if rfi.created_at else '',
            'user': '',
            'url': f'/rfis?project_id={project_id}' if project_id else '/rfis',
        })
    for co in co_q.order_by(ChangeOrder.created_at.desc()).limit(5).all():
        activity.append({
            'type': 'change_order',
            'message': f'{co.number}: {co.title or co.description or "Change order"}',
            'timestamp': co.created_at.isoformat() if co.created_at else '',
            'user': '',
            'url': f'/change-orders?project_id={project_id}' if project_id else '/change-orders',
        })
    for log in log_q.order_by(DailyLog.created_at.desc()).limit(5).all():
        author = User.query.get(log.user_id) if log.user_id else None
        activity.append({
            'type': 'daily_log',
            'message': f'Daily log — {(log.work_performed or "")[:60]}',
            'timestamp': log.created_at.isoformat() if log.created_at else '',
            'user': f'{author.first_name} {author.last_name}'.strip() if author else '',
            'url': f'/daily-log?project_id={project_id}' if project_id else '/daily-log',
        })
    activity.sort(key=lambda x: x.get('timestamp') or '', reverse=True)
    activity = activity[:12]

    schedule_progress = []
    overall_pct = None
    if project_id:
        record = ScheduleData.query.filter_by(project_id=int(project_id)).first()
        if record and record.payload:
            try:
                payload = json.loads(record.payload)
                tasks_data = payload.get('data') or []
                for t in tasks_data:
                    if t.get('type') == 'project':
                        continue
                    prog = t.get('progress') or 0
                    if prog > 1:
                        prog = prog / 100.0
                    if prog <= 0 and prog != 0:
                        continue
                    text = t.get('text') or t.get('name') or 'Activity'
                    schedule_progress.append({
                        'name': text[:60],
                        'percent': round(min(100, prog * 100 if prog <= 1 else prog)),
                    })
                schedule_progress = sorted(schedule_progress, key=lambda x: -x['percent'])[:6]
                if tasks_data:
                    progs = []
                    for t in tasks_data:
                        if t.get('type') == 'project':
                            continue
                        p = t.get('progress') or 0
                        if p > 1:
                            p = p / 100.0
                        progs.append(p)
                    overall_pct = round(sum(progs) / len(progs) * 100) if progs else None
            except (TypeError, json.JSONDecodeError):
                pass
    if not schedule_progress and tasks:
        schedule_progress = [{
            'name': t['description'][:60],
            'percent': t['percent_complete'] or 0,
        } for t in tasks[:6]]

    financial = forecast_summary or {}
    commitments = commitment_stats or {}
    change_orders = co_stats or {}

    erp_pending_count = 0
    billing_variance_total = 0.0
    billing_variance_count = 0
    if project_id and SageSyncEvent is not None:
        erp_pending_count = SageSyncEvent.query.filter_by(
            project_id=int(project_id),
            accounting_status='pending_review',
        ).count()
    if project_id and PayAppProjectState is not None:
        try:
            from change_event_persistence import compute_billing_variance_for_sub_cos
            cos = ChangeOrder.query.filter_by(project_id=int(project_id)).all()
            variances = compute_billing_variance_for_sub_cos(cos, PayAppProjectState, int(project_id))
            flagged = [v for v in variances if abs(float(v.get('variance') or 0)) > 0.01]
            billing_variance_count = len(flagged)
            billing_variance_total = round(sum(float(v.get('variance') or 0) for v in flagged), 2)
        except Exception:
            pass

    location = {
        'city': getattr(project, 'city', None) or '',
        'state': getattr(project, 'state', None) or '',
        'address': getattr(project, 'address', None) or '',
        'zip_code': getattr(project, 'zip_code', None) or '',
    }
    if not location['city'] and location['address']:
        parts = [p.strip() for p in location['address'].split(',')]
        if len(parts) >= 2:
            location['city'] = parts[-2]
            location['state'] = parts[-1][:2].strip()

    return {
        'project': {
            'id': project.id if project else None,
            'name': project.name if project else None,
            'number': project.number if project else None,
            'status': project.status if project else None,
        },
        'location': location,
        'kpis': {
            'active_projects': active_projects,
            'total_projects': total_projects,
            'open_rfis': open_rfis,
            'overdue_rfis': overdue_rfis,
            'open_change_orders': open_cos,
            'pending_co_amount': round(pending_co_amount, 2),
            'open_punch_items': open_punch,
            'high_priority_punch': high_punch,
            'open_submittals': open_submittals,
            'week_hours': round(week_hours, 1),
            'overall_progress': overall_pct,
        },
        'daily_logs': daily_logs,
        'open_items': {
            'rfis_awaiting': open_rfis,
            'overdue_rfis': overdue_rfis,
            'change_orders_pending': open_cos,
            'pending_co_amount': round(pending_co_amount, 2),
            'high_priority_punch': high_punch,
            'open_punch': open_punch,
            'open_submittals': open_submittals,
        },
        'upcoming_tasks': tasks,
        'schedule_progress': schedule_progress,
        'safety': {
            'incidents': incidents,
            'near_misses': near_misses,
            'observations': observations,
            'week_reports': len(week_safety),
        },
        'assigned_items': assigned_items,
        'recent_activity': activity,
        'financial': {
            'contract_amount': financial.get('contract_amount'),
            'original_budget': financial.get('original_budget'),
            'revised_budget': financial.get('revised_budget'),
            'actual_cost': financial.get('actual_cost'),
            'variance': financial.get('variance'),
            'committed': financial.get('committed'),
            'pct_complete': financial.get('percent_complete'),
            'paid_out': financial.get('paid_out'),
        },
        'forecast_chart': {
            'monthly_trends': financial.get('monthly_trends') or [],
            'categories': financial.get('categories') or [],
        },
        'commitments': commitments,
        'change_orders': change_orders,
        'erp_queue': {
            'pending_review_count': erp_pending_count,
        },
        'billing_variance': {
            'flagged_count': billing_variance_count,
            'total_variance': billing_variance_total,
        },
    }


def get_accessible_projects(Project, user, ProjectMembership=None):
    """Projects the user may view on the portfolio dashboard."""
    if getattr(user, 'role', None) == 'Admin':
        return Project.query.order_by(Project.name).all()

    allowed_ids = set()
    if ProjectMembership is not None:
        for row in ProjectMembership.query.filter_by(user_id=user.id).all():
            allowed_ids.add(int(row.project_id))

    company_id = getattr(user, 'company_id', None)
    if company_id:
        for p in Project.query.filter_by(client_company_id=company_id).all():
            allowed_ids.add(int(p.id))

    if allowed_ids:
        return Project.query.filter(Project.id.in_(sorted(allowed_ids))).order_by(Project.name).all()

    return Project.query.order_by(Project.name).all()


def _schedule_pct_from_payload(payload):
    tasks_data = payload.get('data') or []
    progs = []
    for t in tasks_data:
        if t.get('type') == 'project':
            continue
        p = t.get('progress') or 0
        if p > 1:
            p = p / 100.0
        progs.append(p)
    return round(sum(progs) / len(progs) * 100) if progs else None


def build_project_snapshot(
    project,
    *,
    RFI,
    ChangeOrder,
    PotentialChangeOrder,
    PunchItem,
    Submittal,
    ScheduleData,
    budget_state=None,
    forecast_summary=None,
    co_stats=None,
    rfi_stats=None,
):
    """Lightweight per-project metrics for the all-projects dashboard."""
    pid = int(project.id)
    today = datetime.utcnow().date()

    if rfi_stats is None:
        open_rfi_statuses = ('Open', 'Awaiting Response', 'Under Review')
        rfis = RFI.query.filter_by(project_id=pid).all()
        open_rfis = sum(1 for r in rfis if r.status in open_rfi_statuses)
        overdue_rfis = sum(
            1 for r in rfis
            if r.status in open_rfi_statuses and r.due_date and r.due_date < today
        )
        rfi_stats = {'open': open_rfis, 'overdue': overdue_rfis, 'total': len(rfis)}

    if co_stats is None:
        from co_persistence import compute_dashboard_stats
        co_stats = compute_dashboard_stats(ChangeOrder, PotentialChangeOrder, pid)

    open_punch = PunchItem.query.filter(
        PunchItem.project_id == pid,
        PunchItem.status != 'Completed',
    ).count()
    open_submittals = Submittal.query.filter(
        Submittal.project_id == pid,
        ~Submittal.status.in_(('Approved', 'Closed', 'Rejected')),
    ).count()

    schedule_pct = None
    record = ScheduleData.query.filter_by(project_id=pid).first()
    if record and record.payload:
        try:
            schedule_pct = _schedule_pct_from_payload(json.loads(record.payload))
        except (TypeError, json.JSONDecodeError):
            pass
    if schedule_pct is None and getattr(project, 'percent_complete', None) is not None:
        schedule_pct = int(project.percent_complete)

    financial = forecast_summary or {}
    start = getattr(project, 'start_date', None)
    end = getattr(project, 'end_date', None)
    year = None
    if start:
        year = start.year
    elif getattr(project, 'created_at', None):
        year = project.created_at.year

    return {
        'id': pid,
        'number': project.number or '',
        'name': project.name or '',
        'status': project.status or '',
        'location': project.location_label() if hasattr(project, 'location_label') else '',
        'client': project.client or '',
        'project_manager': project.project_manager or '',
        'year': year,
        'start_date': start.isoformat() if start else None,
        'end_date': end.isoformat() if end else None,
        'schedule_pct': schedule_pct,
        'rfis': {
            'open': rfi_stats.get('open', 0),
            'overdue': rfi_stats.get('overdue', 0),
            'total': rfi_stats.get('total', 0),
        },
        'change_orders': {
            'approved_count': co_stats.get('approved_count', 0),
            'approved_total': round(float(co_stats.get('approved_total') or 0), 2),
            'pending_count': co_stats.get('pending_count', 0),
            'pending_total': round(float(co_stats.get('pending_total') or 0), 2),
            'open_pco_count': co_stats.get('open_pco_count', 0),
            'pco_rom_total': round(float(co_stats.get('pco_rom_total') or 0), 2),
        },
        'open_punch': open_punch,
        'open_submittals': open_submittals,
        'financial': {
            'contract_amount': financial.get('contract_amount'),
            'original_budget': financial.get('original_budget'),
            'revised_budget': financial.get('revised_budget'),
            'actual_cost': financial.get('actual_cost'),
            'variance': financial.get('variance'),
            'forecast_to_complete': financial.get('forecast_to_complete'),
            'estimated_cost_at_completion': financial.get('estimated_cost_at_completion'),
            'projected_over_under': financial.get('projected_over_under'),
            'pct_complete': financial.get('percent_complete'),
            'pct_complete_cost': financial.get('percent_complete_cost'),
            'paid_out': financial.get('paid_out'),
            'pending_changes': financial.get('pending_changes'),
        },
    }


def build_portfolio_dashboard(
    user,
    *,
    Project,
    RFI,
    ChangeOrder,
    PotentialChangeOrder,
    PunchItem,
    Submittal,
    ScheduleData,
    BudgetProjectState,
    PayAppProjectState,
    ProjectMembership=None,
    approved_co_fn=None,
    get_budget_state=None,
    get_pay_app_state=None,
    build_forecast_summary=None,
    compute_rfi_dashboard=None,
    compute_co_dashboard=None,
):
    """Aggregate snapshot cards for all projects the user can access."""
    projects = get_accessible_projects(Project, user, ProjectMembership)
    snapshots = []

    for project in projects:
        pid = int(project.id)
        budget_state = {}
        pay_state = {}
        forecast_summary = {}
        if get_budget_state and BudgetProjectState is not None:
            _, budget_state = get_budget_state(BudgetProjectState, pid)
        if get_pay_app_state and PayAppProjectState is not None:
            _, pay_state = get_pay_app_state(PayAppProjectState, pid)
        approved_co = approved_co_fn(pid) if approved_co_fn else 0.0
        if build_forecast_summary:
            forecast_summary = build_forecast_summary(project, budget_state, pay_state, approved_co)
        rfi_stats = compute_rfi_dashboard(RFI, pid) if compute_rfi_dashboard else None
        co_stats = compute_co_dashboard(ChangeOrder, PotentialChangeOrder, pid) if compute_co_dashboard else None

        snapshots.append(build_project_snapshot(
            project,
            RFI=RFI,
            ChangeOrder=ChangeOrder,
            PotentialChangeOrder=PotentialChangeOrder,
            PunchItem=PunchItem,
            Submittal=Submittal,
            ScheduleData=ScheduleData,
            budget_state=budget_state,
            forecast_summary=forecast_summary,
            co_stats=co_stats,
            rfi_stats=rfi_stats,
        ))

    active_statuses = {'Active', 'Pre-Construction'}
    return {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'accessible_count': len(snapshots),
        'active_count': sum(1 for p in projects if (p.status or '') in active_statuses),
        'projects': snapshots,
    }
