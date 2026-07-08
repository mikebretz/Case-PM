"""
Case PM workflow layer — approvals, internal messages, notifications, module state sync.
"""
from datetime import datetime
import json

from flask import jsonify, request
from flask_login import current_user

db = None
User = None
Project = None
Company = None
Notification = None
AuditLog = None
login_required = None
ApprovalRequest = None
InternalMessage = None
ModuleState = None
ProjectMembership = None


def init_models(_db):
    """Define SQLAlchemy models once db is available."""
    global db, ApprovalRequest, InternalMessage, ModuleState, ProjectMembership
    if ApprovalRequest is not None:
        return
    db = _db

    class _ApprovalRequest(db.Model):
        __tablename__ = 'approval_request'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
        module = db.Column(db.String(80), nullable=False)
        entity_type = db.Column(db.String(80), nullable=False)
        entity_id = db.Column(db.String(120), nullable=False)
        title = db.Column(db.String(300), nullable=False)
        description = db.Column(db.Text)
        status = db.Column(db.String(40), default='pending')
        requested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        assignee_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        assignee_role = db.Column(db.String(80), nullable=True)
        action_url = db.Column(db.String(400))
        payload_json = db.Column(db.Text)
        decision = db.Column(db.String(40))
        decision_comments = db.Column(db.Text)
        decided_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        decided_at = db.Column(db.DateTime)

        def to_dict(self):
            return {
                'id': self.id,
                'project_id': self.project_id,
                'company_id': self.company_id,
                'module': self.module,
                'entity_type': self.entity_type,
                'entity_id': self.entity_id,
                'title': self.title,
                'description': self.description or '',
                'status': self.status,
                'requested_by_id': self.requested_by_id,
                'assignee_user_id': self.assignee_user_id,
                'assignee_role': self.assignee_role,
                'action_url': self.action_url or '',
                'payload': self.get_payload(),
                'decision': self.decision or '',
                'decision_comments': self.decision_comments or '',
                'decided_by_id': self.decided_by_id,
                'created_at': self.created_at.isoformat() if self.created_at else '',
                'decided_at': self.decided_at.isoformat() if self.decided_at else '',
            }

        def get_payload(self):
            if not self.payload_json:
                return {}
            try:
                return json.loads(self.payload_json)
            except (TypeError, json.JSONDecodeError):
                return {}

    class _InternalMessage(db.Model):
        __tablename__ = 'internal_message'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        approval_id = db.Column(db.Integer, db.ForeignKey('approval_request.id'), nullable=True)
        folder = db.Column(db.String(60), default='internal-inbox')
        msg_type = db.Column(db.String(40), default='alert')
        subject = db.Column(db.String(300), nullable=False)
        preview = db.Column(db.String(500))
        body = db.Column(db.Text)
        from_label = db.Column(db.String(120))
        from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        module = db.Column(db.String(80))
        action_url = db.Column(db.String(400))
        action_label = db.Column(db.String(120))
        priority = db.Column(db.String(20), default='normal')
        requires_action = db.Column(db.Boolean, default=False)
        is_read = db.Column(db.Boolean, default=False)
        archived = db.Column(db.Boolean, default=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        def to_dict(self):
            d = {
                'id': self.id,
                'folder': self.folder,
                'type': self.msg_type,
                'subject': self.subject,
                'preview': self.preview or '',
                'body': self.body or '',
                'from': self.from_label or 'Case PM',
                'fromUser': self.from_label or 'System',
                'project': self._project_name(),
                'module': self.module or '',
                'actionUrl': self.action_url or '',
                'actionLabel': self.action_label or 'Open',
                'priority': self.priority or 'normal',
                'requiresAction': self.requires_action,
                'unread': not self.is_read,
                'archived': self.archived,
                'date': self.created_at.isoformat() if self.created_at else '',
                'approvalId': self.approval_id,
                'payload': {},
                'entityType': '',
                'entityId': '',
            }
            if self.approval_id:
                approval = ApprovalRequest.query.get(self.approval_id)
                if approval:
                    d['payload'] = approval.get_payload()
                    d['entityType'] = approval.entity_type or ''
                    d['entityId'] = approval.entity_id or ''
            return d

        def _project_name(self):
            if not self.project_id or not Project:
                return ''
            p = Project.query.get(self.project_id)
            return p.name if p else ''

    class _ModuleState(db.Model):
        __tablename__ = 'module_state'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
        module = db.Column(db.String(80), nullable=False)
        state_key = db.Column(db.String(120), nullable=False)
        data_json = db.Column(db.Text)
        updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        __table_args__ = (
            db.UniqueConstraint('project_id', 'company_id', 'module', 'state_key', name='uq_module_state'),
        )

    class _ProjectMembership(db.Model):
        __tablename__ = 'project_membership'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
        role = db.Column(db.String(80), default='Viewer')
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)

        __table_args__ = (
            db.UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
        )

    ApprovalRequest = _ApprovalRequest
    InternalMessage = _InternalMessage
    ModuleState = _ModuleState
    ProjectMembership = _ProjectMembership


