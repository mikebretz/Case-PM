"""Simple Sage 300 vendor/customer directory for Companies lookup and import."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# Demo directory — used when SAGE_API_URL is not configured (same pattern as sage_service.py)
SAGE_DEMO_DIRECTORY = [
    {'code': 'SUB-0101', 'name': 'Gulf Coast Electric LLC', 'company_type': 'Subcontractor', 'trade': 'Electrical', 'phone': '(239) 555-0101', 'email': 'ap@gulfelectric.com'},
    {'code': 'SUB-0102', 'name': 'Sunshine Concrete Inc', 'company_type': 'Subcontractor', 'trade': 'Concrete', 'phone': '(239) 555-0102', 'email': 'billing@sunshineconcrete.com'},
    {'code': 'SUB-0103', 'name': 'Florida Steel Erectors', 'company_type': 'Subcontractor', 'trade': 'Structural Steel', 'phone': '(239) 555-0103', 'email': 'ap@flsteel.com'},
    {'code': 'SUB-0104', 'name': 'Coastal Plumbing & Mechanical', 'company_type': 'Subcontractor', 'trade': 'Plumbing', 'phone': '(239) 555-0104', 'email': 'invoices@coastalplumb.com'},
    {'code': 'SUB-0105', 'name': 'Premier Drywall Systems', 'company_type': 'Subcontractor', 'trade': 'Drywall', 'phone': '(239) 555-0105', 'email': 'ar@premierdrywall.com'},
    {'code': 'VEN-0201', 'name': 'BuildRight Supply Co', 'company_type': 'Supplier', 'trade': 'Materials', 'phone': '(239) 555-0201', 'email': 'orders@buildright.com'},
    {'code': 'VEN-0202', 'name': 'Equipment Rentals of SW FL', 'company_type': 'Supplier', 'trade': 'Equipment', 'phone': '(239) 555-0202', 'email': 'billing@eqrentals.com'},
    {'code': 'CUS-0301', 'name': 'Harborview Development Group', 'company_type': 'Client', 'trade': '', 'phone': '(239) 555-0301', 'email': 'projects@harborview.com'},
    {'code': 'CUS-0302', 'name': 'Palms Medical Center', 'company_type': 'Client', 'trade': '', 'phone': '(239) 555-0302', 'email': 'facilities@palmsmed.org'},
    {'code': 'CUS-0303', 'name': 'City of Cape Coral', 'company_type': 'Client', 'trade': '', 'phone': '(239) 555-0303', 'email': 'purchasing@capecoral.gov'},
]


def sage_kind_for_company_type(company_type):
    t = (company_type or '').lower()
    if 'client' in t or 'owner' in t:
        return 'customer'
    return 'vendor'


def resolve_sage_number(company_type='', external_id='', sage_ap='', sage_ar='', sage_number=''):
    """Single Sage # shown in the UI — backward compatible with older records."""
    if sage_number:
        return (sage_number or '').strip()
    if sage_kind_for_company_type(company_type) == 'customer':
        return (sage_ar or external_id or '').strip()
    return (sage_ap or external_id or '').strip()


def apply_sage_number_fields(body):
    """Map a single sage_number from the UI into stored AP/AR/external fields."""
    sage_number = (body.get('sage_number') or '').strip()
    if not sage_number:
        # Legacy fields may still be sent
        sage_number = resolve_sage_number(
            body.get('company_type') or body.get('type') or '',
            body.get('external_id') or '',
            body.get('sage_ap_vendor_code') or '',
            body.get('sage_ar_customer_code') or '',
        )
    company_type = body.get('company_type') or body.get('type') or 'Subcontractor'
    body['sage_number'] = sage_number
    body['external_id'] = sage_number
    if sage_kind_for_company_type(company_type) == 'customer':
        body['sage_ar_customer_code'] = sage_number
        body['sage_ap_vendor_code'] = ''
    else:
        body['sage_ap_vendor_code'] = sage_number
        body['sage_ar_customer_code'] = ''
    return body


