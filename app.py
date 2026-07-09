



# ============================================================
# Case PM - Ultimate Construction Project Management System
# Cleaned & Completed Full Version (vFinal)
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
import sys
import json
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'case-pm-ultimate-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///case_pm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB for large drawing sets

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"

# Endpoints that are not scoped to a single project (portfolio / admin).
PROJECT_AGNOSTIC_ENDPOINTS = frozenset({
    'dashboard',
    'projects_page',
    'project_detail',
    'create_project',
    'email_page',
    'companies_page',
    'create_company',
    'upload_coi',
    'user_management',
    'create_user',
    'delete_user',
    'program_settings',
    'audit_log',
    'audit_log_page',
    'notifications',
    'mark_notification_read',
    'profile',
    'update_profile',
    'search',
    'login',
    'logout',
    'force_change_password',
    'static',
    'favicon',
    'api_stats',
    'api_current_project',
    'api_portfolio_schedules',
})

CURRENT_PROJECT_SESSION_KEY = 'current_project_id'


# ==================== PERMISSION DECORATORS ====================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Admin':
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(permission):
                flash("Permission denied.", "error")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ==================== USER MODEL ====================
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='Viewer')
    company = db.Column(db.String(120))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
    permissions_json = db.Column(db.Text)
    status = db.Column(db.String(20), default='Active')
    must_change_password = db.Column(db.Boolean, default=True)
    require_2fa = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def has_permission(self, permission):
        if self.role == 'Admin':
            return True
        try:
            from case_workflow import get_role_permissions, user_can_approve
            perms = get_role_permissions(self)
            if perms.get('modules') == '*':
                return True
            if permission in (perms.get('modules') or []):
                return True
            return user_can_approve(self, permission)
        except Exception:
            return False

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== DATABASE MODELS ====================

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(200), nullable=False)
    client = db.Column(db.String(150))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    contract_value = db.Column(db.Float)
    status = db.Column(db.String(50), default='Active')
    percent_complete = db.Column(db.Integer, default=0)
    project_manager = db.Column(db.String(120))
    sage_job_number = db.Column(db.String(50))
    accounting_project_number = db.Column(db.String(50))
    stage = db.Column(db.String(80))
    project_type = db.Column(db.String(80))
    description = db.Column(db.Text)
    details_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_details(self):
        if not self.details_json:
            return {}
        try:
            return json.loads(self.details_json)
        except (TypeError, json.JSONDecodeError):
            return {}

    def set_details(self, data):
        self.details_json = json.dumps(data or {})

    def location_label(self):
        parts = [p for p in [self.city, self.state] if p]
        if parts:
            return ', '.join(parts)
        return self.address or '—'

    def has_original_contract(self):
        pdf_path = os.path.join(
            app.config.get('UPLOAD_FOLDER', 'uploads'),
            'contracts',
            str(self.id),
            'original_contract.pdf',
        )
        return os.path.isfile(pdf_path)

    def has_project_logo(self):
        meta = _read_project_asset_meta(self.id, 'projects')
        if not meta or not meta.get('filename'):
            return False
        path = os.path.join(_project_asset_folder(self.id, 'projects'), meta['filename'])
        return os.path.isfile(path)

    def project_logo_url(self):
        if not self.has_project_logo():
            return None
        return url_for('serve_project_logo', project_id=int(self.id))

    def to_dict(self):
        d = self.get_details()
        return {
            'id': self.id,
            'number': self.number or '',
            'name': self.name or '',
            'client': self.client or '',
            'address': self.address or '',
            'city': self.city or '',
            'state': self.state or '',
            'zip_code': self.zip_code or '',
            'start_date': self.start_date.isoformat() if self.start_date else '',
            'end_date': self.end_date.isoformat() if self.end_date else '',
            'contract_value': self.contract_value or 0,
            'status': self.status or 'Active',
            'percent_complete': self.percent_complete or 0,
            'project_manager': self.project_manager or '',
            'sage_job_number': self.sage_job_number or '',
            'accounting_project_number': self.accounting_project_number or '',
            'stage': self.stage or '',
            'project_type': self.project_type or '',
            'description': self.description or '',
            'has_original_contract': self.has_original_contract(),
            'has_project_logo': self.has_project_logo(),
            'logo_url': self.project_logo_url(),
            **d,
        }


def get_current_project_id():
    """Resolve the active project id from URL, session, or first project."""
    if not current_user.is_authenticated:
        return None

    project_id = request.args.get('project_id', type=int)
    if project_id:
        if Project.query.get(project_id):
            session[CURRENT_PROJECT_SESSION_KEY] = project_id
            return project_id
        return None

    stored = session.get(CURRENT_PROJECT_SESSION_KEY)
    if stored:
        try:
            stored_id = int(stored)
            if Project.query.get(stored_id):
                return stored_id
        except (TypeError, ValueError):
            pass

    first = Project.query.order_by(Project.name).first()
    if first:
        session[CURRENT_PROJECT_SESSION_KEY] = first.id
        return first.id
    return None


def get_active_project():
    pid = get_current_project_id()
    return Project.query.get(pid) if pid else None


def query_for_active_project(model):
    """Filter a SQLAlchemy model query to the current project."""
    q = model.query
    project = get_active_project()
    if project is not None:
        q = q.filter_by(project_id=project.id)
    return q


def redirect_with_project(endpoint, **values):
    """Redirect to a project-scoped page, preserving current project."""
    if endpoint not in PROJECT_AGNOSTIC_ENDPOINTS:
        pid = get_current_project_id()
        if pid and 'project_id' not in values:
            values['project_id'] = pid
    return redirect(url_for(endpoint, **values))


@app.context_processor
def inject_project_context():
    if not current_user.is_authenticated:
        return {}
    active = get_active_project()
    portal = {}
    try:
        from case_workflow import get_role_permissions, user_portal_type, is_sub_user, is_architect_user
        portal = {
            'portal_type': user_portal_type(current_user),
            'is_sub_portal': is_sub_user(current_user),
            'is_architect_portal': is_architect_user(current_user),
            'role_permissions': get_role_permissions(current_user),
        }
    except Exception:
        portal = {'portal_type': 'staff', 'is_sub_portal': False, 'is_architect_portal': False}
    return {
        'active_project': active,
        'project_name': active.name if active else 'Select Project',
        'all_projects': Project.query.order_by(Project.name).all(),
        **portal,
    }


class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.Date, nullable=False)
    weather = db.Column(db.String(100))
    work_performed = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ManpowerEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'))
    company = db.Column(db.String(150))
    personnel_count = db.Column(db.Integer)
    hours = db.Column(db.Float)
    work_performed = db.Column(db.Text)


class EquipmentEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'))
    equipment_name = db.Column(db.String(150))
    quantity = db.Column(db.Integer, default=1)
    condition = db.Column(db.String(100))


class RFI(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    number = db.Column(db.String(30), unique=True)
    subject = db.Column(db.String(200), nullable=False)
    question = db.Column(db.Text)
    priority = db.Column(db.String(20), default='Medium')
    status = db.Column(db.String(30), default='Open')
    date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    drawing_reference = db.Column(db.String(100))
    spec_reference = db.Column(db.String(100))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    from_party = db.Column(db.String(150))
    to_party = db.Column(db.String(150))
    received_from_company = db.Column(db.String(200))
    received_from_contact = db.Column(db.String(150))
    responsible_contractor = db.Column(db.String(200))
    rfi_manager_name = db.Column(db.String(150))
    assignees_json = db.Column(db.Text)
    distribution_json = db.Column(db.Text)
    ball_in_court_role = db.Column(db.String(80))
    official_answer = db.Column(db.Text)
    answered_at = db.Column(db.DateTime)
    answered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.Column(db.Text)
    cost_impact_amount = db.Column(db.Float, default=0)
    schedule_impact_days = db.Column(db.Integer, default=0)
    schedule_impact_label = db.Column(db.String(50))
    is_private = db.Column(db.Integer, default=0)
    attachments_json = db.Column(db.Text)
    responses_json = db.Column(db.Text)
    plan_pins_json = db.Column(db.Text)
    linked_pco_id = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime)
    location_description = db.Column(db.String(300))
    discipline = db.Column(db.String(80))


class Drawing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    sheet_number = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(300))
    discipline = db.Column(db.String(80))
    section_prefix = db.Column(db.String(10))
    sort_key = db.Column(db.String(40))
    status = db.Column(db.String(30), default='Current')
    current_revision_id = db.Column(db.Integer)
    thumbnail_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('project_id', 'sheet_number', name='uq_drawing_project_sheet'),)


class DrawingRevision(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drawing_id = db.Column(db.Integer, db.ForeignKey('drawing.id'), nullable=False)
    revision_number = db.Column(db.String(20), default='0')
    revision_label = db.Column(db.String(40))
    drawing_date = db.Column(db.Date)
    received_date = db.Column(db.Date)
    set_name = db.Column(db.String(150))
    file_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(300))
    is_current = db.Column(db.Boolean, default=True)
    superseded_at = db.Column(db.DateTime)
    upload_source = db.Column(db.String(40))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)


class DrawingMarkup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drawing_id = db.Column(db.Integer, db.ForeignKey('drawing.id'), nullable=False)
    revision_id = db.Column(db.Integer, db.ForeignKey('drawing_revision.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_name = db.Column(db.String(150))
    layer = db.Column(db.String(20), default='personal')
    markup_type = db.Column(db.String(30), nullable=False)
    geometry_json = db.Column(db.Text)
    style_json = db.Column(db.Text)
    label = db.Column(db.String(300))
    linked_rfi_id = db.Column(db.Integer, db.ForeignKey('rfi.id'))
    measurement_value = db.Column(db.Float)
    measurement_unit = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published_at = db.Column(db.DateTime)


class ChangeOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    number = db.Column(db.String(30), unique=True)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float)
    reason = db.Column(db.String(200))
    schedule_impact = db.Column(db.String(100))
    status = db.Column(db.String(30), default='Pending')
    date = db.Column(db.Date)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cost_code = db.Column(db.String(30))
    requested_by = db.Column(db.String(150))
    priority = db.Column(db.String(20))
    revision = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    sov_synced_at = db.Column(db.DateTime)
    sage_sync_status = db.Column(db.String(30))
    title = db.Column(db.String(200))
    company_name = db.Column(db.String(200))
    company_id = db.Column(db.String(64))
    contact_name = db.Column(db.String(150))
    contact_email = db.Column(db.String(150))
    contact_phone = db.Column(db.String(50))
    ball_in_court_role = db.Column(db.String(80))
    source_pco_id = db.Column(db.Integer)
    schedule_impact_days = db.Column(db.Integer, default=0)
    contract_type = db.Column(db.String(40), default='Owner')
    submitted_at = db.Column(db.DateTime)
    attachments_json = db.Column(db.Text)
    linked_rfi_id = db.Column(db.Integer, db.ForeignKey('rfi.id'), nullable=True)
    linked_commitment_ref = db.Column(db.String(80))
    approval_stage = db.Column(db.Integer, default=0)
    plan_pins_json = db.Column(db.Text)


class ChangeOrderAllocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    amount = db.Column(db.Float, default=0)
    sov_line_legacy_id = db.Column(db.String(64))
    description = db.Column(db.String(200))


class ChangeOrderRevision(db.Model):
    __tablename__ = 'change_order_revision'
    id = db.Column(db.Integer, primary_key=True)
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=False)
    revision = db.Column(db.Integer, default=0)
    snapshot_json = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PotentialChangeOrder(db.Model):
    __tablename__ = 'potential_change_order'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    estimated_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default='Open')
    reason = db.Column(db.String(200))
    priority = db.Column(db.String(20), default='Medium')
    schedule_impact_days = db.Column(db.Integer, default=0)
    company_name = db.Column(db.String(200))
    company_id = db.Column(db.String(64))
    contact_name = db.Column(db.String(150))
    contact_email = db.Column(db.String(150))
    contact_phone = db.Column(db.String(50))
    requested_by = db.Column(db.String(150))
    ball_in_court_role = db.Column(db.String(80), default='Project Manager')
    cost_code = db.Column(db.String(30))
    notes = db.Column(db.Text)
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=True)
    linked_rfi_id = db.Column(db.Integer, db.ForeignKey('rfi.id'), nullable=True)
    linked_commitment_ref = db.Column(db.String(80))
    attachments_json = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PCOAllocation(db.Model):
    __tablename__ = 'pco_allocation'
    id = db.Column(db.Integer, primary_key=True)
    pco_id = db.Column(db.Integer, db.ForeignKey('potential_change_order.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    amount = db.Column(db.Float, default=0)
    description = db.Column(db.String(200))


class Commitment(db.Model):
    __tablename__ = 'commitment'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text, nullable=False)
    commitment_type = db.Column(db.String(40), default='Purchase Order')
    status = db.Column(db.String(40), default='Draft')
    original_amount = db.Column(db.Float, default=0)
    approved_changes = db.Column(db.Float, default=0)
    current_amount = db.Column(db.Float, default=0)
    company_name = db.Column(db.String(200))
    company_id = db.Column(db.String(64))
    contact_name = db.Column(db.String(150))
    contact_email = db.Column(db.String(150))
    contact_phone = db.Column(db.String(50))
    date = db.Column(db.Date)
    executed_date = db.Column(db.Date)
    retainage_percent = db.Column(db.Float, default=0)
    aia_form = db.Column(db.String(20), default='N/A')
    payment_terms = db.Column(db.String(120))
    scope_of_work = db.Column(db.Text)
    notes = db.Column(db.Text)
    ball_in_court_role = db.Column(db.String(80), default='Creator')
    approval_stage = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    signature_method = db.Column(db.String(30), default='internal')
    signature_status = db.Column(db.String(40), default='unsigned')
    docusign_envelope_id = db.Column(db.String(120))
    docusign_status = db.Column(db.String(60))
    signed_document_url = db.Column(db.String(400))
    certified_signatures_json = db.Column(db.Text)
    attachments_json = db.Column(db.Text)
    sage_sync_status = db.Column(db.String(60))
    budget_validated = db.Column(db.Boolean, default=False)
    invoiced_amount = db.Column(db.Float, default=0)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    billing_type = db.Column(db.String(40), default='Lump Sum')
    bond_required = db.Column(db.Boolean, default=False)
    insurance_requirements = db.Column(db.Text)
    owner_name = db.Column(db.String(200))
    contractor_name = db.Column(db.String(200))
    architect_engineer = db.Column(db.String(200))
    delivery_date = db.Column(db.Date)
    freight_terms = db.Column(db.String(120))
    tax_exempt = db.Column(db.Boolean, default=False)
    aia_contract_json = db.Column(db.Text)
    external_document_provider = db.Column(db.String(40))
    external_document_id = db.Column(db.String(200))
    external_document_url = db.Column(db.String(500))
    catina_project_id = db.Column(db.String(120))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CommitmentAllocation(db.Model):
    __tablename__ = 'commitment_allocation'
    id = db.Column(db.Integer, primary_key=True)
    commitment_id = db.Column(db.Integer, db.ForeignKey('commitment.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    amount = db.Column(db.Float, default=0)
    description = db.Column(db.String(200))


class PayAppProjectState(db.Model):
    __tablename__ = 'pay_app_project_state'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), unique=True, nullable=False)
    data_json = db.Column(db.Text, default='{}')
    version = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class BudgetProjectState(db.Model):
    __tablename__ = 'budget_project_state'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), unique=True, nullable=False)
    data_json = db.Column(db.Text, default='{}')
    version = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class SageSyncEvent(db.Model):
    __tablename__ = 'sage_sync_event'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), default='queued')
    sage_job_number = db.Column(db.String(80))
    message = db.Column(db.Text)
    payload_json = db.Column(db.Text)
    response_json = db.Column(db.Text)
    error_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posted_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Submittal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    number = db.Column(db.String(30), unique=True)
    description = db.Column(db.String(200), nullable=False)
    spec_section = db.Column(db.String(20))
    status = db.Column(db.String(30), default='Pending')
    priority = db.Column(db.String(20), default='Medium')
    submitted_by = db.Column(db.String(150))
    date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    ball_in_court = db.Column(db.String(50))
    review_comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PunchItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    number = db.Column(db.String(30))
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(150))
    trade = db.Column(db.String(80))
    priority = db.Column(db.String(20), default='Medium')
    status = db.Column(db.String(30), default='Open')
    due_date = db.Column(db.Date)
    assigned_to = db.Column(db.String(100))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    plan_pins_json = db.Column(db.Text)


class SafetyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    number = db.Column(db.String(30))
    type = db.Column(db.String(30))
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(150))
    severity = db.Column(db.String(20))
    status = db.Column(db.String(30), default='Open')
    immediate_actions = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    corrective_actions = db.Column(db.Text)
    assigned_to = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    reported_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ScheduleTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    number = db.Column(db.String(30))
    description = db.Column(db.String(200), nullable=False)
    phase = db.Column(db.String(80))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    duration_days = db.Column(db.Integer)
    percent_complete = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default='Not Started')
    predecessor = db.Column(db.String(50))
    assigned_to = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ScheduleData(db.Model):
    """Full CPM schedule payload (Gantt tasks + links) per project."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), unique=True, nullable=False)
    payload = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    type = db.Column(db.String(50))
    contact_first_name = db.Column(db.String(80))
    contact_last_name = db.Column(db.String(80))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    license_number = db.Column(db.String(50))
    tax_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class COI(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'))
    expiration_date = db.Column(db.Date)
    file_path = db.Column(db.String(300))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'))
    filename = db.Column(db.String(200), nullable=False)
    caption = db.Column(db.String(300))
    category = db.Column(db.String(50))
    taken_at = db.Column(db.DateTime)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WeeklyReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    week_ending = db.Column(db.Date, nullable=False)
    work_performed = db.Column(db.Text)
    safety_notes = db.Column(db.Text)
    status = db.Column(db.String(30), default='Draft')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')


# ==================== FILE UPLOAD HELPERS ====================
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'docx', 'xlsx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'photos'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'coi'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'documents'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'attachments'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'change_orders'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'spec_books'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'contracts'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'projects'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'commitments'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'drawings'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'rfis'), exist_ok=True)

LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_logo_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in LOGO_EXTENSIONS


def _project_asset_folder(project_id, subfolder):
    return os.path.join(app.config['UPLOAD_FOLDER'], subfolder, str(project_id))


def _read_project_asset_meta(project_id, subfolder):
    meta_path = os.path.join(_project_asset_folder(project_id, subfolder), 'meta.json')
    if not os.path.isfile(meta_path):
        return None
    try:
        with open(meta_path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def save_uploaded_file(file, folder='photos'):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        filename = f"{timestamp}_{filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(upload_path, exist_ok=True)
        file_path = os.path.join(upload_path, filename)
        file.save(file_path)
        return filename
    return None




# ==================== HELPER FUNCTIONS ====================

def generate_next_number(prefix, model_class):
    """Generate next sequential number (e.g. RFI-001, CO-042, PL-007)"""
    last_record = model_class.query.order_by(model_class.number.desc()).first()
    if last_record and last_record.number:
        try:
            last_num = int(last_record.number.split('-')[-1])
            return f"{prefix}-{last_num + 1:03d}"
        except:
            pass
    return f"{prefix}-001"


def get_dashboard_stats():
    """Returns key statistics for the dashboard."""
    stats = {
        'total_projects': Project.query.count(),
        'active_projects': Project.query.filter(Project.status.in_(['Active', 'Pre-Construction'])).count(),
        'open_rfis': RFI.query.filter(RFI.status.in_(['Open', 'Awaiting Response', 'Under Review'])).count(),
        'overdue_rfis': RFI.query.filter(
            RFI.due_date < datetime.utcnow().date(),
            RFI.status.in_(['Open', 'Awaiting Response', 'Under Review'])
        ).count(),
        'open_change_orders': ChangeOrder.query.filter(ChangeOrder.status == 'Pending').count(),
        'open_punch_items': PunchItem.query.filter(PunchItem.status != 'Completed').count(),
        'high_priority_punch': PunchItem.query.filter(
            PunchItem.priority == 'High',
            PunchItem.status != 'Completed'
        ).count(),
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(status='Active').count(),
    }
    return stats


# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if not user:
            flash('No account found with that email address.', 'error')
            return render_template('login.html')

        if not user.check_password(password):
            flash('Incorrect password. Please try again.', 'error')
            return render_template('login.html')

        if user.status != 'Active':
            flash('Your account has been deactivated. Please contact an administrator.', 'error')
            return render_template('login.html')

        login_user(user, remember=remember)
        user.last_login = datetime.utcnow()
        db.session.commit()

        if user.must_change_password:
            flash('You must change your password before continuing.', 'warning')
            return redirect(url_for('force_change_password'))

        flash(f'Welcome back, {user.first_name}!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/force-change-password', methods=['GET', 'POST'])
@login_required
def force_change_password():
    if not current_user.must_change_password:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('force_change_password.html')

        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('force_change_password.html')

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()

        flash('Password changed successfully! Please log in again.', 'success')
        logout_user()
        return redirect(url_for('login'))

    return render_template('force_change_password.html')


# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    stats = get_dashboard_stats()
    projects = Project.query.order_by(Project.created_at.desc()).limit(8).all()
    recent_daily_logs = DailyLog.query.order_by(DailyLog.date.desc()).limit(6).all()
    upcoming_tasks = ScheduleTask.query.filter(
        ScheduleTask.status.in_(['Not Started', 'In Progress'])
    ).order_by(ScheduleTask.end_date.asc()).limit(8).all()

    return render_template(
        'dashboard.html',
        stats=stats,
        projects=projects,
        recent_daily_logs=recent_daily_logs,
        upcoming_tasks=upcoming_tasks
    )


@app.route('/api/current-project', methods=['GET', 'POST'])
@login_required
def api_current_project():
    """Get or set the session-scoped current project."""
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        project_id = data.get('project_id')
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'project_id required'}), 400
        project = Project.query.get(project_id)
        if not project:
            return jsonify({'error': 'Invalid project_id'}), 404
        session[CURRENT_PROJECT_SESSION_KEY] = project_id
        return jsonify({
            'ok': True,
            'project_id': project.id,
            'name': project.name,
            'number': project.number,
            'address': project.address,
        })

    active = get_active_project()
    if not active:
        return jsonify({'project_id': None, 'name': None, 'number': None, 'address': None})
    d = active.to_dict()
    return jsonify({
        'project_id': active.id,
        'name': active.name,
        'number': active.number,
        'address': active.address,
        'city': active.city,
        'state': active.state,
        'zip_code': active.zip_code,
        'client': active.client,
        'contract_value': active.contract_value,
        'contract_amount': _project_contract_amount(active),
        'contract_amount_source': (
            'original_contract' if _parse_float(d.get('original_contract_amount')) is not None else
            ('contract_value' if active.contract_value else None)
        ),
        'sage_job_number': active.sage_job_number or active.accounting_project_number,
        'accounting_project_number': active.accounting_project_number,
        'prime_aia_form': d.get('prime_aia_form'),
        'owner_legal_name': d.get('owner_legal_name') or active.client,
        'contractor_legal_name': d.get('contractor_legal_name'),
        'architect_of_record': d.get('architect_of_record') or d.get('architect_firm'),
        'default_retainage_percent': d.get('default_retainage_percent'),
        'catina_project_id': d.get('catina_project_id'),
        'catina_document_url': d.get('catina_document_url'),
        'original_contract_amount': d.get('original_contract_amount'),
        'contract_execution_date': d.get('contract_execution_date'),
        'notice_to_proceed_date': d.get('notice_to_proceed_date'),
        'sage_contract_number': d.get('sage_contract_number'),
        'sage_billings_account': d.get('sage_billings_account'),
        'sage_wip_account': d.get('sage_wip_account'),
        'sage_ar_customer_code': d.get('sage_ar_customer_code'),
        'has_original_contract': active.has_original_contract(),
        'has_project_logo': active.has_project_logo(),
        'logo_url': active.project_logo_url(),
    })




# ==================== PROJECTS ROUTES ====================

PROJECT_DETAIL_FIELDS = [
    'bid_type', 'program', 'delivery_method', 'financing', 'owner_type', 'square_feet',
    'departments', 'office', 'county', 'country', 'region', 'designated_market_area',
    'timezone', 'latitude', 'longitude', 'phone', 'fax', 'store_number', 'flag_color',
    'actual_start_date', 'projected_finish_date', 'substantial_completion_date',
    'warranty_start_date', 'warranty_end_date',
    'owner_contact_name', 'owner_contact_email', 'owner_contact_phone',
    'architect_firm', 'architect_contact', 'superintendent', 'estimator',
    # Prime contract & AIA
    'original_contract_amount', 'prime_aia_form', 'contractor_legal_name', 'owner_legal_name',
    'architect_of_record', 'architect_license_number', 'contract_execution_date',
    'notice_to_proceed_date', 'catina_project_id', 'catina_document_url',
    'default_retainage_percent', 'default_billing_period', 'bond_required',
    'performance_bond_amount', 'payment_bond_amount', 'insurance_gl_limit',
    'insurance_auto_limit', 'prevailing_wage', 'building_permit_number', 'ahj_authority',
    'lien_state', 'ocip_ccip', 'contingency_amount', 'allowances_total',
    # Sage 300 CRE
    'sage_contract_number', 'sage_account_set', 'sage_accounting_method',
    'sage_billings_account', 'sage_wip_account', 'sage_revenue_account',
    'sage_ar_customer_code', 'sage_default_tax_group', 'sage_company_code',
    'sage_database', 'sage_ap_vendor_prefix', 'sage_cost_code_prefix',
    'sage_subcontract_liability_account', 'sage_default_cost_type', 'sage_sync_enabled',
    'parent_project_id', 'project_template', 'notes',
]


def ensure_project_schema():
    """Add new Project columns on existing SQLite databases."""
    from sqlalchemy import inspect, text, func
    inspector = inspect(db.engine)
    if 'project' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('project')}
    additions = {
        'city': 'VARCHAR(100)',
        'state': 'VARCHAR(50)',
        'zip_code': 'VARCHAR(20)',
        'project_manager': 'VARCHAR(120)',
        'sage_job_number': 'VARCHAR(50)',
        'accounting_project_number': 'VARCHAR(50)',
        'stage': 'VARCHAR(80)',
        'project_type': 'VARCHAR(80)',
        'description': 'TEXT',
        'details_json': 'TEXT',
        'updated_at': 'DATETIME',
    }
    for col, typedef in additions.items():
        if col not in existing:
            db.session.execute(text(f'ALTER TABLE project ADD COLUMN {col} {typedef}'))
    db.session.commit()


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _parse_float(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '').replace('$', ''))
    except (TypeError, ValueError):
        return None


def _project_contract_amount(project):
    """Prefer original_contract_amount from project details, then contract_value."""
    if not project:
        return None
    details = project.get_details()
    original = _parse_float(details.get('original_contract_amount'))
    if original is not None:
        return original
    if project.contract_value:
        return float(project.contract_value)
    return None


def _project_financial_context(project):
    """Shared contract/retainage defaults for budget and pay applications."""
    if not project:
        return {
            'original_contract_amount': None,
            'contract_value': None,
            'contract_amount': None,
            'contract_amount_source': None,
            'default_retainage_percent': None,
            'sage_job': '',
        }
    details = project.get_details()
    original = _parse_float(details.get('original_contract_amount'))
    contract_value = float(project.contract_value) if project.contract_value else None
    if original is not None:
        amount, source = original, 'original_contract'
    elif contract_value is not None:
        amount, source = contract_value, 'contract_value'
    else:
        amount, source = None, None
    retainage = _parse_float(details.get('default_retainage_percent'))
    return {
        'original_contract_amount': original,
        'contract_value': contract_value,
        'contract_amount': amount,
        'contract_amount_source': source,
        'default_retainage_percent': retainage,
        'sage_job': project.sage_job_number or project.accounting_project_number or '',
    }


def _normalize_project_number(value):
    """Canonical project number — uppercase so PRJ-001 and prj-001 are treated the same."""
    return (value or '').strip().upper()


def _project_number_conflict(number, exclude_project_id=None):
    """Return conflicting Project if number already exists (case-insensitive)."""
    from sqlalchemy import func
    normalized = _normalize_project_number(number)
    if not normalized:
        return None
    q = Project.query.filter(func.upper(Project.number) == normalized)
    if exclude_project_id:
        q = q.filter(Project.id != int(exclude_project_id))
    return q.first()


def _apply_project_form(project, form):
    project.name = (form.get('name') or '').strip()
    project.client = (form.get('client') or '').strip()
    project.address = (form.get('address') or '').strip()
    project.city = (form.get('city') or '').strip()
    project.state = (form.get('state') or '').strip()
    project.zip_code = (form.get('zip_code') or '').strip()
    project.start_date = _parse_date(form.get('start_date'))
    project.end_date = _parse_date(form.get('end_date'))
    project.contract_value = _parse_float(form.get('contract_value')) or 0.0
    project.status = form.get('status') or project.status or 'Active'
    project.percent_complete = int(form.get('percent_complete') or project.percent_complete or 0)
    project.project_manager = (form.get('project_manager') or '').strip()
    project.sage_job_number = (form.get('sage_job_number') or '').strip()
    project.accounting_project_number = (form.get('accounting_project_number') or '').strip()
    project.stage = (form.get('stage') or '').strip()
    project.project_type = (form.get('project_type') or '').strip()
    project.description = (form.get('description') or '').strip()
    if form.get('number'):
        project.number = _normalize_project_number(form.get('number'))
    details = {k: (form.get(k) or '').strip() for k in PROJECT_DETAIL_FIELDS}
    project.set_details(details)
    project.updated_at = datetime.utcnow()


@app.route('/projects')
@login_required
def projects_page():
    ensure_project_schema()
    from sage_service import latest_sage_events_by_project, project_sage_sync_status

    projects = Project.query.order_by(Project.created_at.desc()).all()
    companies = Company.query.order_by(Company.name).all()
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    active_projects = [p for p in projects if p.status == 'Active']
    latest_sage_events = latest_sage_events_by_project(SageSyncEvent, [p.id for p in projects])
    sage_statuses = {
        p.id: project_sage_sync_status(p, latest_sage_events.get(p.id))
        for p in projects
    }
    stats = {
        'total': len(projects),
        'active': len(active_projects),
        'completed': sum(1 for p in projects if p.status == 'Completed'),
        'on_hold': sum(1 for p in projects if p.status == 'On Hold'),
        'pre_construction': sum(1 for p in projects if p.status == 'Pre-Construction'),
        'contract_value': sum(p.contract_value or 0 for p in projects),
        'active_value': sum(p.contract_value or 0 for p in active_projects),
        'avg_percent_complete': (
            round(sum(p.percent_complete or 0 for p in active_projects) / len(active_projects))
            if active_projects else 0
        ),
    }
    return render_template(
        'projects.html',
        projects=projects,
        companies=companies,
        users=users,
        stats=stats,
        sage_statuses=sage_statuses,
    )


@app.route('/projects/create', methods=['POST'])
@login_required
def create_project():
    ensure_project_schema()
    try:
        name = request.form.get('name')
        if not name:
            flash('Project name is required.', 'error')
            return redirect(url_for('projects_page'))

        next_num = Project.query.count() + 1
        raw_number = request.form.get('number') or f"PRJ-{next_num:03d}"
        number = _normalize_project_number(raw_number)
        conflict = _project_number_conflict(number)
        if conflict:
            flash(f'Project number "{number}" is already used by "{conflict.name}". Project numbers are not case-sensitive.', 'error')
            return redirect(url_for('projects_page'))

        project = Project(
            number=number,
            name=name,
        )
        _apply_project_form(project, request.form)

        db.session.add(project)
        db.session.commit()

        log = AuditLog(
            user_id=current_user.id,
            action='Created Project',
            target_type='Project',
            target_id=project.id,
            details=f'Project "{name}" was created'
        )
        db.session.add(log)
        db.session.commit()

        flash(f'Project "{name}" created successfully!', 'success')
        return redirect(url_for('projects_page'))

    except Exception as e:
        db.session.rollback()
        err = str(e)
        if 'UNIQUE constraint failed' in err and 'project.number' in err:
            flash('That project number is already in use (not case-sensitive).', 'error')
        else:
            flash(f'Error creating project: {err}', 'error')
        return redirect(url_for('projects_page'))


@app.route('/projects/<int:project_id>/update', methods=['POST'])
@login_required
def update_project(project_id):
    ensure_project_schema()
    project = Project.query.get_or_404(project_id)
    try:
        new_number = _normalize_project_number(request.form.get('number') or project.number)
        conflict = _project_number_conflict(new_number, exclude_project_id=project_id)
        if conflict:
            msg = f'Project number "{new_number}" is already used by "{conflict.name}". Project numbers are not case-sensitive.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('projects_page'))

        _apply_project_form(project, request.form)
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'ok': True, 'project': project.to_dict()})
        flash(f'Project "{project.name}" updated successfully!', 'success')
        return redirect(url_for('projects_page'))
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': str(e)}), 400
        flash(f'Error updating project: {str(e)}', 'error')
        return redirect(url_for('projects_page'))


@app.route('/api/projects/validate-number', methods=['GET'])
@login_required
def api_validate_project_number():
    number = _normalize_project_number(request.args.get('number', ''))
    exclude_id = request.args.get('exclude_id', type=int)
    if not number:
        return jsonify({'ok': False, 'error': 'Project number required'})
    conflict = _project_number_conflict(number, exclude_project_id=exclude_id)
    if conflict:
        return jsonify({
            'ok': False,
            'available': False,
            'error': f'Project number "{number}" is already used by "{conflict.name}".',
            'conflict_project_id': conflict.id,
        })
    return jsonify({'ok': True, 'available': True, 'number': number})


@app.route('/api/projects/<int:project_id>')
@login_required
def api_get_project(project_id):
    ensure_project_schema()
    project = Project.query.get_or_404(project_id)
    return jsonify(project.to_dict())


@app.route('/projects/<int:project_id>/status', methods=['POST'])
@login_required
def update_project_status(project_id):
    ensure_project_schema()
    project = Project.query.get_or_404(project_id)
    data = request.get_json(silent=True) or {}
    status = data.get('status') or request.form.get('status')
    if status:
        project.status = status
        project.updated_at = datetime.utcnow()
        db.session.commit()
    return jsonify({'ok': True, 'status': project.status})


@app.route('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('project_detail.html', project=project)


# ==================== DAILY LOG ROUTES ====================

@app.route('/daily-log')
@login_required
def daily_log():
    logs = query_for_active_project(DailyLog).order_by(DailyLog.date.desc()).limit(30).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('daily_log.html', logs=logs, projects=projects)


@app.route('/daily-log/create', methods=['POST'])
@login_required
def create_daily_log():
    try:
        project_id = request.form.get('project_id')
        date_str = request.form.get('date')
        weather = request.form.get('weather')
        work_performed = request.form.get('work_performed')
        notes = request.form.get('notes')

        if not project_id or not date_str:
            flash('Project and Date are required.', 'error')
            return redirect_with_project('daily_log')

        log = DailyLog(
            project_id=int(project_id),
            user_id=current_user.id,
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            weather=weather,
            work_performed=work_performed,
            notes=notes
        )

        db.session.add(log)
        db.session.commit()

        flash('Daily Log saved successfully!', 'success')
        return redirect_with_project('daily_log')

    except Exception as e:
        db.session.rollback()
        flash(f'Error saving daily log: {str(e)}', 'error')
        return redirect_with_project('daily_log')


# ==================== FILE UPLOAD ROUTES ====================

@app.route('/photos/upload', methods=['POST'])
@login_required
def upload_photo():
    file = request.files.get('photo')
    project_id = request.form.get('project_id')
    caption = request.form.get('caption')

    filename = save_uploaded_file(file, folder='photos')

    if filename:
        photo = Photo(
            project_id=project_id if project_id else None,
            filename=filename,
            caption=caption,
            uploaded_by_id=current_user.id,
            taken_at=datetime.utcnow()
        )
        db.session.add(photo)
        db.session.commit()
        flash('Photo uploaded successfully!', 'success')
    else:
        flash('Invalid file type. Only images and PDFs are allowed.', 'error')

    return redirect(request.referrer or url_for('photos_page'))


@app.route('/companies/<int:company_id>/upload-coi', methods=['POST'])
@login_required
def upload_coi(company_id):
    company = Company.query.get_or_404(company_id)
    file = request.files.get('coi_file')
    expiration_date = request.form.get('expiration_date')

    filename = save_uploaded_file(file, folder='coi')

    if filename:
        coi = COI(
            company_id=company.id,
            expiration_date=datetime.strptime(expiration_date, '%Y-%m-%d').date() if expiration_date else None,
            file_path=filename
        )
        db.session.add(coi)
        db.session.commit()
        flash('Certificate of Insurance uploaded successfully!', 'success')
    else:
        flash('Invalid file type for COI upload.', 'error')

    return redirect(url_for('companies_page'))




# ==================== RFI ROUTES ====================

@app.route('/rfis')
@login_required
def rfis_page():
    return render_template('rfis.html')


@app.route('/rfis/create', methods=['POST'])
@login_required
def create_rfi():
    """Legacy form create — redirects to API-style handling."""
    try:
        project_id = request.form.get('project_id') or get_current_project_id()
        subject = request.form.get('subject')
        if not subject or not project_id:
            flash('Subject and Project are required.', 'error')
            return redirect_with_project('rfis_page')
        from rfi_persistence import apply_rfi_fields
        due_date = request.form.get('due_date')
        rfi = RFI(
            project_id=int(project_id),
            number=generate_next_number('RFI', RFI),
            subject=subject,
            question=request.form.get('question'),
            priority=request.form.get('priority', 'Medium'),
            status=request.form.get('status') or 'Draft',
            date=datetime.utcnow().date(),
            due_date=datetime.strptime(due_date, '%Y-%m-%d').date() if due_date else None,
            created_by_id=current_user.id,
            ball_in_court_role='RFI Manager',
        )
        apply_rfi_fields(rfi, {
            'from_party': request.form.get('from_party'),
            'to_party': request.form.get('to_party'),
            'drawing_reference': request.form.get('drawing_reference'),
            'spec_reference': request.form.get('spec_reference'),
            'notes': request.form.get('notes'),
        })
        db.session.add(rfi)
        db.session.commit()
        flash(f'RFI {rfi.number} created successfully!', 'success')
        return redirect_with_project('rfis_page')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating RFI: {str(e)}', 'error')
        return redirect_with_project('rfis_page')


@app.route('/rfis/<int:rfi_id>/update-status', methods=['POST'])
@login_required
def update_rfi_status(rfi_id):
    rfi = RFI.query.get_or_404(rfi_id)
    new_status = request.form.get('status')

    if new_status:
        old_status = rfi.status
        rfi.status = new_status
        db.session.commit()

        log = AuditLog(
            user_id=current_user.id,
            action='Updated RFI Status',
            target_type='RFI',
            target_id=rfi.id,
            details=f"Changed status from '{old_status}' to '{new_status}'"
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({'success': True, 'new_status': new_status})

    return jsonify({'success': False, 'message': 'No status provided'}), 400


# ==================== RFI REST API ====================

@app.route('/api/rfis/dashboard', methods=['GET'])
@login_required
def api_rfi_dashboard():
    from rfi_persistence import compute_rfi_dashboard
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify(compute_rfi_dashboard(RFI, int(project_id)))


@app.route('/api/rfis', methods=['GET'])
@login_required
def api_list_rfis():
    from rfi_persistence import rfi_to_dict, get_linked_records
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    status = request.args.get('status')
    priority = request.args.get('priority')
    q = RFI.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    rfis = q.order_by(RFI.created_at.desc()).all()
    result = []
    for rfi in rfis:
        linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PotentialChangeOrder)
        result.append(rfi_to_dict(rfi, linked_cos, linked_pcos))
    return jsonify({'rfis': result})


@app.route('/api/rfis/<int:rfi_id>', methods=['GET'])
@login_required
def api_get_rfi(rfi_id):
    from rfi_persistence import rfi_to_dict, get_linked_records
    rfi = RFI.query.get_or_404(rfi_id)
    linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PotentialChangeOrder)
    return jsonify(rfi_to_dict(rfi, linked_cos, linked_pcos))


@app.route('/api/rfis', methods=['POST'])
@login_required
def api_create_rfi():
    from rfi_persistence import apply_rfi_fields, rfi_to_dict
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        subject = (body.get('subject') or '').strip()
        if not subject:
            return jsonify({'error': 'subject required'}), 400
        status = body.get('status') or 'Draft'
        rfi = RFI(
            project_id=int(project_id),
            number=generate_next_number('RFI', RFI),
            subject=subject,
            question=body.get('question'),
            priority=body.get('priority') or 'Medium',
            status=status,
            date=datetime.utcnow().date(),
            created_by_id=current_user.id,
            ball_in_court_role='RFI Manager' if status == 'Draft' else 'Assignee',
        )
        apply_rfi_fields(rfi, body)
        if body.get('create_as_open'):
            rfi.status = 'Open'
            rfi.submitted_at = datetime.utcnow()
            rfi.ball_in_court_role = 'Assignee'
        db.session.add(rfi)
        db.session.commit()
        return jsonify({'ok': True, 'rfi': rfi_to_dict(rfi)})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/rfis/<int:rfi_id>', methods=['PUT'])
@login_required
def api_update_rfi(rfi_id):
    from rfi_persistence import apply_rfi_fields, rfi_to_dict, get_linked_records
    rfi = RFI.query.get_or_404(rfi_id)
    body = request.get_json(silent=True) or {}
    apply_rfi_fields(rfi, body)
    db.session.commit()
    linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PotentialChangeOrder)
    return jsonify({'ok': True, 'rfi': rfi_to_dict(rfi, linked_cos, linked_pcos)})


@app.route('/api/rfis/<int:rfi_id>/workflow', methods=['POST'])
@login_required
def api_rfi_workflow(rfi_id):
    from rfi_persistence import workflow_rfi, rfi_to_dict, add_response, get_linked_records
    rfi = RFI.query.get_or_404(rfi_id)
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    user_name = f'{current_user.first_name} {current_user.last_name}'.strip() or current_user.email
    try:
        if action == 'respond':
            add_response(rfi, body, current_user.id, user_name)
        else:
            workflow_rfi(rfi, action, user_name)
        db.session.commit()
        linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PotentialChangeOrder)
        return jsonify({'ok': True, 'rfi': rfi_to_dict(rfi, linked_cos, linked_pcos)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400


@app.route('/api/rfis/<int:rfi_id>/attachments', methods=['POST'])
@login_required
def api_rfi_upload_attachment(rfi_id):
    from rfi_persistence import apply_rfi_fields, rfi_to_dict, _parse_json
    rfi = RFI.query.get_or_404(rfi_id)
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    safe = secure_filename(f.filename)
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'rfis', str(rfi_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe)
    f.save(path)
    attachments = _parse_json(rfi.attachments_json, [])
    attachments.append({
        'filename': safe,
        'original_name': f.filename,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
    })
    apply_rfi_fields(rfi, {'attachments': attachments})
    db.session.commit()
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/api/rfis/<int:rfi_id>/promote-pco', methods=['POST'])
@login_required
def api_rfi_promote_pco(rfi_id):
    """Create a PCO from an RFI (RedTeam / Procore style)."""
    from co_persistence import pco_to_dict
    rfi = RFI.query.get_or_404(rfi_id)
    body = request.get_json(silent=True) or {}
    pco = PotentialChangeOrder(
        project_id=rfi.project_id,
        number=generate_next_number('PCO', PotentialChangeOrder),
        title=body.get('title') or f'PCO from {rfi.number}: {rfi.subject}',
        description=body.get('description') or rfi.official_answer or rfi.question,
        estimated_amount=float(body.get('estimated_amount') or rfi.cost_impact_amount or 0),
        status='Open',
        reason=body.get('reason') or 'Design Change',
        priority=rfi.priority or 'Medium',
        schedule_impact_days=rfi.schedule_impact_days or 0,
        linked_rfi_id=rfi.id,
        ball_in_court_role='Project Manager',
        created_by_id=current_user.id,
    )
    db.session.add(pco)
    db.session.flush()
    rfi.linked_pco_id = pco.id
    db.session.commit()
    return jsonify({'ok': True, 'pco': pco_to_dict(pco), 'pco_id': pco.id})


@app.route('/uploads/rfis/<int:rfi_id>/<path:filename>')
@login_required
def serve_rfi_attachment(rfi_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'rfis', str(rfi_id))
    return send_from_directory(folder, filename)


@app.route('/api/rfis/link-options', methods=['GET'])
@login_required
def api_rfi_link_options():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    cos = ChangeOrder.query.filter_by(project_id=int(project_id)).order_by(ChangeOrder.created_at.desc()).limit(200).all()
    pcos = PotentialChangeOrder.query.filter_by(project_id=int(project_id)).order_by(PotentialChangeOrder.created_at.desc()).limit(200).all()
    return jsonify({
        'change_orders': [{'id': c.id, 'number': c.number, 'title': getattr(c, 'title', None) or c.description, 'status': c.status} for c in cos],
        'pcos': [{'id': p.id, 'number': p.number, 'title': p.title, 'status': p.status} for p in pcos],
    })


# ==================== CHANGE ORDER ROUTES ====================

@app.route('/change-orders')
@login_required
def change_orders_page():
    return render_template('change_orders.html')


def _parse_change_order_date(value):
    if not value:
        return datetime.utcnow().date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], '%Y-%m-%d').date()
        except ValueError:
            return datetime.utcnow().date()
    return value


def _change_order_from_payload(data, project_id=None):
    pid = data.get('project_id') or project_id or get_current_project_id()
    if not pid:
        raise ValueError('project_id required')
    return {
        'project_id': int(pid),
        'description': (data.get('description') or '').strip(),
        'amount': float(data.get('amount') or 0),
        'reason': data.get('reason'),
        'schedule_impact': data.get('schedule_impact'),
        'status': data.get('status') or 'Draft',
        'date': _parse_change_order_date(data.get('date')),
        'cost_code': data.get('cost_code'),
        'requested_by': data.get('requested_by'),
        'priority': data.get('priority'),
        'revision': int(data.get('revision') or 0),
        'notes': data.get('notes'),
    }


@app.route('/change-orders/create', methods=['POST'])
@login_required
def create_change_order():
    try:
        data = request.get_json(silent=True) or request.form
        fields = _change_order_from_payload(data)
        if not fields['description']:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Description is required'}), 400
            flash('Description and Project are required.', 'error')
            return redirect_with_project('change_orders_page')

        number = generate_next_number('CO', ChangeOrder)
        co = ChangeOrder(
            number=number,
            created_by_id=current_user.id,
            **fields,
        )
        db.session.add(co)
        db.session.commit()

        if request.is_json:
            return jsonify({'success': True, 'id': co.id, 'number': co.number})
        flash(f'Change Order {number} created successfully!', 'success')
        return redirect_with_project('change_orders_page')

    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(f'Error creating Change Order: {str(e)}', 'error')
        return redirect_with_project('change_orders_page')


@app.route('/change-orders/<int:co_id>/update-status', methods=['POST'])
@login_required
def update_change_order_status(co_id):
    co = ChangeOrder.query.get_or_404(co_id)
    data = request.get_json(silent=True) or {}
    new_status = data.get('status') or request.form.get('status')
    if not new_status:
        return jsonify({'success': False, 'message': 'No status provided'}), 400

    old_status = co.status
    co.status = new_status
    from co_persistence import BALL_IN_COURT_MAP
    co.ball_in_court_role = BALL_IN_COURT_MAP.get(new_status, co.ball_in_court_role)
    if new_status == 'Submitted' and not co.submitted_at:
        co.submitted_at = datetime.utcnow()

    log = AuditLog(
        user_id=current_user.id,
        action='Updated Change Order Status',
        target_type='ChangeOrder',
        target_id=co.id,
        details=f"Changed status from '{old_status}' to '{new_status}'",
    )
    db.session.add(log)

    if new_status in ('Submitted', 'Under Review'):
        try:
            from case_workflow import create_approval
            create_approval(
                project_id=co.project_id,
                module='Change Orders',
                entity_type='ChangeOrder',
                entity_id=co.id,
                title=f'Change Order {co.number or co.id} requires approval',
                description=co.description or '',
                action_url=f'/change-orders?project_id={co.project_id}',
                payload={'amount': co.amount, 'status': new_status},
            )
        except Exception:
            pass

    sync_result = None
    budget_sync_result = None
    if new_status == 'Approved' and old_status != 'Approved':
        co.approved_at = datetime.utcnow()
        co.approved_by_id = current_user.id
        try:
            from pay_app_persistence import sync_change_order_to_sov
            sync_result = sync_change_order_to_sov(
                ChangeOrder, ChangeOrderAllocation, PayAppProjectState,
                ScheduleData, Project, db, co.id, current_user.id,
            )
            co.sage_sync_status = 'sov_synced'
            from sage_service import create_and_process_sage_event
            create_and_process_sage_event(
                SageSyncEvent, Project, db, co.project_id,
                'ChangeOrderApproved',
                message=f'Change Order {co.number} approved — SOV and schedule updated',
                payload={'change_order_id': co.id, 'amount': co.amount, 'sync': sync_result},
                user_id=current_user.id,
            )
        except Exception as exc:
            co.sage_sync_status = f'sync_error:{str(exc)[:120]}'
            sync_result = {'error': str(exc)}

    try:
        from budget_persistence import sync_change_order_to_budget
        budget_sync_result = sync_change_order_to_budget(
            ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
            db, co.id, old_status, new_status, current_user.id,
        )
    except Exception:
        pass

    db.session.commit()
    return jsonify({
        'success': True,
        'new_status': new_status,
        'sov_synced': new_status == 'Approved' and sync_result and not sync_result.get('error'),
        'sync_result': sync_result,
        'budget_sync_result': budget_sync_result,
    })


# ==================== SUBMITTAL ROUTES ====================

@app.route('/submittals')
@login_required
def submittals_page():
    submittals = query_for_active_project(Submittal).order_by(Submittal.created_at.desc()).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('submittals.html', submittals=submittals, projects=projects)


@app.route('/submittals/create', methods=['POST'])
@login_required
def create_submittal():
    try:
        project_id = request.form.get('project_id')
        description = request.form.get('description')
        spec_section = request.form.get('spec_section')
        priority = request.form.get('priority', 'Medium')

        if not description or not project_id:
            flash('Description and Project are required.', 'error')
            return redirect_with_project('submittals_page')

        number = generate_next_number('SUB', Submittal)

        submittal = Submittal(
            project_id=int(project_id),
            number=number,
            description=description,
            spec_section=spec_section,
            priority=priority,
            status='Pending',
            submitted_by=current_user.full_name,
            date=datetime.utcnow().date()
        )

        db.session.add(submittal)
        db.session.commit()

        flash(f'Submittal {number} created successfully!', 'success')
        return redirect_with_project('submittals_page')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Submittal: {str(e)}', 'error')
        return redirect_with_project('submittals_page')


@app.route('/submittals/<int:submittal_id>/update-status', methods=['POST'])
@login_required
def update_submittal_status(submittal_id):
    submittal = Submittal.query.get_or_404(submittal_id)
    new_status = request.form.get('status')

    if new_status:
        submittal.status = new_status
        db.session.commit()
        return jsonify({'success': True, 'new_status': new_status})

    return jsonify({'success': False}), 400


@app.route('/api/submittals/spec-book', methods=['GET'])
@login_required
def api_get_spec_book():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'spec_books', str(project_id))
    meta_path = os.path.join(folder, 'meta.json')
    pdf_path = os.path.join(folder, 'spec_book.pdf')
    if not os.path.isfile(meta_path) or not os.path.isfile(pdf_path):
        return jsonify({'found': False})
    try:
        with open(meta_path, encoding='utf-8') as fh:
            meta = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return jsonify({'found': False})
    meta['found'] = True
    meta['url'] = url_for('serve_spec_book_pdf', project_id=int(project_id))
    return jsonify(meta)


@app.route('/api/submittals/spec-book', methods=['POST'])
@login_required
def api_upload_spec_book():
    project_id = request.form.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    if not allowed_file(file.filename) or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'PDF file required'}), 400

    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'spec_books', str(project_id))
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, 'spec_book.pdf')
    file.save(pdf_path)

    section_map_raw = request.form.get('sectionPageMap') or '{}'
    try:
        section_page_map = json.loads(section_map_raw)
    except json.JSONDecodeError:
        section_page_map = {}

    meta = {
        'filename': secure_filename(file.filename) or file.filename,
        'uploadedAt': datetime.utcnow().isoformat() + 'Z',
        'pageCount': int(request.form.get('pageCount') or 0),
        'sectionPageMap': section_page_map,
    }
    with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)

    meta['ok'] = True
    meta['url'] = url_for('serve_spec_book_pdf', project_id=int(project_id))
    return jsonify(meta)


@app.route('/api/projects/<int:project_id>/original-contract', methods=['GET'])
@login_required
def api_get_original_contract(project_id):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id))
    meta_path = os.path.join(folder, 'meta.json')
    pdf_path = os.path.join(folder, 'original_contract.pdf')
    if not os.path.isfile(meta_path) or not os.path.isfile(pdf_path):
        return jsonify({'found': False})
    try:
        with open(meta_path, encoding='utf-8') as fh:
            meta = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return jsonify({'found': False})
    meta['found'] = True
    meta['url'] = url_for('serve_original_contract_pdf', project_id=int(project_id))
    return jsonify(meta)


@app.route('/api/projects/<int:project_id>/original-contract', methods=['POST'])
@login_required
def api_upload_original_contract(project_id):
    Project.query.get_or_404(project_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    if not allowed_file(file.filename) or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'PDF file required'}), 400

    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id))
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, 'original_contract.pdf')
    file.save(pdf_path)

    meta = {
        'filename': secure_filename(file.filename) or file.filename,
        'uploadedAt': datetime.utcnow().isoformat() + 'Z',
        'uploadedById': current_user.id,
        'uploadedByName': getattr(current_user, 'full_name', None) or current_user.email,
        'aiaForm': (request.form.get('aia_form') or '').strip(),
        'executedDate': (request.form.get('executed_date') or '').strip(),
    }
    with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)

    meta['ok'] = True
    meta['url'] = url_for('serve_original_contract_pdf', project_id=int(project_id))
    return jsonify(meta)


@app.route('/api/projects/<int:project_id>/original-contract', methods=['DELETE'])
@login_required
def api_delete_original_contract(project_id):
    if current_user.role != 'Admin':
        return jsonify({'error': 'Admin only'}), 403
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id))
    for name in ('original_contract.pdf', 'meta.json'):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            os.remove(path)
    return jsonify({'ok': True})


@app.route('/api/projects/<int:project_id>/logo', methods=['GET'])
@login_required
def api_get_project_logo(project_id):
    Project.query.get_or_404(project_id)
    folder = _project_asset_folder(project_id, 'projects')
    meta = _read_project_asset_meta(project_id, 'projects')
    if not meta or not meta.get('filename'):
        return jsonify({'found': False})
    logo_path = os.path.join(folder, meta['filename'])
    if not os.path.isfile(logo_path):
        return jsonify({'found': False})
    meta['found'] = True
    meta['url'] = url_for('serve_project_logo', project_id=int(project_id))
    return jsonify(meta)


@app.route('/api/projects/<int:project_id>/logo', methods=['POST'])
@login_required
def api_upload_project_logo(project_id):
    Project.query.get_or_404(project_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    if not allowed_logo_file(file.filename):
        return jsonify({'error': 'Image required (PNG, JPG, GIF, WebP, or SVG)'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    stored_name = f'logo.{ext}'
    folder = _project_asset_folder(project_id, 'projects')
    os.makedirs(folder, exist_ok=True)

    for existing in os.listdir(folder):
        if existing.startswith('logo.'):
            try:
                os.remove(os.path.join(folder, existing))
            except OSError:
                pass

    file.save(os.path.join(folder, stored_name))
    meta = {
        'filename': stored_name,
        'originalName': secure_filename(file.filename) or file.filename,
        'uploadedAt': datetime.utcnow().isoformat() + 'Z',
        'uploadedById': current_user.id,
        'uploadedByName': getattr(current_user, 'full_name', None) or current_user.email,
    }
    with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)

    meta['ok'] = True
    meta['url'] = url_for('serve_project_logo', project_id=int(project_id))
    return jsonify(meta)


@app.route('/api/projects/<int:project_id>/logo', methods=['DELETE'])
@login_required
def api_delete_project_logo(project_id):
    if current_user.role != 'Admin':
        return jsonify({'error': 'Admin only'}), 403
    folder = _project_asset_folder(project_id, 'projects')
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
    return jsonify({'ok': True})


@app.route('/api/projects/<int:project_id>/aia/catina-link', methods=['POST'])
@login_required
def api_project_catina_link(project_id):
    from aia_service import build_catina_create_url, build_catina_open_url, commitment_export_for_catina
    project = Project.query.get_or_404(project_id)
    d = project.to_dict()
    catina_url = d.get('catina_document_url')
    catina_id = d.get('catina_project_id')
    if catina_url or catina_id:
        url = build_catina_open_url(catina_id, catina_url)
    else:
        payload = commitment_export_for_catina({
            'id': None,
            'number': project.number,
            'aia_form': d.get('prime_aia_form') or 'A101',
            'title': project.name,
            'description': project.description,
            'current_amount': project.contract_value,
            'owner_name': d.get('owner_legal_name') or project.client,
            'contractor_name': d.get('contractor_legal_name'),
            'architect_engineer': d.get('architect_of_record'),
        })
        url = build_catina_create_url(payload, {'name': project.name, 'number': project.number})
    return jsonify({'ok': True, 'url': url, 'portal': 'AIA Contract Documents (Catina)'})


@app.route('/uploads/contracts/<int:project_id>/original_contract.pdf')
@login_required
def serve_original_contract_pdf(project_id):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id))
    return send_from_directory(directory, 'original_contract.pdf', mimetype='application/pdf')


@app.route('/uploads/projects/<int:project_id>/logo')
@login_required
def serve_project_logo(project_id):
    meta = _read_project_asset_meta(project_id, 'projects')
    if not meta or not meta.get('filename'):
        return jsonify({'error': 'not found'}), 404
    directory = _project_asset_folder(project_id, 'projects')
    ext = meta['filename'].rsplit('.', 1)[-1].lower()
    mimetypes = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'svg': 'image/svg+xml',
    }
    return send_from_directory(directory, meta['filename'], mimetype=mimetypes.get(ext, 'application/octet-stream'))


@app.route('/uploads/spec_books/<int:project_id>/spec_book.pdf')
@login_required
def serve_spec_book_pdf(project_id):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'spec_books', str(project_id))
    return send_from_directory(directory, 'spec_book.pdf', mimetype='application/pdf')




# ==================== PUNCH LIST ROUTES ====================

@app.route('/punch-list')
@login_required
def punch_list_page():
    punch_items = query_for_active_project(PunchItem).order_by(PunchItem.created_at.desc()).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('punch_list.html', punch_items=punch_items, projects=projects)


@app.route('/punch-list/create', methods=['POST'])
@login_required
def create_punch_item():
    try:
        project_id = request.form.get('project_id')
        description = request.form.get('description')
        location = request.form.get('location')
        trade = request.form.get('trade')
        priority = request.form.get('priority', 'Medium')
        due_date = request.form.get('due_date')

        if not description or not project_id:
            flash('Description and Project are required.', 'error')
            return redirect_with_project('punch_list_page')

        number = generate_next_number('PL', PunchItem)

        item = PunchItem(
            project_id=int(project_id),
            number=number,
            description=description,
            location=location,
            trade=trade,
            priority=priority,
            status='Open',
            due_date=datetime.strptime(due_date, '%Y-%m-%d').date() if due_date else None,
            created_by_id=current_user.id
        )

        db.session.add(item)
        db.session.commit()

        flash(f'Punch Item {number} created successfully!', 'success')
        return redirect_with_project('punch_list_page')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Punch Item: {str(e)}', 'error')
        return redirect_with_project('punch_list_page')


@app.route('/punch-list/<int:item_id>/update-status', methods=['POST'])
@login_required
def update_punch_status(item_id):
    item = PunchItem.query.get_or_404(item_id)
    new_status = request.form.get('status')

    if new_status:
        item.status = new_status
        if new_status == 'Completed':
            item.completed_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'new_status': new_status})

    return jsonify({'success': False}), 400


# ==================== SAFETY ROUTES ====================

@app.route('/safety')
@login_required
def safety_page():
    reports = query_for_active_project(SafetyReport).order_by(SafetyReport.created_at.desc()).limit(50).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('safety.html', reports=reports, projects=projects)


@app.route('/safety/create', methods=['POST'])
@login_required
def create_safety_report():
    try:
        project_id = request.form.get('project_id')
        report_type = request.form.get('type')
        description = request.form.get('description')
        location = request.form.get('location')
        severity = request.form.get('severity', 'Medium')
        immediate_actions = request.form.get('immediate_actions')
        corrective_actions = request.form.get('corrective_actions')

        if not description or not project_id:
            flash('Description and Project are required.', 'error')
            return redirect_with_project('safety_page')

        number = generate_next_number('SAF', SafetyReport)

        report = SafetyReport(
            project_id=int(project_id),
            number=number,
            type=report_type,
            description=description,
            location=location,
            severity=severity,
            status='Open',
            immediate_actions=immediate_actions,
            corrective_actions=corrective_actions,
            reported_by_id=current_user.id
        )

        db.session.add(report)
        db.session.commit()

        flash(f'Safety Report {number} created successfully!', 'success')
        return redirect_with_project('safety_page')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Safety Report: {str(e)}', 'error')
        return redirect_with_project('safety_page')


# ==================== SCHEDULE ROUTES ====================

@app.route('/schedule')
@login_required
def schedule_page():
    projects = Project.query.order_by(Project.name).all()
    return render_template('schedule.html', projects=projects)


@app.route('/api/schedules/portfolio')
@login_required
def api_portfolio_schedules():
    """Lightweight schedule + EVM summary for all projects (portfolio dashboard)."""
    projects = Project.query.order_by(Project.name).all()
    rows = []
    for p in projects:
        record = ScheduleData.query.filter_by(project_id=p.id).first()
        summary = {
            'project_id': p.id,
            'project_number': p.number or '',
            'project_name': p.name,
            'start_date': None,
            'finish_date': None,
            'pct_complete': None,
            'critical_count': 0,
            'activity_count': 0,
            'cpi': None,
            'spi': None,
            'bac': None,
            'has_schedule': False
        }
        if record and record.payload:
            try:
                payload = json.loads(record.payload)
            except json.JSONDecodeError:
                payload = None
            if payload and payload.get('data'):
                summary['has_schedule'] = True
                tasks = payload['data']
                links = payload.get('links') or []
                data_date = (payload.get('settings') or {}).get('data_date')
                start = finish = None
                progress_sum = crit = act = 0
                bac = bcwp = acwp = bcws = 0.0
                for t in tasks:
                    if t.get('type') == 'project':
                        continue
                    act += 1
                    sd = t.get('start_date')
                    ed = t.get('end_date')
                    if sd and (not start or sd < start):
                        start = sd
                    if ed and (not finish or ed > finish):
                        finish = ed
                    prog = t.get('progress') or 0
                    if prog > 1:
                        prog = prog / 100.0
                    progress_sum += prog
                    if t.get('$critical') or t.get('critical'):
                        crit += 1
                    cost = float(t.get('cost') or 0)
                    if cost > 0:
                        bac += cost
                        bcwp += cost * prog
                        acwp += float(t.get('actual_cost') or 0) or cost * prog
                summary['start_date'] = start
                summary['finish_date'] = finish
                summary['activity_count'] = act
                summary['critical_count'] = crit
                summary['pct_complete'] = round((progress_sum / act) * 100) if act else 0
                summary['bac'] = round(bac, 2)
                summary['cpi'] = round(bcwp / acwp, 3) if acwp > 0 else None
                summary['spi'] = round(bcwp / bac, 3) if bac > 0 and progress_sum > 0 else None
        if summary['has_schedule']:
            rows.append(summary)
    return jsonify(rows)


@app.route('/api/schedule', methods=['GET'])
@login_required
def api_get_schedule():
    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    record = ScheduleData.query.filter_by(project_id=project_id).first()
    if not record or not record.payload:
        return jsonify({'project_id': project_id, 'payload': None})
    try:
        payload = json.loads(record.payload)
    except json.JSONDecodeError:
        payload = None
    return jsonify({
        'project_id': project_id,
        'payload': payload,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None
    })


@app.route('/api/schedule', methods=['PUT'])
@login_required
def api_save_schedule():
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id')
        payload = body.get('payload')
        if not project_id or payload is None:
            return jsonify({'error': 'project_id and payload required'}), 400
        project_id = int(project_id)
        if not Project.query.get(project_id):
            return jsonify({'error': 'Invalid project_id'}), 400
        record = ScheduleData.query.filter_by(project_id=int(project_id)).first()
        payload_json = json.dumps(payload)
        if record:
            record.payload = payload_json
            record.updated_at = datetime.utcnow()
        else:
            record = ScheduleData(project_id=int(project_id), payload=payload_json)
            db.session.add(record)
        db.session.commit()
        return jsonify({'ok': True, 'project_id': project_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/schedule/create', methods=['POST'])
@login_required
def create_schedule_task():
    try:
        project_id = request.form.get('project_id')
        description = request.form.get('description')
        phase = request.form.get('phase')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        status = request.form.get('status', 'Not Started')
        assigned_to = request.form.get('assigned_to')

        if not description or not project_id:
            flash('Description and Project are required.', 'error')
            return redirect_with_project('schedule_page')

        number = generate_next_number('TSK', ScheduleTask)

        task = ScheduleTask(
            project_id=int(project_id),
            number=number,
            description=description,
            phase=phase,
            start_date=datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None,
            end_date=datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None,
            status=status,
            assigned_to=assigned_to
        )

        db.session.add(task)
        db.session.commit()

        flash(f'Schedule Task {number} created successfully!', 'success')
        return redirect_with_project('schedule_page')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Schedule Task: {str(e)}', 'error')
        return redirect_with_project('schedule_page')




# ==================== COMPANIES / VENDORS ROUTES ====================

@app.route('/companies')
@login_required
def companies_page():
    companies = Company.query.order_by(Company.name.asc()).all()
    return render_template('companies.html', companies=companies)


@app.route('/companies/create', methods=['POST'])
@login_required
def create_company():
    try:
        name = request.form.get('name')
        company_type = request.form.get('type')
        contact_first = request.form.get('contact_first_name')
        contact_last = request.form.get('contact_last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')

        if not name:
            flash('Company name is required.', 'error')
            return redirect(url_for('companies_page'))

        company = Company(
            name=name,
            type=company_type,
            contact_first_name=contact_first,
            contact_last_name=contact_last,
            email=email,
            phone=phone
        )

        db.session.add(company)
        db.session.commit()

        flash(f'Company "{name}" added successfully!', 'success')
        return redirect(url_for('companies_page'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error adding company: {str(e)}', 'error')
        return redirect(url_for('companies_page'))


# ==================== USER MANAGEMENT ROUTES (Admin Only) ====================

@app.route('/user-management')
@login_required
def user_management():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('user_management.html', users=users)


@app.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    try:
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        role = request.form.get('role', 'Viewer')
        company = request.form.get('company')
        temp_password = request.form.get('temp_password') or 'TempPass123!'

        if not first_name or not last_name or not email:
            flash('First name, last name, and email are required.', 'error')
            return redirect(url_for('user_management'))

        if User.query.filter_by(email=email).first():
            flash('A user with this email already exists.', 'error')
            return redirect(url_for('user_management'))

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            company=company,
            status='Active',
            must_change_password=True
        )
        new_user.set_password(temp_password)

        db.session.add(new_user)
        db.session.commit()

        flash(f'User {new_user.full_name} created successfully. Temporary password: {temp_password}', 'success')
        return redirect(url_for('user_management'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating user: {str(e)}', 'error')
        return redirect(url_for('user_management'))


@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('user_management'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.full_name} has been deleted.', 'success')
    return redirect(url_for('user_management'))


# ==================== WEEKLY REPORT ROUTES ====================

@app.route('/weekly-report')
@login_required
def weekly_report():
    reports = query_for_active_project(WeeklyReport).order_by(WeeklyReport.week_ending.desc()).limit(20).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('weekly_report.html', reports=reports, projects=projects)


@app.route('/weekly-report/create', methods=['POST'])
@login_required
def create_weekly_report():
    try:
        project_id = request.form.get('project_id')
        week_ending = request.form.get('week_ending')
        work_performed = request.form.get('work_performed')
        safety_notes = request.form.get('safety_notes')

        if not project_id or not week_ending:
            flash('Project and Week Ending date are required.', 'error')
            return redirect_with_project('weekly_report')

        report = WeeklyReport(
            project_id=int(project_id),
            week_ending=datetime.strptime(week_ending, '%Y-%m-%d').date(),
            work_performed=work_performed,
            safety_notes=safety_notes,
            status='Submitted',
            created_by_id=current_user.id
        )

        db.session.add(report)
        db.session.commit()

        flash('Weekly Report submitted successfully!', 'success')
        return redirect_with_project('weekly_report')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Weekly Report: {str(e)}', 'error')
        return redirect_with_project('weekly_report')


# ==================== PLACEHOLDER ROUTES (Prevent BuildError) ====================
# These modules have templates but limited backend logic.
# They will be expanded in future updates.

@app.route('/photos')
@login_required
def photos_page():
    projects = Project.query.order_by(Project.name).all()
    photos = query_for_active_project(Photo).order_by(Photo.created_at.desc()).limit(50).all()
    return render_template('photos.html', projects=projects, photos=photos)


@app.route('/documents')
@login_required
def documents_page():
    return render_template('documents.html')


@app.route('/drawings')
@login_required
def drawings_page():
    return render_template('drawings.html')


# ==================== DRAWINGS REST API ====================

def _drawing_folder(project_id):
    path = os.path.join(app.config['UPLOAD_FOLDER'], 'drawings', str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def _serialize_drawing(drawing):
    from drawing_persistence import drawing_to_dict, revision_to_dict
    from sqlalchemy import func

    rev = None
    if drawing.current_revision_id:
        rev = DrawingRevision.query.get(drawing.current_revision_id)
    if not rev:
        rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
    rev_count = DrawingRevision.query.filter_by(drawing_id=drawing.id).count()
    markup_count = DrawingMarkup.query.filter_by(drawing_id=drawing.id).count()
    linked_rfis = []
    pins = DrawingMarkup.query.filter_by(drawing_id=drawing.id, markup_type='rfi_pin').all()
    for p in pins:
        if p.linked_rfi_id:
            rfi = RFI.query.get(p.linked_rfi_id)
            if rfi:
                linked_rfis.append({'id': rfi.id, 'number': rfi.number, 'subject': rfi.subject})
    d = drawing_to_dict(drawing, rev, rev_count, markup_count, linked_rfis)
    return d


@app.route('/api/drawings/dashboard', methods=['GET'])
@login_required
def api_drawings_dashboard():
    from drawing_persistence import compute_drawing_dashboard
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify(compute_drawing_dashboard(Drawing, DrawingRevision, int(project_id)))


@app.route('/api/drawings', methods=['GET'])
@login_required
def api_list_drawings():
    from drawing_persistence import group_drawings_by_section
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    section = request.args.get('section')
    discipline = request.args.get('discipline')
    status = request.args.get('status')
    q = Drawing.query.filter_by(project_id=int(project_id))
    if section:
        q = q.filter_by(section_prefix=section.upper())
    if discipline:
        q = q.filter_by(discipline=discipline)
    if status:
        q = q.filter_by(status=status)
    drawings = q.order_by(Drawing.sort_key, Drawing.sheet_number).all()
    items = [_serialize_drawing(d) for d in drawings]
    grouped = group_drawings_by_section(items)
    return jsonify({'drawings': items, 'sections': grouped})


@app.route('/api/drawings/<int:drawing_id>', methods=['GET'])
@login_required
def api_get_drawing(drawing_id):
    from drawing_persistence import revision_to_dict, markup_to_dict
    drawing = Drawing.query.get_or_404(drawing_id)
    data = _serialize_drawing(drawing)
    revisions = DrawingRevision.query.filter_by(drawing_id=drawing.id).order_by(DrawingRevision.uploaded_at.desc()).all()
    data['revisions'] = [revision_to_dict(r) for r in revisions]
    rev_id = drawing.current_revision_id
    markups = DrawingMarkup.query.filter(
        DrawingMarkup.drawing_id == drawing.id,
        db.or_(DrawingMarkup.revision_id == rev_id, DrawingMarkup.revision_id.is_(None)),
    ).all()
    data['markups'] = [markup_to_dict(m) for m in markups]
    return jsonify(data)


@app.route('/api/drawings/<int:drawing_id>/detect-scale', methods=['GET'])
@login_required
def api_detect_drawing_scale(drawing_id):
    """Detect drawing scale from the current revision PDF title block."""
    from drawing_persistence import (
        extract_pdf_page_text,
        extract_scale_from_text,
        extract_title_block_metadata,
        resolve_drawing_file_path,
        ocr_title_block_regions,
    )
    drawing = Drawing.query.get_or_404(drawing_id)
    rev = DrawingRevision.query.get(drawing.current_revision_id) if drawing.current_revision_id else None
    if not rev:
        rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
    upload_root = app.config.get('UPLOAD_FOLDER')
    path = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
    if not path:
        return jsonify({'error': 'Drawing file not found'}), 404
    layout = extract_title_block_metadata(path, 0)
    text = extract_pdf_page_text(path, 0)
    ocr = ocr_title_block_regions(path, 0)
    combined = '\n'.join(filter(None, [text, ocr, layout.get('text_preview')]))
    scale = layout.get('scale') or extract_scale_from_text(combined)
    if not scale:
        return jsonify({'ok': True, 'scale': None, 'message': 'No scale found on sheet'})
    return jsonify({'ok': True, 'scale': scale})


@app.route('/api/drawings/sets', methods=['GET'])
@login_required
def api_drawing_sets():
    """List drawing set names for compare workflows."""
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    revisions = (
        DrawingRevision.query.join(Drawing, DrawingRevision.drawing_id == Drawing.id)
        .filter(Drawing.project_id == int(project_id))
        .order_by(DrawingRevision.uploaded_at.desc())
        .all()
    )
    sets = {}
    for rev in revisions:
        name = rev.set_name or 'Unnamed Set'
        sets.setdefault(name, {
            'name': name,
            'revision_count': 0,
            'sheet_count': 0,
            'drawing_ids': [],
            'latest_upload': None,
        })
        sets[name]['revision_count'] += 1
        if not sets[name]['latest_upload'] or (rev.uploaded_at and rev.uploaded_at.isoformat() > sets[name]['latest_upload']):
            sets[name]['latest_upload'] = rev.uploaded_at.isoformat() if rev.uploaded_at else None
    drawing_sets = {}
    for d in Drawing.query.filter_by(project_id=int(project_id)).all():
        rev = DrawingRevision.query.get(d.current_revision_id) if d.current_revision_id else None
        if not rev:
            continue
        name = rev.set_name or 'Unnamed Set'
        drawing_sets[name] = drawing_sets.get(name, 0) + 1
        if d.id not in sets.get(name, {}).get('drawing_ids', []):
            sets.setdefault(name, {
                'name': name,
                'revision_count': 0,
                'sheet_count': 0,
                'drawing_ids': [],
                'latest_upload': None,
            })
            sets[name]['drawing_ids'].append(d.id)
    for name in sets:
        sets[name]['sheet_count'] = drawing_sets.get(name, len(sets[name]['drawing_ids']))
    return jsonify({'sets': sorted(sets.values(), key=lambda s: s.get('latest_upload') or '', reverse=True)})


@app.route('/api/drawings/bulk-delete', methods=['POST'])
@login_required
def api_bulk_delete_drawings():
    """Delete multiple drawing sheets at once."""
    from drawing_persistence import delete_drawings_bulk
    data = request.get_json(silent=True) or {}
    project_id = data.get('project_id') or get_current_project_id()
    drawing_ids = data.get('drawing_ids') or []
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not drawing_ids:
        return jsonify({'error': 'drawing_ids required'}), 400
    try:
        deleted = delete_drawings_bulk(
            db, Drawing, DrawingRevision, DrawingMarkup, int(project_id), drawing_ids,
            upload_root=app.config.get('UPLOAD_FOLDER'),
            RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
        )
        db.session.commit()
        return jsonify({'ok': True, 'deleted_count': len(deleted), 'deleted_ids': deleted})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/drawings/delete-set', methods=['POST'])
@login_required
def api_delete_drawing_set():
    """Delete all sheets whose current revision belongs to a drawing set upload name."""
    from drawing_persistence import delete_drawings_by_set_name
    data = request.get_json(silent=True) or {}
    project_id = data.get('project_id') or get_current_project_id()
    set_name = (data.get('set_name') or '').strip()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not set_name:
        return jsonify({'error': 'set_name required'}), 400
    try:
        deleted = delete_drawings_by_set_name(
            db, Drawing, DrawingRevision, DrawingMarkup, int(project_id), set_name,
            upload_root=app.config.get('UPLOAD_FOLDER'),
            RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
        )
        db.session.commit()
        return jsonify({'ok': True, 'deleted_count': len(deleted), 'deleted_ids': deleted, 'set_name': set_name})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/drawings/<int:drawing_id>/file', methods=['GET'])
@login_required
def api_serve_drawing_file(drawing_id):
    from drawing_persistence import resolve_drawing_file_path
    drawing = Drawing.query.get_or_404(drawing_id)
    rev = DrawingRevision.query.get(drawing.current_revision_id) if drawing.current_revision_id else None
    if not rev:
        rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
    upload_root = app.config.get('UPLOAD_FOLDER')
    resolved = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
    if not rev or not resolved:
        return jsonify({'error': 'Drawing file not found on server'}), 404
    directory = os.path.dirname(resolved)
    filename = os.path.basename(resolved)
    return send_from_directory(directory, filename, mimetype='application/pdf')


@app.route('/api/drawings/<int:drawing_id>/revisions/<int:revision_id>/file', methods=['GET'])
@login_required
def api_serve_drawing_revision_file(drawing_id, revision_id):
    from drawing_persistence import resolve_drawing_file_path
    rev = DrawingRevision.query.filter_by(id=revision_id, drawing_id=drawing_id).first_or_404()
    upload_root = app.config.get('UPLOAD_FOLDER')
    resolved = resolve_drawing_file_path(rev.file_path, upload_root)
    if not resolved:
        return jsonify({'error': 'Revision file not found on server'}), 404
    directory = os.path.dirname(resolved)
    filename = os.path.basename(resolved)
    return send_from_directory(directory, filename, mimetype='application/pdf')


@app.route('/api/drawings/<int:drawing_id>/thumbnail', methods=['GET'])
@login_required
def api_drawing_thumbnail(drawing_id):
    drawing = Drawing.query.get_or_404(drawing_id)
    if drawing.thumbnail_path and os.path.isfile(drawing.thumbnail_path):
        directory = os.path.dirname(os.path.abspath(drawing.thumbnail_path))
        filename = os.path.basename(drawing.thumbnail_path)
        return send_from_directory(directory, filename, mimetype='image/png')
    return jsonify({'use_pdf': True, 'file_url': f'/api/drawings/{drawing_id}/file'}), 200


@app.route('/api/drawings/upload', methods=['POST'])
@login_required
def api_upload_drawing():
    """Upload one or more drawing pages. Multi-page PDFs are split automatically."""
    from drawing_persistence import ensure_drawing_dependencies, prepare_upload_pages, process_pages_from_upload
    try:
        ensure_drawing_dependencies()
        project_id = request.form.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'error': 'file required'}), 400
        if not allowed_file(file.filename) or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'PDF files only'}), 400

        set_name = request.form.get('set_name') or os.path.splitext(file.filename)[0]
        manual_sheet = (request.form.get('sheet_number') or '').strip()
        manual_title = (request.form.get('title') or '').strip()
        folder = _drawing_folder(project_id)
        ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        safe = secure_filename(file.filename)
        dest = os.path.join(folder, f'{ts}_{safe}')
        file.save(dest)

        batch_dir = os.path.join(folder, f'set_{ts}')
        split_result = prepare_upload_pages(dest, batch_dir)
        pages = split_result['pages']
        split_warnings = split_result.get('warnings') or []
        expected_page_count = split_result.get('expected_page_count', len(pages))
        split_engine = split_result.get('split_engine', 'unknown')

        if not pages:
            return jsonify({'error': 'Could not read PDF pages. The file may be corrupt or password-protected.'}), 400

        from_combined_set = len(pages) > 1
        created, needs_review = process_pages_from_upload(
            db, Drawing, DrawingRevision, DrawingMarkup,
            project_id=int(project_id),
            pages=pages,
            original_filename=file.filename,
            set_name=set_name,
            uploaded_by_id=current_user.id,
            from_combined_set=from_combined_set,
            upload_source='combined_set' if from_combined_set else 'individual',
            manual_sheet=manual_sheet if not from_combined_set else None,
            manual_title=manual_title if not from_combined_set else None,
            upload_stamp=ts,
        )

        if not created:
            db.session.rollback()
            return jsonify({
                'error': 'No drawing pages could be imported.',
                'needs_review': needs_review,
            }), 400

        db.session.commit()
        drawings = [_serialize_drawing(Drawing.query.get(item['id'])) for item in created]
        return jsonify({
            'ok': True,
            'split': from_combined_set,
            'page_count': len(pages),
            'expected_page_count': expected_page_count,
            'split_engine': split_engine,
            'warnings': split_warnings,
            'created_count': len(created),
            'needs_review_count': len(needs_review),
            'needs_review': needs_review,
            'drawings': drawings,
            'pages': created,
            'drawing': drawings[0] if len(drawings) == 1 else None,
            'revision': drawings[0].get('revision_label') if len(drawings) == 1 else None,
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/drawings/upload-set', methods=['POST'])
@login_required
def api_upload_drawing_set():
    """Upload a multi-page PDF drawing set (alias — splits automatically)."""
    return api_upload_drawing()


@app.route('/api/drawings/<int:drawing_id>', methods=['DELETE'])
@login_required
def api_delete_drawing(drawing_id):
    """Delete a drawing sheet and all of its revisions."""
    from drawing_persistence import delete_drawing_record
    drawing = Drawing.query.get_or_404(drawing_id)
    try:
        delete_drawing_record(
            db, Drawing, DrawingRevision, DrawingMarkup, drawing,
            upload_root=app.config.get('UPLOAD_FOLDER'),
            RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
        )
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': drawing_id})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/drawings/substitute', methods=['POST'])
@login_required
def api_substitute_drawings():
    """Replace existing sheets with revised pages; old revisions archived automatically."""
    from drawing_persistence import (
        ensure_drawing_dependencies,
        upsert_drawing_from_upload,
        detect_sheet_number,
        extract_title_from_text,
        split_pdf_to_pages,
    )
    try:
        ensure_drawing_dependencies()
        project_id = request.form.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        set_name = request.form.get('set_name') or 'Substitute Pages'
        files = request.files.getlist('files')
        if not files:
            single = request.files.get('file')
            if single:
                files = [single]
        if not files:
            return jsonify({'error': 'Upload one or more PDF pages'}), 400

        folder = _drawing_folder(project_id)
        ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        sub_dir = os.path.join(folder, f'substitute_{ts}')
        os.makedirs(sub_dir, exist_ok=True)
        substituted = []
        skipped = []

        def process_page(file_path, original_name, page_note='', from_combined_set=False):
            text = ''
            try:
                from pypdf import PdfReader
                reader = PdfReader(file_path)
                if reader.pages:
                    text = reader.pages[0].extract_text() or ''
            except Exception:
                pass
            sheet_number, page_text, _method, revision = detect_sheet_number(
                file_path, original_name, text, 0, from_combined_set=from_combined_set,
            )
            if not sheet_number:
                skipped.append({'file': original_name, 'reason': 'Sheet number not detected'})
                return
            existing = Drawing.query.filter_by(project_id=int(project_id), sheet_number=sheet_number).first()
            if not existing:
                skipped.append({'file': original_name, 'sheet': sheet_number, 'reason': 'No existing sheet to replace'})
                return
            title = extract_title_from_text(page_text or text, sheet_number) or existing.title
            drawing, rev, old_rev = upsert_drawing_from_upload(
                db, Drawing, DrawingRevision, DrawingMarkup,
                project_id=int(project_id),
                sheet_number=sheet_number,
                title=title,
                discipline=existing.discipline,
                file_path=file_path,
                original_filename=original_name,
                set_name=set_name,
                drawing_date=None,
                received_date=date.today(),
                upload_source='substitute',
                uploaded_by_id=current_user.id,
                notes=page_note or 'Substitute page upload',
                sheet_revision=revision,
            )
            substituted.append({
                'sheet_number': sheet_number,
                'new_revision': rev.revision_label,
                'previous_revision': old_rev.revision_label if old_rev else None,
                'drawing_id': drawing.id,
            })

        for f in files:
            if not f or not f.filename:
                continue
            if not f.filename.lower().endswith('.pdf'):
                skipped.append({'file': f.filename, 'reason': 'Not a PDF'})
                continue
            dest = os.path.join(sub_dir, secure_filename(f.filename))
            f.save(dest)
            try:
                from pypdf import PdfReader
                reader = PdfReader(dest)
                if len(reader.pages) > 1:
                    pages = split_pdf_to_pages(dest, sub_dir)
                    for page in pages:
                        process_page(
                            page['file_path'], f.filename,
                            f'Substitute page {page["page_index"] + 1}',
                            from_combined_set=True,
                        )
                else:
                    process_page(dest, f.filename)
            except Exception:
                process_page(dest, f.filename)

        db.session.commit()
        return jsonify({'ok': True, 'substituted': substituted, 'skipped': skipped})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/drawings/<int:drawing_id>/markups', methods=['GET', 'POST'])
@login_required
def api_drawing_markups(drawing_id):
    from drawing_persistence import markup_to_dict, link_pin_markup
    drawing = Drawing.query.get_or_404(drawing_id)
    if request.method == 'GET':
        revision_id = request.args.get('revision_id', type=int) or drawing.current_revision_id
        q = DrawingMarkup.query.filter_by(drawing_id=drawing.id)
        if revision_id:
            q = q.filter(db.or_(DrawingMarkup.revision_id == revision_id, DrawingMarkup.revision_id.is_(None)))
        return jsonify({'markups': [markup_to_dict(m) for m in q.all()]})

    body = request.get_json(silent=True) or {}
    user_name = f'{current_user.first_name} {current_user.last_name}'.strip() or current_user.email
    markup = DrawingMarkup(
        drawing_id=drawing.id,
        revision_id=body.get('revision_id') or drawing.current_revision_id,
        user_id=current_user.id,
        user_name=user_name,
        layer=body.get('layer') or 'personal',
        markup_type=body.get('markup_type') or 'line',
        geometry_json=json.dumps(body.get('geometry') or {}),
        style_json=json.dumps(body.get('style') or {}),
        label=body.get('label'),
        linked_rfi_id=body.get('linked_rfi_id'),
        measurement_value=body.get('measurement_value'),
        measurement_unit=body.get('measurement_unit'),
    )
    if body.get('publish'):
        markup.layer = 'published'
        markup.published_at = datetime.utcnow()
    db.session.add(markup)
    db.session.flush()

    geom = body.get('geometry') or {}
    if markup.markup_type in ('rfi_pin', 'co_pin', 'punch_pin'):
        link_pin_markup(
            markup, drawing, geom, body.get('label'),
            RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
        )

    db.session.commit()
    return jsonify({'ok': True, 'markup': markup_to_dict(markup)})


@app.route('/api/drawings/markups/<int:markup_id>', methods=['PUT', 'DELETE'])
@login_required
def api_drawing_markup_item(markup_id):
    from drawing_persistence import markup_to_dict, unlink_pin_markup
    markup = DrawingMarkup.query.get_or_404(markup_id)
    if request.method == 'DELETE':
        if markup.markup_type in ('rfi_pin', 'co_pin', 'punch_pin'):
            unlink_pin_markup(markup, RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem)
        db.session.delete(markup)
        db.session.commit()
        return jsonify({'ok': True})
    body = request.get_json(silent=True) or {}
    if 'geometry' in body:
        markup.geometry_json = json.dumps(body['geometry'])
    if 'style' in body:
        markup.style_json = json.dumps(body['style'])
    if 'label' in body:
        markup.label = body['label']
    if body.get('publish'):
        markup.layer = 'published'
        markup.published_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'markup': markup_to_dict(markup)})


@app.route('/api/drawings/<int:drawing_id>/revisions', methods=['GET'])
@login_required
def api_drawing_revisions(drawing_id):
    from drawing_persistence import revision_to_dict
    drawing = Drawing.query.get_or_404(drawing_id)
    revisions = DrawingRevision.query.filter_by(drawing_id=drawing.id).order_by(DrawingRevision.uploaded_at.desc()).all()
    return jsonify({'revisions': [revision_to_dict(r) for r in revisions]})


@app.route('/api/drawings/punch-items', methods=['GET'])
@login_required
def api_drawings_punch_items():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    items = PunchItem.query.filter_by(project_id=int(project_id)).filter(PunchItem.status != 'Completed').all()
    return jsonify({
        'punch_items': [{
            'id': p.id,
            'number': p.number,
            'description': (p.description or '')[:120],
            'location': p.location,
            'status': p.status,
        } for p in items]
    })


@app.route('/api/drawings/change-orders', methods=['GET'])
@login_required
def api_drawings_change_orders():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    cos = ChangeOrder.query.filter_by(project_id=int(project_id)).filter(ChangeOrder.status != 'Void').all()
    return jsonify({
        'change_orders': [{
            'id': c.id,
            'number': c.number,
            'title': getattr(c, 'title', None) or (c.description or '')[:80],
            'status': c.status,
        } for c in cos],
    })


@app.route('/api/drawings/rfis', methods=['GET'])
@login_required
def api_drawings_rfis():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    rfis = RFI.query.filter_by(project_id=int(project_id)).filter(RFI.status != 'Void').all()
    return jsonify({'rfis': [{'id': r.id, 'number': r.number, 'subject': r.subject, 'drawing_reference': r.drawing_reference} for r in rfis]})


@app.route('/api/drawings/by-sheet', methods=['GET'])
@login_required
def api_drawing_by_sheet():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    sheet = request.args.get('sheet', '').strip()
    if not project_id or not sheet:
        return jsonify({'error': 'project_id and sheet required'}), 400
    from drawing_persistence import normalize_sheet_number
    norm = normalize_sheet_number(sheet) or sheet.upper()
    drawing = Drawing.query.filter_by(project_id=int(project_id), sheet_number=norm).first()
    if not drawing:
        drawing = Drawing.query.filter(
            Drawing.project_id == int(project_id),
            Drawing.sheet_number.ilike(f'%{sheet}%'),
        ).first()
    if not drawing:
        return jsonify({'error': 'Drawing not found'}), 404
    return jsonify(_serialize_drawing(drawing))


@app.route('/api/drawings/takeoff', methods=['GET'])
@login_required
def api_drawings_takeoff():
    from drawing_persistence import collect_takeoff_items
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    drawing_id = request.args.get('drawing_id', type=int)
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    items = collect_takeoff_items(DrawingMarkup, Drawing, int(project_id), drawing_id)
    return jsonify({'items': items})


@app.route('/api/drawings/export-takeoff-to-budget', methods=['POST'])
@login_required
def api_export_takeoff_to_budget():
    from budget_persistence import get_budget_state, save_budget_state, merge_state_patch
    from drawing_persistence import collect_takeoff_items, export_takeoff_to_budget_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project_id = int(project_id)
    drawing_id = body.get('drawing_id')
    cost_code = (body.get('cost_code') or '01-000').strip()
    cost_type = body.get('cost_type') or 'Subcontract'
    items = collect_takeoff_items(DrawingMarkup, Drawing, project_id, drawing_id)
    if not items:
        return jsonify({'error': 'No takeoff measurements found'}), 400
    record, existing = get_budget_state(BudgetProjectState, project_id)
    merged = export_takeoff_to_budget_state(existing, items, cost_code=cost_code, cost_type=cost_type)
    record = save_budget_state(BudgetProjectState, db, project_id, merged, current_user.id)
    return jsonify({
        'ok': True,
        'imported': len(items),
        'version': record.version,
        'items': items,
    })


@app.route('/budget')
@login_required
def budget_page():
    active = get_active_project()
    fin = _project_financial_context(active)
    return render_template(
        'budget.html',
        project_original_contract_amount=fin['original_contract_amount'],
        project_contract_value=fin['contract_value'],
        project_contract_amount=fin['contract_amount'],
        project_contract_amount_source=fin['contract_amount_source'],
        project_sage_job=fin['sage_job'],
    )


@app.route('/commitments')
@login_required
def commitments_page():
    active = get_active_project()
    return render_template('commitments.html', active_project=active)


def generate_commitment_number(commitment_type, project_id):
    from commitment_persistence import prefix_for_type
    prefix = prefix_for_type(commitment_type or 'Purchase Order')
    last = (
        Commitment.query.filter_by(project_id=int(project_id))
        .filter(Commitment.number.like(f'{prefix}-%'))
        .order_by(Commitment.id.desc())
        .first()
    )
    if last and last.number:
        try:
            n = int(last.number.split('-')[-1])
            return f'{prefix}-{n + 1:03d}'
        except (TypeError, ValueError):
            pass
    return f'{prefix}-001'


def _parse_commitment_date(value):
    if not value:
        return datetime.utcnow().date()
    try:
        return datetime.fromisoformat(str(value).replace('Z', '')).date()
    except (TypeError, ValueError):
        return datetime.utcnow().date()


def _sage_commitment_event(commitment, event_type, message='', extra=None, user_id=None):
    from commitment_persistence import build_commitment_sage_payload
    from sage_service import create_and_process_sage_event
    allocs = CommitmentAllocation.query.filter_by(commitment_id=commitment.id).all()
    payload = build_commitment_sage_payload(commitment, allocs, extra)
    return create_and_process_sage_event(
        SageSyncEvent, Project, db, commitment.project_id,
        event_type,
        message=message or f'{commitment.number} — {event_type}',
        payload=payload,
        user_id=user_id,
        Commitment=Commitment,
    )


@app.route('/api/commitments/dashboard', methods=['GET'])
@login_required
def api_commitments_dashboard():
    from commitment_persistence import compute_dashboard_stats
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify(compute_dashboard_stats(Commitment, int(project_id)))


@app.route('/api/commitments/next-number', methods=['GET'])
@login_required
def api_commitments_next_number():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    ctype = request.args.get('type') or 'Purchase Order'
    return jsonify({
        'number': generate_commitment_number(ctype, int(project_id)),
        'commitment_type': ctype,
    })


@app.route('/api/commitments/cost-codes', methods=['GET'])
@login_required
def api_commitments_cost_codes():
    from co_persistence import get_budget_cost_codes
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify({'cost_codes': get_budget_cost_codes(BudgetProjectState, int(project_id))})


@app.route('/api/commitments', methods=['GET'])
@login_required
def api_list_commitments():
    from commitment_persistence import commitment_to_dict
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    status = request.args.get('status')
    ctype = request.args.get('type')
    q = Commitment.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    if ctype:
        q = q.filter_by(commitment_type=ctype)
    rows = q.order_by(Commitment.created_at.desc()).all()
    result = []
    for c in rows:
        allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        result.append(commitment_to_dict(c, allocs))
    return jsonify({'commitments': result})


@app.route('/api/commitments/<int:commitment_id>', methods=['GET'])
@login_required
def api_get_commitment(commitment_id):
    from commitment_persistence import commitment_to_dict
    c = Commitment.query.get_or_404(commitment_id)
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify(commitment_to_dict(c, allocs))


@app.route('/api/commitments', methods=['POST'])
@login_required
def api_create_commitment():
    from commitment_persistence import apply_commitment_fields, commitment_to_dict, save_allocations, validate_budget_headroom
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        description = (body.get('description') or body.get('title') or '').strip()
        if not description:
            return jsonify({'error': 'description required'}), 400
        ctype = body.get('commitment_type') or 'Purchase Order'
        number = body.get('number') or generate_commitment_number(ctype, project_id)
        c = Commitment(
            project_id=int(project_id),
            number=number,
            description=description,
            commitment_type=ctype,
            status=body.get('status') or 'Draft',
            date=_parse_commitment_date(body.get('date')),
            ball_in_court_role='Creator',
            created_by_id=current_user.id,
        )
        apply_commitment_fields(c, body)
        db.session.add(c)
        db.session.flush()
        if body.get('allocations'):
            total = save_allocations(CommitmentAllocation, c.id, body['allocations'], db)
            if total:
                c.original_amount = total
                c.current_amount = total + float(c.approved_changes or 0)
        warnings = validate_budget_headroom(BudgetProjectState, int(project_id), body.get('allocations') or [])
        db.session.commit()
        allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        return jsonify({'ok': True, 'commitment': commitment_to_dict(c, allocs), 'budget_warnings': warnings})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/commitments/<int:commitment_id>', methods=['PUT'])
@login_required
def api_update_commitment(commitment_id):
    from commitment_persistence import apply_commitment_fields, commitment_to_dict, save_allocations, validate_budget_headroom
    c = Commitment.query.get_or_404(commitment_id)
    body = request.get_json(silent=True) or {}
    old_type = c.commitment_type
    apply_commitment_fields(c, body)
    new_type = body.get('commitment_type') or c.commitment_type
    if new_type != old_type and c.status == 'Draft':
        c.number = generate_commitment_number(new_type, c.project_id)
        c.aia_form = body.get('aia_form') or c.aia_form
    if body.get('number') and c.status == 'Draft':
        c.number = body['number']
    c.updated_at = datetime.utcnow()
    if body.get('allocations') is not None:
        total = save_allocations(CommitmentAllocation, c.id, body['allocations'], db)
        if total:
            c.original_amount = total
            c.current_amount = total + float(c.approved_changes or 0)
    warnings = validate_budget_headroom(BudgetProjectState, c.project_id, body.get('allocations') or [])
    db.session.commit()
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify({'ok': True, 'commitment': commitment_to_dict(c, allocs), 'budget_warnings': warnings})


@app.route('/api/commitments/<int:commitment_id>', methods=['DELETE'])
@login_required
def api_delete_commitment(commitment_id):
    if current_user.role != 'Admin':
        return jsonify({'error': 'Only administrators can delete commitments'}), 403
    c = Commitment.query.get_or_404(commitment_id)
    force = request.args.get('force') == '1'
    body = request.get_json(silent=True) or {}
    if body.get('force'):
        force = True
    if c.status not in ('Draft', 'Rejected', 'Void'):
        if force:
            c.status = 'Void'
            c.ball_in_court_role = None
            db.session.flush()
            _sage_commitment_event(c, 'CommitmentVoided', user_id=current_user.id)
        else:
            return jsonify({
                'error': f'Cannot delete commitment in status {c.status}. Use force delete or void first.',
                'can_force': True,
            }), 400
    CommitmentAllocation.query.filter_by(commitment_id=c.id).delete()
    db.session.delete(c)
    db.session.commit()
    return jsonify({'ok': True, 'deleted_id': commitment_id})


@app.route('/api/commitments/<int:commitment_id>/workflow', methods=['POST'])
@login_required
def api_commitment_workflow(commitment_id):
    from commitment_persistence import (
        commitment_workflow_action, commitment_to_dict, notify_ball_in_court,
        sync_commitment_to_budget, sync_commitment_to_sub_sov,
    )
    c = Commitment.query.get_or_404(commitment_id)
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    try:
        new_status, final_approved = commitment_workflow_action(c, action, current_user)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    budget_sync = None
    sov_sync = None

    if action == 'submit' and not c.submitted_at:
        c.submitted_at = datetime.utcnow()
        try:
            from case_workflow import create_approval
            create_approval(
                project_id=c.project_id,
                module='Commitments',
                entity_type='Commitment',
                entity_id=c.id,
                title=f'{c.number} submitted — {c.ball_in_court_role} review',
                description=c.description or '',
                action_url=f'/commitments?project_id={c.project_id}',
                payload={'amount': c.current_amount, 'type': c.commitment_type},
                assignee_role=c.ball_in_court_role,
            )
        except Exception:
            pass
        _sage_commitment_event(
            c, 'CommitmentSubmitted',
            message=f'{c.number} submitted — ball with {c.ball_in_court_role}',
            user_id=current_user.id,
        )

    if action == 'reject':
        _sage_commitment_event(c, 'CommitmentRejected', user_id=current_user.id)

    if action == 'void':
        _sage_commitment_event(c, 'CommitmentVoided', user_id=current_user.id)

    if action == 'send_docusign':
        from commitment_persistence import commitment_to_dict
        from docusign_service import send_commitment_envelope
        allocs_pre = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        ds_result = send_commitment_envelope(commitment_to_dict(c, allocs_pre))
        if ds_result.get('envelope_id'):
            c.docusign_envelope_id = ds_result['envelope_id']
        c.docusign_status = ds_result.get('status', 'sent')
        if ds_result.get('simulated'):
            c.docusign_status = 'simulated'
        _sage_commitment_event(
            c, 'CommitmentDocuSignSent',
            message=f'DocuSign envelope for {c.number}',
            extra={'envelope_id': c.docusign_envelope_id, 'docusign_result': ds_result},
            user_id=current_user.id,
        )

    if action == 'sign_internal' and c.signature_status == 'fully_executed':
        _sage_commitment_event(c, 'CommitmentExecuted', user_id=current_user.id)

    if final_approved:
        c.approved_at = datetime.utcnow()
        c.approved_by_id = current_user.id
        allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        try:
            budget_sync = sync_commitment_to_budget(BudgetProjectState, db, c, allocs, current_user.id)
            c.sage_sync_status = 'budget_synced'
        except Exception as exc:
            budget_sync = {'error': str(exc)}
        try:
            sov_sync = sync_commitment_to_sub_sov(PayAppProjectState, db, c, allocs, current_user.id)
        except Exception as exc:
            sov_sync = {'error': str(exc)}
        _sage_commitment_event(
            c, 'CommitmentApproved',
            message=f'Commitment {c.number} approved — budget & SOV updated',
            extra={'budget_sync': budget_sync, 'sov_sync': sov_sync},
            user_id=current_user.id,
        )
    elif action == 'approve' and not final_approved:
        _sage_commitment_event(
            c, 'CommitmentApprovalStep',
            message=f'{c.number} — approved step, ball with {c.ball_in_court_role}',
            extra={'new_status': new_status},
            user_id=current_user.id,
        )

    if action in ('submit', 'approve') and c.ball_in_court_role:
        notify_ball_in_court(c.project_id, c, User)
        if action == 'approve' and not final_approved:
            try:
                from case_workflow import create_approval
                create_approval(
                    project_id=c.project_id,
                    module='Commitments',
                    entity_type='Commitment',
                    entity_id=c.id,
                    title=f'{c.number} — {c.ball_in_court_role} approval',
                    description=c.description or '',
                    action_url=f'/commitments?project_id={c.project_id}',
                    payload={'amount': c.current_amount},
                    assignee_role=c.ball_in_court_role,
                )
            except Exception:
                pass

    db.session.commit()
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify({
        'ok': True,
        'new_status': new_status,
        'final_approved': final_approved,
        'ball_in_court_role': c.ball_in_court_role,
        'commitment': commitment_to_dict(c, allocs),
        'budget_sync_result': budget_sync,
        'sov_sync_result': sov_sync,
    })


@app.route('/api/integrations/status', methods=['GET'])
@login_required
def api_integrations_status():
    import os
    from aia_service import integration_info as aia_info
    from docusign_service import integration_info as docusign_info
    sage_url = os.environ.get('SAGE_API_URL', '').strip()
    return jsonify({
        'sage_300': {
            'configured': bool(sage_url),
            'api_url_set': bool(sage_url),
            'connector_endpoint': f'{sage_url.rstrip("/")}/api/v1/transactions' if sage_url else None,
            'note': 'Set SAGE_API_URL and SAGE_API_KEY. Project sage_job_number required per project.',
        },
        'aia': aia_info(),
        'docusign': docusign_info(),
    })


@app.route('/api/commitments/<int:commitment_id>/sage-sync', methods=['POST'])
@login_required
def api_commitment_sage_sync(commitment_id):
    from commitment_persistence import commitment_to_dict
    c = Commitment.query.get_or_404(commitment_id)
    body = request.get_json(silent=True) or {}
    event_type = body.get('event_type') or 'CommitmentUpdated'
    if c.status == 'Approved' and event_type == 'CommitmentUpdated':
        event_type = 'CommitmentApproved'
    event = _sage_commitment_event(
        c, event_type,
        message=body.get('message') or f'Manual Sage sync — {c.number}',
        extra={'manual': True},
        user_id=current_user.id,
    )
    from sage_service import sage_event_to_dict
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    db.session.refresh(c)
    return jsonify({
        'ok': True,
        'event': sage_event_to_dict(event),
        'commitment': commitment_to_dict(c, allocs),
    })


@app.route('/api/commitments/<int:commitment_id>/aia/export', methods=['GET'])
@login_required
def api_commitment_aia_export(commitment_id):
    from commitment_persistence import commitment_to_dict
    from aia_service import commitment_export_for_catina
    c = Commitment.query.get_or_404(commitment_id)
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify(commitment_export_for_catina(commitment_to_dict(c, allocs)))


@app.route('/api/commitments/<int:commitment_id>/aia/catina-link', methods=['POST'])
@login_required
def api_commitment_catina_link(commitment_id):
    from commitment_persistence import commitment_to_dict
    from aia_service import build_catina_create_url, build_catina_open_url
    c = Commitment.query.get_or_404(commitment_id)
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    cdict = commitment_to_dict(c, allocs)
    active = Project.query.get(c.project_id)
    project_dict = {
        'name': active.name if active else '',
        'number': active.number if active else '',
    }
    url = build_catina_open_url(c.external_document_id, c.external_document_url) if c.external_document_id else build_catina_create_url(cdict, project_dict)
    return jsonify({
        'ok': True,
        'url': url,
        'portal': 'AIA Contract Documents (Catina)',
        'configured': bool(__import__('aia_service').is_catina_configured()),
    })


@app.route('/api/commitments/<int:commitment_id>/aia/register-document', methods=['POST'])
@login_required
def api_commitment_register_aia_document(commitment_id):
    from commitment_persistence import commitment_to_dict
    from aia_service import register_external_document as link_doc
    c = Commitment.query.get_or_404(commitment_id)
    body = request.get_json(silent=True) or {}
    provider = body.get('provider') or 'catina'
    doc_id = body.get('document_id') or body.get('external_document_id')
    doc_url = body.get('document_url') or body.get('external_document_url')
    if not doc_id and not doc_url:
        return jsonify({'error': 'document_id or document_url required'}), 400
    link_doc(c, provider, doc_id or doc_url, doc_url, body.get('catina_project_id'))
    c.updated_at = datetime.utcnow()
    db.session.commit()
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify({'ok': True, 'commitment': commitment_to_dict(c, allocs)})


@app.route('/api/webhooks/docusign', methods=['POST'])
def api_docusign_webhook():
    from docusign_service import parse_webhook_payload
    raw = request.get_data()
    data = parse_webhook_payload(raw)
    if not data:
        return jsonify({'error': 'invalid payload'}), 400
    envelope_id = None
    status = None
    if isinstance(data, dict):
        envelope_id = data.get('envelopeId') or data.get('data', {}).get('envelopeId')
        status = data.get('status') or data.get('event')
    if envelope_id:
        c = Commitment.query.filter_by(docusign_envelope_id=envelope_id).first()
        if c:
            c.docusign_status = status or c.docusign_status
            if status in ('completed', 'Completed'):
                c.signature_status = 'fully_executed'
                c.executed_date = datetime.utcnow().date()
            c.updated_at = datetime.utcnow()
            db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/commitments/<int:commitment_id>/attachments', methods=['POST'])
@login_required
def api_upload_commitment_attachment(commitment_id):
    from commitment_persistence import commitment_to_dict, _parse_json
    c = Commitment.query.get_or_404(commitment_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    saved = save_uploaded_file(file, folder=f'commitments/{commitment_id}')
    if not saved:
        return jsonify({'error': 'invalid file type'}), 400
    items = _parse_json(c.attachments_json, [])
    items.append({
        'filename': saved,
        'original_name': file.filename,
        'uploaded_at': datetime.utcnow().isoformat() + 'Z',
        'uploaded_by_id': current_user.id,
    })
    c.attachments_json = json.dumps(items)
    db.session.commit()
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify({'ok': True, 'commitment': commitment_to_dict(c, allocs)})


@app.route('/uploads/commitments/<path:subpath>')
@login_required
def serve_commitment_attachment(subpath):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'commitments')
    return send_from_directory(directory, subpath)


@app.route('/deliveries')
@login_required
def deliveries_page():
    return render_template('deliveries.html')


@app.route('/inspections')
@login_required
def inspections_page():
    return render_template('inspections.html')


@app.route('/meeting-minutes')
@login_required
def meeting_minutes_page():
    return render_template('meeting_minutes.html')


@app.route('/pay-applications')
@login_required
def pay_applications_page():
    active = get_active_project()
    fin = _project_financial_context(active)
    return render_template(
        'pay_applications.html',
        project_original_contract_amount=fin['original_contract_amount'],
        project_contract_value=fin['contract_value'],
        project_contract_amount=fin['contract_amount'],
        project_contract_amount_source=fin['contract_amount_source'],
        project_default_retainage_percent=fin['default_retainage_percent'],
        project_sage_job=fin['sage_job'],
    )


@app.route('/program-settings')
@login_required
def program_settings():
    from program_settings_persistence import load_sage_defaults
    return render_template('program_settings.html', sage_defaults=load_sage_defaults())


@app.route('/api/program-settings/sage', methods=['GET'])
@login_required
def api_get_sage_program_settings():
    from program_settings_persistence import load_sage_defaults, SAGE_DEFAULT_KEYS
    sage = load_sage_defaults()
    return jsonify({'sage': sage, 'keys': SAGE_DEFAULT_KEYS})


@app.route('/api/program-settings/sage', methods=['PUT'])
@login_required
def api_save_sage_program_settings():
    if current_user.role != 'Admin':
        return jsonify({'error': 'Admin only'}), 403
    from program_settings_persistence import save_sage_defaults
    body = request.get_json(silent=True) or {}
    sage = save_sage_defaults(body.get('sage') or body)
    return jsonify({'ok': True, 'sage': sage})


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)




# ==================== PROFILE UPDATE ROUTE ====================

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        current_user.first_name = request.form.get('first_name', current_user.first_name)
        current_user.last_name = request.form.get('last_name', current_user.last_name)
        current_user.phone = request.form.get('phone', current_user.phone)

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('profile'))


# ==================== ERROR HANDLERS ====================

@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.errorhandler(404)
def page_not_found(e):
    if request.path == '/favicon.ico':
        return '', 204
    return 'Page not found', 404


@app.errorhandler(500)
def internal_server_error(e):
    db.session.rollback()
    return 'Internal server error', 500


@app.errorhandler(403)
def forbidden(e):
    flash("You do not have permission to access this resource.", "error")
    return redirect(url_for('dashboard'))


# ==================== ADMIN AUDIT LOG ====================

@app.route('/audit-log')
@login_required
@admin_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('audit_log.html', logs=logs)


# ==================== EMAIL PAGE ====================
@app.route('/email')
@login_required
def email_page():
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    return render_template(
        'email.html',
        users=[{'name': u.full_name, 'email': u.email} for u in users],
    )


# ==================== AUDIT LOG PAGE (Clean route for sidebar) ====================
@app.route('/audit_log')
@login_required
def audit_log_page():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('audit_log.html', logs=logs)


# ==================== NOTIFICATIONS ====================

@app.route('/notifications')
@login_required
def notifications():
    user_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    return render_template('notifications.html', notifications=user_notifications)


@app.route('/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        return jsonify({'success': False}), 403

    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True})


# ==================== GLOBAL SEARCH ====================

@app.route('/search')
@login_required
def global_search():
    query = request.args.get('q', '').strip()

    if not query or len(query) < 2:
        flash('Please enter at least 2 characters to search.', 'warning')
        return redirect(url_for('dashboard'))

    projects = Project.query.filter(Project.name.ilike(f'%{query}%')).limit(10).all()
    rfis = RFI.query.filter(RFI.subject.ilike(f'%{query}%')).limit(10).all()
    daily_logs = DailyLog.query.filter(DailyLog.work_performed.ilike(f'%{query}%')).limit(10).all()

    return render_template(
        'search_results.html',
        query=query,
        projects=projects,
        rfis=rfis,
        daily_logs=daily_logs
    )


# ==================== BUDGET API ====================

@app.route('/api/budget/state', methods=['GET'])
@login_required
def api_get_budget_state():
    from budget_persistence import get_budget_state as load_state
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    record, data = load_state(BudgetProjectState, project_id)
    if not record:
        return jsonify({'project_id': project_id, 'data': None, 'version': 0})
    return jsonify({
        'project_id': project_id,
        'data': data,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    })


@app.route('/api/budget/state', methods=['PUT'])
@login_required
def api_save_budget_state():
    from budget_persistence import merge_state_patch, save_budget_state as persist_state, get_budget_state as load_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project_id = int(project_id)
    patch = body.get('data') or body.get('patch') or {}
    full_replace = bool(body.get('full_replace'))
    record, existing = load_state(BudgetProjectState, project_id)
    if full_replace:
        merged = patch
    else:
        merged = merge_state_patch(existing, patch)
    record = persist_state(BudgetProjectState, db, project_id, merged, current_user.id)
    return jsonify({
        'ok': True,
        'project_id': project_id,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    })


@app.route('/api/budget/import-local', methods=['POST'])
@login_required
def api_import_budget_local():
    from budget_persistence import save_budget_state as persist_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    data = body.get('data')
    if not project_id or not isinstance(data, dict):
        return jsonify({'error': 'project_id and data required'}), 400
    record = persist_state(BudgetProjectState, db, int(project_id), data, current_user.id)
    return jsonify({'ok': True, 'version': record.version})


@app.route('/api/budget/pending-change-orders', methods=['GET'])
@login_required
def api_budget_pending_change_orders():
    from budget_persistence import PENDING_CO_STATUSES
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    cos = ChangeOrder.query.filter(
        ChangeOrder.project_id == project_id,
        ChangeOrder.status.in_(list(PENDING_CO_STATUSES) + ['Pending', 'Draft']),
    ).order_by(ChangeOrder.created_at.desc()).all()
    return jsonify({
        'change_orders': [{
            'id': co.id,
            'number': co.number,
            'description': co.description,
            'amount': co.amount,
            'status': co.status,
            'cost_code': co.cost_code,
        } for co in cos if co.status not in ('Approved', 'Rejected')],
    })


@app.route('/api/budget/publish', methods=['POST'])
@login_required
def api_publish_budget():
    """Finalize budget publish: mark Sage sync status on lines and queue Sage event."""
    from budget_persistence import get_budget_state, save_budget_state, mark_budget_lines_sage_status
    from sage_service import create_and_process_sage_event
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project_id = int(project_id)
    sage_status = body.get('sage_status', 'Synced')
    record, state = get_budget_state(BudgetProjectState, project_id)
    if not state:
        return jsonify({'error': 'no budget state'}), 400
    state = mark_budget_lines_sage_status(state, sage_status)
    record = save_budget_state(BudgetProjectState, db, project_id, state, current_user.id)
    project = Project.query.get(project_id)
    resolved_contract = state.get('budgetContractAmount')
    if resolved_contract in (None, ''):
        resolved_contract = _project_contract_amount(project)
    event = create_and_process_sage_event(
        SageSyncEvent, Project, db, project_id,
        'BudgetPublished',
        message=body.get('message', f'Budget revision {state.get("budgetRevision", "")} published'),
        payload={
            'revision': state.get('budgetRevision'),
            'lines_count': len(state.get('budgetLines') or []),
            'total_original': sum((l.get('original_budget') or 0) for l in (state.get('budgetLines') or [])),
            'contract_amount': resolved_contract,
            'original_contract_amount': _parse_float((project.get_details() if project else {}).get('original_contract_amount')),
        },
        user_id=current_user.id,
    )
    from sage_service import sage_event_to_dict
    return jsonify({
        'ok': True,
        'version': record.version,
        'event': sage_event_to_dict(event),
        'budgetLines': state.get('budgetLines'),
    })


# ==================== PAY APPLICATION API ====================

@app.route('/api/pay-applications/state', methods=['GET'])
@login_required
def api_get_pay_app_state():
    from pay_app_persistence import get_pay_app_state as load_state
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    record, data = load_state(PayAppProjectState, project_id)
    if not record:
        return jsonify({'project_id': project_id, 'data': None, 'version': 0})
    return jsonify({
        'project_id': project_id,
        'data': data,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    })


@app.route('/api/pay-applications/state', methods=['PUT'])
@login_required
def api_save_pay_app_state():
    from pay_app_persistence import merge_state_patch, save_pay_app_state as persist_state, get_pay_app_state as load_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project_id = int(project_id)
    patch = body.get('data') or body.get('patch') or {}
    full_replace = bool(body.get('full_replace'))
    record, existing = load_state(PayAppProjectState, project_id)
    if full_replace:
        merged = patch
    else:
        merged = merge_state_patch(existing, patch)
    record = persist_state(PayAppProjectState, db, project_id, merged, current_user.id)
    return jsonify({
        'ok': True,
        'project_id': project_id,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    })


@app.route('/api/pay-applications/import-local', methods=['POST'])
@login_required
def api_import_pay_app_local():
    from pay_app_persistence import save_pay_app_state as persist_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    data = body.get('data')
    if not project_id or not isinstance(data, dict):
        return jsonify({'error': 'project_id and data required'}), 400
    record = persist_state(PayAppProjectState, db, int(project_id), data, current_user.id)
    return jsonify({'ok': True, 'version': record.version})


# ==================== SAGE 300 SYNC API ====================

@app.route('/api/sage/sync-events', methods=['GET'])
@login_required
def api_list_sage_sync_events():
    from sage_service import sage_event_to_dict
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    limit = min(request.args.get('limit', 50, type=int), 200)
    events = SageSyncEvent.query.filter_by(project_id=project_id).order_by(SageSyncEvent.created_at.desc()).limit(limit).all()
    return jsonify({'events': [sage_event_to_dict(e) for e in events]})


@app.route('/api/sage/sync-events', methods=['POST'])
@login_required
def api_create_sage_sync_event():
    from sage_service import create_and_process_sage_event, sage_event_to_dict
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    event_type = body.get('event_type') or body.get('eventType')
    if not project_id or not event_type:
        return jsonify({'error': 'project_id and event_type required'}), 400
    auto = body.get('auto_process', True)
    event = create_and_process_sage_event(
        SageSyncEvent, Project, db, int(project_id),
        event_type,
        message=body.get('message', ''),
        payload=body.get('payload'),
        user_id=current_user.id,
        auto_process=auto,
    )
    return jsonify({'ok': True, 'event': sage_event_to_dict(event)})


@app.route('/api/sage/sync-events/<int:event_id>/retry', methods=['POST'])
@login_required
def api_retry_sage_sync_event(event_id):
    from sage_service import process_sage_event, sage_event_to_dict
    event = SageSyncEvent.query.get_or_404(event_id)
    event.status = 'queued'
    process_sage_event(event, db, Commitment=Commitment)
    return jsonify({'ok': True, 'event': sage_event_to_dict(event)})


# ==================== CHANGE ORDER & PCO API ====================

@app.route('/api/change-orders/dashboard', methods=['GET'])
@login_required
def api_change_orders_dashboard():
    from co_persistence import compute_dashboard_stats
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify(compute_dashboard_stats(ChangeOrder, PotentialChangeOrder, int(project_id)))


@app.route('/api/change-orders/cost-codes', methods=['GET'])
@login_required
def api_change_orders_cost_codes():
    from co_persistence import get_budget_cost_codes
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify({'cost_codes': get_budget_cost_codes(BudgetProjectState, int(project_id))})


@app.route('/api/change-orders', methods=['GET'])
@login_required
def api_list_change_orders():
    from co_persistence import co_to_dict
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    status = request.args.get('status')
    q = ChangeOrder.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    cos = q.order_by(ChangeOrder.created_at.desc()).all()
    result = []
    for co in cos:
        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        revs = ChangeOrderRevision.query.filter_by(change_order_id=co.id).order_by(ChangeOrderRevision.revision.desc()).all()
        revisions = [{'revision': r.revision, 'created_at': r.created_at.isoformat() if r.created_at else None, 'notes': r.notes} for r in revs]
        result.append(co_to_dict(co, allocs, revisions))
    return jsonify({'change_orders': result})


@app.route('/api/change-orders/<int:co_id>', methods=['GET'])
@login_required
def api_get_change_order(co_id):
    from co_persistence import co_to_dict
    co = ChangeOrder.query.get_or_404(co_id)
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    revs = ChangeOrderRevision.query.filter_by(change_order_id=co.id).order_by(ChangeOrderRevision.revision.desc()).all()
    revisions = [{'revision': r.revision, 'created_at': r.created_at.isoformat() if r.created_at else None, 'notes': r.notes, 'snapshot': json.loads(r.snapshot_json) if r.snapshot_json else None} for r in revs]
    return jsonify(co_to_dict(co, allocs, revisions))


@app.route('/api/change-orders/<int:co_id>/allocate', methods=['POST'])
@login_required
def api_allocate_change_order(co_id):
    from co_persistence import save_allocations
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    allocations = body.get('allocations') or []
    save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, allocations, db)
    if allocations:
        co.amount = sum(float(a.get('amount') or 0) for a in allocations)
        if len(allocations) == 1:
            co.cost_code = allocations[0].get('cost_code')
    elif body.get('cost_code'):
        co.cost_code = body.get('cost_code')
    db.session.commit()
    return jsonify({'ok': True, 'amount': co.amount})


@app.route('/api/change-orders', methods=['POST'])
@login_required
def api_create_change_order():
    from co_persistence import apply_co_fields, co_to_dict, save_allocations
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        description = (body.get('description') or body.get('title') or '').strip()
        if not description:
            return jsonify({'error': 'description required'}), 400
        number = generate_next_number('CO', ChangeOrder)
        co = ChangeOrder(
            project_id=int(project_id),
            number=number,
            description=description,
            status=body.get('status') or 'Draft',
            date=_parse_change_order_date(body.get('date')),
            ball_in_court_role='Creator',
            created_by_id=current_user.id,
        )
        apply_co_fields(co, body)
        db.session.add(co)
        db.session.flush()
        if body.get('allocations'):
            save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, body['allocations'], db)
            co.amount = sum(float(a.get('amount') or 0) for a in body['allocations'])
        db.session.commit()
        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        return jsonify({'ok': True, 'change_order': co_to_dict(co, allocs)})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/change-orders/<int:co_id>', methods=['PUT'])
@login_required
def api_update_change_order(co_id):
    from co_persistence import apply_co_fields, co_to_dict, save_allocations
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    apply_co_fields(co, body)
    if body.get('allocations') is not None:
        save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, body['allocations'], db)
        if body['allocations']:
            co.amount = sum(float(a.get('amount') or 0) for a in body['allocations'])
    db.session.commit()
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({'ok': True, 'change_order': co_to_dict(co, allocs)})


@app.route('/api/change-orders/<int:co_id>/revision', methods=['POST'])
@login_required
def api_create_co_revision(co_id):
    from co_persistence import co_to_dict
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    co.revision = (co.revision or 0) + 1
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    snapshot = co_to_dict(co, allocs)
    db.session.add(ChangeOrderRevision(
        change_order_id=co.id,
        revision=co.revision,
        snapshot_json=json.dumps(snapshot),
        notes=body.get('notes', ''),
        created_by_id=current_user.id,
    ))
    if co.status == 'Approved':
        co.status = 'Draft'
        co.ball_in_court_role = 'Creator'
    db.session.commit()
    return jsonify({'ok': True, 'revision': co.revision})


@app.route('/api/change-orders/<int:co_id>/sync-to-sov', methods=['POST'])
@login_required
def api_sync_change_order_to_sov(co_id):
    from pay_app_persistence import sync_change_order_to_sov
    try:
        result = sync_change_order_to_sov(
            ChangeOrder, ChangeOrderAllocation, PayAppProjectState,
            ScheduleData, Project, db, co_id, current_user.id,
        )
        return jsonify({'ok': True, **result})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/change-orders/link-options', methods=['GET'])
@login_required
def api_change_orders_link_options():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    rfis = RFI.query.filter_by(project_id=int(project_id)).order_by(RFI.created_at.desc()).limit(200).all()
    commitments = Commitment.query.filter_by(project_id=int(project_id)).order_by(Commitment.created_at.desc()).limit(200).all()
    return jsonify({
        'rfis': [{'id': r.id, 'number': r.number, 'subject': r.subject, 'status': r.status} for r in rfis],
        'commitments': [
            {
                'id': c.id,
                'number': c.number,
                'description': c.description,
                'commitment_type': c.commitment_type,
                'status': c.status,
                'amount': c.current_amount or c.original_amount,
                'company_name': c.company_name,
            }
            for c in commitments
        ],
    })


@app.route('/api/change-orders/<int:co_id>/workflow', methods=['POST'])
@login_required
def api_change_order_workflow(co_id):
    from co_persistence import co_workflow_action, notify_ball_in_court, co_to_dict
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    old_status = co.status
    try:
        new_status, final_approved = co_workflow_action(co, action, current_user, User)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if action == 'submit' and not co.submitted_at:
        co.submitted_at = datetime.utcnow()
        try:
            from case_workflow import create_approval
            create_approval(
                project_id=co.project_id,
                module='Change Orders',
                entity_type='ChangeOrder',
                entity_id=co.id,
                title=f'Change Order {co.number} submitted — {co.ball_in_court_role} review',
                description=co.description or '',
                action_url=f'/change-orders?project_id={co.project_id}',
                payload={'amount': co.amount, 'status': new_status, 'ball_in_court': co.ball_in_court_role},
                assignee_role=co.ball_in_court_role,
            )
        except Exception:
            pass
        from sage_service import create_and_process_sage_event
        create_and_process_sage_event(
            SageSyncEvent, Project, db, co.project_id,
            'ChangeOrderSubmitted',
            message=f'{co.number} submitted — ball with {co.ball_in_court_role}',
            payload={'change_order_id': co.id, 'amount': co.amount},
            user_id=current_user.id,
        )

    sync_result = None
    budget_sync_result = None
    if final_approved:
        co.approved_at = datetime.utcnow()
        co.approved_by_id = current_user.id
        try:
            from pay_app_persistence import sync_change_order_to_sov
            sync_result = sync_change_order_to_sov(
                ChangeOrder, ChangeOrderAllocation, PayAppProjectState,
                ScheduleData, Project, db, co.id, current_user.id,
            )
            co.sage_sync_status = 'sov_synced'
            from sage_service import create_and_process_sage_event
            create_and_process_sage_event(
                SageSyncEvent, Project, db, co.project_id,
                'ChangeOrderApproved',
                message=f'Change Order {co.number} approved — SOV and schedule updated',
                payload={'change_order_id': co.id, 'amount': co.amount, 'sync': sync_result},
                user_id=current_user.id,
            )
        except Exception as exc:
            co.sage_sync_status = f'sync_error:{str(exc)[:120]}'
            sync_result = {'error': str(exc)}
        try:
            from budget_persistence import sync_change_order_to_budget
            budget_sync_result = sync_change_order_to_budget(
                ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
                db, co.id, old_status, 'Approved', current_user.id,
            )
        except Exception:
            pass
    elif action in ('submit', 'approve') and co.ball_in_court_role:
        notify_ball_in_court(
            co.project_id, co, User,
            title=f'{co.number} — action required ({co.ball_in_court_role})',
            description=f'Status: {new_status}. {co.description or ""}',
        )
        if action == 'approve' and not final_approved:
            try:
                from case_workflow import create_approval
                create_approval(
                    project_id=co.project_id,
                    module='Change Orders',
                    entity_type='ChangeOrder',
                    entity_id=co.id,
                    title=f'Change Order {co.number} — {co.ball_in_court_role} approval',
                    description=co.description or '',
                    action_url=f'/change-orders?project_id={co.project_id}',
                    payload={'amount': co.amount, 'status': new_status},
                    assignee_role=co.ball_in_court_role,
                )
            except Exception:
                pass

    if action == 'reject':
        try:
            from budget_persistence import sync_change_order_to_budget
            budget_sync_result = sync_change_order_to_budget(
                ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
                db, co.id, old_status, 'Rejected', current_user.id,
            )
        except Exception:
            pass

    db.session.commit()
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({
        'ok': True,
        'new_status': new_status,
        'final_approved': final_approved,
        'ball_in_court_role': co.ball_in_court_role,
        'change_order': co_to_dict(co, allocs),
        'sync_result': sync_result,
        'budget_sync_result': budget_sync_result,
    })


@app.route('/api/change-orders/<int:co_id>/attachments', methods=['POST'])
@login_required
def api_upload_co_attachment(co_id):
    from co_persistence import append_attachment, attachment_record, co_to_dict
    co = ChangeOrder.query.get_or_404(co_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'change_orders', str(co_id))
    os.makedirs(folder, exist_ok=True)
    saved = save_uploaded_file(file, folder=f'change_orders/{co_id}')
    if not saved:
        return jsonify({'error': 'invalid file type'}), 400
    record = attachment_record(saved, file.filename, current_user.id)
    append_attachment(co, record)
    db.session.commit()
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({'ok': True, 'attachment': record, 'change_order': co_to_dict(co, allocs)})


@app.route('/api/pcos/<int:pco_id>/attachments', methods=['POST'])
@login_required
def api_upload_pco_attachment(pco_id):
    from co_persistence import pco_to_dict
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    saved = save_uploaded_file(file, folder=f'change_orders/pco_{pco_id}')
    if not saved:
        return jsonify({'error': 'invalid file type'}), 400
    # Store PCO attachments in notes/metadata via a simple JSON file list on pco notes field - use attachments on promote
    # For now store in pco notes append - better: add attachments_json to PCO
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'change_orders', f'pco_{pco_id}')
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({
        'ok': True,
        'attachment': {'filename': saved, 'original_name': file.filename, 'path': f'change_orders/pco_{pco_id}/{saved}'},
        'pco': pco_to_dict(pco, allocs),
    })


@app.route('/uploads/change_orders/<path:subpath>')
@login_required
def serve_co_attachment(subpath):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'change_orders')
    return send_from_directory(directory, subpath)


# ==================== PCO (Potential Change Order) API ====================

@app.route('/api/pcos', methods=['GET'])
@login_required
def api_list_pcos():
    from co_persistence import pco_to_dict
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    status = request.args.get('status')
    q = PotentialChangeOrder.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    pcos = q.order_by(PotentialChangeOrder.created_at.desc()).all()
    result = []
    for pco in pcos:
        allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
        result.append(pco_to_dict(pco, allocs))
    return jsonify({'pcos': result})


@app.route('/api/pcos/<int:pco_id>', methods=['GET'])
@login_required
def api_get_pco(pco_id):
    from co_persistence import pco_to_dict
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify(pco_to_dict(pco, allocs))


@app.route('/api/pcos', methods=['POST'])
@login_required
def api_create_pco():
    from co_persistence import apply_pco_fields, pco_to_dict, save_allocations
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    title = (body.get('title') or body.get('description') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    pco = PotentialChangeOrder(
        project_id=int(project_id),
        number=generate_next_number('PCO', PotentialChangeOrder),
        title=title,
        description=body.get('description') or title,
        status=body.get('status') or 'Open',
        ball_in_court_role='Project Manager',
        requested_by=body.get('requested_by') or f'{current_user.first_name} {current_user.last_name}'.strip(),
        created_by_id=current_user.id,
    )
    apply_pco_fields(pco, body)
    db.session.add(pco)
    db.session.flush()
    if body.get('allocations'):
        save_allocations(PCOAllocation, 'pco_id', pco.id, body['allocations'], db)
        pco.estimated_amount = sum(float(a.get('amount') or 0) for a in body['allocations'])
    db.session.commit()
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({'ok': True, 'pco': pco_to_dict(pco, allocs)})


@app.route('/api/pcos/<int:pco_id>', methods=['PUT'])
@login_required
def api_update_pco(pco_id):
    from co_persistence import apply_pco_fields, pco_to_dict, save_allocations
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    body = request.get_json(silent=True) or {}
    apply_pco_fields(pco, body)
    if body.get('allocations') is not None:
        save_allocations(PCOAllocation, 'pco_id', pco.id, body['allocations'], db)
        if body['allocations']:
            pco.estimated_amount = sum(float(a.get('amount') or 0) for a in body['allocations'])
    pco.updated_at = datetime.utcnow()
    db.session.commit()
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({'ok': True, 'pco': pco_to_dict(pco, allocs)})


@app.route('/api/pcos/<int:pco_id>/update-status', methods=['POST'])
@login_required
def api_update_pco_status(pco_id):
    from co_persistence import pco_to_dict
    from sage_service import create_and_process_sage_event
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    body = request.get_json(silent=True) or {}
    new_status = body.get('status')
    if not new_status:
        return jsonify({'error': 'status required'}), 400
    old_status = pco.status
    pco.status = new_status
    if new_status == 'Pending Review':
        pco.ball_in_court_role = 'Project Manager'
        try:
            from case_workflow import create_approval
            create_approval(
                project_id=pco.project_id,
                module='Change Orders',
                entity_type='PCO',
                entity_id=pco.id,
                title=f'PCO {pco.number} — {pco.title}',
                description=pco.description or '',
                action_url=f'/change-orders?project_id={pco.project_id}',
                payload={'estimated_amount': pco.estimated_amount, 'status': new_status, 'type': 'pco'},
            )
        except Exception:
            pass
        create_and_process_sage_event(
            SageSyncEvent, Project, db, pco.project_id,
            'PCOSubmitted',
            message=f'PCO {pco.number} submitted for review',
            payload={'pco_id': pco.id, 'estimated_amount': pco.estimated_amount},
            user_id=current_user.id,
        )
    db.session.commit()
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({'ok': True, 'pco': pco_to_dict(pco, allocs), 'old_status': old_status})


@app.route('/api/pcos/<int:pco_id>/promote', methods=['POST'])
@login_required
def api_promote_pco(pco_id):
    from co_persistence import promote_pco_to_co, co_to_dict, pco_to_dict
    from sage_service import create_and_process_sage_event
    try:
        co = promote_pco_to_co(
            PotentialChangeOrder, PCOAllocation, ChangeOrder, ChangeOrderAllocation,
            db, pco_id, current_user.id, generate_next_number,
        )
        pco = PotentialChangeOrder.query.get(pco_id)
        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        create_and_process_sage_event(
            SageSyncEvent, Project, db, co.project_id,
            'PCOPromoted',
            message=f'PCO {pco.number} promoted to {co.number}',
            payload={'pco_id': pco.id, 'change_order_id': co.id, 'amount': co.amount},
            user_id=current_user.id,
        )
        return jsonify({
            'ok': True,
            'change_order': co_to_dict(co, allocs),
            'pco': pco_to_dict(pco, PCOAllocation.query.filter_by(pco_id=pco.id).all()),
        })
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


# ==================== QUICK STATS API ====================

@app.route('/api/stats')
@login_required
def api_stats():
    stats = get_dashboard_stats()
    return jsonify(stats)




with app.app_context():
    try:
        import case_workflow as cw
        cw.register_workflow(app, db, {
            'User': User,
            'Project': Project,
            'Company': Company,
            'Notification': Notification,
            'AuditLog': AuditLog,
            'login_required': login_required,
        })
        db.create_all()
        cw.ensure_workflow_schema(db.engine)
        try:
            from pay_app_persistence import ensure_pay_app_schema
            ensure_pay_app_schema(db.engine, db)
        except Exception as _pe:
            print('Pay app schema:', _pe)
        try:
            from co_persistence import ensure_co_schema
            ensure_co_schema(db.engine, db)
        except Exception as _ce:
            print('CO schema:', _ce)
        try:
            from rfi_persistence import ensure_rfi_schema
            ensure_rfi_schema(db.engine, db)
        except Exception as _re:
            print('RFI schema:', _re)
        try:
            from drawing_persistence import ensure_drawing_schema
            ensure_drawing_schema(db.engine, db)
        except Exception as _dr:
            print('Drawing schema:', _dr)
        try:
            from commitment_persistence import ensure_commitment_schema
            ensure_commitment_schema(db.engine, db)
        except Exception as _cm:
            print('Commitment schema:', _cm)
    except Exception as _e:
        print('Workflow init:', _e)

# ==================== FINAL STARTUP & INITIALIZATION ====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        try:
            import case_workflow as cw
            cw.ensure_workflow_schema(db.engine)
        except Exception:
            pass

        # Create default admin user if it doesn't exist
        if not User.query.filter_by(email='admin@casepm.local').first():
            admin = User(
                first_name='Admin',
                last_name='User',
                email='admin@casepm.local',
                role='Admin',
                status='Active',
                must_change_password=True,
                require_2fa=False
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

            print("\n" + "=" * 75)
            print("✅ DEFAULT ADMIN ACCOUNT CREATED SUCCESSFULLY")
            print("-" * 75)
            print("   Email:    admin@casepm.local")
            print("   Password: admin123")
            print("   Role:     Admin")
            print("-" * 75)
            print("   ⚠️  IMPORTANT: You will be forced to change the password on first login.")
            print("=" * 75 + "\n")

        # Create uploads directory structure if it doesn't exist
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'coi'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'attachments'), exist_ok=True)

        try:
            from drawing_persistence import ensure_drawing_dependencies
            ensure_drawing_dependencies()
            print('✅ Drawing PDF libraries ready (pypdf, pymupdf)')
        except Exception as dep_exc:
            print(f'⚠️  Drawing upload libraries not available: {dep_exc}')
            print(f'   Run: {sys.executable} -m pip install -r requirements.txt')

    # Start the Flask development server
    print("\n" + "=" * 75)
    print("🚀 CASE PM - ULTIMATE VERSION STARTING")
    print("=" * 75)
    print("   Access the application at: http://127.0.0.1:5000")
    print("   Press CTRL+C to stop the server")
    print("=" * 75 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)


# ==================== END OF APPLICATION ====================
