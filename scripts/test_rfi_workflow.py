#!/usr/bin/env python3
"""Tests for Procore-style RFI workflow, fields, and private access."""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _rfi(**kwargs):
    base = dict(
        subject='Clarify footing detail',
        question='Please confirm rebar spacing at grid B-4.',
        status='Draft',
        due_date=date.today() + timedelta(days=7),
        rfi_manager_name='Pat Manager',
        rfi_manager_user_id=10,
        assignees_json='[{"user_id": 20, "name": "Alex Architect"}]',
        distribution_json='[]',
        responses_json='[]',
        is_private=0,
        created_by_id=1,
        created_at=datetime.utcnow(),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_normalize_party_list_accepts_strings_and_objects():
    from rfi_persistence import normalize_party_list, party_names

    items = normalize_party_list(['Alice', {'user_id': 5, 'name': 'Bob'}])
    assert len(items) == 2
    assert items[0]['name'] == 'Alice'
    assert items[1]['user_id'] == 5
    assert party_names(items) == ['Alice', 'Bob']


def test_validate_rfi_open_fields_requires_core_fields():
    from rfi_persistence import validate_rfi_open_fields

    ok = _rfi()
    validate_rfi_open_fields(ok)

    missing = _rfi(question='', assignees_json='[]')
    try:
        validate_rfi_open_fields(missing)
        assert False, 'expected ValueError'
    except ValueError as exc:
        assert 'Question' in str(exc)
        assert 'assignee' in str(exc).lower()


def test_workflow_submit_sets_open_and_ball_to_assignee():
    from rfi_persistence import workflow_rfi

    rfi = _rfi(status='Draft', ball_in_court_role='RFI Manager')
    workflow_rfi(rfi, 'submit')
    assert rfi.status == 'Open'
    assert rfi.ball_in_court_role == 'Assignee'
    assert rfi.ball_in_court_user_id == 20
    assert rfi.date_initiated is not None


def test_add_response_returns_ball_to_manager():
    from rfi_persistence import add_response, _parse_json

    rfi = _rfi(status='Open', ball_in_court_role='Assignee', ball_in_court_user_id=20)
    add_response(rfi, {'body': 'Use #5 at 12 inches on center.'}, 20, 'Alex Architect')
    assert rfi.status == 'Under Review'
    assert rfi.ball_in_court_role == 'RFI Manager'
    assert rfi.ball_in_court_user_id == 10
    responses = _parse_json(rfi.responses_json, [])
    assert len(responses) == 1
    assert responses[0]['is_official'] is False


def test_mark_response_official_sets_answered_status():
    from rfi_persistence import add_response, mark_response_official, _parse_json

    rfi = _rfi(status='Under Review', ball_in_court_role='RFI Manager', ball_in_court_user_id=10)
    add_response(rfi, {'body': 'First reply'}, 20, 'Alex Architect')
    responses = _parse_json(rfi.responses_json, [])
    mark_response_official(rfi, responses[0]['id'], 10)
    assert rfi.status == 'Answered'
    assert rfi.official_answer == 'First reply'
    assert rfi.ball_in_court_role == 'RFI Manager'
    responses = _parse_json(rfi.responses_json, [])
    assert responses[0]['is_official'] is True


def test_private_rfi_access_rules():
    from rfi_persistence import user_can_access_private_rfi

    rfi = _rfi(is_private=1, created_by_id=1, rfi_manager_user_id=10, assignees_json='[{"user_id": 20, "name": "Alex"}]')
    admin = SimpleNamespace(id=99, role='Admin', first_name='A', last_name='Admin')
    creator = SimpleNamespace(id=1, role='Project Manager', first_name='C', last_name='Creator')
    manager = SimpleNamespace(id=10, role='Project Manager', first_name='Pat', last_name='Manager')
    outsider = SimpleNamespace(id=77, role='Architect', first_name='Out', last_name='Side')

    assert user_can_access_private_rfi(admin, rfi, is_privileged=True)
    assert user_can_access_private_rfi(creator, rfi)
    assert user_can_access_private_rfi(manager, rfi)
    assert not user_can_access_private_rfi(outsider, rfi)


def test_compute_days_outstanding():
    from rfi_persistence import compute_days_outstanding

    started = datetime.utcnow() - timedelta(days=5)
    rfi = _rfi(status='Open', date_initiated=started, closed_at=None)
    assert compute_days_outstanding(rfi) >= 5


def main():
    test_normalize_party_list_accepts_strings_and_objects()
    test_validate_rfi_open_fields_requires_core_fields()
    test_workflow_submit_sets_open_and_ball_to_assignee()
    test_add_response_returns_ball_to_manager()
    test_mark_response_official_sets_answered_status()
    test_private_rfi_access_rules()
    test_compute_days_outstanding()
    print('test_rfi_workflow: OK')


if __name__ == '__main__':
    main()
