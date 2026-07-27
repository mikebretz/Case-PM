#!/usr/bin/env python3
"""Tests for external portal financial redaction and consultant module caps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from external_portal_security import (  # noqa: E402
    redact_dashboard_payload,
    redact_financial_fields,
    redact_portfolio_payload,
)
from permissions_catalog import permissions_from_role  # noqa: E402
from portal_sub_access import consultant_portal_module_allowed  # noqa: E402


class _User:
    def __init__(self, role: str, permissions_json: str | None = None):
        self.role = role
        self.is_authenticated = True
        self.permissions_json = permissions_json


def test_dashboard_redaction_strips_financial_blocks() -> None:
    payload = {
        'kpis': {'open_rfis': 2, 'pending_co_amount': 50000},
        'financial': {'contract_amount': 1_000_000},
        'commitments': {'approved_total': 250000},
        'open_items': {'pending_co_amount': 50000},
    }
    out = redact_dashboard_payload(payload)
    assert 'financial' not in out
    assert 'commitments' not in out
    assert out['kpis'].get('pending_co_amount') is None
    assert out.get('external_portal') is True


def test_portfolio_redaction_strips_project_financials() -> None:
    payload = {
        'projects': [{
            'id': 1,
            'name': 'Demo',
            'financial': {'contract_amount': 100},
            'change_orders': {'approved_total': 50, 'pending_count': 1},
        }],
    }
    out = redact_portfolio_payload(payload)
    assert 'financial' not in out['projects'][0]
    assert 'approved_total' not in out['projects'][0]['change_orders']


def test_change_order_list_redaction() -> None:
    payload = {'change_orders': [{'number': 'CO-1', 'amount': 12000, 'allocations': [{'amount': 12000}]}]}
    out = redact_financial_fields(payload)
    assert out['change_orders'][0]['amount'] is None
    assert out['change_orders'][0]['allocations'][0]['amount'] is None


def test_architect_cannot_access_estimating_via_consultant_cap() -> None:
    perms = permissions_from_role('Architect')
    user = _User('Architect', json.dumps(perms))
    assert not consultant_portal_module_allowed(user, 'estimating')
    assert not consultant_portal_module_allowed(user, 'change_orders_rfq')
    assert consultant_portal_module_allowed(user, 'rfis')
    assert consultant_portal_module_allowed(user, 'submittals')


def main() -> int:
    test_dashboard_redaction_strips_financial_blocks()
    test_portfolio_redaction_strips_project_financials()
    test_change_order_list_redaction()
    test_architect_cannot_access_estimating_via_consultant_cap()
    print('test_external_portal_security: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
