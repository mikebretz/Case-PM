#!/usr/bin/env python3
"""Tests for sub/vendor portal optional module access."""
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class SubVendorModuleAccessTests(unittest.TestCase):
    def _user(self, role, modules):
        import json
        perms = {
            'version': 2,
            'portal': 'sub',
            'global': {'sub_vendor_portal_only': True},
            'modules': modules,
        }
        return SimpleNamespace(
            role=role,
            is_authenticated=True,
            permissions_json=json.dumps(perms),
        )

    def test_rfis_allowed_when_granted_view(self):
        from portal_sub_access import sub_vendor_module_allowed

        user = self._user('Subcontractor Accountant', {
            'pay_applications_sub': {'access': 'entry', 'approve': 'submit'},
            'rfis': {'access': 'view', 'approve': 'none'},
            'submittals': {'access': 'none', 'approve': 'none'},
        })
        self.assertTrue(sub_vendor_module_allowed(user, 'rfis'))
        self.assertFalse(sub_vendor_module_allowed(user, 'submittals'))

    def test_core_pay_app_module_always_allowed(self):
        from portal_sub_access import sub_vendor_module_allowed

        user = self._user('Subcontractor Accountant', {
            'pay_applications_sub': {'access': 'entry', 'approve': 'submit'},
        })
        self.assertTrue(sub_vendor_module_allowed(user, 'pay_applications_sub'))


if __name__ == '__main__':
    unittest.main()
