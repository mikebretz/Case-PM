



# ============================================================
# Case PM - Ultimate Construction Project Management System
# Cleaned & Completed Full Version (vFinal)
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory, send_file
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
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 60},
}

from db_sqlite import commit_with_retry, register_sqlite_pragmas
register_sqlite_pragmas()


def _acting_user_id(explicit_user_id=None):
    """Resolve user id for background jobs (no Flask request / current_user)."""
    if explicit_user_id is not None:
        return explicit_user_id
    try:
        from flask import has_request_context
        if not has_request_context():
            return None
        user = current_user._get_current_object() if hasattr(current_user, '_get_current_object') else current_user
    except Exception:
        return None
    if user is None:
        return None
    try:
        if getattr(user, 'is_authenticated', False):
            return user.id
    except Exception:
        return None
    return None

db = SQLAlchemy(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB for large drawing sets

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
    attachments_json = db.Column(db.Text)
    details_json = db.Column(db.Text)
    status = db.Column(db.String(30), default='Submitted')
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
    cost_type = db.Column(db.String(80))
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
    cost_type = db.Column(db.String(80))
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
    attachments_json = db.Column(db.Text)
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
    category = db.Column(db.String(80))
    assigned_company = db.Column(db.String(150))
    completed_at = db.Column(db.DateTime)
    completed_by_id = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    details_json = db.Column(db.Text)
    attachments_json = db.Column(db.Text)


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


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('document_folder.id'))
    name = db.Column(db.String(300), nullable=False)
    document_type = db.Column(db.String(80), nullable=False, default='Other')
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300))
    file_size = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(120))
    is_system_locked = db.Column(db.Boolean, default=False)
    source_drawing_id = db.Column(db.Integer)
    source_sheet = db.Column(db.String(80))
    source_metadata_json = db.Column(db.Text)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime)
    version_count = db.Column(db.Integer, default=1)
    checked_out_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    checked_out_at = db.Column(db.DateTime)
    checkout_note = db.Column(db.String(500))
    tags_json = db.Column(db.Text)
    custom_metadata_json = db.Column(db.Text)
    content_hash = db.Column(db.String(64))
    retention_until = db.Column(db.DateTime)
    legal_hold = db.Column(db.Boolean, default=False)
    editor_kind = db.Column(db.String(20))   # 'sheet' | 'doc' — opens in built-in editor
    editor_content = db.Column(db.Text)      # serialized editor state (json for sheet, html for doc)


class DocumentFolder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('document_folder.id'))
    name = db.Column(db.String(200), nullable=False)
    is_system = db.Column(db.Boolean, default=False)
    system_key = db.Column(db.String(80))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime)


class DocumentShareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    token = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label = db.Column(db.String(200))
    password_hash = db.Column(db.String(256))
    expires_at = db.Column(db.DateTime)
    max_downloads = db.Column(db.Integer)
    download_count = db.Column(db.Integer, default=0)
    allow_download = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime)
    approval_status = db.Column(db.String(20), default='approved')
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)


class DocumentFolderShareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('document_folder.id'), nullable=False)
    token = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label = db.Column(db.String(200))
    password_hash = db.Column(db.String(256))
    expires_at = db.Column(db.DateTime)
    max_downloads = db.Column(db.Integer)
    download_count = db.Column(db.Integer, default=0)
    allow_browse = db.Column(db.Boolean, default=True)
    allow_download = db.Column(db.Boolean, default=True)
    allow_upload = db.Column(db.Boolean, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime)
    approval_status = db.Column(db.String(20), default='approved')
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)


class DocumentVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    version_no = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300))
    file_size = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(120))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DocumentComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    folder_id = db.Column(db.Integer, db.ForeignKey('document_folder.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(80), nullable=False)
    detail_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DocumentMarkup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user_name = db.Column(db.String(150))
    layer = db.Column(db.String(20), default='personal')
    markup_type = db.Column(db.String(30), nullable=False)
    geometry_json = db.Column(db.Text)
    style_json = db.Column(db.Text)
    label = db.Column(db.String(300))
    measurement_value = db.Column(db.Float)
    measurement_unit = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published_at = db.Column(db.DateTime)


class DocumentFolderPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('document_folder.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    can_view = db.Column(db.Boolean, default=True)
    can_upload = db.Column(db.Boolean, default=False)
    can_manage = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('folder_id', 'user_id', name='uq_folder_user_perm'),)


class DocumentFolderTemplate(db.Model):
    __tablename__ = 'document_folder_template'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    project_type = db.Column(db.String(80))
    description = db.Column(db.String(500))
    folders_json = db.Column(db.Text, nullable=False)
    is_system = db.Column(db.Boolean, default=False)
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
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    period_type = db.Column(db.String(20), default='weekly')  # 'weekly' | 'biweekly'
    details_json = db.Column(db.Text)
    notes = db.Column(db.Text)


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
ALLOWED_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tif', 'tiff',
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'csv', 'txt', 'rtf',
    'zip', 'rar', '7z', 'dwg', 'dxf',
    'json', 'html', 'htm',
}

# File extensions that can be opened in the built-in editors.
SHEET_EXTENSIONS = {'xlsx', 'xls', 'csv'}
DOC_EDITOR_EXTENSIONS = {'docx', 'doc', 'txt', 'rtf', 'html', 'htm'}

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
    active = get_active_project()
    return render_template('dashboard.html', active_project=active)


@app.route('/api/dashboard/summary', methods=['GET'])
@login_required
def api_dashboard_summary():
    from budget_persistence import get_budget_state
    from pay_app_persistence import get_pay_app_state
    from forecast_persistence import build_forecast_summary
    from dashboard_persistence import build_dashboard_summary
    from commitment_persistence import compute_dashboard_stats as commitment_dashboard
    from co_persistence import compute_dashboard_stats as co_dashboard

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    InternalMessage = None
    ApprovalRequest = None
    try:
        from case_workflow import InternalMessage as IM, ApprovalRequest as AR
        InternalMessage = IM
        ApprovalRequest = AR
    except Exception:
        pass

    budget_state = {}
    pay_state = {}
    forecast_summary = {}
    commitment_stats = {}
    co_stats = {}
    if project_id:
        _, budget_state = get_budget_state(BudgetProjectState, int(project_id))
        _, pay_state = get_pay_app_state(PayAppProjectState, int(project_id))
        project = Project.query.get(int(project_id))
        approved_co = _project_approved_change_orders_total(int(project_id))
        if project:
            forecast_summary = build_forecast_summary(project, budget_state, pay_state, approved_co)
        commitment_stats = commitment_dashboard(Commitment, int(project_id))
        co_stats = co_dashboard(ChangeOrder, PotentialChangeOrder, int(project_id))

    payload = build_dashboard_summary(
        project_id,
        current_user.id,
        Project=Project,
        DailyLog=DailyLog,
        ManpowerEntry=ManpowerEntry,
        RFI=RFI,
        ChangeOrder=ChangeOrder,
        PunchItem=PunchItem,
        Submittal=Submittal,
        SafetyReport=SafetyReport,
        ScheduleTask=ScheduleTask,
        ScheduleData=ScheduleData,
        Commitment=Commitment,
        User=User,
        InternalMessage=InternalMessage,
        ApprovalRequest=ApprovalRequest,
        budget_state=budget_state,
        pay_state=pay_state,
        forecast_summary=forecast_summary,
        commitment_stats=commitment_stats,
        co_stats=co_stats,
    )
    return jsonify(payload)


@app.route('/api/dashboard/weather', methods=['GET'])
@login_required
def api_dashboard_weather():
    """Live weather via Open-Meteo (geocode + current conditions)."""
    import urllib.error
    import urllib.parse
    import urllib.request

    city = (request.args.get('city') or '').strip()
    state = (request.args.get('state') or '').strip()
    if not city:
        active = get_active_project()
        if active:
            city = (active.city or '').strip()
            state = (active.state or '').strip()
            if not city and active.address:
                parts = [p.strip() for p in active.address.split(',')]
                if len(parts) >= 2:
                    city = parts[-2]
                    state = parts[-1][:2].strip()
    if not city:
        return jsonify({'error': 'No project location configured', 'ok': False}), 404

    query = urllib.parse.urlencode({'name': city, 'count': 5, 'language': 'en', 'format': 'json'})
    try:
        with urllib.request.urlopen(
            f'https://geocoding-api.open-meteo.com/v1/search?{query}',
            timeout=10,
        ) as resp:
            geo = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({'error': str(exc), 'ok': False}), 502

    results = geo.get('results') or []
    if not results:
        return jsonify({'error': f'Location not found: {city}', 'ok': False}), 404

    match = results[0]
    if state:
        state_up = state.upper()
        for r in results:
            admin = (r.get('admin1_code') or r.get('admin1') or '').upper()
            if state_up in admin or admin.startswith(state_up):
                match = r
                break

    lat = match.get('latitude')
    lon = match.get('longitude')
    label = ', '.join(filter(None, [match.get('name'), match.get('admin1')]))

    forecast_url = (
        'https://api.open-meteo.com/v1/forecast?'
        + urllib.parse.urlencode({
            'latitude': lat,
            'longitude': lon,
            'current': 'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature',
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'temperature_unit': 'fahrenheit',
            'wind_speed_unit': 'mph',
            'timezone': 'auto',
            'forecast_days': 1,
        })
    )
    try:
        with urllib.request.urlopen(forecast_url, timeout=10) as resp:
            wx = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return jsonify({'error': str(exc), 'ok': False}), 502

    current = wx.get('current') or {}
    daily = wx.get('daily') or {}
    code = int(current.get('weather_code') or 0)
    descriptions = {
        0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
        45: 'Foggy', 48: 'Depositing rime fog', 51: 'Light drizzle', 53: 'Drizzle',
        55: 'Dense drizzle', 61: 'Slight rain', 63: 'Rain', 65: 'Heavy rain',
        71: 'Slight snow', 73: 'Snow', 75: 'Heavy snow', 80: 'Rain showers',
        81: 'Moderate showers', 82: 'Violent showers', 95: 'Thunderstorm',
    }
    precip = 0
    if daily.get('precipitation_probability_max'):
        precip = daily['precipitation_probability_max'][0]

    return jsonify({
        'ok': True,
        'location': label,
        'city': match.get('name'),
        'state': match.get('admin1'),
        'temperature': round(float(current.get('temperature_2m') or 0)),
        'feels_like': round(float(current.get('apparent_temperature') or 0)),
        'humidity': int(current.get('relative_humidity_2m') or 0),
        'wind_mph': round(float(current.get('wind_speed_10m') or 0)),
        'high': round(float((daily.get('temperature_2m_max') or [0])[0])),
        'low': round(float((daily.get('temperature_2m_min') or [0])[0])),
        'precip_chance': int(precip or 0),
        'description': descriptions.get(code, 'Current conditions'),
        'weather_code': code,
        'updated_at': current.get('time'),
    })


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


def _project_approved_change_orders_total(project_id):
    """Sum approved change order amounts — allocation rows when present, else header amount."""
    if not project_id:
        return 0.0
    cos = ChangeOrder.query.filter_by(project_id=int(project_id), status='Approved').all()
    if not cos:
        return 0.0
    total = 0.0
    for co in cos:
        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        if allocs:
            total += sum(float(a.amount or 0) for a in allocs)
        else:
            total += float(co.amount or 0)
    return round(total, 2)


def _project_financial_context(project):
    """Shared contract/retainage defaults for budget and pay applications."""
    if not project:
        return {
            'original_contract_amount': None,
            'contract_value': None,
            'contract_amount': None,
            'contract_amount_source': None,
            'approved_change_orders_total': 0.0,
            'current_contract_value': None,
            'default_retainage_percent': None,
            'sage_job': '',
        }
    details = project.get_details()
    original = _parse_float(details.get('original_contract_amount'))
    contract_value = float(project.contract_value) if project.contract_value else None
    approved_co_total = _project_approved_change_orders_total(project.id)
    if original is not None:
        amount, source = original, 'original_contract'
        base_contract = original
    elif contract_value is not None:
        amount, source = contract_value, 'contract_value'
        base_contract = contract_value
    else:
        amount, source = None, None
        base_contract = None
    if base_contract is not None:
        current_contract_value = base_contract + approved_co_total
    else:
        current_contract_value = approved_co_total if approved_co_total else None
    retainage = _parse_float(details.get('default_retainage_percent'))
    return {
        'original_contract_amount': original,
        'contract_value': contract_value,
        'contract_amount': amount,
        'contract_amount_source': source,
        'approved_change_orders_total': approved_co_total,
        'current_contract_value': current_contract_value,
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
    companies_for_js = [{'name': c.name, 'type': c.type or ''} for c in companies]
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
        companies_for_js=companies_for_js,
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
            msg = 'Project name is required.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('projects_page'))

        next_num = Project.query.count() + 1
        raw_number = request.form.get('number') or f"PRJ-{next_num:03d}"
        number = _normalize_project_number(raw_number)
        conflict = _project_number_conflict(number)
        if conflict:
            msg = f'Project number "{number}" is already used by "{conflict.name}". Project numbers are not case-sensitive.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
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
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': True, 'project_id': project.id, 'project': project.to_dict()})
        return redirect(url_for('projects_page'))

    except Exception as e:
        db.session.rollback()
        err = str(e)
        if 'UNIQUE constraint failed' in err and 'project.number' in err:
            msg = 'That project number is already in use (not case-sensitive).'
        else:
            msg = f'Error creating project: {err}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': msg}), 400
        flash(msg, 'error')
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
        try:
            from budget_persistence import get_budget_state, save_budget_state, reconcile_budget_contract_from_project
            project_amt = _project_contract_amount(project)
            if project_amt is not None:
                record, state = get_budget_state(BudgetProjectState, project_id)
                state = state or {}
                state, changed = reconcile_budget_contract_from_project(state, project_amt)
                if changed:
                    save_budget_state(BudgetProjectState, db, project_id, state, current_user.id)
        except Exception:
            pass
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
    projects = Project.query.order_by(Project.name).all()
    active = get_active_project()
    return render_template('daily_log.html', projects=projects, active_project=active)


def _daily_log_url_helpers():
    return {
        'doc': lambda doc_id: url_for('api_documents_download', doc_id=doc_id),
        'attachment': lambda log_id, filename: url_for('serve_daily_log_attachment', log_id=log_id, filename=filename),
    }


@app.route('/api/daily-logs/companies', methods=['GET'])
@login_required
def api_daily_log_companies():
    """On-site companies for the manpower dropdown.

    Pulls subs/vendors that actually have commitments on the project (so the list
    reflects who is contracted and likely on site), plus the full company directory.
    """
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    seen = {}

    def add(name, company_id=None, source=None, contact=None, phone=None, ctype=None):
        key = (name or '').strip().lower()
        if not key:
            return
        if key not in seen:
            seen[key] = {
                'name': name.strip(),
                'company_id': str(company_id) if company_id is not None else None,
                'sources': [],
                'contact': contact or '',
                'phone': phone or '',
                'type': ctype or '',
            }
        if source and source not in seen[key]['sources']:
            seen[key]['sources'].append(source)

    if project_id:
        for c in Commitment.query.filter_by(project_id=int(project_id)).all():
            if c.company_name:
                label = 'Subcontract' if c.commitment_type == 'Subcontract' else 'Commitment'
                add(c.company_name, c.company_id, label,
                    contact=getattr(c, 'contact_name', None), phone=getattr(c, 'contact_phone', None))

    for c in Company.query.order_by(Company.name.asc()).all():
        contact = f'{c.contact_first_name or ""} {c.contact_last_name or ""}'.strip()
        add(c.name, c.id, 'Directory', contact=contact, phone=c.phone, ctype=c.type)

    companies = sorted(seen.values(), key=lambda x: (0 if ('Subcontract' in x['sources'] or 'Commitment' in x['sources']) else 1, x['name'].lower()))
    return jsonify({'ok': True, 'companies': companies})


@app.route('/api/daily-logs', methods=['GET'])
@login_required
def api_daily_logs_list():
    from daily_log_persistence import serialize_log, compute_stats
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = DailyLog.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    logs = q.order_by(DailyLog.date.desc(), DailyLog.id.desc()).limit(200).all()
    items = [serialize_log(l, ManpowerEntry, EquipmentEntry, User=User, summary=True) for l in logs]
    stats = compute_stats(DailyLog, ManpowerEntry, project_id)
    return jsonify({'ok': True, 'logs': items, 'stats': stats, 'project_id': project_id})


@app.route('/api/daily-logs', methods=['POST'])
@login_required
def api_daily_logs_create():
    from daily_log_persistence import build_details, sync_manpower, sync_equipment, serialize_log
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    date_str = body.get('date')
    if not project_id or not date_str:
        return jsonify({'error': 'project_id and date required'}), 400
    try:
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid date'}), 400

    log = DailyLog(
        project_id=int(project_id),
        user_id=current_user.id,
        date=log_date,
        weather=body.get('weather'),
        work_performed=body.get('work_performed'),
        notes=body.get('notes'),
        status=body.get('status') or 'Submitted',
        details_json=json.dumps(build_details(body)),
    )
    db.session.add(log)
    db.session.flush()
    sync_manpower(db, ManpowerEntry, log.id, body.get('manpower'))
    sync_equipment(db, EquipmentEntry, log.id, body.get('equipment'))
    db.session.commit()
    return jsonify({'ok': True, 'log': serialize_log(log, ManpowerEntry, EquipmentEntry, User=User, url_helpers=_daily_log_url_helpers())})


