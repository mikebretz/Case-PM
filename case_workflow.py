"""
Case PM workflow layer — approvals, internal messages, notifications, module state sync.
"""
from datetime import datetime
import json
import uuid

from flask import jsonify, request
from flask_login import current_user

db = None
_registered_db = None
_get_current_project_id_fn = None
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

INTERNAL_MESSAGE_MOVE_FOLDERS = frozenset({
    'internal-inbox', 'sent', 'drafts', 'trash',
    'approvals', 'alerts', 'team', 'mentions',
    'announcements', 'action-required', 'fyi', 'internal-archive',
})


def _apply_internal_folder_move(msg, folder):
    """Move an internal message to a folder or archive."""
    if folder == 'internal-archive':
        msg.archived = True
        return
    msg.archived = False
    msg.folder = folder


def _canonical_db(fallback=None):
    """Return the SQLAlchemy extension for the active Flask app."""
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            ext = current_app.extensions.get('sqlalchemy')
            if ext is not None:
                return ext
    except Exception:
        pass
    try:
        import sys
        app_mod = sys.modules.get('app')
        if app_mod is not None and getattr(app_mod, 'db', None) is not None:
            return app_mod.db
    except Exception:
        pass
    return fallback


def _workflow_db():
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            ext = current_app.extensions.get('sqlalchemy')
            if ext is not None:
                return ext
    except Exception:
        pass
    canonical = _canonical_db(None)
    if canonical is None:
        raise RuntimeError('Case PM database is not initialized.')
    return canonical


def _workflow_session():
    return _workflow_db().session


def model_query(model):
    """Run ORM queries against the active Flask app database."""
    if model is None:
        raise RuntimeError('Model not available')
    return _workflow_session().query(model)


def ensure_workflow_models_bound():
    """Sync module db pointers. Workflow ORM classes are defined once per process."""
    global db, _registered_db
    canonical = _workflow_db()
    db = canonical
    _registered_db = canonical
    if InternalMessage is None:
        init_models(canonical)
    return canonical


def _current_project_id():
    if _get_current_project_id_fn:
        try:
            return _get_current_project_id_fn()
        except Exception:
            return None
    return None


def _runtime_model(name, fallback=None):
    try:
        import sys
        app_mod = sys.modules.get('app')
        if app_mod is not None:
            model = getattr(app_mod, name, None)
            if model is not None:
                return model
    except Exception:
        pass
    return fallback


def _lookup_user_by_id(user_id):
    if not user_id:
        return None
    user_model = _runtime_model('User', User)
    if user_model is None:
        return None
    try:
        return model_query(user_model).get(int(user_id))
    except Exception:
        return None


def _lookup_project_by_id(project_id):
    if not project_id:
        return None
    project_model = _runtime_model('Project', Project)
    if project_model is None:
        return None
    try:
        return model_query(project_model).get(int(project_id))
    except Exception:
        return None


def _lookup_approval_by_id(approval_id):
    if not approval_id or ApprovalRequest is None:
        return None
    try:
        return model_query(ApprovalRequest).get(int(approval_id))
    except Exception:
        return None


