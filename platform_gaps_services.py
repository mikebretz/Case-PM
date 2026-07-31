"""Platform gap features — transmittals, job cost, payroll, client portal, integrations, AI."""
from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime

from budget_persistence import get_budget_state, save_budget_state, _find_budget_line, normalize_cost_code
from extended_platform_persistence import _parse_json, serialize_record
from transmittal_pdf import build_transmittal_pdf
from wh347_pdf import build_wh347_pdf, parse_workers, validate_prevailing_wage


def _record_fields(row):
    simple = _parse_json(row.simple_fields_json) or {}
    advanced = _parse_json(row.advanced_fields_json) or {}
    return simple, advanced


def _notify(user_id, title, message, link=None):
    try:
        import case_workflow as cw
        cw.notify_user(user_id, title, message, link)
        cw._workflow_session().commit()
    except Exception:
        pass


def _notify_project_team(project_id, User, title, message, link=None, exclude_user_id=None):
    if not project_id or not User:
        return
    try:
        from app import ProjectMembership
        members = ProjectMembership.query.filter_by(project_id=int(project_id)).all()
        for m in members:
            if exclude_user_id and m.user_id == exclude_user_id:
                continue
            _notify(m.user_id, title, message, link)
    except Exception:
        pass


def _parse_distribution_list(advanced, simple):
    raw = advanced.get('distribution_list') or advanced.get('cc_party') or simple.get('to_party') or ''
    recipients = []
    for part in re.split(r'[;,\n]+', str(raw)):
        part = part.strip()
        if not part:
            continue
        if '<' in part and '>' in part:
            name, email = part.split('<', 1)
            recipients.append({'name': name.strip(), 'email': email.rstrip('>').strip()})
        elif '@' in part:
            recipients.append({'name': part.split('@')[0], 'email': part})
        else:
            recipients.append({'name': part, 'email': ''})
    to_party = simple.get('to_party') or ''
    if to_party and not any(r['name'] == to_party for r in recipients):
        if '@' in to_party:
            recipients.insert(0, {'name': to_party.split('@')[0], 'email': to_party})
        else:
            recipients.insert(0, {'name': to_party, 'email': ''})
    return recipients


def send_transmittal(db, row, Project, User, OperationsTransmittalRecipient, user_id):
    """Distribute transmittal, generate PDF package, notify recipients."""
    simple, advanced = _record_fields(row)
    project = Project.query.get(row.project_id) if row.project_id else None
    dist = _parse_distribution_list(advanced, simple)
    if not dist:
        raise ValueError('Add recipients in Distribution List (advanced) or To field.')

    OperationsTransmittalRecipient.query.filter_by(transmittal_record_id=row.id).delete()
    created = []
    for r in dist:
        token = secrets.token_urlsafe(24)
        rec = OperationsTransmittalRecipient(
            transmittal_record_id=row.id,
            name=r.get('name') or 'Recipient',
            email=r.get('email') or '',
            status='Sent',
            ack_token=token,
            sent_at=datetime.utcnow(),
        )
        db.session.add(rec)
        created.append(rec)

    row.status = 'Sent'
    pdf_data = build_transmittal_pdf(
        {**simple, **advanced, 'id': row.id, 'title': row.title},
        project,
        [{'name': r.name, 'email': r.email, 'status': r.status} for r in created],
    )

    # Email distribution
    ack_base = '/api/operations/transmittals/ack/'
    for rec in created:
        link = f'/operations?module=transmittals&id={row.id}'
        if rec.email:
            try:
                from email_notifications import send_workflow_email
                ack_url = f'{ack_base}{rec.ack_token}'
                send_workflow_email(
                    rec.email,
                    f'Transmittal: {row.title}',
                    f'<p>You have received transmittal <strong>{row.title}</strong>.</p>'
                    f'<p><a href="{ack_url}">Acknowledge receipt</a></p>',
                    f'Transmittal: {row.title}. Acknowledge: {ack_url}',
                )
            except Exception:
                pass
        if User and rec.email:
            u = User.query.filter(User.email.ilike(rec.email)).first()
            if u:
                _notify(u.id, f'Transmittal: {row.title}', 'Please review and acknowledge.', link)

    db.session.commit()
    return {
        'recipient_count': len(created),
        'pdf_bytes': len(pdf_data),
        'message': f'Transmittal sent to {len(created)} recipient(s).',
    }


