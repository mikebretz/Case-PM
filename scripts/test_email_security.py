"""Unit tests for email security scanner and persistence."""
import sys
import unittest

sys.path.insert(0, '/workspace')


class EmailSecurityScannerTests(unittest.TestCase):
    def test_blocks_listed_sender(self):
        from email_security import scan_email_message
        msg = {
            'id': 'm1',
            'folder': 'inbox',
            'from': 'Spammer',
            'fromEmail': 'spam@evil.xyz',
            'subject': 'Hello',
            'body': '<p>Hi</p>',
        }
        scan = scan_email_message(msg, blocked_senders=['spam@evil.xyz'])
        self.assertEqual(scan.action, 'block')
        self.assertEqual(scan.risk_score, 100)

    def test_safe_sender_bypasses(self):
        from email_security import scan_email_message
        msg = {
            'id': 'm2',
            'folder': 'inbox',
            'from': 'DocuSign',
            'fromEmail': 'noreply@docusign.net',
            'subject': 'Please DocuSign',
            'body': '<p>Please review and sign.</p>',
        }
        scan = scan_email_message(msg, safe_senders=['noreply@docusign.net'])
        self.assertEqual(scan.action, 'allow')
        self.assertEqual(scan.risk_score, 0)

    def test_phishing_detected(self):
        from email_security import scan_email_message
        msg = {
            'id': 'm3',
            'folder': 'inbox',
            'from': 'PayPal',
            'fromEmail': 'billing@paypa1-secure.click',
            'subject': 'Verify your account immediately',
            'body': '<p>Confirm your billing: https://paypa1-secure.click/login</p>',
        }
        scan = scan_email_message(msg, user_email='user@casepm.com')
        self.assertIn(scan.action, ('warn', 'quarantine', 'block'))
        self.assertGreaterEqual(scan.risk_score, 35)
        self.assertIn(scan.category, ('phishing', 'spoofing', 'malware'))

    def test_malware_attachment_detected(self):
        from email_security import scan_email_message
        msg = {
            'id': 'm4',
            'folder': 'inbox',
            'from': 'IT',
            'fromEmail': 'it@external.tk',
            'subject': 'Invoice',
            'body': '<p>See attached</p>',
            'attachments': [{'name': 'scan.pdf.exe', 'size': '900 KB'}],
        }
        scan = scan_email_message(msg)
        self.assertGreaterEqual(scan.risk_score, 35)
        self.assertIn(scan.action, ('warn', 'quarantine', 'block'))

    def test_false_positive_override(self):
        from email_security import scan_email_message
        msg = {
            'id': 'fp1',
            'folder': 'spam',
            'from': 'Notifications',
            'fromEmail': 'notifications@casepm.com',
            'subject': 'Daily digest',
            'body': '<p>3 items need your attention</p>',
        }
        scan = scan_email_message(msg, false_positive_overrides=['fp1'])
        self.assertEqual(scan.action, 'allow')

    def test_simulation_meets_targets(self):
        from email_security import run_simulation
        result = run_simulation(count=200, junk_level='standard')
        self.assertGreaterEqual(result['threat_detection_rate'], 0.85)
        self.assertGreaterEqual(result['legitimate_pass_rate'], 0.9)


class EmailSecurityPersistenceTests(unittest.TestCase):
    def test_preferences_round_trip(self):
        from app import app, db, User, UserEmailSecurity
        from email_security_persistence import load_security_state, update_preferences, add_safe_sender, record_phishing_report
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            user = User.query.filter_by(email='admin@casepm.local').first()
            self.assertIsNotNone(user)
            state = update_preferences(user.id, {'junkLevel': 'high', 'blockRemoteImages': True}, db=db, UserEmailSecurity=UserEmailSecurity)
            self.assertEqual(state['preferences']['junkLevel'], 'high')
            state = add_safe_sender(user.id, 'trusted@example.com', db=db, UserEmailSecurity=UserEmailSecurity)
            self.assertIn('trusted@example.com', state['safe_senders'])
            state = record_phishing_report(user.id, {
                'message_id': 'x1',
                'fromEmail': 'phish@bad.xyz',
                'subject': 'test',
            }, db=db, UserEmailSecurity=UserEmailSecurity)
            self.assertIn('phish@bad.xyz', state['blocked_senders'])
            loaded = load_security_state(user.id, db=db, UserEmailSecurity=UserEmailSecurity)
            self.assertGreaterEqual(len(loaded['reports']), 1)

    def test_api_scan_route(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            user = User.query.filter_by(email='admin@casepm.local').first()
            self.assertIsNotNone(user)
            with app.test_client() as client:
                _login_client(client, user, app)
                with client.session_transaction() as sess:
                    token = sess.get('casepm_csrf_token')
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                res = client.post('/api/email/security/scan', json={
                    'messages': [{
                        'id': 'api_test_1',
                        'folder': 'inbox',
                        'from': 'Microsoft',
                        'fromEmail': 'security@micros0ft-login.xyz',
                        'subject': 'Verify your account immediately',
                        'body': '<p>Click here to verify your password</p>',
                    }],
                }, headers=headers)
                self.assertEqual(res.status_code, 200, res.get_json())
                data = res.get_json()
                self.assertTrue(data.get('ok'))
                scan = data['results']['api_test_1']
                self.assertIn(scan['action'], ('warn', 'quarantine', 'block'))


if __name__ == '__main__':
    unittest.main()
