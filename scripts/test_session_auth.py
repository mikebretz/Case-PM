"""Session idle timeout / login bootstrap tests."""
import time
import unittest
from unittest.mock import patch


class SessionActivityTests(unittest.TestCase):
    @patch('program_settings_persistence.load_security_settings', return_value={'session_timeout_minutes': 30})
    def test_reset_activity_after_stale_timestamp(self, _mock):
        import app as app_module
        from access_control import enforce_session_idle_timeout, SESSION_ACTIVITY_KEY, reset_session_activity
        from flask import session

        user = type('U', (), {'is_authenticated': True})()
        with app_module.app.test_request_context('/dashboard'):
            session[SESSION_ACTIVITY_KEY] = time.time() - 7200
            should_logout, _ = enforce_session_idle_timeout(user, 'dashboard')
            self.assertTrue(should_logout)

            reset_session_activity()
            should_logout, _ = enforce_session_idle_timeout(user, 'dashboard')
            self.assertFalse(should_logout)

    def test_presence_heartbeat_does_not_extend_session(self):
        import app as app_module
        from access_control import enforce_session_idle_timeout, SESSION_ACTIVITY_KEY, should_extend_session_activity
        from flask import session

        with app_module.app.test_request_context('/api/presence/heartbeat', method='POST'):
            self.assertFalse(should_extend_session_activity('api_presence_heartbeat', '/api/presence/heartbeat'))
        with app_module.app.test_request_context('/api/notifications', method='GET'):
            self.assertFalse(should_extend_session_activity(None, '/api/notifications'))

        user = type('U', (), {'is_authenticated': True})()
        stale = time.time() - 120
        with app_module.app.test_request_context('/api/presence/heartbeat', method='POST'):
            session[SESSION_ACTIVITY_KEY] = stale
            enforce_session_idle_timeout(user, 'api_presence_heartbeat')
            self.assertAlmostEqual(float(session[SESSION_ACTIVITY_KEY]), stale, delta=1)

        with app_module.app.test_request_context('/api/session/touch', method='POST'):
            session[SESSION_ACTIVITY_KEY] = stale
            enforce_session_idle_timeout(user, 'api_session_touch')
            self.assertGreater(float(session[SESSION_ACTIVITY_KEY]), stale + 10)


if __name__ == '__main__':
    unittest.main()