ROLE_PERMISSIONS = {
    'Admin': {'portal': 'staff', 'approve': '*', 'modules': '*'},
    'Project Manager': {'portal': 'staff', 'approve': ['Pay Applications', 'Change Orders', 'Submittals', 'RFIs', 'Budget'], 'modules': '*'},
    'Superintendent': {'portal': 'staff', 'approve': ['Daily Log', 'Safety'], 'modules': 'field'},
    'Architect': {'portal': 'consultant', 'approve': ['Submittals', 'RFIs', 'Change Orders'], 'modules': ['Submittals', 'RFIs', 'Change Orders', 'Drawings', 'Documents', 'Email']},
    'Owner': {'portal': 'consultant', 'approve': ['Change Orders', 'Pay Applications'], 'modules': ['Pay Applications', 'Change Orders', 'RFIs', 'Documents', 'Email', 'Schedule']},
    'Contractor Accounting': {
        'portal': 'staff',
        'approve': ['Pay Applications', 'Change Orders'],
        'modules': ['Pay Applications', 'Change Orders', 'Budget', 'Documents', 'Email', 'Schedule'],
    },
    'Company User': {'portal': 'sub', 'approve': [], 'modules': ['Pay Applications', 'Submittals', 'Documents', 'Email', 'RFIs']},
    'Viewer': {'portal': 'staff', 'approve': [], 'modules': 'view'},
}


def ensure_workflow_schema(engine):
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'user' in inspector.get_table_names():
        cols = {c['name'] for c in inspector.get_columns('user')}
        if 'company_id' not in cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN company_id INTEGER'))
        if 'permissions_json' not in cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN permissions_json TEXT'))
        db.session.commit()


def get_role_permissions(user):
    if not user:
        return {}
    if getattr(user, 'permissions_json', None):
        try:
            return json.loads(user.permissions_json)
        except (TypeError, json.JSONDecodeError):
            pass
    return ROLE_PERMISSIONS.get(user.role or 'Viewer', ROLE_PERMISSIONS['Viewer'])


def user_can_approve(user, module):
    if not user:
        return False
    if user.role == 'Admin':
        return True
    perms = get_role_permissions(user)
    approve = perms.get('approve', [])
    if approve == '*':
        return True
    return module in approve


def user_portal_type(user):
    return get_role_permissions(user).get('portal', 'staff')


def is_sub_user(user):
    return user_portal_type(user) == 'sub' or user.role == 'Company User'


def is_architect_user(user):
    return user.role == 'Architect'


def notify_user(user_id, title, message, link=None):
    if not user_id or not Notification:
        return
    n = Notification(user_id=user_id, title=title, message=message, link=link or '')
    db.session.add(n)


def create_internal_message(user_id, *, folder, msg_type, subject, preview='', body='',
                            project_id=None, approval_id=None, from_label='Case PM',
                            from_user_id=None, module='', action_url='', action_label='Open',
                            priority='normal', requires_action=False):
    msg = InternalMessage(
        user_id=user_id,
        project_id=project_id,
        approval_id=approval_id,
        folder=folder,
        msg_type=msg_type,
        subject=subject,
        preview=preview or subject[:500],
        body=body,
        from_label=from_label,
        from_user_id=from_user_id,
        module=module,
        action_url=action_url,
        action_label=action_label,
        priority=priority,
        requires_action=requires_action,
    )
    db.session.add(msg)
    return msg


