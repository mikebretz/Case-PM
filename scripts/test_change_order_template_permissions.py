#!/usr/bin/env python3
"""Tests for change order template upload/delete permission checks."""
from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class ChangeOrderTemplatePermissionTests(unittest.TestCase):
    def _user(self, role, permissions_json=None, email='user@example.com'):
        user = SimpleNamespace(
            id=1,
            role=role,
            email=email,
            is_authenticated=True,
            is_active=True,
            permissions_json=permissions_json,
        )
        user.get_id = lambda: str(user.id)
        return user

    def test_developer_can_manage_templates(self):
        from app import _require_change_order_template_manage

        user = self._user('Developer')
        with __import__('app').app.test_request_context():
            from flask_login import login_user

            login_user(user)
            self.assertIsNone(_require_change_order_template_manage())

    def test_admin_can_manage_templates(self):
        from app import _require_change_order_template_manage

        user = self._user('Admin')
        with __import__('app').app.test_request_context():
            from flask_login import login_user

            login_user(user)
            self.assertIsNone(_require_change_order_template_manage())

    def test_pm_with_change_orders_edit_can_manage_templates(self):
        from app import _require_change_order_template_manage
        from permissions_catalog import permissions_from_role

        user = self._user('Project Manager', permissions_json=permissions_from_role('Project Manager'))
        with __import__('app').app.test_request_context():
            from flask_login import login_user

            login_user(user)
            self.assertIsNone(_require_change_order_template_manage())

    def test_view_only_user_denied(self):
        from app import _require_change_order_template_manage
        from permissions_catalog import permissions_from_role

        perms = permissions_from_role('Architect')
        perms['modules']['change_orders'] = {'access': 'view', 'approve': 'none'}
        user = self._user('Architect', permissions_json=perms)
        with __import__('app').app.test_request_context():
            from flask_login import login_user

            login_user(user)
            denied = _require_change_order_template_manage()
            self.assertIsNotNone(denied)
            response, status = denied
            self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
