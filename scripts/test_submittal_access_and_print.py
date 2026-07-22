#!/usr/bin/env python3
"""Tests for submittal API access and print form."""
import json
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class SubmittalAccessControlTests(unittest.TestCase):
    def test_view_only_sub_can_post_comment_via_api_guard(self):
        from access_control import min_access_for_request

        self.assertEqual(
            min_access_for_request('POST', '/api/submittals/2/comments'),
            'view',
        )
        self.assertEqual(
            min_access_for_request('DELETE', '/api/submittals/2/attachments'),
            'view',
        )
        self.assertEqual(
            min_access_for_request('POST', '/api/submittals/sync'),
            'view',
        )
        self.assertEqual(
            min_access_for_request('POST', '/api/submittals/2/attachments'),
            'view',
        )
        self.assertEqual(
            min_access_for_request('POST', '/api/submittals/2/signature'),
            'view',
        )
        self.assertEqual(
            min_access_for_request('POST', '/api/submittals/2/workflow'),
            'view',
        )

    def test_other_post_still_requires_entry(self):
        from access_control import min_access_for_request

        self.assertEqual(
            min_access_for_request('POST', '/api/submittals/spec-book'),
            'entry',
        )


class SubmittalFormPdfTests(unittest.TestCase):
    def test_fill_submittal_form_pdf(self):
        from submittal_form_pdf import fill_submittal_form_pdf, build_submittal_form_field_values
        from datetime import date

        submittal = SimpleNamespace(
            number='260500-1',
            spec_section='26 05 00',
            description='PRODUCT DATA',
            date=date(2026, 5, 21),
            details_json=json.dumps({
                'sectionName': 'COMMON WORK RESULTS FOR ELECTRICAL',
                'paragraph': '1.3,A',
                'rev': '0',
                'type': 'PRODUCT DATA',
            }),
        )
        project = SimpleNamespace(name='Aldi #664 Lakeland')
        company_info = {
            'company_name': 'CASE CONTRACTING',
            'company_address': '2311 Turkey Creek Road',
            'company_city': 'Plant City',
            'company_state': 'FL',
            'company_zip': '33566',
            'company_phone': '821-754-3477',
        }
        values = build_submittal_form_field_values(submittal, project=project, company_info=company_info)
        self.assertEqual(values['Job Number#1'], 'Aldi #664 Lakeland')
        self.assertEqual(values['Spec Section Title#1'], '260500 - COMMON WORK RESULTS FOR ELECTRICAL')
        self.assertEqual(values['Submittal Title#1'], 'PRODUCT DATA')
        self.assertEqual(values['Spec Section Number#1'], '260500-1.3,A')
        self.assertEqual(values['Submittal Number#1'], '260500-1')
        self.assertEqual(values['Revision Number#1'], '0')
        self.assertEqual(values['Sent Date#1'], '5/21/2026')
        self.assertIn('CASE CONTRACTING', values['Contractor Field#1'])

        pdf = fill_submittal_form_pdf(submittal, project=project, company_info=company_info)
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_uploader_may_delete_attachment(self):
        from document_module_security import assert_submittal_attachment_delete_allowed

        user = SimpleNamespace(id=5, role='Subcontractor Contact', first_name='Bob', last_name='Sub')
        submittal = SimpleNamespace(status='Draft', assigned_company_id=42)
        att = {'uploaded_by_id': 5, 'filename': 'test.pdf'}
        assert_submittal_attachment_delete_allowed(user, submittal, att)

    def test_other_sub_cannot_delete_attachment(self):
        from document_module_security import assert_submittal_attachment_delete_allowed

        user = SimpleNamespace(
            id=6,
            role='Subcontractor Contact',
            first_name='Other',
            last_name='User',
            permissions_json=json.dumps({
                'version': 2,
                'portal': 'sub',
                'modules': {'submittals': {'access': 'view', 'approve': 'none'}},
            }),
        )
        submittal = SimpleNamespace(
            status='Draft',
            assigned_company_id=42,
            assigned_contact_user_id=6,
            assigned_company_name='My Co',
        )
        att = {'uploaded_by_id': 5, 'filename': 'test.pdf'}
        with self.assertRaises(PermissionError):
            assert_submittal_attachment_delete_allowed(user, submittal, att)


if __name__ == '__main__':
    unittest.main()
