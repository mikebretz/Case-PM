#!/usr/bin/env python3
"""Project membership API and persistence tests."""
import sys
import unittest

sys.path.insert(0, '/workspace')


class ProjectMembershipTests(unittest.TestCase):
    def test_list_and_save_memberships_use_workflow_session(self):
        from app import app, db, User, Project
        from case_workflow import ProjectMembership
        from project_access import list_memberships_for_user, save_memberships_for_user
        from scripts.simulate_security_harness import _login_client

        with app.app_context():
            admin = User.query.filter_by(email='admin@casepm.local').first()
            project = Project.query.first()
            self.assertIsNotNone(admin)
            self.assertIsNotNone(project)

            target = User.query.filter(User.id != admin.id, User.role != 'Developer').first()
            self.assertIsNotNone(target)

            saved = save_memberships_for_user(target.id, [project.id], ProjectMembership=ProjectMembership)
            db.session.commit()
            self.assertEqual(saved, [project.id])
            rows = list_memberships_for_user(target.id, ProjectMembership=ProjectMembership)
            self.assertEqual([r['project_id'] for r in rows], [project.id])

            with app.test_client() as client:
                _login_client(client, admin, app)
                client.get('/user-management')
                with client.session_transaction() as sess:
                    token = sess.get('casepm_csrf_token')
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                rv = client.get(f'/api/users/{target.id}/project-memberships')
                self.assertEqual(rv.status_code, 200, rv.get_json())
                data = rv.get_json()
                self.assertTrue(data.get('ok'))
                rv2 = client.put(
                    f'/api/users/{target.id}/project-memberships',
                    json={'project_ids': [project.id]},
                    headers=headers,
                )
                self.assertEqual(rv2.status_code, 200, rv2.get_json())
                self.assertEqual(rv2.get_json().get('project_ids'), [project.id])


if __name__ == '__main__':
    unittest.main()