@app.route('/api/daily-logs/<int:log_id>', methods=['PUT'])
@login_required
def api_daily_logs_update(log_id):
    from daily_log_persistence import build_details, sync_manpower, sync_equipment, serialize_log
    log = DailyLog.query.get_or_404(log_id)
    body = request.get_json(silent=True) or {}
    if body.get('date'):
        try:
            log.date = datetime.strptime(body['date'], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return jsonify({'error': 'invalid date'}), 400
    for field in ('weather', 'work_performed', 'notes', 'status'):
        if field in body:
            setattr(log, field, body[field])
    log.details_json = json.dumps(build_details(body))
    sync_manpower(db, ManpowerEntry, log.id, body.get('manpower'))
    sync_equipment(db, EquipmentEntry, log.id, body.get('equipment'))
    db.session.commit()
    return jsonify({'ok': True, 'log': serialize_log(log, ManpowerEntry, EquipmentEntry, User=User, url_helpers=_daily_log_url_helpers())})


@app.route('/api/daily-logs/<int:log_id>', methods=['DELETE'])
@login_required
def api_daily_logs_delete(log_id):
    log = DailyLog.query.get_or_404(log_id)
    ManpowerEntry.query.filter_by(daily_log_id=log.id).delete()
    EquipmentEntry.query.filter_by(daily_log_id=log.id).delete()
    db.session.delete(log)
    db.session.commit()
    return jsonify({'ok': True})


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


@app.route('/api/daily-logs/<int:log_id>/attachments', methods=['POST'])
@login_required
def api_daily_log_upload_attachment(log_id):
    from rfi_persistence import _parse_json

    log = DailyLog.query.get_or_404(log_id)
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    custom_name = (request.form.get('name') or '').strip()
    kind = (request.form.get('kind') or '').strip()
    _, ext = os.path.splitext(f.filename)
    if custom_name:
        base = secure_filename(custom_name) or 'photo'
        display_name = custom_name if custom_name.lower().endswith(ext.lower()) else f'{custom_name}{ext}'
        safe = f'{base}{ext.lower()}'
        # Avoid collisions with existing files in the folder.
        folder = os.path.join(app.config['UPLOAD_FOLDER'], 'daily_logs', str(log_id))
        os.makedirs(folder, exist_ok=True)
        if os.path.exists(os.path.join(folder, safe)):
            safe = f'{base}-{int(datetime.utcnow().timestamp())}{ext.lower()}'
    else:
        safe = secure_filename(f.filename)
        display_name = f.filename
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'daily_logs', str(log_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe)
    f.save(path)
    attachments = _parse_json(log.attachments_json, [])
    att = {
        'filename': safe,
        'original_name': display_name,
        'kind': kind or None,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
    }
    attachments.append(att)
    log.attachments_json = json.dumps(attachments)
    db.session.commit()
    try:
        with open(path, 'rb') as fh:
            fb = fh.read()
        # File everything into Documents › Daily Logs › "Daily Log MM-DD-YYYY" (locked).
        sub_name = f"Daily Log {log.date.strftime('%m-%d-%Y')}" if log.date else 'Daily Log'
        doctype = 'Photo' if (kind or '').lower() == 'photo' else 'Daily Log'
        doc = _mirror_to_system_subfolder(
            log.project_id, fb, display_name, f.filename, 'daily-logs', sub_name, doctype,
            {
                'daily_log_id': log.id,
                'log_date': log.date.isoformat() if log.date else None,
                'photo_label': custom_name or display_name,
            },
            is_system_locked=True, uploaded_by_id=current_user.id,
        )
        if doc and doc.get('id'):
            att['document_id'] = doc['id']
            log.attachments_json = json.dumps(attachments)
            db.session.commit()
        _notify_documents_team(
            log.project_id,
            'Daily log photos filed',
            f'"{display_name}" filed to Documents › Daily Logs › {sub_name}.',
            f'/documents?project_id={log.project_id}',
        )
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/uploads/daily_logs/<int:log_id>/<path:filename>')
@login_required
def serve_daily_log_attachment(log_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'daily_logs', str(log_id))
    return send_from_directory(folder, filename)


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
        try:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', filename)
            if os.path.isfile(full_path):
                with open(full_path, 'rb') as fh:
                    fb = fh.read()
                label = (caption or filename).strip() or filename
                _mirror_to_system_folder(
                    int(project_id), fb, label, file.filename, 'photos', 'Photo',
                    {'photo_id': photo.id, 'caption': caption},
                )
                _notify_documents_team(
                    int(project_id),
                    'Photo filed to Documents',
                    f'"{label}" was copied to Documents › Photos.',
                    f'/documents?project_id={project_id}',
                )
        except Exception:
            pass
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
    payload = rfi_to_dict(rfi, linked_cos, linked_pcos)
    payload['attachments'] = _enrich_rfi_attachments(rfi_id, payload.get('attachments') or [])
    return jsonify(payload)


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


def _enrich_rfi_attachments(rfi_id, attachments):
    from rfi_persistence import _parse_json
    items = _parse_json(attachments, []) if not isinstance(attachments, list) else list(attachments)
    for a in items:
        if a.get('document_id'):
            a['url'] = url_for('api_documents_download', doc_id=a['document_id'])
            a['source'] = 'documents'
        elif a.get('filename'):
            a['url'] = url_for('serve_rfi_attachment', rfi_id=rfi_id, filename=a['filename'])
            a['source'] = 'upload'
    return items


@app.route('/api/rfis/<int:rfi_id>/attachments', methods=['GET'])
@login_required
def api_rfi_list_attachments(rfi_id):
    from rfi_persistence import _parse_json
    rfi = RFI.query.get_or_404(rfi_id)
    attachments = _enrich_rfi_attachments(rfi_id, _parse_json(rfi.attachments_json, []))
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/api/rfis/<int:rfi_id>/attachments', methods=['POST'])
@login_required
def api_rfi_upload_attachment(rfi_id):
    from rfi_persistence import apply_rfi_fields, _parse_json
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
    att = {
        'filename': safe,
        'original_name': f.filename,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
    }
    attachments.append(att)
    apply_rfi_fields(rfi, {'attachments': attachments})
    db.session.commit()
    try:
        with open(path, 'rb') as fh:
            fb = fh.read()
        # File into Documents › RFIs › "<RFI number>" (locked) so it's always findable.
        sub_name = (rfi.number or f'RFI-{rfi.id}').strip()
        doc = _mirror_to_system_subfolder(
            rfi.project_id, fb, f'{sub_name} — {f.filename}', f.filename, 'rfis', sub_name, 'RFI',
            {'rfi_id': rfi.id, 'rfi_number': rfi.number},
            is_system_locked=True, uploaded_by_id=current_user.id,
        )
        if doc and doc.get('id'):
            att['document_id'] = doc['id']
            apply_rfi_fields(rfi, {'attachments': attachments})
            db.session.commit()
        _notify_documents_team(
            rfi.project_id,
            'RFI attachment filed',
            f'"{f.filename}" filed to Documents › RFIs › {sub_name}.',
            f'/documents?project_id={rfi.project_id}',
        )
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True, 'attachments': _enrich_rfi_attachments(rfi_id, attachments)})


@app.route('/api/rfis/<int:rfi_id>/attachments/link', methods=['POST'])
@login_required
def api_rfi_link_document_attachment(rfi_id):
    from rfi_persistence import apply_rfi_fields, _parse_json
    rfi = RFI.query.get_or_404(rfi_id)
    body = request.get_json(silent=True) or {}
    doc_id = body.get('document_id')
    if not doc_id:
        return jsonify({'error': 'document_id required'}), 400
    doc = Document.query.get_or_404(int(doc_id))
    if doc.project_id != rfi.project_id:
        return jsonify({'error': 'Document belongs to a different project'}), 400
    if doc.deleted_at:
        return jsonify({'error': 'Document is in trash'}), 400
    attachments = _parse_json(rfi.attachments_json, [])
    if any(a.get('document_id') == doc.id for a in attachments):
        return jsonify({'ok': True, 'attachments': _enrich_rfi_attachments(rfi_id, attachments)})
    attachments.append({
        'document_id': doc.id,
        'original_name': doc.name or doc.original_filename or doc.filename,
        'linked_from_documents': True,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
    })
    apply_rfi_fields(rfi, {'attachments': attachments})
    db.session.commit()
    return jsonify({'ok': True, 'attachments': _enrich_rfi_attachments(rfi_id, attachments)})


def _attachment_user_label():
    return f'{current_user.first_name} {current_user.last_name}'.strip() or current_user.email or 'User'


def _link_document_to_json_attachments(entity, project_id, doc_ids, attachments_json):
    from rfi_persistence import _parse_json
    attachments = _parse_json(attachments_json, [])
    linked = []
    for raw_id in doc_ids or []:
        doc_id = int(raw_id)
        doc = Document.query.get(doc_id)
        if not doc or doc.project_id != int(project_id) or doc.deleted_at:
            raise ValueError(f'Document #{doc_id} is not available for this project')
        if any(a.get('document_id') == doc.id for a in attachments):
            continue
        attachments.append({
            'document_id': doc.id,
            'original_name': doc.name or doc.original_filename or doc.filename,
            'linked_from_documents': True,
            'uploaded_at': datetime.utcnow().isoformat(),
            'uploaded_by': _attachment_user_label(),
        })
        linked.append(doc.id)
    return attachments, linked


@app.route('/api/attachments/link', methods=['POST'])
@login_required
def api_link_documents_to_entity():
    from rfi_persistence import _parse_json, apply_rfi_fields
    from co_persistence import append_attachment
    body = request.get_json(silent=True) or {}
    entity_type = (body.get('entity_type') or '').lower().replace('-', '_')
    entity_id = body.get('entity_id')
    doc_ids = body.get('document_ids') or []
    if body.get('document_id'):
        doc_ids.append(body.get('document_id'))
    if not entity_type or not entity_id or not doc_ids:
        return jsonify({'error': 'entity_type, entity_id, and document_ids required'}), 400
    entity_id = int(entity_id)
    try:
        if entity_type == 'rfi':
            rfi = RFI.query.get_or_404(entity_id)
            attachments, linked = _link_document_to_json_attachments(rfi, rfi.project_id, doc_ids, rfi.attachments_json)
            apply_rfi_fields(rfi, {'attachments': attachments})
            db.session.commit()
            return jsonify({'ok': True, 'linked': linked, 'attachments': _enrich_rfi_attachments(rfi.id, attachments)})
        if entity_type == 'submittal':
            submittal = Submittal.query.get_or_404(entity_id)
            attachments, linked = _link_document_to_json_attachments(submittal, submittal.project_id, doc_ids, submittal.attachments_json)
            submittal.attachments_json = json.dumps(attachments)
            db.session.commit()
            for a in attachments:
                if a.get('filename'):
                    a['url'] = url_for('serve_submittal_attachment', submittal_id=submittal.id, filename=a.get('filename', ''))
                elif a.get('document_id'):
                    a['url'] = url_for('api_documents_download', doc_id=a['document_id'])
            return jsonify({'ok': True, 'linked': linked, 'attachments': attachments})
        if entity_type == 'daily_log':
            log = DailyLog.query.get_or_404(entity_id)
            attachments, linked = _link_document_to_json_attachments(log, log.project_id, doc_ids, log.attachments_json)
            log.attachments_json = json.dumps(attachments)
            db.session.commit()
            for a in attachments:
                if a.get('document_id'):
                    a['url'] = url_for('api_documents_download', doc_id=a['document_id'])
                elif a.get('filename'):
                    a['url'] = url_for('serve_daily_log_attachment', log_id=log.id, filename=a.get('filename', ''))
            return jsonify({'ok': True, 'linked': linked, 'attachments': attachments})
        if entity_type in ('change_order', 'co'):
            co = ChangeOrder.query.get_or_404(entity_id)
            for raw_id in doc_ids:
                doc = Document.query.get_or_404(int(raw_id))
                if doc.project_id != co.project_id:
                    return jsonify({'error': 'Document belongs to a different project'}), 400
                items = append_attachment(co, {
                    'document_id': doc.id,
                    'filename': None,
                    'original_name': doc.name or doc.original_filename or doc.filename,
                    'linked_from_documents': True,
                    'uploaded_at': datetime.utcnow().isoformat() + 'Z',
                    'uploaded_by_id': current_user.id,
                })
            db.session.commit()
            from co_persistence import co_to_dict
            allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
            return jsonify({'ok': True, 'linked': [int(x) for x in doc_ids], 'change_order': co_to_dict(co, allocs), 'attachments': items})
        if entity_type == 'commitment':
            c = Commitment.query.get_or_404(entity_id)
            attachments, linked = _link_document_to_json_attachments(c, c.project_id, doc_ids, c.attachments_json)
            c.attachments_json = json.dumps(attachments)
            db.session.commit()
            from commitment_persistence import commitment_to_dict
            allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
            return jsonify({'ok': True, 'linked': linked, 'attachments': attachments, 'commitment': commitment_to_dict(c, allocs)})
        return jsonify({'error': f'Unsupported entity_type: {entity_type}'}), 400
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400


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

    from co_persistence import run_change_order_accounting_sync
    accounting = run_change_order_accounting_sync(
        co, old_status, new_status, current_user.id,
        ChangeOrder=ChangeOrder,
        ChangeOrderAllocation=ChangeOrderAllocation,
        PayAppProjectState=PayAppProjectState,
        ScheduleData=ScheduleData,
        Project=Project,
        BudgetProjectState=BudgetProjectState,
        db=db,
        Commitment=Commitment,
        CommitmentAllocation=CommitmentAllocation,
        SageSyncEvent=SageSyncEvent,
        queue_sage_event=(new_status == 'Approved' and old_status != 'Approved'),
    )
    sync_result = accounting.get('sync_result')
    budget_sync_result = accounting.get('budget_sync_result')

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


@app.route('/api/submittals/<int:submittal_id>/attachments', methods=['POST'])
@login_required
def api_submittal_upload_attachment(submittal_id):
    from rfi_persistence import _parse_json

    submittal = Submittal.query.get_or_404(submittal_id)
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    safe = secure_filename(f.filename)
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'submittals', str(submittal_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe)
    f.save(path)
    attachments = _parse_json(submittal.attachments_json, [])
    attachments.append({
        'filename': safe,
        'original_name': f.filename,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
    })
    submittal.attachments_json = json.dumps(attachments)
    db.session.commit()
    try:
        with open(path, 'rb') as fh:
            fb = fh.read()
        _mirror_to_system_folder(
            submittal.project_id, fb, f'{submittal.number} — {safe}', f.filename, 'submittals', 'Submittal',
            {'submittal_id': submittal.id, 'submittal_number': submittal.number},
        )
        _notify_documents_team(
            submittal.project_id,
            'Submittal attachment filed',
            f'"{f.filename}" was archived to Documents › Submittals.',
            f'/documents?project_id={submittal.project_id}',
        )
    except Exception:
        pass
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/uploads/submittals/<int:submittal_id>/<path:filename>')
@login_required
def serve_submittal_attachment(submittal_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'submittals', str(submittal_id))
    return send_from_directory(folder, filename)


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

    try:
        with open(pdf_path, 'rb') as fh:
            fb = fh.read()
        _mirror_to_system_folder(
            int(project_id), fb, meta['filename'], file.filename, 'specifications', 'Specification',
            {'spec_book': True},
        )
        _notify_documents_team(
            int(project_id),
            'Specifications book filed',
            f'"{meta["filename"]}" was archived to Documents › Specifications.',
            f'/documents?project_id={project_id}',
        )
    except Exception:
        pass

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

    try:
        with open(pdf_path, 'rb') as fh:
            fb = fh.read()
        _mirror_to_system_folder(
            int(project_id), fb, meta['filename'], file.filename, 'contracts', 'Contract',
            {'original_contract': True},
        )
        _notify_documents_team(
            int(project_id),
            'Contract filed to Documents',
            f'"{meta["filename"]}" was archived to Documents › Contracts.',
            f'/documents?project_id={project_id}',
        )
    except Exception:
        pass

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
    projects = Project.query.order_by(Project.name).all()
    return render_template('punch_list.html', projects=projects, active_project=get_active_project())


def _punch_url_helpers():
    return {
        'doc': lambda doc_id: url_for('api_documents_download', doc_id=doc_id),
        'attachment': lambda item_id, filename: url_for('serve_punch_attachment', item_id=item_id, filename=filename),
    }


@app.route('/uploads/punch/<int:item_id>/<path:filename>')
@login_required
def serve_punch_attachment(item_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'punch', str(item_id))
    return send_from_directory(folder, filename)


@app.route('/api/punch-items', methods=['GET'])
@login_required
def api_punch_items_list():
    from punch_persistence import serialize_item, compute_stats, CATEGORIES, STATUSES, PRIORITIES
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = PunchItem.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    items = q.order_by(PunchItem.created_at.desc()).all()
    return jsonify({
        'ok': True,
        'items': [serialize_item(i, User=User, summary=True) for i in items],
        'stats': compute_stats(PunchItem, project_id),
        'categories': list(CATEGORIES),
        'statuses': list(STATUSES),
        'priorities': list(PRIORITIES),
        'project_id': project_id,
    })


def _punch_apply(item, body):
    from punch_persistence import build_details
    for field in ('description', 'location', 'trade', 'category', 'priority', 'assigned_to', 'assigned_company'):
        if field in body:
            setattr(item, field, body[field])
    if 'due_date' in body:
        due = body.get('due_date')
        try:
            item.due_date = datetime.strptime(due, '%Y-%m-%d').date() if due else None
        except (TypeError, ValueError):
            pass
    if 'status' in body and body['status']:
        _punch_set_status(item, body['status'])
    if 'subtasks' in body:
        details = json.loads(item.details_json) if item.details_json else {}
        details['subtasks'] = build_details(body)['subtasks']
        item.details_json = json.dumps(details)


def _punch_set_status(item, status):
    from punch_persistence import OPEN_STATUSES
    item.status = status
    if status == 'Closed':
        item.completed_at = datetime.utcnow()
        item.completed_by_id = current_user.id
    elif status in OPEN_STATUSES:
        item.completed_at = None
        item.completed_by_id = None


@app.route('/api/punch-items', methods=['POST'])
@login_required
def api_punch_items_create():
    from punch_persistence import serialize_item
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    description = (body.get('description') or '').strip()
    if not project_id or not description:
        return jsonify({'error': 'project_id and description required'}), 400
    item = PunchItem(
        project_id=int(project_id),
        number=generate_next_number('PL', PunchItem),
        description=description,
        priority=body.get('priority') or 'Medium',
        status=body.get('status') or 'Open',
        created_by_id=current_user.id,
    )
    _punch_apply(item, body)
    db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'item': serialize_item(item, User=User, url_helpers=_punch_url_helpers())})


@app.route('/api/punch-items/<int:item_id>', methods=['GET'])
@login_required
def api_punch_item_get(item_id):
    from punch_persistence import serialize_item
    item = PunchItem.query.get_or_404(item_id)
    return jsonify({'ok': True, 'item': serialize_item(item, User=User, url_helpers=_punch_url_helpers())})


@app.route('/api/punch-items/<int:item_id>', methods=['PUT'])
@login_required
def api_punch_items_update(item_id):
    from punch_persistence import serialize_item
    item = PunchItem.query.get_or_404(item_id)
    body = request.get_json(silent=True) or {}
    _punch_apply(item, body)
    db.session.commit()
    return jsonify({'ok': True, 'item': serialize_item(item, User=User, url_helpers=_punch_url_helpers())})


@app.route('/api/punch-items/<int:item_id>/status', methods=['POST'])
@login_required
def api_punch_item_status(item_id):
    """Fast check-off / status change for field use."""
    from punch_persistence import serialize_item
    item = PunchItem.query.get_or_404(item_id)
    body = request.get_json(silent=True) or {}
    status = body.get('status')
    if not status:
        return jsonify({'error': 'status required'}), 400
    _punch_set_status(item, status)
    db.session.commit()
    return jsonify({'ok': True, 'item': serialize_item(item, User=User, summary=True)})


@app.route('/api/punch-items/<int:item_id>/comment', methods=['POST'])
@login_required
def api_punch_item_comment(item_id):
    from punch_persistence import add_comment, serialize_item
    item = PunchItem.query.get_or_404(item_id)
    body = request.get_json(silent=True) or {}
    text = (body.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'text required'}), 400
    author = f'{current_user.first_name} {current_user.last_name}'.strip()
    add_comment(item, text, author)
    db.session.commit()
    return jsonify({'ok': True, 'item': serialize_item(item, User=User, url_helpers=_punch_url_helpers())})


@app.route('/api/punch-items/<int:item_id>', methods=['DELETE'])
@login_required
def api_punch_items_delete(item_id):
    item = PunchItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/punch-items/<int:item_id>/attachments', methods=['POST'])
@login_required
def api_punch_item_upload_attachment(item_id):
    from rfi_persistence import _parse_json
    item = PunchItem.query.get_or_404(item_id)
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    custom_name = (request.form.get('name') or '').strip()
    kind = (request.form.get('kind') or '').strip()
    _, ext = os.path.splitext(f.filename)
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'punch', str(item_id))
    os.makedirs(folder, exist_ok=True)
    if custom_name:
        base = secure_filename(custom_name) or 'photo'
        display_name = custom_name if custom_name.lower().endswith(ext.lower()) else f'{custom_name}{ext}'
        safe = f'{base}{ext.lower()}'
        if os.path.exists(os.path.join(folder, safe)):
            safe = f'{base}-{int(datetime.utcnow().timestamp())}{ext.lower()}'
    else:
        safe = secure_filename(f.filename)
        display_name = f.filename
    path = os.path.join(folder, safe)
    f.save(path)
    attachments = _parse_json(item.attachments_json, [])
    att = {
        'filename': safe,
        'original_name': display_name,
        'kind': kind or None,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
    }
    attachments.append(att)
    item.attachments_json = json.dumps(attachments)
    db.session.commit()
    try:
        with open(path, 'rb') as fh:
            fb = fh.read()
        sub_name = (item.number or f'Punch-{item.id}').strip()
        doc = _mirror_to_system_subfolder(
            item.project_id, fb, display_name, f.filename, 'photos', f'Punch List — {sub_name}', 'Photo',
            {'punch_item_id': item.id, 'punch_number': item.number, 'photo_label': custom_name or display_name},
            is_system_locked=True, uploaded_by_id=current_user.id,
        )
        if doc and doc.get('id'):
            att['document_id'] = doc['id']
            item.attachments_json = json.dumps(attachments)
            db.session.commit()
    except Exception:
        db.session.rollback()
    from punch_persistence import serialize_item
    return jsonify({'ok': True, 'item': serialize_item(item, User=User, url_helpers=_punch_url_helpers())})


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
    companies_for_js = [{'id': c.id, 'name': c.name, 'type': c.type or ''} for c in companies]
    return render_template('companies.html', companies=companies, companies_for_js=companies_for_js)


@app.route('/api/companies/sync', methods=['POST'])
@login_required
def api_sync_company():
    """Upsert a company from the Companies UI (localStorage) into the database."""
    body = request.get_json(silent=True) or {}
    name = (body.get('company_name') or body.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Company name is required'}), 400

    company_type = (body.get('company_type') or body.get('type') or 'Client').strip()
    email = (body.get('primary_email') or body.get('email') or '').strip() or None
    phone = (body.get('primary_phone') or body.get('phone') or '').strip() or None
    tax_id = (body.get('tax_id') or '').strip() or None
    license_number = (body.get('license_number') or '').strip() or None

    from sqlalchemy import func
    existing = Company.query.filter(func.lower(Company.name) == name.lower()).first()
    if existing:
        existing.type = company_type
        if email:
            existing.email = email
        if phone:
            existing.phone = phone
        if tax_id:
            existing.tax_id = tax_id
        if license_number:
            existing.license_number = license_number
        company = existing
    else:
        company = Company(
            name=name,
            type=company_type,
            email=email,
            phone=phone,
            tax_id=tax_id,
            license_number=license_number,
        )
        db.session.add(company)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'ok': True,
        'company': {'id': company.id, 'name': company.name, 'type': company.type or ''},
    })


