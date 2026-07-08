



# ============================================================
# Case PM - Ultimate Construction Project Management System
# Cleaned & Completed Full Version (vFinal)
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
import json
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'case-pm-ultimate-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///case_pm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB

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
    return {
        'active_project': active,
        'project_name': active.name if active else 'Select Project',
        'all_projects': Project.query.order_by(Project.name).all(),
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


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
        'open_rfis': RFI.query.filter(RFI.status.in_(['Open', 'Awaiting Response'])).count(),
        'overdue_rfis': RFI.query.filter(
            RFI.due_date < datetime.utcnow().date(),
            RFI.status.in_(['Open', 'Awaiting Response'])
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
    return jsonify({
        'project_id': active.id,
        'name': active.name,
        'number': active.number,
        'address': active.address,
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
    'sage_contract_number', 'sage_account_set', 'sage_accounting_method',
    'sage_billings_account', 'sage_wip_account', 'sage_revenue_account',
    'sage_ar_customer_code', 'sage_default_tax_group', 'parent_project_id',
    'project_template', 'notes',
]


def ensure_project_schema():
    """Add new Project columns on existing SQLite databases."""
    from sqlalchemy import inspect, text
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
        project.number = (form.get('number') or '').strip()
    details = {k: (form.get(k) or '').strip() for k in PROJECT_DETAIL_FIELDS}
    project.set_details(details)
    project.updated_at = datetime.utcnow()


@app.route('/projects')
@login_required
def projects_page():
    ensure_project_schema()
    projects = Project.query.order_by(Project.created_at.desc()).all()
    companies = Company.query.order_by(Company.name).all()
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    active_projects = [p for p in projects if p.status == 'Active']
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
        project = Project(
            number=request.form.get('number') or f"PRJ-{next_num:03d}",
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
        flash(f'Error creating project: {str(e)}', 'error')
        return redirect(url_for('projects_page'))


@app.route('/projects/<int:project_id>/update', methods=['POST'])
@login_required
def update_project(project_id):
    ensure_project_schema()
    project = Project.query.get_or_404(project_id)
    try:
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
    rfis = query_for_active_project(RFI).order_by(RFI.created_at.desc()).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('rfis.html', rfis=rfis, projects=projects)


@app.route('/rfis/create', methods=['POST'])
@login_required
def create_rfi():
    try:
        project_id = request.form.get('project_id')
        subject = request.form.get('subject')
        question = request.form.get('question')
        priority = request.form.get('priority', 'Medium')
        due_date = request.form.get('due_date')

        if not subject or not project_id:
            flash('Subject and Project are required.', 'error')
            return redirect_with_project('rfis_page')

        number = generate_next_number('RFI', RFI)

        rfi = RFI(
            project_id=int(project_id),
            number=number,
            subject=subject,
            question=question,
            priority=priority,
            status='Open',
            date=datetime.utcnow().date(),
            due_date=datetime.strptime(due_date, '%Y-%m-%d').date() if due_date else None,
            created_by_id=current_user.id
        )

        db.session.add(rfi)
        db.session.commit()

        flash(f'RFI {number} created successfully!', 'success')
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


# ==================== CHANGE ORDER ROUTES ====================

@app.route('/change-orders')
@login_required
def change_orders_page():
    change_orders = query_for_active_project(ChangeOrder).order_by(ChangeOrder.created_at.desc()).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template('change_orders.html', change_orders=change_orders, projects=projects)


@app.route('/change-orders/create', methods=['POST'])
@login_required
def create_change_order():
    try:
        project_id = request.form.get('project_id')
        description = request.form.get('description')
        amount = request.form.get('amount')
        reason = request.form.get('reason')
        schedule_impact = request.form.get('schedule_impact')

        if not description or not project_id:
            flash('Description and Project are required.', 'error')
            return redirect_with_project('change_orders_page')

        number = generate_next_number('CO', ChangeOrder)

        co = ChangeOrder(
            project_id=int(project_id),
            number=number,
            description=description,
            amount=float(amount) if amount else 0.0,
            reason=reason,
            schedule_impact=schedule_impact,
            status='Pending',
            date=datetime.utcnow().date(),
            created_by_id=current_user.id
        )

        db.session.add(co)
        db.session.commit()

        flash(f'Change Order {number} created successfully!', 'success')
        return redirect_with_project('change_orders_page')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Change Order: {str(e)}', 'error')
        return redirect_with_project('change_orders_page')


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


@app.route('/budget')
@login_required
def budget_page():
    return render_template('budget.html')


@app.route('/commitments')
@login_required
def commitments_page():
    return render_template('commitments.html')


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
    return render_template('pay_applications.html')


@app.route('/program-settings')
@login_required
def program_settings():
    return render_template('program_settings.html')


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
    return render_template('email.html')


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
    ).limit(30).all()
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


# ==================== QUICK STATS API ====================

@app.route('/api/stats')
@login_required
def api_stats():
    stats = get_dashboard_stats()
    return jsonify(stats)




# ==================== FINAL STARTUP & INITIALIZATION ====================

if __name__ == '__main__':
    with app.app_context():
        # Create all database tables
        db.create_all()

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

    # Start the Flask development server
    print("\n" + "=" * 75)
    print("🚀 CASE PM - ULTIMATE VERSION STARTING")
    print("=" * 75)
    print("   Access the application at: http://127.0.0.1:5000")
    print("   Press CTRL+C to stop the server")
    print("=" * 75 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)


# ==================== END OF APPLICATION ====================
