



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
import urllib.parse
from functools import wraps

app = Flask(__name__)


@app.template_filter('usd')
def format_usd_filter(value, cents=True):
    if value in (None, ''):
        return '—'
    try:
        n = float(value)
    except (TypeError, ValueError):
        return '—'
    if cents:
        return f'${n:,.2f}'
    return f'${n:,.0f}'
app.config['SECRET_KEY'] = 'pending-security-init'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///case_pm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 60},
}

from security_platform import (
    apply_security_headers,
    configure_app_security,
    ensure_csrf_token,
    get_pending_2fa_user_id,
    guard_csrf,
    guard_host_header,
    guard_https_redirect,
    is_2fa_verified,
    load_deployment_settings,
    mark_2fa_verified,
    set_pending_2fa_user,
)
from access_control import configure_app_security as _access_control_extras

configure_app_security(app)
_access_control_extras(app)

from db_sqlite import commit_with_retry, register_sqlite_pragmas
register_sqlite_pragmas()


def _disk_build():
    """Git SHA (or env) on disk — changes after git pull even before restart."""
    env = os.environ.get('CASEPM_ASSET_VERSION', '').strip()
    if env:
        return env
    try:
        import subprocess
        root = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return datetime.utcnow().strftime('%Y%m%d%H%M')


app.config['CASEPM_STARTUP_BUILD'] = _disk_build()


def _asset_version():
    """Build id for this running server process (set at startup)."""
    return app.config.get('CASEPM_STARTUP_BUILD') or _disk_build()


def _restart_required():
    """True when git pull updated files but the server was not restarted."""
    running = _asset_version()
    disk = _disk_build()
    return bool(running and disk and running != disk)


@app.context_processor
def inject_asset_version():
    return {
        'asset_v': _asset_version(),
        'disk_build': _disk_build(),
        'restart_required': _restart_required(),
    }


@app.route('/api/version')
def api_version():
    """Public build info — use to verify remote PCs see the restarted server."""
    from version import CASEPM_VERSION
    running = _asset_version()
    disk = _disk_build()
    return jsonify({
        'ok': True,
        'version': CASEPM_VERSION,
        'running_build': running,
        'disk_build': disk,
        'restart_required': running != disk,
        'remote_mode': os.environ.get('CASEPM_REMOTE', '').lower() in ('1', 'true', 'yes'),
    })


@app.template_global()
def static_v(filename):
    return url_for('static', filename=filename) + '?v=' + _asset_version()


@app.after_request
def _html_no_cache(response):
    """HTML pages must not be cached — remote browsers otherwise keep old toolbars/modals."""
    ctype = (response.content_type or '')
    if 'text/html' in ctype:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    return response


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
    'safety_page',
    'login',
    'logout',
    'recovery_login',
    'recovery_enter',
    'force_change_password',
    'verify_2fa',
    'static',
    'favicon',
    'download_casepm_connector',
    'download_casepm_connector_vbs',
    'api_stats',
    'api_current_project',
    'api_portfolio_schedules',
    'developer_console',
})

CURRENT_PROJECT_SESSION_KEY = 'current_project_id'


# ==================== PERMISSION DECORATORS ====================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from developer_tools import is_admin_or_developer
        if not current_user.is_authenticated or not is_admin_or_developer(current_user):
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def developer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from developer_tools import is_developer
        if not current_user.is_authenticated or not is_developer(current_user):
            if (request.path or '').startswith('/api/'):
                return jsonify({'error': 'Developer access only.'}), 403
            flash("Developer access only.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def users_module_required(f):
    """User management — Admin or users module admin permission."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from access_control import users_module_admin
        if not current_user.is_authenticated or not users_module_admin(current_user):
            flash("You do not have permission to manage users.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def _developer_unlock_bypass():
    from developer_tools import developer_unlock_active
    return developer_unlock_active()


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


_user_signature_schema_ready = False
_audit_schema_ready = False

# Page routes enforced by per-user module permissions (non-admin).
MODULE_ROUTE_GUARD = {
    'budget_page': 'budget',
    'forecast_page': 'forecast',
    'pay_applications_page': 'pay_applications',
    'commitments_page': 'commitments',
    'companies_page': 'companies',
    'user_management': 'users',
    'program_settings': 'program_settings',
    'audit_log_page': 'audit_log',
    'audit_log': 'audit_log',
    'developer_console': 'developer',
    'rfis_page': 'rfis',
    'submittals_page': 'submittals',
    'change_orders_page': 'change_orders',
    'daily_log': 'daily_log',
    'weekly_report': 'weekly_report',
    'punch_list_page': 'punch_list',
    'safety_page': 'safety',
    'photos_page': 'photos',
    'inspections_page': 'inspections',
    'schedule_page': 'schedule',
    'documents_page': 'documents',
    'drawings_page': 'drawings',
    'deliveries_page': 'deliveries',
    'meeting_minutes_page': 'meeting_minutes',
    'email_page': 'email',
    'projects_page': 'projects',
    'project_detail': 'projects',
}


@app.before_request
def _migrate_user_signature_schema():
    """Run before login loads User — new signature columns must exist first."""
    global _user_signature_schema_ready
    if _user_signature_schema_ready:
        return
    try:
        _bootstrap_user_schema(db)
        _user_signature_schema_ready = True
    except Exception as exc:
        print(f'User schema migration warning: {exc}')


@app.before_request
def _platform_security_guards():
    blocked = guard_https_redirect()
    if blocked is not None:
        return blocked
    blocked = guard_host_header()
    if blocked is not None:
        return blocked
    blocked = guard_csrf(request.endpoint)
    if blocked is not None:
        try:
            write_audit('CSRF_BLOCKED', request.path, module='security', category='other')
            db.session.commit()
        except Exception:
            pass
        return blocked


@app.after_request
def _platform_security_headers(response):
    return apply_security_headers(response)


@app.before_request
def _require_2fa_verification():
    if not current_user.is_authenticated:
        return
    ep = request.endpoint or ''
    if ep in ('verify_2fa', 'logout', 'login', 'recovery_login', 'recovery_enter', 'static', 'favicon'):
        return
    try:
        from totp_auth import user_needs_2fa, user_has_totp_configured
        if user_needs_2fa(current_user) and not is_2fa_verified():
            if not user_has_totp_configured(current_user) and ep not in ('force_change_password',):
                flash('Set up two-factor authentication to continue.', 'warning')
                return redirect(url_for('verify_2fa', setup=1))
            return redirect(url_for('verify_2fa'))
    except Exception:
        return


@app.before_request
def _session_idle_timeout():
    if not current_user.is_authenticated:
        return
    try:
        from access_control import enforce_session_idle_timeout
        from flask_login import logout_user
        should_logout, _mins = enforce_session_idle_timeout(current_user, request.endpoint)
        if should_logout:
            logout_user()
            flash('Your session expired due to inactivity. Please sign in again.', 'warning')
            return redirect(url_for('login'))
    except Exception:
        return


@app.before_request
def _guard_api_module_access():
    if not current_user.is_authenticated:
        return
    try:
        from access_control import guard_api_request
        blocked = guard_api_request(current_user)
        if blocked is not None:
            return blocked
    except Exception:
        return


@app.before_request
def _guard_module_route_access():
    if not current_user.is_authenticated:
        return
    if getattr(current_user, 'role', None) == 'Admin':
        return
    ep = request.endpoint or ''
    module_key = MODULE_ROUTE_GUARD.get(ep)
    if not module_key:
        return
    try:
        from developer_tools import is_developer
        if is_developer(current_user):
            return
    except Exception:
        pass
    try:
        from access_control import FINANCIAL_MODULES, user_global_flags
        from case_workflow import user_has_module_access
        flags = user_global_flags(current_user)
        if flags.get('hide_financials') and module_key in FINANCIAL_MODULES:
            flash('Financial modules are not available for your account.', 'error')
            return redirect(url_for('dashboard'))
        if flags.get('client_portal_only') and module_key in (
            'budget', 'forecast', 'commitments', 'users', 'program_settings', 'audit_log',
            'companies', 'safety', 'daily_log', 'punch_list', 'inspections', 'deliveries',
            'meeting_minutes', 'weekly_report', 'photos',
        ):
            flash('Client portal access only — module not available.', 'error')
            return redirect(url_for('dashboard'))
        try:
            from portal_sub_access import is_sub_vendor_portal_user, sub_vendor_module_allowed, portal_home_redirect
            route_module = module_key
            if ep == 'email_page':
                has_email = user_has_module_access(current_user, 'email', 'view')
                has_internal = user_has_module_access(current_user, 'internal_messages', 'view')
                if not has_email and not has_internal:
                    flash('You do not have permission to access internal messages.', 'error')
                    return redirect(url_for('dashboard'))
                route_module = 'email' if has_email else 'internal_messages'
            if is_sub_vendor_portal_user(current_user) and not sub_vendor_module_allowed(current_user, route_module):
                flash('This module is not available for subcontractor portal users.', 'error')
                return portal_home_redirect(current_user)
        except Exception:
            pass
        if ep == 'email_page':
            return
        if not user_has_module_access(current_user, module_key, 'view'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'You do not have permission to access this module.'}), 403
            flash(f'You do not have permission to access {module_key.replace("_", " ").title()}.', 'error')
            return redirect(url_for('dashboard'))
    except Exception:
        return


@app.before_request
def _migrate_audit_log_schema():
    global _audit_schema_ready
    if _audit_schema_ready:
        return
    try:
        from audit_log_persistence import ensure_audit_log_schema
        ensure_audit_log_schema(db)
        _audit_schema_ready = True
    except Exception:
        pass


def write_audit(action, detail='', module='app', commit=False, **kwargs):
    """Server-side audit helper — safe to call from any route."""
    try:
        from audit_log_persistence import record_audit, ensure_audit_log_schema
        ensure_audit_log_schema(db)
        user = current_user if current_user.is_authenticated else None
        project = get_active_project() if user else None
        fields = {
            'action': action,
            'detail': detail,
            'module': module,
            'project_id': kwargs.get('project_id') or (project.id if project else None),
            'project_name': kwargs.get('project_name') or (project.name if project else ''),
            **kwargs,
        }
        record_audit(db, AuditLog, user, **fields)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    except Exception:
        db.session.rollback()


def _alter_user_columns(db, additions):
    """Add missing user columns — inline fallback when persistence modules are unavailable."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('user')}
    for col, typedef in additions.items():
        if col not in existing:
            db.session.execute(text(f'ALTER TABLE user ADD COLUMN {col} {typedef}'))
    db.session.commit()


def _bootstrap_user_schema(db):
    """Ensure user table columns exist before Flask-Login loads User."""
    try:
        from user_signature_persistence import ensure_user_signature_schema
        ensure_user_signature_schema(db)
    except ImportError:
        _alter_user_columns(db, {
            'signature_path': 'VARCHAR(300)',
            'signature_hash': 'VARCHAR(64)',
            'signature_legal_name': 'VARCHAR(150)',
            'signature_initials': 'VARCHAR(20)',
            'signature_set_at': 'DATETIME',
            'signature_audit_json': 'TEXT',
            'certificate_meta_json': 'TEXT',
        })
    except Exception as exc:
        print(f'User signature schema warning: {exc}')
    try:
        from user_profile_persistence import ensure_user_profile_schema
        ensure_user_profile_schema(db)
    except ImportError:
        _alter_user_columns(db, {
            'job_title': 'VARCHAR(120)',
            'address': 'VARCHAR(300)',
            'profile_image_path': 'VARCHAR(300)',
        })
    except Exception as exc:
        print(f'User profile schema warning: {exc}')
    try:
        from user_management_service import ensure_user_admin_schema
        ensure_user_admin_schema(db)
    except Exception as exc:
        print(f'User admin schema warning: {exc}')
    try:
        from totp_auth import ensure_totp_schema
        ensure_totp_schema(db)
    except Exception as exc:
        print(f'TOTP schema warning: {exc}')
    try:
        from email_mailbox_persistence import ensure_email_mailbox_schema
        ensure_email_mailbox_schema(db)
    except Exception as exc:
        print(f'Email mailbox schema warning: {exc}')
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    job_title = db.Column(db.String(120))
    address = db.Column(db.String(300))
    profile_image_path = db.Column(db.String(300))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='Viewer')
    company = db.Column(db.String(120))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
    permissions_json = db.Column(db.Text)
    status = db.Column(db.String(20), default='Active')
    must_change_password = db.Column(db.Boolean, default=True)
    require_2fa = db.Column(db.Boolean, default=False)
    totp_secret = db.Column(db.String(64))
    totp_enabled = db.Column(db.Boolean, default=False)
    signature_path = db.Column(db.String(300))
    signature_hash = db.Column(db.String(64))
    signature_legal_name = db.Column(db.String(150))
    signature_initials = db.Column(db.String(20))
    signature_set_at = db.Column(db.DateTime)
    signature_audit_json = db.Column(db.Text)
    certificate_meta_json = db.Column(db.Text)
    stamp_path = db.Column(db.String(300))
    stamp_hash = db.Column(db.String(64))
    stamp_set_at = db.Column(db.DateTime)
    user_stamps_json = db.Column(db.Text)
    phones_json = db.Column(db.Text)
    notes = db.Column(db.Text)
    access_enabled = db.Column(db.Boolean, default=True)
    department = db.Column(db.String(120))
    employee_id = db.Column(db.String(80))
    license_tier = db.Column(db.String(40))
    timezone = db.Column(db.String(80))
    emergency_contact_json = db.Column(db.Text)
    certifications_json = db.Column(db.Text)
    locale = db.Column(db.String(20), default='en-US')
    office_location = db.Column(db.String(120))
    cost_center = db.Column(db.String(80))
    hire_date = db.Column(db.String(20))
    reports_to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    default_project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    bio = db.Column(db.Text)
    linkedin_url = db.Column(db.String(300))
    work_phone_ext = db.Column(db.String(20))
    date_format_pref = db.Column(db.String(10), default='MDY')
    notification_prefs_json = db.Column(db.Text)
    integrations_json = db.Column(db.Text)
    hr_documents_json = db.Column(db.Text)
    invite_sent_at = db.Column(db.DateTime)
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
        if self.role in ('Admin', 'Developer'):
            return True
        try:
            from case_workflow import user_has_module_access, user_can_approve, _resolve_module_key
            key = _resolve_module_key(permission)
            if user_has_module_access(self, key, 'view'):
                return True
            return user_can_approve(self, permission)
        except Exception:
            return False

    def __repr__(self):
        return f'<User {self.email}>'


class UserEmailMailbox(db.Model):
    __tablename__ = 'user_email_mailbox'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    messages_json = db.Column(db.Text)
    meta_json = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailMailboxAccess(db.Model):
    __tablename__ = 'email_mailbox_access'
    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    grantee_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    can_send = db.Column(db.Boolean, default=False)
    granted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime)
    notes = db.Column(db.String(300))


class UserEmailConnection(db.Model):
    __tablename__ = 'user_email_connection'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    provider = db.Column(db.String(40), default='microsoft')
    email_address = db.Column(db.String(255))
    display_name = db.Column(db.String(255))
    encrypted_tokens = db.Column(db.Text)
    scopes = db.Column(db.Text)
    status = db.Column(db.String(40), default='connected')
    connected_at = db.Column(db.DateTime)
    last_sync_at = db.Column(db.DateTime)
    last_error = db.Column(db.String(500))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as exc:
        err = str(exc).lower()
        if 'no such column' in err or 'has no column' in err:
            try:
                _bootstrap_user_schema(db)
                db.session.rollback()
                return User.query.get(int(user_id))
            except Exception:
                db.session.rollback()
        raise


# ==================== DATABASE MODELS ====================

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(200), nullable=False)
    client = db.Column(db.String(150))
    client_company_id = db.Column(db.Integer, db.ForeignKey('company.id'))
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

    def address_display(self):
        """Full street + city/state/zip for list views."""
        parts = []
        if self.address:
            parts.append(self.address.strip())
        city_state = ', '.join(p for p in [self.city, self.state] if p)
        if self.zip_code:
            city_state = f'{city_state} {self.zip_code}'.strip() if city_state else self.zip_code.strip()
        if city_state:
            parts.append(city_state)
        return ', '.join(parts)

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
        from project_team_persistence import migrate_legacy_team_contacts, primary_project_manager_name
        d = self.get_details()
        team_contacts = migrate_legacy_team_contacts(d)
        return {
            'id': self.id,
            'number': self.number or '',
            'name': self.name or '',
            'client': self.client or '',
            'client_company_id': self.client_company_id,
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
            'team_contacts': team_contacts,
            'address_display': self.address_display(),
            **d,
        }


def get_current_project_id():
    """Resolve the active project id from URL, session, or first accessible project."""
    if not current_user.is_authenticated:
        return None

    project_id = request.args.get('project_id', type=int)
    if project_id:
        from project_access import user_can_access_project
        if Project.query.get(project_id) and user_can_access_project(current_user, project_id, Project):
            session[CURRENT_PROJECT_SESSION_KEY] = project_id
            return project_id
        return None

    stored = session.get(CURRENT_PROJECT_SESSION_KEY)
    if stored:
        try:
            stored_id = int(stored)
            from project_access import user_can_access_project
            if Project.query.get(stored_id) and user_can_access_project(current_user, stored_id, Project):
                return stored_id
        except (TypeError, ValueError):
            pass

    from project_access import filter_projects_for_user
    first = filter_projects_for_user(current_user, Project.query.order_by(Project.name).all(), Project)
    if first:
        session[CURRENT_PROJECT_SESSION_KEY] = first[0].id
        return first[0].id
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
    if not getattr(current_user, 'is_authenticated', False):
        return {'current_user_profile': {}}
    portal = {}
    try:
        from case_workflow import get_role_permissions, user_portal_type, is_sub_user, is_architect_user
        from portal_sub_access import is_sub_vendor_portal_user
        portal = {
            'portal_type': user_portal_type(current_user),
            'is_sub_portal': is_sub_user(current_user),
            'is_architect_portal': is_architect_user(current_user),
            'is_sub_vendor_portal': is_sub_vendor_portal_user(current_user),
            'role_permissions': get_role_permissions(current_user),
        }
    except Exception:
        portal = {'portal_type': 'staff', 'is_sub_portal': False, 'is_architect_portal': False, 'is_sub_vendor_portal': False}
    company_info = {}
    company_logo_url = ''
    try:
        from program_settings_persistence import load_company_info
        company_info = load_company_info() or {}
        company_logo_url = (company_info.get('logo_data_url') or '').strip()
    except Exception:
        pass
    profile = {}
    if current_user.is_authenticated:
        try:
            from user_profile_persistence import ensure_user_profile_schema, serialize_profile
            ensure_user_profile_schema(db)
            profile = serialize_profile(current_user)
        except Exception:
            profile = {
                'id': current_user.id,
                'first_name': current_user.first_name,
                'last_name': current_user.last_name,
                'full_name': current_user.full_name,
                'email': current_user.email,
                'role': current_user.role,
                'company': current_user.company or '',
                'phone': current_user.phone or '',
                'require_2fa': bool(getattr(current_user, 'require_2fa', False)),
            }
    from project_access import filter_projects_for_user
    sub_vendor_company_linked = True
    try:
        from portal_sub_access import (
            is_sub_vendor_portal_user,
            resolve_sub_vendor_company,
            ensure_sub_vendor_project_memberships,
            user_has_linked_vendor_company,
        )
        if is_sub_vendor_portal_user(current_user):
            cid, _, _ = resolve_sub_vendor_company(current_user, Company, db, persist_link=True)
            sub_vendor_company_linked = user_has_linked_vendor_company(
                current_user, Company, db, persist_link=False,
            ) or cid is not None or bool((getattr(current_user, 'company', None) or '').strip())
            ensure_sub_vendor_project_memberships(current_user, db)
    except Exception:
        sub_vendor_company_linked = True
    all_projects = filter_projects_for_user(
        current_user,
        Project.query.order_by(Project.name).all(),
        Project,
    )
    active = get_active_project()
    csrf_token = ''
    try:
        from security_platform import ensure_csrf_token
        csrf_token = ensure_csrf_token()
    except Exception:
        pass
    ep = request.endpoint or ''
    path = request.path or ''
    page_requires_active_project = bool(
        active is None
        and ep
        and ep not in PROJECT_AGNOSTIC_ENDPOINTS
        and not path.startswith('/api/')
        and not path.startswith('/static/')
    )
    return {
        'active_project': active,
        'project_name': active.name if active else 'Select Project',
        'all_projects': all_projects,
        'company_logo_url': company_logo_url,
        'company_info': company_info,
        'current_user_profile': profile,
        'csrf_token': csrf_token,
        'sub_vendor_company_linked': sub_vendor_company_linked,
        'page_requires_active_project': page_requires_active_project,
        **portal,
    }


@app.context_processor
def inject_developer_flag():
    from audit_log_persistence import ENDPOINT_TO_MODULE
    ep = request.endpoint or ''
    page_module = ENDPOINT_TO_MODULE.get(ep, 'app')
    if not getattr(current_user, 'is_authenticated', False):
        return {'is_developer': False, 'developer_unlock_mode': False, 'page_module': page_module, 'is_admin_user': False, 'can_access_module': lambda m, min_access='view': False, 'allowed_modules': {}, 'module_access_levels': {}, 'user_security_flags': {'hide_financials': False, 'client_portal_only': False}, 'security_settings': {'session_timeout_minutes': 60, 'warn_before_logout_minutes': 5}}
    try:
        from developer_tools import is_developer, developer_unlock_active
        dev = is_developer(current_user)
        unlock = developer_unlock_active(current_user) if dev else False
    except Exception:
        dev = False
        unlock = False
    is_admin = getattr(current_user, 'role', None) == 'Admin'
    is_privileged = is_admin or dev
    flags = {'hide_financials': False, 'client_portal_only': False}
    security_settings = {'session_timeout_minutes': 60, 'warn_before_logout_minutes': 5}
    try:
        from program_settings_persistence import load_security_settings
        security_settings = load_security_settings()
    except Exception:
        pass
    try:
        from access_control import FINANCIAL_MODULES, user_global_flags
        from case_workflow import user_has_module_access, user_module_perms
        from permissions_catalog import all_module_keys
        flags = user_global_flags(current_user)
        def can_access_module(module_key, min_access='view'):
            if is_privileged:
                return True
            if flags.get('hide_financials') and module_key in FINANCIAL_MODULES:
                return False
            return user_has_module_access(current_user, module_key, min_access)
        all_keys = all_module_keys()
        allowed_modules = (
            {k: True for k in all_keys}
            if is_privileged else
            {k: can_access_module(k, 'view') for k in all_keys}
        )
        module_access_levels = (
            {k: 'admin' for k in all_keys}
            if is_privileged else
            {k: user_module_perms(current_user, k).get('access', 'none') for k in all_keys}
        )
    except Exception:
        def can_access_module(module_key, min_access='view'):
            return True
        allowed_modules = {}
        module_access_levels = {}
    messaging_internal_only = False
    try:
        from access_control import user_email_internal_only, user_can_external_email, user_can_internal_messages
        messaging_internal_only = user_email_internal_only(current_user)
        messaging_nav_visible = user_can_internal_messages(current_user) or user_can_external_email(current_user)
    except Exception:
        messaging_nav_visible = True
    return {
        'is_developer': dev,
        'developer_unlock_mode': unlock,
        'page_module': page_module,
        'is_admin_user': is_privileged,
        'can_access_module': can_access_module,
        'allowed_modules': allowed_modules,
        'module_access_levels': module_access_levels,
        'user_security_flags': flags,
        'security_settings': security_settings,
        'messaging_internal_only': messaging_internal_only,
        'messaging_nav_visible': messaging_nav_visible,
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
    cost_impact_label = db.Column(db.String(50))
    schedule_impact_days = db.Column(db.Integer, default=0)
    schedule_impact_label = db.Column(db.String(50))
    is_private = db.Column(db.Integer, default=0)
    attachments_json = db.Column(db.Text)
    responses_json = db.Column(db.Text)
    comments_json = db.Column(db.Text)
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
    number = db.Column(db.String(30), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('project_id', 'number', name='uq_change_order_project_number'),
    )
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
    approval_history_json = db.Column(db.Text)
    approval_signatures_json = db.Column(db.Text)
    executed_locked = db.Column(db.Boolean, default=False)
    linked_owner_co_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=True)
    sub_co_kind = db.Column(db.String(40))
    auto_generated = db.Column(db.Boolean, default=False)
    change_event_id = db.Column(db.Integer, nullable=True)
    source_rfq_id = db.Column(db.Integer, nullable=True)
    linked_cor_id = db.Column(db.Integer, nullable=True)
    linked_drawing_revision = db.Column(db.String(80))
    source_cpco_id = db.Column(db.Integer, nullable=True)
    billed_amount = db.Column(db.Float, default=0)
    billing_variance = db.Column(db.Float, default=0)


class ChangeOrderAllocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    change_order_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    cost_type = db.Column(db.String(80))
    amount = db.Column(db.Float, default=0)
    sov_line_legacy_id = db.Column(db.String(64))
    description = db.Column(db.String(200))
    sov_line_id = db.Column(db.String(64))
    tax_group = db.Column(db.String(40))
    retainage_percent = db.Column(db.Float)


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
    change_event_id = db.Column(db.Integer, nullable=True)
    contract_type = db.Column(db.String(40), default='Owner')
    source_rfq_id = db.Column(db.Integer, nullable=True)
    linked_cor_id = db.Column(db.Integer, nullable=True)
    linked_drawing_revision = db.Column(db.String(80))
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
    sov_line_id = db.Column(db.String(64))
    tax_group = db.Column(db.String(40))
    sov_line_id = db.Column(db.String(64))
    tax_group = db.Column(db.String(40))


class ChangeEvent(db.Model):
    __tablename__ = 'change_event'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default='Open')
    reason = db.Column(db.String(200))
    priority = db.Column(db.String(20), default='Medium')
    schedule_impact_days = db.Column(db.Integer, default=0)
    rom_amount = db.Column(db.Float, default=0)
    linked_rfi_id = db.Column(db.Integer, nullable=True)
    drawing_revision = db.Column(db.String(80))
    drawing_sheet_id = db.Column(db.String(80))
    contingency_release_amount = db.Column(db.Float, default=0)
    ball_in_court_role = db.Column(db.String(80))
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubcontractorRFQ(db.Model):
    __tablename__ = 'subcontractor_rfq'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    change_event_id = db.Column(db.Integer, db.ForeignKey('change_event.id'), nullable=True)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default='Draft')
    company_name = db.Column(db.String(200))
    company_id = db.Column(db.String(64))
    linked_commitment_ref = db.Column(db.String(80))
    due_date = db.Column(db.Date)
    quoted_amount = db.Column(db.Float, default=0)
    quoted_at = db.Column(db.DateTime)
    quoted_by = db.Column(db.String(150))
    quote_notes = db.Column(db.Text)
    linked_pco_id = db.Column(db.Integer, nullable=True)
    linked_cpco_id = db.Column(db.Integer, nullable=True)
    linked_sco_id = db.Column(db.Integer, nullable=True)
    ball_in_court_role = db.Column(db.String(80))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RFQAllocation(db.Model):
    __tablename__ = 'rfq_allocation'
    id = db.Column(db.Integer, primary_key=True)
    rfq_id = db.Column(db.Integer, db.ForeignKey('subcontractor_rfq.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    cost_type = db.Column(db.String(80))
    amount = db.Column(db.Float, default=0)
    quoted_amount = db.Column(db.Float, default=0)
    description = db.Column(db.String(200))
    sov_line_id = db.Column(db.String(64))
    tax_group = db.Column(db.String(40))


class ChangeOrderRequest(db.Model):
    __tablename__ = 'change_order_request'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    change_event_id = db.Column(db.Integer, db.ForeignKey('change_event.id'), nullable=True)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default='Draft')
    reason = db.Column(db.String(200))
    priority = db.Column(db.String(20), default='Medium')
    schedule_impact_days = db.Column(db.Integer, default=0)
    linked_pco_id = db.Column(db.Integer, nullable=True)
    change_order_id = db.Column(db.Integer, nullable=True)
    drawing_revision = db.Column(db.String(80))
    ball_in_court_role = db.Column(db.String(80))
    approval_stage = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CORAllocation(db.Model):
    __tablename__ = 'cor_allocation'
    id = db.Column(db.Integer, primary_key=True)
    cor_id = db.Column(db.Integer, db.ForeignKey('change_order_request.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    cost_type = db.Column(db.String(80))
    amount = db.Column(db.Float, default=0)
    description = db.Column(db.String(200))
    sov_line_id = db.Column(db.String(64))
    tax_group = db.Column(db.String(40))


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


class Estimate(db.Model):
    __tablename__ = 'estimate'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default='Draft')
    estimate_type = db.Column(db.String(40), default='Hard Bid')
    bid_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    contingency_pct = db.Column(db.Float, default=5.0)
    overhead_pct = db.Column(db.Float, default=10.0)
    profit_pct = db.Column(db.Float, default=10.0)
    tax_pct = db.Column(db.Float, default=0.0)
    direct_cost_total = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)
    awarded_at = db.Column(db.DateTime)
    pushed_to_budget_at = db.Column(db.DateTime)
    pushed_to_budget_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assumptions_json = db.Column(db.Text)
    attachments_json = db.Column(db.Text)
    settings_json = db.Column(db.Text)
    rom_amount = db.Column(db.Float, default=0)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BidPackage(db.Model):
    __tablename__ = 'bid_package'
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    spec_section = db.Column(db.String(30))
    division = db.Column(db.String(20))
    description = db.Column(db.Text)
    scope_notes = db.Column(db.Text)
    status = db.Column(db.String(30), default='Draft')
    due_date = db.Column(db.Date)
    awarded_invitation_id = db.Column(db.Integer, nullable=True)
    drawing_refs_json = db.Column(db.Text)
    spec_refs_json = db.Column(db.Text)
    attachments_json = db.Column(db.Text)
    email_template_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EstimateLine(db.Model):
    __tablename__ = 'estimate_line'
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    bid_package_id = db.Column(db.Integer, db.ForeignKey('bid_package.id'), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    cost_code = db.Column(db.String(30))
    division = db.Column(db.String(20))
    spec_section = db.Column(db.String(30))
    description = db.Column(db.String(500))
    cost_type = db.Column(db.String(80), default='Subcontract')
    unit = db.Column(db.String(30), default='EA')
    quantity = db.Column(db.Float, default=0)
    unit_cost = db.Column(db.Float, default=0)
    extended_cost = db.Column(db.Float, default=0)
    source = db.Column(db.String(40), default='manual')
    source_ref = db.Column(db.String(120))
    notes = db.Column(db.Text)
    line_kind = db.Column(db.String(30), default='base')
    alternate_key = db.Column(db.String(40))
    assembly_id = db.Column(db.Integer, nullable=True)
    markup_id = db.Column(db.Integer, nullable=True)
    group_key = db.Column(db.String(80))
    meta_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BidInvitation(db.Model):
    __tablename__ = 'bid_invitation'
    id = db.Column(db.Integer, primary_key=True)
    bid_package_id = db.Column(db.Integer, db.ForeignKey('bid_package.id'), nullable=False)
    company_id = db.Column(db.String(64))
    company_name = db.Column(db.String(200))
    contact_email = db.Column(db.String(200))
    contact_name = db.Column(db.String(150))
    status = db.Column(db.String(30), default='Draft')
    sent_at = db.Column(db.DateTime)
    responded_at = db.Column(db.DateTime)
    quote_amount = db.Column(db.Float, default=0)
    quote_notes = db.Column(db.Text)
    decline_reason = db.Column(db.Text)
    qualification_json = db.Column(db.Text)
    scope_gaps_json = db.Column(db.Text)
    reminder_sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BidQuoteLine(db.Model):
    __tablename__ = 'bid_quote_line'
    id = db.Column(db.Integer, primary_key=True)
    invitation_id = db.Column(db.Integer, db.ForeignKey('bid_invitation.id'), nullable=False)
    cost_code = db.Column(db.String(30))
    description = db.Column(db.String(500))
    amount = db.Column(db.Float, default=0)
    quantity = db.Column(db.Float, default=0)
    unit = db.Column(db.String(30))
    unit_cost = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)


class EstimateAssembly(db.Model):
    __tablename__ = 'estimate_assembly'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    trade = db.Column(db.String(80))
    spec_section = db.Column(db.String(30))
    unit = db.Column(db.String(30), default='EA')
    unit_cost = db.Column(db.Float, default=0)
    components_json = db.Column(db.Text)
    source = db.Column(db.String(40), default='library')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EstimateSnapshot(db.Model):
    __tablename__ = 'estimate_snapshot'
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    label = db.Column(db.String(120))
    data_json = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EstimateAlternate(db.Model):
    __tablename__ = 'estimate_alternate'
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    alt_key = db.Column(db.String(40))
    label = db.Column(db.String(200))
    include_in_base = db.Column(db.Boolean, default=False)
    amount = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)


class EstimateCostHistory(db.Model):
    __tablename__ = 'estimate_cost_history'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    cost_code = db.Column(db.String(30))
    trade = db.Column(db.String(80))
    unit = db.Column(db.String(30))
    unit_cost = db.Column(db.Float, default=0)
    description = db.Column(db.String(300))
    source_project_name = db.Column(db.String(200))
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)


class EstimateBudgetMapping(db.Model):
    __tablename__ = 'estimate_budget_mapping'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    spec_section = db.Column(db.String(30))
    cost_code = db.Column(db.String(30))
    cost_type = db.Column(db.String(80), default='Subcontract')


class BidPackageAddendum(db.Model):
    __tablename__ = 'bid_package_addendum'
    id = db.Column(db.Integer, primary_key=True)
    bid_package_id = db.Column(db.Integer, db.ForeignKey('bid_package.id'), nullable=False)
    number = db.Column(db.String(30))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    require_rebid = db.Column(db.Boolean, default=False)
    document_ids_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BidLevelingNote(db.Model):
    __tablename__ = 'bid_leveling_note'
    id = db.Column(db.Integer, primary_key=True)
    bid_package_id = db.Column(db.Integer, db.ForeignKey('bid_package.id'), nullable=False)
    invitation_id = db.Column(db.Integer, db.ForeignKey('bid_invitation.id'), nullable=True)
    note_type = db.Column(db.String(40), default='scope_gap')
    text = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    accounting_status = db.Column(db.String(30), default='pending_review')
    accounting_reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    accounting_reviewed_at = db.Column(db.DateTime, nullable=True)
    accounting_notes = db.Column(db.Text)


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
    comments_json = db.Column(db.Text)
    attachments_json = db.Column(db.Text)
    assigned_company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
    assigned_company_name = db.Column(db.String(200))
    assigned_contact_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_contact_name = db.Column(db.String(150))
    assigned_contact_email = db.Column(db.String(200))
    details_json = db.Column(db.Text)
    updated_at = db.Column(db.DateTime)
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
    report_date = db.Column(db.Date)
    attachments_json = db.Column(db.Text)
    details_json = db.Column(db.Text)


