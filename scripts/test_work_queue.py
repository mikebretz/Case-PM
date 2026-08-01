#!/usr/bin/env python3
"""Unit tests for unified my-work queue builder."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _User:
    def __init__(self, role: str, user_id: int = 1):
        self.role = role
        self.id = user_id
        self.permissions_json = None


def test_build_my_work_queue_smoke() -> None:
    import app as app_module
    from permissions_catalog import permissions_from_role
    from work_queue_service import build_my_work_queue

    user = _User('Project Manager')
    user.permissions_json = json.dumps(permissions_from_role('Project Manager'))
    with app_module.app.app_context():
        out = build_my_work_queue(user, limit=5)
    assert out.get('ok') is True
    assert 'items' in out
    assert isinstance(out['items'], list)


def main() -> int:
    test_build_my_work_queue_smoke()
    print('test_work_queue: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
