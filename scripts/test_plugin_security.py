"""Tests for third-party plugin security controls."""
import sys
import unittest

sys.path.insert(0, '/workspace')


class PluginSecurityTests(unittest.TestCase):
    def test_blocks_private_hosts(self):
        from plugin_security import validate_external_url
        with self.assertRaises(ValueError):
            validate_external_url('http://127.0.0.1/test')
        with self.assertRaises(ValueError):
            validate_external_url('http://localhost/admin')

    def test_allows_osrm(self):
        from plugin_security import validate_external_url
        url = validate_external_url('https://router.project-osrm.org/route/v1/driving/0,0;1,1')
        self.assertIn('router.project-osrm.org', url)

    def test_blocks_unknown_host(self):
        from plugin_security import validate_external_url
        with self.assertRaises(ValueError):
            validate_external_url('https://evil.example.com/payload')

    def test_validate_coordinates(self):
        from plugin_security import validate_coordinates
        lat, lng = validate_coordinates(28.5, -81.3)
        self.assertAlmostEqual(lat, 28.5)
        with self.assertRaises(ValueError):
            validate_coordinates(999, 0)

    def test_build_osrm_url(self):
        from plugin_security import build_osrm_url
        url = build_osrm_url(-81.3, 28.5, -82.0, 29.0)
        self.assertTrue(url.startswith('https://router.project-osrm.org/'))

    def test_csp_includes_cdn_hosts(self):
        from plugin_security import build_content_security_policy
        csp = build_content_security_policy()
        self.assertIn('cdn.jsdelivr.net', csp)
        self.assertIn("object-src 'none'", csp)
        connect_idx = csp.index('connect-src')
        connect_clause = csp[connect_idx:].split(';', 1)[0]
        self.assertIn('https://cdn.jsdelivr.net', connect_clause)

    def test_plugin_inventory(self):
        from plugin_security import plugin_inventory_payload
        payload = plugin_inventory_payload()
        ids = {p['id'] for p in payload['plugins']}
        self.assertIn('leaflet', ids)
        self.assertIn('luckysheet', ids)
        self.assertIn('tinymce', ids)

    def test_safe_notification_url(self):
        from plugin_security import safe_notification_url
        origin = 'https://app.casepm.local'
        self.assertEqual(safe_notification_url('/dashboard', origin=origin), '/dashboard')
        self.assertEqual(safe_notification_url('https://evil.com/x', origin=origin), '/')

    def test_directions_email_escapes_html(self):
        from directions_service import build_directions_email_html
        html_out = build_directions_email_html({
            'origin': {'label': '<script>alert(1)</script>'},
            'destination': {'label': 'Job & Site'},
            'distance_miles': 10,
            'duration_minutes': 15,
            'steps': [{'instruction': '<b>Turn</b>', 'name': 'Main & St', 'distance_miles': 1}],
            'links': {'google_maps': 'https://maps.google.com', 'apple_maps': 'https://maps.apple.com'},
        })
        self.assertNotIn('<script>', html_out)
        self.assertIn('&lt;script&gt;', html_out)


if __name__ == '__main__':
    unittest.main()