def acknowledge_transmittal(db, OperationsTransmittalRecipient, ExtendedModuleRecord, token):
    rec = OperationsTransmittalRecipient.query.filter_by(ack_token=token).first()
    if not rec:
        raise ValueError('Invalid acknowledgment link.')
    rec.status = 'Acknowledged'
    rec.acknowledged_at = datetime.utcnow()
    row = ExtendedModuleRecord.query.get(rec.transmittal_record_id)
    if row:
        pending = OperationsTransmittalRecipient.query.filter_by(
            transmittal_record_id=row.id
        ).filter(OperationsTransmittalRecipient.status != 'Acknowledged').count()
        if pending == 0:
            row.status = 'Acknowledged'
    db.session.commit()
    return {'ok': True, 'transmittal_id': rec.transmittal_record_id}


def get_transmittal_recipients(OperationsTransmittalRecipient, record_id):
    rows = OperationsTransmittalRecipient.query.filter_by(transmittal_record_id=record_id).all()
    return [{
        'id': r.id, 'name': r.name, 'email': r.email, 'status': r.status,
        'sent_at': r.sent_at.isoformat() if r.sent_at else None,
        'acknowledged_at': r.acknowledged_at.isoformat() if r.acknowledged_at else None,
    } for r in rows]


def build_transmittal_pdf_for_record(row, Project, OperationsTransmittalRecipient):
    simple, advanced = _record_fields(row)
    project = Project.query.get(row.project_id) if row.project_id else None
    recs = get_transmittal_recipients(OperationsTransmittalRecipient, row.id)
    return build_transmittal_pdf({**simple, **advanced, 'id': row.id, 'title': row.title}, project, recs)


def apply_cost_to_budget(db, BudgetProjectState, project_id, cost_code, amount, cost_type, user_id, source_ref):
    """Increment budget line actual cost."""
    if not project_id or not amount:
        return None
    _, state = get_budget_state(BudgetProjectState, project_id)
    if not state:
        state = {'budgetLines': []}
    lines = state.get('budgetLines') or []
    code = (cost_code or '01-0000').strip()
    line = _find_budget_line(lines, code, cost_type)
    if not line:
        line = {
            'id': int(datetime.utcnow().timestamp() * 1000),
            'cost_code': code,
            'description': f'Job cost — {source_ref}',
            'cost_type': cost_type or 'Labor',
            'original_budget': 0,
            'approved_changes': 0,
            'pending': 0,
            'actual': 0,
            'syncStatus': 'Pending',
            'percent_complete': 0,
            'notes': source_ref,
        }
        lines.append(line)
    line['actual'] = float(line.get('actual') or 0) + float(amount)
    line['actual_source'] = source_ref
    state['budgetLines'] = lines
    save_budget_state(BudgetProjectState, db, project_id, state, user_id)
    return line


def post_timesheet_to_job_cost(db, row, BudgetProjectState, SageSyncEvent, Project, user_id):
    """Post approved timesheet hours/cost to budget actuals and queue Sage event."""
    if row.status == 'Posted':
        raise ValueError('Timesheet already posted.')
    simple, advanced = _record_fields(row)
    hours = float(simple.get('total_hours') or row.amount or 0)
    hourly_rate = float(advanced.get('hourly_rate') or simple.get('hourly_rate') or 0)
    if not hourly_rate and hours:
        hourly_rate = float(row.amount or 0) / hours if row.amount else 55.0
    labor_cost = hours * hourly_rate if hours else float(row.amount or 0)
    cost_code = advanced.get('cost_code') or '01-0000'
    if not row.project_id:
        raise ValueError('Timesheet must be linked to a project.')
    if labor_cost <= 0:
        raise ValueError('Enter total hours and hourly rate (advanced) before posting.')

    apply_cost_to_budget(
        db, BudgetProjectState, row.project_id, cost_code, labor_cost,
        'Labor', user_id, f'Timesheet #{row.number or row.id}',
    )
    row.status = 'Posted'
    row.amount = labor_cost
    db.session.flush()

    import app as app_mod
    from accounting_posting import process_construction_event

    gl_out = process_construction_event(
        'TimesheetPosted',
        int(row.project_id),
        {
            'amount': labor_cost,
            'labor_cost': labor_cost,
            'cost_code': cost_code,
            'timesheet_id': row.id,
            'timesheet_ref': f'Timesheet #{row.number or row.id}',
            'idempotency_key': f'timesheet-{row.id}',
            'force_builtin_post': True,
        },
        db=db,
        models=app_mod._acct_models,
        user_id=user_id,
        Project=Project,
    )
    if not gl_out.get('posted') and gl_out.get('skipped') not in ('already_posted',):
        raise ValueError(
            f'Accounting G/L post failed for timesheet: {gl_out.get("skipped") or gl_out}',
        )

    if SageSyncEvent and Project:
        from sage_service import create_and_process_sage_event
        create_and_process_sage_event(
            SageSyncEvent, Project, db, row.project_id,
            'TimesheetPosted',
            message=f'Timesheet {row.number or row.id} posted — ${labor_cost:,.2f} to {cost_code}',
            payload={
                'timesheet_id': row.id,
                'cost_code': cost_code,
                'hours': hours,
                'amount': labor_cost,
                'idempotency_key': f'timesheet-{row.id}',
            },
            user_id=user_id,
        )
    db.session.commit()
    return {'amount': labor_cost, 'cost_code': cost_code, 'hours': hours, 'message': f'Posted ${labor_cost:,.2f} to job cost.'}