def find_assignees(project_id, module, company_id=None):
    users = User.query.filter_by(status='Active').all()
    assignees = []
    for u in users:
        if user_can_approve(u, module) and not is_sub_user(u):
            assignees.append(u)
    if not assignees:
        assignees = [u for u in users if u.role in ('Admin', 'Project Manager')]
    return assignees


def create_approval(*, project_id, module, entity_type, entity_id, title,
                    description='', company_id=None, assignee_role=None,
                    action_url='', payload=None, requested_by_id=None,
                    notify_company_user_id=None):
    approval = ApprovalRequest(
        project_id=project_id,
        company_id=company_id,
        module=module,
        entity_type=entity_type,
        entity_id=str(entity_id),
        title=title,
        description=description,
        status='pending',
        requested_by_id=requested_by_id or (current_user.id if current_user.is_authenticated else None),
        assignee_role=assignee_role or 'Project Manager',
        action_url=action_url,
        payload_json=json.dumps(payload or {}),
    )
    db.session.add(approval)
    db.session.flush()

    assignees = find_assignees(project_id, module, company_id)
    folder = 'approvals' if module in ('Pay Applications', 'Change Orders') else 'action-required'
    msg_type = 'approval' if folder == 'approvals' else 'alert'

    for u in assignees:
        create_internal_message(
            u.id,
            folder=folder,
            msg_type=msg_type,
            subject=title,
            preview=description[:500] if description else title,
            body=description or f'<p>{title}</p>',
            project_id=project_id,
            approval_id=approval.id,
            from_label=current_user.full_name if current_user.is_authenticated else 'Case PM System',
            from_user_id=current_user.id if current_user.is_authenticated else None,
            module=module,
            action_url=action_url,
            action_label='Review',
            priority='high' if module == 'Pay Applications' else 'normal',
            requires_action=True,
        )
        notify_user(u.id, title, description or title, action_url)

    if notify_company_user_id:
        notify_user(notify_company_user_id, f'Update: {title}', description or title, action_url)

    if AuditLog and current_user.is_authenticated:
        db.session.add(AuditLog(
            user_id=current_user.id,
            action='Approval Requested',
            target_type=entity_type,
            target_id=entity_id,
            details=title,
        ))
    return approval


def decide_approval(approval_id, decision, comments=''):
    approval = ApprovalRequest.query.get_or_404(approval_id)
    if approval.status != 'pending':
        return approval, 'already_decided'

    if not user_can_approve(current_user, approval.module):
        return None, 'forbidden'

    approval.status = 'approved' if decision == 'approve' else 'rejected' if decision == 'reject' else 'dismissed'
    approval.decision = decision
    approval.decision_comments = comments
    approval.decided_by_id = current_user.id
    approval.decided_at = datetime.utcnow()

    InternalMessage.query.filter_by(approval_id=approval.id).update({
        'is_read': True,
        'requires_action': False,
        'archived': decision == 'dismiss',
    })

    if approval.requested_by_id:
        verb = 'approved' if decision == 'approve' else 'rejected' if decision == 'reject' else 'dismissed'
        notify_user(
            approval.requested_by_id,
            f'{approval.title} — {verb}',
            comments or f'Your request was {verb}.',
            approval.action_url,
        )
        create_internal_message(
            approval.requested_by_id,
            folder='team',
            msg_type='message',
            subject=f'{approval.title} — {verb}',
            preview=comments or f'Decision: {verb}',
            body=f'<p>{comments or verb}</p>',
            project_id=approval.project_id,
            approval_id=approval.id,
            from_label=current_user.full_name,
            from_user_id=current_user.id,
            module=approval.module,
            action_url=approval.action_url,
            requires_action=False,
        )

    if AuditLog:
        db.session.add(AuditLog(
            user_id=current_user.id,
            action=f'Approval {decision}',
            target_type=approval.entity_type,
            target_id=approval.entity_id,
            details=comments or approval.title,
        ))
    return approval, None


