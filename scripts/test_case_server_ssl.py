#!/usr/bin/env python3
"""Tests for Case PM server URL / SSL helpers."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CaseServerSslTests(unittest.TestCase):
    def test_access_urls_https(self):
        from case_server import access_urls

        urls = access_urls('0.0.0.0', 5000, scheme='https')
        self.assertTrue(urls['local'][0].startswith('https://'))

    def test_resolve_url_scheme_from_ssl_env(self):
        from case_server import resolve_url_scheme

        os.environ['CASEPM_SSL_CERT'] = __file__
        os.environ['CASEPM_SSL_KEY'] = __file__
        try:
            self.assertEqual(resolve_url_scheme(), 'https')
        finally:
            os.environ.pop('CASEPM_SSL_CERT', None)
            os.environ.pop('CASEPM_SSL_KEY', None)


if __name__ == '__main__':
    unittest.main()
