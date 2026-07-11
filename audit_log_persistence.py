"""Audit / activity log persistence — schema, record, and query."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

AUDIT_MODULES = [
    ('dashboard', 'Dashboard'),
    ('projects', 'Projects'),
    ('daily_log', 'Daily Log'),
    ('rfis', 'RFIs'),
    ('change_orders', 'Change Orders'),
    ('submittals', 'Submittals'),
    ('punch_list', 'Punch List'),
    ('safety', 'Safety'),
    ('photos', 'Photos'),
    ('inspections', 'Inspections'),
    ('schedule', 'Schedule'),
    ('budget', 'Budget'),
    ('forecast', 'Forecast'),
    ('pay_applications', 'Pay Applications'),
    ('commitments', 'Commitments'),
    ('companies', 'Companies / Vendors'),
    ('users', 'User Management'),
    ('documents', 'Documents'),
    ('drawings', 'Drawings'),
    ('deliveries', 'Deliveries'),
    ('meeting_minutes', 'Meeting Minutes'),
    ('weekly_report', 'Weekly Report'),
    ('email', 'Email'),
    ('program_settings', 'Program Settings'),
    ('developer', 'Developer Console'),
    ('notifications', 'Notifications'),
    ('accounting', 'Accounting'),
    ('app', 'General'),
]

ENDPOINT_TO_MODULE = {
    'dashboard': 'dashboard',
    'projects_page': 'projects',
    'project_detail': 'projects',
    'create_project': 'projects',
    'update_project': 'projects',
    'daily_log': 'daily_log',
    'weekly_report': 'weekly_report',
    'rfis_page': 'rfis',
    'change_orders_page': 'change_orders',
    'update_change_order_status': 'change_orders',
    'submittals_page': 'submittals',
    'punch_list_page': 'punch_list',
    'safety_page': 'safety',
    'photos_page': 'photos',
    'inspections_page': 'inspections',
    'schedule_page': 'schedule',
    'budget_page': 'budget',
    'forecast_page': 'forecast',
    'pay_applications_page': 'pay_applications',
    'commitments_page': 'commitments',
    'companies_page': 'companies',
    'user_management': 'users',
    'documents_page': 'documents',
    'document_viewer_page': 'documents',
    'document_sheet_editor_page': 'documents',
    'document_word_editor_page': 'documents',
    'drawings_page': 'drawings',
    'deliveries_page': 'deliveries',
    'meeting_minutes_page': 'meeting_minutes',
    'email_page': 'email',
    'program_settings': 'program_settings',
    'developer_console': 'developer',
    'notifications': 'notifications',
    'audit_log_page': 'app',
    'audit_log': 'app',
}

AUDIT_CATEGORIES = [
    'create', 'update', 'delete', 'approve', 'reject', 'submit', 'export',
    'import', 'view', 'login', 'settings', 'sync', 'upload', 'download', 'other',
]

_schema_ready = False


def ensure_audit_log_schema(db):
    global _schema_ready
    if _schema_ready:
        return
    cols = [
        ('module', 'VARCHAR(80)'),
        ('user_name', 'VARCHAR(150)'),
        ('user_email', 'VARCHAR(120)'),
        ('project_id', 'INTEGER'),
        ('project_name', 'VARCHAR(200)'),
        ('company_id', 'INTEGER'),
        ('company_name', 'VARCHAR(200)'),
        ('change_order_id', 'INTEGER'),
        ('entity_ref', 'VARCHAR(120)'),
        ('category', 'VARCHAR(40)'),
        ('severity', 'VARCHAR(20)'),
        ('metadata_json', 'TEXT'),
        ('client_id', 'VARCHAR(80)'),
    ]
    try:
        existing = {
            row[1] for row in db.session.execute(text('PRAGMA table_info(audit_log)')).fetchall()
        }
        for col, typedef in cols:
            if col not in existing:
                db.session.execute(text(f'ALTER TABLE audit_log ADD COLUMN {col} {typedef}'))
        db.session.commit()
        _schema_ready = True
    except Exception:
        db.session.rollback()


def module_label(module_key):
    for key, label in AUDIT_MODULES:
        if key == module_key:
            return label
    return (module_key or 'General').replace('_', ' ').title()


def serialize_log(row, user=None):
    meta = {}
    if getattr(row, 'metadata_json', None):
        try:
            meta = json.loads(row.metadata_json) if row.metadata_json else {}
        except (TypeError, json.JSONDecodeError):
            meta = {}
    u = user
    if not u and getattr(row, 'user_id', None):
        try:
            from app import User
            u = User.query.get(row.user_id)
        except Exception:
            u = None
    user_name = getattr(row, 'user_name', None) or (u.full_name if u else 'System')
    user_email = getattr(row, 'user_email', None) or (getattr(u, 'email', None) if u else '')
    ts = row.timestamp
    return {
        'id': row.id,
        'module': getattr(row, 'module', None) or 'app',
        'module_label': module_label(getattr(row, 'module', None) or 'app'),
        'action': row.action or '',
        'detail': row.details or '',
        'category': getattr(row, 'category', None) or 'other',
        'severity': getattr(row, 'severity', None) or 'info',
        'user_id': row.user_id,
        'user_name': user_name,
        'user_email': user_email,
        'project_id': getattr(row, 'project_id', None),
        'project_name': getattr(row, 'project_name', None) or '',
        'company_id': getattr(row, 'company_id', None),
        'company_name': getattr(row, 'company_name', None) or '',
        'change_order_id': getattr(row, 'change_order_id', None),
        'target_type': row.target_type or '',
        'target_id': row.target_id,
        'entity_ref': getattr(row, 'entity_ref', None) or '',
        'metadata': meta,
        'client_id': getattr(row, 'client_id', None) or '',
        'timestamp': ts.isoformat() + 'Z' if ts else '',
    }


def record_audit(db, AuditLog, user, **fields):
    """Insert one audit row. `user` may be None for system events."""
    ensure_audit_log_schema(db)
    action = (fields.get('action') or 'Action').strip()[:100]
    if not action:
        action = 'Action'
    detail = fields.get('detail') or fields.get('details') or ''
    meta = fields.get('metadata')
    if meta is not None and not isinstance(meta, dict):
        meta = {}
    client_id = (fields.get('client_id') or '').strip()[:80]
    if client_id:
        existing = AuditLog.query.filter_by(client_id=client_id).first()
        if existing:
            return existing

    row = AuditLog(
        user_id=getattr(user, 'id', None) if user else fields.get('user_id'),
        action=action,
        target_type=(fields.get('target_type') or '')[:50] or None,
        target_id=fields.get('target_id'),
        details=str(detail)[:4000] if detail else None,
        timestamp=fields.get('timestamp') or datetime.utcnow(),
        module=(fields.get('module') or 'app')[:80],
        user_name=(fields.get('user_name') or (user.full_name if user else ''))[:150] or None,
        user_email=(fields.get('user_email') or (getattr(user, 'email', '') if user else ''))[:120] or None,
        project_id=fields.get('project_id'),
        project_name=(fields.get('project_name') or '')[:200] or None,
        company_id=fields.get('company_id'),
        company_name=(fields.get('company_name') or '')[:200] or None,
        change_order_id=fields.get('change_order_id'),
        entity_ref=(fields.get('entity_ref') or '')[:120] or None,
        category=(fields.get('category') or 'other')[:40],
        severity=(fields.get('severity') or 'info')[:20],
        metadata_json=json.dumps(meta or {}) if meta else None,
        client_id=client_id or None,
    )
    db.session.add(row)
    return row


def record_audit_batch(db, AuditLog, user, events):
    created = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        created.append(record_audit(db, AuditLog, user, **ev))
    return created


def _parse_date(val):
    if not val:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
        try:
            return datetime.strptime(val.replace('Z', ''), fmt.replace('Z', ''))
        except ValueError:
            continue
    return None


def query_audit_logs(AuditLog, args):
    """Query with extensive filters from request args dict."""
    q = AuditLog.query
    module = (args.get('module') or '').strip()
    if module and module != 'all':
        q = q.filter(AuditLog.module == module)

    user_id = args.get('user_id')
    if user_id:
        try:
            q = q.filter(AuditLog.user_id == int(user_id))
        except (TypeError, ValueError):
            pass

    for field in ('user_name', 'company_name', 'project_name', 'entity_ref', 'action', 'target_type'):
        val = (args.get(field) or '').strip()
        if val:
            q = q.filter(getattr(AuditLog, field).ilike(f'%{val}%'))

    for field in ('company_id', 'project_id', 'change_order_id', 'target_id'):
        val = args.get(field)
        if val not in (None, ''):
            try:
                q = q.filter(getattr(AuditLog, field) == int(val))
            except (TypeError, ValueError):
                pass

    category = (args.get('category') or '').strip()
    if category and category != 'all':
        q = q.filter(AuditLog.category == category)

    severity = (args.get('severity') or '').strip()
    if severity and severity != 'all':
        q = q.filter(AuditLog.severity == severity)

    date_from = _parse_date(args.get('date_from') or args.get('from'))
    date_to = _parse_date(args.get('date_to') or args.get('to'))
    if date_from:
        q = q.filter(AuditLog.timestamp >= date_from)
    if date_to:
        q = q.filter(AuditLog.timestamp <= date_to)

    search = (args.get('q') or args.get('search') or '').strip()
    if search:
        like = f'%{search}%'
        q = q.filter(
            db_or_ilike(AuditLog, like,
                        'action', 'details', 'user_name', 'user_email',
                        'company_name', 'project_name', 'entity_ref', 'module', 'metadata_json')
        )

    total = q.count()
    try:
        limit = min(int(args.get('limit') or 100), 500)
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = max(int(args.get('offset') or 0), 0)
    except (TypeError, ValueError):
        offset = 0

    rows = q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
    return rows, total


def db_or_ilike(model, pattern, *columns):
    from sqlalchemy import or_
    parts = []
    for col in columns:
        attr = getattr(model, col, None)
        if attr is not None:
            parts.append(attr.ilike(pattern))
    return or_(*parts) if parts else True


def audit_stats(AuditLog):
    from sqlalchemy import func
    total = AuditLog.query.count()
    by_module = (
        AuditLog.query.with_entities(AuditLog.module, func.count(AuditLog.id))
        .group_by(AuditLog.module)
        .order_by(func.count(AuditLog.id).desc())
        .limit(20)
        .all()
    )
    recent = AuditLog.query.order_by(AuditLog.timestamp.desc()).first()
    return {
        'total': total,
        'by_module': [{'module': m or 'app', 'label': module_label(m or 'app'), 'count': c} for m, c in by_module],
        'last_event_at': recent.timestamp.isoformat() + 'Z' if recent and recent.timestamp else None,
    }
