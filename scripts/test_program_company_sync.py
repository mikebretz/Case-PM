#!/usr/bin/env python3
"""Program Settings → main contractor company sync tests."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import companies_persistence as cp  # noqa: E402
import program_settings_persistence as psp  # noqa: E402


class _FakeCompany:
    _next_id = 1

    def __init__(self, name, type=None, phone=None, tax_id=None, license_number=None, details_json=None, email=None):
        self.id = _FakeCompany._next_id
        _FakeCompany._next_id += 1
        self.name = name
        self.type = type
        self.phone = phone
        self.tax_id = tax_id
        self.license_number = license_number
        self.details_json = details_json
        self.email = email
        self.primary_contact_user_id = None
        self.financial_contact_user_id = None
        self.trade = None


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._name_lower = None

    def all(self):
        return list(self._rows)

    def filter(self, expr):
        self._name_lower = getattr(getattr(expr, 'right', None), 'value', None)
        if isinstance(self._name_lower, str):
            self._name_lower = self._name_lower.lower()
        return self

    def first(self):
        if self._name_lower is None:
            return None
        for row in self._rows:
            if row.name.lower() == self._name_lower:
                return row
        return None


class _FakeCompanyModel:
    rows = []

    def __init__(self, name, type=None, phone=None, tax_id=None, license_number=None, details_json=None):
        row = _FakeCompany(name, type=type, phone=phone, tax_id=tax_id, license_number=license_number, details_json=details_json)
        for key, value in row.__dict__.items():
            setattr(self, key, value)
        _FakeCompanyModel.rows.append(self)


_FakeCompanyModel.query = _FakeQuery(_FakeCompanyModel.rows)


class _FakeSession:
    def add(self, obj):
        pass

    def commit(self):
        pass


class _FakeDB:
    def __init__(self):
        self.session = _FakeSession()


def _with_temp_settings(payload):
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, 'program_settings.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'company': payload}, fh)
    old = psp._settings_path
    psp._settings_path = lambda: path
    return path, old


def test_creates_main_contractor_from_program_settings():
    _FakeCompanyModel.rows = []
    _FakeCompanyModel.query = _FakeQuery(_FakeCompanyModel.rows)
    settings = {
        'company_name': 'Case Construction LLC',
        'tax_id': '12-3456789',
        'company_phone': '555-0100',
        'company_address': '100 Builder Way',
        'company_city': 'Portland',
        'company_state': 'OR',
        'company_zip': '97201',
        'company_website': 'https://case.example',
        'company_license': 'OR-999',
        'dba_name': 'Case PM',
    }
    path, old = _with_temp_settings(settings)
    try:
        cp.ensure_company_schema = lambda db: None
        company = cp.ensure_program_company_from_settings(_FakeDB(), _FakeCompanyModel)
        assert company is not None
        assert company.name == 'Case Construction LLC'
        assert company.type == cp.MAIN_CONTRACTOR_TYPE
        assert company.tax_id == '12-3456789'
        details = json.loads(company.details_json)
        assert details['is_program_company'] is True
        assert details['is_main_contractor'] is True
        assert '100 Builder Way' in details['billing_address']
        assert 'Portland' in details['billing_address']
        serialized = cp.serialize_company(company)
        assert serialized['is_program_company'] is True
        assert serialized['company_type'] == cp.MAIN_CONTRACTOR_TYPE
    finally:
        psp._settings_path = old
        os.remove(path)


def test_updates_existing_program_company_on_rename():
    _FakeCompanyModel.rows = []
    _FakeCompanyModel.query = _FakeQuery(_FakeCompanyModel.rows)
    existing = _FakeCompany(
        'Old Name',
        type=cp.MAIN_CONTRACTOR_TYPE,
        details_json=json.dumps({'is_program_company': True, 'status': 'Active'}),
    )
    _FakeCompanyModel.rows.append(existing)
    settings = {'company_name': 'New GC Name', 'company_phone': '555-0200'}
    path, old = _with_temp_settings(settings)
    try:
        cp.ensure_company_schema = lambda db: None
        company = cp.ensure_program_company_from_settings(_FakeDB(), _FakeCompanyModel)
        assert company.name == 'New GC Name'
        assert company.phone == '555-0200'
        assert json.loads(company.details_json)['is_program_company'] is True
    finally:
        psp._settings_path = old
        os.remove(path)


def test_sort_companies_main_first():
    main = _FakeCompany('Zeta GC', details_json=json.dumps({'is_program_company': True}))
    other = _FakeCompany('Alpha Sub')
    ordered = cp.sort_companies_main_first([other, main])
    assert ordered[0] is main


if __name__ == '__main__':
    test_creates_main_contractor_from_program_settings()
    test_updates_existing_program_company_on_rename()
    test_sort_companies_main_first()
    print('ok: program company sync tests passed')
