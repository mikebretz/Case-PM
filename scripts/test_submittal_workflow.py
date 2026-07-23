#!/usr/bin/env python3
"""Submittal workflow helpers — assignee submit from Draft."""
import json
import sys
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class SubmittalWorkflowTests(unittest.TestCase):
    def _sub_user(self):
        return SimpleNamespace(
            id=100,
            role='Subcontractor Contact',
            is_authenticated=True,
            company_id=42,
            company='My Co',
            permissions_json=json.dumps({
                'version': 2,
                'portal': 'sub',
                'modules': {'submittals': {'access': 'view', 'approve': 'none'}},
            }),
        )

    def test_return_from_draft_sets_received_date_and_status(self):
        from submittal_persistence import submittal_workflow_action

        submittal = SimpleNamespace(
            status='Draft',
            ball_in_court='Project Manager',
            assigned_company_id=42,
            assigned_contact_user_id=100,
            assigned_company_name='My Co',
            details_json='{"rev":"0"}',
            date=None,
            due_date=None,
        )
        new_status = submittal_workflow_action(
            submittal, 'return_from_sub', self._sub_user(),
            Company=None, db=None,
        )
        self.assertEqual(new_status, 'Returned from Subcontractor')
        self.assertIsNotNone(submittal.date)
        self.assertEqual(submittal.status, 'Returned from Subcontractor')

    def test_notified_date_sets_required_by_two_weeks(self):
        from submittal_persistence import _set_submittal_notified_date

        submittal = SimpleNamespace(details_json='{}', due_date=None)
        notified = datetime(2026, 7, 1).date()
        _set_submittal_notified_date(submittal, notified)
        details = json.loads(submittal.details_json)
        self.assertEqual(details['notifiedDate'], '2026-07-01')
        self.assertEqual(submittal.due_date, notified + timedelta(days=14))

    def test_submit_to_architect_records_contractor_review_stamp(self):
        from submittal_persistence import submittal_workflow_action

        submittal = SimpleNamespace(
            status='Returned from Subcontractor',
            ball_in_court='Project Manager',
            assigned_company_id=42,
            details_json='{"rev":"0"}',
        )
        pm = SimpleNamespace(
            id=7,
            role='Project Manager',
            full_name='Pat PM',
            signature_legal_name='Patricia PM',
            signature_hash='abc123',
            signature_path='uploads/signatures/user_7.png',
        )
        new_status = submittal_workflow_action(
            submittal, 'submit_to_architect', pm,
            Company=None, db=None,
        )
        self.assertEqual(new_status, 'Submitted to Architect')
        details = json.loads(submittal.details_json)
        stamp = details.get('contractorReviewStamp') or {}
        self.assertEqual(stamp.get('reviewed_by_name'), 'Patricia PM')
        self.assertEqual(stamp.get('reviewed_by_id'), 7)
        self.assertTrue(stamp.get('reviewed_at'))
        self.assertEqual(stamp.get('signature_hash'), 'abc123')


if __name__ == '__main__':
    unittest.main()
