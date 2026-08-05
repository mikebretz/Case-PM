"""Tests for email OAuth credential resolution."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEmailOAuthCredentials(unittest.TestCase):
    def test_microsoft_from_env(self):
        with patch.dict(os.environ, {'MICROSOFT_CLIENT_ID': 'ms-id', 'MICROSOFT_CLIENT_SECRET': 'ms-sec'}, clear=False):
            from email_oauth_credentials import microsoft_client_id, microsoft_client_secret, microsoft_configured
            self.assertEqual(microsoft_client_id(), 'ms-id')
            self.assertEqual(microsoft_client_secret(), 'ms-sec')
            self.assertTrue(microsoft_configured())

    def test_google_from_program_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch('email_oauth_credentials._program_oauth', return_value={
                'google_client_id': 'g-id',
                'google_client_secret': 'g-sec',
            }):
                from email_oauth_credentials import google_client_id, google_configured
                self.assertEqual(google_client_id(), 'g-id')
                self.assertTrue(google_configured())


if __name__ == '__main__':
    unittest.main()