def post_direct_cost_to_job_cost(db, row, BudgetProjectState, SageSyncEvent, Project, user_id):
    if row.status == 'Posted':
        raise ValueError('Direct cost already posted.')
    simple, advanced = _record_fields(row)
    amount = float(simple.get('amount') or row.amount or 0)
    cost_code = advanced.get('cost_code') or '01-0000'
    cost_type = advanced.get('cost_type') or 'Other'
    if not row.project_id or amount <= 0:
        raise ValueError('Project and amount required.')
    apply_cost_to_budget(
        db, BudgetProjectState, row.project_id, cost_code, amount,
        cost_type, user_id, f'Direct cost #{row.number or row.id}',
    )
    row.status = 'Posted'
    db.session.flush()

    import app as app_mod
    from accounting_posting import process_construction_event

    gl_out = process_construction_event(
        'DirectCostPosted',
        int(row.project_id),
        {
            'amount': amount,
            'cost_code': cost_code,
            'cost_type': cost_type,
            'direct_cost_id': row.id,
            'idempotency_key': f'direct-cost-{row.id}',
            'force_builtin_post': True,
        },
        db=db,
        models=app_mod._acct_models,
        user_id=user_id,
        Project=Project,
    )
    if not gl_out.get('posted') and gl_out.get('skipped') not in ('already_posted',):
        raise ValueError(
            f'Accounting G/L post failed for direct cost: {gl_out.get("skipped") or gl_out}',
        )

    if SageSyncEvent and Project:
        from sage_service import create_and_process_sage_event
        create_and_process_sage_event(
            SageSyncEvent, Project, db, row.project_id,
            'DirectCostPosted',
            message=f'Direct cost {row.number or row.id} — ${amount:,.2f}',
            payload={'direct_cost_id': row.id, 'cost_code': cost_code, 'amount': amount,
                     'idempotency_key': f'direct-cost-{row.id}'},
            user_id=user_id,
        )
    db.session.commit()
    return {'amount': amount, 'cost_code': cost_code, 'message': f'Posted ${amount:,.2f} to job cost.'}


def generate_certified_payroll(db, row, Project):
    simple, advanced = _record_fields(row)
    project = Project.query.get(row.project_id) if row.project_id else None
    workers = parse_workers(advanced.get('workers_json'))
    project_rate = None
    if project and project.details_json:
        try:
            project_rate = json.loads(project.details_json).get('prevailing_wage_rate')
        except (TypeError, json.JSONDecodeError):
            pass
    pdf_bytes, violations = build_wh347_pdf(
        {'simple': simple, 'advanced': advanced, 'title': row.title,
         'record_date': row.record_date.isoformat() if row.record_date else None,
         'number': row.number},
        project, workers,
    )
    return pdf_bytes, violations


