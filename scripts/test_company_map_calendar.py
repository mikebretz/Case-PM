"""Tests for company map geocoding and email calendar."""
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock

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

    def test_florida_projects_sort_first(self):
        from geocode_service import search_address_suggestions
        projects = [
            {'id': 1, 'name': 'Atlanta Job', 'city': 'Atlanta', 'state': 'GA', 'status': 'Active', 'latitude': 33.7, 'longitude': -84.4},
            {'id': 2, 'name': 'Lakeland Job', 'city': 'Lakeland', 'state': 'FL', 'status': 'Active', 'latitude': 28.0, 'longitude': -81.9},
        ]
        results = search_address_suggestions('job', projects, limit=5)
        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0]['id'], 2)

    def test_geocode_query_us_only(self):
        from geocode_service import geocode_query, _is_us_country
        self.assertTrue(_is_us_country('United States', 'US'))
        self.assertFalse(_is_us_country('Canada', 'CA'))


class EmailCalendarCatalogTests(unittest.TestCase):
    def test_meeting_minute_to_calendar_event(self):
        from email_calendar_catalog import meeting_minute_to_calendar_event, meeting_type_to_event_type
        self.assertEqual(meeting_type_to_event_type('owner'), 'owner_meeting')
        self.assertEqual(meeting_type_to_event_type('toolbox_talk'), 'toolbox_talk')
        meeting = MagicMock()
        meeting.id = 42
        meeting.project_id = 7
        meeting.meeting_date = date(2026, 8, 15)
        meeting.start_time = '10:00'
        meeting.end_time = '11:00'
        meeting.meeting_type = 'toolbox_talk'
        meeting.status = 'Scheduled'
        meeting.subject = 'Weekly toolbox'
        meeting.location = 'Job trailer'
        meeting.virtual_link = ''
        meeting.organizer = 'PM'
        meeting.attendees_json = '["crew@example.com"]'
        ev = meeting_minute_to_calendar_event(meeting, project_name='Test Project')
        self.assertIsNotNone(ev)
        self.assertEqual(ev['id'], 'mm_42')
        self.assertEqual(ev['eventType'], 'toolbox_talk')
        self.assertEqual(ev['source'], 'meeting_minutes')
        self.assertTrue(ev['readOnly'])

    def test_merge_meeting_minute_events(self):
        from email_calendar_catalog import merge_meeting_minute_events
        stored = [{'id': 'evt_1', 'title': 'Manual', 'start': '2026-08-01T09:00:00'}]
        minute = [{'id': 'mm_5', 'meetingMinuteId': 5, 'title': 'Safety', 'start': '2026-08-02T09:00:00', 'source': 'meeting_minutes'}]
        merged = merge_meeting_minute_events(stored, minute)
        self.assertEqual(len(merged), 2)
        self.assertTrue(any(e.get('id') == 'mm_5' for e in merged))


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
                res = client.get('/api/company-map/locations?geocode=0&status=current')
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertTrue(data.get('ok'))
                self.assertIn('locations', data)
                self.assertIn('mapped_count', data)

    def test_calendar_catalog_route(self):
        from app import app, User
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            user = User.query.filter_by(email='admin@casepm.local').first()
            with app.test_client() as client:
                _login_client(client, user, app)
                res = client.get('/api/email/calendar/catalog')
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertTrue(data.get('ok'))
                self.assertTrue(any(t.get('id') == 'toolbox_talk' for t in data.get('event_types', [])))
                self.assertTrue(any(t.get('id') == 'bid' for t in data.get('event_types', [])))


class DirectionsServiceTests(unittest.TestCase):
    def test_directions_orlando_to_lakeland(self):
        from directions_service import get_directions
        # Approximate Orlando to Lakeland, FL
        result = get_directions(28.5383, -81.3792, 28.0395, -81.9498)
        self.assertGreater(result['distance_miles'], 20)
        self.assertGreater(result['duration_minutes'], 20)
        self.assertIn('google_maps', result.get('links', {}))


if __name__ == '__main__':
    unittest.main()