@app.route('/api/companies/clients', methods=['GET'])
@login_required
def api_client_companies():
    """Client / Owner companies for project dropdowns."""
    rows = Company.query.order_by(Company.name.asc()).all()
    clients = []
    for c in rows:
        t = (c.type or '').lower()
        if not t or 'client' in t or 'owner' in t:
            clients.append({'id': c.id, 'name': c.name, 'type': c.type or ''})
    return jsonify({'ok': True, 'clients': clients})


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
    projects = Project.query.order_by(Project.name).all()
    return render_template('weekly_report.html', projects=projects, active_project=get_active_project())


@app.route('/api/weekly-reports', methods=['GET'])
@login_required
def api_weekly_reports_list():
    from weekly_report_persistence import serialize_report, compute_stats
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = WeeklyReport.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    reports = q.order_by(WeeklyReport.week_ending.desc(), WeeklyReport.id.desc()).limit(200).all()
    items = [serialize_report(r, User=User, summary=True) for r in reports]
    stats = compute_stats(WeeklyReport, project_id)
    return jsonify({'ok': True, 'reports': items, 'stats': stats, 'project_id': project_id})


@app.route('/api/weekly-reports/compile', methods=['GET'])
@login_required
def api_weekly_reports_compile():
    from weekly_report_persistence import compile_from_daily_logs, default_period
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    period_type = request.args.get('period_type') or 'weekly'
    start_s = request.args.get('start')
    end_s = request.args.get('end')
    try:
        if start_s and end_s:
            start = datetime.strptime(start_s, '%Y-%m-%d').date()
            end = datetime.strptime(end_s, '%Y-%m-%d').date()
        else:
            start, end = default_period(period_type)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid dates'}), 400
    result = compile_from_daily_logs(DailyLog, ManpowerEntry, EquipmentEntry, int(project_id), start, end)
    result['start'] = start.isoformat()
    result['end'] = end.isoformat()
    result['ok'] = True
    return jsonify(result)


def _weekly_report_apply(report, body):
    from weekly_report_persistence import build_details
    if body.get('period_start'):
        try:
            report.period_start = datetime.strptime(body['period_start'], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            pass
    if body.get('period_end'):
        try:
            report.period_end = datetime.strptime(body['period_end'], '%Y-%m-%d').date()
            report.week_ending = report.period_end
        except (TypeError, ValueError):
            pass
    for field in ('work_performed', 'safety_notes', 'notes', 'status', 'period_type'):
        if field in body:
            setattr(report, field, body[field])
    report.details_json = json.dumps(build_details(body))


@app.route('/api/weekly-reports', methods=['POST'])
@login_required
def api_weekly_reports_create():
    from weekly_report_persistence import serialize_report
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    end_s = body.get('period_end') or body.get('week_ending')
    if not end_s:
        return jsonify({'error': 'period_end required'}), 400
    try:
        week_ending = datetime.strptime(end_s, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid period_end'}), 400
    report = WeeklyReport(
        project_id=int(project_id),
        week_ending=week_ending,
        status=body.get('status') or 'Submitted',
        created_by_id=current_user.id,
    )
    _weekly_report_apply(report, body)
    db.session.add(report)
    db.session.commit()
    return jsonify({'ok': True, 'report': serialize_report(report, User=User)})


@app.route('/api/weekly-reports/<int:report_id>', methods=['GET'])
@login_required
def api_weekly_report_get(report_id):
    from weekly_report_persistence import serialize_report
    report = WeeklyReport.query.get_or_404(report_id)
    return jsonify({'ok': True, 'report': serialize_report(report, User=User)})


@app.route('/api/weekly-reports/<int:report_id>', methods=['PUT'])
@login_required
def api_weekly_reports_update(report_id):
    from weekly_report_persistence import serialize_report
    report = WeeklyReport.query.get_or_404(report_id)
    body = request.get_json(silent=True) or {}
    _weekly_report_apply(report, body)
    db.session.commit()
    return jsonify({'ok': True, 'report': serialize_report(report, User=User)})


@app.route('/api/weekly-reports/<int:report_id>', methods=['DELETE'])
@login_required
def api_weekly_reports_delete(report_id):
    report = WeeklyReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    return jsonify({'ok': True})


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


@app.route('/documents/viewer')
@login_required
def document_viewer_page():
    return render_template('document_viewer.html')


@app.route('/documents/sheet')
@login_required
def document_sheet_editor_page():
    return render_template('sheet_editor.html', active_project=get_active_project())


@app.route('/documents/word')
@login_required
def document_word_editor_page():
    return render_template('word_editor.html', active_project=get_active_project())


@app.route('/api/documents/<int:doc_id>/editor-content', methods=['GET'])
@login_required
def api_document_editor_content(doc_id):
    """Return the editable content + metadata for the built-in Sheet/Word editors."""
    from document_persistence import _editor_kind_for
    doc = Document.query.get_or_404(doc_id)
    kind = _editor_kind_for(doc)
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id))
    file_path = os.path.join(directory, doc.filename)
    return jsonify({
        'ok': True,
        'id': doc.id,
        'name': doc.name,
        'original_filename': doc.original_filename,
        'editor_kind': kind,
        'has_editor_content': bool(doc.editor_content),
        'editor_content': doc.editor_content,
        'download_url': url_for('api_documents_download', doc_id=doc.id),
        'file_exists': os.path.isfile(file_path),
        'folder_id': doc.folder_id,
    })


@app.route('/api/documents/editor/save', methods=['POST'])
@login_required
def api_document_editor_save():
    """Create or update a Sheet/Word document from the built-in editors.

    Accepts multipart form:
      - doc_id (optional): update existing, else create
      - kind: 'sheet' | 'doc'
      - name: display name
      - folder_id (optional): target folder for new docs
      - content: serialized editor state (json for sheet, html for doc)
      - file (optional): exported .xlsx/.docx/.txt blob to store as the downloadable file
    """
    from document_features import file_content_hash
    from document_integration import guess_mime
    from document_persistence import (
        ensure_document_schema, ensure_system_folders, resolve_folder_by_key, document_folder,
    )

    ensure_project_schema()
    ensure_document_schema(db.engine, db)

    doc_id = request.form.get('doc_id', type=int)
    kind = (request.form.get('kind') or '').strip() or 'sheet'
    name = (request.form.get('name') or '').strip() or ('Untitled Spreadsheet' if kind == 'sheet' else 'Untitled Document')
    content = request.form.get('content') or ''
    project_id = request.form.get('project_id', type=int) or get_current_project_id()
    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    blob = request.files.get('file')

    if doc_id:
        doc = Document.query.get_or_404(doc_id)
        project_id = doc.project_id
    else:
        if not project_id:
            return jsonify({'error': 'No active project. Select a project first.'}), 400
        ensure_system_folders(db, DocumentFolder, int(project_id), current_user.id, Document=Document)
        folder_id = request.form.get('folder_id', type=int)
        if not folder_id:
            mine = resolve_folder_by_key(db, DocumentFolder, int(project_id), 'my-files')
            folder_id = mine.id if mine else None
        default_ext = 'xlsx' if kind == 'sheet' else 'docx'
        doc = Document(
            project_id=int(project_id),
            folder_id=folder_id,
            name=name,
            document_type='Spreadsheet' if kind == 'sheet' else 'Document',
            filename='pending',
            original_filename=f'{name}.{default_ext}',
            mime_type=guess_mime(f'x.{default_ext}'),
            uploaded_by_id=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            editor_kind=kind,
        )
        db.session.add(doc)
        db.session.flush()

    doc.name = name
    doc.editor_kind = kind
    doc.editor_content = content
    doc.updated_at = datetime.utcnow()

    directory = document_folder(upload_root, int(project_id))
    os.makedirs(directory, exist_ok=True)

    if blob and blob.filename:
        ext = blob.filename.rsplit('.', 1)[-1].lower() if '.' in blob.filename else ('xlsx' if kind == 'sheet' else 'docx')
        file_bytes = blob.read()
        stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        stored = f'{stamp}_{secure_filename(name)[:80] or "document"}.{ext}'
        with open(os.path.join(directory, stored), 'wb') as fh:
            fh.write(file_bytes)
        # Remove previous stored file if it was a real file (not the placeholder).
        if doc.filename and doc.filename != 'pending' and doc.filename != stored:
            old = os.path.join(directory, doc.filename)
            if os.path.isfile(old):
                try:
                    os.remove(old)
                except OSError:
                    pass
        doc.filename = stored
        doc.original_filename = f'{name}.{ext}'
        doc.file_size = len(file_bytes)
        doc.mime_type = guess_mime(f'x.{ext}')
        doc.content_hash = file_content_hash(file_bytes)
    elif doc.filename == 'pending':
        # No blob provided on create — persist the editor content itself as the file.
        ext = 'json' if kind == 'sheet' else 'html'
        raw = content.encode('utf-8')
        stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        stored = f'{stamp}_{secure_filename(name)[:80] or "document"}.{ext}'
        with open(os.path.join(directory, stored), 'wb') as fh:
            fh.write(raw)
        doc.filename = stored
        doc.file_size = len(raw)
        doc.mime_type = guess_mime(f'x.{ext}')

    db.session.commit()
    return jsonify({
        'ok': True,
        'id': doc.id,
        'name': doc.name,
        'editor_kind': doc.editor_kind,
        'download_url': url_for('api_documents_download', doc_id=doc.id),
    })


@app.route('/share/<token>')
def public_share_page(token):
    from document_persistence import document_to_dict, format_file_size, share_link_is_valid

    link = DocumentShareLink.query.filter_by(token=token).first_or_404()
    doc = Document.query.get_or_404(link.document_id)
    if not share_link_is_valid(link):
        err = 'This link has been revoked.' if link.revoked_at else 'This link has expired or reached its download limit.'
        return render_template('share_download.html', error=err, doc=None, link=None, needs_password=False), 410
    needs_password = bool(link.password_hash) and not _share_is_unlocked(link)
    if needs_password:
        return render_template('share_download.html', error=None, doc=None, link={'token': token}, needs_password=True)
    return render_template(
        'share_download.html',
        error=None,
        doc=document_to_dict(doc),
        link={
            'token': link.token,
            'download_url': url_for('public_share_download', token=token),
            'expires_at': link.expires_at.isoformat() if link.expires_at else None,
            'size': format_file_size(doc.file_size),
        },
        needs_password=False,
    )


@app.route('/share/<token>/unlock', methods=['POST'])
def public_share_unlock(token):
    link = DocumentShareLink.query.filter_by(token=token).first_or_404()
    body = request.get_json(silent=True) or {}
    password = body.get('password') or request.form.get('password')
    if _unlock_share(link, password):
        return jsonify({'ok': True})
    return jsonify({'error': 'Incorrect password'}), 403


@app.route('/share/folder/<token>')
def public_folder_share_page(token):
    from document_persistence import share_link_is_valid

    link = DocumentFolderShareLink.query.filter_by(token=token).first_or_404()
    if not share_link_is_valid(link):
        err = 'This link has been revoked.' if link.revoked_at else 'This link has expired or reached its limit.'
        return render_template('share_folder.html', error=err, token=None), 410
    needs_password = bool(link.password_hash) and not _share_is_unlocked(link)
    folder = DocumentFolder.query.get_or_404(link.folder_id)
    return render_template(
        'share_folder.html',
        error=None,
        token=token,
        needs_password=needs_password,
        folder_name=folder.name,
        allow_upload=bool(link.allow_upload),
    )


@app.route('/share/folder/<token>/unlock', methods=['POST'])
def public_folder_share_unlock(token):
    link = DocumentFolderShareLink.query.filter_by(token=token).first_or_404()
    body = request.get_json(silent=True) or {}
    password = body.get('password') or request.form.get('password')
    if _unlock_share(link, password):
        return jsonify({'ok': True})
    return jsonify({'error': 'Incorrect password'}), 403


@app.route('/share/<token>/download')
def public_share_download(token):
    from document_persistence import share_link_is_valid

    link = DocumentShareLink.query.filter_by(token=token).first_or_404()
    if not share_link_is_valid(link):
        return jsonify({'error': 'Link unavailable'}), 410
    if link.password_hash and not _share_is_unlocked(link):
        return jsonify({'error': 'Password required'}), 403
    if not link.allow_download:
        return jsonify({'error': 'Download disabled'}), 403
    doc = Document.query.get_or_404(link.document_id)
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id))
    path = os.path.join(directory, doc.filename)
    if not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404
    link.download_count = (link.download_count or 0) + 1
    db.session.commit()
    return send_from_directory(
        directory,
        doc.filename,
        as_attachment=True,
        download_name=doc.original_filename or doc.name,
    )


def _documents_base_url():
    return request.url_root.rstrip('/')


def _user_display_name(user_id):
    if not user_id:
        return None
    user = User.query.get(user_id)
    if not user:
        return None
    name = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    return name or user.email


def _document_dict_with_user(doc, actor_id=None):
    from document_persistence import document_to_dict

    project = Project.query.get(doc.project_id)
    folder = DocumentFolder.query.get(doc.folder_id) if doc.folder_id else None
    return document_to_dict(
        doc,
        project.name if project else None,
        folder.name if folder else None,
        _user_display_name(doc.uploaded_by_id),
        checkout=_document_checkout_fields(doc, actor_id=actor_id),
    )


def _document_checkout_fields(doc, actor_id=None):
    uid = _acting_user_id(actor_id)
    role = ''
    if uid:
        user = User.query.get(uid)
        role = getattr(user, 'role', '') if user else ''
    co_id = getattr(doc, 'checked_out_by_id', None)
    folder = DocumentFolder.query.get(doc.folder_id) if doc.folder_id else None
    can_manage = role == 'Admin'
    if not can_manage and folder and uid:
        if getattr(folder, 'is_system', False):
            can_manage = False
        elif folder.created_by_id == uid:
            can_manage = True
    is_system = bool(doc.is_system_locked)
    return {
        'checked_out_by_id': co_id,
        'checked_out_by_name': _user_display_name(co_id) if co_id else None,
        'checked_out_at': doc.checked_out_at.isoformat() if getattr(doc, 'checked_out_at', None) else None,
        'checkout_note': getattr(doc, 'checkout_note', None),
        'is_checked_out': bool(co_id),
        'is_checked_out_by_me': bool(co_id and uid and co_id == uid),
        'is_edit_locked': bool(co_id and uid and co_id != uid),
        'can_check_out': not is_system and not co_id,
        'can_check_in': bool(co_id and uid and co_id == uid),
        'can_force_unlock': bool(co_id and can_manage),
    }


def _document_edit_lock_error(doc):
    """Return (response, status_code) if edits are blocked by checkout, else None."""
    if doc.is_system_locked:
        return None
    co_id = getattr(doc, 'checked_out_by_id', None)
    if co_id and co_id != current_user.id:
        name = _user_display_name(co_id)
        return jsonify({
            'error': f'This file is checked out by {name}. They must check it in before you can edit it.',
            'checked_out_by_id': co_id,
            'checked_out_by_name': name,
        }), 423
    return None


def _log_doc_activity(project_id, action, document_id=None, folder_id=None, detail=None, actor_id=None):
    try:
        act = DocumentActivity(
            project_id=int(project_id),
            document_id=document_id,
            folder_id=folder_id,
            user_id=_acting_user_id(actor_id),
            action=action,
            detail_json=json.dumps(detail or {}),
            created_at=datetime.utcnow(),
        )
        db.session.add(act)
    except Exception:
        pass


def _share_session_key(token):
    return f'share_unlocked_{token}'


def _share_is_unlocked(link):
    if not getattr(link, 'password_hash', None):
        return True
    return bool(session.get(_share_session_key(link.token)))


def _unlock_share(link, password):
    from document_persistence import verify_share_password
    if verify_share_password(getattr(link, 'password_hash', None), password):
        session[_share_session_key(link.token)] = True
        return True
    return False


def _active_documents():
    return Document.query.filter(Document.deleted_at.is_(None))


def _active_folders():
    return DocumentFolder.query.filter(DocumentFolder.deleted_at.is_(None))


def _folder_access(folder, required='view'):
    """Check folder permission. No rows = open to all project users; Admin/PM always allowed."""
    if not folder or not current_user.is_authenticated:
        return False
    role = (getattr(current_user, 'role', '') or '').strip()
    if role in ('Admin', 'Project Manager'):
        return True
    if folder.created_by_id == current_user.id:
        return True
    # Locked system folders stay available to all project users (permissions apply to custom folders only).
    if getattr(folder, 'is_system', False):
        if required == 'manage':
            return role == 'Admin'
        return True
    perms = DocumentFolderPermission.query.filter_by(folder_id=folder.id).all()
    if not perms:
        return True
    user_perm = DocumentFolderPermission.query.filter_by(
        folder_id=folder.id, user_id=current_user.id,
    ).first()
    if not user_perm:
        return False
    if required == 'manage':
        return bool(user_perm.can_manage)
    if required == 'upload':
        return bool(user_perm.can_upload or user_perm.can_manage)
    return bool(user_perm.can_view or user_perm.can_upload or user_perm.can_manage)


def _archive_document_version(doc, notes=None):
    from document_persistence import version_storage_path
    import shutil

    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    src_dir = os.path.join(upload_root, 'documents', str(doc.project_id))
    src_path = os.path.join(src_dir, doc.filename)
    if not os.path.isfile(src_path):
        return
    ver_no = doc.version_count or 1
    ver_dir = version_storage_path(upload_root, doc.project_id, doc.id)
    archived_name = f'v{ver_no}_{doc.filename}'
    dst_path = os.path.join(ver_dir, archived_name)
    shutil.copy2(src_path, dst_path)
    ver = DocumentVersion(
        document_id=doc.id,
        version_no=ver_no,
        filename=archived_name,
        original_filename=doc.original_filename,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        uploaded_by_id=doc.uploaded_by_id,
        notes=notes,
        created_at=datetime.utcnow(),
    )
    db.session.add(ver)
    doc.version_count = ver_no + 1


def _mirror_to_system_folder(
    project_id,
    file_bytes,
    name,
    original_filename,
    system_folder_key,
    document_type='Other',
    source_metadata=None,
):
    from document_persistence import ensure_system_folders, resolve_folder_by_key

    ensure_system_folders(db, DocumentFolder, int(project_id), current_user.id if current_user.is_authenticated else None, Document=Document)
    folder = resolve_folder_by_key(db, DocumentFolder, int(project_id), system_folder_key)
    if not folder:
        return None
    meta = {**(source_metadata or {}), 'mirrored_from_module': True, 'system_folder_key': system_folder_key}
    try:
        from document_integration import guess_mime
        return _save_document_bytes(
            int(project_id), file_bytes, name, original_filename,
            guess_mime(original_filename), document_type, folder.id, False,
            None, None, meta,
        )
    except ValueError:
        return None


def _mirror_to_system_subfolder(
    project_id,
    file_bytes,
    name,
    original_filename,
    system_folder_key,
    subfolder_name,
    document_type='Other',
    source_metadata=None,
    is_system_locked=True,
    uploaded_by_id=None,
):
    """Mirror a file into Documents › <system folder> › <subfolder>, locked by default.

    Used so module attachments (daily log photos, RFI files, etc.) always land in a
    predictable, browsable, non-deletable location instead of a hidden upload path.
    """
    from document_persistence import (
        ensure_system_folders, resolve_folder_by_key, get_or_create_child_folder,
    )

    actor = _acting_user_id(uploaded_by_id)
    ensure_system_folders(db, DocumentFolder, int(project_id), actor, Document=Document)
    parent = resolve_folder_by_key(db, DocumentFolder, int(project_id), system_folder_key)
    if not parent:
        return None
    sub = get_or_create_child_folder(
        db, DocumentFolder, int(project_id), parent.id, subfolder_name, actor,
    )
    db.session.commit()
    meta = {
        **(source_metadata or {}),
        'mirrored_from_module': True,
        'system_folder_key': system_folder_key,
        'subfolder': subfolder_name,
    }
    try:
        from document_integration import guess_mime
        return _save_document_bytes(
            int(project_id), file_bytes, name, original_filename,
            guess_mime(original_filename), document_type, sub.id, bool(is_system_locked),
            None, None, meta, uploaded_by_id=actor,
        )
    except ValueError:
        return None


def _notify_documents_team(project_id, title, message, link=None):
    from document_integration import notify_documents_team
    notify_documents_team(db, User, int(project_id), title=title, message=message, link=link)


def _slim_documents_archive(docs_info):
    """Keep upload job payloads small and JSON-safe."""
    if not docs_info:
        return None
    return {
        'folder_id': docs_info.get('folder_id'),
        'folder_name': docs_info.get('folder_name'),
        'documents_url': docs_info.get('documents_url'),
        'document_count': len(docs_info.get('documents') or []),
        'skipped_individual_sheets': docs_info.get('skipped_individual_sheets', 0),
        'archive_error': docs_info.get('archive_error'),
    }