def file_certified_payroll(db, row, Project, user_id):
    pdf_bytes, violations = generate_certified_payroll(db, row, Project)
    if violations:
        raise ValueError(f'Prevailing wage violations: {len(violations)} worker(s) below required rate.')
    row.status = 'Filed'
    db.session.commit()
    _notify_project_team(
        row.project_id, None, 'Certified payroll filed',
        f'WH-347 {row.title} filed for week ending {row.record_date}.',
        f'/operations?module=certified_payroll&id={row.id}',
        exclude_user_id=user_id,
    )
    return {'message': 'Certified payroll filed. WH-347 compliance passed.', 'violations': []}


def build_client_portal_feed(db, models, user, project_id=None):
    """Aggregate pending approvals and shared documents for owner portal."""
    ClientPortalApproval = models['ClientPortalApproval']
    Project = models['Project']
    RFI = models.get('RFI')
    ExtendedModuleRecord = models['ExtendedModuleRecord']

    pid = project_id
    if not pid:
        try:
            from app import get_current_project_id
            pid = get_current_project_id()
        except Exception:
            pass

    approvals = []
    q = ClientPortalApproval.query.filter_by(status='Pending')
    if pid:
        q = q.filter_by(project_id=int(pid))
    if user:
        q = q.filter(
            (ClientPortalApproval.assigned_user_id == user.id) |
            (ClientPortalApproval.assigned_user_id.is_(None))
        )
    for a in q.order_by(ClientPortalApproval.created_at.desc()).limit(50):
        approvals.append({
            'id': a.id, 'item_type': a.item_type, 'item_id': a.item_id,
            'title': a.title, 'description': a.description,
            'action_url': a.action_url, 'status': a.status,
            'created_at': a.created_at.isoformat() if a.created_at else None,
        })

    # Auto-sync open RFIs/submittals visible to client
    if RFI and pid:
        for r in RFI.query.filter_by(project_id=int(pid)).filter(
            RFI.status.in_(['Open', 'Pending', 'Under Review'])
        ).limit(20):
            if not ClientPortalApproval.query.filter_by(
                item_type='rfi', item_id=r.id, project_id=int(pid)
            ).first():
                approvals.append({
                    'id': None, 'item_type': 'rfi', 'item_id': r.id,
                    'title': f'RFI {r.number}: {r.subject}',
                    'description': (r.question or '')[:200],
                    'action_url': f'/rfis?project_id={pid}&rfi_id={r.id}',
                    'status': 'Pending', 'auto': True,
                })

    portal_items = []
    if pid:
        for item in ExtendedModuleRecord.query.filter_by(
            module_key='client_portal_items', project_id=int(pid)
        ).filter(ExtendedModuleRecord.status.in_(['Published', 'Open', 'Pending'])).limit(30):
            adv = _parse_json(item.advanced_fields_json) or {}
            if adv.get('client_visible') in (True, 'true', 'yes', '1', 1):
                portal_items.append(serialize_record(item))

    projects = []
    if Project:
        pq = Project.query
        if pid:
            pq = pq.filter_by(id=int(pid))
        for p in pq.limit(10):
            projects.append({'id': p.id, 'name': p.name, 'number': p.number, 'status': p.status})

    return {'approvals': approvals, 'portal_items': portal_items, 'projects': projects}


def respond_client_portal(db, ClientPortalApproval, approval_id, user, response, decision):
    row = ClientPortalApproval.query.get_or_404(approval_id)
    if row.assigned_user_id and row.assigned_user_id != user.id:
        raise ValueError('This approval is assigned to another user.')
    row.client_response = response
    row.status = decision or 'Responded'
    row.responded_at = datetime.utcnow()
    db.session.commit()
    if row.created_by_id:
        _notify(row.created_by_id, f'Client response: {row.title}', response or decision, row.action_url)
    return {'ok': True, 'status': row.status}