def init_models(_db):
    """Define SQLAlchemy models once db is available."""
    global db, ApprovalRequest, InternalMessage, ModuleState, ProjectMembership
    canonical = _canonical_db(_db) or _db
    if InternalMessage is not None:
        db = canonical
        return
    db = canonical

    class _ApprovalRequest(db.Model):
        __tablename__ = 'approval_request'
        __table_args__ = {'extend_existing': True}
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
        __table_args__ = {'extend_existing': True}
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
        recipients_json = db.Column(db.Text)
        thread_key = db.Column(db.String(120))
        in_reply_to_id = db.Column(db.Integer, db.ForeignKey('internal_message.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        def _sender_display(self):
            """Resolve sender name without generic Case PM email branding."""
            if self.from_user_id:
                u = _lookup_user_by_id(self.from_user_id)
                if u:
                    name = (getattr(u, 'full_name', None) or '').strip()
                    if not name:
                        name = f'{getattr(u, "first_name", "")} {getattr(u, "last_name", "")}'.strip()
                    if name:
                        return name
            label = (self.from_label or '').strip()
            generic = {'case pm', 'case pm system', 'case pm admin', 'system'}
            if label and label.lower() not in generic:
                return label
            return 'Project Team'

        def _sender_email(self):
            if self.from_user_id:
                u = _lookup_user_by_id(self.from_user_id)
                if u:
                    return (getattr(u, 'email', None) or '').strip()
            return ''

        def _reply_to_recipient(self):
            email = self._sender_email()
            name = self._sender_display()
            if not email and not name:
                return None
            generic = {'project team', 'case pm', 'case pm system', 'case pm admin', 'system'}
            if not email and (name or '').strip().lower() in generic:
                return None
            return {'name': name or email, 'email': email}

        def to_dict(self):
            sender = self._sender_display()
            recipients = _parse_recipients_json(self.recipients_json)
            d = {
                'id': self.id,
                'folder': self.folder,
                'type': self.msg_type,
                'subject': self.subject,
                'preview': self.preview or '',
                'body': self.body or '',
                'from': sender,
                'fromUser': sender,
                'fromEmail': self._sender_email(),
                'fromUserId': self.from_user_id,
                'replyTo': self._reply_to_recipient(),
                'to': recipients['to'],
                'cc': recipients['cc'],
                'bcc': recipients['bcc'],
                'threadKey': self.thread_key or '',
                'inReplyToId': self.in_reply_to_id,
                'projectId': self.project_id,
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
                approval = _lookup_approval_by_id(self.approval_id)
                if approval:
                    d['payload'] = approval.get_payload()
                    d['entityType'] = approval.entity_type or ''
                    d['entityId'] = approval.entity_id or ''
            return d

        def _project_name(self):
            if not self.project_id:
                return ''
            p = _lookup_project_by_id(self.project_id)
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
            {'extend_existing': True},
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
            {'extend_existing': True},
        )

    ApprovalRequest = _ApprovalRequest
    InternalMessage = _InternalMessage
    ModuleState = _ModuleState
    ProjectMembership = _ProjectMembership


ROLE_PERMISSIONS = {
    'Admin': {'portal': 'staff', 'approve': '*', 'modules': '*'},
    'Project Manager': {'portal': 'staff', 'approve': ['Pay Applications', 'Change Orders', 'Commitments', 'Submittals', 'RFIs', 'Budget'], 'modules': '*'},
    'Superintendent': {'portal': 'staff', 'approve': ['Daily Log', 'Safety'], 'modules': 'field'},
    'Architect': {'portal': 'consultant', 'approve': ['Submittals', 'RFIs', 'Change Orders'], 'modules': ['Submittals', 'RFIs', 'Change Orders', 'Drawings', 'Documents', 'Photos', 'Punch List', 'Inspections', 'Meeting Minutes', 'Project Directory', 'Internal Messages']},
    'Owner': {'portal': 'consultant', 'approve': ['Change Orders', 'Pay Applications'], 'modules': ['Pay Applications', 'Change Orders', 'RFIs', 'Documents', 'Email', 'Schedule']},
    'Contractor Accounting': {
        'portal': 'staff',
        'approve': ['Pay Applications', 'Change Orders', 'Commitments'],
        'modules': ['Pay Applications', 'Change Orders', 'Commitments', 'Budget', 'Documents', 'Email', 'Schedule'],
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
            _workflow_session().execute(text('ALTER TABLE user ADD COLUMN company_id INTEGER'))
        if 'permissions_json' not in cols:
            _workflow_session().execute(text('ALTER TABLE user ADD COLUMN permissions_json TEXT'))
    if 'internal_message' in inspector.get_table_names():
        cols = {c['name'] for c in inspector.get_columns('internal_message')}
        if 'recipients_json' not in cols:
            _workflow_session().execute(text('ALTER TABLE internal_message ADD COLUMN recipients_json TEXT'))
        if 'thread_key' not in cols:
            _workflow_session().execute(text('ALTER TABLE internal_message ADD COLUMN thread_key VARCHAR(120)'))
        if 'in_reply_to_id' not in cols:
            _workflow_session().execute(text('ALTER TABLE internal_message ADD COLUMN in_reply_to_id INTEGER'))
    _workflow_session().commit()


def _recipient_entry(user):
    name = (getattr(user, 'full_name', None) or '').strip()
    if not name:
        name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    email = (getattr(user, 'email', None) or '').strip()
    return {'name': name or email, 'email': email}


def _recipients_payload(to_users, cc_users, bcc_users):
    return {
        'to': [_recipient_entry(u) for u in (to_users or [])],
        'cc': [_recipient_entry(u) for u in (cc_users or [])],
        'bcc': [_recipient_entry(u) for u in (bcc_users or [])],
    }


def _parse_recipients_json(raw):
    if not raw:
        return {'to': [], 'cc': [], 'bcc': []}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {'to': [], 'cc': [], 'bcc': []}
    if not isinstance(data, dict):
        return {'to': [], 'cc': [], 'bcc': []}
    return {
        'to': data.get('to') or [],
        'cc': data.get('cc') or [],
        'bcc': data.get('bcc') or [],
    }


def get_role_permissions(user):
    if not user:
        return {}
    try:
        from user_permissions_persistence import get_user_permissions
        perms = get_user_permissions(user)
        # Legacy compat for JS that checks modules === '*'
        if user.role == 'Admin':
            legacy = dict(perms)
            legacy['modules'] = '*'
            legacy['approve'] = '*'
            return legacy
        return perms
    except Exception:
        pass
    if getattr(user, 'permissions_json', None):
        try:
            return json.loads(user.permissions_json)
        except (TypeError, json.JSONDecodeError):
            pass
    return ROLE_PERMISSIONS.get(user.role or 'Viewer', ROLE_PERMISSIONS['Viewer'])


def _resolve_module_key(module):
    from permissions_catalog import WORKFLOW_MODULE_MAP, LEGACY_MODULE_MAP, all_module_keys
    if module in all_module_keys():
        return module
    return WORKFLOW_MODULE_MAP.get(module) or LEGACY_MODULE_MAP.get(module) or module


def user_module_perms(user, module):
    if not user:
        return {'access': 'none', 'approve': 'none'}
    if user.role == 'Admin':
        return {'access': 'admin', 'approve': 'approve_reject'}
    perms = get_role_permissions(user)
    if perms.get('modules') == '*':
        return {'access': 'admin', 'approve': 'approve_reject'}
    modules = perms.get('modules') or {}
    if isinstance(modules, list):
        # legacy list format
        key = _resolve_module_key(module)
        if key in modules or module in modules:
            return {'access': 'edit', 'approve': 'none'}
        return {'access': 'view' if perms.get('modules') == 'view' else 'none', 'approve': 'none'}
    key = _resolve_module_key(module)
    if key in modules:
        return modules.get(key, {'access': 'none', 'approve': 'none'})
    # Inherit from parent module when checking a sub-tab key
    from permissions_catalog import SUBMODULE_PARENT
    parent = SUBMODULE_PARENT.get(key)
    if parent and parent in modules:
        return dict(modules.get(parent, {'access': 'none', 'approve': 'none'}))
    return {'access': 'none', 'approve': 'none'}


def _direct_module_access_rank(user, module):
    from permissions_catalog import ACCESS_RANK
    mp = user_module_perms(user, module)
    return ACCESS_RANK.get(mp.get('access', 'none'), 0)


def user_has_module_access(user, module, min_access='view'):
    from permissions_catalog import ACCESS_RANK, submodule_keys_for
    if user.role in ('Admin', 'Developer'):
        return True
    key = _resolve_module_key(module)
    if _direct_module_access_rank(user, key) >= ACCESS_RANK.get(min_access, 0):
        return True
    # Parent page access if any sub-tab is allowed
    for sub_key in submodule_keys_for(key):
        if _direct_module_access_rank(user, sub_key) >= ACCESS_RANK.get(min_access, 0):
            return True
    return False


def user_can_approve(user, module, action='approve'):
    if not user:
        return False
    if user.role in ('Admin', 'Developer'):
        return True
    perms = get_role_permissions(user)
    approve = perms.get('approve', [])
    if approve == '*':
        return True
    # Legacy list format
    if isinstance(approve, list) and module in approve:
        return action in ('approve', 'submit')
    mp = user_module_perms(user, module)
    ap = mp.get('approve', 'none')
    if action == 'approve':
        return ap in ('approve', 'approve_reject')
    if action == 'reject':
        return ap in ('reject', 'approve_reject')
    if action == 'submit':
        return ap in ('submit', 'approve', 'approve_reject')
    return ap == 'approve_reject'


def user_portal_type(user):
    return get_role_permissions(user).get('portal', 'staff')


def is_sub_user(user):
    return user_portal_type(user) == 'sub' or user.role in (
        'Company User', 'Subcontractor', 'Subcontractor Contact', 'Subcontractor Accountant',
    )


def is_architect_user(user):
    return user.role == 'Architect'


def notify_user(user_id, title, message, link=None):
    if not user_id or not Notification:
        return
    n = Notification(user_id=user_id, title=title, message=message, link=link or '')
    _workflow_session().add(n)


def create_internal_message(user_id, *, folder, msg_type, subject, preview='', body='',
                            project_id=None, approval_id=None, from_label='Case PM',
                            from_user_id=None, module='', action_url='', action_label='Open',
                            priority='normal', requires_action=False, recipients_json=None,
                            thread_key=None, in_reply_to_id=None):
    ensure_workflow_models_bound()
    recipients_blob = None
    if recipients_json:
        recipients_blob = recipients_json if isinstance(recipients_json, str) else json.dumps(recipients_json)
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
        recipients_json=recipients_blob,
        thread_key=thread_key,
        in_reply_to_id=in_reply_to_id,
    )
    _workflow_session().add(msg)
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
    _workflow_session().add(approval)
    _workflow_session().flush()

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
        _workflow_session().add(AuditLog(
            user_id=current_user.id,
            action='Approval Requested',
            target_type=entity_type,
            target_id=entity_id,
            details=title,
        ))
    return approval


def decide_approval(approval_id, decision, comments=''):
    from financial_security import require_financial_project_access

    approval = ApprovalRequest.query.get_or_404(approval_id)
    if approval.status != 'pending':
        return approval, 'already_decided'

    try:
        require_financial_project_access(current_user, approval.project_id, Project)
    except PermissionError:
        return None, 'forbidden'
    except ValueError as exc:
        return None, str(exc)

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
        _workflow_session().add(AuditLog(
            user_id=current_user.id,
            action=f'Approval {decision}',
            target_type=approval.entity_type,
            target_id=approval.entity_id,
            details=comments or approval.title,
        ))
    return approval, None


def register_workflow(app, _db, models):
    global db, _registered_db, _get_current_project_id_fn
    global User, Project, Company, Notification, AuditLog, login_required
    canonical = _canonical_db(_db) or _db
    init_models(canonical)
    db = canonical
    _registered_db = canonical
    _get_current_project_id_fn = models.get('get_current_project_id')
    User = models['User']
    Project = models['Project']
    Company = models['Company']
    Notification = models['Notification']
    AuditLog = models.get('AuditLog')
    login_required = models['login_required']

    @app.route('/api/portal/context')
    @login_required
    def api_portal_context():
        try:
            from portal_sub_access import build_portal_context_payload
            payload = build_portal_context_payload(current_user, Company, db, {
                'get_role_permissions': get_role_permissions,
                'user_portal_type': user_portal_type,
                'is_sub_user': is_sub_user,
                'is_architect_user': is_architect_user,
                'user_can_approve': user_can_approve,
            })
            return jsonify(payload)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            role = getattr(current_user, 'role', None) or ''
            sub_roles = ('Subcontractor Accountant', 'Subcontractor Contact', 'Subcontractor', 'Company User')
            return jsonify({
                'userId': getattr(current_user, 'id', None),
                'userName': getattr(current_user, 'full_name', None) or '',
                'userEmail': getattr(current_user, 'email', None) or '',
                'role': role,
                'isAdmin': role == 'Admin',
                'portal': 'sub' if role in sub_roles else 'staff',
                'companyId': getattr(current_user, 'company_id', None),
                'companyName': getattr(current_user, 'company', None) or '',
                'companyType': '',
                'vendorCompanyLinked': bool(getattr(current_user, 'company_id', None)),
                'canApprove': {},
                'permissions': {'global': {}},
                'isSub': role in sub_roles,
                'isArchitect': role == 'Architect',
                'isSubVendorPayPortal': role in ('Subcontractor Accountant', 'Subcontractor Contact'),
                'emailInternalOnly': role in sub_roles,
                'canInternalMessages': role in sub_roles,
                'canExternalEmail': role not in sub_roles,
                '_fallback': True,
                '_detail': str(exc),
            })

    @app.route('/api/internal-messages/contacts')
    @login_required
    def api_internal_message_contacts():
        try:
            ensure_workflow_models_bound()
            from access_control import user_email_internal_only
            from document_module_security import is_staff_portal_user
            from project_workflow_users import build_internal_message_contacts

            user_model = _runtime_model('User', User)
            project_model = _runtime_model('Project', Project)
            company_model = _runtime_model('Company', Company)

            project_id = request.args.get('project_id', type=int)
            if not project_id:
                project_id = _current_project_id()

            if is_staff_portal_user(current_user) and not user_email_internal_only(current_user):
                users = model_query(user_model).filter_by(status='Active').all()
                users = sorted(
                    users,
                    key=lambda user: (
                        (getattr(user, 'first_name', '') or '').lower(),
                        (getattr(user, 'last_name', '') or '').lower(),
                    ),
                )[:500]
                contacts = []
                for user in users:
                    if user.id == current_user.id:
                        continue
                    name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
                    if not name:
                        name = (getattr(user, 'full_name', None) or getattr(user, 'email', None) or '').strip()
                    contacts.append({
                        'id': user.id,
                        'user_id': user.id,
                        'name': name,
                        'email': (getattr(user, 'email', None) or '').strip(),
                        'company': (getattr(user, 'company', None) or '').strip(),
                        'phone': (getattr(user, 'phone', None) or '').strip(),
                        'position': (getattr(user, 'job_title', None) or '').strip(),
                        'group': 'staff',
                    })
                return jsonify({'ok': True, 'scoped': False, 'project_id': project_id, 'contacts': contacts})

            project = model_query(project_model).get(project_id) if project_id else None
            if project_id and project is None:
                return jsonify({'error': 'Invalid project_id'}), 404
            if project_id:
                from project_access import user_can_access_project
                if not user_can_access_project(current_user, project_id, project_model):
                    return jsonify({'error': 'You do not have access to this project.'}), 403

            contacts = build_internal_message_contacts(
                project,
                user_model,
                Company=company_model,
                exclude_user_id=current_user.id,
            )
            return jsonify({'ok': True, 'scoped': True, 'project_id': project_id, 'contacts': contacts})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Unable to load contacts: {exc}'}), 500

    @app.route('/api/internal-messages', methods=['GET', 'POST'])
    @login_required
    def api_internal_messages():
        if request.method == 'POST':
            try:
                ensure_workflow_models_bound()
                from project_workflow_users import (
                    parse_recipient_emails,
                    resolve_users_by_emails,
                    validate_internal_message_recipients,
                )

                if not user_has_module_access(current_user, 'internal_messages', 'entry'):
                    return jsonify({'error': 'You do not have permission to send internal messages.'}), 403

                user_model = _runtime_model('User', User)
                project_model = _runtime_model('Project', Project)
                company_model = _runtime_model('Company', Company)

                data = request.get_json(silent=True) or {}
                to_values = data.get('to') or []
                cc_values = data.get('cc') or []
                bcc_values = data.get('bcc') or []
                subject = (data.get('subject') or '').strip() or '(No subject)'
                body = data.get('body') or ''
                preview = (data.get('preview') or '').strip() or body.replace('<', ' ').replace('>', ' ').strip()[:500]
                project_id = data.get('project_id')
                try:
                    project_id = int(project_id) if project_id is not None else None
                except (TypeError, ValueError):
                    project_id = None
                if not project_id:
                    project_id = _current_project_id()

                emails = parse_recipient_emails(to_values, cc_values, bcc_values)
                if not emails:
                    return jsonify({'error': 'Add at least one recipient.'}), 400

                to_users = resolve_users_by_emails(parse_recipient_emails(to_values), user_model)
                cc_users = resolve_users_by_emails(parse_recipient_emails(cc_values), user_model)
                bcc_users = resolve_users_by_emails(parse_recipient_emails(bcc_values), user_model)
                recipients = []
                seen_ids = set()
                for user in to_users + cc_users + bcc_users:
                    if user.id in seen_ids:
                        continue
                    seen_ids.add(user.id)
                    recipients.append(user)
                if not recipients:
                    return jsonify({'error': 'No matching active users for those recipients.'}), 400

                visible_recipients = _recipients_payload(to_users, cc_users, [])
                sent_recipients = _recipients_payload(to_users, cc_users, bcc_users)

                project = model_query(project_model).get(project_id) if project_id else None
                if project_id and project is None:
                    return jsonify({'error': 'Invalid project.'}), 404
                if project_id:
                    from project_access import user_can_access_project
                    if not user_can_access_project(current_user, project_id, project_model):
                        return jsonify({'error': 'You do not have access to this project.'}), 403

                ok, err = validate_internal_message_recipients(
                    current_user,
                    recipients,
                    project,
                    user_model,
                    Company=company_model,
                )
                if not ok:
                    return jsonify({'error': err or 'Recipient not allowed.'}), 403

                from email_mailbox_persistence import resolve_mailbox_user_id
                from app import EmailMailboxAccess
                try:
                    mailbox_user_id = resolve_mailbox_user_id(
                        current_user,
                        data.get('user_id'),
                        User=user_model,
                        EmailMailboxAccess=EmailMailboxAccess,
                    )
                except PermissionError:
                    return jsonify({'error': 'Mailbox access denied'}), 403

                thread_key = (data.get('thread_key') or '').strip() or None
                reply_to_id = data.get('reply_to_id')
                parent_msg = None
                if reply_to_id:
                    try:
                        parent_msg = model_query(InternalMessage).filter_by(
                            id=int(reply_to_id),
                            user_id=mailbox_user_id,
                        ).first()
                    except (TypeError, ValueError):
                        parent_msg = None
                if parent_msg:
                    thread_key = parent_msg.thread_key or thread_key
                    if not thread_key:
                        thread_key = f'legacy-{parent_msg.id}'
                if not thread_key:
                    thread_key = str(uuid.uuid4())

                sender_name = (getattr(current_user, 'full_name', None) or '').strip()
                if not sender_name:
                    sender_name = f'{getattr(current_user, "first_name", "")} {getattr(current_user, "last_name", "")}'.strip()
                recipient_labels = []
                created = []
                for user in recipients:
                    if int(user.id) == int(current_user.id):
                        continue
                    label = (getattr(user, 'full_name', None) or getattr(user, 'email', None) or '').strip()
                    if label:
                        recipient_labels.append(label)
                    msg = create_internal_message(
                        user.id,
                        folder='team',
                        msg_type='message',
                        subject=subject,
                        preview=preview,
                        body=body,
                        project_id=project_id,
                        from_label=sender_name,
                        from_user_id=current_user.id,
                        module='Internal',
                        action_url='',
                        action_label='',
                        priority='normal',
                        requires_action=False,
                        recipients_json=visible_recipients,
                        thread_key=thread_key,
                        in_reply_to_id=parent_msg.id if parent_msg else None,
                    )
                    created.append(msg)

                if not created:
                    return jsonify({'error': 'Add at least one recipient other than yourself.'}), 400

                sent_preview = preview
                if recipient_labels:
                    sent_preview = f"To: {', '.join(recipient_labels)} — {preview}"[:500]

                create_internal_message(
                    current_user.id,
                    folder='sent',
                    msg_type='message',
                    subject=subject,
                    preview=sent_preview,
                    body=body,
                    project_id=project_id,
                    from_label=sender_name,
                    from_user_id=current_user.id,
                    module='Internal',
                    action_url='',
                    action_label='',
                    priority='normal',
                    requires_action=False,
                    recipients_json=sent_recipients,
                    thread_key=thread_key,
                    in_reply_to_id=parent_msg.id if parent_msg else None,
                )
                _workflow_session().commit()
                return jsonify({
                    'ok': True,
                    'sent': len(created),
                    'message_ids': [m.id for m in created],
                    'thread_key': thread_key,
                })
            except Exception as exc:
                _workflow_session().rollback()
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Unable to send message: {exc}'}), 500

        from email_mailbox_persistence import resolve_mailbox_user_id
        from app import EmailMailboxAccess
        try:
            ensure_workflow_models_bound()
            folder = request.args.get('folder')
            archived = request.args.get('archived') == '1'
            try:
                mailbox_user_id = resolve_mailbox_user_id(
                    current_user,
                    request.args.get('user_id', type=int),
                    User=_runtime_model('User', User),
                    EmailMailboxAccess=EmailMailboxAccess,
                )
            except PermissionError:
                return jsonify({'error': 'Mailbox access denied'}), 403
            q = model_query(InternalMessage).filter_by(user_id=mailbox_user_id, archived=archived)
            if folder and folder not in ('internal-inbox', ''):
                q = q.filter_by(folder=folder)
            messages = q.order_by(InternalMessage.created_at.desc()).limit(200).all()
            return jsonify([m.to_dict() for m in messages])
        except Exception as exc:
            _workflow_session().rollback()
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Unable to load messages: {exc}'}), 500

    def _internal_message_for_actor(msg_id):
        from email_mailbox_persistence import resolve_mailbox_user_id
        from app import EmailMailboxAccess
        requested = request.args.get('user_id', type=int)
        if not requested:
            body = request.get_json(silent=True) or {}
            requested = body.get('user_id')
        try:
            mailbox_user_id = resolve_mailbox_user_id(
                current_user,
                requested,
                User=_runtime_model('User', User),
                EmailMailboxAccess=EmailMailboxAccess,
            )
        except PermissionError:
            return None, (jsonify({'error': 'Mailbox access denied'}), 403)
        msg = model_query(InternalMessage).filter_by(id=msg_id, user_id=mailbox_user_id).first()
        if not msg:
            return None, (jsonify({'error': 'Not found'}), 404)
        return msg, None

    @app.route('/api/internal-messages/<int:msg_id>/read', methods=['POST'])
    @login_required
    def api_internal_message_read(msg_id):
        msg, err = _internal_message_for_actor(msg_id)
        if err:
            return err
        msg.is_read = True
        _workflow_session().commit()
        return jsonify({'ok': True})

    @app.route('/api/internal-messages/<int:msg_id>/archive', methods=['POST'])
    @login_required
    def api_internal_message_archive(msg_id):
        msg, err = _internal_message_for_actor(msg_id)
        if err:
            return err
        msg.archived = True
        msg.is_read = True
        msg.requires_action = False
        _workflow_session().commit()
        return jsonify({'ok': True})

    @app.route('/api/internal-messages/<int:msg_id>', methods=['DELETE'])
    @login_required
    def api_internal_message_delete(msg_id):
        msg, err = _internal_message_for_actor(msg_id)
        if err:
            return err
        permanent = msg.folder == 'trash'
        if permanent:
            _workflow_session().delete(msg)
        else:
            msg.folder = 'trash'
            msg.archived = False
            msg.is_read = True
            msg.requires_action = False
        _workflow_session().commit()
        return jsonify({'ok': True, 'permanent': permanent})

    @app.route('/api/internal-messages/bulk', methods=['POST'])
    @login_required
    def api_internal_messages_bulk():
        from email_mailbox_persistence import resolve_mailbox_user_id
        from app import EmailMailboxAccess
        data = request.get_json(silent=True) or {}
        ids = data.get('ids') or []
        action = (data.get('action') or '').strip().lower()
        folder = (data.get('folder') or '').strip()
        if not ids or action not in ('read', 'unread', 'move'):
            return jsonify({'error': 'Invalid bulk request.'}), 400
        if action == 'move' and folder not in INTERNAL_MESSAGE_MOVE_FOLDERS:
            return jsonify({'error': 'Invalid folder.'}), 400
        try:
            mailbox_user_id = resolve_mailbox_user_id(
                current_user,
                data.get('user_id'),
                User=_runtime_model('User', User),
                EmailMailboxAccess=EmailMailboxAccess,
            )
        except PermissionError:
            return jsonify({'error': 'Mailbox access denied'}), 403
        updated = 0
        for raw_id in ids:
            try:
                msg_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            msg = model_query(InternalMessage).filter_by(id=msg_id, user_id=mailbox_user_id).first()
            if not msg:
                continue
            if action == 'move':
                _apply_internal_folder_move(msg, folder)
            else:
                msg.is_read = action == 'read'
                if action == 'read':
                    msg.requires_action = False
            updated += 1
        _workflow_session().commit()
        return jsonify({'ok': True, 'updated': updated})

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
        _workflow_session().commit()
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
        _workflow_session().commit()
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
        _workflow_session().commit()
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
            _workflow_session().add(row)
        row.data_json = json.dumps(payload)
        row.updated_by_id = current_user.id
        row.updated_at = datetime.utcnow()
        _workflow_session().commit()
        return jsonify({'ok': True})

    @app.route('/api/workflow/event', methods=['POST'])
    @login_required
    def api_workflow_event():
        from financial_security import require_financial_project_access

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

        if event in ('submit', 'request_approval', 'notify'):
            if not project_id:
                return jsonify({'error': 'project_id required'}), 400
            try:
                require_financial_project_access(current_user, project_id, Project)
            except (ValueError, PermissionError) as exc:
                return jsonify({'error': str(exc)}), 403

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
            _workflow_session().commit()
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
            _workflow_session().commit()
            return jsonify({'ok': True})

        if event in ('approve', 'reject', 'dismiss'):
            approval_id = data.get('approval_id')
            if approval_id:
                decision = 'dismiss' if event == 'dismiss' else event
                approval, err = decide_approval(approval_id, decision, data.get('comments', ''))
                if err:
                    status = 403 if err in ('forbidden',) or 'access' in str(err).lower() else 400
                    return jsonify({'error': err}), status
                _workflow_session().commit()
                return jsonify({'ok': True, 'approval': approval.to_dict()})

        return jsonify({'error': 'Unknown event'}), 400

    @app.route('/api/workflow/respond/<module>/<int:entity_id>', methods=['GET', 'POST'])
    @login_required
    def api_workflow_respond(module, entity_id):
        from financial_security import require_financial_project_access

        module_key = (module or '').lower().replace('-', '_').replace(' ', '_')
        Project = models.get('Project')
        try:
            if module_key in ('rfi', 'rfis'):
                from rfi_persistence import get_linked_records
                from workflow_responder import get_rfi_responder_context, execute_rfi_action
                RFI = models.get('RFI')
                if not RFI:
                    return jsonify({'error': 'RFI module unavailable'}), 500
                rfi = RFI.query.get_or_404(entity_id)
                try:
                    from document_module_security import assert_rfi_read_allowed, assert_rfi_workflow_allowed
                    assert_rfi_read_allowed(current_user)
                    require_financial_project_access(current_user, rfi.project_id, Project)
                except (ValueError, PermissionError) as exc:
                    return jsonify({'error': str(exc)}), 403
                ChangeOrder = models.get('ChangeOrder')
                PCO = models.get('PotentialChangeOrder')
                linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PCO) if ChangeOrder and PCO else ([], [])
                if request.method == 'GET':
                    ctx = get_rfi_responder_context(rfi, current_user, linked_cos, linked_pcos)
                    return jsonify({'ok': True, **ctx})
                body = request.get_json(silent=True) or {}
                action = body.get('action')
                try:
                    assert_rfi_workflow_allowed(current_user)
                except PermissionError as exc:
                    return jsonify({'error': str(exc)}), 403
                execute_rfi_action(rfi, action, current_user, User, body)
                _workflow_session().commit()
                ctx = get_rfi_responder_context(rfi, current_user, linked_cos, linked_pcos)
                return jsonify({'ok': True, 'action': action, **ctx})

            if module_key in ('co', 'change_order', 'change_orders'):
                from workflow_responder import get_co_responder_context, execute_co_action
                ChangeOrder = models.get('ChangeOrder')
                ChangeOrderAllocation = models.get('ChangeOrderAllocation')
                if not ChangeOrder:
                    return jsonify({'error': 'Change order module unavailable'}), 500
                co = ChangeOrder.query.get_or_404(entity_id)
                try:
                    require_financial_project_access(current_user, co.project_id, Project)
                except (ValueError, PermissionError) as exc:
                    return jsonify({'error': str(exc)}), 403
                allocs = []
                if ChangeOrderAllocation:
                    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
                alloc_payload = [{
                    'cost_code': a.cost_code,
                    'cost_type': getattr(a, 'cost_type', None),
                    'amount': a.amount,
                    'description': getattr(a, 'description', ''),
                } for a in allocs]
                if request.method == 'GET':
                    ctx = get_co_responder_context(co, current_user, allocs)
                    return jsonify({'ok': True, **ctx})
                body = request.get_json(silent=True) or {}
                workflow_deps = {
                    'ChangeOrder': ChangeOrder,
                    'ChangeOrderAllocation': ChangeOrderAllocation,
                    'PayAppProjectState': models.get('PayAppProjectState'),
                    'ScheduleData': models.get('ScheduleData'),
                    'Project': models.get('Project'),
                    'BudgetProjectState': models.get('BudgetProjectState'),
                    'db': db,
                    'Commitment': models.get('Commitment'),
                    'CommitmentAllocation': models.get('CommitmentAllocation'),
                    'SageSyncEvent': models.get('SageSyncEvent'),
                    'generate_next_number_fn': models.get('generate_next_number_fn'),
                    'developer_unlock_bypass': models.get('developer_unlock_bypass', lambda: False)(),
                }
                action, co_dict, wf_result = execute_co_action(
                    co, body.get('action'), current_user, User, body,
                    ChangeOrderAllocation, workflow_deps=workflow_deps,
                )
                _workflow_session().commit()
                ctx = get_co_responder_context(co, current_user, allocs)
                return jsonify({
                    'ok': True,
                    'action': action,
                    'change_order': co_dict,
                    'new_status': wf_result.get('new_status'),
                    'final_approved': wf_result.get('final_approved'),
                    'sync_result': wf_result.get('sync_result'),
                    'budget_sync_result': wf_result.get('budget_sync_result'),
                    'auto_sub_change_orders': wf_result.get('auto_sub_change_orders'),
                    **ctx,
                })

            if module_key in ('pay_applications', 'pay_app', 'payapp', 'g702'):
                from pay_app_persistence import get_pay_app_state
                from workflow_responder import get_pay_app_responder_context, execute_pay_app_action
                PayAppProjectState = models.get('PayAppProjectState')
                if not PayAppProjectState:
                    return jsonify({'error': 'Pay application module unavailable'}), 500
                project_id = request.args.get('project_id', type=int) or (
                    models.get('get_current_project_id')() if models.get('get_current_project_id') else None
                )
                if not project_id:
                    return jsonify({'error': 'project_id required'}), 400
                try:
                    require_financial_project_access(current_user, project_id, Project)
                except (ValueError, PermissionError) as exc:
                    return jsonify({'error': str(exc)}), 403
                from access_control import user_global_flags
                if user_global_flags(current_user).get('hide_financials'):
                    return jsonify({'error': 'Financial data is not available for your account.'}), 403
                record, state = get_pay_app_state(PayAppProjectState, project_id)
                period = (state or {}).get('currentPayAppPeriod') or {}
                if entity_id and str(period.get('periodNumber')) != str(entity_id):
                    for hist in (state or {}).get('payAppHistory') or []:
                        if str(hist.get('periodNumber')) == str(entity_id):
                            period = hist.get('period') or period
                            break
                if request.method == 'GET':
                    ctx = get_pay_app_responder_context(project_id, period, current_user, state)
                    return jsonify({'ok': True, **ctx})
                body = request.get_json(silent=True) or {}
                workflow_deps = {
                    'PayAppProjectState': PayAppProjectState,
                    'db': db,
                    'ChangeOrder': models.get('ChangeOrder'),
                    'ChangeOrderAllocation': models.get('ChangeOrderAllocation'),
                    'BudgetProjectState': models.get('BudgetProjectState'),
                    'Commitment': models.get('Commitment'),
                    'CommitmentAllocation': models.get('CommitmentAllocation'),
                    'Project': models.get('Project'),
                    'SageSyncEvent': models.get('SageSyncEvent'),
                    'get_state': lambda: get_pay_app_state(PayAppProjectState, project_id),
                }
                action, ctx, wf_result = execute_pay_app_action(
                    project_id, period, body.get('action'), current_user, User, body,
                    workflow_deps=workflow_deps,
                )
                _workflow_session().commit()
                return jsonify({
                    'ok': True,
                    'action': action,
                    'new_status': wf_result.get('new_status'),
                    'final_approved': wf_result.get('final_approved'),
                    'sage_result': wf_result.get('sage_result'),
                    **ctx,
                })

            return jsonify({'error': f'Unsupported module: {module}'}), 400
        except ValueError as exc:
            _workflow_session().rollback()
            return jsonify({'error': str(exc)}), 400