def _archive_drawing_set_to_documents(project_id, set_name, source_pdf_path, created, uploaded_by_id):
    """Save uploaded drawing set PDFs into Documents › Drawings › Drawing Sets › {set_name}/."""
    from document_persistence import ensure_document_schema, resolve_folder_by_key, get_or_create_child_folder, ensure_system_folders
    from drawing_persistence import resolve_drawing_file_path, current_revision_for_drawing

    if not created or not (set_name or '').strip():
        return None

    ensure_project_schema()
    ensure_document_schema(db.engine, db)
    ensure_system_folders(db, DocumentFolder, int(project_id), uploaded_by_id, Document=Document)
    parent = resolve_folder_by_key(db, DocumentFolder, int(project_id), 'drawing-sets')
    if not parent:
        return None

    set_folder = get_or_create_child_folder(
        db, DocumentFolder, int(project_id), parent.id, set_name.strip(), uploaded_by_id,
    )
    upload_root = app.config.get('UPLOAD_FOLDER')
    saved = {
        'folder_id': set_folder.id,
        'folder_name': set_folder.name,
        'documents_url': f'/documents?project_id={project_id}&folder_id={set_folder.id}',
        'documents': [],
        'full_set': None,
        'skipped_individual_sheets': 0,
    }
    stamp = datetime.utcnow().strftime('%Y-%m-%d')
    mirror_individual = len(created) <= 20

    if source_pdf_path and os.path.isfile(source_pdf_path):
        with open(source_pdf_path, 'rb') as fh:
            full_bytes = fh.read()
        full_name = f'{set_name.strip()} — Full Set ({stamp}).pdf'
        try:
            doc = _save_document_bytes(
                int(project_id), full_bytes, full_name, os.path.basename(source_pdf_path),
                'application/pdf', 'Drawing', set_folder.id, False,
                None, None,
                {
                    'set_name': set_name,
                    'mirrored_from_module': True,
                    'source': 'drawing_set_upload',
                    'is_full_set': True,
                },
                uploaded_by_id=uploaded_by_id,
            )
            saved['full_set'] = doc
            saved['documents'].append(doc)
        except (ValueError, OSError) as exc:
            saved['archive_error'] = f'Could not save full set PDF to Documents: {exc}'

    if mirror_individual:
        for item in created:
            drawing = Drawing.query.get(item['id'])
            if not drawing:
                continue
            rev = current_revision_for_drawing(DrawingRevision, drawing)
            path = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
            if not path or not os.path.isfile(path):
                saved['skipped_individual_sheets'] += 1
                continue
            with open(path, 'rb') as fh:
                sheet_bytes = fh.read()
            sheet_label = f'{drawing.sheet_number or "Sheet"} — {drawing.title or set_name}'.strip(' —')
            try:
                doc = _save_document_bytes(
                    int(project_id), sheet_bytes, sheet_label, os.path.basename(path),
                    'application/pdf', 'Drawing', set_folder.id, False,
                    drawing.id, drawing.sheet_number,
                    {
                        'set_name': set_name,
                        'mirrored_from_module': True,
                        'source': 'drawing_set_upload',
                        'revision_label': item.get('revision_label'),
                    },
                    uploaded_by_id=uploaded_by_id,
                )
                saved['documents'].append(doc)
            except (ValueError, OSError):
                saved['skipped_individual_sheets'] += 1
                continue
    elif len(created) > 20:
        saved['skipped_individual_sheets'] = len(created)

    if saved['documents']:
        try:
            _notify_documents_team(
                int(project_id),
                'Drawing set saved to Documents',
                f'"{set_name}" ({len(saved["documents"])} file(s)) is in Documents › Drawings › Drawing Sets › {set_name}.',
                saved['documents_url'],
            )
        except Exception:
            db.session.rollback()
    return saved


def _ensure_module_attachment_columns():
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    migrations = [
        ('submittal', 'attachments_json', 'TEXT'),
        ('daily_log', 'attachments_json', 'TEXT'),
        ('daily_log', 'details_json', 'TEXT'),
        ('daily_log', 'status', 'VARCHAR(30)'),
        ('weekly_report', 'period_start', 'DATE'),
        ('weekly_report', 'period_end', 'DATE'),
        ('weekly_report', 'period_type', 'VARCHAR(20)'),
        ('weekly_report', 'details_json', 'TEXT'),
        ('weekly_report', 'notes', 'TEXT'),
        ('punch_item', 'category', 'VARCHAR(80)'),
        ('punch_item', 'assigned_company', 'VARCHAR(150)'),
        ('punch_item', 'completed_at', 'DATETIME'),
        ('punch_item', 'completed_by_id', 'INTEGER'),
        ('punch_item', 'updated_at', 'DATETIME'),
        ('punch_item', 'details_json', 'TEXT'),
        ('punch_item', 'attachments_json', 'TEXT'),
    ]
    for table, column, typedef in migrations:
        if table not in tables:
            continue
        cols = {c['name'] for c in insp.get_columns(table)}
        if column not in cols:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {typedef}'))
    db.session.commit()


def _save_document_bytes(
    project_id: int,
    file_bytes: bytes,
    name: str,
    original_filename: str,
    mime_type: str,
    document_type: str = 'Other',
    folder_id: int | None = None,
    is_system_locked: bool = False,
    source_drawing_id=None,
    source_sheet=None,
    source_metadata=None,
    tags=None,
    custom_metadata=None,
    uploaded_by_id=None,
):
    from document_features import file_content_hash, project_document_settings, retention_until_from_years, parse_tags
    from document_persistence import document_folder, ensure_system_folders, resolve_folder_by_key

    ensure_project_schema()
    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    actor_id = _acting_user_id(uploaded_by_id)
    ensure_system_folders(db, DocumentFolder, project_id, actor_id, Document=Document)
    if not folder_id:
        default_folder = resolve_folder_by_key(db, DocumentFolder, project_id, 'my-files')
        folder_id = default_folder.id if default_folder else None

    ext = original_filename.rsplit('.', 1)[-1].lower() if original_filename and '.' in original_filename else 'bin'
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f'File type .{ext} not allowed')

    stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    stored_name = f'{stamp}_{secure_filename(name).replace(" ", "_")[:80]}.{ext}'
    folder_path = document_folder(upload_root, int(project_id))
    file_path = os.path.join(folder_path, stored_name)
    with open(file_path, 'wb') as fh:
        fh.write(file_bytes)

    project = Project.query.get(int(project_id))
    settings = project_document_settings(project) if project else {}
    content_hash = file_content_hash(file_bytes)
    tag_list = parse_tags(tags) if tags is not None else []

    doc = Document(
        project_id=int(project_id),
        folder_id=int(folder_id) if folder_id else None,
        name=name,
        document_type=document_type or 'Other',
        filename=stored_name,
        original_filename=original_filename,
        file_size=len(file_bytes),
        mime_type=mime_type,
        is_system_locked=bool(is_system_locked),
        source_drawing_id=int(source_drawing_id) if source_drawing_id else None,
        source_sheet=source_sheet,
        source_metadata_json=json.dumps(source_metadata) if source_metadata else None,
        uploaded_by_id=actor_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        content_hash=content_hash,
        tags_json=json.dumps(tag_list) if tag_list else None,
        custom_metadata_json=json.dumps(custom_metadata) if custom_metadata else None,
        retention_until=retention_until_from_years(settings.get('retention_years', 7)),
    )
    db.session.add(doc)
    db.session.commit()
    _log_doc_activity(project_id, 'upload', document_id=doc.id, folder_id=doc.folder_id, detail={'name': doc.name}, actor_id=actor_id)
    db.session.commit()
    return _document_dict_with_user(doc, actor_id=actor_id)


def _find_duplicate_document(project_id: int, content_hash: str, exclude_id: int | None = None):
    if not content_hash:
        return None
    q = _active_documents().filter_by(project_id=int(project_id), content_hash=content_hash)
    if exclude_id:
        q = q.filter(Document.id != int(exclude_id))
    return q.first()


@app.route('/api/document-folders', methods=['GET'])
@login_required
def api_document_folders_list():
    from document_persistence import ensure_system_folders, folder_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    parent_id = request.args.get('parent_id')
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    q = DocumentFolder.query.filter_by(project_id=int(project_id))
    if parent_id == 'null' or parent_id == '':
        q = q.filter(DocumentFolder.parent_id.is_(None))
    elif parent_id is not None:
        q = q.filter_by(parent_id=int(parent_id))
    folders = q.order_by(DocumentFolder.is_system.desc(), DocumentFolder.name).all()
    out = []
    for f in folders:
        child_count = DocumentFolder.query.filter_by(parent_id=f.id).count()
        file_count = Document.query.filter_by(folder_id=f.id).count()
        out.append(folder_to_dict(f, child_count, file_count))
    return jsonify({'ok': True, 'folders': out})


@app.route('/api/document-folders/tree', methods=['GET'])
@login_required
def api_document_folders_tree():
    from document_persistence import ensure_system_folders, folder_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    all_folders = _active_folders().filter_by(project_id=int(project_id)).order_by(
        DocumentFolder.is_system.desc(), DocumentFolder.name,
    ).all()
    by_parent: dict = {}
    for f in all_folders:
        by_parent.setdefault(f.parent_id, []).append(f)

    def build_node(folder):
        children = [build_node(c) for c in by_parent.get(folder.id, [])]
        file_count = _active_documents().filter_by(folder_id=folder.id).count()
        node = folder_to_dict(folder, len(children), file_count)
        node['children'] = children
        return node

    roots = [build_node(f) for f in by_parent.get(None, [])]
    return jsonify({'ok': True, 'tree': roots})


@app.route('/api/document-folders', methods=['POST'])
@login_required
def api_document_folders_create():
    from document_persistence import ensure_system_folders, folder_to_dict

    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    name = (body.get('name') or '').strip()
    parent_id = body.get('parent_id')
    if not project_id or not name:
        return jsonify({'error': 'project_id and name required'}), 400
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    if parent_id:
        parent = DocumentFolder.query.get(int(parent_id))
        if not parent or parent.project_id != int(project_id):
            return jsonify({'error': 'Parent folder not found'}), 404
    folder = DocumentFolder(
        project_id=int(project_id),
        parent_id=int(parent_id) if parent_id else None,
        name=name,
        is_system=False,
        created_by_id=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.session.add(folder)
    db.session.commit()
    return jsonify({'ok': True, 'folder': folder_to_dict(folder)}), 201


@app.route('/api/document-folders/<int:folder_id>', methods=['PATCH'])
@login_required
def api_document_folders_patch(folder_id):
    from document_persistence import folder_is_descendant, folder_to_dict

    folder = DocumentFolder.query.get_or_404(folder_id)
    if folder.is_system:
        return jsonify({'error': 'System folders cannot be modified'}), 403
    body = request.get_json(silent=True) or {}
    if 'name' in body and body['name']:
        folder.name = str(body['name']).strip()[:200]
    if 'parent_id' in body:
        new_parent = body['parent_id']
        if new_parent:
            parent = DocumentFolder.query.get(int(new_parent))
            if not parent or parent.project_id != folder.project_id:
                return jsonify({'error': 'Invalid parent folder'}), 400
            if folder_is_descendant(db, DocumentFolder, int(new_parent), folder.id):
                return jsonify({'error': 'Cannot move folder into itself'}), 400
            folder.parent_id = int(new_parent)
        else:
            folder.parent_id = None
    db.session.commit()
    return jsonify({'ok': True, 'folder': folder_to_dict(folder)})


@app.route('/api/document-folders/<int:folder_id>', methods=['DELETE'])
@login_required
def api_document_folders_delete(folder_id):
    folder = DocumentFolder.query.get_or_404(folder_id)
    if folder.is_system:
        return jsonify({'error': 'System folders cannot be deleted'}), 403
    if _active_folders().filter_by(parent_id=folder.id).count():
        return jsonify({'error': 'Folder is not empty (contains subfolders)'}), 400
    if _active_documents().filter_by(folder_id=folder.id).count():
        return jsonify({'error': 'Folder is not empty (contains files)'}), 400
    folder.deleted_at = datetime.utcnow()
    _log_doc_activity(folder.project_id, 'delete', folder_id=folder.id, detail={'name': folder.name})
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/documents/browse', methods=['GET'])
@login_required
def api_documents_browse():
    from document_persistence import document_to_dict, ensure_system_folders, folder_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    folder_id = request.args.get('folder_id')
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    project = Project.query.get(int(project_id))

    fq = _active_folders().filter_by(project_id=int(project_id))
    if folder_id in (None, '', 'null'):
        fq = fq.filter(DocumentFolder.parent_id.is_(None))
        current_folder = None
    else:
        current_folder = _active_folders().filter_by(id=int(folder_id)).first()
        if not current_folder or current_folder.project_id != int(project_id):
            return jsonify({'error': 'Folder not found'}), 404
        if not _folder_access(current_folder, 'view'):
            return jsonify({'error': 'No access to this folder'}), 403
        fq = fq.filter_by(parent_id=current_folder.id)

    folders = fq.order_by(DocumentFolder.is_system.desc(), DocumentFolder.name).all()
    folder_nodes = []
    for f in folders:
        if not _folder_access(f, 'view'):
            continue
        child_count = _active_folders().filter_by(parent_id=f.id).count()
        file_count = _active_documents().filter_by(folder_id=f.id).count()
        folder_nodes.append(folder_to_dict(f, child_count, file_count))

    dq = _active_documents().filter_by(project_id=int(project_id))
    if folder_id in (None, '', 'null'):
        dq = dq.filter(Document.folder_id.is_(None))
    else:
        dq = dq.filter_by(folder_id=int(folder_id))
    docs = dq.order_by(Document.name).all()

    breadcrumbs = []
    if current_folder:
        chain = [current_folder]
        parent = DocumentFolder.query.get(current_folder.parent_id) if current_folder.parent_id else None
        while parent:
            chain.insert(0, parent)
            parent = DocumentFolder.query.get(parent.parent_id) if parent.parent_id else None
        breadcrumbs = [{'id': f.id, 'name': f.name, 'is_system': f.is_system} for f in chain]

    return jsonify({
        'ok': True,
        'project_id': int(project_id),
        'project_name': project.name if project else None,
        'folder_id': current_folder.id if current_folder else None,
        'breadcrumbs': breadcrumbs,
        'folders': folder_nodes,
        'files': [_document_dict_with_user(d) for d in docs],
    })


@app.route('/api/documents/<int:doc_id>', methods=['GET'])
@login_required
def api_documents_get(doc_id):
    doc = Document.query.get_or_404(doc_id)
    payload = {'ok': True, 'document': _document_dict_with_user(doc)}
    if request.args.get('markups'):
        from document_persistence import document_markup_to_dict
        markups = DocumentMarkup.query.filter_by(document_id=doc.id).all()
        payload['markups'] = [document_markup_to_dict(m) for m in markups]
    return jsonify(payload)


@app.route('/api/documents/<int:doc_id>/markups', methods=['GET', 'POST'])
@login_required
def api_document_markups(doc_id):
    from document_persistence import document_markup_to_dict

    doc = Document.query.get_or_404(doc_id)
    lock = _document_edit_lock_error(doc)
    if lock and request.method == 'POST':
        return lock
    if request.method == 'GET':
        rows = DocumentMarkup.query.filter_by(document_id=doc.id).all()
        return jsonify({'markups': [document_markup_to_dict(m) for m in rows]})

    body = request.get_json(silent=True) or {}
    user_name = f'{current_user.first_name} {current_user.last_name}'.strip() or current_user.email
    markup = DocumentMarkup(
        document_id=doc.id,
        user_id=current_user.id,
        user_name=user_name,
        layer=body.get('layer') or 'personal',
        markup_type=body.get('markup_type') or 'line',
        geometry_json=json.dumps(body.get('geometry') or {}),
        style_json=json.dumps(body.get('style') or {}),
        label=body.get('label'),
        measurement_value=body.get('measurement_value'),
        measurement_unit=body.get('measurement_unit'),
    )
    if body.get('publish'):
        markup.layer = 'published'
        markup.published_at = datetime.utcnow()
    db.session.add(markup)
    db.session.commit()
    return jsonify({'ok': True, 'markup': document_markup_to_dict(markup)})


@app.route('/api/documents/markups/<int:markup_id>', methods=['PUT', 'DELETE'])
@login_required
def api_document_markup_item(markup_id):
    from document_persistence import document_markup_to_dict

    markup = DocumentMarkup.query.get_or_404(markup_id)
    doc = Document.query.get_or_404(markup.document_id)
    lock = _document_edit_lock_error(doc)
    if lock:
        return lock
    if request.method == 'DELETE':
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
    return jsonify({'ok': True, 'markup': document_markup_to_dict(markup)})


@app.route('/api/documents', methods=['GET'])
@login_required
def api_documents_list():
    from document_persistence import document_to_dict, ensure_system_folders

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    folder_id = request.args.get('folder_id')
    if project_id:
        ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    q = Document.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    if folder_id:
        q = q.filter_by(folder_id=int(folder_id))
    docs = q.order_by(Document.created_at.desc()).limit(1000).all()
    return jsonify({
        'ok': True,
        'documents': [_document_dict_with_user(d) for d in docs],
    })


def _infer_data_url_upload(raw_input, mime_type=None, filename=None):
    """Infer MIME type and stored filename for base64 / data-URL uploads."""
    data_url = str(raw_input or '')
    if data_url.startswith('data:'):
        header = data_url.split(',', 1)[0].lower()
        if 'image/png' in header:
            return 'image/png', secure_filename(filename or 'upload.png')
        if 'image/jpeg' in header or 'image/jpg' in header:
            return 'image/jpeg', secure_filename(filename or 'upload.jpg')
        if 'image/webp' in header:
            return 'image/webp', secure_filename(filename or 'upload.webp')
        if 'application/pdf' in header:
            return 'application/pdf', secure_filename(filename or 'upload.pdf')
    mime_ext = {
        'image/png': 'png',
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/webp': 'webp',
        'application/pdf': 'pdf',
    }
    mt = (mime_type or '').lower()
    if mt in mime_ext:
        base = (filename or 'upload').rsplit('.', 1)[0]
        return mt, secure_filename(f'{base}.{mime_ext[mt]}')
    return 'image/png', secure_filename(filename or 'upload.png')


@app.route('/api/documents', methods=['POST'])
@login_required
def api_documents_create():
    import base64 as b64mod
    from document_persistence import resolve_folder_by_key

    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    project_id = None
    name = None
    document_type = 'Other'
    folder_id = None
    source_drawing_id = None
    source_sheet = None
    source_metadata = {}
    file_bytes = None
    original_filename = None
    mime_type = 'application/octet-stream'
    is_system_locked = False
    create_share_link = False

    if request.content_type and 'multipart/form-data' in request.content_type:
        project_id = request.form.get('project_id', type=int) or get_current_project_id()
        name = (request.form.get('name') or '').strip()
        document_type = (request.form.get('document_type') or request.form.get('type') or 'Other').strip()
        folder_id = request.form.get('folder_id', type=int)
        source_drawing_id = request.form.get('source_drawing_id', type=int)
        source_sheet = (request.form.get('source_sheet') or '').strip() or None
        create_share_link = request.form.get('create_share_link') in ('1', 'true', 'yes')
        up = request.files.get('file')
        if not up or not up.filename:
            return jsonify({'error': 'File is required'}), 400
        file_bytes = up.read()
        original_filename = secure_filename(up.filename)
        mime_type = up.mimetype or mime_type
        if not name:
            name = original_filename
    else:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        name = (body.get('name') or '').strip()
        document_type = (body.get('document_type') or body.get('type') or 'Drawing').strip()
        folder_id = body.get('folder_id')
        source_drawing_id = body.get('source_drawing_id')
        source_sheet = (body.get('source_sheet') or '').strip() or None
        source_metadata = body.get('source_metadata') or {}
        is_system_locked = bool(body.get('is_system_locked'))
        create_share_link = bool(body.get('create_share_link'))
        system_folder_key = body.get('system_folder_key')
        if system_folder_key and project_id:
            sf = resolve_folder_by_key(db, DocumentFolder, int(project_id), system_folder_key)
            if sf:
                folder_id = sf.id
                is_system_locked = is_system_locked or system_folder_key == 'printed-output'
        image_data = body.get('image_data') or body.get('template')
        file_b64 = body.get('file_base64')
        if image_data or file_b64:
            raw = image_data or file_b64
            if ',' in str(raw):
                raw = str(raw).split(',', 1)[1]
            try:
                file_bytes = b64mod.b64decode(raw)
            except Exception:
                return jsonify({'error': 'Invalid file data'}), 400
            mime_type, original_filename = _infer_data_url_upload(
                image_data or file_b64,
                body.get('mime_type'),
                body.get('filename') or (f'{name}.png' if name else None),
            )
            if body.get('save_as_pdf'):
                from document_features import image_bytes_to_pdf
                file_bytes = image_bytes_to_pdf(file_bytes)
                mime_type = 'application/pdf'
                base = (name or 'snip').rsplit('.', 1)[0]
                original_filename = secure_filename(f'{base}.pdf')
        else:
            return jsonify({'error': 'file or image_data required'}), 400

    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not Project.query.get(int(project_id)):
        return jsonify({'error': 'Project not found'}), 404
    if not file_bytes:
        return jsonify({'error': 'Empty file'}), 400

    from document_features import file_content_hash
    dup = _find_duplicate_document(int(project_id), file_content_hash(file_bytes))
    duplicate_warning = None
    if dup:
        duplicate_warning = {
            'id': dup.id,
            'name': dup.name,
            'folder_id': dup.folder_id,
            'message': f'A file with identical content already exists: "{dup.name}"',
        }

    tags = request.form.get('tags') if (request.content_type and 'multipart/form-data' in request.content_type) else (request.get_json(silent=True) or {}).get('tags')
    custom_metadata = None if (request.content_type and 'multipart/form-data' in request.content_type) else (request.get_json(silent=True) or {}).get('custom_metadata')

    try:
        doc_dict = _save_document_bytes(
            int(project_id), file_bytes, name or 'Document', original_filename or 'file.bin',
            mime_type, document_type, folder_id, is_system_locked,
            source_drawing_id, source_sheet, source_metadata,
            tags=tags,
            custom_metadata=custom_metadata,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    share = None
    if create_share_link:
        share = _create_document_share_link(doc_dict['id'])

    meta = source_metadata if isinstance(source_metadata, dict) else {}
    if not meta.get('mirrored_from_module') and not meta.get('shared_upload'):
        uploader = _user_display_name(current_user.id) if current_user.is_authenticated else 'Someone'
        _notify_documents_team(
            int(project_id),
            'Document uploaded',
            f'{uploader} uploaded "{doc_dict.get("name")}" to Documents.',
            f'/documents?project_id={project_id}',
        )

    return jsonify({
        'ok': True,
        'document': doc_dict,
        'share_link': share,
        'duplicate_warning': duplicate_warning,
    }), 201


@app.route('/api/documents/printed-output', methods=['POST'])
@login_required
def api_documents_printed_output():
    """Save a print/PDF output into the locked Printed Output system folder."""
    import base64 as b64mod
    from document_persistence import resolve_folder_by_key

    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    name = (body.get('name') or 'Printed document').strip()
    pdf_data = body.get('pdf_base64') or body.get('file_base64')
    source_module = body.get('source_module') or 'unknown'
    if not project_id or not pdf_data:
        return jsonify({'error': 'project_id and pdf_base64 required'}), 400
    if ',' in pdf_data:
        pdf_data = pdf_data.split(',', 1)[1]
    try:
        file_bytes = b64mod.b64decode(pdf_data)
    except Exception:
        return jsonify({'error': 'Invalid PDF data'}), 400
    folder = resolve_folder_by_key(db, DocumentFolder, int(project_id), 'printed-output')
    if not folder:
        return jsonify({'error': 'Printed Output folder missing'}), 500
    try:
        doc_dict = _save_document_bytes(
            int(project_id), file_bytes, name, secure_filename(f'{name}.pdf'),
            'application/pdf', 'Printed', folder.id, True,
            source_metadata={'source_module': source_module, 'printed_at': datetime.utcnow().isoformat()},
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'document': doc_dict}), 201


def _create_document_share_link(document_id: int, days: int = 30, max_downloads: int | None = None, password: str | None = None):
    from document_features import clamp_share_expiry_days, project_document_settings
    from document_persistence import default_share_expiry, hash_share_password, new_share_token, share_link_to_dict

    doc = Document.query.get_or_404(document_id)
    project = Project.query.get(doc.project_id)
    settings = project_document_settings(project) if project else {}
    expiry_days = clamp_share_expiry_days(days, settings)
    needs_approval = bool(settings.get('share_requires_approval')) and getattr(current_user, 'role', '') not in ('Admin', 'Project Manager')
    approval_status = 'pending' if needs_approval else 'approved'
    link = DocumentShareLink(
        document_id=doc.id,
        token=new_share_token(),
        label=doc.name,
        password_hash=hash_share_password(password),
        expires_at=default_share_expiry(expiry_days),
        max_downloads=max_downloads,
        download_count=0,
        allow_download=True,
        created_by_id=current_user.id,
        created_at=datetime.utcnow(),
        approval_status=approval_status,
        approved_at=datetime.utcnow() if approval_status == 'approved' else None,
        approved_by_id=current_user.id if approval_status == 'approved' else None,
    )
    db.session.add(link)
    db.session.commit()
    _log_doc_activity(doc.project_id, 'share', document_id=doc.id, detail={'type': 'file_link', 'approval_status': approval_status})
    db.session.commit()
    share = share_link_to_dict(link, _documents_base_url())
    if approval_status == 'pending':
        _notify_documents_team(
            doc.project_id,
            'Share link pending approval',
            f'A share link for "{doc.name}" needs PM approval before it goes live.',
            '/documents',
        )
    else:
        _notify_documents_team(
            doc.project_id,
            'Document share link created',
            f'A download link was created for "{doc.name}". Expires in {expiry_days} days.',
            share.get('share_url'),
        )
    share['approval_status'] = approval_status
    share['expires_in_days'] = expiry_days
    return share


@app.route('/api/documents/<int:doc_id>', methods=['PATCH'])
@login_required
def api_documents_patch(doc_id):
    doc = Document.query.get_or_404(doc_id)
    lock_err = _document_edit_lock_error(doc)
    if lock_err:
        return lock_err
    body = request.get_json(silent=True) or {}
    if doc.is_system_locked:
        if 'name' in body and body.get('name') and body['name'] != doc.name:
            return jsonify({'error': 'Locked job files cannot be renamed'}), 403
        if 'folder_id' in body:
            new_fid = int(body['folder_id']) if body['folder_id'] else None
            if new_fid != doc.folder_id:
                return jsonify({'error': 'Locked job files cannot be moved'}), 403
    if 'name' in body and body['name']:
        doc.name = str(body['name']).strip()[:300]
    if 'folder_id' in body and not doc.is_system_locked:
        fid = body['folder_id']
        if fid:
            folder = DocumentFolder.query.get(int(fid))
            if not folder or folder.project_id != doc.project_id:
                return jsonify({'error': 'Invalid folder'}), 400
            doc.folder_id = folder.id
        else:
            doc.folder_id = None
    if 'tags' in body:
        from document_features import parse_tags
        doc.tags_json = json.dumps(parse_tags(body.get('tags')))
    if 'custom_metadata' in body and isinstance(body.get('custom_metadata'), dict):
        doc.custom_metadata_json = json.dumps(body['custom_metadata'])
    if 'legal_hold' in body and getattr(current_user, 'role', '') in ('Admin', 'Project Manager'):
        doc.legal_hold = bool(body.get('legal_hold'))
    doc.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)})