def _normalize_entry(code, name, company_type='Subcontractor', trade='', phone='', email='', source='demo'):
    code = (code or '').strip()
    name = (name or '').strip()
    if not code or not name:
        return None
    return {
        'code': code,
        'sage_number': code,
        'external_id': code,
        'company_name': name,
        'name': name,
        'company_type': company_type or 'Subcontractor',
        'trade': trade or '',
        'primary_phone': phone or '',
        'primary_email': email or '',
        'source': source,
    }


def _entries_from_db(Company):
    rows = Company.query.order_by(Company.name.asc()).all()
    out = []
    for c in rows:
        details = {}
        if c.details_json:
            try:
                details = json.loads(c.details_json)
            except (TypeError, json.JSONDecodeError):
                details = {}
        code = resolve_sage_number(
            c.type or '',
            details.get('external_id') or '',
            details.get('sage_ap_vendor_code') or '',
            details.get('sage_ar_customer_code') or '',
            details.get('sage_number') or '',
        )
        if not code:
            continue
        entry = _normalize_entry(
            code,
            c.name,
            c.type or 'Subcontractor',
            c.trade or details.get('trade') or '',
            c.phone or '',
            c.email or '',
            source='casepm',
        )
        if entry:
            out.append(entry)
    return out


def _try_live_lookup(code, kind='vendor'):
    api_url = os.environ.get('SAGE_API_URL', '').strip()
    api_key = os.environ.get('SAGE_API_KEY', '').strip()
    if not api_url or not code:
        return None
    path = 'customers' if kind == 'customer' else 'vendors'
    url = f"{api_url.rstrip('/')}/api/v1/{path}/{urllib.parse.quote(code)}"
    try:
        req = urllib.request.Request(
            url,
            headers={'Authorization': f'Bearer {api_key}' if api_key else '', 'Accept': 'application/json'},
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode('utf-8') or '{}')
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None

    name = body.get('name') or body.get('company_name') or body.get('vendor_name') or ''
    company_type = 'Client' if kind == 'customer' else body.get('company_type') or 'Subcontractor'
    return _normalize_entry(
        body.get('code') or body.get('vendor_code') or code,
        name,
        company_type,
        body.get('trade') or '',
        body.get('phone') or '',
        body.get('email') or '',
        source='sage_live',
    )


def lookup_sage_company(code, company_type='', Company=None):
    """Look up one Sage vendor/customer # — live API first, then local directory."""
    code = (code or '').strip()
    if not code:
        return None

    kind = sage_kind_for_company_type(company_type)
    live = _try_live_lookup(code, kind)
    if live:
        return live

    code_l = code.lower()
    for item in SAGE_DEMO_DIRECTORY:
        if item['code'].lower() == code_l:
            return _normalize_entry(**item, source='sage_demo')

    if Company is not None:
        for entry in _entries_from_db(Company):
            if entry['code'].lower() == code_l:
                return entry

    return None


def list_sage_companies(search='', company_type='', Company=None):
    """List Sage vendors/customers for import — demo + CasePM records."""
    q = (search or '').strip().lower()
    want_kind = sage_kind_for_company_type(company_type) if company_type else ''

    merged = {}
    for item in SAGE_DEMO_DIRECTORY:
        entry = _normalize_entry(**item, source='sage_demo')
        if entry:
            merged[entry['code'].lower()] = entry

    if Company is not None:
        for entry in _entries_from_db(Company):
            merged[entry['code'].lower()] = entry

    rows = list(merged.values())
    if want_kind == 'customer':
        rows = [r for r in rows if sage_kind_for_company_type(r['company_type']) == 'customer']
    elif want_kind == 'vendor':
        rows = [r for r in rows if sage_kind_for_company_type(r['company_type']) == 'vendor']

    if q:
        rows = [
            r for r in rows
            if q in r['code'].lower() or q in r['company_name'].lower() or q in (r.get('trade') or '').lower()
        ]

    rows.sort(key=lambda r: r['company_name'].lower())
    return rows