class SafetyCertification(db.Model):
    """Personnel OSHA / safety training records (OSHA 10/30, First Aid, CPR, etc.)."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    person_name = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150))
    trade = db.Column(db.String(80))
    cert_type = db.Column(db.String(120), nullable=False)  # OSHA 10, OSHA 30, First Aid, CPR, etc.
    issuer = db.Column(db.String(150))
    card_number = db.Column(db.String(80))
    issued_date = db.Column(db.Date)
    expiration_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    attachments_json = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SafetyTrainingEvent(db.Model):
    """Scheduled training, renewal reminders, and calendar events for certifications."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    cert_id = db.Column(db.Integer, db.ForeignKey('safety_certification.id'), nullable=True)
    person_name = db.Column(db.String(150), nullable=False)
    company = db.Column(db.String(150))
    cert_type = db.Column(db.String(120))
    event_type = db.Column(db.String(40), default='scheduled_training')  # scheduled_training, renewal_reminder
    event_date = db.Column(db.Date, nullable=False)
    training_url = db.Column(db.String(500))
    training_provider = db.Column(db.String(200))
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), default='Scheduled')  # Scheduled, Completed, Cancelled, Skipped
    notify_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    internal_task_sent = db.Column(db.Boolean, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
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


class Delivery(db.Model):
    """Scheduled material/equipment delivery — syncs to the Schedule as a line item."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    delivery_number = db.Column(db.String(30))
    supplier = db.Column(db.String(200))
    description = db.Column(db.Text, nullable=False)
    delivery_date = db.Column(db.Date, nullable=False)
    time_window = db.Column(db.String(60))       # e.g. "8:00 AM - 10:00 AM"
    duration_days = db.Column(db.Integer, default=1)
    status = db.Column(db.String(30), default='Scheduled')
    location = db.Column(db.String(150))
    quantity = db.Column(db.String(80))
    po_number = db.Column(db.String(80))
    carrier = db.Column(db.String(150))
    responsible = db.Column(db.String(120))
    received_by = db.Column(db.String(120))
    notes = db.Column(db.Text)
    schedule_task_id = db.Column(db.String(60))   # id of the synced task in ScheduleData payload
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PermitInspectionItem(db.Model):
    """Permit or inspection event — syncs to Schedule; tracks Florida AHJ workflow."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    item_number = db.Column(db.String(30))
    record_kind = db.Column(db.String(20), default='inspection')  # permit | inspection
    trade = db.Column(db.String(40), default='building')
    inspection_phase = db.Column(db.String(60))
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    fbc_reference = db.Column(db.String(120))
    permit_number = db.Column(db.String(80))
    parent_id = db.Column(db.Integer, db.ForeignKey('permit_inspection_item.id'))
    jurisdiction_level = db.Column(db.String(40))
    jurisdiction_name = db.Column(db.String(150))
    authority_name = db.Column(db.String(200))
    authority_phone = db.Column(db.String(60))
    authority_url = db.Column(db.String(300))
    scheduled_date = db.Column(db.Date)
    scheduled_time = db.Column(db.String(30))
    duration_days = db.Column(db.Integer, default=1)
    status = db.Column(db.String(40), default='Not Started')
    inspector = db.Column(db.String(120))
    location = db.Column(db.String(150))
    result_notes = db.Column(db.Text)
    correction_notes = db.Column(db.Text)
    schedule_task_id = db.Column(db.String(60))
    catalog_source = db.Column(db.String(40))
    details_json = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MeetingMinute(db.Model):
    """Project meeting record — voice transcript, recording, action items, schedule sync."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    meeting_number = db.Column(db.String(30))
    meeting_date = db.Column(db.Date)
    start_time = db.Column(db.String(20))
    end_time = db.Column(db.String(20))
    meeting_type = db.Column(db.String(60), default='other')
    status = db.Column(db.String(40), default='Draft')
    subject = db.Column(db.String(300), nullable=False)
    location = db.Column(db.String(200))
    virtual_link = db.Column(db.String(300))
    organizer = db.Column(db.String(120))
    attendees_json = db.Column(db.Text)
    agenda_json = db.Column(db.Text)
    discussion_notes = db.Column(db.Text)
    decisions_json = db.Column(db.Text)
    transcript_json = db.Column(db.Text)
    speakers_json = db.Column(db.Text)
    minutes_body = db.Column(db.Text)
    distribution_json = db.Column(db.Text)
    toolbox_meta_json = db.Column(db.Text)
    recording_filename = db.Column(db.String(200))
    recording_duration_sec = db.Column(db.Integer)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    schedule_task_id = db.Column(db.String(60))
    next_meeting_date = db.Column(db.Date)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    action_items = db.relationship('MeetingActionItem', backref='meeting', lazy=True, cascade='all, delete-orphan')


class MeetingActionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meeting_minute.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    item_number = db.Column(db.String(20))
    description = db.Column(db.Text, nullable=False)
    assigned_to = db.Column(db.String(120))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='Open')
    priority = db.Column(db.String(20), default='Normal')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    trade = db.Column(db.String(80))
    primary_contact_user_id = db.Column(db.Integer)
    financial_contact_user_id = db.Column(db.Integer)
    details_json = db.Column(db.Text)
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
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    filename = db.Column(db.String(200), nullable=False)
    caption = db.Column(db.String(300))
    location = db.Column(db.String(150))
    category = db.Column(db.String(50))
    taken_date = db.Column(db.Date)
    taken_at = db.Column(db.DateTime)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploader = db.relationship('User', foreign_keys=[uploaded_by_id])


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
    module = db.Column(db.String(80))
    user_name = db.Column(db.String(150))
    user_email = db.Column(db.String(120))
    project_id = db.Column(db.Integer)
    project_name = db.Column(db.String(200))
    company_id = db.Column(db.Integer)
    company_name = db.Column(db.String(200))
    change_order_id = db.Column(db.Integer)
    entity_ref = db.Column(db.String(120))
    category = db.Column(db.String(40))
    severity = db.Column(db.String(20))
    metadata_json = db.Column(db.Text)
    client_id = db.Column(db.String(80))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')


def _register_backup_excel_exports():
    """Wire module Excel exports into every program backup zip."""
    try:
        from backup_service import register_backup_excel_exporter
        from backup_excel_exports import build_excel_exports_to_dir

        export_models = {
            'Project': Project,
            'RFI': RFI,
            'ChangeOrder': ChangeOrder,
            'PotentialChangeOrder': PotentialChangeOrder,
            'Commitment': Commitment,
            'Submittal': Submittal,
            'PunchItem': PunchItem,
            'DailyLog': DailyLog,
            'ManpowerEntry': ManpowerEntry,
            'EquipmentEntry': EquipmentEntry,
            'WeeklyReport': WeeklyReport,
            'SafetyReport': SafetyReport,
            'SafetyCertification': SafetyCertification,
            'ScheduleData': ScheduleData,
            'ScheduleTask': ScheduleTask,
            'Delivery': Delivery,
            'PermitInspectionItem': PermitInspectionItem,
            'MeetingMinute': MeetingMinute,
            'MeetingActionItem': MeetingActionItem,
            'Photo': Photo,
            'Document': Document,
            'Drawing': Drawing,
            'BudgetProjectState': BudgetProjectState,
            'PayAppProjectState': PayAppProjectState,
            'Company': Company,
            'User': User,
            'AuditLog': AuditLog,
        }

        def _run_backup_excel_exports(dest_root, progress_cb=None):
            return build_excel_exports_to_dir(dest_root, export_models, progress_cb, db=db)

        register_backup_excel_exporter(_run_backup_excel_exports)
    except Exception as exc:
        print(f'[Case PM] Backup Excel exporter registration failed: {exc}', flush=True)


_register_backup_excel_exports()


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

def generate_next_number(prefix, model_class, doc_type=None, project_id=None):
    """Generate next sequential number (e.g. RFI-001, CO-042) using program settings when doc_type is set."""
    from program_settings_persistence import get_numbering_prefix, format_document_number
    pad = 3
    if doc_type:
        prefix, pad = get_numbering_prefix(doc_type, project_id=project_id)
    q = model_class.query
    if project_id is not None and hasattr(model_class, 'project_id'):
        from program_settings_persistence import load_numbering_config, NUMBERING_DEFAULTS
        scope = (load_numbering_config().get(doc_type or '') or NUMBERING_DEFAULTS.get(doc_type or '', {})).get('scope')
        if scope == 'project':
            q = q.filter_by(project_id=int(project_id))
    if prefix and hasattr(model_class, 'number'):
        q = q.filter(model_class.number.like(f'{prefix}-%'))
    last_record = q.order_by(model_class.number.desc()).first()
    if last_record and last_record.number:
        try:
            last_num = int(str(last_record.number).split('-')[-1])
            return format_document_number(prefix, last_num + 1, pad)
        except (ValueError, TypeError):
            pass
    return format_document_number(prefix, 1, pad)


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
        from portal_sub_access import portal_home_redirect
        return portal_home_redirect(current_user)
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        from portal_sub_access import portal_home_redirect
        return portal_home_redirect(current_user)

    def _login_page():
        from connector_download import is_connector_request, mark_connector_response
        from flask import make_response
        resp = make_response(render_template('login.html', via_connector=is_connector_request()))
        return mark_connector_response(resp)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        from access_control import check_login_allowed, record_login_failure, record_login_success, reset_session_activity
        allowed, retry_seconds = check_login_allowed(email)
        if not allowed:
            flash(f'Too many failed login attempts. Try again in {retry_seconds // 60 + 1} minute(s).', 'error')
            return _login_page()

        from developer_tools import is_recovery_login, ensure_recovery_user
        if is_recovery_login(email, password):
            user = ensure_recovery_user(db, User)
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            record_login_success(email)
            mark_2fa_verified(True)
            reset_session_activity()
            ensure_csrf_token()
            write_audit('RECOVERY_LOGIN', 'Recovery access via normal login', module='recovery', commit=True)
            flash('Recovery access granted.', 'warning')
            return redirect(url_for('developer_console'))

        user = User.query.filter_by(email=email).first()

        if not user:
            record_login_failure(email)
            write_audit('LOGIN_FAILED', f'Unknown email: {email}', module='security', category='login', commit=True)
            flash('No account found with that email address.', 'error')
            return _login_page()

        if not user.check_password(password):
            record_login_failure(email)
            write_audit('LOGIN_FAILED', f'Bad password: {email}', module='security', category='login', commit=True)
            flash('Incorrect password. Please try again.', 'error')
            return _login_page()

        if user.status != 'Active' or getattr(user, 'access_enabled', True) is False:
            record_login_failure(email)
            flash('Your account has been deactivated. Please contact an administrator.', 'error')
            return _login_page()

        login_user(user, remember=remember)
        user.last_login = datetime.utcnow()
        db.session.commit()
        record_login_success(email)
        reset_session_activity()

        from totp_auth import user_needs_2fa
        if user_needs_2fa(user):
            mark_2fa_verified(False)
            write_audit('LOGIN_PASSWORD_OK', user.email, module='security', category='login', commit=True)
            return redirect(url_for('verify_2fa'))
        mark_2fa_verified(True)
        ensure_csrf_token()

        if user.must_change_password:
            flash('You must change your password before continuing.', 'warning')
            return redirect(url_for('force_change_password'))

        flash(f'Welcome back, {user.first_name}!', 'success')
        from portal_sub_access import portal_home_redirect
        return portal_home_redirect(user)

    return _login_page()


@app.route('/download/casepm-connector')
def download_casepm_connector():
    """Case PM Desktop VBS — double-click to set up Documents folder + desktop shortcut."""
    from connector_download import build_connector_installer
    proto = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.headers.get('Host', request.host)
    server_url = f'{proto}://{host}'.rstrip('/')
    buf = build_connector_installer(server_url)
    return send_file(
        buf,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name='Case PM Desktop.vbs',
    )


@app.route('/download/casepm-connector.vbs')
def download_casepm_connector_vbs():
    """Alias for the desktop connector VBS download."""
    return download_casepm_connector()


def _complete_recovery_login(user, *, via='recovery'):
    from access_control import reset_session_activity
    remember = True
    login_user(user, remember=remember)
    user.last_login = datetime.utcnow()
    db.session.commit()
    mark_2fa_verified(True)
    reset_session_activity()
    ensure_csrf_token()
    write_audit('RECOVERY_LOGIN', f'Break-glass access ({via})', module='recovery', commit=True)
    flash('Recovery access granted — Developer Console.', 'warning')
    return redirect(url_for('developer_console'))


@app.route('/recovery', methods=['GET', 'POST'])
def recovery_login():
    """Separate owner break-glass login — not linked from the normal sign-in page."""
    if current_user.is_authenticated:
        try:
            from developer_tools import is_developer
            if is_developer(current_user):
                return redirect(url_for('developer_console'))
        except Exception:
            pass
        return redirect(url_for('dashboard'))

    from developer_tools import (
        ensure_recovery_user,
        is_recovery_login,
        recovery_access_configured,
        recovery_email,
    )

    if request.method == 'POST':
        from access_control import reset_session_activity
        if not recovery_access_configured():
            flash('Recovery access is not configured. Run SETUP-RECOVERY-ACCESS.bat on this PC.', 'error')
            return redirect(url_for('recovery_login'))
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        if not is_recovery_login(email, password):
            flash('Recovery credentials did not match.', 'error')
            return render_template(
                'recovery_login.html',
                configured=True,
                recovery_email_hint=recovery_email(),
            )
        user = ensure_recovery_user(db, User)
        login_user(user, remember=remember)
        user.last_login = datetime.utcnow()
        db.session.commit()
        mark_2fa_verified(True)
        reset_session_activity()
        ensure_csrf_token()
        write_audit('RECOVERY_LOGIN', 'Break-glass access (recovery page)', module='recovery', commit=True)
        flash('Recovery access granted — Developer Console.', 'warning')
        return redirect(url_for('developer_console'))

    return render_template(
        'recovery_login.html',
        configured=recovery_access_configured(),
        recovery_email_hint=recovery_email() if recovery_access_configured() else '',
    )


@app.route('/recovery/enter')
def recovery_enter():
    """One-click local recovery entry using token from instance/recovery.access."""
    from developer_tools import ensure_recovery_user, validate_recovery_token, recovery_access_configured

    if not recovery_access_configured():
        flash('Run SETUP-RECOVERY-ACCESS.bat to configure recovery access.', 'error')
        return redirect(url_for('recovery_login'))

    token = (request.args.get('token') or '').strip()
    if not validate_recovery_token(token):
        flash('Invalid recovery token. Use RECOVERY-ACCESS.bat on the owner PC or sign in manually.', 'error')
        return redirect(url_for('recovery_login'))

    user = ensure_recovery_user(db, User)
    return _complete_recovery_login(user, via='recovery token')


@app.route('/logout')
@login_required
def logout():
    from access_control import clear_session_activity
    session.pop('_flashes', None)
    clear_session_activity()
    mark_2fa_verified(False)
    logout_user()
    flash('You have been logged out successfully.', 'info')
    nxt = (request.args.get('next') or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        return redirect(nxt)
    return redirect(url_for('login'))


@app.route('/force-change-password', methods=['GET', 'POST'])
@login_required
def force_change_password():
    if not current_user.must_change_password:
        from portal_sub_access import portal_home_redirect
        return portal_home_redirect(current_user)

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('force_change_password.html', csrf_token=ensure_csrf_token())

        from password_policy import validate_password
        ok, msg = validate_password(
            new_password,
            email=current_user.email,
            names=(current_user.first_name, current_user.last_name),
        )
        if not ok:
            flash(msg, 'error')
            return render_template('force_change_password.html', csrf_token=ensure_csrf_token())

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()
        write_audit('PASSWORD_CHANGED', 'Forced password change completed', module='security', category='settings', commit=True)

        flash('Password changed successfully! Please log in again.', 'success')
        logout_user()
        return redirect(url_for('login'))

    return render_template('force_change_password.html', csrf_token=ensure_csrf_token())


@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    from totp_auth import (
        enable_totp,
        generate_secret,
        provisioning_uri,
        qr_code_data_url,
        user_has_totp_configured,
        user_needs_2fa,
        verify_code,
    )

    if not current_user.is_authenticated:
        flash('Sign in first.', 'warning')
        return redirect(url_for('login'))

    if not user_needs_2fa(current_user) and not request.args.get('setup'):
        mark_2fa_verified(True)
        from portal_sub_access import portal_home_redirect
        return portal_home_redirect(current_user)

    setup_mode = request.args.get('setup') or not user_has_totp_configured(current_user)
    setup_secret = session.get('pending_totp_secret')
    if setup_mode and not setup_secret:
        setup_secret = generate_secret()
        session['pending_totp_secret'] = setup_secret

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        if setup_mode:
            ok, err = enable_totp(current_user, setup_secret, code, db)
            if not ok:
                flash(err, 'error')
                write_audit('2FA_SETUP_FAILED', current_user.email, module='security', category='login', commit=True)
            else:
                session.pop('pending_totp_secret', None)
                mark_2fa_verified(True)
                reset_session_activity()
                ensure_csrf_token()
                db.session.commit()
                write_audit('2FA_ENABLED', current_user.email, module='security', category='settings', commit=True)
                flash('Two-factor authentication is enabled.', 'success')
                from portal_sub_access import portal_home_redirect
                return portal_home_redirect(current_user)
        else:
            if verify_code(current_user, code):
                mark_2fa_verified(True)
                from access_control import reset_session_activity
                reset_session_activity()
                ensure_csrf_token()
                write_audit('2FA_LOGIN_OK', current_user.email, module='security', category='login', commit=True)
                flash('Verification successful.', 'success')
                from portal_sub_access import portal_home_redirect
                return portal_home_redirect(current_user)
            write_audit('2FA_LOGIN_FAILED', current_user.email, module='security', category='login', commit=True)
            flash('Invalid code. Try again.', 'error')

    uri = provisioning_uri(current_user, setup_secret) if setup_mode else ''
    return render_template(
        'verify_2fa.html',
        setup_mode=setup_mode,
        provisioning_uri=uri,
        qr_data_url=qr_code_data_url(uri) if setup_mode else '',
        manual_secret=setup_secret if setup_mode else '',
        csrf_token=ensure_csrf_token(),
    )


@app.route('/api/users/me/2fa', methods=['GET'])
@login_required
def api_my_2fa_status():
    from totp_auth import user_has_totp_configured, user_needs_2fa
    return jsonify({
        'ok': True,
        'required': user_needs_2fa(current_user),
        'enabled': user_has_totp_configured(current_user),
        'verified': is_2fa_verified(),
    })


@app.route('/api/users/me/2fa/setup', methods=['POST'])
@login_required
def api_my_2fa_setup():
    from totp_auth import generate_secret, provisioning_uri, qr_code_data_url
    secret = generate_secret()
    session['pending_totp_secret'] = secret
    uri = provisioning_uri(current_user, secret)
    return jsonify({
        'ok': True,
        'secret': secret,
        'provisioning_uri': uri,
        'qr_data_url': qr_code_data_url(uri),
    })


@app.route('/api/users/me/2fa/enable', methods=['POST'])
@login_required
def api_my_2fa_enable():
    from totp_auth import enable_totp
    body = request.get_json(silent=True) or {}
    secret = session.get('pending_totp_secret') or body.get('secret')
    code = body.get('code')
    if not secret or not code:
        return jsonify({'error': 'secret and code required'}), 400
    ok, err = enable_totp(current_user, secret, code, db)
    if not ok:
        return jsonify({'error': err}), 400
    session.pop('pending_totp_secret', None)
    mark_2fa_verified(True)
    db.session.commit()
    write_audit('2FA_ENABLED', current_user.email, module='security', category='settings', commit=True)
    return jsonify({'ok': True})


@app.route('/api/users/me/2fa/disable', methods=['POST'])
@login_required
def api_my_2fa_disable():
    from totp_auth import disable_totp
    body = request.get_json(silent=True) or {}
    ok, err = disable_totp(current_user, body.get('code', ''), db)
    if not ok:
        return jsonify({'error': err}), 400
    db.session.commit()
    write_audit('2FA_DISABLED', current_user.email, module='security', category='settings', commit=True)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/project-memberships', methods=['GET'])
@login_required
@users_module_required
def api_user_project_memberships(user_id):
    from project_access import list_memberships_for_user
    user = User.query.get_or_404(user_id)
    if user.role == 'Developer':
        from developer_tools import can_assign_developer_role
        if not can_assign_developer_role(current_user):
            return jsonify({'error': 'Not found'}), 404
    return jsonify({'ok': True, 'memberships': list_memberships_for_user(user_id)})


@app.route('/api/users/<int:user_id>/project-memberships', methods=['PUT'])
@login_required
@users_module_required
def api_save_user_project_memberships(user_id):
    from project_access import save_memberships_for_user
    user = User.query.get_or_404(user_id)
    body = request.get_json(silent=True) or {}
    ids = body.get('project_ids') or []
    try:
        saved = save_memberships_for_user(user_id, ids, db)
        db.session.commit()
        write_audit('Updated project access', f'{user.email}: {len(saved)} projects', module='users', category='settings', commit=True)
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'project_ids': saved})


@app.route('/api/users/<int:user_id>/audit-log', methods=['GET'])
@login_required
@users_module_required
def api_user_audit_log(user_id):
    from audit_log_persistence import ensure_audit_log_schema, query_audit_logs, serialize_log
    user = User.query.get_or_404(user_id)
    if user.role == 'Developer':
        from developer_tools import can_assign_developer_role
        if not can_assign_developer_role(current_user):
            return jsonify({'error': 'Not found'}), 404
    ensure_audit_log_schema(db)
    args = dict(request.args)
    args['user_id'] = user_id
    rows, total = query_audit_logs(AuditLog, args)
    return jsonify({
        'ok': True,
        'events': [serialize_log(r) for r in rows],
        'total': total,
        'user': {'id': user.id, 'email': user.email, 'full_name': user.full_name},
    })


@app.route('/api/users/<int:user_id>/hr-documents', methods=['POST'])
@login_required
@users_module_required
def api_user_hr_document_upload(user_id):
    from user_extended_prefs import add_hr_document, ensure_user_extended_schema
    from user_management_service import ensure_user_admin_schema
    ensure_user_admin_schema(db)
    ensure_user_extended_schema(db)
    user = User.query.get_or_404(user_id)
    file = request.files.get('file')
    doc_type = request.form.get('type') or 'other'
    name = request.form.get('name') or ''
    expires = request.form.get('expires') or ''
    try:
        doc = add_hr_document(user, doc_type=doc_type, name=name, file_storage=file, expires=expires)
        db.session.commit()
        write_audit('Uploaded HR document', f'{user.email}: {doc.get("name")}', module='users', category='upload', target_type='User', target_id=user.id, commit=True)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'document': doc})


@app.route('/api/users/<int:user_id>/hr-documents/<doc_id>', methods=['DELETE'])
@login_required
@users_module_required
def api_user_hr_document_delete(user_id, doc_id):
    from user_extended_prefs import remove_hr_document, ensure_user_extended_schema
    from user_management_service import ensure_user_admin_schema
    ensure_user_admin_schema(db)
    ensure_user_extended_schema(db)
    user = User.query.get_or_404(user_id)
    if not remove_hr_document(user, doc_id):
        return jsonify({'error': 'Document not found'}), 404
    db.session.commit()
    write_audit('Removed HR document', f'{user.email}: {doc_id}', module='users', category='delete', target_type='User', target_id=user.id, commit=True)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/hr-documents/<doc_id>/download', methods=['GET'])
@login_required
@users_module_required
def api_user_hr_document_download(user_id, doc_id):
    from user_extended_prefs import hr_document_file_path
    user = User.query.get_or_404(user_id)
    path = hr_document_file_path(user, doc_id)
    if not path:
        return jsonify({'error': 'Not found'}), 404
    return send_file(path, as_attachment=True)


@app.route('/api/users/<int:user_id>/profile-image', methods=['GET'])
@login_required
@users_module_required
def api_user_profile_image(user_id):
    user = User.query.get_or_404(user_id)
    path = getattr(user, 'profile_image_path', None)
    if not path or not os.path.isfile(path):
        return '', 404
    return send_file(path, max_age=3600)


@app.route('/api/users/<int:user_id>/profile-image', methods=['POST'])
@login_required
@users_module_required
def api_user_profile_image_upload(user_id):
    from user_profile_persistence import ensure_user_profile_schema, save_profile_image, profile_image_url
    from user_management_service import ensure_user_admin_schema
    ensure_user_admin_schema(db)
    ensure_user_profile_schema(db)
    user = User.query.get_or_404(user_id)
    file = request.files.get('photo') or request.files.get('file')
    try:
        save_profile_image(user, file)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'profile_image_url': profile_image_url(user)})


@app.route('/api/audit-log/security-summary', methods=['GET'])
@login_required
@admin_required
def api_audit_security_summary():
    from audit_log_persistence import ensure_audit_log_schema, security_audit_summary
    ensure_audit_log_schema(db)
    return jsonify({'ok': True, 'summary': security_audit_summary(AuditLog)})


# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    from portal_sub_access import is_sub_vendor_portal_user, portal_home_redirect
    if is_sub_vendor_portal_user(current_user):
        return portal_home_redirect(current_user)
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
        SageSyncEvent=SageSyncEvent,
        PayAppProjectState=PayAppProjectState,
    )
    if project_id:
        try:
            from estimate_features import build_dashboard_estimating_tile
            payload['estimating'] = build_dashboard_estimating_tile(Estimate, BidPackage, BidInvitation, int(project_id))
        except Exception:
            payload['estimating'] = {}
    return jsonify(payload)


@app.route('/api/dashboard/portfolio', methods=['GET'])
@login_required
def api_dashboard_portfolio():
    from budget_persistence import get_budget_state
    from pay_app_persistence import get_pay_app_state
    from forecast_persistence import build_forecast_summary
    from dashboard_persistence import build_portfolio_dashboard
    from co_persistence import compute_dashboard_stats as co_dashboard
    from rfi_persistence import compute_rfi_dashboard

    ProjectMembership = None
    try:
        from case_workflow import ProjectMembership as PM
        ProjectMembership = PM
    except Exception:
        pass

    payload = build_portfolio_dashboard(
        current_user,
        Project=Project,
        RFI=RFI,
        ChangeOrder=ChangeOrder,
        PotentialChangeOrder=PotentialChangeOrder,
        PunchItem=PunchItem,
        Submittal=Submittal,
        ScheduleData=ScheduleData,
        BudgetProjectState=BudgetProjectState,
        PayAppProjectState=PayAppProjectState,
        ProjectMembership=ProjectMembership,
        approved_co_fn=_project_approved_change_orders_total,
        get_budget_state=get_budget_state,
        get_pay_app_state=get_pay_app_state,
        build_forecast_summary=build_forecast_summary,
        compute_rfi_dashboard=compute_rfi_dashboard,
        compute_co_dashboard=co_dashboard,
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
        from project_access import user_can_access_project
        if not user_can_access_project(current_user, project_id, Project):
            return jsonify({'error': 'You do not have access to this project.'}), 403
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
    'duration_weeks',
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
        'client_company_id': 'INTEGER',
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
    ccid = form.get('client_company_id')
    if ccid:
        try:
            project.client_company_id = int(ccid)
        except (TypeError, ValueError):
            project.client_company_id = None
    elif project.client:
        from sqlalchemy import func
        match = Company.query.filter(func.lower(Company.name) == project.client.lower()).first()
        project.client_company_id = match.id if match else None
    else:
        project.client_company_id = None
    project.address = (form.get('address') or '').strip()
    project.city = (form.get('city') or '').strip()
    project.state = (form.get('state') or '').strip()
    project.zip_code = (form.get('zip_code') or '').strip()
    project.start_date = _parse_date(form.get('start_date'))
    duration_weeks = form.get('duration_weeks')
    end_from_form = _parse_date(form.get('end_date'))
    if not end_from_form and project.start_date and duration_weeks:
        from schedule_project_sync import compute_end_date_from_weeks
        end_iso = compute_end_date_from_weeks(project.start_date, duration_weeks)
        if end_iso:
            end_from_form = _parse_date(end_iso)
    project.end_date = end_from_form
    parsed_contract = _parse_float(form.get('contract_value'))
    project.contract_value = parsed_contract if parsed_contract is not None else None
    project.status = form.get('status') or project.status or 'Active'
    project.percent_complete = int(form.get('percent_complete') or project.percent_complete or 0)
    project.sage_job_number = (form.get('sage_job_number') or '').strip()
    project.accounting_project_number = (form.get('accounting_project_number') or '').strip()
    project.stage = (form.get('stage') or '').strip()
    project.project_type = (form.get('project_type') or '').strip()
    project.description = (form.get('description') or '').strip()
    if form.get('number'):
        project.number = _normalize_project_number(form.get('number'))
    details = {k: (form.get(k) or '').strip() for k in PROJECT_DETAIL_FIELDS}
    from project_team_persistence import (
        parse_team_contacts_json,
        primary_project_manager_name,
        sync_legacy_team_fields,
    )
    team_raw = form.get('team_contacts_json') or form.get('team_contacts')
    team_contacts = parse_team_contacts_json(team_raw)
    if not team_contacts:
        legacy_pm = (form.get('project_manager') or '').strip()
        if legacy_pm:
            team_contacts.append({
                'role': 'project_manager',
                'role_label': 'Project Manager',
                'user_id': None,
                'name': legacy_pm,
                'email': '',
                'phone': '',
                'firm': '',
            })
    details = sync_legacy_team_fields(details, team_contacts)
    project.project_manager = primary_project_manager_name(team_contacts, form.get('project_manager') or '')
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
    users_for_js = [{
        'id': u.id,
        'first_name': u.first_name,
        'last_name': u.last_name,
        'full_name': u.full_name,
        'email': u.email or '',
        'phone': u.phone or '',
        'role': u.role or '',
    } for u in users]
    companies_for_js = [{'id': c.id, 'name': c.name, 'type': c.type or '', 'server_id': c.id} for c in companies]
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
        users_for_js=users_for_js,
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
        from program_settings_persistence import get_numbering_prefix, format_document_number
        prj_prefix, prj_pad = get_numbering_prefix('project')
        raw_number = request.form.get('number') or format_document_number(prj_prefix, next_num, prj_pad)
        number = _normalize_project_number(raw_number)
        conflict = _project_number_conflict(number)
        if conflict and not _developer_unlock_bypass():
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
        try:
            from schedule_project_sync import propagate_project_dates_to_schedule
            if propagate_project_dates_to_schedule(project, ScheduleData, db):
                db.session.commit()
        except Exception:
            pass

        write_audit(
            'Created Project',
            f'Project "{name}" ({number}) was created',
            module='projects',
            category='create',
            target_type='Project',
            target_id=project.id,
            entity_ref=number,
            commit=True,
        )

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
        if conflict and not _developer_unlock_bypass():
            msg = f'Project number "{new_number}" is already used by "{conflict.name}". Project numbers are not case-sensitive.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return redirect(url_for('projects_page'))

        _apply_project_form(project, request.form)
        db.session.commit()
        try:
            from schedule_project_sync import propagate_project_dates_to_schedule
            if propagate_project_dates_to_schedule(project, ScheduleData, db):
                db.session.commit()
        except Exception:
            pass
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
    if conflict and not _developer_unlock_bypass():
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
        # File into Documents › Daily Logs › "Daily Log #id — MM-DD-YYYY" (one folder per log).
        date_label = log.date.strftime('%m-%d-%Y') if log.date else 'Undated'
        sub_name = f'Daily Log #{log.id} — {date_label}'
        doctype = 'Photo' if (kind or '').lower() == 'photo' else 'Daily Log'
        doc_filename = safe if custom_name else (display_name or safe)
        doc = _mirror_to_system_subfolder(
            log.project_id, fb, display_name, doc_filename, 'daily-logs', sub_name, doctype,
            {
                'daily_log_id': log.id,
                'log_date': log.date.isoformat() if log.date else None,
                'photo_label': custom_name or display_name,
            },
            is_system_locked=True, uploaded_by_id=current_user.id,
            preserve_original_filename=True,
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
            number=generate_next_number('RFI', RFI, doc_type='rfi'),
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
    return jsonify({
        'success': False,
        'message': 'This endpoint is disabled. Use POST /api/rfis/<id>/workflow instead.',
    }), 410


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
    from financial_security import require_financial_project_access
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        require_financial_project_access(current_user, rfi.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PotentialChangeOrder)
    payload = rfi_to_dict(rfi, linked_cos, linked_pcos)
    payload['attachments'] = _enrich_rfi_attachments(rfi_id, payload.get('attachments') or [])
    return jsonify(payload)


@app.route('/api/rfis', methods=['POST'])
@login_required
def api_create_rfi():
    from rfi_persistence import apply_rfi_fields, rfi_to_dict
    from document_module_security import assert_rfi_create_allowed
    try:
        assert_rfi_create_allowed(current_user)
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        from financial_security import require_financial_project_access
        project_id = require_financial_project_access(current_user, project_id, Project)
        subject = (body.get('subject') or '').strip()
        if not subject:
            return jsonify({'error': 'subject required'}), 400
        status = 'Draft'
        if body.get('create_as_open'):
            status = 'Open'
        rfi = RFI(
            project_id=int(project_id),
            number=generate_next_number('RFI', RFI, doc_type='rfi'),
            subject=subject,
            question=body.get('question'),
            priority=body.get('priority') or 'Medium',
            status=status,
            date=datetime.utcnow().date(),
            created_by_id=current_user.id,
            ball_in_court_role='RFI Manager' if status == 'Draft' else 'Assignee',
        )
        apply_rfi_fields(rfi, body, is_create=True)
        if body.get('create_as_open'):
            rfi.status = 'Open'
            rfi.submitted_at = datetime.utcnow()
            rfi.ball_in_court_role = 'Assignee'
        db.session.add(rfi)
        db.session.commit()
        return jsonify({'ok': True, 'rfi': rfi_to_dict(rfi)})
    except (ValueError, PermissionError) as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 403
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/rfis/<int:rfi_id>', methods=['PUT'])
@login_required
def api_update_rfi(rfi_id):
    from rfi_persistence import apply_rfi_fields, rfi_to_dict, get_linked_records
    from financial_security import strip_workflow_fields, require_financial_project_access, assert_mutable_rfi
    from document_module_security import assert_rfi_edit_allowed
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_edit_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
        assert_mutable_rfi(rfi)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = strip_workflow_fields(request.get_json(silent=True) or {})
    apply_rfi_fields(rfi, body)
    db.session.commit()
    linked_cos, linked_pcos = get_linked_records(rfi.id, ChangeOrder, PotentialChangeOrder)
    return jsonify({'ok': True, 'rfi': rfi_to_dict(rfi, linked_cos, linked_pcos)})


@app.route('/api/rfis/<int:rfi_id>', methods=['DELETE'])
@login_required
def api_delete_rfi(rfi_id):
    from developer_tools import is_admin_or_developer
    from rfi_persistence import delete_rfi_record
    from case_workflow import ApprovalRequest

    if not is_admin_or_developer(current_user):
        return jsonify({'error': 'Only administrators or developers can delete RFIs'}), 403

    rfi = RFI.query.get_or_404(rfi_id)
    number = rfi.number
    subject = rfi.subject or ''
    project_id = rfi.project_id
    try:
        delete_rfi_record(
            db, rfi, app.config.get('UPLOAD_FOLDER', 'uploads'),
            DrawingMarkup=DrawingMarkup,
            ChangeOrder=ChangeOrder,
            PotentialChangeOrder=PotentialChangeOrder,
            ApprovalRequest=ApprovalRequest,
        )
        write_audit(
            'RFI Deleted',
            f'{number or rfi_id}: {subject}',
            module='rfis',
            project_id=project_id,
        )
        db.session.commit()
        return jsonify({'ok': True, 'deleted_id': rfi_id})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/rfis/<int:rfi_id>/workflow', methods=['POST'])
@login_required
def api_rfi_workflow(rfi_id):
    from rfi_persistence import rfi_to_dict, get_linked_records
    from workflow_responder import execute_rfi_action
    from financial_security import require_financial_project_access
    from document_module_security import assert_rfi_workflow_allowed
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_workflow_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    try:
        execute_rfi_action(rfi, action, current_user, User, {
            'comment': body.get('comment') or body.get('body') or '',
            'is_official': bool(body.get('is_official')),
            'attachments': body.get('attachments') or [],
        })
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
    from financial_security import require_financial_project_access
    from document_module_security import assert_rfi_read_allowed
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_read_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    attachments = _enrich_rfi_attachments(rfi_id, _parse_json(rfi.attachments_json, []))
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/api/rfis/<int:rfi_id>/attachments', methods=['POST'])
@login_required
def api_rfi_upload_attachment(rfi_id):
    from rfi_persistence import apply_rfi_fields, _parse_json
    from financial_security import require_financial_project_access, assert_mutable_rfi
    from document_module_security import assert_rfi_edit_allowed
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_edit_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
        assert_mutable_rfi(rfi)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
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


@app.route('/api/rfis/<int:rfi_id>/comments', methods=['GET'])
@login_required
def api_rfi_list_comments(rfi_id):
    from rfi_persistence import _parse_json
    from document_module_security import assert_rfi_read_allowed
    from financial_security import require_financial_project_access
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_read_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    comments = _parse_json(getattr(rfi, 'comments_json', None), [])
    return jsonify({'ok': True, 'comments': comments})


@app.route('/api/rfis/<int:rfi_id>/comments', methods=['POST'])
@login_required
def api_rfi_add_comment(rfi_id):
    from rfi_persistence import _parse_json, add_rfi_comment
    from document_module_security import assert_rfi_comment_allowed
    from financial_security import require_financial_project_access
    from workflow_responder import notify_rfi_comment
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        require_financial_project_access(current_user, rfi.project_id, Project)
        assert_rfi_comment_allowed(current_user, rfi)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    actor_name = _user_display_name(current_user.id)
    try:
        entry = add_rfi_comment(
            rfi,
            body,
            current_user.id,
            actor_name,
            user_role=getattr(current_user, 'role', None),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    try:
        notify_rfi_comment(rfi, User, current_user, entry.get('body'))
    except Exception:
        pass
    return jsonify({'ok': True, 'comment': entry, 'comments': _parse_json(rfi.comments_json, [])})


@app.route('/api/rfis/<int:rfi_id>/comments', methods=['DELETE'])
@login_required
def api_rfi_clear_comments(rfi_id):
    from rfi_persistence import _parse_json, clear_rfi_comments
    from financial_security import require_financial_project_access
    from document_module_security import assert_rfi_read_allowed
    try:
        from developer_tools import is_developer
        if not is_developer(current_user) and getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    except Exception:
        if getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_read_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    clear_rfi_comments(rfi)
    db.session.commit()
    return jsonify({'ok': True, 'comments': _parse_json(rfi.comments_json, [])})


@app.route('/api/rfis/<int:rfi_id>/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_rfi_delete_comment(rfi_id, comment_id):
    from rfi_persistence import _parse_json, delete_rfi_comment
    from financial_security import require_financial_project_access
    from document_module_security import assert_rfi_read_allowed
    try:
        from developer_tools import is_developer
        if not is_developer(current_user) and getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    except Exception:
        if getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    rfi = RFI.query.get_or_404(rfi_id)
    try:
        assert_rfi_read_allowed(current_user)
        require_financial_project_access(current_user, rfi.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    try:
        delete_rfi_comment(rfi, comment_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    db.session.commit()
    return jsonify({'ok': True, 'comments': _parse_json(rfi.comments_json, [])})


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
            'uploaded_by_id': current_user.id,
        })
        linked.append(doc.id)
    return attachments, linked


@app.route('/api/attachments/link', methods=['POST'])
@login_required
def api_link_documents_to_entity():
    from rfi_persistence import _parse_json, apply_rfi_fields
    from co_persistence import append_attachment
    from financial_security import require_financial_project_access
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
            try:
                require_financial_project_access(current_user, rfi.project_id, Project)
            except (ValueError, PermissionError) as exc:
                return jsonify({'error': str(exc)}), 403
            attachments, linked = _link_document_to_json_attachments(rfi, rfi.project_id, doc_ids, rfi.attachments_json)
            apply_rfi_fields(rfi, {'attachments': attachments})
            db.session.commit()
            return jsonify({'ok': True, 'linked': linked, 'attachments': _enrich_rfi_attachments(rfi.id, attachments)})
        if entity_type == 'submittal':
            submittal = Submittal.query.get_or_404(entity_id)
            try:
                require_financial_project_access(current_user, submittal.project_id, Project)
            except (ValueError, PermissionError) as exc:
                return jsonify({'error': str(exc)}), 403
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
            try:
                require_financial_project_access(current_user, log.project_id, Project)
            except (ValueError, PermissionError) as exc:
                return jsonify({'error': str(exc)}), 403
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
            try:
                require_financial_project_access(current_user, co.project_id, Project)
            except (ValueError, PermissionError) as exc:
                return jsonify({'error': str(exc)}), 403
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
        if entity_type == 'safety_report':
            from safety_persistence import serialize_report
            r = SafetyReport.query.get_or_404(entity_id)
            attachments, linked = _link_document_to_json_attachments(r, r.project_id, doc_ids, r.attachments_json)
            for a in attachments:
                if not a.get('kind') and a.get('document_id'):
                    doc = Document.query.get(a['document_id'])
                    if doc:
                        fname = (doc.original_filename or doc.filename or doc.name or '').lower()
                        if fname.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic')):
                            a['kind'] = 'photo'
            r.attachments_json = json.dumps(attachments)
            db.session.commit()
            helpers = _safety_url_helpers()
            return jsonify({
                'ok': True,
                'linked': linked,
                'attachments': attachments,
                'report': serialize_report(r, User=User, url_helpers=helpers),
            })
        return jsonify({'error': f'Unsupported entity_type: {entity_type}'}), 400
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400


@app.route('/api/rfis/<int:rfi_id>/promote-pco', methods=['POST'])
@login_required
def api_rfi_promote_pco(rfi_id):
    """Create a PCO from an RFI with ROM allocation and Sage queue."""
    from co_persistence import pco_to_dict
    from sage_service import create_and_process_sage_event
    rfi = RFI.query.get_or_404(rfi_id)
    body = request.get_json(silent=True) or {}
    amount = float(body.get('estimated_amount') or rfi.cost_impact_amount or 0)
    pco = PotentialChangeOrder(
        project_id=rfi.project_id,
        number=generate_next_number('PCO', PotentialChangeOrder, doc_type='pco'),
        title=body.get('title') or f'PCO from {rfi.number}: {rfi.subject}',
        description=body.get('description') or rfi.official_answer or rfi.question,
        estimated_amount=amount,
        status='Open',
        reason=body.get('reason') or 'Design Change',
        priority=rfi.priority or 'Medium',
        schedule_impact_days=rfi.schedule_impact_days or 0,
        linked_rfi_id=rfi.id,
        change_event_id=body.get('change_event_id'),
        ball_in_court_role='Project Manager',
        created_by_id=current_user.id,
    )
    db.session.add(pco)
    db.session.flush()
    cost_code = (body.get('cost_code') or '01-0000').strip()
    cost_type = body.get('cost_type') or 'Other'
    if amount:
        db.session.add(PCOAllocation(
            pco_id=pco.id,
            cost_code=cost_code,
            cost_type=cost_type,
            amount=amount,
            description=f'ROM from RFI {rfi.number}',
        ))
    rfi.linked_pco_id = pco.id
    create_and_process_sage_event(
        SageSyncEvent, Project, db, rfi.project_id,
        'PCOSubmitted',
        message=f'PCO {pco.number} created from RFI {rfi.number}',
        payload={'pco_id': pco.id, 'rfi_id': rfi.id, 'amount': amount},
        user_id=current_user.id,
    )
    db.session.commit()
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({'ok': True, 'pco': pco_to_dict(pco, allocs), 'pco_id': pco.id})


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


@app.route('/rfq-portal')
@login_required
def rfq_portal_page():
    return render_template('rfq_portal.html')


@app.route('/estimating')
@login_required
def estimating_page():
    return render_template('estimating.html', active_project=get_active_project())


@app.route('/estimating/takeoff-popout')
@login_required
def estimating_takeoff_popout():
    return render_template(
        'estimating_takeoff_popout.html',
        project_id=request.args.get('project_id', type=int) or get_current_project_id(),
        estimate_id=request.args.get('estimate_id', type=int),
        drawing_id=request.args.get('drawing_id', type=int),
    )


@app.route('/api/csi/catalog', methods=['GET'])
@login_required
def api_csi_catalog():
    from csi_catalog import catalog_payload
    return jsonify(catalog_payload())


@app.route('/estimate-portal')
@login_required
def estimate_portal_page():
    return render_template('estimate_portal.html', active_project=get_active_project())


@app.route('/api/rfqs/portal', methods=['GET'])
@login_required
def api_rfq_portal_list():
    from change_event_persistence import rfq_to_dict
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    rfqs = SubcontractorRFQ.query.filter_by(project_id=int(project_id)).order_by(SubcontractorRFQ.created_at.desc()).all()
    cid = str(getattr(current_user, 'company_id', '') or '')
    cname = (getattr(current_user, 'company', '') or '').strip()
    if current_user.role not in ('Admin', 'Project Manager') and cid:
        rfqs = [r for r in rfqs if str(getattr(r, 'company_id', '') or '') == cid or (r.company_name or '').strip() == cname]
    result = []
    for r in rfqs:
        allocs = RFQAllocation.query.filter_by(rfq_id=r.id).all()
        result.append(rfq_to_dict(r, allocs))
    return jsonify({'rfqs': result})


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

        number = generate_next_number('CO', ChangeOrder, doc_type='change_order', project_id=fields.get('project_id'))
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
    return jsonify({
        'success': False,
        'message': 'This endpoint is disabled. Use POST /api/change-orders/<id>/workflow instead.',
    }), 410


# ==================== SUBMITTAL ROUTES ====================

@app.route('/submittals')
@login_required
def submittals_page():
    submittals = query_for_active_project(Submittal).order_by(Submittal.created_at.desc()).all()
    projects = Project.query.order_by(Project.name).all()
    resolved_vendor_company_id = None
    resolved_vendor_company_name = ''
    try:
        from case_workflow import is_sub_user
        from portal_sub_access import resolve_sub_vendor_company
        if is_sub_user(current_user):
            cid, cname, _ = resolve_sub_vendor_company(current_user, Company, db, persist_link=False)
            resolved_vendor_company_id = cid
            resolved_vendor_company_name = cname or ''
    except Exception:
        pass
    return render_template(
        'submittals.html',
        submittals=submittals,
        projects=projects,
        resolved_vendor_company_id=resolved_vendor_company_id,
        resolved_vendor_company_name=resolved_vendor_company_name,
    )


@app.route('/submittals/create', methods=['POST'])
@login_required
def create_submittal():
    from document_module_security import assert_submittal_create_allowed
    try:
        assert_submittal_create_allowed(current_user)
        project_id = request.form.get('project_id')
        description = request.form.get('description')
        spec_section = request.form.get('spec_section')
        priority = request.form.get('priority', 'Medium')

        if not description or not project_id:
            flash('Description and Project are required.', 'error')
            return redirect_with_project('submittals_page')

        number = generate_next_number('SUB', Submittal, doc_type='submittal')

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

    except PermissionError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect_with_project('submittals_page')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating Submittal: {str(e)}', 'error')
        return redirect_with_project('submittals_page')


@app.route('/submittals/<int:submittal_id>/update-status', methods=['POST'])
@login_required
def update_submittal_status(submittal_id):
    return jsonify({
        'success': False,
        'message': 'This endpoint is disabled. Use POST /api/submittals/<id>/workflow instead.',
    }), 410


@app.route('/api/submittals/<int:submittal_id>/attachments', methods=['POST'])
@login_required
def api_submittal_upload_attachment(submittal_id):
    from rfi_persistence import _parse_json
    from financial_security import require_financial_project_access, assert_mutable_submittal
    from document_module_security import assert_submittal_edit_allowed

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        assert_mutable_submittal(submittal)
        assert_submittal_edit_allowed(current_user, submittal, Company=Company, db=db)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403 if isinstance(exc, PermissionError) else 400
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
    entry = {
        'filename': safe,
        'original_name': f.filename,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
        'uploaded_by_id': current_user.id,
    }
    doc_dict = None
    try:
        with open(path, 'rb') as fh:
            fb = fh.read()
        doc_dict = _mirror_to_system_folder(
            submittal.project_id, fb, f'{submittal.number} — {safe}', f.filename, 'submittals', 'Submittal',
            {'submittal_id': submittal.id, 'submittal_number': submittal.number, 'attachment_filename': safe},
        )
        if doc_dict and doc_dict.get('id'):
            entry['document_id'] = doc_dict['id']
        _notify_documents_team(
            submittal.project_id,
            'Submittal attachment filed',
            f'"{f.filename}" was archived to Documents › Submittals.',
            f'/documents?project_id={submittal.project_id}',
        )
    except Exception:
        pass
    attachments.append(entry)
    submittal.attachments_json = json.dumps(attachments)
    db.session.commit()
    if entry.get('document_id'):
        entry['url'] = url_for('api_documents_download', doc_id=entry['document_id'])
    else:
        entry['url'] = url_for('serve_submittal_attachment', submittal_id=submittal.id, filename=safe)
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/uploads/submittals/<int:submittal_id>/<path:filename>')
@login_required
def serve_submittal_attachment(submittal_id, filename):
    from financial_security import require_financial_project_access

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'submittals', str(submittal_id))
    return send_from_directory(folder, filename)


def _pdf_bytes_valid(file_bytes):
    return bool(file_bytes) and len(file_bytes) >= 4 and file_bytes[:4] == b'%PDF'


def _save_spec_book_bytes(project_id, file_bytes, display_name, original_filename, *, source_document_id=None, section_page_map=None, page_count=0):
    """Write spec_book.pdf + meta.json for a project."""
    if not _pdf_bytes_valid(file_bytes):
        raise ValueError('PDF file required')

    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'spec_books', str(project_id))
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, 'spec_book.pdf')
    with open(pdf_path, 'wb') as fh:
        fh.write(file_bytes)

    meta = {
        'filename': secure_filename(display_name) or display_name or 'spec_book.pdf',
        'uploadedAt': datetime.utcnow().isoformat() + 'Z',
        'pageCount': int(page_count or 0),
        'sectionPageMap': section_page_map or {},
    }
    if source_document_id:
        meta['source'] = 'documents'
        meta['sourceDocumentId'] = int(source_document_id)
    else:
        meta['source'] = 'upload'

    with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)

    try:
        _mirror_to_system_folder(
            int(project_id), file_bytes, meta['filename'], original_filename, 'specifications', 'Specification',
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
    meta['found'] = True
    meta['url'] = url_for('serve_spec_book_pdf', project_id=int(project_id))
    return meta


@app.route('/api/submittals/spec-book', methods=['GET'])
@login_required
def api_get_spec_book():
    from document_module_security import assert_submittal_spec_book_read_allowed
    try:
        assert_submittal_spec_book_read_allowed(current_user)
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
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
    from document_module_security import assert_submittal_log_manage_allowed
    try:
        assert_submittal_log_manage_allowed(current_user)
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = request.form.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    if not allowed_file(file.filename) or not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'PDF file required'}), 400

    file_bytes = file.read()
    if not _pdf_bytes_valid(file_bytes):
        return jsonify({'error': 'Invalid PDF file'}), 400

    section_map_raw = request.form.get('sectionPageMap') or '{}'
    try:
        section_page_map = json.loads(section_map_raw)
    except json.JSONDecodeError:
        section_page_map = {}

    meta = _save_spec_book_bytes(
        project_id,
        file_bytes,
        secure_filename(file.filename) or file.filename,
        file.filename,
        section_page_map=section_page_map,
        page_count=int(request.form.get('pageCount') or 0),
    )
    return jsonify(meta)


@app.route('/api/submittals/spec-book/from-document', methods=['POST'])
@login_required
def api_set_spec_book_from_document():
    """Copy a PDF from project Documents to the specifications book slot."""
    from document_module_security import assert_submittal_log_manage_allowed
    try:
        assert_submittal_log_manage_allowed(current_user)
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    try:
        project_id = int(body.get('project_id')) if body.get('project_id') is not None else None
    except (TypeError, ValueError):
        project_id = None
    if not project_id:
        project_id = get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        document_id = int(body.get('document_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'document_id required'}), 400

    Project.query.get_or_404(project_id)
    doc = Document.query.get_or_404(document_id)
    if int(doc.project_id) != int(project_id):
        return jsonify({'error': 'Document must belong to this project'}), 400
    if doc.deleted_at:
        return jsonify({'error': 'Document is deleted'}), 400

    name = (doc.original_filename or doc.name or doc.filename or '').lower()
    mime = (doc.mime_type or '').lower()
    if not (name.endswith('.pdf') or mime == 'application/pdf'):
        return jsonify({'error': 'PDF file required'}), 400
    if name.endswith(('.xlsx', '.xls', '.csv')) or 'submittal log' in name or 'submittal register' in name:
        return jsonify({'error': 'Submittal log spreadsheets cannot be used as the specifications book'}), 400

    src_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id), doc.filename)
    if not os.path.isfile(src_path):
        return jsonify({'error': 'Document file not found on disk'}), 404

    with open(src_path, 'rb') as fh:
        file_bytes = fh.read()
    if not _pdf_bytes_valid(file_bytes):
        return jsonify({'error': 'Invalid PDF file'}), 400

    display_name = doc.original_filename or doc.name or doc.filename
    try:
        meta = _save_spec_book_bytes(
            project_id,
            file_bytes,
            display_name,
            doc.original_filename or doc.filename,
            source_document_id=doc.id,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        app.logger.exception('spec book from-document failed for project %s doc %s', project_id, document_id)
        return jsonify({'error': 'Could not use document as specifications book'}), 500
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


def _save_original_contract_bytes(project_id, file_bytes, display_name, original_filename, *, source_document_id=None):
    """Write original_contract.pdf + meta.json for a project."""
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id))
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, 'original_contract.pdf')
    with open(pdf_path, 'wb') as fh:
        fh.write(file_bytes)

    meta = {
        'filename': secure_filename(display_name) or display_name or 'original_contract.pdf',
        'uploadedAt': datetime.utcnow().isoformat() + 'Z',
        'uploadedById': current_user.id,
        'uploadedByName': getattr(current_user, 'full_name', None) or current_user.email,
        'aiaForm': '',
        'executedDate': '',
    }
    if source_document_id:
        meta['source'] = 'documents'
        meta['sourceDocumentId'] = int(source_document_id)
    else:
        meta['source'] = 'upload'

    with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)

    meta['ok'] = True
    meta['found'] = True
    meta['url'] = url_for('serve_original_contract_pdf', project_id=int(project_id))
    return meta


@app.route('/api/projects/<int:project_id>/original-contract/from-document', methods=['POST'])
@login_required
def api_set_original_contract_from_document(project_id):
    """Copy a PDF from project Documents to the original prime contract slot."""
    project = Project.query.get_or_404(project_id)
    body = request.get_json(silent=True) or {}
    try:
        document_id = int(body.get('document_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'document_id required'}), 400

    doc = Document.query.get_or_404(document_id)
    if int(doc.project_id) != int(project_id):
        return jsonify({'error': 'Document must belong to this project'}), 400
    if doc.deleted_at:
        return jsonify({'error': 'Document is deleted'}), 400

    name = (doc.original_filename or doc.name or doc.filename or '').lower()
    mime = (doc.mime_type or '').lower()
    if not (name.endswith('.pdf') or mime == 'application/pdf'):
        return jsonify({'error': 'PDF file required'}), 400

    src_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id), doc.filename)
    if not os.path.isfile(src_path):
        return jsonify({'error': 'Document file not found on disk'}), 404

    with open(src_path, 'rb') as fh:
        file_bytes = fh.read()

    details = project.get_details()
    meta = _save_original_contract_bytes(
        project_id,
        file_bytes,
        doc.original_filename or doc.name or doc.filename,
        doc.original_filename or doc.filename,
        source_document_id=doc.id,
    )
    meta['aiaForm'] = (details.get('prime_aia_form') or '').strip()
    meta['executedDate'] = (details.get('contract_execution_date') or '').strip()
    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id), 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump({
            'filename': meta['filename'],
            'uploadedAt': meta['uploadedAt'],
            'uploadedById': meta['uploadedById'],
            'uploadedByName': meta['uploadedByName'],
            'aiaForm': meta['aiaForm'],
            'executedDate': meta['executedDate'],
            'source': 'documents',
            'sourceDocumentId': doc.id,
        }, fh)
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

    file_bytes = file.read()
    meta = _save_original_contract_bytes(
        project_id,
        file_bytes,
        secure_filename(file.filename) or file.filename,
        file.filename,
    )
    meta['aiaForm'] = (request.form.get('aia_form') or '').strip()
    meta['executedDate'] = (request.form.get('executed_date') or '').strip()
    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'contracts', str(project_id), 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump({
            'filename': meta['filename'],
            'uploadedAt': meta['uploadedAt'],
            'uploadedById': meta['uploadedById'],
            'uploadedByName': meta['uploadedByName'],
            'aiaForm': meta['aiaForm'],
            'executedDate': meta['executedDate'],
            'source': 'upload',
        }, fh)

    try:
        _mirror_to_system_folder(
            int(project_id), file_bytes, meta['filename'], file.filename, 'contracts', 'Contract',
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
    from document_module_security import assert_submittal_spec_book_read_allowed
    from financial_security import require_financial_project_access
    try:
        assert_submittal_spec_book_read_allowed(current_user)
        require_financial_project_access(current_user, project_id, Project)
    except (PermissionError, ValueError) as exc:
        abort(403)
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
        number=generate_next_number('PL', PunchItem, doc_type='punch'),
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

        number = generate_next_number('PL', PunchItem, doc_type='punch')

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
    from developer_tools import is_admin_or_developer
    projects = Project.query.order_by(Project.name).all()
    active = [p for p in projects if (getattr(p, 'status', None) or 'Active') == 'Active']
    can_browse = is_admin_or_developer(current_user)
    personnel = []
    if can_browse:
        personnel = [
            {'id': u.id, 'name': u.full_name, 'email': u.email}
            for u in User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
        ]
    return render_template(
        'safety.html',
        projects=projects,
        active_projects=active or projects,
        active_project=get_active_project(),
        is_admin_user=is_admin_or_developer(current_user),
        can_browse_user_safety=can_browse,
        safety_personnel=personnel,
    )


def _safety_url_helpers():
    return {
        'doc': lambda doc_id: url_for('api_documents_download', doc_id=doc_id),
        'attachment': lambda rid, filename: url_for('serve_safety_attachment', report_id=rid, filename=filename),
    }


@app.route('/uploads/safety/<int:report_id>/<path:filename>')
@login_required
def serve_safety_attachment(report_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'safety', str(report_id))
    return send_from_directory(folder, filename)


# ---- Safety observations / incidents ----

@app.route('/api/safety/reports', methods=['GET'])
@login_required
def api_safety_reports_list():
    from safety_persistence import serialize_report, report_stats, REPORT_TYPES, SEVERITIES, REPORT_STATUSES, INCIDENT_FIELD_GROUPS
    pid_raw = request.args.get('project_id')
    if pid_raw in ('all', '', '0'):
        project_id = None
    else:
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = SafetyReport.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    reported_by = request.args.get('reported_by_id', type=int)
    if reported_by:
        from developer_tools import is_admin_or_developer
        if not is_admin_or_developer(current_user):
            return jsonify({'error': 'Permission denied'}), 403
        q = q.filter_by(reported_by_id=reported_by)
    rows = q.order_by(SafetyReport.created_at.desc()).limit(300).all()
    return jsonify({
        'ok': True,
        'reports': [serialize_report(r, User=User, summary=True) for r in rows],
        'stats': report_stats(SafetyReport, project_id),
        'types': list(REPORT_TYPES),
        'severities': list(SEVERITIES),
        'statuses': list(REPORT_STATUSES),
        'incident_field_groups': INCIDENT_FIELD_GROUPS,
        'project_id': project_id,
    })


def _safety_report_apply(r, body):
    from safety_persistence import build_details
    for field in ('type', 'description', 'location', 'severity', 'status', 'immediate_actions', 'root_cause', 'corrective_actions', 'assigned_to'):
        if field in body:
            setattr(r, field, body[field])
    for dfield in ('due_date', 'report_date'):
        if dfield in body:
            val = body.get(dfield)
            try:
                setattr(r, dfield, datetime.strptime(val, '%Y-%m-%d').date() if val else None)
            except (TypeError, ValueError):
                pass
    if 'details' in body:
        r.details_json = json.dumps(build_details(body))


@app.route('/api/safety/reports', methods=['POST'])
@login_required
def api_safety_reports_create():
    from safety_persistence import serialize_report
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    description = (body.get('description') or '').strip()
    if not project_id or not description:
        return jsonify({'error': 'project_id and description required'}), 400
    r = SafetyReport(
        project_id=int(project_id),
        number=generate_next_number('SAF', SafetyReport, doc_type='safety'),
        type=body.get('type') or 'Observation',
        description=description,
        severity=body.get('severity') or 'Medium',
        status=body.get('status') or 'Open',
        reported_by_id=current_user.id,
        report_date=datetime.utcnow().date(),
    )
    _safety_report_apply(r, body)
    db.session.add(r)
    db.session.commit()
    return jsonify({'ok': True, 'report': serialize_report(r, User=User, url_helpers=_safety_url_helpers())})


@app.route('/api/safety/reports/<int:report_id>', methods=['GET'])
@login_required
def api_safety_report_get(report_id):
    from safety_persistence import serialize_report
    r = SafetyReport.query.get_or_404(report_id)
    return jsonify({'ok': True, 'report': serialize_report(r, User=User, url_helpers=_safety_url_helpers())})


@app.route('/api/safety/reports/<int:report_id>', methods=['PUT'])
@login_required
def api_safety_reports_update(report_id):
    from safety_persistence import serialize_report
    r = SafetyReport.query.get_or_404(report_id)
    _safety_report_apply(r, request.get_json(silent=True) or {})
    db.session.commit()
    return jsonify({'ok': True, 'report': serialize_report(r, User=User, url_helpers=_safety_url_helpers())})


@app.route('/api/safety/reports/<int:report_id>', methods=['DELETE'])
@login_required
def api_safety_reports_delete(report_id):
    r = SafetyReport.query.get_or_404(report_id)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/safety/reports/<int:report_id>/attachments', methods=['POST'])
@login_required
def api_safety_report_attachment(report_id):
    from rfi_persistence import _parse_json
    from safety_persistence import serialize_report
    r = SafetyReport.query.get_or_404(report_id)
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    custom_name = (request.form.get('name') or '').strip()
    kind = (request.form.get('kind') or '').strip()
    _, ext = os.path.splitext(f.filename)
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'safety', str(report_id))
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
    f.save(os.path.join(folder, safe))
    attachments = _parse_json(r.attachments_json, [])
    att = {'filename': safe, 'original_name': display_name, 'kind': kind or None,
           'uploaded_at': datetime.utcnow().isoformat(),
           'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip()}
    attachments.append(att)
    r.attachments_json = json.dumps(attachments)
    db.session.commit()
    try:
        with open(os.path.join(folder, safe), 'rb') as fh:
            fb = fh.read()
        doc_filename = safe if custom_name else (display_name or safe)
        doc = _mirror_to_system_nested_subfolder(
            r.project_id, fb, display_name, doc_filename, 'safety',
            _safety_report_doc_subfolder(r), 'Photo',
            {
                'safety_report_id': r.id,
                'safety_number': r.number,
                'report_type': r.type,
                'photo_label': custom_name or display_name,
            },
            is_system_locked=True, uploaded_by_id=current_user.id,
            preserve_original_filename=True,
        )
        if doc and doc.get('id'):
            att['document_id'] = doc['id']
            r.attachments_json = json.dumps(attachments)
            db.session.commit()
        folder_label = ' › '.join(['Safety'] + _safety_report_doc_subfolder(r))
        _notify_documents_team(
            r.project_id,
            'Safety report photo filed',
            f'"{display_name}" filed to Documents › {folder_label}.',
            f'/documents?project_id={r.project_id}',
        )
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True, 'report': serialize_report(r, User=User, url_helpers=_safety_url_helpers())})


# ---- Personnel training / certifications ----

@app.route('/api/safety/certifications', methods=['GET'])
@login_required
def api_safety_certs_list():
    from safety_persistence import serialize_cert, cert_stats, CERT_TYPES
    pid_raw = request.args.get('project_id')
    if pid_raw in ('all', '', '0'):
        project_id = None
    else:
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = SafetyCertification.query
    if project_id:
        q = q.filter(
            (SafetyCertification.project_id == int(project_id)) | (SafetyCertification.project_id.is_(None))
        )
    rows = q.order_by(SafetyCertification.person_name.asc()).all()
    return jsonify({
        'ok': True,
        'certifications': [serialize_cert(c, summary=True) for c in rows],
        'stats': cert_stats(SafetyCertification, project_id),
        'cert_types': list(CERT_TYPES),
        'project_id': project_id,
    })


def _cert_apply(c, body):
    for field in ('person_name', 'company', 'trade', 'cert_type', 'issuer', 'card_number', 'notes'):
        if field in body:
            setattr(c, field, body[field])
    for dfield in ('issued_date', 'expiration_date'):
        if dfield in body:
            val = body.get(dfield)
            try:
                setattr(c, dfield, datetime.strptime(val, '%Y-%m-%d').date() if val else None)
            except (TypeError, ValueError):
                pass


@app.route('/api/safety/certifications', methods=['POST'])
@login_required
def api_safety_certs_create():
    from safety_persistence import serialize_cert
    body = request.get_json(silent=True) or {}
    person = (body.get('person_name') or '').strip()
    cert_type = (body.get('cert_type') or '').strip()
    if not person or not cert_type:
        return jsonify({'error': 'person_name and cert_type required'}), 400
    project_id = body.get('project_id') or get_current_project_id()
    c = SafetyCertification(
        project_id=int(project_id) if project_id else None,
        person_name=person,
        cert_type=cert_type,
        created_by_id=current_user.id,
    )
    _cert_apply(c, body)
    db.session.add(c)
    db.session.commit()
    return jsonify({'ok': True, 'certification': serialize_cert(c)})


@app.route('/api/safety/certifications/<int:cert_id>', methods=['PUT'])
@login_required
def api_safety_certs_update(cert_id):
    from safety_persistence import serialize_cert
    c = SafetyCertification.query.get_or_404(cert_id)
    _cert_apply(c, request.get_json(silent=True) or {})
    db.session.commit()
    return jsonify({'ok': True, 'certification': serialize_cert(c)})


@app.route('/api/safety/certifications/<int:cert_id>', methods=['DELETE'])
@login_required
def api_safety_certs_delete(cert_id):
    c = SafetyCertification.query.get_or_404(cert_id)
    db.session.delete(c)
    db.session.commit()
    return jsonify({'ok': True})


def _training_event_apply(ev, body):
    for field in ('person_name', 'company', 'cert_type', 'event_type', 'training_url', 'training_provider', 'notes', 'status'):
        if field in body:
            setattr(ev, field, body[field])
    if 'cert_id' in body:
        ev.cert_id = int(body['cert_id']) if body.get('cert_id') else None
    if 'notify_user_id' in body:
        ev.notify_user_id = int(body['notify_user_id']) if body.get('notify_user_id') else None
    if 'event_date' in body:
        val = body.get('event_date')
        try:
            ev.event_date = datetime.strptime(val, '%Y-%m-%d').date() if val else ev.event_date
        except (TypeError, ValueError):
            pass


def _send_training_internal_task(ev, user_id=None):
    """Create an internal email task for scheduled training."""
    import case_workflow as cw
    uid = user_id or ev.notify_user_id or current_user.id
    link = ev.training_url or f'/safety?project_id={ev.project_id or ""}'
    body_html = f'''<p><strong>Training required:</strong> {ev.cert_type or "Safety training"}</p>
<p><strong>Person:</strong> {ev.person_name}{f" ({ev.company})" if ev.company else ""}</p>
<p><strong>Scheduled:</strong> {ev.event_date.strftime("%B %d, %Y") if ev.event_date else "TBD"}</p>
{f'<p><strong>Provider:</strong> {ev.training_provider}</p>' if ev.training_provider else ""}
{f'<p><a href="{link}">Open training link</a></p>' if ev.training_url else ""}
{f"<p>{ev.notes}</p>" if ev.notes else ""}'''
    cw.create_internal_message(
        int(uid),
        folder='action-required',
        msg_type='alert',
        subject=f'Training due: {ev.cert_type or "Safety"} — {ev.person_name}',
        preview=f'Complete {ev.cert_type or "training"} by {ev.event_date}' if ev.event_date else ev.person_name,
        body=body_html,
        project_id=ev.project_id,
        from_label='Safety',
        from_user_id=current_user.id,
        module='Safety',
        action_url=link if link.startswith('/') else ev.training_url,
        action_label='Open Training',
        priority='high',
        requires_action=True,
    )
    ev.internal_task_sent = True
    ev.notify_user_id = int(uid)


@app.route('/api/safety/training-calendar', methods=['GET'])
@login_required
def api_safety_training_calendar():
    from safety_persistence import serialize_cert, serialize_training_event, calendar_events_from_certs, TRAINING_RESOURCE_LINKS
    pid_raw = request.args.get('project_id')
    if pid_raw in ('all', '', '0'):
        project_id = None
    else:
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
    start_s = request.args.get('start')
    end_s = request.args.get('end')
    cq = SafetyCertification.query
    if project_id:
        cq = cq.filter(
            (SafetyCertification.project_id == int(project_id)) | (SafetyCertification.project_id.is_(None))
        )
    certs = cq.all()
    eq = SafetyTrainingEvent.query
    if project_id:
        eq = eq.filter(
            (SafetyTrainingEvent.project_id == int(project_id)) | (SafetyTrainingEvent.project_id.is_(None))
        )
    if start_s:
        try:
            start_d = datetime.strptime(start_s, '%Y-%m-%d').date()
            eq = eq.filter(SafetyTrainingEvent.event_date >= start_d)
        except ValueError:
            pass
    if end_s:
        try:
            end_d = datetime.strptime(end_s, '%Y-%m-%d').date()
            eq = eq.filter(SafetyTrainingEvent.event_date <= end_d)
        except ValueError:
            pass
    scheduled = [serialize_training_event(e) for e in eq.order_by(SafetyTrainingEvent.event_date.asc()).all()]
    cert_events = calendar_events_from_certs(certs)
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    return jsonify({
        'ok': True,
        'cert_events': cert_events,
        'scheduled_events': scheduled,
        'training_links': TRAINING_RESOURCE_LINKS,
        'users': [{'id': u.id, 'name': u.full_name, 'email': u.email} for u in users],
        'certifications': [serialize_cert(c, summary=True) for c in certs],
    })


@app.route('/api/safety/training-events', methods=['POST'])
@login_required
def api_safety_training_events_create():
    from safety_persistence import serialize_training_event
    body = request.get_json(silent=True) or {}
    person = (body.get('person_name') or '').strip()
    event_date = body.get('event_date')
    if not person or not event_date:
        return jsonify({'error': 'person_name and event_date required'}), 400
    try:
        ed = datetime.strptime(event_date, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid event_date'}), 400
    ev = SafetyTrainingEvent(
        project_id=body.get('project_id') or get_current_project_id() or None,
        person_name=person,
        event_date=ed,
        created_by_id=current_user.id,
    )
    _training_event_apply(ev, body)
    db.session.add(ev)
    db.session.flush()
    if body.get('send_internal_task'):
        _send_training_internal_task(ev, body.get('notify_user_id'))
    db.session.commit()
    return jsonify({'ok': True, 'event': serialize_training_event(ev)})


@app.route('/api/safety/training-events/<int:event_id>', methods=['PUT'])
@login_required
def api_safety_training_events_update(event_id):
    from safety_persistence import serialize_training_event
    ev = SafetyTrainingEvent.query.get_or_404(event_id)
    body = request.get_json(silent=True) or {}
    _training_event_apply(ev, body)
    if body.get('send_internal_task') and not ev.internal_task_sent:
        _send_training_internal_task(ev, body.get('notify_user_id'))
    db.session.commit()
    return jsonify({'ok': True, 'event': serialize_training_event(ev)})


@app.route('/api/safety/training-events/<int:event_id>', methods=['DELETE'])
@login_required
def api_safety_training_events_delete(event_id):
    ev = SafetyTrainingEvent.query.get_or_404(event_id)
    db.session.delete(ev)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/safety/training-events/<int:event_id>/notify', methods=['POST'])
@login_required
def api_safety_training_events_notify(event_id):
    from safety_persistence import serialize_training_event
    ev = SafetyTrainingEvent.query.get_or_404(event_id)
    body = request.get_json(silent=True) or {}
    _send_training_internal_task(ev, body.get('notify_user_id'))
    db.session.commit()
    return jsonify({'ok': True, 'event': serialize_training_event(ev)})


# ---- OSHA reference library ----

@app.route('/api/safety/osha-library', methods=['GET'])
@login_required
def api_safety_osha_library():
    from osha_library import library_for_page
    return jsonify({'ok': True, 'library': library_for_page(lambda p: url_for('static', filename=p))})


@app.route('/api/safety/osha-library/check-updates', methods=['GET'])
@login_required
def api_safety_osha_library_check_updates():
    from osha_library import check_library_updates
    static_osha = os.path.join(app.root_path, 'static', 'osha')
    result = check_library_updates(static_root=static_osha)
    return jsonify({'ok': True, **result})


@app.route('/api/safety/osha-library/save-to-documents', methods=['POST'])
@login_required
def api_safety_osha_save_to_documents():
    """Download OSHA reference PDFs (bundled + official) into Documents › Safety › OSHA Reference."""
    import urllib.request
    from osha_library import OSHA_LIBRARY
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    body = request.get_json(silent=True) or {}
    keys = body.get('keys')
    saved, failed = [], []
    for item in OSHA_LIBRARY:
        if keys and item['key'] not in keys:
            continue
        data = None
        fname = item.get('bundled_file') or f"{item['key']}.pdf"
        # Prefer the bundled local file; fall back to the official PDF URL.
        if item.get('bundled_file'):
            local = os.path.join(app.root_path, 'static', 'osha', item['bundled_file'])
            if os.path.isfile(local):
                with open(local, 'rb') as fh:
                    data = fh.read()
        if data is None and item.get('pdf_url'):
            try:
                req = urllib.request.Request(item['pdf_url'], headers={'User-Agent': 'CasePM/1.0'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
            except Exception:
                data = None
        if not data:
            failed.append(item['title'])
            continue
        try:
            doc = _mirror_to_system_subfolder(
                int(project_id), data, f"{item['pub'] + ' — ' if item.get('pub') else ''}{item['title']}", fname,
                'safety', 'OSHA Reference', 'Safety',
                {'osha_key': item['key'], 'source': 'OSHA', 'url': item.get('pdf_url') or item.get('topic_url')},
                is_system_locked=True, uploaded_by_id=current_user.id,
            )
            if doc and doc.get('id'):
                saved.append(item['title'])
            else:
                failed.append(item['title'])
        except Exception:
            failed.append(item['title'])
    return jsonify({'ok': True, 'saved': saved, 'failed': failed, 'saved_count': len(saved)})


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

        number = generate_next_number('SAF', SafetyReport, doc_type='safety')

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
        # Reverse sync: adjustments to delivery-linked tasks flow back to Deliveries.
        deliveries_updated = 0
        inspections_updated = 0
        meetings_updated = 0
        try:
            from deliveries_persistence import apply_schedule_to_deliveries
            deliveries_updated = apply_schedule_to_deliveries(payload, Delivery, db)
        except Exception:
            db.session.rollback()
        try:
            from permits_inspections_persistence import apply_schedule_to_items
            inspections_updated = apply_schedule_to_items(payload, PermitInspectionItem, db)
        except Exception:
            db.session.rollback()
        try:
            from meeting_minutes_persistence import apply_schedule_to_meetings
            meetings_updated = apply_schedule_to_meetings(payload, MeetingMinute, db)
        except Exception:
            db.session.rollback()
        return jsonify({
            'ok': True, 'project_id': project_id,
            'deliveries_updated': deliveries_updated,
            'inspections_updated': inspections_updated,
            'meetings_updated': meetings_updated,
        })
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
    from companies_persistence import ensure_company_schema, serialize_company
    ensure_company_schema(db)
    companies = Company.query.order_by(Company.name.asc()).all()
    companies_for_js = []
    for c in companies:
        row = serialize_company(c)
        row['server_id'] = c.id
        companies_for_js.append(row)
    return render_template('companies.html', companies=companies, companies_for_js=companies_for_js)


@app.route('/api/companies', methods=['GET'])
@login_required
def api_companies_list():
    from companies_persistence import ensure_company_schema, serialize_company, projects_for_company
    ensure_company_schema(db)
    rows = Company.query.order_by(Company.name.asc()).all()
    include_projects = request.args.get('include_projects') == '1'
    out = []
    for c in rows:
        projs = projects_for_company(Project, c) if include_projects else None
        out.append(serialize_company(c, projects=projs))
    return jsonify({'ok': True, 'companies': out})


@app.route('/api/companies/<int:company_id>/users', methods=['GET'])
@login_required
def api_company_linked_users(company_id):
    """Users linked to a company (for Companies → Who to Contact)."""
    from sqlalchemy import func
    company = Company.query.get_or_404(company_id)
    rows = User.query.filter(
        User.status == 'Active',
        (
            (User.company_id == company_id)
            | (func.lower(User.company) == company.name.lower())
            | (User.id == company.primary_contact_user_id)
            | (User.id == company.financial_contact_user_id)
        ),
    ).order_by(User.last_name, User.first_name).all()
    users = []
    for u in rows:
        users.append({
            'id': u.id,
            'firstName': u.first_name,
            'lastName': u.last_name,
            'email': u.email,
            'phone': u.phone or '',
            'jobTitle': getattr(u, 'job_title', None) or '',
            'role': u.role or '',
            'company_id': u.company_id,
        })
    return jsonify({'ok': True, 'users': users})


@app.route('/api/companies/<int:company_id>/link-user', methods=['POST'])
@login_required
@users_module_required
def api_company_link_user(company_id):
    """Assign a user to this company (company membership lives on Companies, not User Management)."""
    company = Company.query.get_or_404(company_id)
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id')
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id required'}), 400
    user = User.query.get_or_404(user_id)
    user.company_id = company.id
    user.company = company.name
    db.session.commit()
    write_audit(
        'Linked user to company',
        f'{user.full_name} → {company.name}',
        module='companies',
        category='update',
        target_type='Company',
        target_id=company.id,
        commit=True,
    )
    return jsonify({'ok': True, 'user_id': user.id, 'company_id': company.id})


@app.route('/api/companies/<int:company_id>/unlink-user', methods=['POST'])
@login_required
@users_module_required
def api_company_unlink_user(company_id):
    """Remove a user's company membership and clear primary/financial contact if needed."""
    company = Company.query.get_or_404(company_id)
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id')
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id required'}), 400
    user = User.query.get_or_404(user_id)
    if user.company_id == company.id:
        user.company_id = None
        user.company = None
    if company.primary_contact_user_id == user_id:
        company.primary_contact_user_id = None
    if company.financial_contact_user_id == user_id:
        company.financial_contact_user_id = None
    db.session.commit()
    write_audit(
        'Unlinked user from company',
        f'{user.full_name} ← {company.name}',
        module='companies',
        category='update',
        target_type='Company',
        target_id=company.id,
        commit=True,
    )
    return jsonify({
        'ok': True,
        'user_id': user.id,
        'company_id': company.id,
        'primary_contact_user_id': company.primary_contact_user_id,
        'financial_contact_user_id': company.financial_contact_user_id,
    })


@app.route('/api/companies/<int:company_id>/set-contact', methods=['POST'])
@login_required
@users_module_required
def api_company_set_contact(company_id):
    """Designate primary or financial contact for a company."""
    company = Company.query.get_or_404(company_id)
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id')
    contact_type = (body.get('contact_type') or body.get('role') or '').strip().lower()
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id required'}), 400
    if contact_type not in ('primary', 'financial'):
        return jsonify({'error': 'contact_type must be primary or financial'}), 400
    user = User.query.get_or_404(user_id)
    if user.company_id != company.id:
        user.company_id = company.id
        user.company = company.name
    if contact_type == 'primary':
        company.primary_contact_user_id = user_id
        if user.email:
            company.email = user.email
        if user.phone:
            company.phone = user.phone
    else:
        company.financial_contact_user_id = user_id
    try:
        from portal_sub_access import grant_company_contact_project_memberships
        grant_company_contact_project_memberships(user, company, db)
    except Exception:
        pass
    db.session.commit()
    write_audit(
        f'Set {contact_type} contact',
        f'{user.full_name} → {company.name}',
        module='companies',
        category='update',
        target_type='Company',
        target_id=company.id,
        commit=True,
    )
    from companies_persistence import serialize_company
    return jsonify({'ok': True, 'company': serialize_company(company)})


@app.route('/api/companies/<int:company_id>/projects', methods=['GET'])
@login_required
def api_company_projects(company_id):
    from companies_persistence import projects_for_company
    company = Company.query.get_or_404(company_id)
    return jsonify({'ok': True, 'projects': projects_for_company(Project, company)})


@app.route('/api/companies/sync', methods=['POST'])
@login_required
def api_sync_company():
    """Upsert a company from the Companies UI (localStorage) into the database."""
    from companies_persistence import ensure_company_schema, apply_company_payload, serialize_company
    ensure_company_schema(db)
    body = request.get_json(silent=True) or {}
    name = (body.get('company_name') or body.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Company name is required'}), 400

    from sqlalchemy import func
    existing = Company.query.filter(func.lower(Company.name) == name.lower()).first()
    if existing:
        company = existing
    else:
        company = Company(name=name)
        db.session.add(company)

    apply_company_payload(company, body)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'ok': True,
        'company': serialize_company(company),
    })