@app.route('/api/documents/<int:doc_id>/checkout', methods=['POST'])
@login_required
def api_documents_checkout(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.deleted_at:
        return jsonify({'error': 'Document is in recycle bin'}), 400
    if doc.is_system_locked:
        return jsonify({'error': 'System job files cannot be checked out'}), 403
    folder = DocumentFolder.query.get(doc.folder_id) if doc.folder_id else None
    if folder and not _folder_access(folder, 'upload'):
        return jsonify({'error': 'No upload permission for this folder'}), 403
    co_id = getattr(doc, 'checked_out_by_id', None)
    if co_id and co_id != current_user.id:
        return jsonify({
            'error': f'Already checked out by {_user_display_name(co_id)}',
            'checked_out_by_name': _user_display_name(co_id),
        }), 423
    body = request.get_json(silent=True) or {}
    note = (body.get('note') or '').strip()[:500] or None
    doc.checked_out_by_id = current_user.id
    doc.checked_out_at = datetime.utcnow()
    doc.checkout_note = note
    _log_doc_activity(doc.project_id, 'checkout', document_id=doc.id, folder_id=doc.folder_id, detail={'note': note})
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)})


@app.route('/api/documents/<int:doc_id>/checkin', methods=['POST'])
@login_required
def api_documents_checkin(doc_id):
    doc = Document.query.get_or_404(doc_id)
    co_id = getattr(doc, 'checked_out_by_id', None)
    if not co_id:
        return jsonify({'error': 'File is not checked out'}), 400
    if co_id != current_user.id:
        return jsonify({'error': 'Only the user who checked out this file can check it in'}), 403
    doc.checked_out_by_id = None
    doc.checked_out_at = None
    doc.checkout_note = None
    _log_doc_activity(doc.project_id, 'checkin', document_id=doc.id, folder_id=doc.folder_id, detail={'name': doc.name})
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)})


@app.route('/api/documents/<int:doc_id>/force-unlock', methods=['POST'])
@login_required
def api_documents_force_unlock(doc_id):
    doc = Document.query.get_or_404(doc_id)
    co_id = getattr(doc, 'checked_out_by_id', None)
    if not co_id:
        return jsonify({'error': 'File is not checked out'}), 400
    fields = _document_checkout_fields(doc)
    if not fields.get('can_force_unlock'):
        return jsonify({'error': 'Admin or folder manage permission required'}), 403
    prev_user = _user_display_name(co_id)
    doc.checked_out_by_id = None
    doc.checked_out_at = None
    doc.checkout_note = None
    _log_doc_activity(
        doc.project_id, 'force_unlock', document_id=doc.id, folder_id=doc.folder_id,
        detail={'previous_user': prev_user},
    )
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)})


@app.route('/api/documents/<int:doc_id>/download')
@login_required
def api_documents_download(doc_id):
    doc = Document.query.get_or_404(doc_id)
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id))
    if not os.path.isfile(os.path.join(directory, doc.filename)):
        return jsonify({'error': 'File not found'}), 404
    return send_from_directory(
        directory,
        doc.filename,
        as_attachment=True,
        download_name=doc.original_filename or doc.name,
    )


@app.route('/api/documents/<int:doc_id>/share-links', methods=['GET'])
@login_required
def api_document_share_links_list(doc_id):
    from document_persistence import share_link_to_dict

    Document.query.get_or_404(doc_id)
    links = DocumentShareLink.query.filter_by(document_id=doc_id).order_by(DocumentShareLink.created_at.desc()).all()
    base = _documents_base_url()
    return jsonify({'ok': True, 'links': [share_link_to_dict(l, base) for l in links]})


@app.route('/api/documents/<int:doc_id>/share-links', methods=['POST'])
@login_required
def api_document_share_links_create(doc_id):
    body = request.get_json(silent=True) or {}
    days = int(body.get('expires_days') or 30)
    max_dl = body.get('max_downloads')
    password = body.get('password')
    share = _create_document_share_link(
        doc_id, days=days, max_downloads=int(max_dl) if max_dl else None, password=password,
    )
    return jsonify({'ok': True, 'share_link': share}), 201


@app.route('/api/share-links/<int:link_id>', methods=['DELETE'])
@login_required
def api_share_links_revoke(link_id):
    link = DocumentShareLink.query.get_or_404(link_id)
    link.revoked_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def api_documents_delete(doc_id):
    doc = Document.query.get_or_404(doc_id)
    lock_err = _document_edit_lock_error(doc)
    if lock_err:
        return lock_err
    if doc.is_system_locked:
        return jsonify({'error': 'This file is locked (job/print output) and cannot be deleted'}), 403
    if doc.deleted_at:
        return jsonify({'ok': True})
    doc.deleted_at = datetime.utcnow()
    _log_doc_activity(doc.project_id, 'delete', document_id=doc.id, folder_id=doc.folder_id, detail={'name': doc.name})
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/uploads/documents/<int:project_id>/<path:filename>')
@login_required
def serve_document_file(project_id, filename):
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(project_id))
    if not os.path.isfile(os.path.join(directory, filename)):
        return 'Not found', 404
    return send_from_directory(directory, filename)


# ==================== DOCUMENTS — SEARCH, TRASH, VERSIONS, COMMENTS, FOLDER SHARES ====================

@app.route('/api/documents/search', methods=['GET'])
@login_required
def api_documents_search():
    from document_persistence import folder_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = (request.args.get('q') or '').strip()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not q:
        return jsonify({'ok': True, 'files': [], 'folders': []})
    like = f'%{q}%'
    files = _active_documents().filter(
        Document.project_id == int(project_id),
        Document.name.ilike(like),
    ).order_by(Document.name).limit(200).all()
    folders = _active_folders().filter(
        DocumentFolder.project_id == int(project_id),
        DocumentFolder.name.ilike(like),
    ).order_by(DocumentFolder.name).limit(100).all()
    return jsonify({
        'ok': True,
        'files': [_document_dict_with_user(d) for d in files if not d.folder_id or _folder_access(DocumentFolder.query.get(d.folder_id), 'view')],
        'folders': [folder_to_dict(f) for f in folders if _folder_access(f, 'view')],
    })


@app.route('/api/documents/trash', methods=['GET'])
@login_required
def api_documents_trash():
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    files = Document.query.filter(
        Document.project_id == int(project_id),
        Document.deleted_at.isnot(None),
    ).order_by(Document.deleted_at.desc()).limit(500).all()
    folders = DocumentFolder.query.filter(
        DocumentFolder.project_id == int(project_id),
        DocumentFolder.deleted_at.isnot(None),
    ).order_by(DocumentFolder.deleted_at.desc()).limit(200).all()
    from document_persistence import folder_to_dict
    return jsonify({
        'ok': True,
        'files': [_document_dict_with_user(d) for d in files],
        'folders': [folder_to_dict(f) for f in folders],
    })


@app.route('/api/documents/<int:doc_id>/restore', methods=['POST'])
@login_required
def api_documents_restore(doc_id):
    doc = Document.query.get_or_404(doc_id)
    doc.deleted_at = None
    _log_doc_activity(doc.project_id, 'restore', document_id=doc.id, detail={'name': doc.name})
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)})


@app.route('/api/document-folders/<int:folder_id>/restore', methods=['POST'])
@login_required
def api_document_folders_restore(folder_id):
    from document_persistence import folder_to_dict
    folder = DocumentFolder.query.get_or_404(folder_id)
    folder.deleted_at = None
    _log_doc_activity(folder.project_id, 'restore', folder_id=folder.id, detail={'name': folder.name})
    db.session.commit()
    return jsonify({'ok': True, 'folder': folder_to_dict(folder)})


@app.route('/api/documents/<int:doc_id>/permanent', methods=['DELETE'])
@login_required
def api_documents_permanent_delete(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if not doc.deleted_at:
        return jsonify({'error': 'Move to recycle bin first'}), 400
    if doc.is_system_locked:
        return jsonify({'error': 'Locked file cannot be permanently deleted'}), 403
    if doc.legal_hold:
        return jsonify({'error': 'File is on legal hold and cannot be deleted'}), 403
    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    file_path = os.path.join(upload_root, 'documents', str(doc.project_id), doc.filename)
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    DocumentShareLink.query.filter_by(document_id=doc.id).delete()
    DocumentVersion.query.filter_by(document_id=doc.id).delete()
    DocumentComment.query.filter_by(document_id=doc.id).delete()
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/documents/<int:doc_id>/versions', methods=['GET'])
@login_required
def api_document_versions_list(doc_id):
    from document_persistence import version_to_dict
    Document.query.get_or_404(doc_id)
    versions = DocumentVersion.query.filter_by(document_id=doc_id).order_by(DocumentVersion.version_no.desc()).all()
    return jsonify({
        'ok': True,
        'versions': [version_to_dict(v, _user_display_name(v.uploaded_by_id)) for v in versions],
        'current_version': Document.query.get(doc_id).version_count or 1,
    })


@app.route('/api/documents/<int:doc_id>/versions', methods=['POST'])
@login_required
def api_document_versions_upload(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.deleted_at:
        return jsonify({'error': 'Document is in recycle bin'}), 400
    lock_err = _document_edit_lock_error(doc)
    if lock_err:
        return lock_err
    folder = DocumentFolder.query.get(doc.folder_id) if doc.folder_id else None
    if folder and not _folder_access(folder, 'upload'):
        return jsonify({'error': 'No upload permission'}), 403
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'file required'}), 400
    file_bytes = file.read()
    notes = (request.form.get('notes') or '').strip()[:500]
    _archive_document_version(doc, notes=notes or 'Replaced with new upload')
    ext = (file.filename or 'bin').rsplit('.', 1)[-1].lower()
    stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    stored_name = f'{stamp}_{secure_filename(doc.name).replace(" ", "_")[:80]}.{ext}'
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id))
    with open(os.path.join(directory, stored_name), 'wb') as fh:
        fh.write(file_bytes)
    old_name = doc.filename
    doc.filename = stored_name
    doc.file_size = len(file_bytes)
    doc.mime_type = file.mimetype or doc.mime_type
    doc.original_filename = file.filename
    doc.uploaded_by_id = current_user.id
    doc.updated_at = datetime.utcnow()
    _log_doc_activity(doc.project_id, 'version', document_id=doc.id, detail={'from': old_name, 'to': stored_name})
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)}), 201


@app.route('/api/documents/<int:doc_id>/versions/<int:ver_id>/download')
@login_required
def api_document_version_download(doc_id, ver_id):
    from document_persistence import version_storage_path
    doc = Document.query.get_or_404(doc_id)
    ver = DocumentVersion.query.filter_by(id=ver_id, document_id=doc_id).first_or_404()
    directory = version_storage_path(app.config['UPLOAD_FOLDER'], doc.project_id, doc.id)
    return send_from_directory(directory, ver.filename, as_attachment=True, download_name=ver.original_filename or ver.filename)


@app.route('/api/documents/<int:doc_id>/versions/<int:ver_id>/restore', methods=['POST'])
@login_required
def api_document_version_restore(doc_id, ver_id):
    from document_persistence import version_storage_path
    doc = Document.query.get_or_404(doc_id)
    lock_err = _document_edit_lock_error(doc)
    if lock_err:
        return lock_err
    ver = DocumentVersion.query.filter_by(id=ver_id, document_id=doc_id).first_or_404()
    ver_dir = version_storage_path(app.config['UPLOAD_FOLDER'], doc.project_id, doc.id)
    src = os.path.join(ver_dir, ver.filename)
    if not os.path.isfile(src):
        return jsonify({'error': 'Version file missing'}), 404
    _archive_document_version(doc, notes=f'Before restore v{ver.version_no}')
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id))
    stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    stored_name = f'{stamp}_restored_{ver.filename}'
    import shutil
    shutil.copy2(src, os.path.join(directory, stored_name))
    doc.filename = stored_name
    doc.file_size = ver.file_size
    doc.mime_type = ver.mime_type
    doc.original_filename = ver.original_filename
    doc.updated_at = datetime.utcnow()
    _log_doc_activity(doc.project_id, 'restore_version', document_id=doc.id, detail={'version_no': ver.version_no})
    db.session.commit()
    return jsonify({'ok': True, 'document': _document_dict_with_user(doc)})


@app.route('/api/documents/<int:doc_id>/comments', methods=['GET'])
@login_required
def api_document_comments_list(doc_id):
    from document_persistence import comment_to_dict
    Document.query.get_or_404(doc_id)
    comments = DocumentComment.query.filter_by(document_id=doc_id).order_by(DocumentComment.created_at.asc()).all()
    return jsonify({
        'ok': True,
        'comments': [comment_to_dict(c, _user_display_name(c.user_id)) for c in comments],
    })


@app.route('/api/documents/<int:doc_id>/comments', methods=['POST'])
@login_required
def api_document_comments_create(doc_id):
    from document_persistence import comment_to_dict
    doc = Document.query.get_or_404(doc_id)
    body = request.get_json(silent=True) or {}
    text = (body.get('body') or '').strip()
    if not text:
        return jsonify({'error': 'body required'}), 400
    comment = DocumentComment(document_id=doc_id, user_id=current_user.id, body=text[:5000], created_at=datetime.utcnow())
    db.session.add(comment)
    _log_doc_activity(doc.project_id, 'comment', document_id=doc.id, detail={'preview': text[:120]})
    db.session.commit()
    return jsonify({'ok': True, 'comment': comment_to_dict(comment, _user_display_name(current_user.id))}), 201


