#!/usr/bin/env python3
"""Tests for RFI/submittal document module permissions."""
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class DocumentModuleSecurityTests(unittest.TestCase):
    def _user(self, role, modules, portal='sub'):
        import json
        return SimpleNamespace(
            role=role,
            is_authenticated=True,
            permissions_json=json.dumps({
                'version': 2,
                'portal': portal,
                'modules': modules,
            }),
        )

    def test_view_only_cannot_edit_rfi(self):
        from document_module_security import assert_rfi_edit_allowed, assert_rfi_create_allowed

        user = self._user('Subcontractor', {
            'rfis': {'access': 'view', 'approve': 'none'},
        })
        with self.assertRaises(PermissionError):
            assert_rfi_create_allowed(user)
        with self.assertRaises(PermissionError):
            assert_rfi_edit_allowed(user)

    def test_sub_cannot_edit_unassigned_submittal(self):
        from document_module_security import assert_submittal_edit_allowed

        user = self._user('Subcontractor', {
            'submittals': {'access': 'entry', 'approve': 'submit'},
        })
        submittal = SimpleNamespace(
            status='Sent to Subcontractor',
            assigned_company_id=99,
            assigned_contact_user_id=None,
            assigned_company_name='Other Co',
        )
        with self.assertRaises(PermissionError):
            assert_submittal_edit_allowed(user, submittal)

    def test_sub_can_edit_assigned_submittal(self):
        from document_module_security import assert_submittal_edit_allowed

        user = self._user('Subcontractor', {
            'submittals': {'access': 'entry', 'approve': 'submit'},
        }, portal='sub')
        user.company_id = 42
        submittal = SimpleNamespace(
            status='Sent to Subcontractor',
            assigned_company_id=42,
            assigned_contact_user_id=None,
            assigned_company_name='My Co',
        )
        assert_submittal_edit_allowed(user, submittal)

    def test_view_only_cannot_manage_submittal_log(self):
        from document_module_security import assert_submittal_log_manage_allowed

        user = self._user('Subcontractor', {
            'submittals': {'access': 'view', 'approve': 'none'},
        })
        with self.assertRaises(PermissionError):
            assert_submittal_log_manage_allowed(user)

    def test_sub_only_sees_assigned_submittals(self):
        from document_module_security import submittal_visible_to_user

        user = self._user('Subcontractor', {
            'submittals': {'access': 'entry', 'approve': 'submit'},
        }, portal='sub')
        user.company_id = 42
        assigned = SimpleNamespace(
            assigned_company_id=42,
            assigned_contact_user_id=None,
            assigned_company_name='My Co',
        )
        other = SimpleNamespace(
            assigned_company_id=99,
            assigned_contact_user_id=None,
            assigned_company_name='Other Co',
        )
        self.assertTrue(submittal_visible_to_user(assigned, user))
        self.assertFalse(submittal_visible_to_user(other, user))

    def test_sub_sees_submittal_assigned_to_contact(self):
        from document_module_security import submittal_visible_to_user

        user = self._user('Subcontractor Contact', {
            'submittals': {'access': 'entry', 'approve': 'submit'},
        }, portal='sub')
        user.id = 100
        user.company_id = None
        submittal = SimpleNamespace(
            assigned_company_id=42,
            assigned_contact_user_id=100,
            assigned_company_name='My Co',
        )
        self.assertTrue(submittal_visible_to_user(submittal, user))

    def test_staff_sees_all_submittals(self):
        from document_module_security import submittal_visible_to_user

        user = self._user('Project Manager', {
            'submittals': {'access': 'edit', 'approve': 'none'},
        }, portal='staff')
        submittal = SimpleNamespace(
            assigned_company_id=99,
            assigned_contact_user_id=None,
            assigned_company_name='Other Co',
        )
        self.assertTrue(submittal_visible_to_user(submittal, user))

    def test_assigned_sub_can_comment(self):
        from document_module_security import assert_submittal_comment_allowed

        user = self._user('Subcontractor Contact', {
            'submittals': {'access': 'view', 'approve': 'none'},
        }, portal='sub')
        user.id = 100
        user.company_id = 42
        submittal = SimpleNamespace(
            assigned_company_id=42,
            assigned_contact_user_id=100,
            assigned_company_name='My Co',
        )
        assert_submittal_comment_allowed(user, submittal)

    def test_view_only_assigned_sub_can_edit_draft(self):
        from document_module_security import assert_submittal_edit_allowed

        user = self._user('Subcontractor', {
            'submittals': {'access': 'view', 'approve': 'none'},
        }, portal='sub')
        user.company_id = 42
        submittal = SimpleNamespace(
            status='Draft',
            assigned_company_id=42,
            assigned_contact_user_id=None,
            assigned_company_name='My Co',
        )
        assert_submittal_edit_allowed(user, submittal)

    def test_view_only_sub_can_read_spec_book(self):
        from document_module_security import assert_submittal_spec_book_read_allowed

        user = self._user('Subcontractor Contact', {
            'submittals': {'access': 'view', 'approve': 'none'},
        }, portal='sub')
        assert_submittal_spec_book_read_allowed(user)

    def test_sub_workflow_allowed_from_draft(self):
        from document_module_security import assert_submittal_workflow_allowed

        user = self._user('Subcontractor Contact', {
            'submittals': {'access': 'view', 'approve': 'none'},
        }, portal='sub')
        user.id = 100
        user.company_id = 42
        submittal = SimpleNamespace(
            status='Draft',
            assigned_company_id=42,
            assigned_contact_user_id=100,
            assigned_company_name='My Co',
        )
        assert_submittal_workflow_allowed(user, submittal, 'return_from_sub')

    def test_view_only_can_comment_on_rfi(self):
        from document_module_security import assert_rfi_comment_allowed

        user = self._user('Subcontractor', {
            'rfis': {'access': 'view', 'approve': 'none'},
        }, portal='sub')
        rfi = SimpleNamespace(status='Open', project_id=1)
        assert_rfi_comment_allowed(user, rfi)

    def test_rfi_comment_persistence(self):
        from rfi_persistence import add_rfi_comment, clear_rfi_comments, delete_rfi_comment, _parse_json

        rfi = SimpleNamespace(comments_json=None, updated_at=None)
        entry = add_rfi_comment(rfi, {'body': 'Test question'}, 1, 'Alice', 'PM')
        self.assertEqual(entry['body'], 'Test question')
        comments = _parse_json(rfi.comments_json, [])
        self.assertEqual(len(comments), 1)
        delete_rfi_comment(rfi, entry['id'])
        self.assertEqual(_parse_json(rfi.comments_json, []), [])
        add_rfi_comment(rfi, {'body': 'Another'}, 1, 'Alice', 'PM')
        clear_rfi_comments(rfi)
        self.assertEqual(_parse_json(rfi.comments_json, []), [])

    def test_submittal_comment_delete(self):
        from submittal_persistence import add_submittal_comment, clear_submittal_comments, delete_submittal_comment, _parse_json

        sub = SimpleNamespace(comments_json=None, updated_at=None)
        entry = add_submittal_comment(sub, {'body': 'Note one'}, 1, 'Bob', 'PM')
        add_submittal_comment(sub, {'body': 'Note two'}, 2, 'Carol', 'Sub')
        self.assertEqual(len(_parse_json(sub.comments_json, [])), 2)
        delete_submittal_comment(sub, entry['id'])
        remaining = _parse_json(sub.comments_json, [])
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['body'], 'Note two')
        clear_submittal_comments(sub)
        self.assertEqual(_parse_json(sub.comments_json, []), [])

    def test_submittal_digital_signature_requires_profile(self):
        from submittal_persistence import append_submittal_digital_signature

        user = SimpleNamespace(id=1, full_name='Jane Sub', signature_hash=None)
        sub = SimpleNamespace(details_json='{}', updated_at=None)
        with self.assertRaises(ValueError) as ctx:
            append_submittal_digital_signature(
                sub,
                user,
                {'signature_attestation': True, 'signature_hash': 'abc'},
            )
        self.assertIn('signature', str(ctx.exception).lower())

    def test_view_only_assigned_sub_can_sign(self):
        from document_module_security import assert_submittal_signature_allowed

        user = self._user('Subcontractor', {
            'submittals': {'access': 'view', 'approve': 'none'},
        }, portal='sub')
        user.company_id = 42
        submittal = SimpleNamespace(
            assigned_company_id=42,
            assigned_contact_user_id=None,
            assigned_company_name='My Co',
        )
        assert_submittal_signature_allowed(user, submittal)

    def test_review_submission_persistence(self):
        from submittal_persistence import add_submittal_review_submission, _parse_json

        sub = SimpleNamespace(details_json='{}', updated_at=None, review_comments=None)
        entry, subs = add_submittal_review_submission(
            sub, {'body': 'Please clarify anchor spacing.'}, 2, 'Pat PM', 'Project Manager', party='Project Manager',
        )
        self.assertEqual(entry['party'], 'Project Manager')
        details = _parse_json(sub.details_json, {})
        self.assertEqual(len(details.get('reviewSubmissions') or []), 1)


if __name__ == '__main__':
    unittest.main()