@app.route('/api/sage/companies', methods=['GET'])
@login_required
def api_sage_companies_list():
    """Simple Sage vendor/customer directory for Companies import."""
    from companies_persistence import ensure_company_schema
    from sage_companies_service import list_sage_companies

    ensure_company_schema(db)
    search = (request.args.get('search') or '').strip()
    company_type = (request.args.get('company_type') or '').strip()
    rows = list_sage_companies(search=search, company_type=company_type, Company=Company)
    return jsonify({'ok': True, 'companies': rows, 'live_api': bool(os.environ.get('SAGE_API_URL', '').strip())})


@app.route('/api/sage/companies/lookup', methods=['GET'])
@login_required
def api_sage_company_lookup():
    """Look up a single Sage vendor/customer # and return name + basics."""
    from companies_persistence import ensure_company_schema
    from sage_companies_service import lookup_sage_company

    ensure_company_schema(db)
    code = (request.args.get('code') or request.args.get('sage_number') or '').strip()
    company_type = (request.args.get('company_type') or '').strip()
    if not code:
        return jsonify({'error': 'Sage number is required'}), 400
    match = lookup_sage_company(code, company_type=company_type, Company=Company)
    if not match:
        return jsonify({'ok': False, 'found': False, 'code': code}), 404
    return jsonify({'ok': True, 'found': True, 'company': match})