@app.route('/api/documents/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_document_comments_delete(comment_id):
    comment = DocumentComment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id and getattr(current_user, 'role', '') != 'Admin':
        return jsonify({'error': 'Not allowed'}), 403
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/documents/<int:doc_id>/activity', methods=['GET'])
@login_required
def api_document_activity(doc_id):
    from document_persistence import activity_to_dict
    doc = Document.query.get_or_404(doc_id)
    acts = DocumentActivity.query.filter_by(document_id=doc_id).order_by(DocumentActivity.created_at.desc()).limit(100).all()
    return jsonify({'ok': True, 'activity': [activity_to_dict(a, _user_display_name(a.user_id)) for a in acts]})


@app.route('/api/documents/activity', methods=['GET'])
@login_required
def api_project_document_activity():
    from document_persistence import activity_to_dict
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    acts = DocumentActivity.query.filter_by(project_id=int(project_id)).order_by(DocumentActivity.created_at.desc()).limit(200).all()
    return jsonify({'ok': True, 'activity': [activity_to_dict(a, _user_display_name(a.user_id)) for a in acts]})


def _create_folder_share_link(folder_id, days=30, max_downloads=None, password=None, allow_upload=False):
    from document_features import clamp_share_expiry_days, project_document_settings
    from document_persistence import default_share_expiry, folder_share_link_to_dict, hash_share_password, new_share_token

    folder = DocumentFolder.query.get_or_404(folder_id)
    project = Project.query.get(folder.project_id)
    settings = project_document_settings(project) if project else {}
    expiry_days = clamp_share_expiry_days(days, settings)
    needs_approval = bool(settings.get('share_requires_approval')) and getattr(current_user, 'role', '') not in ('Admin', 'Project Manager')
    approval_status = 'pending' if needs_approval else 'approved'
    link = DocumentFolderShareLink(
        folder_id=folder.id,
        token=new_share_token(),
        label=folder.name,
        password_hash=hash_share_password(password),
        expires_at=default_share_expiry(expiry_days),
        max_downloads=max_downloads,
        download_count=0,
        allow_browse=True,
        allow_download=True,
        allow_upload=bool(allow_upload),
        created_by_id=current_user.id,
        created_at=datetime.utcnow(),
        approval_status=approval_status,
        approved_at=datetime.utcnow() if approval_status == 'approved' else None,
        approved_by_id=current_user.id if approval_status == 'approved' else None,
    )
    db.session.add(link)
    _log_doc_activity(folder.project_id, 'share', folder_id=folder.id, detail={'type': 'folder_link', 'allow_upload': allow_upload, 'approval_status': approval_status})
    db.session.commit()
    share = folder_share_link_to_dict(link, _documents_base_url())
    kind = 'Request-files' if allow_upload else 'Folder share'
    if approval_status == 'pending':
        _notify_documents_team(
            folder.project_id,
            f'{kind} link pending approval',
            f'A share link for folder "{folder.name}" needs PM approval.',
            '/documents',
        )
    else:
        _notify_documents_team(
            folder.project_id,
            f'{kind} link created',
            f'A link was created for folder "{folder.name}". Expires in {expiry_days} days.',
            share.get('share_url'),
        )
    share['approval_status'] = approval_status
    share['expires_in_days'] = expiry_days
    return share


@app.route('/api/document-folders/<int:folder_id>/share-links', methods=['GET'])
@login_required
def api_folder_share_links_list(folder_id):
    from document_persistence import folder_share_link_to_dict
    DocumentFolder.query.get_or_404(folder_id)
    links = DocumentFolderShareLink.query.filter_by(folder_id=folder_id).order_by(DocumentFolderShareLink.created_at.desc()).all()
    base = _documents_base_url()
    return jsonify({'ok': True, 'links': [folder_share_link_to_dict(l, base) for l in links]})


@app.route('/api/document-folders/<int:folder_id>/share-links', methods=['POST'])
@login_required
def api_folder_share_links_create(folder_id):
    body = request.get_json(silent=True) or {}
    days = int(body.get('expires_days') or 30)
    max_dl = body.get('max_downloads')
    share = _create_folder_share_link(
        folder_id,
        days=days,
        max_downloads=int(max_dl) if max_dl else None,
        password=body.get('password'),
        allow_upload=bool(body.get('allow_upload')),
    )
    return jsonify({'ok': True, 'share_link': share}), 201


@app.route('/api/folder-share-links/<int:link_id>', methods=['DELETE'])
@login_required
def api_folder_share_links_revoke(link_id):
    link = DocumentFolderShareLink.query.get_or_404(link_id)
    link.revoked_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/share/folder/<token>/browse')
def public_folder_share_browse(token):
    from document_persistence import folder_is_under_root_share, folder_to_dict, share_link_is_valid

    link = DocumentFolderShareLink.query.filter_by(token=token).first_or_404()
    if not share_link_is_valid(link):
        return jsonify({'error': 'Link unavailable'}), 410
    if link.password_hash and not _share_is_unlocked(link):
        return jsonify({'error': 'Password required'}), 403
    if not link.allow_browse:
        return jsonify({'error': 'Browse disabled'}), 403
    root = DocumentFolder.query.get_or_404(link.folder_id)
    folder_id = request.args.get('folder_id', type=int) or root.id
    if not folder_is_under_root_share(db, DocumentFolder, folder_id, root.id):
        return jsonify({'error': 'Folder not in shared scope'}), 403
    current = DocumentFolder.query.get(folder_id)
    subfolders = _active_folders().filter_by(parent_id=folder_id).order_by(DocumentFolder.name).all()
    files = _active_documents().filter_by(folder_id=folder_id).order_by(Document.name).all()
    breadcrumbs = []
    if current:
        chain = [current]
        parent = DocumentFolder.query.get(current.parent_id) if current.parent_id else None
        while parent:
            if parent.id == root.id:
                chain.insert(0, parent)
                break
            chain.insert(0, parent)
            parent = DocumentFolder.query.get(parent.parent_id) if parent.parent_id else None
        breadcrumbs = [{'id': f.id, 'name': f.name} for f in chain]
    return jsonify({
        'ok': True,
        'root_folder_id': root.id,
        'folder_id': folder_id,
        'folder_name': current.name if current else root.name,
        'breadcrumbs': breadcrumbs,
        'allow_upload': bool(link.allow_upload),
        'allow_download': bool(link.allow_download),
        'folders': [folder_to_dict(f, _active_folders().filter_by(parent_id=f.id).count(), _active_documents().filter_by(folder_id=f.id).count()) for f in subfolders],
        'files': [{'id': d.id, 'name': d.name, 'size': d.file_size, 'mime_type': d.mime_type, 'document_type': d.document_type} for d in files],
    })


@app.route('/share/folder/<token>/download/<int:doc_id>')
def public_folder_share_download(token, doc_id):
    from document_persistence import folder_is_under_root_share, format_file_size, share_link_is_valid

    link = DocumentFolderShareLink.query.filter_by(token=token).first_or_404()
    if not share_link_is_valid(link):
        return jsonify({'error': 'Link unavailable'}), 410
    if link.password_hash and not _share_is_unlocked(link):
        return jsonify({'error': 'Password required'}), 403
    if not link.allow_download:
        return jsonify({'error': 'Download disabled'}), 403
    doc = _active_documents().filter_by(id=doc_id).first_or_404()
    if not folder_is_under_root_share(db, DocumentFolder, doc.folder_id, link.folder_id):
        return jsonify({'error': 'File not in shared folder'}), 403
    directory = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id))
    if not os.path.isfile(os.path.join(directory, doc.filename)):
        return jsonify({'error': 'File not found'}), 404
    link.download_count = (link.download_count or 0) + 1
    db.session.commit()
    return send_from_directory(directory, doc.filename, as_attachment=True, download_name=doc.original_filename or doc.name)


@app.route('/share/folder/<token>/upload', methods=['POST'])
def public_folder_share_upload(token):
    from document_persistence import folder_is_under_root_share, share_link_is_valid

    link = DocumentFolderShareLink.query.filter_by(token=token).first_or_404()
    if not share_link_is_valid(link):
        return jsonify({'error': 'Link unavailable'}), 410
    if link.password_hash and not _share_is_unlocked(link):
        return jsonify({'error': 'Password required'}), 403
    if not link.allow_upload:
        return jsonify({'error': 'Upload disabled'}), 403
    folder_id = request.form.get('folder_id', type=int) or link.folder_id
    if not folder_is_under_root_share(db, DocumentFolder, folder_id, link.folder_id):
        return jsonify({'error': 'Invalid folder'}), 403
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'file required'}), 400
    folder = DocumentFolder.query.get_or_404(folder_id)
    file_bytes = file.read()
    try:
        doc_dict = _save_document_bytes(
            folder.project_id, file_bytes, file.filename, file.filename,
            file.mimetype or 'application/octet-stream', 'Shared upload', folder.id, False,
            source_metadata={'shared_upload': True, 'share_token': token},
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    _notify_documents_team(
        folder.project_id,
        'File uploaded via shared link',
        f'"{file.filename}" was uploaded to folder "{folder.name}" via a request-files link.',
        f'/documents?project_id={folder.project_id}',
    )
    return jsonify({'ok': True, 'document': doc_dict}), 201


@app.route('/api/document-folders/<int:folder_id>/permissions', methods=['GET'])
@login_required
def api_folder_permissions_list(folder_id):
    from document_persistence import permission_to_dict
    folder = DocumentFolder.query.get_or_404(folder_id)
    if not _folder_access(folder, 'manage') and getattr(current_user, 'role', '') != 'Admin':
        return jsonify({'error': 'Manage permission required'}), 403
    perms = DocumentFolderPermission.query.filter_by(folder_id=folder_id).all()
    out = []
    for p in perms:
        u = User.query.get(p.user_id)
        out.append(permission_to_dict(p, _user_display_name(p.user_id), u.email if u else None))
    return jsonify({'ok': True, 'permissions': out})


@app.route('/api/document-folders/<int:folder_id>/permissions', methods=['POST'])
@login_required
def api_folder_permissions_set(folder_id):
    from document_persistence import permission_to_dict
    folder = DocumentFolder.query.get_or_404(folder_id)
    if not _folder_access(folder, 'manage') and getattr(current_user, 'role', '') != 'Admin':
        return jsonify({'error': 'Manage permission required'}), 403
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    perm = DocumentFolderPermission.query.filter_by(folder_id=folder_id, user_id=int(user_id)).first()
    if not perm:
        perm = DocumentFolderPermission(folder_id=folder_id, user_id=int(user_id), created_at=datetime.utcnow())
        db.session.add(perm)
    perm.can_view = bool(body.get('can_view', True))
    perm.can_upload = bool(body.get('can_upload', False))
    perm.can_manage = bool(body.get('can_manage', False))
    # Never lock out the user who is setting permissions.
    if current_user.id != int(user_id):
        mgr = DocumentFolderPermission.query.filter_by(folder_id=folder_id, user_id=current_user.id).first()
        if not mgr:
            mgr = DocumentFolderPermission(
                folder_id=folder_id, user_id=current_user.id,
                can_view=True, can_upload=True, can_manage=True,
                created_at=datetime.utcnow(),
            )
            db.session.add(mgr)
        else:
            mgr.can_view = True
            mgr.can_upload = True
            mgr.can_manage = True
    db.session.commit()
    u = User.query.get(perm.user_id)
    return jsonify({'ok': True, 'permission': permission_to_dict(perm, _user_display_name(perm.user_id), u.email if u else None)})


@app.route('/api/document-folders/permissions/<int:perm_id>', methods=['DELETE'])
@login_required
def api_folder_permissions_delete(perm_id):
    perm = DocumentFolderPermission.query.get_or_404(perm_id)
    folder = DocumentFolder.query.get_or_404(perm.folder_id)
    if not _folder_access(folder, 'manage') and getattr(current_user, 'role', '') != 'Admin':
        return jsonify({'error': 'Manage permission required'}), 403
    db.session.delete(perm)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/users/list', methods=['GET'])
@login_required
def api_users_list_short():
    users = User.query.filter_by(status='Active').order_by(User.first_name, User.last_name).limit(500).all()
    return jsonify({
        'ok': True,
        'users': [{'id': u.id, 'name': _user_display_name(u.id), 'email': u.email} for u in users],
    })


@app.route('/api/document-folders/<int:folder_id>/download-zip')
@login_required
def api_document_folder_download_zip(folder_id):
    import io
    import zipfile
    from document_integration import iter_folder_documents

    folder = DocumentFolder.query.get_or_404(folder_id)
    if not _folder_access(folder, 'view'):
        return jsonify({'error': 'No access to this folder'}), 403
    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    entries = iter_folder_documents(Document, DocumentFolder, upload_root, folder.id)
    if not entries:
        return jsonify({'error': 'Folder has no files to download'}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        used: set[str] = set()
        for arc, path in entries:
            name = arc
            n = 1
            while name in used:
                base, dot, ext = arc.rpartition('.')
                if dot:
                    name = f'{base} ({n}).{ext}'
                else:
                    name = f'{arc} ({n})'
                n += 1
            used.add(name)
            zf.write(path, name)
    buf.seek(0)
    safe = secure_filename(folder.name) or 'folder'
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{safe}.zip')


@app.route('/share/folder/<token>/download-zip')
def public_folder_share_download_zip(token):
    import io
    import zipfile
    from document_integration import iter_folder_documents
    from document_persistence import share_link_is_valid

    link = DocumentFolderShareLink.query.filter_by(token=token).first_or_404()
    if not share_link_is_valid(link):
        return jsonify({'error': 'Link unavailable'}), 410
    if link.password_hash and not _share_is_unlocked(link):
        return jsonify({'error': 'Password required'}), 403
    if not link.allow_download:
        return jsonify({'error': 'Download disabled'}), 403
    folder = DocumentFolder.query.get_or_404(link.folder_id)
    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    entries = iter_folder_documents(Document, DocumentFolder, upload_root, folder.id)
    if not entries:
        return jsonify({'error': 'Folder has no files'}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arc, path in entries:
            zf.write(path, arc)
    buf.seek(0)
    link.download_count = (link.download_count or 0) + 1
    db.session.commit()
    safe = secure_filename(folder.name) or 'shared-folder'
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{safe}.zip')


@app.route('/api/documents/share-links/admin', methods=['GET'])
@login_required
def api_documents_share_links_admin():
    from document_persistence import folder_share_link_to_dict, share_link_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    base = _documents_base_url()
    docs = _active_documents().filter_by(project_id=int(project_id)).all()
    doc_ids = [d.id for d in docs]
    file_links = []
    if doc_ids:
        for link in DocumentShareLink.query.filter(DocumentShareLink.document_id.in_(doc_ids)).order_by(DocumentShareLink.created_at.desc()).all():
            doc = Document.query.get(link.document_id)
            row = share_link_to_dict(link, base)
            row['target_name'] = doc.name if doc else 'File'
            row['target_type'] = 'file'
            file_links.append(row)
    folders = _active_folders().filter_by(project_id=int(project_id)).all()
    folder_ids = [f.id for f in folders]
    folder_links = []
    if folder_ids:
        for link in DocumentFolderShareLink.query.filter(DocumentFolderShareLink.folder_id.in_(folder_ids)).order_by(DocumentFolderShareLink.created_at.desc()).all():
            folder = DocumentFolder.query.get(link.folder_id)
            row = folder_share_link_to_dict(link, base)
            row['target_name'] = folder.name if folder else 'Folder'
            row['target_type'] = 'folder'
            row['allow_upload'] = bool(link.allow_upload)
            folder_links.append(row)
    return jsonify({'ok': True, 'file_links': file_links, 'folder_links': folder_links})


@app.route('/api/documents/share-links/admin/<string:link_kind>/<int:link_id>', methods=['DELETE'])
@login_required
def api_documents_share_links_admin_revoke(link_kind, link_id):
    if link_kind == 'file':
        link = DocumentShareLink.query.get_or_404(link_id)
        link.revoked_at = datetime.utcnow()
    elif link_kind == 'folder':
        link = DocumentFolderShareLink.query.get_or_404(link_id)
        link.revoked_at = datetime.utcnow()
    else:
        return jsonify({'error': 'Invalid link kind'}), 400
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/documents/bulk', methods=['POST'])
@login_required
def api_documents_bulk():
    """Bulk move, delete, or download documents."""
    import io
    import zipfile

    body = request.get_json(silent=True) or {}
    action = (body.get('action') or '').strip().lower()
    doc_ids = [int(x) for x in (body.get('document_ids') or []) if x]
    if not doc_ids:
        return jsonify({'error': 'document_ids required'}), 400

    docs = [_active_documents().filter_by(id=did).first() for did in doc_ids]
    docs = [d for d in docs if d]
    if not docs:
        return jsonify({'error': 'No documents found'}), 404

    if action == 'move':
        folder_id = body.get('folder_id')
        if not folder_id:
            return jsonify({'error': 'folder_id required'}), 400
        folder = DocumentFolder.query.get_or_404(int(folder_id))
        moved = 0
        for doc in docs:
            if doc.is_system_locked or doc.legal_hold:
                continue
            lock_err = _document_edit_lock_error(doc)
            if lock_err:
                continue
            if doc.project_id != folder.project_id:
                continue
            doc.folder_id = folder.id
            doc.updated_at = datetime.utcnow()
            moved += 1
        db.session.commit()
        return jsonify({'ok': True, 'moved_count': moved})

    if action == 'delete':
        deleted = 0
        for doc in docs:
            if doc.is_system_locked or doc.legal_hold:
                continue
            lock_err = _document_edit_lock_error(doc)
            if lock_err:
                continue
            if not doc.deleted_at:
                doc.deleted_at = datetime.utcnow()
                _log_doc_activity(doc.project_id, 'delete', document_id=doc.id, detail={'name': doc.name, 'bulk': True})
                deleted += 1
        db.session.commit()
        return jsonify({'ok': True, 'deleted_count': deleted})

    if action == 'download_zip':
        upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            used: set[str] = set()
            for doc in docs:
                path = os.path.join(upload_root, 'documents', str(doc.project_id), doc.filename)
                if not os.path.isfile(path):
                    continue
                arc = (doc.original_filename or doc.name or doc.filename).replace('\\', '/').split('/')[-1]
                name = arc
                n = 1
                while name in used:
                    base, dot, ext = arc.rpartition('.')
                    name = f'{base} ({n}).{ext}' if dot else f'{arc} ({n})'
                    n += 1
                used.add(name)
                zf.write(path, name)
        if not used:
            return jsonify({'error': 'No files to download'}), 404
        buf.seek(0)
        return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='documents.zip')

    return jsonify({'error': 'Invalid action — use move, delete, or download_zip'}), 400


@app.route('/api/documents/folder-templates', methods=['GET'])
@login_required
def api_document_folder_templates_list():
    project_type = request.args.get('project_type')
    q = DocumentFolderTemplate.query.order_by(DocumentFolderTemplate.name)
    if project_type:
        q = q.filter(
            db.or_(
                DocumentFolderTemplate.project_type.is_(None),
                DocumentFolderTemplate.project_type == '',
                DocumentFolderTemplate.project_type == project_type,
            )
        )
    templates = q.all()
    return jsonify({
        'ok': True,
        'templates': [{
            'id': t.id,
            'name': t.name,
            'project_type': t.project_type,
            'description': t.description,
            'is_system': bool(t.is_system),
        } for t in templates],
    })


@app.route('/api/documents/folder-templates/<int:template_id>/apply', methods=['POST'])
@login_required
def api_document_folder_template_apply(template_id):
    from document_features import apply_folder_template

    template = DocumentFolderTemplate.query.get_or_404(template_id)
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    created = apply_folder_template(db, DocumentFolder, template, int(project_id), current_user.id)
    db.session.commit()
    return jsonify({'ok': True, 'created_folder_ids': created, 'created_count': len(created)})


@app.route('/api/projects/<int:project_id>/document-settings', methods=['GET'])
@login_required
def api_project_document_settings_get(project_id):
    from document_features import project_document_settings

    project = Project.query.get_or_404(project_id)
    return jsonify({'ok': True, 'settings': project_document_settings(project)})


@app.route('/api/projects/<int:project_id>/document-settings', methods=['PATCH'])
@login_required
def api_project_document_settings_patch(project_id):
    from document_features import project_document_settings

    if getattr(current_user, 'role', '') not in ('Admin', 'Project Manager'):
        return jsonify({'error': 'Admin or PM required'}), 403
    project = Project.query.get_or_404(project_id)
    body = request.get_json(silent=True) or {}
    details = project.get_details()
    docs = details.get('documents') or {}
    for key in ('share_requires_approval', 'default_share_expiry_days', 'max_share_expiry_days', 'retention_years'):
        if key in body:
            docs[key] = body[key]
    details['documents'] = docs
    project.set_details(details)
    db.session.commit()
    return jsonify({'ok': True, 'settings': project_document_settings(project)})


@app.route('/api/documents/share-links/<string:link_kind>/<int:link_id>/approve', methods=['POST'])
@login_required
def api_share_link_approve(link_kind, link_id):
    if getattr(current_user, 'role', '') not in ('Admin', 'Project Manager'):
        return jsonify({'error': 'Admin or PM required'}), 403
    body = request.get_json(silent=True) or {}
    approve = body.get('approve', True)
    if link_kind == 'file':
        link = DocumentShareLink.query.get_or_404(link_id)
    elif link_kind == 'folder':
        link = DocumentFolderShareLink.query.get_or_404(link_id)
    else:
        return jsonify({'error': 'Invalid link kind'}), 400
    link.approval_status = 'approved' if approve else 'rejected'
    link.approved_by_id = current_user.id
    link.approved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'approval_status': link.approval_status})


