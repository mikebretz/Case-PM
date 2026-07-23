#!/usr/bin/env python3
"""Unit tests for internal messaging vs external email permissions."""
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class MessagingPermissionTests(unittest.TestCase):
    def setUp(self):
        from permissions_catalog import ACCESS_RANK
        self.rank = ACCESS_RANK

    def _user(self, role, permissions_json=None):
        return SimpleNamespace(
            role=role,
            is_authenticated=True,
            permissions_json=permissions_json,
        )

    def test_sub_roles_get_internal_not_external_email(self):
        from permissions_catalog import permissions_from_role

        for role in (
            'Subcontractor Accountant',
            'Subcontractor Contact',
            'Subcontractor',
            'Company User',
        ):
            with self.subTest(role=role):
                modules = permissions_from_role(role)['modules']
                self.assertGreater(
                    self.rank[modules['internal_messages']['access']],
                    self.rank['none'],
                    msg=role,
                )
                self.assertEqual(modules['email']['access'], 'none', msg=role)

    def test_staff_keeps_both_email_and_internal(self):
        from permissions_catalog import permissions_from_role

        modules = permissions_from_role('Project Manager')['modules']
        self.assertGreater(self.rank[modules['email']['access']], self.rank['none'])
        self.assertGreater(self.rank[modules['internal_messages']['access']], self.rank['none'])

    def test_legacy_email_grant_migrates_to_internal_for_sub(self):
        from permissions_catalog import ensure_messaging_modules

        legacy = {
            'version': 2,
            'portal': 'sub',
            'modules': {'email': {'access': 'edit', 'approve': 'none'}},
            'global': {},
        }
        fixed = ensure_messaging_modules(legacy, 'Subcontractor')
        self.assertEqual(fixed['modules']['email']['access'], 'none')
        self.assertEqual(fixed['modules']['internal_messages']['access'], 'edit')

    def test_access_helpers_for_subcontractor(self):
        from access_control import (
            user_can_external_email,
            user_can_internal_messages,
            user_email_internal_only,
        )

        user = self._user('Subcontractor')
        self.assertTrue(user_can_internal_messages(user))
        self.assertFalse(user_can_external_email(user))
        self.assertTrue(user_email_internal_only(user))

    def test_architect_stored_permissions_backfill_internal_messages(self):
        import json
        from permissions_catalog import merge_permissions
        from case_workflow import user_has_module_access

        stale = {
            'version': 2,
            'portal': 'consultant',
            'modules': {
                'email': {'access': 'none', 'approve': 'none'},
                'rfis': {'access': 'view', 'approve': 'approve_reject'},
            },
            'global': {'from_role': 'Architect'},
        }
        user = self._user('Architect', permissions_json=json.dumps(stale))
        merged = merge_permissions('Architect', user.permissions_json)
        self.assertEqual(merged['modules']['internal_messages']['access'], 'edit')
        self.assertTrue(user_has_module_access(user, 'internal_messages', 'entry'))

    def test_ensure_workflow_models_bound_is_idempotent(self):
        from app import app
        import case_workflow as cw

        with app.app_context():
            first = cw.InternalMessage
            cw.ensure_workflow_models_bound()
            cw.ensure_workflow_models_bound()
            self.assertIs(cw.InternalMessage, first)
            msg = cw.create_internal_message(
                1,
                folder='team',
                msg_type='message',
                subject='idempotent bind test',
            )
            self.assertIsNotNone(msg)
            cw._workflow_session().rollback()

    def test_internal_message_send_api(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            arch = User.query.filter_by(email='test@arch.com').first()
            admin = User.query.filter_by(email='admin@casepm.local').first()
            self.assertIsNotNone(arch)
            self.assertIsNotNone(admin)
            with app.test_client() as client:
                _login_client(client, arch, app)
                client.get('/email?tab=internal')
                with client.session_transaction() as sess:
                    token = sess.get('casepm_csrf_token')
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                contacts = client.get('/api/internal-messages/contacts?project_id=1')
                self.assertEqual(contacts.status_code, 200, contacts.get_json())
                sent = client.post('/api/internal-messages', json={
                    'to': ['admin@casepm.local'],
                    'subject': 'bind test',
                    'body': '<p>hello</p>',
                    'project_id': 1,
                }, headers=headers)
                self.assertEqual(sent.status_code, 200, sent.get_json())
                listed = client.get('/api/internal-messages')
                self.assertEqual(listed.status_code, 200, listed.get_json())
                rows = listed.get_json()
                self.assertIsInstance(rows, list)
                sent_rows = [r for r in rows if r.get('folder') == 'sent' and r.get('subject') == 'bind test']
                self.assertTrue(sent_rows, 'sent copy should appear in GET /api/internal-messages')
                _login_client(client, admin, app)
                inbox = client.get('/api/internal-messages')
                self.assertEqual(inbox.status_code, 200, inbox.get_json())
                inbox_rows = inbox.get_json()
                received = [r for r in inbox_rows if r.get('subject') == 'bind test' and r.get('folder') != 'sent']
                self.assertTrue(received, 'recipient should see message in inbox list')


if __name__ == '__main__':
    unittest.main()
