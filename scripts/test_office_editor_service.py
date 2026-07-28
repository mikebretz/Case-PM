#!/usr/bin/env python3
"""Tests for LibreOffice Online / WOPI integration helpers."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class OfficeEditorServiceTests(unittest.TestCase):
    def test_issue_and_verify_wopi_token(self):
        from office_editor_service import issue_wopi_token, verify_wopi_token

        token = issue_wopi_token(doc_id=42, user_id=7, write=True, ttl_seconds=120)
        payload = verify_wopi_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['doc_id'], 42)
        self.assertEqual(payload['user_id'], 7)
        self.assertTrue(payload['write'])

    def test_blank_office_bytes(self):
        from office_editor_service import blank_office_bytes

        xlsx = blank_office_bytes('xlsx')
        docx = blank_office_bytes('docx')
        self.assertTrue(xlsx[:2] == b'PK')
        self.assertTrue(docx[:2] == b'PK')

    def test_editor_kind_to_ext(self):
        from office_editor_service import editor_kind_to_ext

        self.assertEqual(editor_kind_to_ext('sheet'), 'xlsx')
        self.assertEqual(editor_kind_to_ext('doc'), 'docx')

    def test_office_enabled_env(self):
        from office_editor_service import office_enabled

        old = os.environ.get('LIBREOFFICE_ONLINE_URL')
        try:
            os.environ['LIBREOFFICE_ONLINE_URL'] = 'http://localhost:9980'
            self.assertTrue(office_enabled())
            os.environ.pop('LIBREOFFICE_ONLINE_URL', None)
            self.assertFalse(office_enabled())
        finally:
            if old is None:
                os.environ.pop('LIBREOFFICE_ONLINE_URL', None)
            else:
                os.environ['LIBREOFFICE_ONLINE_URL'] = old


if __name__ == '__main__':
    unittest.main()