@app.route('/api/submittals/sync', methods=['POST'])
@login_required
def api_submittal_sync():
    """Upsert a submittal from the UI and return server id for attachments."""
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    number = (body.get('number') or '').strip()
    description = (body.get('description') or body.get('subject') or 'Submittal').strip()
    if not project_id or not number:
        return jsonify({'error': 'project_id and number required'}), 400
    submittal = Submittal.query.filter_by(project_id=int(project_id), number=number).first()
    if not submittal:
        submittal = Submittal(
            project_id=int(project_id),
            number=number,
            description=description[:200],
            spec_section=body.get('spec_section'),
            status=body.get('status') or 'Pending',
            priority=body.get('priority') or 'Medium',
            submitted_by=body.get('submitted_by') or _user_display_name(current_user.id),
            date=datetime.utcnow().date(),
        )
        db.session.add(submittal)
    else:
        submittal.description = description[:200]
        if body.get('status'):
            submittal.status = body['status']
        if body.get('spec_section'):
            submittal.spec_section = body['spec_section']
    db.session.commit()
    from rfi_persistence import _parse_json
    attachments = _parse_json(submittal.attachments_json, [])
    return jsonify({'ok': True, 'submittal_id': submittal.id, 'number': submittal.number, 'attachments': attachments})


@app.route('/api/submittals/<int:submittal_id>/attachments', methods=['GET'])
@login_required
def api_submittal_list_attachments(submittal_id):
    from rfi_persistence import _parse_json
    submittal = Submittal.query.get_or_404(submittal_id)
    attachments = _parse_json(submittal.attachments_json, [])
    for a in attachments:
        if a.get('document_id'):
            a['url'] = url_for('api_documents_download', doc_id=a['document_id'])
        elif a.get('filename'):
            a['url'] = url_for('serve_submittal_attachment', submittal_id=submittal_id, filename=a.get('filename', ''))
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/api/daily-logs/<int:log_id>', methods=['GET'])
@login_required
def api_daily_log_get(log_id):
    from daily_log_persistence import serialize_log
    log = DailyLog.query.get_or_404(log_id)
    return jsonify({
        'ok': True,
        'log': serialize_log(
            log, ManpowerEntry, EquipmentEntry, User=User,
            url_helpers=_daily_log_url_helpers(),
        ),
    })


@app.route('/api/daily-logs/<int:log_id>/attachments', methods=['GET'])
@login_required
def api_daily_log_list_attachments(log_id):
    from rfi_persistence import _parse_json
    log = DailyLog.query.get_or_404(log_id)
    attachments = _parse_json(log.attachments_json, [])
    for a in attachments:
        if a.get('document_id'):
            a['url'] = url_for('api_documents_download', doc_id=a['document_id'])
        elif a.get('filename'):
            a['url'] = url_for('serve_daily_log_attachment', log_id=log_id, filename=a.get('filename', ''))
    return jsonify({'ok': True, 'attachments': attachments})


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


@app.route('/api/drawings/bulk-update', methods=['PATCH'])
@login_required
def api_bulk_update_drawings():
    """Update multiple drawing sheet rows (spreadsheet-style batch save)."""
    from drawing_persistence import update_drawing_metadata, drawing_to_dict, group_drawings_by_section
    data = request.get_json(silent=True) or {}
    updates = data.get('updates') or []
    if not updates:
        return jsonify({'error': 'updates required'}), 400
    project_id = data.get('project_id') or get_current_project_id()
    results = []
    errors = []
    for item in updates:
        drawing_id = item.get('id')
        if not drawing_id:
            continue
        drawing = Drawing.query.get(int(drawing_id))
        if not drawing:
            errors.append({'id': drawing_id, 'error': 'Not found'})
            continue
        if project_id and drawing.project_id != int(project_id):
            errors.append({'id': drawing_id, 'error': 'Wrong project'})
            continue
        fields = {k: v for k, v in item.items() if k != 'id'}
        if not fields:
            continue
        try:
            drawing, rev, rev_count, markup_count = update_drawing_metadata(
                db, Drawing, DrawingRevision, DrawingMarkup, drawing, fields,
            )
            results.append(drawing_to_dict(drawing, rev, rev_count, markup_count))
        except ValueError as exc:
            errors.append({'id': drawing_id, 'error': str(exc)})
    if errors and not results:
        db.session.rollback()
        return jsonify({'error': errors[0]['error'], 'errors': errors}), 400
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500
    grouped = group_drawings_by_section(results) if results else {}
    return jsonify({'ok': True, 'drawings': results, 'errors': errors, 'sections': grouped})


@app.route('/api/drawings/<int:drawing_id>', methods=['GET', 'PUT'])
@login_required
def api_get_drawing(drawing_id):
    from drawing_persistence import revision_to_dict, markup_to_dict, update_drawing_metadata, drawing_to_dict
    drawing = Drawing.query.get_or_404(drawing_id)
    if request.method == 'PUT':
        body = request.get_json(silent=True) or {}
        try:
            drawing, rev, rev_count, markup_count = update_drawing_metadata(
                db, Drawing, DrawingRevision, DrawingMarkup, drawing, body,
            )
            db.session.commit()
            return jsonify({'ok': True, 'drawing': drawing_to_dict(drawing, rev, rev_count, markup_count)})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 500
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
    from document_persistence import resolve_folder_by_key
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
    parent = resolve_folder_by_key(db, DocumentFolder, int(project_id), 'drawing-sets')
    folder_by_name = {}
    if parent:
        child_q = DocumentFolder.query.filter_by(project_id=int(project_id), parent_id=parent.id)
        if hasattr(DocumentFolder, 'deleted_at'):
            child_q = child_q.filter(DocumentFolder.deleted_at.is_(None))
        for folder in child_q.all():
            folder_by_name[folder.name] = folder
    for name, info in sets.items():
        folder = folder_by_name.get(name)
        if not folder:
            continue
        info['documents_folder_id'] = folder.id
        info['documents_url'] = f'/documents?project_id={project_id}&folder_id={folder.id}'
        full_doc = (
            Document.query.filter_by(project_id=int(project_id), folder_id=folder.id)
            .filter(Document.deleted_at.is_(None) if hasattr(Document, 'deleted_at') else True)
            .filter(Document.name.ilike('%Full Set%'))
            .order_by(Document.created_at.desc())
            .first()
        )
        if full_doc:
            info['full_set_document_id'] = full_doc.id
            info['full_set_download_url'] = f'/api/documents/{full_doc.id}/download'
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


@app.route('/api/drawings/<int:drawing_id>/export-to-documents', methods=['POST'])
@login_required
def api_drawing_export_to_documents(drawing_id):
    """Copy current drawing sheet PDF into Documents › Drawings › Drawing Sets."""
    from drawing_persistence import resolve_drawing_file_path, current_revision_for_drawing, drawings_by_set_name
    from document_persistence import resolve_folder_by_key

    drawing = Drawing.query.get_or_404(drawing_id)
    body = request.get_json(silent=True) or {}
    create_share = bool(body.get('create_share_link'))
    rev = current_revision_for_drawing(DrawingRevision, drawing)
    upload_root = app.config.get('UPLOAD_FOLDER')
    resolved = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
    if not rev or not resolved or not os.path.isfile(resolved):
        return jsonify({'error': 'Drawing file not found'}), 404
    with open(resolved, 'rb') as fh:
        file_bytes = fh.read()
    folder = resolve_folder_by_key(db, DocumentFolder, drawing.project_id, 'drawing-sets')
    if not folder:
        return jsonify({'error': 'Drawing Sets folder missing'}), 500
    name = f'{drawing.sheet_number or "Sheet"} — {drawing.title or (rev.set_name if rev else None) or "Drawing"}'.strip(' —')
    try:
        doc_dict = _save_document_bytes(
            drawing.project_id, file_bytes, name, os.path.basename(resolved),
            'application/pdf', 'Drawing', folder.id, False,
            source_drawing_id=drawing.id,
            source_sheet=drawing.sheet_number,
            source_metadata={
                'set_name': rev.set_name if rev else None,
                'discipline': drawing.discipline,
                'revision': rev.revision_label if rev else None,
                'exported_from': 'drawings',
                'mirrored_from_module': True,
            },
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    share = _create_document_share_link(doc_dict['id']) if create_share else None
    _notify_documents_team(
        drawing.project_id,
        'Drawing exported to Documents',
        f'"{name}" was saved to Documents › Drawings › Drawing Sets.',
        f'/documents?project_id={drawing.project_id}',
    )
    return jsonify({'ok': True, 'document': doc_dict, 'share_link': share}), 201


@app.route('/api/drawings/export-set-to-documents', methods=['POST'])
@login_required
def api_drawing_set_export_to_documents():
    """Export all sheets in a drawing set to Documents › Drawings › Drawing Sets."""
    from drawing_persistence import resolve_drawing_file_path, current_revision_for_drawing, drawings_by_set_name
    from document_persistence import ensure_document_schema, resolve_folder_by_key

    try:
        ensure_project_schema()
        ensure_document_schema(db.engine, db)
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        set_name = (body.get('set_name') or '').strip()
        if not project_id or not set_name:
            return jsonify({'error': 'project_id and set_name required'}), 400
        folder = resolve_folder_by_key(db, DocumentFolder, int(project_id), 'drawing-sets')
        if not folder:
            return jsonify({'error': 'Drawing Sets folder missing'}), 500
        drawings = drawings_by_set_name(db, Drawing, DrawingRevision, int(project_id), set_name)
        if not drawings:
            return jsonify({'error': 'No sheets in this set'}), 404
        upload_root = app.config.get('UPLOAD_FOLDER')
        exported = []
        errors = []
        for drawing in drawings:
            rev = current_revision_for_drawing(DrawingRevision, drawing)
            resolved = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
            if not rev or not resolved or not os.path.isfile(resolved):
                errors.append(f'{drawing.sheet_number}: file not found')
                continue
            with open(resolved, 'rb') as fh:
                file_bytes = fh.read()
            name = f'{drawing.sheet_number or "Sheet"} — {drawing.title or set_name}'.strip(' —')
            try:
                doc_dict = _save_document_bytes(
                    int(project_id), file_bytes, name, os.path.basename(resolved),
                    'application/pdf', 'Drawing', folder.id, False,
                    source_drawing_id=drawing.id,
                    source_sheet=drawing.sheet_number,
                    source_metadata={'set_name': set_name, 'exported_from': 'drawings_set', 'mirrored_from_module': True},
                )
                exported.append(doc_dict)
            except ValueError as exc:
                errors.append(f'{drawing.sheet_number}: {exc}')
            except Exception as exc:
                db.session.rollback()
                errors.append(f'{drawing.sheet_number}: {exc}')
        if exported:
            try:
                _notify_documents_team(
                    int(project_id),
                    'Drawing set exported to Documents',
                    f'{len(exported)} sheet(s) from "{set_name}" were saved to Documents › Drawings › Drawing Sets.',
                    f'/documents?project_id={project_id}',
                )
            except Exception:
                db.session.rollback()
        if not exported and errors:
            return jsonify({'error': errors[0], 'errors': errors}), 500
        return jsonify({'ok': True, 'exported_count': len(exported), 'documents': exported, 'errors': errors})
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('export-set-to-documents failed')
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
    from drawing_upload_jobs import (
        create_job,
        mark_complete,
        mark_progress,
        should_run_async,
        start_job,
    )
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
        use_fast_analysis = False
        upload_kwargs = dict(
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
            fast_analysis=use_fast_analysis,
        )

        if should_run_async(len(pages)):
            job = create_job(int(project_id), len(pages))

            def run_import(job_id=job.id):
                with app.app_context():
                    try:
                        def on_progress(done, total, current_page):
                            mark_progress(
                                job_id,
                                done,
                                total,
                                current_page,
                                f'Reading title block {done} of {total} (page {current_page})…',
                            )

                        created, needs_review = process_pages_from_upload(
                            db, Drawing, DrawingRevision, DrawingMarkup,
                            progress_callback=on_progress,
                            **upload_kwargs,
                        )
                        if not created:
                            db.session.rollback()
                            raise RuntimeError('No drawing pages could be imported.')
                        commit_with_retry(db.session)
                        mark_progress(
                            job_id,
                            len(created),
                            len(pages),
                            len(pages),
                            'Finalizing import…',
                        )
                        drawings = []
                        if len(created) <= 30:
                            drawings = [
                                _serialize_drawing(Drawing.query.get(item['id']))
                                for item in created
                                if item.get('id') and Drawing.query.get(item['id'])
                            ]
                        docs_info = None
                        result_warnings = list(split_warnings)
                        if from_combined_set:
                            try:
                                docs_info = _archive_drawing_set_to_documents(
                                    int(project_id), set_name, dest, created, upload_kwargs['uploaded_by_id'],
                                )
                            except Exception as archive_exc:
                                result_warnings.append(
                                    f'Drawings imported, but Documents archive failed: {archive_exc}'
                                )
                            else:
                                if docs_info and docs_info.get('documents_url'):
                                    result_warnings.append(
                                        f'Set archived to Documents › Drawing Sets › {set_name}.'
                                    )
                                if docs_info and docs_info.get('skipped_individual_sheets', 0) > 20:
                                    result_warnings.append(
                                        'Full set PDF saved to Documents (individual sheet copies skipped for large sets).'
                                    )
                                if docs_info and docs_info.get('archive_error'):
                                    result_warnings.append(str(docs_info['archive_error']))
                        mark_complete(job_id, {
                            'ok': True,
                            'split': from_combined_set,
                            'page_count': len(pages),
                            'expected_page_count': expected_page_count,
                            'split_engine': split_engine,
                            'warnings': result_warnings,
                            'created_count': len(created),
                            'needs_review_count': len(needs_review),
                            'needs_review': needs_review,
                            'drawings': drawings,
                            'pages': created,
                            'drawing': drawings[0] if len(drawings) == 1 else None,
                            'revision': drawings[0].get('revision_label') if len(drawings) == 1 else None,
                            'documents': _slim_documents_archive(docs_info),
                        })
                    except Exception:
                        db.session.rollback()
                        raise
                    finally:
                        db.session.remove()

            start_job(job.id, run_import)
            return jsonify({
                'ok': True,
                'async': True,
                'job_id': job.id,
                'page_count': len(pages),
                'expected_page_count': expected_page_count,
                'message': f'Importing {len(pages)} sheets in the background…',
            }), 202

        created, needs_review = process_pages_from_upload(
            db, Drawing, DrawingRevision, DrawingMarkup,
            **upload_kwargs,
        )

        if not created:
            db.session.rollback()
            return jsonify({
                'error': 'No drawing pages could be imported.',
                'needs_review': needs_review,
            }), 400

        commit_with_retry(db.session)
        drawings = []
        if len(created) <= 30:
            drawings = [
                _serialize_drawing(Drawing.query.get(item['id']))
                for item in created
                if item.get('id') and Drawing.query.get(item['id'])
            ]
        docs_info = None
        response_warnings = list(split_warnings)
        if from_combined_set:
            try:
                docs_info = _archive_drawing_set_to_documents(
                    int(project_id), set_name, dest, created, current_user.id,
                )
            except Exception as archive_exc:
                response_warnings.append(f'Drawings imported, but Documents archive failed: {archive_exc}')
            else:
                if docs_info and docs_info.get('documents_url'):
                    response_warnings.append(f'Set archived to Documents › Drawing Sets › {set_name}.')
                if docs_info and docs_info.get('skipped_individual_sheets', 0) > 20:
                    response_warnings.append(
                        'Full set PDF saved to Documents (individual sheet copies skipped for large sets).'
                    )
                if docs_info and docs_info.get('archive_error'):
                    response_warnings.append(str(docs_info['archive_error']))
        return jsonify({
            'ok': True,
            'split': from_combined_set,
            'page_count': len(pages),
            'expected_page_count': expected_page_count,
            'split_engine': split_engine,
            'warnings': response_warnings,
            'created_count': len(created),
            'needs_review_count': len(needs_review),
            'needs_review': needs_review,
            'drawings': drawings,
            'pages': created,
            'drawing': drawings[0] if len(drawings) == 1 else None,
            'revision': drawings[0].get('revision_label') if len(drawings) == 1 else None,
            'documents': _slim_documents_archive(docs_info),
        })
    except Exception as exc:
        db.session.rollback()
        msg = str(exc)
        if 'database is locked' in msg.lower() or 'database is busy' in msg.lower():
            msg = (
                'The database was busy during import (another Case PM request may have been writing at the same time). '
                'Close extra browser tabs, wait a few seconds, and try the upload again.'
            )
        return jsonify({'error': msg}), 500


@app.route('/api/drawings/upload-jobs/<job_id>', methods=['GET'])
@login_required
def api_get_drawing_upload_job(job_id):
    from drawing_upload_jobs import get_job
    job = get_job(job_id)
    if not job:
        return jsonify({'error': 'Upload job not found'}), 404
    current = get_current_project_id()
    if not current or int(job.project_id) != int(current):
        return jsonify({'error': 'Upload job not found'}), 404
    payload = job.to_dict()
    if job.status == 'complete' and job.result:
        payload['ok'] = True
        payload.update(job.result)
    return jsonify(payload)


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


@app.route('/api/drawings/search/text', methods=['POST'])
@login_required
def api_drawings_search_text():
    from drawing_search import DrawingSearchError, prepare_drawing_targets, search_text
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        query = (body.get('query') or '').strip()
        scope = body.get('scope') or 'project'
        drawing_id = body.get('drawing_id')
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        if len(query) < 2:
            return jsonify({'error': 'Enter at least 2 characters'}), 400
        ids = None
        if scope == 'sheet' and drawing_id is not None:
            try:
                ids = [int(drawing_id)]
            except (TypeError, ValueError):
                return jsonify({'error': 'Invalid drawing_id'}), 400
        targets = prepare_drawing_targets(Drawing, DrawingRevision, ids, int(project_id))
        if scope == 'sheet' and not targets:
            return jsonify({'error': 'Drawing not found'}), 404
        results = search_text(
            targets, query, upload_root=app.config.get('UPLOAD_FOLDER'), max_results=250,
        )
        return jsonify({'ok': True, 'query': query, 'scope': scope, 'count': len(results), 'results': results})
    except DrawingSearchError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception:
        app.logger.exception('Drawing text search failed')
        return jsonify({'error': 'Text search failed. Check server logs for details.'}), 500


@app.route('/api/drawings/search/shape', methods=['POST'])
@login_required
def api_drawings_search_shape():
    from drawing_search import DrawingSearchError, prepare_drawing_targets, search_shape
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        scope = body.get('scope') or 'project'
        drawing_id = body.get('drawing_id')
        template_b64 = body.get('template') or body.get('template_png')
        try:
            threshold = float(body.get('threshold') or 0.82)
        except (TypeError, ValueError):
            threshold = 0.82
        try:
            render_scale = float(body.get('render_scale') or 0) or None
        except (TypeError, ValueError):
            render_scale = None
        try:
            snip_w = float(body.get('snip_w') or 0) or None
            snip_h = float(body.get('snip_h') or 0) or None
        except (TypeError, ValueError):
            snip_w = snip_h = None
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        if not template_b64:
            return jsonify({'error': 'template image required'}), 400
        ids = None
        if scope == 'sheet' and drawing_id is not None:
            try:
                ids = [int(drawing_id)]
            except (TypeError, ValueError):
                return jsonify({'error': 'Invalid drawing_id'}), 400
        targets = prepare_drawing_targets(Drawing, DrawingRevision, ids, int(project_id))
        if scope == 'sheet' and not targets:
            return jsonify({'error': 'Drawing not found'}), 404
        results = search_shape(
            targets,
            template_b64,
            upload_root=app.config.get('UPLOAD_FOLDER'),
            threshold=max(0.65, min(0.98, threshold)),
            max_results=150,
            max_sheets=100 if scope == 'project' else 1,
            render_scale=render_scale,
            snip_w=snip_w,
            snip_h=snip_h,
        )
        return jsonify({'ok': True, 'scope': scope, 'count': len(results), 'results': results})
    except DrawingSearchError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception:
        app.logger.exception('Drawing shape search failed')
        return jsonify({'error': 'Shape search failed. Check server logs for details.'}), 500


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
        active_project=active,
        project_original_contract_amount=fin['original_contract_amount'],
        project_contract_value=fin['contract_value'],
        project_contract_amount=fin['contract_amount'],
        project_contract_amount_source=fin['contract_amount_source'],
        project_sage_job=fin['sage_job'],
    )


@app.route('/forecast')
@login_required
def forecast_page():
    active = get_active_project()
    return render_template('forecast.html', active_project=active)


