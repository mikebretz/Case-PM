"""Tests for company map geocoding and email calendar."""
import sys
import unittest

sys.path.insert(0, '/workspace')


class GeocodeServiceTests(unittest.TestCase):
    def test_project_location_dict(self):
        from geocode_service import project_location_dict
        loc = project_location_dict({
            'id': 1,
            'name': 'Lakeland Store',
            'address': '123 Main St',
            'city': 'Lakeland',
            'state': 'FL',
            'zip_code': '33801',
            'latitude': 28.04,
            'longitude': -81.95,
        })
        self.assertEqual(loc['id'], 1)
        self.assertEqual(loc['latitude'], 28.04)
        self.assertIn('Lakeland', loc['label'])

    def test_search_prioritizes_project_match(self):
        from geocode_service import search_address_suggestions
        projects = [{
            'id': 9,
            'name': 'Lakeland Store #447',
            'address': '1000 County Line Rd',
            'city': 'Lakeland',
            'state': 'FL',
            'status': 'Active',
            'latitude': 28.05,
            'longitude': -81.96,
        }]
        results = search_address_suggestions('lakeland', projects, limit=5)
        self.assertTrue(results)
        self.assertEqual(results[0]['kind'], 'project')
        self.assertEqual(results[0]['id'], 9)


class EmailCalendarApiTests(unittest.TestCase):
    def test_calendar_create_and_list(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            user = User.query.filter_by(email='admin@casepm.local').first()
            self.assertIsNotNone(user)
            with app.test_client() as client:
                token = _login_client(client, user, app)
                with client.session_transaction() as sess:
                    token = sess.get('casepm_csrf_token') or token
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                created = client.post('/api/email/calendar/events', json={
                    'event': {
                        'title': 'Owner meeting test',
                        'start': '2026-08-01T14:00:00',
                        'end': '2026-08-01T15:00:00',
                        'location': 'Lakeland Store #447',
                        'eventType': 'owner_meeting',
                        'attendees': ['owner@example.com'],
                    },
                    'send_invites': False,
                }, headers=headers)
                self.assertEqual(created.status_code, 200, created.get_json())
                listed = client.get('/api/email/calendar', headers=headers)
                self.assertEqual(listed.status_code, 200)
                events = listed.get_json().get('events') or []
                self.assertTrue(any(e.get('title') == 'Owner meeting test' for e in events))

    def test_company_map_locations_route(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            user = User.query.filter_by(email='admin@casepm.local').first()
            with app.test_client() as client:
                _login_client(client, user, app)
                res = client.get('/api/company-map/locations?geocode=0')
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertTrue(data.get('ok'))
                self.assertIn('locations', data)


if __name__ == '__main__':
    unittest.main()
