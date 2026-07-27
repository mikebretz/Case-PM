"""Tests for MS Project MPP import via MPXJ."""
import unittest


SAMPLE_MSPDI = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Tasks>
    <Task>
      <UID>1</UID><ID>1</ID><Name>Phase 1</Name><Summary>1</Summary><OutlineLevel>1</OutlineLevel>
      <Start>2026-01-06T08:00:00</Start><Finish>2026-01-15T17:00:00</Finish><Duration>PT64H0M0S</Duration>
    </Task>
    <Task>
      <UID>2</UID><ID>2</ID><Name>Task A</Name><OutlineLevel>2</OutlineLevel>
      <Start>2026-01-06T08:00:00</Start><Finish>2026-01-08T17:00:00</Finish><Duration>PT16H0M0S</Duration>
      <PercentComplete>50</PercentComplete>
    </Task>
    <Task>
      <UID>3</UID><ID>3</ID><Name>Task B</Name><OutlineLevel>2</OutlineLevel>
      <Start>2026-01-09T08:00:00</Start><Finish>2026-01-10T17:00:00</Finish><Duration>PT16H0M0S</Duration>
      <PredecessorLink><PredecessorUID>2</PredecessorUID><Type>1</Type><LinkLag>0</LinkLag></PredecessorLink>
    </Task>
  </Tasks>
</Project>'''


class ScheduleMppImportTests(unittest.TestCase):
    def test_mpp_import_available(self):
        from schedule_mpp_import import mpp_import_status

        status = mpp_import_status()
        self.assertTrue(status['packages_ok'])
        self.assertTrue(status['available'], status)

    def test_mpp_import_status_shape(self):
        from schedule_mpp_import import mpp_import_status

        status = mpp_import_status()
        for key in ('available', 'packages_ok', 'java_ok', 'message', 'setup_hint'):
            self.assertIn(key, status)

    def test_parse_mspdi_via_mpxj(self):
        from schedule_mpp_import import parse_mpp_bytes

        payload = parse_mpp_bytes(SAMPLE_MSPDI, filename='sample.xml')
        self.assertEqual(payload['source'], 'MS Project MPP')
        self.assertEqual(len(payload['data']), 3)
        self.assertEqual(len(payload['links']), 1)

        by_name = {row['text']: row for row in payload['data']}
        self.assertEqual(by_name['Phase 1']['type'], 'project')
        self.assertEqual(by_name['Task A']['parent'], by_name['Phase 1']['id'])
        self.assertEqual(by_name['Task B']['parent'], by_name['Phase 1']['id'])
        self.assertAlmostEqual(by_name['Task A']['progress'], 0.5)
        self.assertEqual(payload['links'][0]['source'], by_name['Task A']['id'])
        self.assertEqual(payload['links'][0]['target'], by_name['Task B']['id'])

    def test_api_rejects_non_mpp_extension(self):
        import app as app_module
        from scripts.simulate_security_harness import _login_client

        with app_module.app.app_context():
            admin = app_module.User.query.filter_by(role='Admin').first()
            if not admin:
                self.skipTest('No admin user in database')
            project = app_module.Project.query.first()
            if not project:
                self.skipTest('No project in database')

            with app_module.app.test_client() as client:
                token = _login_client(client, admin, app_module.app)
                from io import BytesIO

                data = {
                    'file': (BytesIO(b'not-an-mpp'), 'schedule.xml'),
                }
                rv = client.post(
                    f'/api/schedule/import-mpp?project_id={project.id}',
                    data=data,
                    headers={'X-CSRF-Token': token},
                    content_type='multipart/form-data',
                )
                self.assertEqual(rv.status_code, 400, rv.get_json())


if __name__ == '__main__':
    unittest.main()