@app.route('/api/companies/clients', methods=['GET'])
@login_required
def api_client_companies():
    """Client / Owner companies for project dropdowns."""
    from companies_persistence import ensure_company_schema, serialize_company
    ensure_company_schema(db)
    rows = Company.query.order_by(Company.name.asc()).all()
    clients = []
    for c in rows:
        t = (c.type or '').lower()
        if not t or 'client' in t or 'owner' in t:
            clients.append(serialize_company(c))
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
@users_module_required
def user_management():
    from user_signature_persistence import ensure_user_signature_schema
    from user_permissions_persistence import catalog_payload
    from user_management_service import ensure_user_admin_schema, serialize_user, filter_users_for_actor
    from user_extended_prefs import NOTIFICATION_MODULES, HR_DOCUMENT_TYPES, LOCALE_OPTIONS, DATE_FORMAT_OPTIONS
    from developer_tools import is_developer, can_assign_developer_role
    ensure_user_signature_schema(db)
    ensure_user_admin_schema(db)
    users = filter_users_for_actor(User.query.order_by(User.created_at.desc()).all(), current_user)
    projects = Project.query.order_by(Project.name).all()
    projects_for_js = [{'id': p.id, 'name': p.name, 'number': p.number or '', 'status': p.status or ''} for p in projects]
    return render_template(
        'user_management.html',
        users=users,
        current_user_payload={
            'id': current_user.id,
            'email': current_user.email,
            'role': current_user.role,
            'full_name': current_user.full_name,
        },
        server_users_for_js=[u for u in (serialize_user(x, actor=current_user) for x in users) if u],
        projects_for_js=projects_for_js,
        notification_modules=NOTIFICATION_MODULES,
        hr_document_types=HR_DOCUMENT_TYPES,
        locale_options=LOCALE_OPTIONS,
        date_format_options=DATE_FORMAT_OPTIONS,
        permissions_catalog=catalog_payload(),
        is_admin_user=True,
        can_assign_developer_role=can_assign_developer_role(current_user),
        is_developer_user=is_developer(current_user),
    )


@app.route('/api/users', methods=['GET'])
@login_required
@users_module_required
def api_users_admin_list():
    from user_management_service import ensure_user_admin_schema, serialize_user, filter_users_for_actor
    from developer_tools import can_assign_developer_role
    ensure_user_admin_schema(db)
    rows = filter_users_for_actor(User.query.order_by(User.last_name, User.first_name).all(), current_user)
    return jsonify({
        'ok': True,
        'users': [u for u in (serialize_user(x, actor=current_user) for x in rows) if u],
        'can_assign_developer_role': can_assign_developer_role(current_user),
    })


@app.route('/api/users', methods=['POST'])
@login_required
@users_module_required
def api_users_create():
    from user_management_service import create_user, ensure_user_admin_schema, serialize_user
    ensure_user_admin_schema(db)
    body = request.get_json(silent=True) or {}
    try:
        user, generated_password = create_user(db, User, Company, body, actor_id=current_user.id, actor=current_user)
        db.session.commit()
        write_audit(
            'Created user',
            f'{user.full_name} ({user.email})',
            module='users',
            category='create',
            target_type='User',
            target_id=user.id,
            commit=True,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500
    payload = serialize_user(user, include_permissions=True)
    if generated_password:
        payload['generated_password'] = generated_password
    return jsonify({'ok': True, 'user': payload})


@app.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
@users_module_required
def api_users_get(user_id):
    from user_management_service import serialize_user
    from developer_tools import is_developer
    user = User.query.get_or_404(user_id)
    if user.role == 'Developer' and not is_developer(current_user):
        return jsonify({'error': 'Not found'}), 404
    payload = serialize_user(user, include_permissions=True, actor=current_user)
    if not payload:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'ok': True, 'user': payload})


@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@users_module_required
def api_users_update(user_id):
    from user_management_service import serialize_user, update_user
    user = User.query.get_or_404(user_id)
    body = request.get_json(silent=True) or {}
    try:
        update_user(db, User, Company, user, body, actor=current_user)
        db.session.commit()
        write_audit(
            'Updated user',
            f'{user.full_name} ({user.email})',
            module='users',
            category='update',
            target_type='User',
            target_id=user.id,
            commit=True,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'user': serialize_user(user, include_permissions=True)})


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@users_module_required
def api_users_delete(user_id):
    from developer_tools import is_developer, can_assign_developer_role
    if user_id == current_user.id:
        return jsonify({'error': 'You cannot delete your own account.'}), 400
    user = User.query.get_or_404(user_id)
    if user.role == 'Developer' and not can_assign_developer_role(current_user):
        return jsonify({'error': 'Only a developer can remove Developer accounts.'}), 403
    name = user.full_name
    email = user.email
    db.session.delete(user)
    db.session.commit()
    write_audit('Deleted user', f'{name} ({email})', module='users', category='delete', commit=True)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@users_module_required
def api_users_reset_password(user_id):
    from user_management_service import reset_user_password
    user = User.query.get_or_404(user_id)
    body = request.get_json(silent=True) or {}
    try:
        temp_password = reset_user_password(user, body.get('password'))
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    write_audit(
        'Reset user password',
        user.email,
        module='users',
        category='settings',
        target_type='User',
        target_id=user.id,
        commit=True,
    )
    return jsonify({'ok': True, 'temp_password': temp_password, 'must_change_password': True})


@app.route('/api/permissions/catalog', methods=['GET'])
@login_required
@users_module_required
def api_permissions_catalog():
    from user_permissions_persistence import catalog_payload
    return jsonify({'ok': True, 'catalog': catalog_payload()})


@app.route('/api/permissions/template/<role_name>', methods=['GET'])
@login_required
@users_module_required
def api_permissions_template(role_name):
    from user_permissions_persistence import apply_role_template
    try:
        perms = apply_role_template(role_name)
        return jsonify({'ok': True, 'permissions': perms})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


@app.route('/api/users/<int:user_id>/permissions', methods=['GET'])
@login_required
@users_module_required
def api_get_user_permissions(user_id):
    from user_permissions_persistence import serialize_user_permissions
    user = User.query.get_or_404(user_id)
    return jsonify({'ok': True, **serialize_user_permissions(user)})


@app.route('/api/users/<int:user_id>/permissions', methods=['PUT'])
@login_required
@users_module_required
def api_save_user_permissions(user_id):
    from user_permissions_persistence import save_user_permissions, serialize_user_permissions
    user = User.query.get_or_404(user_id)
    body = request.get_json(silent=True) or {}
    perms = body.get('permissions') or body
    try:
        save_user_permissions(user, perms, db)
        db.session.commit()
        write_audit(
            'Updated user permissions',
            f'{user.full_name} ({user.email})',
            module='users',
            category='settings',
            target_type='User',
            target_id=user.id,
            commit=True,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, **serialize_user_permissions(user)})


@app.route('/api/users/me/signature', methods=['GET'])
@login_required
def api_my_signature():
    from user_signature_persistence import ensure_user_signature_schema, signature_public_view
    ensure_user_signature_schema(db)
    return jsonify({'ok': True, 'signature': signature_public_view(current_user)})


@app.route('/api/users/<int:user_id>/signature', methods=['GET'])
@login_required
def api_user_signature(user_id):
    from user_signature_persistence import ensure_user_signature_schema, signature_public_view
    ensure_user_signature_schema(db)
    user = User.query.get_or_404(user_id)
    return jsonify({'ok': True, 'signature': signature_public_view(user)})


@app.route('/api/users/<int:user_id>/signature/image', methods=['GET'])
@login_required
def api_user_signature_image(user_id):
    from user_signature_persistence import ensure_user_signature_schema
    ensure_user_signature_schema(db)
    user = User.query.get_or_404(user_id)
    path = getattr(user, 'signature_path', None)
    if not path or not os.path.isfile(path):
        return jsonify({'error': 'No signature on file'}), 404
    from flask import send_file
    return send_file(path, mimetype='image/png', max_age=3600)


@app.route('/api/users/me/signature', methods=['PUT'])
@login_required
def api_save_my_signature():
    """Only the authenticated user may update their own signature — admins cannot override."""
    from user_signature_persistence import ensure_user_signature_schema, save_user_signature, signature_public_view
    ensure_user_signature_schema(db)
    body = request.get_json(silent=True) or {}
    data_url = body.get('signature_png') or body.get('signatureDataURL') or body.get('data_url')
    if not data_url:
        return jsonify({'error': 'signature_png is required'}), 400
    try:
        save_user_signature(
            current_user,
            data_url,
            legal_name=body.get('legal_name'),
            initials=body.get('initials'),
        )
        cert_name = (body.get('certificate_file_name') or '').strip()
        if cert_name:
            import json as _json
            current_user.certificate_meta_json = _json.dumps({
                'file_name': cert_name,
                'uploaded_at': datetime.utcnow().isoformat() + 'Z',
                'note': 'Certificate metadata only — private keys are never stored on server',
            })
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500
    return jsonify({'ok': True, 'signature': signature_public_view(current_user)})


@app.route('/api/users/me/signature/audit', methods=['GET'])
@login_required
def api_my_signature_audit():
    from user_signature_persistence import ensure_user_signature_schema
    ensure_user_signature_schema(db)
    try:
        audit = json.loads(current_user.signature_audit_json or '[]')
    except (TypeError, json.JSONDecodeError):
        audit = []
    return jsonify({'ok': True, 'audit': audit[:50]})


@app.route('/api/users/me/stamp', methods=['GET'])
@login_required
def api_my_stamp():
    from user_signature_persistence import ensure_user_signature_schema, stamp_public_view
    ensure_user_signature_schema(db)
    return jsonify({'ok': True, 'stamp': stamp_public_view(current_user)})


@app.route('/api/users/<int:user_id>/stamp', methods=['GET'])
@login_required
def api_user_stamp(user_id):
    from user_signature_persistence import ensure_user_signature_schema, stamp_public_view
    ensure_user_signature_schema(db)
    user = User.query.get_or_404(user_id)
    return jsonify({'ok': True, 'stamp': stamp_public_view(user)})


@app.route('/api/users/<int:user_id>/stamps', methods=['GET'])
@login_required
def api_user_stamps(user_id):
    """Read-only list of another user's approval stamps."""
    from user_signature_persistence import ensure_user_signature_schema, stamps_public_view
    ensure_user_signature_schema(db)
    user = User.query.get_or_404(user_id)
    return jsonify({'ok': True, **stamps_public_view(user)})


@app.route('/api/users/<int:user_id>/stamp/image', methods=['GET'])
@login_required
def api_user_stamp_image(user_id):
    from user_signature_persistence import ensure_user_signature_schema, stamp_file_path
    ensure_user_signature_schema(db)
    user = User.query.get_or_404(user_id)
    path = stamp_file_path(user)
    if not path or not os.path.isfile(path):
        return jsonify({'error': 'No stamp on file'}), 404
    from flask import send_file
    return send_file(path, mimetype='image/png', max_age=3600)


@app.route('/api/users/me/stamp', methods=['PUT'])
@login_required
def api_save_my_stamp():
    """Only the authenticated user may update their own approval stamp."""
    from user_signature_persistence import ensure_user_signature_schema, save_user_stamp
    ensure_user_signature_schema(db)
    body = request.get_json(silent=True) or {}
    data_url = body.get('stamp_png') or body.get('stampDataURL') or body.get('data_url')
    if not data_url:
        return jsonify({'error': 'stamp_png is required'}), 400
    try:
        stamp = save_user_stamp(current_user, data_url)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500
    return jsonify({'ok': True, **stamp} if isinstance(stamp, dict) and 'stamps' in stamp else {'ok': True, 'stamp': stamp.get('stamp') if isinstance(stamp, dict) else stamp})


@app.route('/api/users/me/stamps', methods=['GET'])
@login_required
def api_my_stamps():
    from user_signature_persistence import ensure_user_signature_schema, stamps_public_view
    ensure_user_signature_schema(db)
    return jsonify({'ok': True, **stamps_public_view(current_user)})


@app.route('/api/users/me/stamps', methods=['PUT'])
@login_required
def api_save_my_stamp_entry():
    from user_signature_persistence import ensure_user_signature_schema, save_user_stamp
    ensure_user_signature_schema(db)
    body = request.get_json(silent=True) or {}
    data_url = body.get('stamp_png') or body.get('stampDataURL') or body.get('data_url')
    if not data_url:
        return jsonify({'error': 'stamp_png is required'}), 400
    try:
        result = save_user_stamp(
            current_user,
            data_url,
            label=body.get('label'),
            stamp_id=body.get('stamp_id'),
            make_primary=bool(body.get('make_primary')),
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, **result})


@app.route('/api/users/me/stamps/<stamp_id>', methods=['DELETE'])
@login_required
def api_delete_my_stamp(stamp_id):
    from user_signature_persistence import ensure_user_signature_schema, delete_user_stamp
    ensure_user_signature_schema(db)
    try:
        result = delete_user_stamp(current_user, stamp_id)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, **result})


@app.route('/api/users/<int:user_id>/stamps/<stamp_id>/image', methods=['GET'])
@login_required
def api_user_stamp_entry_image(user_id, stamp_id):
    from user_signature_persistence import ensure_user_signature_schema, stamp_file_path
    ensure_user_signature_schema(db)
    user = User.query.get_or_404(user_id)
    path = stamp_file_path(user, stamp_id)
    if not path or not os.path.isfile(path):
        return jsonify({'error': 'No stamp on file'}), 404
    return send_file(path, mimetype='image/png', max_age=3600)


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


# ==================== PHOTOS MODULE ====================

def _photo_url_helpers():
    return {
        'doc': lambda doc_id: url_for('api_documents_download', doc_id=doc_id),
        'photo': lambda project_id, filename: url_for('serve_project_photo', project_id=project_id, filename=filename),
    }


@app.route('/photos')
@login_required
def photos_page():
    projects = Project.query.order_by(Project.name).all()
    return render_template('photos.html', projects=projects)


@app.route('/api/photos', methods=['GET'])
@login_required
def api_photos_list():
    from photo_persistence import (
        serialize_photo, group_photos_by_date, filter_photos_by_range, compute_photo_stats,
    )

    project = get_active_project()
    if not project:
        return jsonify({'photos': [], 'groups': [], 'stats': compute_photo_stats([])})

    q = Photo.query.filter_by(project_id=project.id).order_by(
        Photo.taken_date.desc(), Photo.created_at.desc()
    )
    search = (request.args.get('search') or '').strip().lower()
    location = (request.args.get('location') or '').strip().lower()
    date_range = (request.args.get('date_range') or '').strip()
    group_mode = (request.args.get('group') or 'day').strip() or 'day'
    if group_mode not in ('day', 'week', 'month'):
        group_mode = 'day'

    rows = q.all()
    serialized = [
        serialize_photo(p, url_helpers=_photo_url_helpers())
        for p in rows
    ]
    if search:
        serialized = [
            p for p in serialized
            if search in (p.get('caption') or '').lower()
            or search in (p.get('location') or '').lower()
            or search in (p.get('uploaded_by') or '').lower()
        ]
    if location:
        serialized = [p for p in serialized if location in (p.get('location') or '').lower()]
    serialized = filter_photos_by_range(serialized, date_range)
    groups = group_photos_by_date(serialized, group_mode)
    stats = compute_photo_stats(serialized)
    return jsonify({
        'ok': True,
        'project_id': project.id,
        'photos': serialized,
        'groups': groups,
        'stats': stats,
        'group_mode': group_mode,
    })


@app.route('/api/photos', methods=['POST'])
@login_required
def api_photos_upload():
    from photo_persistence import serialize_photo

    project = get_active_project()
    if not project:
        return jsonify({'error': 'Select a project first'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400

    custom_name = (request.form.get('name') or request.form.get('caption') or '').strip()
    location = (request.form.get('location') or '').strip()
    taken_date_str = (request.form.get('taken_date') or '').strip()
    taken_date = None
    if taken_date_str:
        try:
            taken_date = datetime.strptime(taken_date_str[:10], '%Y-%m-%d').date()
        except ValueError:
            taken_date = date.today()
    else:
        taken_date = date.today()

    _, ext = os.path.splitext(f.filename)
    if not ext:
        ext = '.jpg'
    if custom_name:
        base = secure_filename(custom_name) or 'photo'
        display_name = custom_name if custom_name.lower().endswith(ext.lower()) else f'{custom_name}{ext}'
        safe = f'{base}{ext.lower()}'
    else:
        safe = secure_filename(f.filename)
        display_name = f.filename

    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', str(project.id))
    os.makedirs(folder, exist_ok=True)
    if os.path.exists(os.path.join(folder, safe)):
        base, ext2 = os.path.splitext(safe)
        safe = f'{base}-{int(datetime.utcnow().timestamp())}{ext2}'
    path = os.path.join(folder, safe)
    f.save(path)

    now = datetime.utcnow()
    photo = Photo(
        project_id=project.id,
        filename=safe,
        caption=custom_name or display_name,
        location=location or None,
        category=location or None,
        taken_date=taken_date,
        taken_at=now,
        uploaded_by_id=current_user.id,
    )
    db.session.add(photo)
    db.session.commit()

    try:
        with open(path, 'rb') as fh:
            fb = fh.read()
        sub_name = taken_date.strftime('%m-%d-%Y')
        doc = _mirror_to_system_subfolder(
            project.id, fb, display_name, f.filename, 'photos', sub_name, 'Photo',
            {
                'photo_id': photo.id,
                'caption': photo.caption,
                'location': location,
                'taken_date': taken_date.isoformat(),
                'photo_label': custom_name or display_name,
            },
            is_system_locked=True, uploaded_by_id=current_user.id,
        )
        if doc and doc.get('id'):
            photo.document_id = doc['id']
            db.session.commit()
        _notify_documents_team(
            project.id,
            'Photo filed to Documents',
            f'"{photo.caption}" filed to Documents › Photos › {sub_name}.',
            f'/documents?project_id={project.id}',
        )
    except Exception:
        db.session.rollback()

    return jsonify({
        'ok': True,
        'photo': serialize_photo(photo, user=current_user, url_helpers=_photo_url_helpers()),
    })


@app.route('/api/photos/<int:photo_id>', methods=['GET'])
@login_required
def api_photo_get(photo_id):
    from photo_persistence import serialize_photo

    photo = Photo.query.get_or_404(photo_id)
    project = get_active_project()
    if project and photo.project_id != project.id:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'ok': True, 'photo': serialize_photo(photo, url_helpers=_photo_url_helpers())})


@app.route('/api/photos/<int:photo_id>', methods=['DELETE'])
@login_required
def api_photo_delete(photo_id):
    photo = Photo.query.get_or_404(photo_id)
    project = get_active_project()
    if project and photo.project_id != project.id:
        return jsonify({'error': 'Not found'}), 404
    try:
        folder = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', str(photo.project_id))
        file_path = os.path.join(folder, photo.filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    except OSError:
        pass
    db.session.delete(photo)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/uploads/photos/<int:project_id>/<path:filename>')
@login_required
def serve_project_photo(project_id, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', str(project_id))
    return send_from_directory(folder, filename)


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
        ensure_document_schema, ensure_system_folders, resolve_my_files_folder, document_folder,
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
            mine = resolve_my_files_folder(db, DocumentFolder, int(project_id), current_user.id, Document=Document, User=User)
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
    """Return (response, status_code) if edits are blocked by checkout or submittal lock, else None."""
    if doc.is_system_locked:
        return None
    try:
        from submittal_persistence import document_linked_to_locked_submittal
        locked_sub = document_linked_to_locked_submittal(
            doc.id, Submittal=Submittal, project_id=getattr(doc, 'project_id', None),
        )
        if locked_sub:
            return jsonify({
                'error': (
                    f'This document is attached to approved submittal '
                    f'{locked_sub.number or locked_sub.id} and cannot be marked up.'
                ),
                'submittal_id': locked_sub.id,
                'submittal_status': locked_sub.status,
            }), 423
    except Exception:
        pass
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


def _documents_privileged():
    from developer_tools import is_admin_or_developer
    return is_admin_or_developer(current_user)


def _folder_owner_name(owner_id):
    if not owner_id:
        return None
    u = User.query.get(int(owner_id))
    return u.full_name if u else None


def _effective_my_files_user_id(project_id=None):
    from document_persistence import ensure_user_my_files_folder

    pid = int(project_id or get_current_project_id() or 0)
    requested = request.args.get('my_files_user_id', type=int)
    if not requested and request.method in ('POST', 'PUT', 'PATCH') and request.is_json:
        body = request.get_json(silent=True) or {}
        requested = body.get('my_files_user_id')
    if requested and _documents_privileged() and pid:
        ensure_user_my_files_folder(db, DocumentFolder, pid, int(requested), Document=Document, User=User)
        return int(requested)
    return current_user.id


def _folder_visible_in_browser(folder) -> bool:
    from document_persistence import (
        MY_FILES_LEGACY_KEY,
        folder_my_files_owner,
        is_my_files_system_key,
    )

    key = getattr(folder, 'system_key', None)
    if key == MY_FILES_LEGACY_KEY:
        return _documents_privileged()
    owner = folder_my_files_owner(db, DocumentFolder, folder.id)
    if owner is not None:
        return owner == current_user.id or _documents_privileged()
    if is_my_files_system_key(key) and folder.parent_id is None:
        return False
    return True


def _documents_my_files_context(project_id: int) -> dict:
    from document_persistence import ensure_user_my_files_folder, list_my_files_owners, resolve_my_files_folder

    uid = _effective_my_files_user_id(project_id)
    ensure_user_my_files_folder(db, DocumentFolder, int(project_id), uid, Document=Document, User=User)
    mine = resolve_my_files_folder(db, DocumentFolder, int(project_id), uid, Document=Document, User=User)
    ctx = {
        'my_files_user_id': uid,
        'my_files_folder_id': mine.id if mine else None,
        'can_browse_other_my_files': _documents_privileged(),
    }
    if _documents_privileged():
        ctx['my_files_owners'] = list_my_files_owners(db, DocumentFolder, int(project_id), User=User)
    return ctx


def _folder_access(folder, required='view'):
    """Check folder permission. No rows = open to all project users; Admin/PM always allowed."""
    from document_persistence import folder_my_files_owner

    if not folder or not current_user.is_authenticated:
        return False

    mf_owner = folder_my_files_owner(db, DocumentFolder, folder.id)
    if mf_owner is not None:
        if mf_owner == current_user.id:
            return True
        if _documents_privileged():
            return True
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
    preserve_original_filename=False,
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
            preserve_original_filename=preserve_original_filename,
        )
    except ValueError:
        return None


def _mirror_to_system_nested_subfolder(
    project_id,
    file_bytes,
    name,
    original_filename,
    system_folder_key,
    subfolder_path,
    document_type='Other',
    source_metadata=None,
    is_system_locked=True,
    uploaded_by_id=None,
    preserve_original_filename=False,
):
    """Mirror into Documents › system folder › nested subfolders (e.g. Safety › Reports › Report #1)."""
    from document_persistence import (
        ensure_system_folders, resolve_folder_by_key, get_or_create_child_folder,
    )

    actor = _acting_user_id(uploaded_by_id)
    ensure_system_folders(db, DocumentFolder, int(project_id), actor, Document=Document)
    parent = resolve_folder_by_key(db, DocumentFolder, int(project_id), system_folder_key)
    if not parent:
        return None
    current = parent
    path_names = [p for p in (subfolder_path or []) if (p or '').strip()]
    for part in path_names:
        current = get_or_create_child_folder(
            db, DocumentFolder, int(project_id), current.id, part.strip(), actor,
        )
    db.session.commit()
    meta = {
        **(source_metadata or {}),
        'mirrored_from_module': True,
        'system_folder_key': system_folder_key,
        'subfolder_path': path_names,
    }
    try:
        from document_integration import guess_mime
        return _save_document_bytes(
            int(project_id), file_bytes, name, original_filename,
            guess_mime(original_filename), document_type, current.id, bool(is_system_locked),
            None, None, meta, uploaded_by_id=actor,
            preserve_original_filename=preserve_original_filename,
        )
    except ValueError:
        return None


def _safety_report_doc_subfolder(r):
    """Documents › Safety › Reports & Observations › {report folder}."""
    sub_name = (r.number or f'SAF-{r.id}').strip()
    rtype = (r.type or 'Report').strip()
    return ['Reports & Observations', f'Report #{r.id} — {sub_name} ({rtype})']


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
        ('safety_report', 'report_date', 'DATE'),
        ('safety_report', 'attachments_json', 'TEXT'),
        ('safety_report', 'details_json', 'TEXT'),
        ('meeting_minute', 'toolbox_meta_json', 'TEXT'),
        ('photo', 'document_id', 'INTEGER'),
        ('photo', 'location', 'VARCHAR(150)'),
        ('photo', 'taken_date', 'DATE'),
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
    preserve_original_filename: bool = False,
):
    from document_features import file_content_hash, project_document_settings, retention_until_from_years, parse_tags
    from document_persistence import document_folder, ensure_system_folders, resolve_my_files_folder

    ensure_project_schema()
    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    actor_id = _acting_user_id(uploaded_by_id)
    ensure_system_folders(db, DocumentFolder, project_id, actor_id, Document=Document)
    if not folder_id:
        default_folder = resolve_my_files_folder(db, DocumentFolder, project_id, actor_id, Document=Document, User=User)
        folder_id = default_folder.id if default_folder else None
    elif folder_id:
        target = DocumentFolder.query.get(int(folder_id))
        if target and not _folder_access(target, 'upload'):
            raise ValueError('You do not have permission to upload to this folder')

    ext = original_filename.rsplit('.', 1)[-1].lower() if original_filename and '.' in original_filename else 'bin'
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f'File type .{ext} not allowed')

    folder_path = document_folder(upload_root, int(project_id))
    if preserve_original_filename:
        base_name = secure_filename(original_filename or name or f'file.{ext}')
        if not base_name:
            base_name = f'file.{ext}'
        stored_name = base_name
        file_path = os.path.join(folder_path, stored_name)
        if os.path.exists(file_path):
            stem, dot, suffix = stored_name.rpartition('.')
            stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            stored_name = f'{stem}-{stamp}{dot}{suffix}' if dot else f'{stored_name}-{stamp}'
            file_path = os.path.join(folder_path, stored_name)
    else:
        stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        stored_name = f'{stamp}_{secure_filename(name).replace(" ", "_")[:80]}.{ext}'
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
    from document_persistence import ensure_system_folders, folder_my_files_owner, folder_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    all_folders = _active_folders().filter_by(project_id=int(project_id)).order_by(
        DocumentFolder.is_system.desc(), DocumentFolder.name,
    ).all()
    all_folders = [f for f in all_folders if _folder_visible_in_browser(f)]
    by_parent: dict = {}
    for f in all_folders:
        by_parent.setdefault(f.parent_id, []).append(f)
    viewer_id = current_user.id

    def build_node(folder):
        owner = folder_my_files_owner(db, DocumentFolder, folder.id)
        children = [build_node(c) for c in by_parent.get(folder.id, [])]
        file_count = _active_documents().filter_by(folder_id=folder.id).count()
        node = folder_to_dict(
            folder, len(children), file_count,
            viewer_user_id=viewer_id,
            owner_name=_folder_owner_name(owner),
        )
        node['children'] = children
        return node

    roots = [build_node(f) for f in by_parent.get(None, [])]
    payload = {'ok': True, 'tree': roots}
    payload.update(_documents_my_files_context(int(project_id)))
    return jsonify(payload)


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
        if not _folder_access(parent, 'upload'):
            return jsonify({'error': 'No permission to create folders here'}), 403
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
    if not _folder_access(folder, 'manage'):
        return jsonify({'error': 'No permission to modify this folder'}), 403
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
            if not _folder_access(parent, 'upload'):
                return jsonify({'error': 'No permission to move folder here'}), 403
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
    if not _folder_access(folder, 'manage'):
        return jsonify({'error': 'No permission to delete this folder'}), 403
    if _active_folders().filter_by(parent_id=folder.id).count():
        return jsonify({'error': 'Folder is not empty (contains subfolders)'}), 400
    if _active_documents().filter_by(folder_id=folder.id).count():
        return jsonify({'error': 'Folder is not empty (contains files)'}), 400
    folder.deleted_at = datetime.utcnow()
    _log_doc_activity(folder.project_id, 'delete', folder_id=folder.id, detail={'name': folder.name})
    db.session.commit()
    return jsonify({'ok': True})


