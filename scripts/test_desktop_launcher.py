#!/usr/bin/env python3
"""Tests for Case PM desktop launcher helpers."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DesktopLauncherTests(unittest.TestCase):
    def test_wait_for_server_rejects_bad_url(self):
        from desktop_launcher import wait_for_server

        self.assertFalse(wait_for_server('http://127.0.0.1:1/', timeout=0.5))


if __name__ == '__main__':
    unittest.main()
