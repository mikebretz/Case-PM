"""Developer unlock session flag."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_developer_unlock_session_roundtrip():
    from developer_tools import (
        UNLOCK_SESSION_KEY,
        developer_unlock_active,
        is_developer,
        set_developer_unlock_mode,
    )

    class U:
        role = 'Developer'
        email = 'dev@example.com'

    assert is_developer(U())
    # Without Flask request context, unlock reads as false
    assert developer_unlock_active(U()) is False

    from app import app

    with app.test_request_context('/'):
        from flask import session

        session[UNLOCK_SESSION_KEY] = False
        assert developer_unlock_active(U()) is False
        set_developer_unlock_mode(True)
        assert developer_unlock_active(U()) is True
        set_developer_unlock_mode(False)
        assert developer_unlock_active(U()) is False


def test_assert_mutable_submittal_with_developer_unlock():
    from financial_security import assert_mutable_submittal

    class Sub:
        status = 'No Exceptions Taken'

    try:
        assert_mutable_submittal(Sub(), developer_unlock=False)
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert_mutable_submittal(Sub(), developer_unlock=True)


if __name__ == '__main__':
    test_developer_unlock_session_roundtrip()
    test_assert_mutable_submittal_with_developer_unlock()
    print('ok')
