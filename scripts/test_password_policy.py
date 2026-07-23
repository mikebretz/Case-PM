#!/usr/bin/env python3
"""Regression tests for password_policy.validate_password."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from password_policy import validate_password  # noqa: E402


def _assert_ok(password: str, **kwargs) -> None:
    ok, msg = validate_password(password, **kwargs)
    assert ok, f"expected valid password, got: {msg!r} ({password=}, {kwargs=})"


def _assert_fail(password: str, expected_fragment: str, **kwargs) -> None:
    ok, msg = validate_password(password, **kwargs)
    assert not ok, f"expected invalid password ({password=}, {kwargs=})"
    assert expected_fragment.lower() in msg.lower(), f"unexpected message: {msg!r}"


def test_short_email_local_part_does_not_block_password() -> None:
    # m@brett.com local part is one character; must not false-positive on passwords containing "m".
    _assert_ok('!313Pmrb9891', email='m@brett.com')


def test_email_local_part_still_blocked_when_long_enough() -> None:
    _assert_fail('MyBrettPass!99', 'email', email='brett@example.com')


def test_name_check_unchanged() -> None:
    _assert_fail('WelcomeBrett!99', 'name', email='', names=('Brett',))


def main() -> int:
    test_short_email_local_part_does_not_block_password()
    test_email_local_part_still_blocked_when_long_enough()
    test_name_check_unchanged()
    print('test_password_policy: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
