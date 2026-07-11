"""Companies persistence — extended vendor/owner fields and project linking."""
from __future__ import annotations

import json

COMPANY_DETAIL_FIELDS = (
    'trade', 'dba_name', 'website', 'payment_terms', 'w9_on_file', 'prequal_status',
    'sage_ap_vendor_code', 'sage_ar_customer_code', 'union_status', 'minority_owned',
    'financial_phone', 'financial_email', 'billing_address', 'shipping_address',
    'license_expiration', 'license_status',
    'gl_carrier', 'gl_policy', 'gl_expiration',
    'wc_carrier', 'wc_policy', 'wc_expiration',
    'cois', 'notes', 'local_id',
)


def _parse_json(raw, default=None):
    if default is None:
        default = {}
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def ensure_company_schema(db):
    """Add Company columns on existing SQLite databases."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'company' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('company')}
    additions = {
        'details_json': 'TEXT',
        'primary_contact_user_id': 'INTEGER',
        'financial_contact_user_id': 'INTEGER',
        'trade': 'VARCHAR(80)',
    }
    for col, typedef in additions.items():
        if col not in existing:
            db.session.execute(text(f'ALTER TABLE company ADD COLUMN {col} {typedef}'))
    db.session.commit()


def apply_company_payload(company, body):
    """Map Companies UI JSON → Company model."""
    name = (body.get('company_name') or body.get('name') or '').strip()
    if name:
        company.name = name
    company.type = (body.get('company_type') or body.get('type') or company.type or 'Client').strip()
    company.email = (body.get('primary_email') or body.get('email') or company.email or '').strip() or None
    company.phone = (body.get('primary_phone') or body.get('phone') or company.phone or '').strip() or None
    company.tax_id = (body.get('tax_id') or company.tax_id or '').strip() or None
    company.license_number = (body.get('license_number') or company.license_number or '').strip() or None
    company.trade = (body.get('trade') or company.trade or '').strip() or None

    for field in ('primary_contact_user_id', 'financial_contact_user_id'):
        if field in body and body[field] is not None:
            try:
                setattr(company, field, int(body[field]) if body[field] else None)
            except (TypeError, ValueError):
                pass

    details = _parse_json(company.details_json, {})
    for key in COMPANY_DETAIL_FIELDS:
        if key in body:
            details[key] = body[key]
    details['status'] = body.get('status') or details.get('status') or 'Active'
    details['external_id'] = body.get('external_id') or details.get('external_id') or ''
    company.details_json = json.dumps(details)


def serialize_company(company, projects=None):
    details = _parse_json(company.details_json, {})
    return {
        'id': company.id,
        'server_id': company.id,
        'name': company.name,
        'company_name': company.name,
        'type': company.type or '',
        'company_type': company.type or '',
        'email': company.email or '',
        'phone': company.phone or '',
        'primary_email': company.email or '',
        'primary_phone': company.phone or '',
        'tax_id': company.tax_id or '',
        'license_number': company.license_number or '',
        'trade': company.trade or details.get('trade') or '',
        'primary_contact_user_id': company.primary_contact_user_id,
        'financial_contact_user_id': company.financial_contact_user_id,
        'financial_phone': details.get('financial_phone') or '',
        'financial_email': details.get('financial_email') or '',
        'external_id': details.get('external_id') or '',
        'status': details.get('status') or 'Active',
        'billing_address': details.get('billing_address') or '',
        'shipping_address': details.get('shipping_address') or '',
        'dba_name': details.get('dba_name') or '',
        'website': details.get('website') or '',
        'payment_terms': details.get('payment_terms') or '',
        'w9_on_file': bool(details.get('w9_on_file')),
        'prequal_status': details.get('prequal_status') or '',
        'sage_ap_vendor_code': details.get('sage_ap_vendor_code') or '',
        'sage_ar_customer_code': details.get('sage_ar_customer_code') or '',
        'union_status': details.get('union_status') or '',
        'minority_owned': bool(details.get('minority_owned')),
        'license_expiration': details.get('license_expiration') or '',
        'license_status': details.get('license_status') or '',
        'gl_carrier': details.get('gl_carrier') or '',
        'gl_policy': details.get('gl_policy') or '',
        'gl_expiration': details.get('gl_expiration') or '',
        'wc_carrier': details.get('wc_carrier') or '',
        'wc_policy': details.get('wc_policy') or '',
        'wc_expiration': details.get('wc_expiration') or '',
        'cois': details.get('cois') or [],
        'notes': details.get('notes') or '',
        'projects': projects or [],
    }


def projects_for_company(Project, company):
    """Projects linked by client_company_id or legacy client name match."""
    from sqlalchemy import func

    q = Project.query
    rows_by_id = q.filter_by(client_company_id=company.id).all() if hasattr(Project, 'client_company_id') else []
    by_name = q.filter(func.lower(Project.client) == (company.name or '').lower()).all()
    seen = {p.id for p in rows_by_id}
    merged = list(rows_by_id)
    for p in by_name:
        if p.id not in seen:
            merged.append(p)
    return [{'id': p.id, 'name': p.name, 'number': p.number, 'status': p.status} for p in merged]
