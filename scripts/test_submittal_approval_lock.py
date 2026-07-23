#!/usr/bin/env python3
"""Tests for submittal approval lock and markup burning."""
import json
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class SubmittalApprovalLockTests(unittest.TestCase):
    def test_approved_status_is_locked(self):
        from submittal_persistence import submittal_is_approved_locked

        sub = SimpleNamespace(
            status='No Exceptions Taken',
            details_json=json.dumps({}),
            attachments_json='[]',
        )
        self.assertTrue(submittal_is_approved_locked(sub))

    def test_draft_is_not_locked(self):
        from submittal_persistence import submittal_is_approved_locked

        sub = SimpleNamespace(status='Draft', details_json='{}', attachments_json='[]')
        self.assertFalse(submittal_is_approved_locked(sub))

    def test_architect_decision_sets_approved_locked(self):
        from submittal_persistence import submittal_workflow_action, _parse_json

        sub = SimpleNamespace(
            status='Submitted to Architect',
            ball_in_court='Architect',
            review_comments=None,
            details_json='{}',
            attachments_json='[]',
            number='100-1',
            project_id=1,
            description='Test',
        )
        user = SimpleNamespace(
            id=1,
            role='Architect',
            full_name='Alex Arch',
            signature_legal_name='Alex Arch',
            stamp_path=None,
            signature_path=None,
        )
        status, _ = submittal_workflow_action(
            sub, 'architect_decision', user, {'decision': 'No Exceptions Taken'},
        )
        self.assertEqual(status, 'No Exceptions Taken')
        details = _parse_json(sub.details_json, {})
        self.assertTrue(details.get('approvedLocked'))

    def test_mutable_submittal_blocks_approved_edit(self):
        from financial_security import assert_mutable_submittal

        sub = SimpleNamespace(status='Reviewed as Noted')
        with self.assertRaises(ValueError):
            assert_mutable_submittal(sub)


class DocumentMarkupPdfTests(unittest.TestCase):
    def test_burn_cloud_and_text_markup(self):
        from document_markup_pdf import burn_markups_onto_pdf_bytes
        import fitz

        doc = fitz.open()
        doc.new_page(width=612, height=792)
        base = doc.tobytes()
        doc.close()

        markups = [
            {
                'markup_type': 'cloud',
                'geometry': {'nx': 0.1, 'ny': 0.1, 'nw': 0.3, 'nh': 0.15},
                'style': {'color': '#ef4444', 'lineWidth': 2},
            },
            {
                'markup_type': 'text',
                'geometry': {'nx': 0.12, 'ny': 0.12},
                'style': {'color': '#38bdf8', 'fontSize': 14},
                'label': 'Review note',
            },
        ]
        out = burn_markups_onto_pdf_bytes(base, markups)
        self.assertTrue(out.startswith(b'%PDF'))
        rendered = fitz.open(stream=out, filetype='pdf')
        try:
            self.assertEqual(rendered.page_count, 1)
        finally:
            rendered.close()


if __name__ == '__main__':
    unittest.main()