def register_workflow(app, _db, models):
    global db, User, Project, Company, Notification, AuditLog, login_required
    init_models(_db)
    db = _db
    User = models['User']
    Project = models['Project']
    Company = models['Company']
    Notification = models['Notification']
    AuditLog = models.get('AuditLog')
    login_required = models['login_required']

    @app.route('/api/portal/context')
    @login_required
    def api_portal_context():
        perms = get_role_permissions(current_user)
        company = Company.query.get(current_user.company_id) if getattr(current_user, 'company_id', None) else None
        return jsonify({
            'userId': current_user.id,
            'userName': current_user.full_name,
            'userEmail': current_user.email,
            'role': current_user.role,
            'portal': user_portal_type(current_user),
            'companyId': getattr(current_user, 'company_id', None),
            'companyName': company.name if company else (current_user.company or ''),
            'companyType': company.type if company else '',
            'canApprove': {m: user_can_approve(current_user, m) for m in
                           ['Pay Applications', 'Change Orders', 'Submittals', 'RFIs', 'Budget']},
            'permissions': perms,
            'isSub': is_sub_user(current_user),
            'isArchitect': is_architect_user(current_user),
        })

    @app.route('/api/internal-messages')
    @login_required
    def api_internal_messages():
        folder = request.args.get('folder')
        archived = request.args.get('archived') == '1'
        q = InternalMessage.query.filter_by(user_id=current_user.id, archived=archived)
        if folder and folder not in ('internal-inbox', ''):
            q = q.filter_by(folder=folder)
        messages = q.order_by(InternalMessage.created_at.desc()).limit(200).all()
        return jsonify([m.to_dict() for m in messages])

    @app.route('/api/internal-messages/<int:msg_id>/read', methods=['POST'])
    @login_required
    def api_internal_message_read(msg_id):
        msg = InternalMessage.query.filter_by(id=msg_id, user_id=current_user.id).first_or_404()
        msg.is_read = True
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/internal-messages/<int:msg_id>/archive', methods=['POST'])
    @login_required
    def api_internal_message_archive(msg_id):
        msg = InternalMessage.query.filter_by(id=msg_id, user_id=current_user.id).first_or_404()
        msg.archived = True
        msg.is_read = True
        msg.requires_action = False
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/approvals', methods=['GET', 'POST'])
    @login_required
    def api_approvals():
        if request.method == 'GET':
            status = request.args.get('status', 'pending')
            project_id = request.args.get('project_id', type=int)
            q = ApprovalRequest.query
            if status:
                q = q.filter_by(status=status)
            if project_id:
                q = q.filter_by(project_id=project_id)
            if is_sub_user(current_user) and getattr(current_user, 'company_id', None):
                q = q.filter(
                    (ApprovalRequest.company_id == current_user.company_id) |
                    (ApprovalRequest.requested_by_id == current_user.id)
                )
            elif current_user.role not in ('Admin', 'Project Manager') and not user_can_approve(current_user, 'Pay Applications'):
                q = q.filter_by(requested_by_id=current_user.id)
            items = q.order_by(ApprovalRequest.created_at.desc()).limit(100).all()
            return jsonify([a.to_dict() for a in items])

        data = request.get_json(silent=True) or {}
        approval = create_approval(
            project_id=data.get('project_id'),
            module=data.get('module', 'General'),
            entity_type=data.get('entity_type', 'item'),
            entity_id=data.get('entity_id', ''),
            title=data.get('title', 'Approval required'),
            description=data.get('description', ''),
            company_id=data.get('company_id'),
            assignee_role=data.get('assignee_role'),
            action_url=data.get('action_url', ''),
            payload=data.get('payload'),
            notify_company_user_id=data.get('notify_company_user_id'),
        )
        db.session.commit()
        return jsonify({'ok': True, 'approval': approval.to_dict()})

    @app.route('/api/approvals/<int:approval_id>/decide', methods=['POST'])
    @login_required
    def api_approval_decide(approval_id):
        data = request.get_json(silent=True) or {}
        decision = data.get('decision', 'approve')
        comments = data.get('comments', '')
        approval, err = decide_approval(approval_id, decision, comments)
        if err == 'forbidden':
            return jsonify({'error': 'Permission denied'}), 403
        if err == 'already_decided':
            return jsonify({'error': 'Already decided'}), 400
        db.session.commit()
        return jsonify({'ok': True, 'approval': approval.to_dict()})

    @app.route('/api/notifications')
    @login_required
    def api_notifications_list():
        items = Notification.query.filter_by(user_id=current_user.id).order_by(
            Notification.created_at.desc()
        ).limit(50).all()
        return jsonify([{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat() if n.created_at else '',
        } for n in items])

    @app.route('/api/notifications/mark-all-read', methods=['POST'])
    @login_required
    def api_notifications_mark_all():
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/module-state/<module>/<state_key>', methods=['GET', 'PUT'])
    @login_required
    def api_module_state(module, state_key):
        if request.method == 'PUT':
            data = request.get_json(silent=True) or {}
            project_id = data.get('project_id')
            company_id = data.get('company_id')
        else:
            project_id = request.args.get('project_id', type=int)
            company_id = request.args.get('company_id', type=int)

        if not project_id:
            return jsonify({'error': 'project_id required'}), 400

        if is_sub_user(current_user):
            company_id = company_id or getattr(current_user, 'company_id', None)

        row = ModuleState.query.filter_by(
            project_id=project_id, module=module, state_key=state_key,
            company_id=company_id,
        ).first()

        if request.method == 'GET':
            if not row:
                return jsonify({'data': None})
            try:
                return jsonify({
                    'data': json.loads(row.data_json or 'null'),
                    'updated_at': row.updated_at.isoformat() if row.updated_at else '',
                })
            except json.JSONDecodeError:
                return jsonify({'data': None})

        payload = (request.get_json(silent=True) or {}).get('data')
        if not row:
            row = ModuleState(
                project_id=project_id,
                company_id=company_id,
                module=module,
                state_key=state_key,
            )
            db.session.add(row)
        row.data_json = json.dumps(payload)
        row.updated_by_id = current_user.id
        row.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/workflow/event', methods=['POST'])
    @login_required
    def api_workflow_event():
        data = request.get_json(silent=True) or {}
        event = data.get('event')
        project_id = data.get('project_id')
        module = data.get('module', 'General')
        entity_type = data.get('entity_type', 'item')
        entity_id = data.get('entity_id', '')
        title = data.get('title', 'Workflow event')
        description = data.get('description', '')
        company_id = data.get('company_id')
        action_url = data.get('action_url', '')
        payload = data.get('payload') or {}

        if event in ('submit', 'request_approval'):
            approval = create_approval(
                project_id=project_id,
                module=module,
                entity_type=entity_type,
                entity_id=entity_id,
                title=title,
                description=description,
                company_id=company_id,
                action_url=action_url,
                payload=payload,
            )
            db.session.commit()
            return jsonify({'ok': True, 'approval': approval.to_dict()})

        if event == 'notify':
            target_user_ids = data.get('user_ids') or []
            if not target_user_ids:
                target_user_ids = [u.id for u in find_assignees(project_id, module, company_id)]
            for uid in target_user_ids:
                create_internal_message(
                    uid,
                    folder=data.get('folder', 'alerts'),
                    msg_type=data.get('msg_type', 'alert'),
                    subject=title,
                    preview=description[:500],
                    body=f'<p>{description}</p>',
                    project_id=project_id,
                    from_label=current_user.full_name,
                    from_user_id=current_user.id,
                    module=module,
                    action_url=action_url,
                    requires_action=data.get('requires_action', False),
                )
                notify_user(uid, title, description, action_url)
            db.session.commit()
            return jsonify({'ok': True})

        if event in ('approve', 'reject', 'dismiss'):
            approval_id = data.get('approval_id')
            if approval_id:
                decision = 'dismiss' if event == 'dismiss' else event
                approval, err = decide_approval(approval_id, decision, data.get('comments', ''))
                if err:
                    return jsonify({'error': err}), 403 if err == 'forbidden' else 400
                db.session.commit()
                return jsonify({'ok': True, 'approval': approval.to_dict()})

        return jsonify({'error': 'Unknown event'}), 400