def create_client_portal_approval(db, ClientPortalApproval, project_id, item_type, item_id,
                                  title, description, action_url, user_id, assign_user_id=None):
    existing = ClientPortalApproval.query.filter_by(
        project_id=project_id, item_type=item_type, item_id=item_id, status='Pending'
    ).first()
    if existing:
        return existing
    row = ClientPortalApproval(
        project_id=project_id,
        item_type=item_type,
        item_id=item_id,
        title=title,
        description=description,
        action_url=action_url,
        assigned_user_id=assign_user_id,
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    if assign_user_id:
        _notify(assign_user_id, f'Approval needed: {title}', description or '', action_url)
    return row


def sync_integration(db, IntegrationSyncLog, integration, project_id, user_id, models):
    """Push/pull Sage or Procore entities."""
    integration = (integration or '').lower()
    logs = []
    if integration == 'sage':
        logs.extend(_sync_sage(db, IntegrationSyncLog, project_id, user_id, models))
    elif integration == 'procore':
        logs.extend(_sync_procore(db, IntegrationSyncLog, project_id, user_id, models))
    else:
        raise ValueError('integration must be sage or procore')
    db.session.commit()
    return {'logs': logs, 'count': len(logs)}


def _log_sync(db, IntegrationSyncLog, integration, direction, entity_type, entity_id,
              project_id, status, message, payload=None, response=None, user_id=None):
    row = IntegrationSyncLog(
        integration=integration,
        direction=direction,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        status=status,
        message=message,
        payload_json=json.dumps(payload) if payload else None,
        response_json=json.dumps(response) if response else None,
        created_by_id=user_id,
    )
    db.session.add(row)
    return {
        'integration': integration, 'entity_type': entity_type, 'status': status, 'message': message,
    }


def _sync_sage(db, IntegrationSyncLog, project_id, user_id, models):
    from sage_service import apply_sage_pull_to_project, create_and_process_sage_event
    Project = models['Project']
    SageSyncEvent = models.get('SageSyncEvent')
    BudgetProjectState = models.get('BudgetProjectState')
    logs = []
    if not project_id:
        raise ValueError('Select a project for Sage sync.')
    try:
        result = apply_sage_pull_to_project(
            project_id,
            Project=Project,
            Commitment=models.get('Commitment'),
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=models.get('PayAppProjectState'),
            db=db,
            user_id=user_id,
            SageSyncEvent=SageSyncEvent,
        )
        lines = result.get('budget_lines_updated') or result.get('lines_updated') or 0
        logs.append(_log_sync(db, IntegrationSyncLog, 'sage', 'pull', 'job_ledger', project_id,
                              project_id, 'posted' if result.get('ok') else 'error',
                              result.get('message') or f'Pulled ledger — {lines} lines', result, result, user_id))
    except Exception as exc:
        logs.append(_log_sync(db, IntegrationSyncLog, 'sage', 'pull', 'job_ledger', project_id,
                              project_id, 'error', str(exc), user_id=user_id))
    if SageSyncEvent:
        ev = create_and_process_sage_event(
            SageSyncEvent, Project, db, project_id, 'ManualSync',
            message='Operations Center manual Sage sync',
            payload={'source': 'platform_gaps', 'idempotency_key': f'manual-sync-{uuid.uuid4().hex[:8]}'},
            user_id=user_id,
        )
        logs.append(_log_sync(db, IntegrationSyncLog, 'sage', 'push', 'manual_sync', ev.id if ev else None,
                              project_id, 'posted', 'Manual sync event queued', user_id=user_id))
    return logs


def _sync_procore(db, IntegrationSyncLog, project_id, user_id, models):
    import os
    import urllib.error
    import urllib.request

    Project = models['Project']
    RFI = models.get('RFI')
    logs = []
    api_url = (os.environ.get('PROCORE_API_URL') or '').rstrip('/')
    api_token = os.environ.get('PROCORE_API_TOKEN') or ''
    company_id = os.environ.get('PROCORE_COMPANY_ID') or ''
    project = Project.query.get(project_id) if project_id else None
    if not project:
        raise ValueError('Project required for Procore sync.')

    procore_project_id = None
    if project.details_json:
        try:
            procore_project_id = json.loads(project.details_json).get('procore_project_id')
        except (TypeError, json.JSONDecodeError):
            pass

    if api_url and api_token and procore_project_id:
        headers = {'Authorization': f'Bearer {api_token}', 'Content-Type': 'application/json'}
        try:
            req = urllib.request.Request(
                f'{api_url}/rest/v1.0/projects/{procore_project_id}/rfis',
                headers=headers,
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            imported = 0
            if RFI and isinstance(data, list):
                for item in data[:25]:
                    num = item.get('number') or item.get('id')
                    if RFI.query.filter_by(project_id=project_id, number=str(num)).first():
                        continue
                    rfi = RFI(
                        project_id=project_id,
                        number=str(num),
                        subject=item.get('subject') or item.get('title') or 'Procore RFI',
                        question=item.get('question') or '',
                        status='Open',
                        created_by_id=user_id,
                    )
                    db.session.add(rfi)
                    imported += 1
            logs.append(_log_sync(db, IntegrationSyncLog, 'procore', 'pull', 'rfis', project_id,
                                  project_id, 'posted', f'Imported {imported} RFIs from Procore', user_id=user_id))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logs.append(_log_sync(db, IntegrationSyncLog, 'procore', 'pull', 'rfis', project_id,
                                  project_id, 'error', str(exc), user_id=user_id))
    else:
        # Map local users with procore_user_id — readiness sync
        from app import User
        mapped = 0
        for u in User.query.limit(500):
            try:
                from user_extended_prefs import merge_integrations
                ints = merge_integrations(u)
                if ints.get('procore_user_id'):
                    mapped += 1
            except Exception:
                pass
        if project.details_json:
            try:
                details = json.loads(project.details_json)
            except (TypeError, json.JSONDecodeError):
                details = {}
        else:
            details = {}
        details['procore_last_sync'] = datetime.utcnow().isoformat() + 'Z'
        details['procore_sync_mode'] = 'mapped_users' if not api_url else 'api'
        project.details_json = json.dumps(details)
        logs.append(_log_sync(
            db, IntegrationSyncLog, 'procore', 'push', 'user_mapping', project_id,
            project_id, 'simulated',
            f'Procore API not configured — mapped {mapped} users with Procore IDs. Set PROCORE_API_URL and PROCORE_API_TOKEN for live sync.',
            user_id=user_id,
        ))
    return logs


def ai_assist(db, models, task, project_id, record_id, user_id, extra_context=None):
    """LLM-backed assist for RFI draft, submittal review, scope gap."""
    from extended_platform_persistence import generate_ai_insight
    from llm_service import chat_completion, llm_configured

    Project = models['Project']
    RFI = models.get('RFI')
    ExtendedModuleRecord = models['ExtendedModuleRecord']
    task = (task or '').lower()
    context_parts = [extra_context or '']

    if task == 'rfi_draft' and RFI and record_id:
        rfi = RFI.query.get(record_id)
        if rfi:
            context_parts.append(f'RFI #{rfi.number}: {rfi.subject}\nQuestion: {rfi.question}')
    elif task == 'submittal_review':
        from app import Submittal
        sub = Submittal.query.get(record_id) if record_id else None
        if sub:
            context_parts.append(f'Submittal: {sub.title or sub.number}\nSpec: {sub.spec_section}\nDescription: {sub.description}')
    elif task == 'scope_gap':
        context_parts.append(f'Scope review for project {project_id}, record {record_id}')

    fallback = generate_ai_insight(
        project_id, 'ai_insights', ' '.join(context_parts), Project, ExtendedModuleRecord,
        RFI, models.get('ChangeOrder'),
    )
    system = (
        'You are an expert construction project manager assistant for Case PM. '
        'Provide concise, actionable guidance for RFIs, submittals, and scope reviews. '
        'Use bullet points. Flag risks and missing information.'
    )
    user_msg = '\n'.join(context_parts)
    if task == 'rfi_draft':
        user_msg = f'Draft a professional RFI response for:\n{user_msg}'
    elif task == 'submittal_review':
        user_msg = f'Review this submittal and list compliance issues, missing items, and recommended action:\n{user_msg}'
    elif task == 'scope_gap':
        user_msg = f'Identify scope gaps and coordination risks:\n{user_msg}'

    messages = [{'role': 'user', 'content': user_msg}]
    text, provider = chat_completion(messages, system_prompt=system)
    if not text:
        text = fallback
        provider = 'rules'
    return {'response': text, 'provider': provider, 'task': task, 'llm_configured': llm_configured()}


def notify_pay_app_event(project_id, period, title, message, user_ids):
    link = f'/pay-applications?project_id={project_id}&period={period}'
    for uid in user_ids or []:
        _notify(uid, title, message, link)


def notify_change_order_event(co, title, message, user_ids):
    link = f'/change-orders?project_id={co.project_id}&co_id={co.id}'
    for uid in user_ids or []:
        _notify(uid, title, message, link)
