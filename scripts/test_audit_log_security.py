"""Audit log tamper resistance."""
import unittest


class AuditLogSecurityTests(unittest.TestCase):
    def test_sanitize_strips_forged_identity_fields(self):
        from audit_log_persistence import sanitize_client_audit_fields

        raw = {
            'action': 'LOGIN_OK',
            'detail': 'test',
            'timestamp': '2000-01-01T00:00:00Z',
            'user_id': 999,
            'user_name': 'Attacker',
            'user_email': 'evil@example.com',
        }
        cleaned = sanitize_client_audit_fields(raw)
        self.assertEqual(cleaned.get('action'), 'LOGIN_OK')
        self.assertNotIn('timestamp', cleaned)
        self.assertNotIn('user_id', cleaned)
        self.assertNotIn('user_name', cleaned)
        self.assertNotIn('user_email', cleaned)


if __name__ == '__main__':
    unittest.main()
