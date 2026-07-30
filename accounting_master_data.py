"""Import master data into accounting from Companies (snapshot; no cascade delete)."""
from __future__ import annotations

import json
from datetime import datetime


def _vendor_code_for_company(company):
    from sage_companies_service import resolve_sage_number
    details = {}
    try:
        details = json.loads(company.details_json or '{}') if company.details_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        details = {}
    sage = resolve_sage_number(
        company.type or '',
        details.get('external_id') or '',
        details.get('sage_ap_vendor_code') or '',
        details.get('sage_ar_customer_code') or '',
        details.get('sage_number') or '',
    )
    if sage:
        return str(sage)[:30]
    return f'C{company.id}'[:30]


def list_importable_companies(db, Company, AcctVendor, AcctCustomer, ledger_id, role='vendor'):
    """Companies not yet linked on this ledger (or all with imported flag)."""
    companies = Company.query.order_by(Company.name).all()
    if role == 'customer':
        linked = {
            c.company_id for c in AcctCustomer.query.filter_by(ledger_id=ledger_id).all()
            if c.company_id
        }
    else:
        linked = {
            v.company_id for v in AcctVendor.query.filter_by(ledger_id=ledger_id).all()
            if v.company_id
        }
    out = []
    for co in companies:
        out.append({
            'id': co.id,
            'name': co.name,
            'type': co.type or '',
            'email': co.email or '',
            'phone': co.phone or '',
            'already_imported': co.id in linked,
        })
    return out


def import_vendor_from_company(db, models, ledger_id, company_id):
    Company = models.get('Company')
    AcctVendor = models['AcctVendor']
    if not Company:
        raise ValueError('Company directory not available')
    company = Company.query.get(int(company_id))
    if not company:
        raise ValueError('Company not found')
    existing = AcctVendor.query.filter_by(ledger_id=ledger_id, company_id=company.id).first()
    if existing:
        from accounting_persistence import serialize_vendor
        return existing, False
    code = _vendor_code_for_company(company)
    suffix = 0
    base_code = code
    while AcctVendor.query.filter_by(ledger_id=ledger_id, code=code).first():
        suffix += 1
        code = f'{base_code[:26]}-{suffix}'[:30]
    meta = {
        'imported_from': 'company',
        'source_company_id': company.id,
        'imported_at': datetime.utcnow().isoformat(),
        'source_name': company.name,
    }
    v = AcctVendor(
        ledger_id=ledger_id,
        code=code,
        name=company.name,
        terms='Net 30',
        email=company.email or '',
        phone=company.phone or '',
        company_id=company.id,
        details_json=json.dumps(meta),
    )
    db.session.add(v)
    db.session.flush()
    from accounting_persistence import serialize_vendor
    return v, True


def import_customer_from_company(db, models, ledger_id, company_id):
    Company = models.get('Company')
    AcctCustomer = models['AcctCustomer']
    if not Company:
        raise ValueError('Company directory not available')
    company = Company.query.get(int(company_id))
    if not company:
        raise ValueError('Company not found')
    existing = AcctCustomer.query.filter_by(ledger_id=ledger_id, company_id=company.id).first()
    if existing:
        from accounting_persistence import serialize_customer
        return existing, False
    code = _vendor_code_for_company(company)
    suffix = 0
    base_code = code
    while AcctCustomer.query.filter_by(ledger_id=ledger_id, code=code).first():
        suffix += 1
        code = f'{base_code[:26]}-{suffix}'[:30]
    meta = {
        'imported_from': 'company',
        'source_company_id': company.id,
        'imported_at': datetime.utcnow().isoformat(),
        'source_name': company.name,
    }
    c = AcctCustomer(
        ledger_id=ledger_id,
        code=code,
        name=company.name,
        terms='Net 30',
        email=company.email or '',
        company_id=company.id,
        details_json=json.dumps(meta),
    )
    db.session.add(c)
    db.session.flush()
    from accounting_persistence import serialize_customer
    return c, True


def list_importable_users(db, User, AcctPayrollEmployee, ledger_id):
    linked = {
        e.user_id for e in AcctPayrollEmployee.query.filter_by(ledger_id=ledger_id).all()
        if e.user_id
    }
    rows = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    return [{
        'id': u.id,
        'name': f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email,
        'email': u.email or '',
        'already_imported': u.id in linked,
    } for u in rows]


def import_employee_from_user(db, models, ledger_id, user_id):
    User = models.get('User')
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    if not User:
        raise ValueError('User directory not available')
    user = User.query.get(int(user_id))
    if not user:
        raise ValueError('User not found')
    existing = AcctPayrollEmployee.query.filter_by(ledger_id=ledger_id, user_id=user.id).first()
    if existing:
        from accounting_payroll import serialize_employee
        return existing, False
    num = f'U{user.id}'
    suffix = 0
    base = num
    while AcctPayrollEmployee.query.filter_by(ledger_id=ledger_id, employee_number=num).first():
        suffix += 1
        num = f'{base}-{suffix}'
    e = AcctPayrollEmployee(
        ledger_id=ledger_id,
        employee_number=num,
        first_name=user.first_name or 'Employee',
        last_name=user.last_name or str(user.id),
        pay_type='hourly',
        user_id=user.id,
        department=(getattr(user, 'job_title', None) or '')[:80],
        status='Active',
    )
    db.session.add(e)
    db.session.flush()
    from accounting_payroll import serialize_employee
    return e, True