@app.route('/api/forecast/summary', methods=['GET'])
@login_required
def api_forecast_summary():
    from budget_persistence import get_budget_state
    from pay_app_persistence import get_pay_app_state
    from forecast_persistence import build_forecast_summary

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project = Project.query.get(int(project_id))
    if not project:
        return jsonify({'error': 'project not found'}), 404
    _, budget_state = get_budget_state(BudgetProjectState, int(project_id))
    _, pay_state = get_pay_app_state(PayAppProjectState, int(project_id))
    approved_co_total = _project_approved_change_orders_total(int(project_id))
    return jsonify(build_forecast_summary(project, budget_state, pay_state, approved_co_total))


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
    reconcile_result = None

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
        try:
            from accounting_reconcile import reconcile_project_accounting
            reconcile_result = reconcile_project_accounting(
                c.project_id,
                current_user.id,
                ChangeOrder=ChangeOrder,
                ChangeOrderAllocation=ChangeOrderAllocation,
                Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation,
                BudgetProjectState=BudgetProjectState,
                PayAppProjectState=PayAppProjectState,
                db=db,
            )
            budget_sync = reconcile_result.get('budget_sync_result')
            sov_sync = reconcile_result.get('sync_result')
        except Exception as exc:
            reconcile_result = {'error': str(exc)}

    if action == 'void':
        _sage_commitment_event(c, 'CommitmentVoided', user_id=current_user.id)
        try:
            from accounting_reconcile import reconcile_project_accounting
            reconcile_result = reconcile_project_accounting(
                c.project_id,
                current_user.id,
                ChangeOrder=ChangeOrder,
                ChangeOrderAllocation=ChangeOrderAllocation,
                Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation,
                BudgetProjectState=BudgetProjectState,
                PayAppProjectState=PayAppProjectState,
                db=db,
            )
            budget_sync = reconcile_result.get('budget_sync_result')
            sov_sync = reconcile_result.get('sync_result')
        except Exception as exc:
            reconcile_result = {'error': str(exc)}

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
        try:
            from accounting_reconcile import reconcile_project_accounting
            reconcile_result = reconcile_project_accounting(
                c.project_id,
                current_user.id,
                ChangeOrder=ChangeOrder,
                ChangeOrderAllocation=ChangeOrderAllocation,
                Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation,
                BudgetProjectState=BudgetProjectState,
                PayAppProjectState=PayAppProjectState,
                db=db,
            )
            budget_sync = reconcile_result.get('budget_sync_result') or budget_sync
            sov_sync = reconcile_result.get('sync_result') or sov_sync
        except Exception as exc:
            reconcile_result = {'error': str(exc)}
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
    try:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'commitments', str(commitment_id), saved)
        if os.path.isfile(full_path):
            with open(full_path, 'rb') as fh:
                fb = fh.read()
            _mirror_to_system_folder(
                c.project_id, fb, f'{c.number or "Commitment"} — {file.filename}', file.filename, 'contracts', 'Contract',
                {'commitment_id': c.id},
            )
            _notify_documents_team(
                c.project_id,
                'Commitment attachment filed',
                f'"{file.filename}" was archived to Documents › Contracts.',
                f'/documents?project_id={c.project_id}',
            )
    except Exception:
        pass
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
        project_approved_change_orders_total=fin['approved_change_orders_total'],
        project_current_contract_value=fin['current_contract_value'],
        project_default_retainage_percent=fin['default_retainage_percent'],
        project_sage_job=fin['sage_job'],
    )


@app.route('/api/projects/financial-summary', methods=['GET'])
@login_required
def api_project_financial_summary():
    """Contract amounts from project file + approved change orders."""
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project = Project.query.get(int(project_id))
    if not project:
        return jsonify({'error': 'project not found'}), 404
    fin = _project_financial_context(project)
    return jsonify({
        'project_id': project.id,
        'original_contract_amount': fin['original_contract_amount'],
        'approved_change_orders_total': fin['approved_change_orders_total'],
        'current_contract_value': fin['current_contract_value'],
        'contract_value': fin['contract_value'],
        'contract_amount': fin['contract_amount'],
        'contract_amount_source': fin['contract_amount_source'],
    })


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
    from budget_persistence import get_budget_state as load_state, save_budget_state, reconcile_budget_contract_from_project
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    project_id = int(project_id)
    project = Project.query.get(project_id)
    project_amt = _project_contract_amount(project)
    record, data = load_state(BudgetProjectState, project_id)
    contract_synced = False
    if data is None:
        data = {}
    if project_amt is not None:
        data, contract_synced = reconcile_budget_contract_from_project(data, project_amt)
        if contract_synced:
            record = save_budget_state(BudgetProjectState, db, project_id, data, current_user.id)
    if not record:
        return jsonify({
            'project_id': project_id,
            'data': data if data else None,
            'version': 0,
            'project_contract_amount': project_amt,
            'contract_synced': contract_synced,
        })
    return jsonify({
        'project_id': project_id,
        'data': data,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
        'project_contract_amount': project_amt,
        'contract_synced': contract_synced,
    })


@app.route('/api/budget/state', methods=['PUT'])
@login_required
def api_save_budget_state():
    from budget_persistence import merge_state_patch, save_budget_state as persist_state, get_budget_state as load_state, push_budget_contract_to_project
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
    project_updated = False
    budget_contract = merged.get('budgetContractAmount')
    if budget_contract not in (None, ''):
        project = Project.query.get(project_id)
        if project:
            project_updated = push_budget_contract_to_project(project, budget_contract)
            if project_updated:
                db.session.commit()
    return jsonify({
        'ok': True,
        'project_id': project_id,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
        'project_contract_updated': project_updated,
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


@app.route('/api/accounting/reconcile', methods=['POST'])
@login_required
def api_accounting_reconcile():
    from accounting_reconcile import reconcile_project_accounting
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        result = reconcile_project_accounting(
            int(project_id),
            current_user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=PayAppProjectState,
            db=db,
        )
        try:
            from sage_service import create_and_process_sage_event
            create_and_process_sage_event(
                SageSyncEvent, Project, db, int(project_id),
                'AccountingReconciled',
                message='Budget, SOV, and commitment totals reconciled',
                payload={
                    'actual_cost_applied': result.get('actual_cost_applied'),
                    'commitment_updates': result.get('commitment_updates'),
                    'invoiced_updates': result.get('invoiced_updates'),
                    'budget_line_count': len(result.get('budgetLines') or []),
                },
                user_id=current_user.id,
            )
        except Exception:
            pass
        return jsonify(result)
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/budget/pending-change-orders', methods=['GET'])
@login_required
def api_budget_pending_change_orders():
    from accounting_reconcile import list_pending_budget_items, _collect_alloc_maps
    from budget_persistence import PENDING_CO_STATUSES
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    cos = ChangeOrder.query.filter(
        ChangeOrder.project_id == project_id,
        ChangeOrder.status.in_(list(PENDING_CO_STATUSES)),
    ).order_by(ChangeOrder.created_at.desc()).all()
    commitments = Commitment.query.filter_by(project_id=project_id).order_by(Commitment.created_at.desc()).all()
    co_ids = [c.id for c in cos]
    com_ids = [c.id for c in commitments]
    co_map, com_map = _collect_alloc_maps(ChangeOrderAllocation, CommitmentAllocation, co_ids, com_ids)
    pending_items = list_pending_budget_items(cos, commitments, co_map, com_map)
    return jsonify({
        'pending_items': pending_items,
        'change_orders': [{
            'id': co.id,
            'number': co.number,
            'description': co.description,
            'amount': co.amount,
            'status': co.status,
            'cost_code': co.cost_code,
            'entity_type': 'change_order',
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
    reconcile_result = None
    try:
        from accounting_reconcile import reconcile_project_accounting
        reconcile_result = reconcile_project_accounting(
            project_id,
            current_user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=PayAppProjectState,
            db=db,
        )
    except Exception as exc:
        reconcile_result = {'error': str(exc)}
    return jsonify({
        'ok': True,
        'project_id': project_id,
        'version': record.version,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
        'reconcile_result': reconcile_result,
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
    from co_persistence import get_budget_cost_codes, get_budget_cost_types
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    return jsonify({
        'cost_codes': get_budget_cost_codes(BudgetProjectState, int(project_id)),
        'cost_types': get_budget_cost_types(BudgetProjectState, int(project_id)),
    })


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
    from co_persistence import save_allocations, validate_allocations
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    allocations = body.get('allocations') or []
    try:
        cleaned = validate_allocations(allocations, require_rows=True, require_amount=True)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, cleaned, db)
    if cleaned:
        co.amount = sum(float(a.get('amount') or 0) for a in cleaned)
        if len(cleaned) == 1:
            co.cost_code = cleaned[0].get('cost_code')
    elif body.get('cost_code'):
        co.cost_code = body.get('cost_code')
    db.session.commit()
    return jsonify({'ok': True, 'amount': co.amount})


@app.route('/api/change-orders', methods=['POST'])
@login_required
def api_create_change_order():
    from co_persistence import apply_co_fields, co_to_dict, run_change_order_accounting_sync, save_allocations, validate_allocations
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        description = (body.get('description') or body.get('title') or '').strip()
        if not description:
            return jsonify({'error': 'description required'}), 400
        status = body.get('status') or 'Draft'
        allocations = body.get('allocations') or []
        if status != 'Draft':
            allocations = validate_allocations(allocations, require_rows=True, require_amount=True)
        number = generate_next_number('CO', ChangeOrder)
        co = ChangeOrder(
            project_id=int(project_id),
            number=number,
            description=description,
            status=status,
            date=_parse_change_order_date(body.get('date')),
            ball_in_court_role='Creator',
            created_by_id=current_user.id,
        )
        apply_co_fields(co, body)
        db.session.add(co)
        db.session.flush()
        if allocations:
            save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, allocations, db)
            co.amount = sum(float(a.get('amount') or 0) for a in allocations)
            if len(allocations) == 1:
                co.cost_code = allocations[0].get('cost_code')
        sync_result = None
        budget_sync_result = None
        if status == 'Approved':
            co.approved_by_id = current_user.id
            accounting = run_change_order_accounting_sync(
                co, 'Draft', status, current_user.id,
                ChangeOrder=ChangeOrder,
                ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState,
                ScheduleData=ScheduleData,
                Project=Project,
                BudgetProjectState=BudgetProjectState,
                db=db,
                Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation,
                SageSyncEvent=SageSyncEvent,
            )
            sync_result = accounting.get('sync_result')
            budget_sync_result = accounting.get('budget_sync_result')
        db.session.commit()
        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        return jsonify({
            'ok': True,
            'change_order': co_to_dict(co, allocs),
            'sync_result': sync_result,
            'budget_sync_result': budget_sync_result,
        })
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/change-orders/<int:co_id>', methods=['PUT'])
@login_required
def api_update_change_order(co_id):
    from co_persistence import apply_co_fields, co_to_dict, run_change_order_accounting_sync, save_allocations, validate_allocations
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    old_status = co.status
    sync_result = None
    budget_sync_result = None
    try:
        apply_co_fields(co, body)
        if body.get('allocations') is not None:
            status = body.get('status') or co.status
            allocations = body['allocations']
            if status != 'Draft':
                allocations = validate_allocations(allocations, require_rows=True, require_amount=True)
            save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, allocations, db)
            if allocations:
                co.amount = sum(float(a.get('amount') or 0) for a in allocations)
                if len(allocations) == 1:
                    co.cost_code = allocations[0].get('cost_code')
        new_status = co.status
        if new_status == 'Approved' and old_status != 'Approved':
            co.approved_by_id = current_user.id
        if new_status == 'Approved' or (
            new_status in ('Submitted', 'Under Review', 'Pending Architect', 'Pending Owner')
            and old_status not in ('Submitted', 'Under Review', 'Pending Architect', 'Pending Owner')
        ) or new_status == 'Rejected':
            accounting = run_change_order_accounting_sync(
                co, old_status, new_status, current_user.id,
                ChangeOrder=ChangeOrder,
                ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState,
                ScheduleData=ScheduleData,
                Project=Project,
                BudgetProjectState=BudgetProjectState,
                db=db,
                Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation,
                SageSyncEvent=SageSyncEvent,
                queue_sage_event=(new_status == 'Approved' and old_status != 'Approved'),
            )
            sync_result = accounting.get('sync_result')
            budget_sync_result = accounting.get('budget_sync_result')
        elif new_status == 'Approved' and old_status == 'Approved' and body.get('allocations') is not None:
            accounting = run_change_order_accounting_sync(
                co, old_status, new_status, current_user.id,
                ChangeOrder=ChangeOrder,
                ChangeOrderAllocation=ChangeOrderAllocation,
                PayAppProjectState=PayAppProjectState,
                ScheduleData=ScheduleData,
                Project=Project,
                BudgetProjectState=BudgetProjectState,
                db=db,
                Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation,
                SageSyncEvent=SageSyncEvent,
                queue_sage_event=False,
            )
            sync_result = accounting.get('sync_result')
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({
        'ok': True,
        'change_order': co_to_dict(co, allocs),
        'sync_result': sync_result,
        'budget_sync_result': budget_sync_result,
        'accounting_synced': bool(sync_result or budget_sync_result),
    })


@app.route('/api/change-orders/<int:co_id>', methods=['DELETE'])
@login_required
def api_delete_change_order(co_id):
    from co_persistence import delete_change_order
    co = ChangeOrder.query.get_or_404(co_id)
    force = request.args.get('force') == '1'
    body = request.get_json(silent=True) or {}
    if body.get('force'):
        force = True
    project_id = co.project_id
    try:
        delete_change_order(
            co,
            db,
            ChangeOrderAllocation,
            ChangeOrderRevision,
            PotentialChangeOrder,
            force=force,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc), 'can_force': co.status == 'Approved'}), 400
    reconcile_result = None
    try:
        from accounting_reconcile import reconcile_project_accounting
        reconcile_result = reconcile_project_accounting(
            project_id,
            current_user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=PayAppProjectState,
            db=db,
        )
    except Exception as exc:
        reconcile_result = {'error': str(exc)}
    return jsonify({'ok': True, 'deleted_id': co_id, 'reconcile_result': reconcile_result})


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
            Commitment=Commitment,
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
    from co_persistence import co_workflow_action, notify_ball_in_court, co_to_dict, append_approval_history, run_change_order_accounting_sync
    co = ChangeOrder.query.get_or_404(co_id)
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    comments = (body.get('comments') or '').strip()
    if action == 'reject' and not comments:
        return jsonify({'error': 'Rejection requires a comment.'}), 400
    old_status = co.status
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    alloc_payload = [{
        'cost_code': a.cost_code,
        'cost_type': getattr(a, 'cost_type', None),
        'amount': a.amount,
        'description': getattr(a, 'description', ''),
    } for a in allocs]
    try:
        new_status, final_approved = co_workflow_action(co, action, current_user, User, alloc_payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    append_approval_history(co, action, current_user, comments, old_status, new_status)

    try:
        from case_workflow import ApprovalRequest, decide_approval
        pending = ApprovalRequest.query.filter_by(
            entity_type='ChangeOrder',
            entity_id=str(co.id),
            status='pending',
        ).order_by(ApprovalRequest.created_at.desc()).first()
        if pending and action in ('approve', 'reject'):
            decide_approval(pending.id, action, comments)
    except Exception:
        pass

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
    if action == 'submit' and new_status == 'Submitted':
        accounting = run_change_order_accounting_sync(
            co, old_status, new_status, current_user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            PayAppProjectState=PayAppProjectState,
            ScheduleData=ScheduleData,
            Project=Project,
            BudgetProjectState=BudgetProjectState,
            db=db,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            SageSyncEvent=SageSyncEvent,
            queue_sage_event=False,
        )
        budget_sync_result = accounting.get('budget_sync_result')

    if final_approved:
        co.approved_by_id = current_user.id
        accounting = run_change_order_accounting_sync(
            co, old_status, 'Approved', current_user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            PayAppProjectState=PayAppProjectState,
            ScheduleData=ScheduleData,
            Project=Project,
            BudgetProjectState=BudgetProjectState,
            db=db,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            SageSyncEvent=SageSyncEvent,
        )
        sync_result = accounting.get('sync_result')
        budget_sync_result = accounting.get('budget_sync_result') or budget_sync_result
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
        accounting = run_change_order_accounting_sync(
            co, old_status, 'Rejected', current_user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            PayAppProjectState=PayAppProjectState,
            ScheduleData=ScheduleData,
            Project=Project,
            BudgetProjectState=BudgetProjectState,
            db=db,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            SageSyncEvent=SageSyncEvent,
            queue_sage_event=False,
        )
        budget_sync_result = accounting.get('budget_sync_result') or budget_sync_result

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
    try:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'change_orders', str(co_id), saved)
        if os.path.isfile(full_path):
            with open(full_path, 'rb') as fh:
                fb = fh.read()
            _mirror_to_system_folder(
                co.project_id, fb, f'{co.number or "CO"} — {file.filename}', file.filename, 'contracts', 'Change Order',
                {'change_order_id': co.id},
            )
            _notify_documents_team(
                co.project_id,
                'Change order attachment filed',
                f'"{file.filename}" was archived to Documents › Contracts.',
                f'/documents?project_id={co.project_id}',
            )
    except Exception:
        pass
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
    try:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'change_orders', f'pco_{pco_id}', saved)
        if os.path.isfile(full_path):
            with open(full_path, 'rb') as fh:
                fb = fh.read()
            _mirror_to_system_folder(
                pco.project_id, fb, f'{pco.number or "PCO"} — {file.filename}', file.filename, 'contracts', 'PCO',
                {'pco_id': pco.id},
            )
            _notify_documents_team(
                pco.project_id,
                'PCO attachment filed',
                f'"{file.filename}" was archived to Documents › Contracts.',
                f'/documents?project_id={pco.project_id}',
            )
    except Exception:
        pass
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
    from co_persistence import apply_pco_fields, pco_to_dict, save_allocations, validate_allocations
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    title = (body.get('title') or body.get('description') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    try:
        status = body.get('status') or 'Open'
        allocations = body.get('allocations') or []
        if status not in ('Open', 'Draft'):
            allocations = validate_allocations(allocations, require_rows=True, require_amount=True)
        pco = PotentialChangeOrder(
            project_id=int(project_id),
            number=generate_next_number('PCO', PotentialChangeOrder),
            title=title,
            description=body.get('description') or title,
            status=status,
            ball_in_court_role='Project Manager',
            requested_by=body.get('requested_by') or f'{current_user.first_name} {current_user.last_name}'.strip(),
            created_by_id=current_user.id,
        )
        apply_pco_fields(pco, body)
        db.session.add(pco)
        db.session.flush()
        if allocations:
            save_allocations(PCOAllocation, 'pco_id', pco.id, allocations, db)
            pco.estimated_amount = sum(float(a.get('amount') or 0) for a in allocations)
        db.session.commit()
        allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
        return jsonify({'ok': True, 'pco': pco_to_dict(pco, allocs)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400


@app.route('/api/pcos/<int:pco_id>', methods=['PUT'])
@login_required
def api_update_pco(pco_id):
    from co_persistence import apply_pco_fields, pco_to_dict, save_allocations, validate_allocations
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    body = request.get_json(silent=True) or {}
    try:
        apply_pco_fields(pco, body)
        if body.get('allocations') is not None:
            status = body.get('status') or pco.status
            allocations = body['allocations']
            if status not in ('Open', 'Draft'):
                allocations = validate_allocations(allocations, require_rows=True, require_amount=True)
            save_allocations(PCOAllocation, 'pco_id', pco.id, allocations, db)
            if allocations:
                pco.estimated_amount = sum(float(a.get('amount') or 0) for a in allocations)
        pco.updated_at = datetime.utcnow()
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
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
        try:
            from document_persistence import ensure_document_schema
            ensure_document_schema(db.engine, db)
        except Exception as _doc:
            print('Document schema:', _doc)
        try:
            ensure_project_schema()
        except Exception as _proj:
            print('Project schema:', _proj)
        try:
            _ensure_module_attachment_columns()
        except Exception as _att:
            print('Attachment columns:', _att)
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
        try:
            from document_persistence import ensure_document_schema
            ensure_document_schema(db.engine, db)
        except Exception:
            pass
        try:
            ensure_project_schema()
        except Exception:
            pass

        # Create default admin user if it doesn't exist
        admin = User.query.filter_by(email='admin@casepm.local').first()
        if not admin:
            admin = User(
                first_name='Admin',
                last_name='User',
                email='admin@casepm.local',
                role='Admin',
                status='Active',
                must_change_password=False,
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
            print("=" * 75 + "\n")
        elif admin.must_change_password:
            admin.must_change_password = False
            db.session.commit()

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
    host = os.environ.get('CASEPM_HOST', '127.0.0.1')
    port = int(os.environ.get('CASEPM_PORT', '5000'))
    remote = os.environ.get('CASEPM_REMOTE', '').lower() in ('1', 'true', 'yes')
    debug = os.environ.get('CASEPM_DEBUG', '0' if remote else '1').lower() not in ('0', 'false', 'no')

    from case_server import print_startup_banner
    print_startup_banner(host, port, remote)

    app.run(
        debug=debug,
        host=host,
        port=port,
        threaded=True,
        use_reloader=debug,
    )


# ==================== END OF APPLICATION ====================
