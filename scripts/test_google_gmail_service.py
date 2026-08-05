"""Smoke tests for Google Gmail OAuth helpers (no network)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGoogleGmailService(unittest.TestCase):
    def test_integration_info_shape(self):
        from google_gmail_service import integration_info
        info = integration_info()
        self.assertIn('configured', info)
        self.assertIn('required_env', info)
        self.assertTrue(info['redirect_note'])

    def test_parse_from_header(self):
        from google_gmail_service import _parse_from
        name, addr = _parse_from('"Jane Doe" <jane@example.com>')
        self.assertEqual(addr, 'jane@example.com')
        self.assertIn('Jane', name)

    def test_gmail_message_mapping(self):
        from google_gmail_service import gmail_message_to_casepm
        msg = {
            'id': 'abc123',
            'threadId': 't1',
            'snippet': 'Hello world',
            'labelIds': ['INBOX', 'UNREAD', 'CATEGORY_PROMOTIONS'],
            'internalDate': '1700000000000',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'Sender <sender@test.com>'},
                    {'name': 'Subject', 'value': 'Test'},
                ],
            },
        }
        out = gmail_message_to_casepm(msg, user_email='me@test.com')
        self.assertEqual(out['source'], 'google_gmail')
        self.assertEqual(out['gmailId'], 'abc123')
        self.assertEqual(out['category'], 'promotions')
        self.assertTrue(out['unread'])


if __name__ == '__main__':
    unittest.main()
