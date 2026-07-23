#!/usr/bin/env python3
"""Architect / consultant portal permission tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from permissions_catalog import permissions_from_role  # noqa: E402
from case_workflow import user_has_module_access  # noqa: E402


class _User:
    def __init__(self, role: str, permissions_json: str | None = None):
        self.role = role
        self.permissions_json = permissions_json


def _architect_user():
    import json
    perms = permissions_from_role('Architect')
    return _User('Architect', json.dumps(perms))


def test_architect_cannot_access_schedule_rfq_or_bid_portal_modules() -> None:
    user = _architect_user()
    assert not user_has_module_access(user, 'schedule', 'view')
    assert not user_has_module_access(user, 'change_orders_rfq', 'view')
    assert not user_has_module_access(user, 'estimating', 'view')


def test_architect_can_access_review_and_directory_modules() -> None:
    user = _architect_user()
    assert user_has_module_access(user, 'dashboard', 'client_view')
    for module in (
        'project_directory', 'drawings', 'documents',
        'rfis', 'submittals', 'change_orders', 'photos', 'punch_list',
        'inspections', 'meeting_minutes', 'email',
    ):
        assert user_has_module_access(user, module, 'view'), module


def test_architect_template_hides_financials_flag() -> None:
    perms = permissions_from_role('Architect')
    assert perms.get('global', {}).get('hide_financials') is True
    assert perms.get('portal') == 'consultant'


def main() -> int:
    test_architect_cannot_access_schedule_rfq_or_bid_portal_modules()
    test_architect_can_access_review_and_directory_modules()
    test_architect_template_hides_financials_flag()
    print('test_architect_portal_permissions: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
