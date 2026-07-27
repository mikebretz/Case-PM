"""Privilege escalation and permission tampering tests."""
import json
import time
import unittest


class UserPermissionsSecurityTests(unittest.TestCase):
    def test_viewer_users_admin_cannot_assign_admin_role(self):
        import app as app_module
        from scripts.simulate_security_harness import _login_client
        from user_permissions_persistence import save_user_permissions
        from permissions_catalog import permissions_from_role

        with app_module.app.app_context():
            User = app_module.User
            db = app_module.db
            uid = int(time.time() * 1000)
            email = f'users.admin.{uid}@casepm.test'
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    first_name='Users', last_name='Admin',
                    email=email, role='Viewer', status='Active',
                )
                user.set_password('Test!12345')
                db.session.add(user)
            perms = permissions_from_role('Viewer')
            perms['modules']['users'] = {'access': 'admin', 'approve': 'none'}
            save_user_permissions(user, perms, db)
            db.session.commit()

            with app_module.app.test_client() as client:
                token = _login_client(client, user, app_module.app)
                headers = {'X-CSRF-Token': token, 'Content-Type': 'application/json'}
                rv = client.put(
                    f'/api/users/{user.id}',
                    json={'role': 'Admin'},
                    headers=headers,
                )
                self.assertEqual(rv.status_code, 400, rv.get_json())
                db.session.refresh(user)
                self.assertEqual(user.role, 'Viewer')

    def test_permissions_payload_capped_for_non_admin(self):
        from user_permissions_persistence import sanitize_permissions_for_actor
        from permissions_catalog import permissions_from_role
        import app as app_module

        with app_module.app.app_context():
            actor = app_module.User(
                first_name='Actor', last_name='Viewer', email='actor@test.local',
                role='Viewer', status='Active',
            )
            actor_perms = permissions_from_role('Viewer')
            actor_perms['modules']['users'] = {'access': 'admin', 'approve': 'none'}
            actor.permissions_json = json.dumps(actor_perms)

            attack = permissions_from_role('Viewer')
            attack['global']['hide_financials'] = False
            attack['modules']['budget'] = {'access': 'admin', 'approve': 'approve_reject'}
            attack['modules']['program_settings'] = {'access': 'admin', 'approve': 'none'}

            capped = sanitize_permissions_for_actor(actor, attack)
            self.assertNotEqual(capped['modules']['budget']['access'], 'admin')
            self.assertLessEqual(
                {'none': 0, 'client_view': 1, 'view': 2, 'entry': 3, 'edit': 4, 'admin': 5}[
                    capped['modules']['budget']['access']
                ],
                2,
            )
            self.assertNotEqual(capped['modules'].get('program_settings', {}).get('access'), 'admin')

    def test_subcontractor_cannot_list_all_users(self):
        import app as app_module
        from scripts.simulate_security_harness import _login_client
        from scripts.simulate_financial_project import _ensure_sim_users

        with app_module.app.app_context():
            users = _ensure_sim_users(app_module.db, app_module.User)
            sub = users['sub']
            with app_module.app.test_client() as client:
                _login_client(client, sub, app_module.app)
                rv = client.get('/api/users/list')
                self.assertEqual(rv.status_code, 403, rv.get_json())


if __name__ == '__main__':
    unittest.main()