def _folder_preview_thumbs(folder_id, project_id, limit=3):
    """Up to three miniature preview items for Windows-style folder thumbnails."""
    from document_persistence import _editor_kind_for
    docs = (
        _active_documents()
        .filter_by(folder_id=folder_id, project_id=project_id)
        .order_by(Document.updated_at.desc())
        .limit(24)
        .all()
    )
    thumbs = []
    for doc in docs:
        if len(thumbs) >= limit:
            break
        mime = (doc.mime_type or '').lower()
        name = (doc.original_filename or doc.filename or doc.name or '').lower()
        kind = _editor_kind_for(doc)
        if mime.startswith('image/') or any(name.endswith(x) for x in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            thumbs.append({
                'type': 'image',
                'url': f'/uploads/documents/{doc.project_id}/{doc.filename}',
                'name': doc.name,
            })
        elif 'pdf' in mime or name.endswith('.pdf'):
            thumbs.append({'type': 'pdf', 'doc_id': doc.id, 'name': doc.name})
        elif kind == 'sheet':
            thumbs.append({'type': 'sheet', 'doc_id': doc.id, 'name': doc.name})
        elif kind == 'doc':
            thumbs.append({'type': 'doc', 'doc_id': doc.id, 'name': doc.name})
    return thumbs


@app.route('/api/documents/browse', methods=['GET'])
@login_required
def api_documents_browse():
    from document_persistence import document_to_dict, ensure_system_folders, folder_my_files_owner, folder_to_dict

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    folder_id = request.args.get('folder_id')
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not Project.query.get(int(project_id)):
        return jsonify({'error': 'Project not found'}), 404
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    project = Project.query.get(int(project_id))
    viewer_id = current_user.id
    mf_ctx = _documents_my_files_context(int(project_id))

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
        if not _folder_visible_in_browser(f) or not _folder_access(f, 'view'):
            continue
        child_count = _active_folders().filter_by(parent_id=f.id).count()
        file_count = _active_documents().filter_by(folder_id=f.id).count()
        preview_thumbs = _folder_preview_thumbs(f.id, f.project_id)
        owner = folder_my_files_owner(db, DocumentFolder, f.id)
        folder_nodes.append(folder_to_dict(
            f, child_count, file_count, preview_thumbs,
            viewer_user_id=viewer_id,
            owner_name=_folder_owner_name(owner),
        ))

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
        for f in chain:
            owner = folder_my_files_owner(db, DocumentFolder, f.id)
            breadcrumbs.append({
                'id': f.id,
                'name': folder_to_dict(f, viewer_user_id=viewer_id, owner_name=_folder_owner_name(owner))['name'],
                'is_system': f.is_system,
            })

    payload = {
        'ok': True,
        'project_id': int(project_id),
        'project_name': project.name if project else None,
        'folder_id': current_folder.id if current_folder else None,
        'breadcrumbs': breadcrumbs,
        'folders': folder_nodes,
        'files': [_document_dict_with_user(d) for d in docs],
    }
    payload.update(mf_ctx)
    return jsonify(payload)


@app.route('/api/documents/my-files-owners', methods=['GET'])
@login_required
def api_documents_my_files_owners():
    from document_persistence import ensure_system_folders, list_my_files_owners

    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not _documents_privileged():
        return jsonify({'error': 'Admin or Developer access required'}), 403
    ensure_system_folders(db, DocumentFolder, project_id, current_user.id, Document=Document)
    owners = list_my_files_owners(db, DocumentFolder, int(project_id), User=User)
    return jsonify({'ok': True, 'owners': owners, 'project_id': int(project_id)})


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

    if folder_id:
        target = DocumentFolder.query.get(int(folder_id))
        if target and not _folder_access(target, 'upload'):
            return jsonify({'error': 'No permission to upload to this folder'}), 403

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
    """Save a print/PDF output into the locked Printed Output system folder (legacy alias)."""
    body = request.get_json(silent=True) or {}
    if not body.get('mime_type'):
        body = dict(body)
        body['mime_type'] = 'application/pdf'
    return _api_documents_save_output_impl(body)


@app.route('/api/documents/save-output', methods=['POST'])
@login_required
def api_documents_save_output():
    """Save print/export output into Documents (Printed Output or a module system folder)."""
    body = request.get_json(silent=True) or {}
    return _api_documents_save_output_impl(body)


def _api_documents_save_output_impl(body):
    import base64 as b64mod
    from document_persistence import resolve_folder_by_key

    project_id = body.get('project_id') or get_current_project_id()
    name = (body.get('name') or 'Printed document').strip()
    file_data = body.get('file_base64') or body.get('pdf_base64')
    mime_type = (body.get('mime_type') or 'application/pdf').strip().lower()
    source_module = body.get('source_module') or 'export'
    system_folder_key = (body.get('system_folder_key') or 'printed-output').strip()
    subfolder = (body.get('subfolder') or '').strip() or None
    extension = (body.get('extension') or '').strip().lstrip('.')

    if not project_id or not file_data:
        return jsonify({'error': 'project_id and file_base64 required'}), 400
    if ',' in str(file_data):
        file_data = str(file_data).split(',', 1)[1]
    try:
        file_bytes = b64mod.b64decode(file_data)
    except Exception:
        return jsonify({'error': 'Invalid file data'}), 400
    if not file_bytes:
        return jsonify({'error': 'Empty file'}), 400

    ext_map = {
        'application/pdf': 'pdf',
        'text/html': 'html',
        'text/plain': 'txt',
        'text/csv': 'csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
        'application/vnd.ms-excel': 'xls',
    }
    ext = extension or ext_map.get(mime_type, 'bin')
    safe_base = secure_filename(name) or 'export'
    if not safe_base.lower().endswith('.' + ext):
        fname = f'{safe_base}.{ext}'
    else:
        fname = safe_base

    doc_type = 'Printed' if system_folder_key == 'printed-output' else 'Export'
    meta = {
        'source_module': source_module,
        'saved_at': datetime.utcnow().isoformat(),
        'mime_type': mime_type,
    }

    if subfolder:
        doc = _mirror_to_system_subfolder(
            int(project_id), file_bytes, name, fname,
            system_folder_key, subfolder, doc_type,
            meta, is_system_locked=True, uploaded_by_id=current_user.id,
        )
    else:
        folder = resolve_folder_by_key(db, DocumentFolder, int(project_id), system_folder_key)
        if not folder:
            return jsonify({'error': f'System folder "{system_folder_key}" missing'}), 500
        try:
            doc = _save_document_bytes(
                int(project_id), file_bytes, name, fname,
                mime_type, doc_type, folder.id, True,
                source_metadata=meta,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    if doc and doc.get('id'):
        _notify_documents_team(
            int(project_id),
            'Output saved to Documents',
            f'"{name}" filed to Documents.',
            f'/documents?project_id={project_id}',
        )
    return jsonify({'ok': True, 'document': doc}), 201


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
    if doc.is_system_locked and not _developer_unlock_bypass():
        if 'name' in body and body.get('name') and body['name'] != doc.name:
            return jsonify({'error': 'Locked job files cannot be renamed'}), 403
        if 'folder_id' in body:
            new_fid = int(body['folder_id']) if body['folder_id'] else None
            if new_fid != doc.folder_id:
                return jsonify({'error': 'Locked job files cannot be moved'}), 403
    if 'name' in body and body['name']:
        doc.name = str(body['name']).strip()[:300]
    if 'folder_id' in body and (not doc.is_system_locked or _developer_unlock_bypass()):
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
    if doc.is_system_locked and not _developer_unlock_bypass():
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
    from financial_security import require_financial_project_access
    doc = Document.query.get_or_404(doc_id)
    try:
        require_financial_project_access(current_user, doc.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
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
    if doc.is_system_locked and not _developer_unlock_bypass():
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
    if doc.is_system_locked and not _developer_unlock_bypass():
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
            if (doc.is_system_locked and not _developer_unlock_bypass()) or doc.legal_hold:
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
            if (doc.is_system_locked and not _developer_unlock_bypass()) or doc.legal_hold:
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


@app.route('/api/submittals', methods=['GET'])
@login_required
def api_list_submittals():
    """List submittals for the active project. Sub portal users only see assigned items."""
    from submittal_persistence import submittal_to_ui_item
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user, submittal_assigned_to_user
    from financial_security import require_financial_project_access
    from co_persistence import user_can_act_on_ball_in_court
    try:
        assert_submittal_read_allowed(current_user)
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        require_financial_project_access(current_user, int(project_id), Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    rows = Submittal.query.filter_by(project_id=int(project_id)).order_by(Submittal.created_at.desc()).all()
    items = []
    for row in rows:
        if not submittal_visible_to_user(row, current_user, Company=Company, db=db):
            continue
        item = submittal_to_ui_item(row)
        item['assignedToMe'] = submittal_assigned_to_user(row, current_user, Company=Company, db=db)
        item['canActOnBall'] = user_can_act_on_ball_in_court(current_user, row.ball_in_court)
        items.append(item)
    return jsonify({'ok': True, 'submittals': items})


@app.route('/api/submittals/sync', methods=['POST'])
@login_required
def api_submittal_sync():
    """Upsert a submittal from the UI and return server id for attachments."""
    from submittal_persistence import apply_submittal_fields
    from financial_security import require_financial_project_access, assert_mutable_submittal
    from document_module_security import (
        assert_submittal_create_allowed,
        assert_submittal_edit_allowed,
        is_staff_portal_user,
    )
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    number = (body.get('number') or '').strip()
    description = (body.get('description') or body.get('subject') or 'Submittal').strip()
    if not project_id or not number:
        return jsonify({'error': 'project_id and number required'}), 400
    try:
        require_financial_project_access(current_user, int(project_id), Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    submittal = Submittal.query.filter_by(project_id=int(project_id), number=number).first()
    if not submittal:
        try:
            assert_submittal_create_allowed(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        submittal = Submittal(
            project_id=int(project_id),
            number=number,
            description=description[:200],
            spec_section=body.get('spec_section'),
            status='Draft',
            priority=body.get('priority') or 'Medium',
            submitted_by=body.get('submitted_by') or _user_display_name(current_user.id),
            date=datetime.utcnow().date(),
        )
        apply_submittal_fields(submittal, body, is_create=True)
        db.session.add(submittal)
    else:
        try:
            assert_mutable_submittal(submittal)
            assert_submittal_edit_allowed(current_user, submittal, Company=Company, db=db)
        except (ValueError, PermissionError) as exc:
            return jsonify({'error': str(exc)}), 400 if isinstance(exc, ValueError) else 403
        patch = dict(body)
        if not is_staff_portal_user(current_user):
            from submittal_persistence import apply_submittal_sub_sync_fields
            apply_submittal_sub_sync_fields(submittal, patch)
        else:
            apply_submittal_fields(submittal, patch, is_create=False)
    db.session.commit()
    from rfi_persistence import _parse_json
    attachments = _parse_json(submittal.attachments_json, [])
    return jsonify({
        'ok': True,
        'submittal_id': submittal.id,
        'number': submittal.number,
        'status': submittal.status,
        'attachments': attachments,
    })


@app.route('/api/submittals/<int:submittal_id>/workflow', methods=['POST'])
@login_required
def api_submittal_workflow(submittal_id):
    from submittal_persistence import submittal_workflow_action
    from financial_security import require_financial_project_access
    from workflow_responder import notify_submittal_ball_in_court, notify_submittal_update
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    old_status = submittal.status
    revision_submittal = None
    try:
        new_status, revision_submittal = submittal_workflow_action(
            submittal, action, current_user, body, Company=Company, db=db, Submittal=Submittal,
        )
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403 if isinstance(exc, PermissionError) else 400
    db.session.commit()
    try:
        if action == 'send_to_sub':
            notify_submittal_update(
                submittal, User,
                title=f'{submittal.number} — submittal assigned to subcontractor',
                description=(
                    f'Please prepare and return submittal {submittal.number}'
                    f' ({submittal.description or ""}).'
                ),
                actor_id=current_user.id,
                event='assigned',
            )
            notify_submittal_ball_in_court(submittal, User)
        elif action == 'return_from_sub':
            notify_submittal_update(
                submittal, User,
                title=f'{submittal.number} — returned from subcontractor',
                description='The subcontractor returned this submittal for PM review.',
                actor_id=current_user.id,
                event='submit',
            )
            notify_submittal_ball_in_court(submittal, User)
        elif new_status != old_status:
            notify_submittal_ball_in_court(submittal, User)
    except Exception:
        pass
    payload = {'ok': True, 'new_status': new_status, 'submittal_id': submittal.id}
    if revision_submittal is not None:
        from submittal_persistence import submittal_to_ui_item
        payload['revision_submittal'] = submittal_to_ui_item(revision_submittal)
        payload['revision_submittal_id'] = revision_submittal.id
    return jsonify(payload)


@app.route('/api/submittals/<int:submittal_id>/print-form', methods=['GET'])
@login_required
def api_submittal_print_form(submittal_id):
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    from program_settings_persistence import load_company_info
    from submittal_form_pdf import build_submittal_print_pdf
    import io

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        assert_submittal_read_allowed(current_user)
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    from rfi_persistence import _parse_json
    attachments = _parse_json(submittal.attachments_json, [])
    project = Project.query.get(submittal.project_id)
    template_path = os.path.join(app.static_folder, 'forms', 'Submittal_Form.pdf')
    try:
        pdf_bytes = build_submittal_print_pdf(
            submittal,
            project=project,
            company_info=load_company_info(),
            attachments=attachments,
            upload_folder=app.config['UPLOAD_FOLDER'],
            Document=Document,
            DocumentMarkup=DocumentMarkup,
            template_path=template_path,
        )
    except FileNotFoundError as exc:
        return jsonify({'error': str(exc)}), 500
    except Exception as exc:
        return jsonify({'error': f'Could not generate submittal form: {exc}'}), 500
    filename = f'Submittal_{submittal.number or submittal_id}.pdf'
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename,
    )


@app.route('/api/submittals/<int:submittal_id>/comments', methods=['GET'])
@login_required
def api_submittal_list_comments(submittal_id):
    from rfi_persistence import _parse_json
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        assert_submittal_read_allowed(current_user)
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    comments = _parse_json(getattr(submittal, 'comments_json', None), [])
    return jsonify({'ok': True, 'comments': comments})


@app.route('/api/submittals/<int:submittal_id>/comments', methods=['POST'])
@login_required
def api_submittal_add_comment(submittal_id):
    from rfi_persistence import _parse_json
    from submittal_persistence import add_submittal_comment
    from document_module_security import assert_submittal_comment_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    from workflow_responder import notify_submittal_comment
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
        assert_submittal_comment_allowed(current_user, submittal, Company=Company, db=db)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    actor_name = _user_display_name(current_user.id)
    try:
        entry = add_submittal_comment(
            submittal,
            body,
            current_user.id,
            actor_name,
            user_role=getattr(current_user, 'role', None),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    try:
        notify_submittal_comment(submittal, User, current_user, entry.get('body'))
    except Exception:
        pass
    return jsonify({'ok': True, 'comment': entry, 'comments': _parse_json(submittal.comments_json, [])})


@app.route('/api/submittals/<int:submittal_id>/comments', methods=['DELETE'])
@login_required
def api_submittal_clear_comments(submittal_id):
    from rfi_persistence import _parse_json
    from submittal_persistence import clear_submittal_comments
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    try:
        from developer_tools import is_developer
        if not is_developer(current_user) and getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    except Exception:
        if getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        assert_submittal_read_allowed(current_user)
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    clear_submittal_comments(submittal)
    db.session.commit()
    return jsonify({'ok': True, 'comments': _parse_json(submittal.comments_json, [])})


@app.route('/api/submittals/<int:submittal_id>/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_submittal_delete_comment(submittal_id, comment_id):
    from rfi_persistence import _parse_json
    from submittal_persistence import delete_submittal_comment
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    try:
        from developer_tools import is_developer
        if not is_developer(current_user) and getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    except Exception:
        if getattr(current_user, 'role', None) != 'Admin':
            return jsonify({'error': 'Developer access required'}), 403
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        assert_submittal_read_allowed(current_user)
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    try:
        delete_submittal_comment(submittal, comment_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    db.session.commit()
    return jsonify({'ok': True, 'comments': _parse_json(submittal.comments_json, [])})


@app.route('/api/submittals/<int:submittal_id>/signature', methods=['POST'])
@login_required
def api_submittal_apply_signature(submittal_id):
    from submittal_persistence import append_submittal_digital_signature
    from document_module_security import assert_submittal_signature_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
        assert_submittal_signature_allowed(current_user, submittal, Company=Company, db=db)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    try:
        entry, history = append_submittal_digital_signature(submittal, current_user, body)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'signature_entry': entry, 'history': history})


@app.route('/api/submittals/<int:submittal_id>/review-submissions', methods=['GET'])
@login_required
def api_submittal_list_review_submissions(submittal_id):
    from rfi_persistence import _parse_json
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        assert_submittal_read_allowed(current_user)
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    details = _parse_json(submittal.details_json, {})
    submissions = details.get('reviewSubmissions') or details.get('review_submissions') or []
    return jsonify({
        'ok': True,
        'review_submissions': submissions,
        'review_comments': submittal.review_comments or '',
    })


@app.route('/api/submittals/<int:submittal_id>/review-submissions', methods=['POST'])
@login_required
def api_submittal_add_review_submission(submittal_id):
    from rfi_persistence import _parse_json
    from submittal_persistence import add_submittal_review_submission
    from document_module_security import assert_submittal_review_submission_allowed, submittal_visible_to_user
    from financial_security import require_financial_project_access
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
        assert_submittal_review_submission_allowed(current_user, submittal, Company=Company, db=db)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    actor_name = _user_display_name(current_user.id)
    party = body.get('party') or getattr(current_user, 'role', None) or 'Reviewer'
    try:
        entry, submissions = add_submittal_review_submission(
            submittal,
            body,
            current_user.id,
            actor_name,
            user_role=getattr(current_user, 'role', None),
            party=party,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    return jsonify({'ok': True, 'submission': entry, 'review_submissions': submissions})


@app.route('/api/submittals/<int:submittal_id>/print-review-sheet', methods=['GET'])
@login_required
def api_submittal_print_review_sheet(submittal_id):
    from document_module_security import assert_submittal_read_allowed, submittal_visible_to_user, is_sub_portal_user, is_staff_portal_user
    from financial_security import require_financial_project_access
    from program_settings_persistence import load_company_info
    from submittal_form_pdf import build_submittal_review_sheet_pdf
    import io

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        assert_submittal_read_allowed(current_user)
        if is_sub_portal_user(current_user) and not is_staff_portal_user(current_user):
            return jsonify({'error': 'Permission denied'}), 403
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    project = Project.query.get(submittal.project_id)
    pdf_bytes = build_submittal_review_sheet_pdf(
        submittal,
        project=project,
        company_info=load_company_info(),
        upload_folder=app.config['UPLOAD_FOLDER'],
    )
    filename = f'Submittal_{submittal.number or submittal_id}_Review_Sheet.pdf'
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename,
    )


@app.route('/api/submittals/<int:submittal_id>/attachments', methods=['GET'])
@login_required
def api_submittal_list_attachments(submittal_id):
    from rfi_persistence import _parse_json
    from financial_security import require_financial_project_access
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    attachments = _parse_json(submittal.attachments_json, [])
    for a in attachments:
        if a.get('document_id'):
            a['url'] = url_for('api_documents_download', doc_id=a['document_id'])
        elif a.get('filename'):
            a['url'] = url_for('serve_submittal_attachment', submittal_id=submittal_id, filename=a.get('filename', ''))
    return jsonify({'ok': True, 'attachments': attachments})


@app.route('/api/submittals/<int:submittal_id>/attachments/viewer-doc', methods=['POST'])
@login_required
def api_submittal_attachment_viewer_doc(submittal_id):
    """Resolve or create a Documents record for markup viewer on a submittal attachment."""
    from rfi_persistence import _parse_json
    from financial_security import require_financial_project_access
    from document_module_security import submittal_visible_to_user

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403

    body = request.get_json(silent=True) or {}
    attachments = _parse_json(submittal.attachments_json, [])
    attachment = None
    att_index = body.get('index')
    if att_index is not None:
        try:
            attachment = attachments[int(att_index)]
        except (IndexError, TypeError, ValueError):
            attachment = None
    if attachment is None and body.get('document_id'):
        doc_id = int(body['document_id'])
        attachment = next((a for a in attachments if int(a.get('document_id') or 0) == doc_id), None)
    if attachment is None and body.get('filename'):
        attachment = next((a for a in attachments if a.get('filename') == body['filename']), None)
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    if attachment.get('document_id'):
        doc = Document.query.get(int(attachment['document_id']))
        if doc and doc.project_id == submittal.project_id and not doc.deleted_at:
            return jsonify({'ok': True, 'document_id': doc.id, 'name': doc.name})

    safe_name = (attachment.get('filename') or '').strip()
    original = (attachment.get('original_name') or safe_name).strip()
    for doc in Document.query.filter_by(project_id=submittal.project_id).filter(Document.deleted_at.is_(None)).all():
        try:
            meta = json.loads(doc.source_metadata_json or '{}')
        except (TypeError, json.JSONDecodeError):
            meta = {}
        if meta.get('submittal_id') == submittal.id and (
            meta.get('attachment_filename') == safe_name
            or (original and original in (doc.original_filename or '', doc.name or ''))
        ):
            attachment['document_id'] = doc.id
            submittal.attachments_json = json.dumps(attachments)
            db.session.commit()
            return jsonify({'ok': True, 'document_id': doc.id, 'name': doc.name})

    if not safe_name:
        return jsonify({'error': 'Attachment is not linked to a viewable document'}), 400
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'submittals', str(submittal_id))
    path = os.path.join(folder, safe_name)
    if not os.path.isfile(path):
        return jsonify({'error': 'Attachment file not found on server'}), 404
    with open(path, 'rb') as fh:
        file_bytes = fh.read()
    doc_dict = _mirror_to_system_folder(
        submittal.project_id,
        file_bytes,
        f'{submittal.number} — {safe_name}',
        original or safe_name,
        'submittals',
        'Submittal',
        {
            'submittal_id': submittal.id,
            'submittal_number': submittal.number,
            'attachment_filename': safe_name,
        },
    )
    if not doc_dict or not doc_dict.get('id'):
        return jsonify({'error': 'Could not prepare document for viewer'}), 500
    attachment['document_id'] = doc_dict['id']
    submittal.attachments_json = json.dumps(attachments)
    db.session.commit()
    return jsonify({'ok': True, 'document_id': doc_dict['id'], 'name': doc_dict.get('name') or original})


def _submittal_attachment_document(submittal, doc_id):
    from submittal_persistence import submittal_links_document
    doc = Document.query.get(int(doc_id))
    if not doc or doc.deleted_at or doc.project_id != submittal.project_id:
        return None
    if submittal_links_document(submittal, doc.id):
        return doc
    try:
        meta = json.loads(doc.source_metadata_json or '{}')
    except (TypeError, json.JSONDecodeError):
        meta = {}
    if meta.get('submittal_id') == submittal.id:
        return doc
    return None


@app.route('/api/submittals/<int:submittal_id>/attachments/document/<int:doc_id>', methods=['GET'])
@login_required
def api_submittal_attachment_document(submittal_id, doc_id):
    """Submittal-scoped document metadata + markups (no Documents module required)."""
    from document_module_security import submittal_visible_to_user
    from document_persistence import document_markup_to_dict
    from financial_security import require_financial_project_access

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    doc = _submittal_attachment_document(submittal, doc_id)
    if not doc:
        return jsonify({'error': 'Document not found for this submittal'}), 404
    markups = DocumentMarkup.query.filter_by(document_id=doc.id).all()
    return jsonify({
        'ok': True,
        'document': {
            'id': doc.id,
            'name': doc.name,
            'original_filename': doc.original_filename,
            'mime_type': doc.mime_type,
            'file_url': url_for('api_submittal_attachment_document_file', submittal_id=submittal_id, doc_id=doc.id),
        },
        'markups': [document_markup_to_dict(m) for m in markups],
    })


@app.route('/api/submittals/<int:submittal_id>/attachments/document/<int:doc_id>/file', methods=['GET'])
@login_required
def api_submittal_attachment_document_file(submittal_id, doc_id):
    from document_module_security import submittal_visible_to_user
    from financial_security import require_financial_project_access

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    doc = _submittal_attachment_document(submittal, doc_id)
    if not doc:
        return jsonify({'error': 'Document not found for this submittal'}), 404
    path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', str(doc.project_id), doc.filename)
    if not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(path, mimetype=doc.mime_type or 'application/octet-stream', as_attachment=False, download_name=doc.original_filename or doc.name)


@app.route('/api/submittals/<int:submittal_id>/attachments/document/<int:doc_id>/markups', methods=['GET', 'POST'])
@login_required
def api_submittal_attachment_document_markups(submittal_id, doc_id):
    from document_module_security import submittal_visible_to_user
    from document_persistence import document_markup_to_dict
    from financial_security import require_financial_project_access
    from submittal_persistence import submittal_is_approved_locked

    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    doc = _submittal_attachment_document(submittal, doc_id)
    if not doc:
        return jsonify({'error': 'Document not found for this submittal'}), 404
    if request.method == 'GET':
        rows = DocumentMarkup.query.filter_by(document_id=doc.id).all()
        return jsonify({'markups': [document_markup_to_dict(m) for m in rows]})
    if submittal_is_approved_locked(submittal):
        return jsonify({'error': 'This submittal is approved and locked; markups cannot be changed.'}), 423
    lock = _document_edit_lock_error(doc)
    if lock:
        return lock
    body = request.get_json(silent=True) or {}
    user_name = _user_display_name(current_user.id)
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


@app.route('/api/submittals/<int:submittal_id>/physical-print/<kind>', methods=['POST'])
@login_required
def api_submittal_physical_print_upload(submittal_id, kind):
    """Upload a physically stamped cover page or marked-up document (supersedes auto print)."""
    from document_module_security import submittal_visible_to_user, user_can_act_on_ball_in_court
    from financial_security import require_financial_project_access
    from submittal_persistence import save_physical_print_upload

    if kind not in ('cover', 'marked-document'):
        return jsonify({'error': 'kind must be cover or marked-document'}), 400
    submittal = Submittal.query.get_or_404(submittal_id)
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
        role = getattr(current_user, 'role', '') or ''
        is_design = 'architect' in role.lower() or 'engineer' in role.lower()
        can_act = user_can_act_on_ball_in_court(current_user, submittal.ball_in_court)
        if not (is_design or can_act or getattr(current_user, 'role', None) in ('Admin', 'Developer', 'Project Manager')):
            return jsonify({'error': 'Permission denied'}), 403
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    safe = secure_filename(f.filename)
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'submittals', str(submittal_id), 'physical')
    os.makedirs(folder, exist_ok=True)
    stored = f'{kind}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}_{safe}'
    path = os.path.join(folder, stored)
    f.save(path)
    entry = {
        'filename': stored,
        'original_name': f.filename,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by_id': current_user.id,
        'uploaded_by': _user_display_name(current_user.id),
    }
    pkg = save_physical_print_upload(
        submittal,
        'cover' if kind == 'cover' else 'marked_document',
        entry,
    )
    db.session.commit()
    return jsonify({'ok': True, 'physical_print_package': pkg})


@app.route('/api/submittals/<int:submittal_id>/attachments', methods=['DELETE'])
@login_required
def api_submittal_delete_attachment(submittal_id):
    from rfi_persistence import _parse_json
    from financial_security import require_financial_project_access, assert_mutable_submittal
    from document_module_security import assert_submittal_attachment_delete_allowed, submittal_visible_to_user

    submittal = Submittal.query.get_or_404(submittal_id)
    body = request.get_json(silent=True) or {}
    filename = (body.get('filename') or '').strip()
    document_id = body.get('document_id')
    try:
        require_financial_project_access(current_user, submittal.project_id, Project)
        if not submittal_visible_to_user(submittal, current_user, Company=Company, db=db):
            return jsonify({'error': 'Permission denied'}), 403
        assert_mutable_submittal(submittal)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403 if isinstance(exc, PermissionError) else 400

    attachments = _parse_json(submittal.attachments_json, [])
    target = None
    target_idx = None
    for idx, att in enumerate(attachments):
        if document_id is not None and att.get('document_id') == int(document_id):
            target = att
            target_idx = idx
            break
        if filename and att.get('filename') == filename:
            target = att
            target_idx = idx
            break
    if target is None:
        return jsonify({'error': 'Attachment not found'}), 404
    try:
        assert_submittal_attachment_delete_allowed(
            current_user, submittal, target, Company=Company, db=db,
        )
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403

    if target.get('filename') and not target.get('document_id'):
        folder = os.path.join(app.config['UPLOAD_FOLDER'], 'submittals', str(submittal_id))
        path = os.path.join(folder, target['filename'])
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

    attachments.pop(target_idx)
    submittal.attachments_json = json.dumps(attachments)
    db.session.commit()
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
    from program_settings_persistence import format_document_number, load_numbering_config
    prefix = prefix_for_type(commitment_type or 'Purchase Order')
    cfg = load_numbering_config()
    pad = 3
    for entry in cfg.values():
        if entry.get('prefix') == prefix:
            pad = entry.get('pad', 3)
            break
    last = (
        Commitment.query.filter_by(project_id=int(project_id))
        .filter(Commitment.number.like(f'{prefix}-%'))
        .order_by(Commitment.id.desc())
        .first()
    )
    if last and last.number:
        try:
            n = int(last.number.split('-')[-1])
            return format_document_number(prefix, n + 1, pad)
        except (TypeError, ValueError):
            pass
    return format_document_number(prefix, 1, pad)


def _parse_commitment_date(value):
    if not value:
        return datetime.utcnow().date()
    try:
        return datetime.fromisoformat(str(value).replace('Z', '')).date()
    except (TypeError, ValueError):
        return datetime.utcnow().date()


def _sage_commitment_event(commitment, event_type, message='', extra=None, user_id=None):
    from commitment_persistence import queue_commitment_sage_event
    return queue_commitment_sage_event(
        commitment, event_type, message=message, extra=extra, user_id=user_id,
        db=db, SageSyncEvent=SageSyncEvent, Project=Project,
        Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
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
    from financial_security import require_financial_project_access
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = int(project_id)
    status = request.args.get('status')
    ctype = request.args.get('type')
    q = Commitment.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    if ctype:
        q = q.filter_by(commitment_type=ctype)
    rows = q.order_by(Commitment.created_at.desc()).all()
    try:
        from portal_sub_access import is_sub_vendor_portal_user, resolve_sub_vendor_company
        from pay_app_persistence import commitment_matches_vendor
        if is_sub_vendor_portal_user(current_user):
            cid, cname, _ = resolve_sub_vendor_company(current_user, Company, db, persist_link=True)
            rows = [
                c for c in rows
                if commitment_matches_vendor(c, cid, cname)
            ]
    except Exception:
        pass
    result = []
    for c in rows:
        allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        result.append(commitment_to_dict(c, allocs))
    return jsonify({'commitments': result})


@app.route('/api/commitments/<int:commitment_id>', methods=['GET'])
@login_required
def api_get_commitment(commitment_id):
    from commitment_persistence import commitment_to_dict
    from financial_security import require_financial_project_access
    c = Commitment.query.get_or_404(commitment_id)
    try:
        require_financial_project_access(current_user, c.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify(commitment_to_dict(c, allocs))


@app.route('/api/commitments', methods=['POST'])
@login_required
def api_create_commitment():
    from commitment_persistence import (
        apply_commitment_fields, commitment_to_dict, save_allocations,
        validate_budget_headroom, validate_commitment_allocations,
    )
    from developer_tools import is_admin_or_developer
    from financial_security import require_financial_project_access, assert_draft_create_status, strip_workflow_fields
    try:
        body = strip_workflow_fields(request.get_json(silent=True) or {})
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        project_id = require_financial_project_access(current_user, project_id, Project)
        description = (body.get('description') or body.get('title') or '').strip()
        if not description:
            return jsonify({'error': 'description required'}), 400
        alloc_errors = validate_commitment_allocations(body.get('allocations') or [])
        if alloc_errors:
            return jsonify({'error': alloc_errors[0], 'allocation_errors': alloc_errors}), 400
        budget_override = bool(body.get('budget_override')) and is_admin_or_developer(current_user)
        budget_errors, warnings = validate_budget_headroom(
            BudgetProjectState, int(project_id), body.get('allocations') or [],
            budget_override=budget_override,
        )
        if budget_errors:
            return jsonify({
                'error': budget_errors[0],
                'budget_errors': budget_errors,
                'can_override': is_admin_or_developer(current_user),
            }), 400
        assert_draft_create_status(body.get('status') or 'Draft', entity_label='Commitment')
        ctype = body.get('commitment_type') or 'Purchase Order'
        number = body.get('number') or generate_commitment_number(ctype, project_id)
        c = Commitment(
            project_id=int(project_id),
            number=number,
            description=description,
            commitment_type=ctype,
            status='Draft',
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
        c.budget_validated = not budget_errors
        db.session.commit()
        allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        return jsonify({'ok': True, 'commitment': commitment_to_dict(c, allocs), 'budget_warnings': warnings})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/commitments/<int:commitment_id>', methods=['PUT'])
@login_required
def api_update_commitment(commitment_id):
    from commitment_persistence import (
        apply_commitment_fields, commitment_to_dict, save_allocations,
        validate_budget_headroom, validate_commitment_allocations,
    )
    from developer_tools import is_admin_or_developer
    from financial_security import require_financial_project_access, assert_mutable_commitment, strip_workflow_fields
    c = Commitment.query.get_or_404(commitment_id)
    try:
        require_financial_project_access(current_user, c.project_id, Project)
        assert_mutable_commitment(c, developer_unlock=_developer_unlock_bypass())
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403 if isinstance(exc, PermissionError) else 400
    body = strip_workflow_fields(request.get_json(silent=True) or {})
    if body.get('allocations') is not None:
        alloc_errors = validate_commitment_allocations(body.get('allocations') or [])
        if alloc_errors:
            return jsonify({'error': alloc_errors[0], 'allocation_errors': alloc_errors}), 400
    budget_override = bool(body.get('budget_override')) and is_admin_or_developer(current_user)
    budget_errors, warnings = [], []
    if body.get('allocations') is not None:
        budget_errors, warnings = validate_budget_headroom(
            BudgetProjectState, c.project_id, body.get('allocations') or [],
            budget_override=budget_override,
        )
        if budget_errors:
            return jsonify({
                'error': budget_errors[0],
                'budget_errors': budget_errors,
                'can_override': is_admin_or_developer(current_user),
            }), 400
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
        c.budget_validated = not budget_errors
    db.session.commit()
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify({'ok': True, 'commitment': commitment_to_dict(c, allocs), 'budget_warnings': warnings})


@app.route('/api/commitments/<int:commitment_id>', methods=['DELETE'])
@login_required
def api_delete_commitment(commitment_id):
    from developer_tools import is_admin_or_developer
    if not is_admin_or_developer(current_user):
        return jsonify({'error': 'Only administrators or developers can delete commitments'}), 403
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
    from financial_security import require_financial_project_access
    c = Commitment.query.get_or_404(commitment_id)
    try:
        require_financial_project_access(current_user, c.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    sage_ctx = {
        'db': db,
        'SageSyncEvent': SageSyncEvent,
        'Project': Project,
        'Commitment': Commitment,
        'CommitmentAllocation': CommitmentAllocation,
    }
    try:
        new_status, final_approved = commitment_workflow_action(
            c, action, current_user, body=body, CommitmentAllocation=CommitmentAllocation,
            sage_ctx=sage_ctx,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': f'Commitment workflow failed: {exc}'}), 500

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
        try:
            _sage_commitment_event(
                c, 'CommitmentSubmitted',
                message=f'{c.number} submitted — ball with {c.ball_in_court_role}',
                user_id=current_user.id,
            )
        except Exception:
            pass

    if action == 'reject':
        try:
            _sage_commitment_event(c, 'CommitmentRejected', user_id=current_user.id)
        except Exception:
            pass
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
    from financial_security import require_financial_project_access
    c = Commitment.query.get_or_404(commitment_id)
    try:
        require_financial_project_access(current_user, c.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    return jsonify(commitment_export_for_catina(commitment_to_dict(c, allocs)))


@app.route('/api/commitments/<int:commitment_id>/aia/catina-link', methods=['POST'])
@login_required
def api_commitment_catina_link(commitment_id):
    from commitment_persistence import commitment_to_dict
    from aia_service import build_catina_create_url, build_catina_open_url
    from financial_security import require_financial_project_access
    c = Commitment.query.get_or_404(commitment_id)
    try:
        require_financial_project_access(current_user, c.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
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
    from financial_security import require_financial_project_access
    c = Commitment.query.get_or_404(commitment_id)
    try:
        require_financial_project_access(current_user, c.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
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
    return render_template('deliveries.html', active_project=get_active_project())


@app.route('/api/deliveries', methods=['GET'])
@login_required
def api_deliveries_list():
    from deliveries_persistence import serialize_delivery, compute_stats, STATUSES
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    q = Delivery.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    rows = q.order_by(Delivery.delivery_date.asc()).all()
    return jsonify({
        'ok': True,
        'deliveries': [serialize_delivery(d, User=User) for d in rows],
        'stats': compute_stats(Delivery, project_id),
        'statuses': list(STATUSES),
        'project_id': project_id,
    })


def _delivery_apply(d, body):
    for field in ('supplier', 'description', 'time_window', 'status', 'location', 'quantity',
                  'po_number', 'carrier', 'responsible', 'received_by', 'notes'):
        if field in body:
            setattr(d, field, body[field])
    if 'duration_days' in body:
        try:
            d.duration_days = max(1, int(body['duration_days']))
        except (TypeError, ValueError):
            d.duration_days = 1
    if 'delivery_date' in body and body['delivery_date']:
        try:
            d.delivery_date = datetime.strptime(body['delivery_date'], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            pass


def _sync_delivery_to_schedule(delivery):
    """Upsert this delivery into the project's schedule payload."""
    from deliveries_persistence import upsert_delivery_tasks, task_id_for
    record = ScheduleData.query.filter_by(project_id=delivery.project_id).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except json.JSONDecodeError:
            payload = {}
    payload = upsert_delivery_tasks(payload, [delivery])
    if not delivery.schedule_task_id:
        delivery.schedule_task_id = task_id_for(delivery)
    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        db.session.add(ScheduleData(project_id=delivery.project_id, payload=payload_json))


@app.route('/api/deliveries', methods=['POST'])
@login_required
def api_deliveries_create():
    from deliveries_persistence import serialize_delivery
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    description = (body.get('description') or '').strip()
    date_str = body.get('delivery_date')
    if not project_id or not description or not date_str:
        return jsonify({'error': 'project_id, description and delivery_date required'}), 400
    try:
        ddate = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid delivery_date'}), 400
    last = Delivery.query.filter_by(project_id=int(project_id)).order_by(Delivery.id.desc()).first()
    seq = 1
    if last and last.delivery_number and last.delivery_number.startswith('DEL-'):
        try:
            seq = int(last.delivery_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = (Delivery.query.filter_by(project_id=int(project_id)).count() or 0) + 1
    else:
        seq = (Delivery.query.filter_by(project_id=int(project_id)).count() or 0) + 1
    d = Delivery(
        project_id=int(project_id),
        delivery_number=f'DEL-{seq:03d}',
        description=description,
        delivery_date=ddate,
        status=body.get('status') or 'Scheduled',
        created_by_id=current_user.id,
    )
    _delivery_apply(d, body)
    db.session.add(d)
    db.session.flush()
    if body.get('push_to_schedule'):
        _sync_delivery_to_schedule(d)
    db.session.commit()
    return jsonify({'ok': True, 'delivery': serialize_delivery(d, User=User)})


@app.route('/api/deliveries/<int:delivery_id>', methods=['GET'])
@login_required
def api_delivery_get(delivery_id):
    from deliveries_persistence import serialize_delivery
    d = Delivery.query.get_or_404(delivery_id)
    return jsonify({'ok': True, 'delivery': serialize_delivery(d, User=User)})


@app.route('/api/deliveries/<int:delivery_id>', methods=['PUT'])
@login_required
def api_deliveries_update(delivery_id):
    from deliveries_persistence import serialize_delivery
    d = Delivery.query.get_or_404(delivery_id)
    _delivery_apply(d, request.get_json(silent=True) or {})
    # Keep the schedule in sync if this delivery is already pushed.
    if d.schedule_task_id:
        _sync_delivery_to_schedule(d)
    db.session.commit()
    return jsonify({'ok': True, 'delivery': serialize_delivery(d, User=User)})


@app.route('/api/deliveries/<int:delivery_id>', methods=['DELETE'])
@login_required
def api_deliveries_delete(delivery_id):
    d = Delivery.query.get_or_404(delivery_id)
    # Remove the linked schedule task if present.
    if d.schedule_task_id:
        record = ScheduleData.query.filter_by(project_id=d.project_id).first()
        if record and record.payload:
            try:
                payload = json.loads(record.payload)
                payload['data'] = [t for t in (payload.get('data') or []) if str(t.get('id')) != str(d.schedule_task_id)]
                record.payload = json.dumps(payload)
                record.updated_at = datetime.utcnow()
            except json.JSONDecodeError:
                pass
    db.session.delete(d)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/deliveries/push-to-schedule', methods=['POST'])
@login_required
def api_deliveries_push_to_schedule():
    """Push selected (or all) deliveries into the Schedule as line items."""
    from deliveries_persistence import upsert_delivery_tasks, task_id_for
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    body = request.get_json(silent=True) or {}
    ids = body.get('ids')
    q = Delivery.query.filter_by(project_id=int(project_id))
    if ids:
        q = q.filter(Delivery.id.in_(ids))
    deliveries = q.all()
    if not deliveries:
        return jsonify({'ok': True, 'pushed': 0})
    record = ScheduleData.query.filter_by(project_id=int(project_id)).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except json.JSONDecodeError:
            payload = {}
    payload = upsert_delivery_tasks(payload, deliveries)
    for d in deliveries:
        if not d.schedule_task_id:
            d.schedule_task_id = task_id_for(d)
    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        db.session.add(ScheduleData(project_id=int(project_id), payload=payload_json))
    db.session.commit()
    return jsonify({'ok': True, 'pushed': len(deliveries),
                    'schedule_url': url_for('schedule_page') + f'?project_id={project_id}'})


@app.route('/inspections')
@login_required
def inspections_page():
    return render_template('inspections.html', active_project=get_active_project())


def _next_permit_inspection_number(project_id, prefix=None):
    from program_settings_persistence import get_numbering_prefix, format_document_number
    if not prefix:
        prefix, pad = get_numbering_prefix('inspection')
    else:
        _, pad = get_numbering_prefix('inspection')
    from sqlalchemy import func
    q = PermitInspectionItem.query.filter_by(project_id=int(project_id))
    last = q.order_by(PermitInspectionItem.id.desc()).first()
    n = 1
    if last and last.item_number:
        try:
            n = int(str(last.item_number).split('-')[-1]) + 1
        except (ValueError, IndexError):
            n = (last.id or 0) + 1
    return format_document_number(prefix, n, pad)


def _apply_permit_inspection_item(item, body):
    for field in (
        'record_kind', 'trade', 'inspection_phase', 'title', 'description', 'fbc_reference',
        'permit_number', 'jurisdiction_level', 'jurisdiction_name', 'authority_name',
        'authority_phone', 'authority_url', 'scheduled_time', 'status', 'inspector',
        'location', 'result_notes', 'correction_notes', 'catalog_source',
    ):
        if field in body:
            setattr(item, field, body[field])
    if 'parent_id' in body:
        item.parent_id = int(body['parent_id']) if body['parent_id'] else None
    if 'duration_days' in body:
        try:
            item.duration_days = max(1, int(body['duration_days']))
        except (TypeError, ValueError):
            item.duration_days = 1
    if 'scheduled_date' in body:
        if body['scheduled_date']:
            try:
                item.scheduled_date = datetime.strptime(body['scheduled_date'][:10], '%Y-%m-%d').date()
            except (TypeError, ValueError):
                pass
        else:
            item.scheduled_date = None
    if 'details' in body:
        item.details_json = json.dumps(body['details'] or {})
    if any(k in body for k in ('notify_user_ids', 'notify_user_id', 'notify_creator', 'reminder_offsets')):
        from inspection_reminders import apply_notification_settings
        apply_notification_settings(item, body)


def _sync_permit_inspection_to_schedule(item):
    from permits_inspections_persistence import upsert_inspection_tasks, task_id_for
    record = ScheduleData.query.filter_by(project_id=item.project_id).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except json.JSONDecodeError:
            payload = {}
    payload = upsert_inspection_tasks(payload, [item])
    if not item.schedule_task_id:
        item.schedule_task_id = task_id_for(item)
    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        db.session.add(ScheduleData(project_id=item.project_id, payload=payload_json))
    db.session.commit()


@app.route('/api/permits-inspections/catalog', methods=['GET'])
@login_required
def api_permits_inspections_catalog():
    from florida_permit_catalog import (
        PERMIT_TRADES, FBC_INSPECTION_TEMPLATES, FLORIDA_STATE_AUTHORITIES,
        FLORIDA_UTILITIES, FLORIDA_WMD, STATUSES,
    )
    from florida_jurisdiction_directory import get_full_directory
    trade = request.args.get('trade')
    return jsonify({
        'ok': True,
        'trades': PERMIT_TRADES,
        'statuses': list(STATUSES),
        'fbc_templates': FBC_INSPECTION_TEMPLATES.get(trade, []) if trade else FBC_INSPECTION_TEMPLATES,
        'directory': get_full_directory(),
        'state_authorities': FLORIDA_STATE_AUTHORITIES,
        'utilities': FLORIDA_UTILITIES,
        'water_management_districts': FLORIDA_WMD,
    })


@app.route('/api/permits-inspections/directory', methods=['GET'])
@login_required
def api_permits_inspections_directory():
    from florida_jurisdiction_directory import search_directory
    q = request.args.get('q', '')
    category = request.args.get('category', 'all')
    return jsonify({'ok': True, 'results': search_directory(q, category)})


@app.route('/api/permits-inspections', methods=['GET'])
@login_required
def api_permits_inspections_list():
    from permits_inspections_persistence import serialize_item, compute_stats, STATUSES
    from florida_permit_catalog import PERMIT_TRADES
    from inspection_reminders import process_due_reminders, REMINDER_OPTIONS
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    try:
        process_due_reminders(PermitInspectionItem, User, project_id=project_id)
        db.session.commit()
    except Exception:
        db.session.rollback()
    q = PermitInspectionItem.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    trade = request.args.get('trade')
    status = request.args.get('status')
    kind = request.args.get('record_kind')
    if trade:
        q = q.filter_by(trade=trade)
    if status:
        q = q.filter_by(status=status)
    if kind:
        q = q.filter_by(record_kind=kind)
    rows = q.order_by(PermitInspectionItem.scheduled_date.asc(), PermitInspectionItem.id.asc()).all()
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    return jsonify({
        'ok': True,
        'items': [serialize_item(r) for r in rows],
        'stats': compute_stats(PermitInspectionItem, project_id),
        'statuses': list(STATUSES),
        'trades': PERMIT_TRADES,
        'users': [{'id': u.id, 'name': u.full_name, 'email': u.email, 'role': u.role} for u in users],
        'reminder_options': REMINDER_OPTIONS,
        'schedule_url': url_for('schedule_page') + (f'?project_id={project_id}' if project_id else ''),
    })


@app.route('/api/permits-inspections/from-template', methods=['POST'])
@login_required
def api_permits_inspections_from_template():
    """Bulk-create FBC checklist items for a trade."""
    from florida_permit_catalog import build_checklist_items
    from permits_inspections_persistence import serialize_item
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    trade = body.get('trade', 'building')
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    jurisdiction = body.get('jurisdiction') or {}
    scheduled_date = body.get('scheduled_date')
    push = bool(body.get('push_to_schedule'))
    created = []
    for tpl in build_checklist_items(trade, jurisdiction):
        item = PermitInspectionItem(
            project_id=int(project_id),
            item_number=_next_permit_inspection_number(project_id),
            record_kind=tpl.get('record_kind', 'inspection'),
            trade=tpl.get('trade', trade),
            inspection_phase=tpl.get('inspection_phase', ''),
            title=tpl.get('title', 'Inspection'),
            description=tpl.get('description', ''),
            fbc_reference=tpl.get('fbc_reference', ''),
            jurisdiction_name=tpl.get('jurisdiction_name', ''),
            authority_name=tpl.get('authority_name', ''),
            authority_phone=tpl.get('authority_phone', ''),
            authority_url=tpl.get('authority_url', ''),
            status=tpl.get('status', 'Not Started'),
            catalog_source='fbc_template',
            created_by_id=current_user.id,
        )
        if scheduled_date:
            try:
                item.scheduled_date = datetime.strptime(scheduled_date[:10], '%Y-%m-%d').date()
            except (TypeError, ValueError):
                pass
        db.session.add(item)
        db.session.flush()
        if push and item.scheduled_date:
            try:
                _sync_permit_inspection_to_schedule(item)
            except Exception:
                db.session.rollback()
        created.append(serialize_item(item))
    db.session.commit()
    return jsonify({'ok': True, 'created': created, 'count': len(created)})


@app.route('/api/permits-inspections', methods=['POST'])
@login_required
def api_permits_inspections_create():
    from permits_inspections_persistence import serialize_item
    from inspection_reminders import notify_scheduled
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    title = (body.get('title') or '').strip()
    if not project_id or not title:
        return jsonify({'error': 'project_id and title required'}), 400
    item = PermitInspectionItem(
        project_id=int(project_id),
        item_number=_next_permit_inspection_number(project_id),
        title=title,
        created_by_id=current_user.id,
    )
    _apply_permit_inspection_item(item, body)
    db.session.add(item)
    db.session.flush()
    if body.get('send_notifications', True) and item.scheduled_date:
        try:
            notify_scheduled(item, User, actor_id=current_user.id)
        except Exception:
            pass
    db.session.commit()
    if body.get('push_to_schedule') and item.scheduled_date:
        try:
            _sync_permit_inspection_to_schedule(item)
        except Exception:
            pass
    return jsonify({'ok': True, 'item': serialize_item(item)})


@app.route('/api/permits-inspections/<int:item_id>', methods=['PUT'])
@login_required
def api_permits_inspections_update(item_id):
    from permits_inspections_persistence import serialize_item
    from inspection_reminders import notify_scheduled, clear_reminders_sent
    item = PermitInspectionItem.query.get_or_404(item_id)
    body = request.get_json(silent=True) or {}
    old_date = item.scheduled_date
    old_time = item.scheduled_time
    _apply_permit_inspection_item(item, body)
    item.updated_at = datetime.utcnow()
    schedule_changed = (
        item.scheduled_date != old_date or (item.scheduled_time or '') != (old_time or '')
    )
    if schedule_changed:
        clear_reminders_sent(item)
    if body.get('send_notifications', schedule_changed) and item.scheduled_date:
        try:
            notify_scheduled(item, User, actor_id=current_user.id)
        except Exception:
            pass
    db.session.commit()
    if body.get('push_to_schedule') or item.schedule_task_id:
        try:
            _sync_permit_inspection_to_schedule(item)
        except Exception:
            pass
    return jsonify({'ok': True, 'item': serialize_item(item)})


@app.route('/api/permits-inspections/<int:item_id>/notify', methods=['POST'])
@login_required
def api_permits_inspections_notify(item_id):
    from permits_inspections_persistence import serialize_item
    from inspection_reminders import notify_manual
    item = PermitInspectionItem.query.get_or_404(item_id)
    body = request.get_json(silent=True) or {}
    user_ids = body.get('notify_user_ids')
    if user_ids is not None:
        user_ids = [int(x) for x in user_ids if x]
    targets = notify_manual(item, User, actor_id=current_user.id, user_ids=user_ids)
    db.session.commit()
    return jsonify({'ok': True, 'notified': len(targets), 'item': serialize_item(item)})


@app.route('/api/permits-inspections/<int:item_id>', methods=['DELETE'])
@login_required
def api_permits_inspections_delete(item_id):
    item = PermitInspectionItem.query.get_or_404(item_id)
    if item.schedule_task_id:
        record = ScheduleData.query.filter_by(project_id=item.project_id).first()
        if record and record.payload:
            try:
                payload = json.loads(record.payload)
                data = payload.get('data') or []
                payload['data'] = [t for t in data if str(t.get('id')) != str(item.schedule_task_id)]
                record.payload = json.dumps(payload)
            except json.JSONDecodeError:
                pass
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/permits-inspections/push-to-schedule', methods=['POST'])
@login_required
def api_permits_inspections_push_to_schedule():
    from permits_inspections_persistence import upsert_inspection_tasks, task_id_for
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    body = request.get_json(silent=True) or {}
    ids = body.get('ids')
    q = PermitInspectionItem.query.filter_by(project_id=int(project_id))
    if ids:
        q = q.filter(PermitInspectionItem.id.in_(ids))
    else:
        q = q.filter(PermitInspectionItem.scheduled_date.isnot(None))
    items = q.all()
    if not items:
        return jsonify({'ok': True, 'pushed': 0})
    record = ScheduleData.query.filter_by(project_id=int(project_id)).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except json.JSONDecodeError:
            payload = {}
    payload = upsert_inspection_tasks(payload, items)
    for item in items:
        if not item.schedule_task_id:
            item.schedule_task_id = task_id_for(item)
    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        db.session.add(ScheduleData(project_id=int(project_id), payload=payload_json))
    db.session.commit()
    return jsonify({
        'ok': True, 'pushed': len(items),
        'schedule_url': url_for('schedule_page') + f'?project_id={project_id}',
    })


@app.route('/api/permits-inspections/import-from-schedule', methods=['POST'])
@login_required
def api_permits_inspections_import_from_schedule():
    """Import permit_inspection / milestone tasks from schedule into this module."""
    from permits_inspections_persistence import serialize_item
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    record = ScheduleData.query.filter_by(project_id=int(project_id)).first()
    if not record or not record.payload:
        return jsonify({'ok': True, 'imported': 0})
    try:
        payload = json.loads(record.payload)
    except json.JSONDecodeError:
        return jsonify({'ok': True, 'imported': 0})
    imported = []
    for t in payload.get('data') or []:
        if not isinstance(t, dict):
            continue
        if t.get('permit_inspection_id'):
            continue
        is_pi = t.get('source') == 'permit_inspection'
        is_milestone = t.get('type') == 'milestone' and 'inspect' in (t.get('text') or '').lower()
        if not is_pi and not is_milestone:
            continue
        start = t.get('start_date')
        try:
            sched = datetime.strptime(str(start)[:10], '%Y-%m-%d').date() if start else None
        except (TypeError, ValueError):
            sched = None
        item = PermitInspectionItem(
            project_id=int(project_id),
            item_number=_next_permit_inspection_number(project_id),
            record_kind='inspection',
            trade='milestone',
            title=(t.get('text') or 'Schedule Milestone')[:300],
            scheduled_date=sched,
            status='Scheduled',
            schedule_task_id=str(t.get('id')),
            catalog_source='schedule_import',
            created_by_id=current_user.id,
        )
        db.session.add(item)
        db.session.flush()
        imported.append(serialize_item(item))
    db.session.commit()
    return jsonify({'ok': True, 'imported': len(imported), 'items': imported})


@app.route('/meeting-minutes')
@login_required
def meeting_minutes_page():
    return render_template('meeting_minutes.html', active_project=get_active_project())


def _next_meeting_number(project_id, prefix=None):
    from program_settings_persistence import get_numbering_prefix, format_document_number
    if project_id is None:
        q = MeetingMinute.query.filter(MeetingMinute.project_id.is_(None))
        prefix, pad = get_numbering_prefix('toolbox')
        prefix = f'{prefix}-CO'
        pad = 3
    else:
        q = MeetingMinute.query.filter_by(project_id=int(project_id))
        if not prefix:
            prefix, pad = get_numbering_prefix('meeting')
        else:
            _, pad = get_numbering_prefix('meeting')
    last = q.order_by(MeetingMinute.id.desc()).first()
    n = 1
    if last and last.meeting_number:
        try:
            n = int(str(last.meeting_number).split('-')[-1]) + 1
        except (ValueError, IndexError):
            n = (last.id or 0) + 1
    return format_document_number(prefix, n, pad)


def _meeting_upload_folder(m):
    pid = m.project_id if m.project_id is not None else 'company'
    return os.path.join(app.config['UPLOAD_FOLDER'], 'meetings', str(pid), str(m.id))


def _apply_meeting_minute(m, body):
    for field in (
        'meeting_number', 'start_time', 'end_time', 'meeting_type', 'status',
        'subject', 'location', 'virtual_link', 'organizer', 'discussion_notes', 'minutes_body',
    ):
        if field in body:
            setattr(m, field, body[field])
    for json_field, attr in (
        ('attendees', 'attendees_json'),
        ('agenda', 'agenda_json'),
        ('decisions', 'decisions_json'),
        ('transcript_segments', 'transcript_json'),
        ('speakers', 'speakers_json'),
        ('distribution', 'distribution_json'),
    ):
        if json_field in body:
            setattr(m, attr, json.dumps(body[json_field] or []))
    if 'toolbox_meta' in body and isinstance(body.get('toolbox_meta'), dict):
        from meeting_minutes_persistence import merge_toolbox_meta
        merge_toolbox_meta(m, body['toolbox_meta'])
    if 'meeting_date' in body:
        if body['meeting_date']:
            try:
                m.meeting_date = datetime.strptime(body['meeting_date'][:10], '%Y-%m-%d').date()
            except (TypeError, ValueError):
                pass
        else:
            m.meeting_date = None
    if 'next_meeting_date' in body:
        if body['next_meeting_date']:
            try:
                m.next_meeting_date = datetime.strptime(body['next_meeting_date'][:10], '%Y-%m-%d').date()
            except (TypeError, ValueError):
                pass
        else:
            m.next_meeting_date = None
    if 'recording_duration_sec' in body:
        try:
            m.recording_duration_sec = int(body['recording_duration_sec'] or 0)
        except (TypeError, ValueError):
            pass


def _sync_meeting_to_schedule(meeting):
    from meeting_minutes_persistence import upsert_meeting_tasks, task_id_for
    record = ScheduleData.query.filter_by(project_id=meeting.project_id).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except json.JSONDecodeError:
            payload = {}
    payload = upsert_meeting_tasks(payload, [meeting])
    if not meeting.schedule_task_id:
        meeting.schedule_task_id = task_id_for(meeting)
    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        db.session.add(ScheduleData(project_id=meeting.project_id, payload=payload_json))
    db.session.commit()


def _save_meeting_action_items(meeting, items):
    if items is None:
        return
    keep_ids = []
    for i, raw in enumerate(items or []):
        if not isinstance(raw, dict):
            continue
        desc = (raw.get('description') or '').strip()
        if not desc:
            continue
        aid = raw.get('id')
        item = None
        if aid:
            item = MeetingActionItem.query.filter_by(id=int(aid), meeting_id=meeting.id).first()
        if not item:
            item = MeetingActionItem(meeting_id=meeting.id, project_id=meeting.project_id)
            db.session.add(item)
        item.item_number = raw.get('item_number') or f'AI-{i + 1:02d}'
        item.description = desc
        item.assigned_to = raw.get('assigned_to') or ''
        item.status = raw.get('status') or 'Open'
        item.priority = raw.get('priority') or 'Normal'
        item.notes = raw.get('notes') or ''
        if raw.get('due_date'):
            try:
                item.due_date = datetime.strptime(raw['due_date'][:10], '%Y-%m-%d').date()
            except (TypeError, ValueError):
                item.due_date = None
        else:
            item.due_date = None
        db.session.flush()
        keep_ids.append(item.id)
    for old in MeetingActionItem.query.filter_by(meeting_id=meeting.id).all():
        if old.id not in keep_ids:
            db.session.delete(old)


@app.route('/api/meeting-minutes/catalog', methods=['GET'])
@login_required
def api_meeting_minutes_catalog():
    from meeting_minutes_catalog import (
        MEETING_TYPES, STATUSES, ACTION_STATUSES, ACTION_PRIORITIES,
        DEFAULT_SPEAKERS, AGENDA_TEMPLATES, get_agenda_template,
        TOOLBOX_COMPLIANCE, get_toolbox_topic_library, TOOLBOX_AGENDA_BRIEFINGS,
    )
    mtype = request.args.get('type')
    return jsonify({
        'ok': True,
        'meeting_types': MEETING_TYPES,
        'statuses': list(STATUSES),
        'action_statuses': list(ACTION_STATUSES),
        'action_priorities': list(ACTION_PRIORITIES),
        'default_speakers': DEFAULT_SPEAKERS,
        'agenda_template': get_agenda_template(mtype) if mtype else None,
        'agenda_templates': AGENDA_TEMPLATES,
        'toolbox_compliance': TOOLBOX_COMPLIANCE,
        'toolbox_topic_library': get_toolbox_topic_library(),
        'toolbox_agenda_briefings': TOOLBOX_AGENDA_BRIEFINGS,
    })


@app.route('/api/meeting-minutes', methods=['GET'])
@login_required
def api_meeting_minutes_list():
    from meeting_minutes_persistence import serialize_meeting, compute_stats
    from meeting_minutes_catalog import MEETING_TYPES, STATUSES
    from sqlalchemy import or_
    pid_raw = request.args.get('project_id')
    if pid_raw in ('all', '', '0'):
        project_id = None
    else:
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
    scope = (request.args.get('scope') or '').lower()
    q = MeetingMinute.query
    status = request.args.get('status')
    mtype = request.args.get('meeting_type')
    if mtype:
        q = q.filter_by(meeting_type=mtype)
    if mtype == 'toolbox_talk':
        if scope == 'company':
            q = q.filter(MeetingMinute.project_id.is_(None))
        elif scope == 'project' and project_id:
            q = q.filter(MeetingMinute.project_id == int(project_id))
        elif project_id:
            q = q.filter(or_(MeetingMinute.project_id.is_(None), MeetingMinute.project_id == int(project_id)))
        elif scope != 'all':
            q = q.filter(or_(MeetingMinute.project_id.is_(None), MeetingMinute.project_id.isnot(None)))
    elif project_id:
        q = q.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(MeetingMinute.meeting_date.desc(), MeetingMinute.id.desc()).all()
    return jsonify({
        'ok': True,
        'meetings': [serialize_meeting(r, ActionItem=MeetingActionItem) for r in rows],
        'stats': compute_stats(MeetingMinute, MeetingActionItem, project_id),
        'meeting_types': MEETING_TYPES,
        'statuses': list(STATUSES),
        'project_id': project_id,
        'schedule_url': url_for('schedule_page'),
    })


@app.route('/api/meeting-minutes', methods=['POST'])
@login_required
def api_meeting_minutes_create():
    from meeting_minutes_persistence import serialize_meeting, generate_simple_minutes, merge_toolbox_meta
    from meeting_minutes_catalog import get_agenda_template, DEFAULT_SPEAKERS
    from developer_tools import is_admin_or_developer
    body = request.get_json(silent=True) or {}
    scope = (body.get('scope') or body.get('toolbox_meta', {}).get('scope') or 'project').lower()
    project_id = body.get('project_id')
    if project_id in ('', 0, '0'):
        project_id = None
    elif project_id is not None:
        project_id = int(project_id)
    if project_id is None and scope != 'company':
        project_id = get_current_project_id()
    subject = (body.get('subject') or '').strip()
    if not subject:
        return jsonify({'error': 'subject required'}), 400
    if scope == 'company':
        if not is_admin_or_developer(current_user):
            return jsonify({'error': 'Only admins can create company-wide toolbox agendas'}), 403
        project_id = None
    elif not project_id:
        return jsonify({'error': 'project_id required for project toolbox meetings'}), 400
    mtype = body.get('meeting_type') or 'other'
    m = MeetingMinute(
        project_id=project_id,
        meeting_number=body.get('meeting_number') or _next_meeting_number(project_id, 'TB' if mtype == 'toolbox_talk' else 'MM'),
        subject=subject,
        meeting_type=mtype,
        status=body.get('status') or ('Published' if scope == 'company' else 'Draft'),
        created_by_id=current_user.id,
    )
    if not body.get('agenda'):
        m.agenda_json = json.dumps(get_agenda_template(mtype))
    if not body.get('speakers'):
        m.speakers_json = json.dumps(DEFAULT_SPEAKERS)
    _apply_meeting_minute(m, body)
    meta = dict(body.get('toolbox_meta') or {})
    meta['scope'] = scope
    if body.get('week_ending'):
        meta['week_ending'] = body['week_ending']
    if scope == 'company':
        meta['published'] = body.get('published', True)
    merge_toolbox_meta(m, meta)
    db.session.add(m)
    db.session.flush()
    _save_meeting_action_items(m, body.get('action_items'))
    if body.get('auto_generate_minutes'):
        data = serialize_meeting(m, ActionItem=MeetingActionItem)
        m.minutes_body = generate_simple_minutes(data)
    db.session.commit()
    if body.get('push_to_schedule') and m.meeting_date:
        try:
            _sync_meeting_to_schedule(m)
        except Exception:
            pass
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>', methods=['GET'])
@login_required
def api_meeting_minutes_get(meeting_id):
    from meeting_minutes_persistence import serialize_meeting
    m = MeetingMinute.query.get_or_404(meeting_id)
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>', methods=['PUT'])
@login_required
def api_meeting_minutes_update(meeting_id):
    from meeting_minutes_persistence import serialize_meeting, generate_simple_minutes
    m = MeetingMinute.query.get_or_404(meeting_id)
    body = request.get_json(silent=True) or {}
    _apply_meeting_minute(m, body)
    m.updated_at = datetime.utcnow()
    if 'action_items' in body:
        _save_meeting_action_items(m, body.get('action_items'))
    if body.get('auto_generate_minutes'):
        data = serialize_meeting(m, ActionItem=MeetingActionItem)
        m.minutes_body = generate_simple_minutes(data)
    db.session.commit()
    if body.get('push_to_schedule') or m.schedule_task_id:
        try:
            _sync_meeting_to_schedule(m)
        except Exception:
            pass
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>', methods=['DELETE'])
@login_required
def api_meeting_minutes_delete(meeting_id):
    m = MeetingMinute.query.get_or_404(meeting_id)
    if m.schedule_task_id:
        record = ScheduleData.query.filter_by(project_id=m.project_id).first()
        if record and record.payload:
            try:
                payload = json.loads(record.payload)
                data = payload.get('data') or []
                payload['data'] = [t for t in data if str(t.get('id')) != str(m.schedule_task_id)]
                record.payload = json.dumps(payload)
            except json.JSONDecodeError:
                pass
    try:
        folder = _meeting_upload_folder(m)
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, fn))
                except OSError:
                    pass
            try:
                os.rmdir(folder)
            except OSError:
                pass
    except OSError:
        pass
    db.session.delete(m)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/meeting-minutes/<int:meeting_id>/generate', methods=['POST'])
@login_required
def api_meeting_minutes_generate(meeting_id):
    from meeting_minutes_persistence import serialize_meeting, generate_simple_minutes, extract_action_items_from_text
    m = MeetingMinute.query.get_or_404(meeting_id)
    data = serialize_meeting(m, ActionItem=MeetingActionItem)
    m.minutes_body = generate_simple_minutes(data)
    if request.args.get('extract_actions') == '1':
        found = extract_action_items_from_text(m.minutes_body)
        existing = {a.description for a in m.action_items}
        for i, raw in enumerate(found):
            if raw['description'] in existing:
                continue
            item = MeetingActionItem(
                meeting_id=m.id,
                project_id=m.project_id,
                item_number=f'AI-{len(m.action_items) + i + 1:02d}',
                description=raw['description'],
                status='Open',
                priority='Normal',
            )
            db.session.add(item)
    m.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>/recording', methods=['POST'])
@login_required
def api_meeting_minutes_upload_recording(meeting_id):
    m = MeetingMinute.query.get_or_404(meeting_id)
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    _, ext = os.path.splitext(f.filename)
    if not ext:
        ext = '.webm'
    safe = secure_filename(f'recording{ext.lower()}') or f'recording{ext.lower()}'
    folder = _meeting_upload_folder(m)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe)
    f.save(path)
    m.recording_filename = safe
    try:
        m.recording_duration_sec = int(request.form.get('duration_sec') or 0)
    except (TypeError, ValueError):
        pass
    m.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({
        'ok': True,
        'recording_url': url_for('api_meeting_minutes_serve_recording', meeting_id=m.id),
        'recording_filename': safe,
        'recording_duration_sec': m.recording_duration_sec or 0,
    })


@app.route('/api/meeting-minutes/<int:meeting_id>/recording', methods=['GET'])
@login_required
def api_meeting_minutes_serve_recording(meeting_id):
    m = MeetingMinute.query.get_or_404(meeting_id)
    if not m.recording_filename:
        return jsonify({'error': 'No recording'}), 404
    folder = _meeting_upload_folder(m)
    return send_from_directory(folder, m.recording_filename)


@app.route('/api/meeting-minutes/<int:meeting_id>/file-to-documents', methods=['POST'])
@login_required
def api_meeting_minutes_file_to_documents(meeting_id):
    from meeting_minutes_persistence import serialize_meeting, generate_simple_minutes
    m = MeetingMinute.query.get_or_404(meeting_id)
    if not m.minutes_body:
        data = serialize_meeting(m, ActionItem=MeetingActionItem)
        m.minutes_body = generate_simple_minutes(data)
    sub_name = (m.meeting_date.strftime('%m-%d-%Y') if m.meeting_date else 'undated')
    fname = f'{m.meeting_number or "MM"}_{sub_name}_minutes.txt'
    body_bytes = (m.minutes_body or '').encode('utf-8')
    doc = _mirror_to_system_subfolder(
        m.project_id, body_bytes, fname, fname, 'meeting-minutes', sub_name, 'Meeting Minutes',
        {'meeting_id': m.id, 'meeting_number': m.meeting_number, 'subject': m.subject},
        is_system_locked=True, uploaded_by_id=current_user.id,
    )
    if doc and doc.get('id'):
        m.document_id = doc['id']
        db.session.commit()
        _notify_documents_team(
            m.project_id,
            'Meeting minutes filed to Documents',
            f'"{m.subject}" filed to Documents › Meeting Minutes › {sub_name}.',
            f'/documents?project_id={m.project_id}',
        )
    return jsonify({'ok': True, 'document': doc, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>/adopt', methods=['POST'])
@login_required
def api_meeting_minutes_adopt(meeting_id):
    """Copy a company-wide toolbox agenda to a project for superintendent use."""
    from meeting_minutes_persistence import serialize_meeting, merge_toolbox_meta, parse_toolbox_meta
    source = MeetingMinute.query.get_or_404(meeting_id)
    if source.meeting_type != 'toolbox_talk':
        return jsonify({'error': 'Only toolbox meetings can be adopted'}), 400
    src_meta = parse_toolbox_meta(source)
    if source.project_id is not None and src_meta.get('scope') != 'company':
        return jsonify({'error': 'Only company-wide agendas can be adopted to a project'}), 400
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    meeting_date = body.get('meeting_date')
    if meeting_date:
        try:
            meeting_date = datetime.strptime(meeting_date, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            meeting_date = source.meeting_date or datetime.utcnow().date()
    else:
        meeting_date = source.meeting_date or datetime.utcnow().date()
    m = MeetingMinute(
        project_id=int(project_id),
        meeting_number=_next_meeting_number(int(project_id), 'TB'),
        subject=body.get('subject') or source.subject,
        meeting_type='toolbox_talk',
        status='Scheduled',
        meeting_date=meeting_date,
        agenda_json=source.agenda_json,
        speakers_json=source.speakers_json,
        organizer=body.get('organizer') or source.organizer or '',
        location=body.get('location') or '',
        created_by_id=current_user.id,
    )
    merge_toolbox_meta(m, {
        'scope': 'project',
        'source_meeting_id': source.id,
        'week_ending': src_meta.get('week_ending'),
        'adopted_at': datetime.utcnow().isoformat(),
    })
    db.session.add(m)
    db.session.commit()
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>/sign-in', methods=['POST'])
@login_required
def api_meeting_minutes_sign_in_upload(meeting_id):
    from meeting_minutes_persistence import serialize_meeting, merge_toolbox_meta, parse_toolbox_meta
    m = MeetingMinute.query.get_or_404(meeting_id)
    if m.meeting_type != 'toolbox_talk':
        return jsonify({'error': 'Sign-in sheets are for toolbox meetings only'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'empty filename'}), 400
    _, ext = os.path.splitext(f.filename)
    safe = secure_filename(f'sign-in{ext.lower()}') or f'sign-in{ext.lower()}'
    folder = _meeting_upload_folder(m)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe)
    f.save(path)
    att = {
        'filename': safe,
        'original_name': f.filename,
        'uploaded_at': datetime.utcnow().isoformat(),
        'uploaded_by': f'{current_user.first_name} {current_user.last_name}'.strip(),
        'url': url_for('api_meeting_minutes_sign_in_serve', meeting_id=m.id),
    }
    merge_toolbox_meta(m, {'sign_in_attachment': att})
    m.updated_at = datetime.utcnow()
    if m.project_id:
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
            sub_name = m.meeting_date.strftime('%m-%d-%Y') if m.meeting_date else 'undated'
            doc = _mirror_to_system_subfolder(
                m.project_id, data, f.filename, safe,
                'safety', 'Toolbox Meetings', 'Safety',
                {
                    'meeting_id': m.id,
                    'meeting_number': m.meeting_number,
                    'subject': m.subject,
                    'kind': 'sign_in_sheet',
                },
                is_system_locked=True, uploaded_by_id=current_user.id,
            )
            if doc and doc.get('id'):
                att['document_id'] = doc['id']
                merge_toolbox_meta(m, {'sign_in_attachment': att})
            _notify_documents_team(
                m.project_id,
                'Toolbox sign-in sheet filed',
                f'Sign-in sheet for "{m.subject}" filed to Documents › Safety › Toolbox Meetings.',
                f'/documents?project_id={m.project_id}',
            )
        except Exception:
            db.session.rollback()
    db.session.commit()
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/<int:meeting_id>/sign-in', methods=['GET'])
@login_required
def api_meeting_minutes_sign_in_serve(meeting_id):
    from meeting_minutes_persistence import parse_toolbox_meta
    m = MeetingMinute.query.get_or_404(meeting_id)
    meta = parse_toolbox_meta(m)
    att = meta.get('sign_in_attachment') or {}
    filename = att.get('filename')
    if not filename:
        return jsonify({'error': 'No sign-in sheet'}), 404
    folder = _meeting_upload_folder(m)
    return send_from_directory(folder, filename)


@app.route('/api/meeting-minutes/<int:meeting_id>/complete', methods=['POST'])
@login_required
def api_meeting_minutes_complete(meeting_id):
    from meeting_minutes_persistence import serialize_meeting, merge_toolbox_meta, parse_toolbox_meta, generate_simple_minutes
    m = MeetingMinute.query.get_or_404(meeting_id)
    if m.meeting_type != 'toolbox_talk':
        return jsonify({'error': 'Only toolbox meetings can be completed here'}), 400
    body = request.get_json(silent=True) or {}
    meta = parse_toolbox_meta(m)
    require_sign_in = body.get('require_sign_in', True)
    if require_sign_in and not meta.get('sign_in_attachment'):
        return jsonify({'error': 'Upload the crew sign-in sheet before marking complete'}), 400
    m.status = 'Completed'
    if not m.minutes_body:
        data = serialize_meeting(m, ActionItem=MeetingActionItem)
        m.minutes_body = generate_simple_minutes(data)
    merge_toolbox_meta(m, {
        'completed_at': datetime.utcnow().isoformat(),
        'completed_by_id': current_user.id,
    })
    m.updated_at = datetime.utcnow()
    db.session.commit()
    if m.project_id and m.minutes_body:
        try:
            sub_name = m.meeting_date.strftime('%m-%d-%Y') if m.meeting_date else 'undated'
            fname = f'{m.meeting_number or "TB"}_{sub_name}_minutes.txt'
            doc = _mirror_to_system_subfolder(
                m.project_id, (m.minutes_body or '').encode('utf-8'), fname, fname,
                'safety', 'Toolbox Meetings', 'Safety',
                {'meeting_id': m.id, 'meeting_number': m.meeting_number, 'subject': m.subject},
                is_system_locked=True, uploaded_by_id=current_user.id,
            )
            if doc and doc.get('id') and not m.document_id:
                m.document_id = doc['id']
                db.session.commit()
        except Exception:
            pass
    return jsonify({'ok': True, 'meeting': serialize_meeting(m, ActionItem=MeetingActionItem)})


@app.route('/api/meeting-minutes/push-to-schedule', methods=['POST'])
@login_required
def api_meeting_minutes_push_to_schedule():
    from meeting_minutes_persistence import upsert_meeting_tasks, task_id_for
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    body = request.get_json(silent=True) or {}
    ids = body.get('ids')
    q = MeetingMinute.query.filter_by(project_id=int(project_id))
    if ids:
        q = q.filter(MeetingMinute.id.in_(ids))
    else:
        q = q.filter(MeetingMinute.meeting_date.isnot(None))
    meetings = q.all()
    if not meetings:
        return jsonify({'ok': True, 'pushed': 0})
    record = ScheduleData.query.filter_by(project_id=int(project_id)).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except json.JSONDecodeError:
            payload = {}
    payload = upsert_meeting_tasks(payload, meetings)
    for m in meetings:
        if not m.schedule_task_id:
            m.schedule_task_id = task_id_for(m)
    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        db.session.add(ScheduleData(project_id=int(project_id), payload=payload_json))
    db.session.commit()
    return jsonify({
        'ok': True, 'pushed': len(meetings),
        'schedule_url': url_for('schedule_page') + f'?project_id={project_id}',
    })


@app.route('/pay-applications')
@login_required
def pay_applications_page():
    active = get_active_project()
    fin = _project_financial_context(active)
    sub_vendor_company_linked = True
    try:
        from portal_sub_access import is_sub_vendor_portal_user, resolve_sub_vendor_company
        if is_sub_vendor_portal_user(current_user):
            cid, _, _ = resolve_sub_vendor_company(current_user, Company, db, persist_link=True)
            sub_vendor_company_linked = cid is not None
    except Exception:
        pass
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
        sub_vendor_company_linked=sub_vendor_company_linked,
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
@admin_required
def program_settings():
    from program_settings_persistence import settings_summary_for_ui, load_security_settings
    from developer_tools import is_developer
    summary = settings_summary_for_ui()
    return render_template(
        'program_settings.html',
        sage_defaults=summary['sage'],
        company_info=summary['company'],
        backup_settings=summary['backup'],
        maintenance_settings=summary['maintenance'],
        security_settings=load_security_settings(),
        is_developer=is_developer(current_user),
    )


@app.route('/developer/live-watch')
@login_required
@developer_required
def developer_live_watch_page():
    session_key = (request.args.get('session') or '').strip()
    return render_template('developer_live_watch.html', session_key=session_key)


@app.route('/developer')
@login_required
@developer_required
def developer_console():
    from program_settings_persistence import load_program_settings
    from developer_tools import (
        can_view_recovery_details,
        developer_unlock_active,
        recovery_status_for_ui,
    )
    show_recovery = can_view_recovery_details(current_user)
    return render_template(
        'developer.html',
        raw_settings=load_program_settings(),
        unlock_mode=developer_unlock_active(current_user),
        recovery_status=recovery_status_for_ui(include_sensitive=show_recovery),
        show_recovery_details=show_recovery,
    )


@app.route('/api/developer/unlock-mode', methods=['GET'])
@login_required
@developer_required
def api_get_developer_unlock_mode():
    from developer_tools import developer_unlock_active
    return jsonify({'ok': True, 'active': developer_unlock_active(current_user)})


@app.route('/api/developer/unlock-mode', methods=['POST'])
@login_required
@developer_required
def api_set_developer_unlock_mode():
    from developer_tools import set_developer_unlock_mode, developer_unlock_active
    body = request.get_json(silent=True) or {}
    active = bool(body.get('active'))
    set_developer_unlock_mode(active)
    write_audit(
        'developer_unlock_on' if active else 'developer_unlock_off',
        'Developer unlock edit mode turned on' if active else 'Developer unlock edit mode turned off',
        module='developer',
        commit=True,
    )
    return jsonify({'ok': True, 'active': developer_unlock_active(current_user)})


@app.route('/api/program-settings', methods=['GET'])
@login_required
@admin_required
def api_get_program_settings():
    from program_settings_persistence import settings_summary_for_ui
    return jsonify({'ok': True, 'settings': settings_summary_for_ui()})


@app.route('/api/program-settings/company', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_company():
    from program_settings_persistence import load_company_info, save_company_info
    if request.method == 'GET':
        return jsonify({'ok': True, 'company': load_company_info()})
    body = request.get_json(silent=True) or {}
    company = save_company_info(body)
    return jsonify({'ok': True, 'company': company})


@app.route('/api/program-settings/security', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_security():
    from program_settings_persistence import load_security_settings, save_security_settings
    if request.method == 'GET':
        return jsonify({'ok': True, 'security': load_security_settings()})
    body = request.get_json(silent=True) or {}
    security = save_security_settings(body)
    write_audit('Updated security settings', 'Program security policy', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'security': security})


@app.route('/api/program-settings/backup', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_backup():
    from program_settings_persistence import load_backup_settings, save_backup_settings, load_maintenance_settings, save_maintenance_settings
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'backup': load_backup_settings(),
            'maintenance': load_maintenance_settings(),
        })
    body = request.get_json(silent=True) or {}
    backup = save_backup_settings(body.get('backup') or body)
    maintenance = save_maintenance_settings(body.get('maintenance') or {})
    return jsonify({'ok': True, 'backup': backup, 'maintenance': maintenance})


@app.route('/api/program-settings/backup/plan', methods=['POST'])
@login_required
@admin_required
def api_plan_program_backup():
    from backup_service import plan_backup_destinations
    body = request.get_json(silent=True) or {}
    cfg = body.get('backup') if isinstance(body.get('backup'), dict) else {}
    return jsonify({'ok': True, 'destinations': plan_backup_destinations(cfg)})


@app.route('/api/program-settings/backup/run', methods=['POST'])
@login_required
@admin_required
def api_run_program_backup():
    from backup_service import get_backup_job, list_backups, start_backup_job
    from program_settings_persistence import load_backup_settings, save_backup_settings
    body = request.get_json(silent=True) or {}
    cfg = load_backup_settings()
    if isinstance(body.get('backup'), dict):
        incoming = body['backup']
        cloud = incoming.get('cloud') if isinstance(incoming.get('cloud'), dict) else {}
        cfg = {
            **cfg,
            **{k: incoming[k] for k in ('auto_enabled', 'frequency', 'retention_days', 'local_path', 'maintenance_window') if k in incoming},
            'cloud': {**(cfg.get('cloud') or {}), **cloud},
        }
        save_backup_settings(cfg)
        cfg = load_backup_settings()

    async_mode = body.get('async', True)
    if not async_mode:
        from backup_service import run_configured_backup, format_display_time
        try:
            result = run_configured_backup(cfg, manual=True)
            status = 'success'
            if result.get('cloud_mirror_status') == 'success':
                status = f"success — copied to {result.get('cloud_mirror')}"
            elif result.get('cloud_mirror_skipped'):
                status = f"success (local only) — {result.get('cloud_mirror_skipped')}"
            cfg['last_run_at'] = result.get('created_at_display') or result.get('created_at', '')
            cfg['last_run_status'] = status
            save_backup_settings(cfg)
            return jsonify({'ok': True, 'result': result, 'backups': list_backups(cfg)})
        except Exception as exc:
            cfg['last_run_status'] = f'error: {exc}'
            save_backup_settings(cfg)
            return jsonify({'error': str(exc)}), 500

    job_id = start_backup_job(app, cfg, manual=True)
    return jsonify({'ok': True, 'job_id': job_id})


@app.route('/api/program-settings/backup/run/status/<job_id>', methods=['GET'])
@login_required
@admin_required
def api_run_program_backup_status(job_id):
    from backup_service import format_display_time, get_backup_job, list_backups
    from program_settings_persistence import load_backup_settings, save_backup_settings
    job = get_backup_job(job_id)
    if not job:
        return jsonify({'error': 'Backup job not found'}), 404

    if job.get('status') in ('done', 'error'):
        cfg = load_backup_settings()
        if job.get('status') == 'done' and job.get('result') and not job.get('finalized'):
            result = job['result']
            status = 'success'
            if result.get('cloud_mirror_status') == 'success':
                status = f"success — copied to {result.get('cloud_mirror')}"
            elif result.get('cloud_mirror_skipped'):
                status = f"success (local only) — {result.get('cloud_mirror_skipped')}"
            cfg['last_run_at'] = result.get('created_at_display') or format_display_time(result.get('created_at'))
            cfg['last_run_status'] = status
            save_backup_settings(cfg)
            from backup_service import mark_backup_job_finalized
            mark_backup_job_finalized(job_id)
            job = dict(job)
            job['backups'] = list_backups(cfg)
        elif job.get('status') == 'error' and not job.get('finalized'):
            cfg['last_run_status'] = f"error: {job.get('error')}"
            save_backup_settings(cfg)
            from backup_service import mark_backup_job_finalized
            mark_backup_job_finalized(job_id)

    return jsonify({'ok': True, 'job': job})


@app.route('/api/program-settings/backup/list', methods=['GET'])
@login_required
@admin_required
def api_list_program_backups():
    from backup_service import list_backups
    from program_settings_persistence import load_backup_settings
    try:
        backups = list_backups(load_backup_settings())
        return jsonify({'ok': True, 'backups': backups})
    except Exception as exc:
        app.logger.exception('Failed to list program backups')
        return jsonify({
            'ok': False,
            'error': str(exc) or 'Unable to list backups',
            'backups': [],
        }), 200


def _migrate_program_schemas():
    """Apply schema migrations after restore, clear, or fresh install."""
    try:
        _bootstrap_user_schema(db)
    except Exception:
        pass
    try:
        import case_workflow as cw
        cw.ensure_workflow_schema(db.engine)
    except Exception:
        pass
    for hook in (
        ('pay_app_persistence', 'ensure_pay_app_schema'),
        ('companies_persistence', 'ensure_company_schema'),
        ('co_persistence', 'ensure_co_schema'),
        ('rfi_persistence', 'ensure_rfi_schema'),
        ('submittal_persistence', 'ensure_submittal_schema'),
        ('drawing_persistence', 'ensure_drawing_schema'),
        ('commitment_persistence', 'ensure_commitment_schema'),
        ('document_persistence', 'ensure_document_schema'),
    ):
        try:
            mod = __import__(hook[0], fromlist=[hook[1]])
            fn = getattr(mod, hook[1])
            if hook[0] == 'companies_persistence':
                fn(db)
            else:
                fn(db.engine, db)
        except Exception:
            pass
    try:
        ensure_project_schema()
    except Exception:
        pass


def _seed_fresh_program_database():
    """Recreate an empty database with default admin + recovery accounts."""
    db.create_all()
    _migrate_program_schemas()

    admin = User.query.filter_by(email='admin@casepm.local').first()
    if not admin:
        admin = User(
            first_name='Admin',
            last_name='User',
            email='admin@casepm.local',
            role='Admin',
            status='Active',
            must_change_password=False,
            require_2fa=False,
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
    try:
        from developer_tools import ensure_recovery_user
        ensure_recovery_user(db, User)
    except Exception:
        pass


@app.route('/api/program-settings/backup/restore', methods=['POST'])
@login_required
@admin_required
def api_restore_program_backup():
    from backup_service import restore_from_backup, list_backups
    from program_settings_persistence import load_backup_settings
    body = request.get_json(silent=True) or {}
    filename = (body.get('filename') or '').strip()
    if not filename:
        return jsonify({'error': 'filename is required'}), 400
    cfg = load_backup_settings()
    try:
        result = restore_from_backup(filename, backup_config=cfg, db=db)
        _migrate_program_schemas()
        write_audit(
            'BACKUP_RESTORED',
            detail=f'Installed backup {result.get("restored_from")}',
            module='program_settings',
            commit=True,
        )
        return jsonify({'ok': True, 'result': result, 'backups': list_backups(cfg)})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400


@app.route('/api/program-settings/backup/upload', methods=['POST'])
@login_required
@admin_required
def api_upload_program_backup():
    from backup_service import save_uploaded_backup, list_backups
    from program_settings_persistence import load_backup_settings
    upload = request.files.get('backup')
    cfg = load_backup_settings()
    try:
        saved = save_uploaded_backup(upload, backup_config=cfg)
        write_audit(
            'BACKUP_UPLOADED',
            detail=f'Uploaded backup {saved.get("filename")}',
            module='program_settings',
            commit=True,
        )
        return jsonify({'ok': True, 'backup': saved, 'backups': list_backups(cfg)})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


@app.route('/api/program-settings/backup/clear-all', methods=['POST'])
@login_required
@admin_required
def api_clear_all_program_data():
    return jsonify({
        'error': 'Clear All Program Data has moved to Developer Console → Maintenance.',
    }), 403


@app.route('/api/program-settings/email', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_email():
    """Company / workflow SMTP settings for system notifications."""
    from program_settings_persistence import load_company_email_settings, save_company_email_settings
    if request.method == 'GET':
        return jsonify({'ok': True, 'email': load_company_email_settings(mask_secret=True), 'scope': 'company'})
    body = request.get_json(silent=True) or {}
    email = save_company_email_settings(body.get('email') or body)
    write_audit('Updated company email settings', 'Program workflow SMTP', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'email': email, 'scope': 'company'})


@app.route('/api/program-settings/email/users-summary', methods=['GET'])
@login_required
@admin_required
def api_program_settings_email_users_summary():
    from user_email_connection_persistence import list_users_email_summary, ensure_user_email_connection_schema
    ensure_user_email_connection_schema(db)
    return jsonify({
        'ok': True,
        'users': list_users_email_summary(User=User, UserEmailConnection=UserEmailConnection),
    })


@app.route('/api/program-settings/numbering', methods=['GET', 'PUT'])
@login_required
def api_program_settings_numbering():
    from program_settings_persistence import load_numbering_config, save_numbering_config, NUMBERING_DEFAULTS, format_document_number
    if request.method == 'GET':
        cfg = load_numbering_config()
        catalog = [{
            'key': key,
            'label': defaults.get('label', key),
            'prefix': cfg[key].get('prefix'),
            'pad': cfg[key].get('pad'),
            'scope': cfg[key].get('scope'),
            'example': format_document_number(cfg[key].get('prefix', 'DOC'), 1, cfg[key].get('pad', 3)),
        } for key, defaults in NUMBERING_DEFAULTS.items()]
        return jsonify({'ok': True, 'numbering': cfg, 'catalog': catalog})
    if current_user.role != 'Admin':
        return jsonify({'error': 'Admin only'}), 403
    body = request.get_json(silent=True) or {}
    saved = save_numbering_config(body.get('numbering') or body)
    return jsonify({'ok': True, 'numbering': saved})


@app.route('/api/program-settings/pay-apps', methods=['GET', 'PUT'])
@login_required
def api_program_settings_pay_apps():
    from program_settings_persistence import load_pay_app_defaults, save_pay_app_defaults
    if request.method == 'GET':
        return jsonify({'ok': True, 'pay_apps': load_pay_app_defaults()})
    if current_user.role != 'Admin':
        return jsonify({'error': 'Admin only'}), 403
    body = request.get_json(silent=True) or {}
    saved = save_pay_app_defaults(body.get('pay_apps') or body)
    return jsonify({'ok': True, 'pay_apps': saved})


@app.route('/api/program-settings/documents', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_documents():
    from program_settings_persistence import load_document_defaults, save_document_defaults
    if request.method == 'GET':
        return jsonify({'ok': True, 'documents': load_document_defaults()})
    body = request.get_json(silent=True) or {}
    saved = save_document_defaults(body.get('documents') or body)
    write_audit('Updated document defaults', 'Program document settings', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'documents': saved})


@app.route('/api/program-settings/notifications', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_notifications():
    from program_settings_persistence import load_notification_defaults, save_notification_defaults
    from user_extended_prefs import NOTIFICATION_MODULES
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'notifications': load_notification_defaults(),
            'modules_catalog': [{'key': k, 'label': lbl} for k, lbl in NOTIFICATION_MODULES],
        })
    body = request.get_json(silent=True) or {}
    saved = save_notification_defaults(body.get('notifications') or body)
    write_audit('Updated notification defaults', 'Program notification settings', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'notifications': saved})


@app.route('/api/program-settings/estimating', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_estimating():
    from program_settings_persistence import load_estimating_defaults, save_estimating_defaults
    from estimate_features import RFP_NOTIFY_MODES
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'estimating': load_estimating_defaults(),
            'notify_modes': list(RFP_NOTIFY_MODES),
        })
    body = request.get_json(silent=True) or {}
    saved = save_estimating_defaults(body.get('estimating') or body)
    write_audit('Updated estimating defaults', 'Program estimating settings', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'estimating': saved})


@app.route('/api/program-settings/inspections', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_inspections():
    from program_settings_persistence import load_inspection_defaults, save_inspection_defaults
    from inspection_reminders import REMINDER_OPTIONS
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'inspections': load_inspection_defaults(),
            'reminder_options': list(REMINDER_OPTIONS),
        })
    body = request.get_json(silent=True) or {}
    saved = save_inspection_defaults(body.get('inspections') or body)
    write_audit('Updated inspection defaults', 'Program inspection settings', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'inspections': saved})


@app.route('/api/program-settings/regional', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_regional():
    from program_settings_persistence import load_regional_defaults, save_regional_defaults
    from user_extended_prefs import LOCALE_OPTIONS, DATE_FORMAT_OPTIONS
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'regional': load_regional_defaults(),
            'locale_options': list(LOCALE_OPTIONS),
            'date_format_options': list(DATE_FORMAT_OPTIONS),
        })
    body = request.get_json(silent=True) or {}
    saved = save_regional_defaults(body.get('regional') or body)
    write_audit('Updated regional defaults', 'Program locale settings', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'regional': saved})


@app.route('/api/program-settings/workflow', methods=['GET', 'PUT'])
@login_required
@admin_required
def api_program_settings_workflow():
    from program_settings_persistence import load_workflow_defaults, save_workflow_defaults
    if request.method == 'GET':
        return jsonify({'ok': True, 'workflow': load_workflow_defaults()})
    body = request.get_json(silent=True) or {}
    saved = save_workflow_defaults(body.get('workflow') or body)
    write_audit('Updated workflow defaults', 'Program workflow settings', module='program_settings', category='settings', commit=True)
    return jsonify({'ok': True, 'workflow': saved})


@app.route('/api/program-settings/integrations', methods=['GET'])
@login_required
@admin_required
def api_program_settings_integrations():
    from program_settings_persistence import integrations_status, load_sage_defaults
    return jsonify({
        'ok': True,
        'integrations': integrations_status(),
        'sage': load_sage_defaults(),
    })


@app.route('/api/program-settings/sage/test', methods=['POST'])
@login_required
@admin_required
def api_test_sage_connection():
    import os
    from program_settings_persistence import load_sage_defaults
    sage = load_sage_defaults()
    api_url = (sage.get('sage_api_url') or os.environ.get('SAGE_API_URL', '')).strip()
    if not api_url:
        return jsonify({
            'ok': True,
            'mode': 'simulated',
            'message': 'No live API URL — Sage database defaults saved; sync will log/simulate until SAGE_API_URL is set.',
            'database': sage.get('sage_database'),
            'company_code': sage.get('sage_company_code'),
        })
    return jsonify({
        'ok': True,
        'mode': 'configured',
        'message': f'API endpoint configured: {api_url}',
        'database': sage.get('sage_database'),
        'company_code': sage.get('sage_company_code'),
    })


@app.route('/api/developer/override-project-number', methods=['POST'])
@login_required
@developer_required
def api_developer_override_project_number():
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id')
    new_number = body.get('number')
    if not project_id or not new_number:
        return jsonify({'error': 'project_id and number required'}), 400
    project = Project.query.get_or_404(int(project_id))
    from developer_tools import override_project_number
    override_project_number(project, new_number, _normalize_project_number)
    db.session.commit()
    return jsonify({'ok': True, 'project': project.to_dict()})


@app.route('/api/developer/unlock-change-order', methods=['POST'])
@login_required
@developer_required
def api_developer_unlock_change_order():
    body = request.get_json(silent=True) or {}
    co_id = body.get('change_order_id')
    if not co_id:
        return jsonify({'error': 'change_order_id required'}), 400
    co = ChangeOrder.query.get_or_404(int(co_id))
    from developer_tools import unlock_change_order
    unlock_change_order(co)
    db.session.commit()
    from co_persistence import co_to_dict
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({'ok': True, 'change_order': co_to_dict(co, allocs)})


def _developer_actor():
    return (getattr(current_user, 'email', None) or 'developer').strip()


@app.route('/api/developer/updates/status', methods=['GET'])
@login_required
@developer_required
def api_developer_updates_status():
    from program_updates import get_status, get_history, list_snapshots
    status = get_status()
    status['history'] = get_history(20)
    status['snapshots'] = list_snapshots()
    status['running_build'] = app.config.get('CASEPM_STARTUP_BUILD')
    git_commit = (status.get('git') or {}).get('commit') or ''
    status['restart_required'] = bool(
        status['running_build'] and git_commit and status['running_build'] != git_commit
    )
    return jsonify({'ok': True, **status})


@app.route('/api/developer/updates/settings', methods=['PUT'])
@login_required
@developer_required
def api_developer_updates_settings():
    from program_updates import save_snapshot_folder, snapshot_dir
    body = request.get_json(silent=True) or {}
    folder = save_snapshot_folder(body.get('snapshot_folder'))
    write_audit('dev_update_settings', f'Snapshot folder set to {folder}', module='developer', commit=True)
    return jsonify({'ok': True, 'snapshot_folder': snapshot_dir()})


@app.route('/api/developer/updates/snapshot', methods=['POST'])
@login_required
@developer_required
def api_developer_updates_snapshot():
    from program_updates import create_snapshot, list_snapshots
    body = request.get_json(silent=True) or {}
    try:
        result = create_snapshot(
            label=body.get('label') or '',
            note=body.get('note') or '',
            actor=_developer_actor(),
        )
        write_audit('dev_code_snapshot', result.get('filename') or 'snapshot', module='developer', commit=True)
        return jsonify({'ok': True, 'result': result, 'snapshots': list_snapshots()})
    except (OSError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.route('/api/developer/updates/restore', methods=['POST'])
@login_required
@developer_required
def api_developer_updates_restore():
    from program_updates import restore_snapshot, list_snapshots, get_history
    body = request.get_json(silent=True) or {}
    filename = (body.get('filename') or '').strip()
    if not filename:
        return jsonify({'error': 'filename required'}), 400
    try:
        result = restore_snapshot(filename, actor=_developer_actor())
        write_audit('dev_code_rollback', filename, module='developer', commit=True)
        return jsonify({
            'ok': True,
            'result': result,
            'snapshots': list_snapshots(),
            'history': get_history(20),
        })
    except (OSError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.route('/api/developer/updates/install', methods=['POST'])
@login_required
@developer_required
def api_developer_updates_install():
    from program_updates import apply_update_zip, list_snapshots, get_history
    upload = request.files.get('file')
    if not upload:
        return jsonify({'error': 'file required'}), 400
    try:
        result = apply_update_zip(
            upload,
            label=request.form.get('label') or '',
            note=request.form.get('note') or '',
            actor=_developer_actor(),
        )
        write_audit('dev_code_install', result.get('upload_name') or 'update zip', module='developer', commit=True)
        return jsonify({
            'ok': True,
            'result': result,
            'snapshots': list_snapshots(),
            'history': get_history(20),
        })
    except (OSError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.route('/api/developer/updates/git-pull', methods=['POST'])
@login_required
@developer_required
def api_developer_updates_git_pull():
    from program_updates import git_pull_update, get_status, get_history
    try:
        result = git_pull_update(actor=_developer_actor())
        write_audit('dev_git_pull', result.get('git_after', {}).get('commit') or 'git pull', module='developer', commit=True)
        status = get_status()
        status['history'] = get_history(20)
        return jsonify({'ok': True, 'result': result, 'status': status})
    except (OSError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


def _maintenance_models_dict():
    from developer_data_maintenance import build_models_dict
    return build_models_dict({
        'Project': Project,
        'Document': Document,
        'DocumentFolder': DocumentFolder,
        'DocumentShareLink': DocumentShareLink,
        'DocumentFolderShareLink': DocumentFolderShareLink,
        'DocumentVersion': DocumentVersion,
        'DocumentComment': DocumentComment,
        'DocumentActivity': DocumentActivity,
        'DocumentMarkup': DocumentMarkup,
        'DocumentFolderPermission': DocumentFolderPermission,
        'Drawing': Drawing,
        'DrawingRevision': DrawingRevision,
        'DrawingMarkup': DrawingMarkup,
        'RFI': RFI,
        'ChangeOrder': ChangeOrder,
        'ChangeOrderAllocation': ChangeOrderAllocation,
        'ChangeOrderRevision': ChangeOrderRevision,
        'PotentialChangeOrder': PotentialChangeOrder,
        'PCOAllocation': PCOAllocation,
        'ChangeEvent': ChangeEvent,
        'SubcontractorRFQ': SubcontractorRFQ,
        'RFQAllocation': RFQAllocation,
        'ChangeOrderRequest': ChangeOrderRequest,
        'CORAllocation': CORAllocation,
        'Commitment': Commitment,
        'CommitmentAllocation': CommitmentAllocation,
        'BudgetProjectState': BudgetProjectState,
        'PayAppProjectState': PayAppProjectState,
        'Submittal': Submittal,
        'PunchItem': PunchItem,
        'DailyLog': DailyLog,
        'ManpowerEntry': ManpowerEntry,
        'EquipmentEntry': EquipmentEntry,
        'WeeklyReport': WeeklyReport,
        'SafetyReport': SafetyReport,
        'SafetyCertification': SafetyCertification,
        'SafetyTrainingEvent': SafetyTrainingEvent,
        'ScheduleData': ScheduleData,
        'ScheduleTask': ScheduleTask,
        'Delivery': Delivery,
        'PermitInspectionItem': PermitInspectionItem,
        'MeetingMinute': MeetingMinute,
        'MeetingActionItem': MeetingActionItem,
        'Photo': Photo,
        'SageSyncEvent': SageSyncEvent,
        'Company': Company,
        'COI': COI,
        'AuditLog': AuditLog,
    })


@app.route('/api/presence/heartbeat', methods=['POST'])
@login_required
def api_presence_heartbeat():
    from user_presence_persistence import upsert_presence_heartbeat
    body = request.get_json(silent=True) or {}
    try:
        session_key = upsert_presence_heartbeat(db, current_user, body)
        return jsonify({'ok': True, 'session_key': session_key})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/developer/presence', methods=['GET'])
@login_required
@developer_required
def api_developer_presence_list():
    from user_presence_persistence import list_online_presence
    data = list_online_presence(db)
    return jsonify({'ok': True, **data})


@app.route('/api/developer/presence/session/<session_key>', methods=['GET'])
@login_required
@developer_required
def api_developer_presence_session(session_key):
    from user_presence_persistence import get_presence_session
    row = get_presence_session(db, session_key)
    if not row:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify({'ok': True, 'session': row})


@app.route('/api/developer/presence/thumbnail/<session_key>', methods=['GET'])
@login_required
@developer_required
def api_developer_presence_thumbnail(session_key):
    from flask import send_file
    from user_presence_persistence import _thumb_path, thumbnail_exists
    if not thumbnail_exists(session_key):
        return jsonify({'error': 'No thumbnail'}), 404
    return send_file(_thumb_path(session_key), mimetype='image/jpeg', max_age=0)


@app.route('/api/developer/maintenance/catalog', methods=['GET'])
@login_required
@developer_required
def api_developer_maintenance_catalog():
    from developer_data_maintenance import maintenance_catalog_for_api
    return jsonify({'ok': True, **maintenance_catalog_for_api(Project)})


@app.route('/api/developer/maintenance/clear', methods=['POST'])
@login_required
@developer_required
def api_developer_maintenance_clear():
    from developer_data_maintenance import resolve_project_ids, clear_module_data, MODULE_CATALOG
    body = request.get_json(silent=True) or {}
    module_key = (body.get('module') or '').strip().lower()
    all_projects = bool(body.get('all_projects'))
    project_ids_raw = body.get('project_ids') or []
    confirm = (body.get('confirm') or '').strip().upper()

    valid_keys = {m['key'] for m in MODULE_CATALOG}
    if module_key not in valid_keys:
        return jsonify({'error': f'Unknown module: {module_key or "(empty)"}'}), 400

    project_ids, err = resolve_project_ids(db, Project, all_projects=all_projects, project_ids=project_ids_raw)
    if err:
        return jsonify({'error': err}), 400

    module_meta = next(m for m in MODULE_CATALOG if m['key'] == module_key)
    if module_meta.get('scope') == 'global' and not all_projects:
        return jsonify({'error': 'Companies & COI can only be cleared when All Projects is selected.'}), 400

    if module_key in ('projects', 'companies') or module_meta.get('danger'):
        if confirm != 'CLEAR':
            return jsonify({'error': 'Type CLEAR to confirm this action.'}), 400
    elif confirm != 'CLEAR':
        return jsonify({'error': 'Type CLEAR to confirm clearing module data.'}), 400

    upload_root = app.config.get('UPLOAD_FOLDER', 'uploads')
    models = _maintenance_models_dict()
    try:
        result = clear_module_data(
            db, module_key, project_ids, upload_root, models, all_projects=all_projects,
        )
        db.session.commit()
        scope_label = 'all projects' if all_projects else f'project(s) {", ".join(str(p) for p in project_ids)}'
        write_audit(
            'DEV_DATA_CLEARED',
            detail=f'Cleared {module_key} for {scope_label}',
            module='developer',
            project_id=project_ids[0] if len(project_ids) == 1 else None,
            commit=True,
        )
        return jsonify({
            'ok': True,
            'module': module_key,
            'all_projects': all_projects,
            'project_ids': project_ids,
            'result': result,
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/developer/maintenance/clear-all-program', methods=['POST'])
@login_required
@developer_required
def api_developer_clear_all_program_data():
    from backup_service import clear_all_program_data, list_backups
    from program_settings_persistence import load_backup_settings
    body = request.get_json(silent=True) or {}
    if (body.get('confirm') or '').strip().upper() != 'DELETE ALL':
        return jsonify({'error': 'Type DELETE ALL to confirm clearing all program data.'}), 400
    cfg = load_backup_settings()
    try:
        result = clear_all_program_data(backup_config=cfg, db=db)
        _seed_fresh_program_database()
        write_audit(
            'PROGRAM_DATA_CLEARED',
            detail='All program data cleared via Developer Console',
            module='developer',
            commit=True,
        )
        return jsonify({
            'ok': True,
            'result': result,
            'backups': list_backups(cfg),
            'default_login': {'email': 'admin@casepm.local', 'password': 'admin123'},
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/program-settings/sage', methods=['GET'])
@login_required
@admin_required
def api_get_sage_program_settings():
    from program_settings_persistence import load_sage_defaults, SAGE_DEFAULT_KEYS
    sage = load_sage_defaults()
    return jsonify({'sage': sage, 'keys': SAGE_DEFAULT_KEYS})


@app.route('/api/program-settings/sage', methods=['PUT'])
@login_required
@admin_required
def api_save_sage_program_settings():
    from program_settings_persistence import save_sage_defaults
    body = request.get_json(silent=True) or {}
    sage = save_sage_defaults(body.get('sage') or body)
    return jsonify({'ok': True, 'sage': sage})


@app.route('/profile')
@login_required
def profile():
    return redirect(url_for('dashboard'))


@app.route('/api/profile/me', methods=['GET'])
@login_required
def api_profile_me():
    from user_profile_persistence import ensure_user_profile_schema, serialize_profile
    ensure_user_profile_schema(db)
    return jsonify({'ok': True, 'profile': serialize_profile(current_user)})


@app.route('/api/profile/me', methods=['PUT'])
@login_required
def api_profile_me_update():
    from user_profile_persistence import ensure_user_profile_schema, serialize_profile
    ensure_user_profile_schema(db)
    body = request.get_json(silent=True) or {}
    if request.form:
        body = {**body, **{k: request.form.get(k) for k in request.form}}
    if body.get('first_name') is not None:
        current_user.first_name = str(body.get('first_name', '')).strip() or current_user.first_name
    if body.get('last_name') is not None:
        current_user.last_name = str(body.get('last_name', '')).strip() or current_user.last_name
    if body.get('phone') is not None:
        current_user.phone = str(body.get('phone', '')).strip()
    if body.get('job_title') is not None:
        current_user.job_title = str(body.get('job_title', '')).strip()
    if body.get('address') is not None:
        current_user.address = str(body.get('address', '')).strip()
    db.session.commit()
    return jsonify({'ok': True, 'profile': serialize_profile(current_user)})


@app.route('/api/profile/me/photo', methods=['POST'])
@login_required
def api_profile_me_photo():
    from user_profile_persistence import ensure_user_profile_schema, save_profile_image, serialize_profile
    ensure_user_profile_schema(db)
    file = request.files.get('photo') or request.files.get('file')
    try:
        save_profile_image(current_user, file)
        db.session.commit()
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'profile': serialize_profile(current_user)})


@app.route('/api/users/me/profile-image')
@login_required
def api_profile_me_image():
    path = getattr(current_user, 'profile_image_path', None)
    if not path or not os.path.isfile(path):
        return '', 404
    from flask import send_file
    return send_file(path, max_age=3600)


# ==================== PROFILE UPDATE ROUTE (legacy form) ====================

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        from user_profile_persistence import ensure_user_profile_schema
        ensure_user_profile_schema(db)
        current_user.first_name = request.form.get('first_name', current_user.first_name)
        current_user.last_name = request.form.get('last_name', current_user.last_name)
        current_user.phone = request.form.get('phone', current_user.phone)
        if request.form.get('job_title') is not None:
            current_user.job_title = request.form.get('job_title', '')
        if request.form.get('address') is not None:
            current_user.address = request.form.get('address', '')

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


# ==================== ERROR HANDLERS ====================

@app.route('/favicon.ico')
def favicon():
    icon = os.path.join(app.root_path, 'static', 'img', 'casepm-desktop-icon.ico')
    if os.path.isfile(icon):
        return send_from_directory(os.path.join(app.root_path, 'static', 'img'), 'casepm-desktop-icon.ico')
    icon = os.path.join(app.root_path, 'static', 'img', 'casepm-icon.ico')
    if os.path.isfile(icon):
        return send_from_directory(os.path.join(app.root_path, 'static', 'img'), 'casepm-icon.ico')
    return '', 204


@app.errorhandler(404)
def page_not_found(e):
    if request.path == '/favicon.ico':
        return '', 204
    if (request.path or '').startswith('/api/'):
        return jsonify({'error': 'Not found', 'path': request.path}), 404
    return 'Page not found', 404


@app.errorhandler(500)
def internal_server_error(e):
    import traceback

    db.session.rollback()
    debug = os.environ.get('CASEPM_DEBUG', '1').lower() not in ('0', 'false', 'no')
    if debug:
        print('\n=== Case PM 500 error ===')
        if e is not None:
            traceback.print_exception(type(e), e, getattr(e, '__traceback__', None))
        else:
            traceback.print_exc()
        print('=== end 500 ===\n')
        if app.debug:
            body = traceback.format_exception(type(e), e, getattr(e, '__traceback__', None)) if e else traceback.format_exc()
            return '<pre style="white-space:pre-wrap">' + ''.join(body) + '</pre>', 500
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
    from audit_log_persistence import audit_modules_for_page, AUDIT_CATEGORIES, ensure_audit_log_schema
    ensure_audit_log_schema(db)
    return render_template(
        'audit_log.html',
        audit_modules=audit_modules_for_page(),
        audit_categories=AUDIT_CATEGORIES,
    )


@app.route('/audit_log')
@login_required
@admin_required
def audit_log_page():
    from audit_log_persistence import audit_modules_for_page, AUDIT_CATEGORIES, ensure_audit_log_schema
    ensure_audit_log_schema(db)
    return render_template(
        'audit_log.html',
        audit_modules=audit_modules_for_page(),
        audit_categories=AUDIT_CATEGORIES,
    )


@app.route('/api/audit-log/events', methods=['GET'])
@login_required
@admin_required
def api_audit_log_list():
    from audit_log_persistence import ensure_audit_log_schema, query_audit_logs, serialize_log
    ensure_audit_log_schema(db)
    rows, total = query_audit_logs(AuditLog, request.args)
    return jsonify({
        'ok': True,
        'events': [serialize_log(r) for r in rows],
        'total': total,
        'limit': request.args.get('limit', 100),
        'offset': request.args.get('offset', 0),
    })


@app.route('/api/audit-log/events', methods=['POST'])
@login_required
@admin_required
def api_audit_log_create():
    from audit_log_persistence import ensure_audit_log_schema, record_audit, serialize_log
    ensure_audit_log_schema(db)
    body = request.get_json(silent=True) or {}
    row = record_audit(db, AuditLog, current_user, **body)
    db.session.commit()
    return jsonify({'ok': True, 'event': serialize_log(row, current_user)})


@app.route('/api/audit-log/events/batch', methods=['POST'])
@login_required
@admin_required
def api_audit_log_batch():
    from audit_log_persistence import ensure_audit_log_schema, record_audit_batch
    ensure_audit_log_schema(db)
    body = request.get_json(silent=True) or {}
    events = body.get('events') or []
    try:
        record_audit_batch(db, AuditLog, current_user, events)
        db.session.commit()
        return jsonify({'ok': True, 'imported': len(events)})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


@app.route('/api/audit-log/stats', methods=['GET'])
@login_required
@admin_required
def api_audit_log_stats():
    from audit_log_persistence import ensure_audit_log_schema, audit_stats
    ensure_audit_log_schema(db)
    return jsonify({'ok': True, 'stats': audit_stats(AuditLog)})


@app.route('/api/audit-log/modules', methods=['GET'])
@login_required
@admin_required
def api_audit_log_modules():
    from audit_log_persistence import audit_modules_for_page, AUDIT_CATEGORIES
    return jsonify({'ok': True, 'modules': audit_modules_for_page(), 'categories': AUDIT_CATEGORIES})


# ==================== EMAIL PAGE ====================
@app.route('/email')
@login_required
def email_page():
    from developer_tools import is_admin_or_developer, is_developer
    from email_mailbox_persistence import list_mailbox_owners_for_actor
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    mailbox_owners = list_mailbox_owners_for_actor(
        current_user, User=User, EmailMailboxAccess=EmailMailboxAccess,
    )
    return render_template(
        'email.html',
        users=[{'name': u.full_name, 'email': u.email} for u in users],
        email_mailbox_ctx={
            'current_user_id': current_user.id,
            'can_browse_other_mailboxes': is_admin_or_developer(current_user),
            'is_developer': is_developer(current_user),
            'mailbox_owners': mailbox_owners,
        },
    )


def _email_mailbox_user_id():
    from email_mailbox_persistence import resolve_mailbox_user_id
    requested = request.args.get('user_id', type=int)
    if request.method in ('PUT', 'POST', 'DELETE'):
        body = request.get_json(silent=True) or {}
        requested = requested or body.get('user_id')
    try:
        return resolve_mailbox_user_id(
            current_user, requested, User=User, EmailMailboxAccess=EmailMailboxAccess,
        )
    except PermissionError:
        return None


@app.route('/api/email/mailbox-owners')
@login_required
def api_email_mailbox_owners():
    from email_mailbox_persistence import list_mailbox_owners_for_actor
    owners = list_mailbox_owners_for_actor(
        current_user, User=User, EmailMailboxAccess=EmailMailboxAccess,
    )
    return jsonify({'ok': True, 'owners': owners, 'current_user_id': current_user.id})


@app.route('/api/email/mailbox', methods=['GET', 'PUT'])
@login_required
def api_email_mailbox():
    from email_mailbox_persistence import load_user_mailbox, save_user_mailbox
    try:
        uid = _email_mailbox_user_id()
    except Exception:
        return jsonify({'error': 'Mailbox access denied'}), 403
    if uid is None:
        return jsonify({'error': 'Mailbox access denied'}), 403
    if request.method == 'GET':
        payload = load_user_mailbox(uid, UserEmailMailbox=UserEmailMailbox)
        return jsonify({
            'ok': True,
            'user_id': uid,
            'messages': payload.get('messages') or [],
            'meta': payload.get('meta') or {},
            'updated_at': payload.get('updated_at'),
        })
    body = request.get_json(silent=True) or {}
    messages = body.get('messages')
    meta = body.get('meta')
    if messages is None:
        return jsonify({'error': 'messages required'}), 400
    from email_mailbox_persistence import can_send_as_mailbox
    if uid != current_user.id and not can_send_as_mailbox(
        current_user, uid, EmailMailboxAccess=EmailMailboxAccess,
    ):
        return jsonify({'error': 'Send/edit access denied for this mailbox'}), 403
    saved = save_user_mailbox(uid, messages, meta or {}, db=db, UserEmailMailbox=UserEmailMailbox)
    return jsonify({'ok': True, 'user_id': uid, **saved})


@app.route('/api/email/mailbox-access')
@login_required
@admin_required
def api_email_mailbox_access_list():
    from email_mailbox_persistence import list_mailbox_access
    owner_id = request.args.get('owner_user_id', type=int)
    if not owner_id:
        return jsonify({'error': 'owner_user_id required'}), 400
    rows = list_mailbox_access(owner_id, EmailMailboxAccess=EmailMailboxAccess, User=User)
    return jsonify({'ok': True, 'access': rows})


@app.route('/api/email/mailbox-access', methods=['POST'])
@login_required
@admin_required
def api_email_mailbox_access_grant():
    from email_mailbox_persistence import grant_mailbox_access
    body = request.get_json(silent=True) or {}
    owner_id = body.get('owner_user_id')
    grantee_id = body.get('grantee_user_id')
    if not owner_id or not grantee_id:
        return jsonify({'error': 'owner_user_id and grantee_user_id required'}), 400
    try:
        row = grant_mailbox_access(
            owner_id, grantee_id,
            can_send=bool(body.get('can_send')),
            granted_by_id=current_user.id,
            notes=body.get('notes') or '',
            db=db, EmailMailboxAccess=EmailMailboxAccess, User=User,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'id': row.id})


@app.route('/api/email/mailbox-access/<int:access_id>', methods=['DELETE'])
@login_required
@admin_required
def api_email_mailbox_access_revoke(access_id):
    from email_mailbox_persistence import revoke_mailbox_access
    if not revoke_mailbox_access(access_id, db=db, EmailMailboxAccess=EmailMailboxAccess):
        return jsonify({'error': 'Access grant not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/email/mailbox-transfer', methods=['POST'])
@login_required
@admin_required
def api_email_mailbox_transfer():
    from email_mailbox_persistence import transfer_mailbox
    from case_workflow import InternalMessage
    body = request.get_json(silent=True) or {}
    from_id = body.get('from_user_id')
    to_id = body.get('to_user_id')
    if not from_id or not to_id:
        return jsonify({'error': 'from_user_id and to_user_id required'}), 400
    try:
        result = transfer_mailbox(
            from_id, to_id,
            include_internal=bool(body.get('include_internal', True)),
            clear_source=bool(body.get('clear_source', False)),
            db=db, UserEmailMailbox=UserEmailMailbox, InternalMessage=InternalMessage,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, **result})


def _resolve_email_settings_user_id(requested_user_id=None):
    """Self-service or admin access for per-user email settings."""
    if requested_user_id in (None, '', 0, 'me'):
        return int(current_user.id)
    target = int(requested_user_id)
    if target == int(current_user.id):
        return target
    if current_user.role != 'Admin':
        raise PermissionError('Admin only')
    user = User.query.get(target)
    if not user:
        raise ValueError('User not found')
    return target


@app.route('/api/email/users/me/settings', methods=['GET', 'PUT'])
@login_required
def api_email_my_settings():
    return api_email_user_settings(current_user.id)


@app.route('/api/email/users/me/connection', methods=['GET', 'DELETE'])
@login_required
def api_email_my_connection():
    return api_email_user_connection(current_user.id)


@app.route('/api/email/users/<int:user_id>/settings', methods=['GET', 'PUT'])
@login_required
def api_email_user_settings(user_id):
    from user_email_connection_persistence import load_user_email_settings, save_user_email_settings
    try:
        uid = _resolve_email_settings_user_id(user_id)
    except PermissionError:
        return jsonify({'error': 'Admin only'}), 403
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    if request.method == 'GET':
        settings = load_user_email_settings(uid, UserEmailMailbox=UserEmailMailbox)
        return jsonify({'ok': True, 'user_id': uid, 'settings': settings})
    body = request.get_json(silent=True) or {}
    saved = save_user_email_settings(uid, body.get('settings') or body, db=db, UserEmailMailbox=UserEmailMailbox)
    return jsonify({'ok': True, 'user_id': uid, 'settings': saved})


@app.route('/api/email/users/<int:user_id>/connection', methods=['GET', 'DELETE'])
@login_required
def api_email_user_connection(user_id):
    from user_email_connection_persistence import (
        connection_status,
        disconnect_connection,
        ensure_user_email_connection_schema,
    )
    try:
        uid = _resolve_email_settings_user_id(user_id)
    except PermissionError:
        return jsonify({'error': 'Admin only'}), 403
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    ensure_user_email_connection_schema(db)
    if request.method == 'GET':
        return jsonify({
            'ok': True,
            'user_id': uid,
            'connection': connection_status(uid, UserEmailConnection=UserEmailConnection, User=User),
        })
    disconnect_connection(uid, db=db, UserEmailConnection=UserEmailConnection)
    write_audit(
        'Disconnected email mailbox',
        f'User #{uid} Microsoft/Outlook disconnected',
        module='email',
        category='settings',
        commit=True,
    )
    return jsonify({'ok': True, 'user_id': uid, 'disconnected': True})


@app.route('/api/email/oauth/microsoft/start')
@login_required
def api_email_oauth_microsoft_start():
    import secrets
    from microsoft_graph_mail_service import authorization_url, integration_info, is_configured
    from user_email_connection_persistence import ensure_user_email_connection_schema
    if not is_configured():
        info = integration_info()
        return jsonify({
            'error': 'Microsoft 365 is not configured on this server.',
            'setup': info,
        }), 503
    try:
        uid = _resolve_email_settings_user_id(request.args.get('user_id', type=int) or current_user.id)
    except PermissionError:
        return jsonify({'error': 'Admin only'}), 403
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    ensure_user_email_connection_schema(db)
    state = secrets.token_urlsafe(24)
    session['email_oauth_state'] = state
    session['email_oauth_user_id'] = uid
    session['email_oauth_return_to'] = (request.args.get('return_to') or '').strip() or url_for('email_page', settings=1)
    redirect_uri = request.url_root.rstrip('/') + '/api/email/oauth/microsoft/callback'
    return jsonify({
        'ok': True,
        'authorization_url': authorization_url(redirect_uri=redirect_uri, state=state),
        'user_id': uid,
    })


@app.route('/api/email/oauth/microsoft/callback')
@login_required
def api_email_oauth_microsoft_callback():
    from microsoft_graph_mail_service import exchange_code, get_user_profile, sync_inbox_messages
    from user_email_connection_persistence import upsert_connection, ensure_user_email_connection_schema
    expected_state = session.pop('email_oauth_state', None)
    user_id = session.pop('email_oauth_user_id', None)
    return_to = session.pop('email_oauth_return_to', None) or url_for('email_page', settings=1)
    if not expected_state or request.args.get('state') != expected_state:
        return redirect(return_to + ('&' if '?' in return_to else '?') + 'outlook=error&reason=state')
    if request.args.get('error'):
        reason = request.args.get('error_description') or request.args.get('error')
        return redirect(return_to + ('&' if '?' in return_to else '?') + f'outlook=error&reason={urllib.parse.quote(str(reason)[:120])}')
    code = request.args.get('code')
    if not code or not user_id:
        return redirect(return_to + ('&' if '?' in return_to else '?') + 'outlook=error&reason=missing_code')
    redirect_uri = request.url_root.rstrip('/') + '/api/email/oauth/microsoft/callback'
    try:
        ensure_user_email_connection_schema(db)
        tokens = exchange_code(code, redirect_uri=redirect_uri)
        profile = get_user_profile(tokens['access_token'])
        email = (profile.get('mail') or profile.get('userPrincipalName') or '').strip()
        display = (profile.get('displayName') or '').strip()
        upsert_connection(
            int(user_id),
            provider='microsoft',
            email_address=email,
            display_name=display,
            tokens=tokens,
            scopes=None,
            db=db,
            UserEmailConnection=UserEmailConnection,
        )
        sync_inbox_messages(
            int(user_id),
            db=db,
            UserEmailConnection=UserEmailConnection,
            UserEmailMailbox=UserEmailMailbox,
        )
        write_audit(
            'Connected Outlook mailbox',
            f'User #{user_id} connected as {email}',
            module='email',
            category='settings',
            commit=True,
        )
        return redirect(return_to + ('&' if '?' in return_to else '?') + 'outlook=connected')
    except Exception as exc:
        db.session.rollback()
        return redirect(return_to + ('&' if '?' in return_to else '?') + f'outlook=error&reason={urllib.parse.quote(str(exc)[:120])}')


@app.route('/api/email/test-connection', methods=['POST'])
@login_required
def api_email_test_connection():
    from microsoft_graph_mail_service import ensure_fresh_tokens, integration_info, is_configured, test_connection
    from user_email_connection_persistence import connection_status, ensure_user_email_connection_schema
    body = request.get_json(silent=True) or {}
    try:
        uid = _resolve_email_settings_user_id(body.get('user_id'))
    except PermissionError:
        return jsonify({'error': 'Admin only'}), 403
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    ensure_user_email_connection_schema(db)
    conn = connection_status(uid, UserEmailConnection=UserEmailConnection, User=User)
    if conn.get('connected') and conn.get('provider') == 'microsoft':
        if not is_configured():
            return jsonify({'error': 'Microsoft 365 not configured', 'setup': integration_info()}), 503
        try:
            tokens = ensure_fresh_tokens(uid, db=db, UserEmailConnection=UserEmailConnection)
            result = test_connection(tokens['access_token'])
            return jsonify({'ok': True, 'mode': 'microsoft_graph', **result})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 400
    settings = body.get('settings') or {}
    host = (settings.get('smtpHost') or '').strip()
    imap = (settings.get('imapHost') or '').strip()
    if not host and not imap:
        return jsonify({'error': 'Connect Microsoft Outlook or enter SMTP/IMAP server details.'}), 400
    return jsonify({
        'ok': True,
        'mode': 'manual',
        'message': f"Manual settings captured for {settings.get('emailAddress') or conn.get('email_address') or 'account'}.",
        'smtp': host or None,
        'imap': imap or None,
    })


@app.route('/api/email/sync', methods=['POST'])
@login_required
def api_email_sync_mailbox():
    from microsoft_graph_mail_service import sync_inbox_messages
    from user_email_connection_persistence import connection_status, ensure_user_email_connection_schema
    body = request.get_json(silent=True) or {}
    try:
        uid = _resolve_email_settings_user_id(body.get('user_id'))
    except PermissionError:
        return jsonify({'error': 'Admin only'}), 403
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    ensure_user_email_connection_schema(db)
    conn = connection_status(uid, UserEmailConnection=UserEmailConnection, User=User)
    if not conn.get('connected'):
        return jsonify({'error': 'Mailbox is not connected.'}), 400
    try:
        result = sync_inbox_messages(
            uid,
            db=db,
            UserEmailConnection=UserEmailConnection,
            UserEmailMailbox=UserEmailMailbox,
            limit=int(body.get('limit') or 40),
        )
        return jsonify({'ok': True, 'user_id': uid, **result})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


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
    from financial_security import require_financial_project_access
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
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
    from budget_persistence import save_budget_state as persist_state, get_budget_state as load_state, push_budget_contract_to_project
    from financial_security import require_financial_project_access, sanitize_budget_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    patch = body.get('data') or body.get('patch') or {}
    full_replace = bool(body.get('full_replace'))
    record, existing = load_state(BudgetProjectState, project_id)
    if full_replace:
        merged = sanitize_budget_state({}, patch)
    else:
        merged = sanitize_budget_state(existing, patch)
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
    from financial_security import require_financial_project_access
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = int(project_id)
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

def _require_linked_sub_vendor_company():
    """Block sub/vendor portal users with no resolved company."""
    try:
        from portal_sub_access import is_sub_vendor_portal_user, user_has_linked_vendor_company
        if is_sub_vendor_portal_user(current_user) and not user_has_linked_vendor_company(
            current_user, Company, db, persist_link=True,
        ):
            return jsonify({
                'error': 'No subcontractor company is linked to your account. Ask your GC administrator to assign you in Companies → Who to Contact.',
            }), 403
    except Exception:
        pass
    return None


def _sync_sub_memberships_after_pay_app_save(project_id, state):
    try:
        from portal_sub_access import sync_sub_vendor_memberships_from_pay_app_state
        sync_sub_vendor_memberships_from_pay_app_state(
            project_id, state, db, Company=Company, User=User,
        )
    except Exception:
        pass


@app.route('/api/pay-applications/state', methods=['GET'])
@login_required
def api_get_pay_app_state():
    try:
        try:
            from pay_app_persistence import ensure_pay_app_schema
            from companies_persistence import ensure_company_schema
            ensure_pay_app_schema(db.engine, db)
            ensure_company_schema(db)
        except Exception:
            pass
        blocked = _require_linked_sub_vendor_company()
        if blocked:
            return blocked
        from pay_app_persistence import get_pay_app_state as load_state, coerce_pay_app_state
        from financial_security import require_financial_project_access
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        try:
            project_id = require_financial_project_access(current_user, project_id, Project)
        except (ValueError, PermissionError) as exc:
            return jsonify({'error': str(exc)}), 403
        project_id = int(project_id)
        record, data = load_state(PayAppProjectState, project_id, db=db)
        if not record:
            return jsonify({'project_id': project_id, 'data': None, 'version': 0})
        data = coerce_pay_app_state(data)
        from financial_security import filter_pay_app_state_for_sub_vendor
        try:
            data = filter_pay_app_state_for_sub_vendor(current_user, data)
            period = (data or {}).get('currentPayAppPeriod') if isinstance(data, dict) else None
            if not period and record and record.data_json:
                try:
                    import json as _json
                    raw = _json.loads(record.data_json)
                    period = raw.get('currentPayAppPeriod')
                except Exception:
                    period = None
            if isinstance(period, dict) and isinstance(data, dict):
                data['payPeriodDisplay'] = {
                    'periodNumber': period.get('periodNumber'),
                    'periodStart': period.get('periodStart'),
                    'periodEnd': period.get('periodEnd'),
                }
            try:
                from portal_sub_access import is_sub_vendor_portal_user, ensure_sub_vendor_project_memberships
                from case_workflow import ProjectMembership
                if is_sub_vendor_portal_user(current_user):
                    ensure_sub_vendor_project_memberships(
                        current_user, db, ProjectMembership=ProjectMembership,
                    )
            except Exception:
                pass
        except Exception as exc:
            app.logger.exception('pay app state filter failed for project %s', project_id)
            return jsonify({'error': 'Could not load pay application state.', 'detail': str(exc)}), 500
        try:
            return jsonify({
                'project_id': project_id,
                'data': data,
                'version': record.version,
                'updated_at': record.updated_at.isoformat() if record.updated_at else None,
            })
        except Exception as exc:
            app.logger.exception('pay app state response failed for project %s', project_id)
            return jsonify({'error': 'Could not serialize pay application state.', 'detail': str(exc)}), 500
    except Exception as exc:
        app.logger.exception('pay app state GET failed')
        return jsonify({'error': 'Could not load pay application state.', 'detail': str(exc)}), 500


@app.route('/api/pay-applications/state', methods=['PUT'])
@login_required
def api_save_pay_app_state():
    try:
        try:
            from pay_app_persistence import ensure_pay_app_schema
            from companies_persistence import ensure_company_schema
            ensure_pay_app_schema(db.engine, db)
            ensure_company_schema(db)
        except Exception:
            pass
        blocked = _require_linked_sub_vendor_company()
        if blocked:
            return blocked
        from pay_app_persistence import (
            get_pay_app_state as load_state,
            save_pay_app_state as persist_state,
            coerce_pay_app_state,
        )
        from financial_security import require_financial_project_access, sanitize_pay_app_state, filter_pay_app_patch_for_sub_vendor
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        try:
            project_id = require_financial_project_access(current_user, project_id, Project)
        except (ValueError, PermissionError) as exc:
            return jsonify({'error': str(exc)}), 403
        record, existing = load_state(PayAppProjectState, project_id, db=db)
        existing = coerce_pay_app_state(existing)
        patch = filter_pay_app_patch_for_sub_vendor(
            current_user, body.get('data') or body.get('patch') or {}, existing,
        )
        full_replace = bool(body.get('full_replace'))
        if full_replace:
            merged = sanitize_pay_app_state(existing, patch)
        else:
            merged = sanitize_pay_app_state(existing, patch)
        alloc_errors = []
        sov_errors = []
        commitment_errors = []
        commitments = []
        try:
            from portal_sub_access import is_sub_vendor_portal_user
            from pay_app_persistence import (
                validate_sub_sov_cost_code_allocations,
                validate_sub_vendor_pay_app_save,
                validate_sub_sov_requires_commitments,
            )
            commitments = Commitment.query.filter_by(project_id=int(project_id)).all()
            if is_sub_vendor_portal_user(current_user):
                sov_errors = validate_sub_vendor_pay_app_save(
                    existing, merged, current_user, Commitment=Commitment, project_id=project_id,
                )
            else:
                alloc_errors = validate_sub_sov_cost_code_allocations(merged)
                from pay_app_persistence import prune_unregistered_sub_sov
                merged = prune_unregistered_sub_sov(merged, commitments)
                commitment_errors = validate_sub_sov_requires_commitments(merged, commitments)
        except Exception:
            pass
        if sov_errors:
            return jsonify({'error': sov_errors[0], 'sov_errors': sov_errors}), 400
        if commitment_errors:
            return jsonify({'error': commitment_errors[0], 'commitment_errors': commitment_errors}), 400
        if alloc_errors:
            return jsonify({'error': alloc_errors[0], 'allocation_errors': alloc_errors}), 400
        try:
            from portal_sub_access import is_sub_vendor_portal_user, sub_vendor_company_keys, resolve_sub_vendor_sov_keys
            if is_sub_vendor_portal_user(current_user):
                sov_keys = resolve_sub_vendor_sov_keys(current_user, existing) | resolve_sub_vendor_sov_keys(current_user, merged)
                if not sov_keys:
                    sov_keys = {str(k) for k in sub_vendor_company_keys(current_user) if k}
                for field in ('subcontractorSOV', 'subSOVStatus', 'subPayAppHistory', 'subPendingSubmissions', 'subPayAppNumbers', 'subLienWaivers', 'subLienWaiverArchive'):
                    prev = existing.get(field) if isinstance(existing.get(field), dict) else {}
                    new = merged.get(field) if isinstance(merged.get(field), dict) else {}
                    other = {k: v for k, v in prev.items() if str(k) not in sov_keys}
                    owned = {k: v for k, v in new.items() if str(k) in sov_keys}
                    merged[field] = {**other, **owned}
                for field in ('contractorSOV', 'currentPayAppPeriod', 'payAppHistory', 'previousPayApps'):
                    if field in existing:
                        merged[field] = existing[field]
        except Exception:
            pass
        try:
            from pay_app_persistence import canonicalize_sub_sov_vendor_keys
            merged = canonicalize_sub_sov_vendor_keys(merged, commitments or Commitment.query.filter_by(project_id=int(project_id)).all())
        except Exception:
            pass
        try:
            record = persist_state(PayAppProjectState, db, project_id, merged, current_user.id)
        except Exception as exc:
            app.logger.exception('pay app state save failed for project %s', project_id)
            return jsonify({'error': 'Could not save pay application state.', 'detail': str(exc)}), 500
        _sync_sub_memberships_after_pay_app_save(project_id, merged)
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
    except Exception as exc:
        app.logger.exception('pay app state PUT failed')
        return jsonify({'error': 'Could not save pay application state.', 'detail': str(exc)}), 500


@app.route('/api/pay-applications/import-local', methods=['POST'])
@login_required
def api_import_pay_app_local():
    from pay_app_persistence import save_pay_app_state as persist_state, get_pay_app_state as load_state
    from financial_security import require_financial_project_access, sanitize_pay_app_state
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    data = body.get('data')
    if not project_id or not isinstance(data, dict):
        return jsonify({'error': 'project_id and data required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    _, existing = load_state(PayAppProjectState, project_id)
    data = sanitize_pay_app_state(existing, data)
    record = persist_state(PayAppProjectState, db, int(project_id), data, current_user.id)
    _sync_sub_memberships_after_pay_app_save(project_id, data)
    return jsonify({'ok': True, 'version': record.version})


@app.route('/api/pay-applications/remove-subcontractor', methods=['POST'])
@login_required
def api_remove_subcontractor_from_project():
    """Remove a subcontractor from pay app state and void related commitments."""
    from pay_app_persistence import (
        get_pay_app_state as load_state,
        save_pay_app_state as persist_state,
        purge_subcontractor_from_pay_state,
        void_subcontractor_commitments,
        commitment_matches_vendor,
    )
    from financial_security import require_financial_project_access

    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    company_id = body.get('company_id') or body.get('companyId')
    company_name = (body.get('company_name') or body.get('companyName') or '').strip()
    force = bool(body.get('force'))

    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    if not company_id and not company_name:
        return jsonify({'error': 'company_id or company_name required'}), 400

    try:
        project_id = int(require_financial_project_access(current_user, project_id, Project))
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403

    if not company_name and company_id:
        for c in Commitment.query.filter_by(project_id=project_id).all():
            if str(c.company_id or '').strip() == str(company_id).strip():
                company_name = c.company_name or company_name
                break

    _, pay_state = load_state(PayAppProjectState, project_id)
    pay_state = pay_state or {}

    sub_hist = pay_state.get('subPayAppHistory') or {}
    hist_keys = []
    from pay_app_persistence import _find_sub_sov_keys_for_company
    for k in _find_sub_sov_keys_for_company(sub_hist, company_id, company_name):
        hist_for_sub = sub_hist.get(k) or {}
        has_pushed = any(
            isinstance(entry, dict) and entry.get('archived') is True
            for entry in hist_for_sub.values()
        )
        has_active = any(
            isinstance(entry, dict)
            and entry.get('status') in ('Approved', 'Pending Approval')
            and entry.get('archived') is not True
            for entry in hist_for_sub.values()
        )
        if has_pushed and not force:
            return jsonify({
                'error': 'Subcontractor has pay applications in Previous Sub Pay Apps. Use force=true to remove anyway.',
                'can_force': True,
            }), 400
        if has_active and not force:
            return jsonify({
                'error': 'Subcontractor has an active pay application in the tracker. Clear the tracker first or use force=true.',
                'can_force': True,
            }), 400

    matching_commitments = [
        c for c in Commitment.query.filter_by(project_id=project_id).all()
        if commitment_matches_vendor(c, company_id, company_name)
    ]
    approved_commitments = [c for c in matching_commitments if c.status not in ('Draft', 'Rejected', 'Void')]
    if approved_commitments and not force:
        return jsonify({
            'error': (
                'This subcontractor has approved commitment(s) that keep re-syncing their Schedule of Values. '
                'Use force=true to void the commitment(s) and remove them.'
            ),
            'can_force': True,
            'commitments': [{'id': c.id, 'number': c.number, 'status': c.status} for c in matching_commitments],
        }), 400

    if force and approved_commitments:
        from developer_tools import is_admin_or_developer
        if not is_admin_or_developer(current_user):
            return jsonify({'error': 'Only administrators or developers can force-remove subcontractors with approved commitments'}), 403

    voided = void_subcontractor_commitments(
        project_id, company_id, company_name,
        Commitment=Commitment, db=db, user_id=current_user.id,
        allow_approved=force,
    )

    purge_result = purge_subcontractor_from_pay_state(pay_state, company_id, company_name)
    from pay_app_persistence import prune_orphan_subcontractor_sov
    prune_result = prune_orphan_subcontractor_sov(
        pay_state,
        Commitment.query.filter_by(project_id=project_id).all(),
    )
    record = persist_state(PayAppProjectState, db, project_id, pay_state, current_user.id)

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
        'company_id': company_id,
        'company_name': company_name,
        'voided_commitments': voided,
        'purge': purge_result,
        'prune': prune_result,
        'version': record.version,
        'reconcile_result': reconcile_result,
    })


@app.route('/api/pay-applications/clear-all-subcontractors', methods=['POST'])
@login_required
def api_clear_all_subcontractors_for_project():
    """Clear all subcontractor SOV/pay-app data for one project and void sub commitments."""
    from pay_app_persistence import (
        get_pay_app_state as load_state,
        save_pay_app_state as persist_state,
        clear_all_subcontractor_pay_data,
        void_all_subcontractor_commitments,
        prune_orphan_subcontractor_sov,
    )
    from financial_security import require_financial_project_access

    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    force = bool(body.get('force', True))

    if not project_id:
        return jsonify({'error': 'project_id required'}), 400

    try:
        project_id = int(require_financial_project_access(current_user, project_id, Project))
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403

    approved_subs = [
        c for c in Commitment.query.filter_by(project_id=project_id).all()
        if c.commitment_type == 'Subcontract' and c.status not in ('Draft', 'Rejected', 'Void')
    ]
    if approved_subs and not force:
        return jsonify({
            'error': 'Project has approved subcontract commitments. Use force=true to void them and clear all subcontractor data.',
            'can_force': True,
            'commitments': [{'id': c.id, 'number': c.number, 'status': c.status} for c in approved_subs],
        }), 400
    if approved_subs and force:
        from developer_tools import is_admin_or_developer
        if not is_admin_or_developer(current_user):
            return jsonify({'error': 'Only administrators or developers can force-clear subcontractors with approved commitments'}), 403

    _, pay_state = load_state(PayAppProjectState, project_id)
    pay_state = pay_state or {}
    voided = void_all_subcontractor_commitments(
        project_id, Commitment=Commitment, db=db, user_id=current_user.id,
    ) if force else []
    cleared = clear_all_subcontractor_pay_data(pay_state)
    prune_result = prune_orphan_subcontractor_sov(pay_state, [])
    record = persist_state(PayAppProjectState, db, project_id, pay_state, current_user.id)

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
        'voided_commitments': voided,
        'cleared': cleared,
        'prune': prune_result,
        'version': record.version,
        'reconcile_result': reconcile_result,
    })


@app.route('/api/pay-applications/clear-all-subcontractors-program', methods=['POST'])
@login_required
def api_clear_all_subcontractors_program():
    """Admin/Developer: clear subcontractor SOV/pay-app data across every project."""
    from developer_tools import is_admin_or_developer
    if not is_admin_or_developer(current_user):
        return jsonify({'error': 'Admin or Developer access required'}), 403

    from pay_app_persistence import (
        get_pay_app_state as load_state,
        save_pay_app_state as persist_state,
        clear_all_subcontractor_pay_data,
        void_all_subcontractor_commitments,
        prune_orphan_subcontractor_sov,
    )

    body = request.get_json(silent=True) or {}
    force = bool(body.get('force', True))
    project_ids = body.get('project_ids')
    if project_ids:
        projects = Project.query.filter(Project.id.in_(project_ids)).all()
    else:
        projects = Project.query.all()

    results = []
    for project in projects:
        approved_subs = [
            c for c in Commitment.query.filter_by(project_id=project.id).all()
            if c.commitment_type == 'Subcontract' and c.status not in ('Draft', 'Rejected', 'Void')
        ]
        if approved_subs and not force:
            results.append({
                'project_id': project.id,
                'project_name': project.name,
                'skipped': True,
                'reason': 'approved_sub_commitments',
                'commitments': len(approved_subs),
            })
            continue

        _, pay_state = load_state(PayAppProjectState, project.id)
        pay_state = pay_state or {}
        voided = void_all_subcontractor_commitments(
            project.id, Commitment=Commitment, db=db, user_id=current_user.id,
        ) if force else []
        cleared = clear_all_subcontractor_pay_data(pay_state)
        prune_result = prune_orphan_subcontractor_sov(pay_state, [])
        record = persist_state(PayAppProjectState, db, project.id, pay_state, current_user.id)
        results.append({
            'project_id': project.id,
            'project_name': project.name,
            'voided_commitments': len(voided),
            'cleared': cleared,
            'prune': prune_result,
            'version': record.version,
        })

    db.session.commit()
    return jsonify({'ok': True, 'projects': results, 'count': len(results)})


@app.route('/api/pay-applications/workflow', methods=['POST'])
@login_required
def api_pay_app_workflow():
    from pay_app_persistence import get_pay_app_state, save_pay_app_state
    from pay_app_workflow import process_pay_app_workflow
    from financial_security import require_financial_project_access

    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = int(project_id)
    entity_type = body.get('entity_type') or 'g702'
    entity_key = body.get('entity_key') or body.get('period_number') or body.get('company_id')
    action = body.get('action')
    if not action:
        return jsonify({'error': 'action required'}), 400

    record, state = get_pay_app_state(PayAppProjectState, project_id)
    if not record:
        state = {}

    try:
        result = process_pay_app_workflow(
            project_id,
            entity_type,
            entity_key,
            action,
            current_user,
            User,
            body,
            state,
            PayAppProjectState=PayAppProjectState,
            db=db,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            BudgetProjectState=BudgetProjectState,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            Project=Project,
            SageSyncEvent=SageSyncEvent,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    try:
        from pay_app_persistence import canonicalize_sub_sov_vendor_keys
        commitments = Commitment.query.filter_by(project_id=project_id).all()
        result['state'] = canonicalize_sub_sov_vendor_keys(result.get('state') or {}, commitments)
    except Exception:
        pass

    record = save_pay_app_state(PayAppProjectState, db, project_id, result['state'], current_user.id)
    db.session.commit()
    return jsonify({
        'ok': True,
        'new_status': result.get('new_status'),
        'final_approved': result.get('final_approved'),
        'ball_in_court_role': result.get('ball_in_court_role'),
        'sage_result': result.get('sage_result'),
        'state': result.get('state'),
        'version': record.version,
    })


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
    if getattr(event, 'accounting_status', None) == 'pending_review':
        return jsonify({'error': 'Event must be accepted in ERP Queue before retrying Sage post.'}), 400
    event.status = 'queued'
    process_sage_event(event, db, Commitment=Commitment)
    return jsonify({'ok': True, 'event': sage_event_to_dict(event)})


@app.route('/api/sage/pull', methods=['POST'])
@login_required
def api_sage_pull_project():
    """Pull sub payments, owner billings, and actuals from Sage for the current project."""
    from sage_service import apply_sage_pull_to_project
    body = request.get_json(silent=True) or {}
    project_id = body.get('project_id') or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    result = apply_sage_pull_to_project(
        int(project_id),
        Project=Project,
        Commitment=Commitment,
        BudgetProjectState=BudgetProjectState,
        PayAppProjectState=PayAppProjectState,
        db=db,
        user_id=current_user.id,
        SageSyncEvent=SageSyncEvent,
        ChangeOrder=ChangeOrder,
        ChangeOrderAllocation=ChangeOrderAllocation,
        CommitmentAllocation=CommitmentAllocation,
    )
    return jsonify(result)


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
    from co_persistence import co_to_dict, is_subcontract_co, enrich_co_dict_links
    from financial_security import require_financial_project_access
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = int(project_id)
    status = request.args.get('status')
    scope = (request.args.get('scope') or '').strip().lower()
    q = ChangeOrder.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    cos = q.order_by(ChangeOrder.created_at.desc()).all()
    if scope == 'owner':
        cos = [c for c in cos if not is_subcontract_co(c)]
    elif scope == 'sub':
        cos = [c for c in cos if is_subcontract_co(c)]
    result = []
    for co in cos:
        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        revs = ChangeOrderRevision.query.filter_by(change_order_id=co.id).order_by(ChangeOrderRevision.revision.desc()).all()
        revisions = [{'revision': r.revision, 'created_at': r.created_at.isoformat() if r.created_at else None, 'notes': r.notes} for r in revs]
        item = co_to_dict(co, allocs, revisions)
        enrich_co_dict_links(item, ChangeOrder)
        result.append(item)
    return jsonify({'change_orders': result})


@app.route('/api/change-orders/<int:co_id>', methods=['GET'])
@login_required
def api_get_change_order(co_id):
    from co_persistence import co_to_dict, enrich_co_dict_links
    from financial_security import require_financial_project_access
    co = ChangeOrder.query.get_or_404(co_id)
    try:
        require_financial_project_access(current_user, co.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    revs = ChangeOrderRevision.query.filter_by(change_order_id=co.id).order_by(ChangeOrderRevision.revision.desc()).all()
    revisions = [{'revision': r.revision, 'created_at': r.created_at.isoformat() if r.created_at else None, 'notes': r.notes, 'snapshot': json.loads(r.snapshot_json) if r.snapshot_json else None} for r in revs]
    payload = co_to_dict(co, allocs, revisions)
    owner_co = None
    if payload.get('linked_owner_co_id'):
        owner_co = ChangeOrder.query.get(payload['linked_owner_co_id'])
    return jsonify(enrich_co_dict_links(payload, ChangeOrder, owner_co=owner_co))


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
    from co_persistence import (
        apply_co_fields, co_to_dict, save_allocations,
        validate_allocations, is_subcontract_co, compute_co_amount_from_allocations,
    )
    from financial_security import require_financial_project_access, assert_draft_create_status, strip_workflow_fields
    try:
        body = strip_workflow_fields(request.get_json(silent=True) or {})
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        project_id = require_financial_project_access(current_user, project_id, Project)
        description = (body.get('description') or body.get('title') or '').strip()
        if not description:
            return jsonify({'error': 'description required'}), 400
        assert_draft_create_status(body.get('status') or 'Draft', entity_label='Change order')
        status = 'Draft'
        allocations = body.get('allocations') or []
        sub_co_kind = body.get('sub_co_kind')
        contract_type = (body.get('contract_type') or 'Owner').strip()
        is_sub = contract_type in ('Subcontract', 'Subcontractor')
        if is_sub and not sub_co_kind:
            sub_co_kind = 'Contract Add'
        if status != 'Draft':
            allocations = validate_allocations(
                allocations, require_rows=True, require_amount=True, sub_co_kind=sub_co_kind,
            )
        if is_sub:
            number = generate_next_number('SCO', ChangeOrder, doc_type='sub_change_order', project_id=int(project_id))
        else:
            number = generate_next_number('CO', ChangeOrder, doc_type='change_order', project_id=int(project_id))
        co = ChangeOrder(
            project_id=int(project_id),
            number=number,
            description=description,
            status=status,
            date=_parse_change_order_date(body.get('date')),
            ball_in_court_role='Creator',
            contract_type='Subcontract' if is_sub else (contract_type or 'Owner'),
            sub_co_kind=sub_co_kind if is_sub else None,
            created_by_id=current_user.id,
        )
        apply_co_fields(co, body)
        if is_sub and not co.sub_co_kind:
            co.sub_co_kind = sub_co_kind or 'Contract Add'
        db.session.add(co)
        db.session.flush()
        if allocations:
            save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, allocations, db)
            co.amount = compute_co_amount_from_allocations(allocations, co.sub_co_kind)
            if len(allocations) == 1:
                co.cost_code = allocations[0].get('cost_code')
        sync_result = None
        budget_sync_result = None
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
    from co_persistence import (
        apply_co_fields, co_to_dict, save_allocations,
        validate_allocations, compute_co_amount_from_allocations,
    )
    from developer_tools import apply_immutable_co_fields
    from financial_security import (
        require_financial_project_access,
        assert_mutable_change_order,
        assert_co_allocation_edit_allowed,
        strip_workflow_fields,
    )
    co = ChangeOrder.query.get_or_404(co_id)
    try:
        require_financial_project_access(current_user, co.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = strip_workflow_fields(request.get_json(silent=True) or {})
    unlock = _developer_unlock_bypass()
    try:
        assert_mutable_change_order(co, developer_unlock=unlock)
        assert_co_allocation_edit_allowed(co, body, developer_unlock=unlock)
        apply_co_fields(co, body)
        if unlock:
            apply_immutable_co_fields(co, body)
            if body.get('executed_locked') is False:
                co.executed_locked = False
        if body.get('allocations') is not None:
            allocations = body['allocations']
            sub_co_kind = body.get('sub_co_kind') or getattr(co, 'sub_co_kind', None)
            if co.status != 'Draft':
                allocations = validate_allocations(
                    allocations, require_rows=True, require_amount=True, sub_co_kind=sub_co_kind,
                )
            save_allocations(ChangeOrderAllocation, 'change_order_id', co.id, allocations, db)
            if allocations:
                co.amount = compute_co_amount_from_allocations(allocations, sub_co_kind)
                if len(allocations) == 1:
                    co.cost_code = allocations[0].get('cost_code')
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({
        'ok': True,
        'change_order': co_to_dict(co, allocs),
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
    if _developer_unlock_bypass() and co.status == 'Approved':
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
    owner_cos = ChangeOrder.query.filter_by(project_id=int(project_id)).order_by(ChangeOrder.created_at.desc()).limit(200).all()
    from co_persistence import is_subcontract_co
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
                'company_id': c.company_id,
            }
            for c in commitments
        ],
        'owner_change_orders': [
            {
                'id': c.id,
                'number': c.number,
                'title': getattr(c, 'title', None) or c.description,
                'status': c.status,
                'amount': c.amount,
            }
            for c in owner_cos if not is_subcontract_co(c) and c.status in ('Approved', 'Submitted', 'Pending Owner', 'Pending Architect', 'Under Review')
        ],
    })


@app.route('/api/change-orders/<int:co_id>/workflow', methods=['POST'])
@login_required
def api_change_order_workflow(co_id):
    from co_persistence import process_change_order_workflow, co_to_dict, is_subcontract_co
    from financial_security import require_financial_project_access
    co = ChangeOrder.query.get_or_404(co_id)
    try:
        require_financial_project_access(current_user, co.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    try:
        result = process_change_order_workflow(
            co, action, current_user, User, body,
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
            generate_next_number_fn=lambda prefix, model, doc_type=None, project_id=None: generate_next_number(
                prefix, model, doc_type=doc_type, project_id=project_id or co.project_id,
            ),
            developer_unlock_bypass=_developer_unlock_bypass(),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    db.session.commit()
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    return jsonify({
        'ok': True,
        'new_status': result['new_status'],
        'final_approved': result['final_approved'],
        'ball_in_court_role': co.ball_in_court_role,
        'change_order': co_to_dict(co, allocs),
        'sync_result': result.get('sync_result'),
        'budget_sync_result': result.get('budget_sync_result'),
        'auto_sub_change_orders': result.get('auto_sub_change_orders') or [],
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
    from co_persistence import pco_to_dict, append_pco_attachment, attachment_record
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'file required'}), 400
    saved = save_uploaded_file(file, folder=f'change_orders/pco_{pco_id}')
    if not saved:
        return jsonify({'error': 'invalid file type'}), 400
    record = attachment_record(saved, file.filename, current_user.id)
    append_pco_attachment(pco, record)
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
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({
        'ok': True,
        'attachment': record,
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
    from financial_security import require_financial_project_access
    project_id = request.args.get('project_id', type=int) or get_current_project_id()
    if not project_id:
        return jsonify({'error': 'project_id required'}), 400
    try:
        project_id = require_financial_project_access(current_user, project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    project_id = int(project_id)
    status = request.args.get('status')
    scope = (request.args.get('scope') or '').strip().lower()
    q = PotentialChangeOrder.query.filter_by(project_id=int(project_id))
    if status:
        q = q.filter_by(status=status)
    pcos = q.order_by(PotentialChangeOrder.created_at.desc()).all()
    if scope == 'cpco':
        pcos = [p for p in pcos if (getattr(p, 'contract_type', None) or 'Owner') == 'Subcontract']
    elif scope == 'owner':
        pcos = [p for p in pcos if (getattr(p, 'contract_type', None) or 'Owner') != 'Subcontract']
    result = []
    for pco in pcos:
        allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
        item = pco_to_dict(pco, allocs)
        item['contract_type'] = getattr(pco, 'contract_type', None) or 'Owner'
        item['change_event_id'] = getattr(pco, 'change_event_id', None)
        item['source_rfq_id'] = getattr(pco, 'source_rfq_id', None)
        item['linked_cor_id'] = getattr(pco, 'linked_cor_id', None)
        item['linked_drawing_revision'] = getattr(pco, 'linked_drawing_revision', None)
        result.append(item)
    return jsonify({'pcos': result})


@app.route('/api/pcos/<int:pco_id>', methods=['GET'])
@login_required
def api_get_pco(pco_id):
    from co_persistence import pco_to_dict
    from financial_security import require_financial_project_access
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    try:
        require_financial_project_access(current_user, pco.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
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
            number=generate_next_number('PCO', PotentialChangeOrder, doc_type='pco'),
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
    from developer_tools import apply_immutable_pco_fields
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    body = request.get_json(silent=True) or {}
    try:
        apply_pco_fields(pco, body)
        if _developer_unlock_bypass():
            apply_immutable_pco_fields(pco, body)
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


@app.route('/api/pcos/<int:pco_id>/workflow', methods=['POST'])
@login_required
def api_pco_workflow(pco_id):
    from co_persistence import process_pco_workflow, pco_to_dict
    from financial_security import require_financial_project_access
    pco = PotentialChangeOrder.query.get_or_404(pco_id)
    try:
        require_financial_project_access(current_user, pco.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return jsonify({'error': str(exc)}), 403
    body = request.get_json(silent=True) or {}
    try:
        result = process_pco_workflow(
            pco, body.get('action'), current_user, User, body,
            SageSyncEvent=SageSyncEvent, Project=Project, db=db,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    db.session.commit()
    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    return jsonify({'ok': True, 'pco': pco_to_dict(pco, allocs), **result})


@app.route('/api/pcos/<int:pco_id>/update-status', methods=['POST'])
@login_required
def api_update_pco_status(pco_id):
    return jsonify({
        'error': 'This endpoint is disabled. Use POST /api/pcos/<id>/workflow instead.',
    }), 410


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

from change_event_routes import register_change_event_routes
register_change_event_routes(app, {
    'db': db,
    'request': request,
    'jsonify': jsonify,
    'login_required': login_required,
    'current_user': current_user,
    'get_current_project_id': get_current_project_id,
    'generate_next_number': generate_next_number,
    'ChangeEvent': ChangeEvent,
    'SubcontractorRFQ': SubcontractorRFQ,
    'RFQAllocation': RFQAllocation,
    'ChangeOrderRequest': ChangeOrderRequest,
    'CORAllocation': CORAllocation,
    'PotentialChangeOrder': PotentialChangeOrder,
    'PCOAllocation': PCOAllocation,
    'ChangeOrder': ChangeOrder,
    'ChangeOrderAllocation': ChangeOrderAllocation,
    'SageSyncEvent': SageSyncEvent,
    'Project': Project,
    'BudgetProjectState': BudgetProjectState,
    'ScheduleData': ScheduleData,
    'Commitment': Commitment,
    'PayAppProjectState': PayAppProjectState,
    'User': User,
    'user_portal_type_fn': lambda u: __import__('case_workflow').user_portal_type(u),
})

from estimate_routes import register_estimate_routes
register_estimate_routes(app, {
    'db': db,
    'request': request,
    'jsonify': jsonify,
    'login_required': login_required,
    'current_user': current_user,
    'get_current_project_id': get_current_project_id,
    'generate_next_number': generate_next_number,
    'Estimate': Estimate,
    'EstimateLine': EstimateLine,
    'BidPackage': BidPackage,
    'BidInvitation': BidInvitation,
    'BidQuoteLine': BidQuoteLine,
    'BudgetProjectState': BudgetProjectState,
    'EstimateBudgetMapping': EstimateBudgetMapping,
    'EstimateAlternate': EstimateAlternate,
    'Commitment': Commitment,
    'CommitmentAllocation': CommitmentAllocation,
    'Company': Company,
    'Drawing': Drawing,
    'DrawingMarkup': DrawingMarkup,
    'User': User,
    'Project': Project,
})

from estimate_feature_routes import register_estimate_feature_routes
register_estimate_feature_routes(app, {
    'db': db,
    'request': request,
    'jsonify': jsonify,
    'login_required': login_required,
    'current_user': current_user,
    'get_current_project_id': get_current_project_id,
    'generate_next_number': generate_next_number,
    'Estimate': Estimate,
    'EstimateLine': EstimateLine,
    'BidPackage': BidPackage,
    'BidInvitation': BidInvitation,
    'BidQuoteLine': BidQuoteLine,
    'EstimateAssembly': EstimateAssembly,
    'EstimateSnapshot': EstimateSnapshot,
    'EstimateAlternate': EstimateAlternate,
    'EstimateCostHistory': EstimateCostHistory,
    'EstimateBudgetMapping': EstimateBudgetMapping,
    'BidPackageAddendum': BidPackageAddendum,
    'BidLevelingNote': BidLevelingNote,
    'BudgetProjectState': BudgetProjectState,
    'Commitment': Commitment,
    'CommitmentAllocation': CommitmentAllocation,
    'Company': Company,
    'COI': COI,
    'Project': Project,
    'Drawing': Drawing,
    'DrawingMarkup': DrawingMarkup,
    'User': User,
})


@app.route('/api/stats')
@login_required
def api_stats():
    stats = get_dashboard_stats()
    return jsonify(stats)


@app.route('/api/health')
def api_health():
    """Public ping for tunnel / load-balancer checks."""
    return jsonify({'ok': True, 'service': 'casepm'})


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
            'RFI': RFI,
            'ChangeOrder': ChangeOrder,
            'ChangeOrderAllocation': ChangeOrderAllocation,
            'PotentialChangeOrder': PotentialChangeOrder,
            'PayAppProjectState': PayAppProjectState,
            'ScheduleData': ScheduleData,
            'BudgetProjectState': BudgetProjectState,
            'Commitment': Commitment,
            'CommitmentAllocation': CommitmentAllocation,
            'SageSyncEvent': SageSyncEvent,
            'generate_next_number_fn': lambda prefix, model, doc_type=None, project_id=None: generate_next_number(
                prefix, model, doc_type=doc_type, project_id=project_id,
            ),
            'developer_unlock_bypass': _developer_unlock_bypass,
            'get_current_project_id': get_current_project_id,
        })
        db.create_all()
        cw.ensure_workflow_schema(db.engine)
        try:
            from pay_app_persistence import ensure_pay_app_schema
            ensure_pay_app_schema(db.engine, db)
        except Exception as _pe:
            print('Pay app schema:', _pe)
        try:
            from companies_persistence import ensure_company_schema
            ensure_company_schema(db)
        except Exception as _co:
            print('Company schema:', _co)
        try:
            from co_persistence import ensure_co_schema
            ensure_co_schema(db.engine, db)
        except Exception as _ce:
            print('CO schema:', _ce)
        try:
            from change_event_persistence import ensure_change_event_schema
            ensure_change_event_schema(db.engine, db)
        except Exception as _cee:
            print('Change event schema:', _cee)
        try:
            from rfi_persistence import ensure_rfi_schema
            ensure_rfi_schema(db.engine, db)
        except Exception as _re:
            print('RFI schema:', _re)
        try:
            from submittal_persistence import ensure_submittal_schema
            ensure_submittal_schema(db.engine, db)
        except Exception as _sub:
            print('Submittal schema:', _sub)
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
            from estimate_features import ensure_estimate_schema
            ensure_estimate_schema(db.engine, db)
        except Exception as _est:
            print('Estimate schema:', _est)
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
        try:
            _bootstrap_user_schema(db)
        except Exception as _sig:
            print('User profile schema:', _sig)
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
            _bootstrap_user_schema(db)
        except Exception as exc:
            print(f'User profile schema startup warning: {exc}')

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

        try:
            from developer_tools import ensure_recovery_user
            ensure_recovery_user(db, User)
        except Exception as exc:
            print(f'⚠️  Recovery access setup skipped: {exc}')

        # Create uploads directory structure if it doesn't exist
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'coi'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'attachments'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profile_images'), exist_ok=True)

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
