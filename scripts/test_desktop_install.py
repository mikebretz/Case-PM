#!/usr/bin/env python3
"""Tests for Case PM desktop app installer builder."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DesktopInstallTests(unittest.TestCase):
    def test_build_installer_contains_webview2_and_icon(self):
        from desktop_install import build_desktop_app_installer

        buf = build_desktop_app_installer(server_url='http://127.0.0.1:5000', casepm_home='/opt/casepm')
        text = buf.read().decode('utf-8')
        self.assertIn('Case PM Desktop App Installer', text)
        self.assertIn('WebView2', text)
        self.assertIn('hard-hat', text)
        self.assertIn('setup.ps1', text)

    def test_powershell_config_local_mode(self):
        from desktop_install import build_desktop_setup_powershell

        ps1 = build_desktop_setup_powershell(
            server_url='http://127.0.0.1:5000',
            casepm_home=r'C:\Case-PM',
            local_mode=True,
        )
        self.assertIn('Ensure-LocalLauncher', ps1)
        self.assertIn('Case-PM', ps1)
        self.assertIn('RUN-DESKTOP.bat', ps1)

    def test_powershell_config_remote_mode(self):
        from desktop_install import build_desktop_setup_powershell, _is_local_server

        self.assertFalse(_is_local_server('https://casepm.company.com'))
        ps1 = build_desktop_setup_powershell(
            server_url='https://casepm.company.com',
            local_mode=False,
        )
        self.assertIn('Ensure-RemoteClient', ps1)
        self.assertIn('Install-WebView2', ps1)


if __name__ == '__main__':
    unittest.main()
