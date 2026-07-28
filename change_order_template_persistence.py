"""Change order print templates — company-specific PDF forms."""
from __future__ import annotations

import json
import os
from datetime import datetime

ALDI_TEMPLATE_SLUG = 'aldi_co'
ALDI_COMPANY_KEY = 'ALDI'


def ensure_change_order_template_schema(engine, db, ChangeOrderTemplate):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if 'change_order_template' not in tables:
        db.session.execute(text('''
            CREATE TABLE change_order_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug VARCHAR(80) NOT NULL UNIQUE,
                name VARCHAR(200) NOT NULL,
                company_key VARCHAR(120),
                description TEXT,
                template_pdf_path VARCHAR(500) NOT NULL,
                engine VARCHAR(80) NOT NULL DEFAULT 'aldi_v1',
                field_map_json TEXT,
                page_layout_json TEXT,
                is_active INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0,
                created_by_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
        '''))
        db.session.commit()
    seed_default_templates(db, ChangeOrderTemplate)


def _base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _aldi_template_pdf_path():
    return os.path.join(_base_dir(), 'static', 'templates', 'change_orders', 'aldi_co_template.pdf')


def seed_default_templates(db, ChangeOrderTemplate):
    if not os.path.isfile(_aldi_template_pdf_path()):
        return
    existing = ChangeOrderTemplate.query.filter_by(slug=ALDI_TEMPLATE_SLUG).first()
    if existing:
        return
    layout = {
        'summary_page': 0,
        'sub_pages': [1, 2, 3, 4, 5],
        'gc_material_page': 7,
        'max_subs': 5,
        'max_sub_rows_summary': 8,
    }
    tpl = ChangeOrderTemplate(
        slug=ALDI_TEMPLATE_SLUG,
        name='ALDI Change Order Form',
        company_key=ALDI_COMPANY_KEY,
        description='Official ALDI Change Order Form (CO) — summary plus subcontractor breakdown pages.',
        template_pdf_path='static/templates/change_orders/aldi_co_template.pdf',
        engine='aldi_v1',
        page_layout_json=json.dumps(layout),
        is_active=True,
        is_default=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(tpl)
    db.session.commit()


def template_to_dict(row):
    layout = {}
    field_map = {}
    try:
        layout = json.loads(row.page_layout_json) if row.page_layout_json else {}
    except (TypeError, json.JSONDecodeError):
        layout = {}
    try:
        field_map = json.loads(row.field_map_json) if row.field_map_json else {}
    except (TypeError, json.JSONDecodeError):
        field_map = {}
    return {
        'id': row.id,
        'slug': row.slug,
        'name': row.name,
        'company_key': row.company_key or '',
        'description': row.description or '',
        'template_pdf_path': row.template_pdf_path,
        'engine': row.engine or 'aldi_v1',
        'field_map': field_map,
        'page_layout': layout,
        'is_active': bool(row.is_active),
        'is_default': bool(row.is_default),
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def resolve_template_pdf_path(row, base_dir=None):
    base = base_dir or _base_dir()
    rel = (row.template_pdf_path or '').strip().lstrip('/')
    if not rel:
        raise FileNotFoundError('Template PDF path is not configured.')
    path = rel if os.path.isabs(rel) else os.path.join(base, rel)
    if not os.path.isfile(path):
        raise FileNotFoundError(f'Template PDF not found: {rel}')
    return path


def apply_template_fields(row, data):
    if 'name' in data:
        row.name = (data.get('name') or '').strip() or row.name
    if 'company_key' in data:
        row.company_key = (data.get('company_key') or '').strip() or None
    if 'description' in data:
        row.description = (data.get('description') or '').strip() or None
    if 'is_active' in data:
        row.is_active = bool(data.get('is_active'))
    if 'is_default' in data:
        row.is_default = bool(data.get('is_default'))
    if 'field_map_json' in data or 'field_map' in data:
        payload = data.get('field_map_json', data.get('field_map'))
        row.field_map_json = json.dumps(payload) if payload is not None else row.field_map_json
    if 'page_layout_json' in data or 'page_layout' in data:
        payload = data.get('page_layout_json', data.get('page_layout'))
        row.page_layout_json = json.dumps(payload) if payload is not None else row.page_layout_json
    row.updated_at = datetime.utcnow()


def set_default_template(template_id, ChangeOrderTemplate, db):
    row = ChangeOrderTemplate.query.get_or_404(template_id)
    ChangeOrderTemplate.query.filter(
        ChangeOrderTemplate.id != row.id,
        ChangeOrderTemplate.company_key == row.company_key,
    ).update({'is_default': False})
    row.is_default = True
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return row
