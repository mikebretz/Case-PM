#!/usr/bin/env python3
"""Tests for Case PM desktop launcher helpers."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DesktopLauncherTests(unittest.TestCase):
    def test_wait_for_server_rejects_bad_url(self):
        from desktop_launcher import wait_for_server

        self.assertFalse(wait_for_server('http://127.0.0.1:1/', timeout=0.5))

    def test_port_is_open_false_for_closed_port(self):
        from desktop_launcher import port_is_open

        self.assertFalse(port_is_open('127.0.0.1', 1))

    @patch('desktop_launcher.sys.platform', 'linux')
    def test_webview2_check_skipped_off_windows(self):
        from desktop_launcher import check_webview2_windows

        ok, message = check_webview2_windows()
        self.assertTrue(ok)
        self.assertEqual(message, '')


if __name__ == '__main__':
    unittest.main()
