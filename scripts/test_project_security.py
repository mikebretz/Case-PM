"""Project scope and upload security helpers."""
import unittest


class ProjectSecurityTests(unittest.TestCase):
    def test_safe_relative_redirect_url_blocks_external(self):
        from project_security import safe_relative_redirect_url

        default = '/email?tab=internal'
        self.assertEqual(safe_relative_redirect_url('https://evil.example/phish', default), default)
        self.assertEqual(safe_relative_redirect_url('//evil.example/phish', default), default)
        self.assertEqual(safe_relative_redirect_url('/dashboard', default), '/dashboard')

    def test_resolve_upload_project_id_for_documents(self):
        import app as app_module
        from project_security import resolve_upload_project_id

        with app_module.app.app_context():
            pid = resolve_upload_project_id('/uploads/documents/999999991/spec.pdf')
            self.assertIsNone(pid)

    def test_resolve_upload_access_for_project_logo(self):
        from project_security import resolve_upload_access

        pid, kind = resolve_upload_access('/uploads/projects/42/logo')
        self.assertEqual(pid, 42)
        self.assertEqual(kind, 'logo')

    def test_guard_api_project_scope_blocks_cross_project_query(self):
        import time
        import app as app_module
        from project_access import save_memberships_for_user
        from scripts.simulate_security_harness import _login_client
        from case_workflow import ProjectMembership, ensure_workflow_schema

        with app_module.app.app_context():
            ensure_workflow_schema(app_module.db.engine)
            uid = f'ps{int(time.time() * 1000)}'
            iso_email = f'iso.{uid}@casepm.test'
            iso = app_module.User.query.filter_by(email=iso_email).first()
            if not iso:
                iso = app_module.User(
                    first_name='Iso', last_name='User', email=iso_email,
                    role='Company User', status='Active',
                )
                iso.set_password('IsoTest!12345')
                app_module.db.session.add(iso)
            p_a = app_module.Project(number=f'PA-{uid}', name='A', status='Active')
            p_b = app_module.Project(number=f'PB-{uid}', name='B', status='Active')
            app_module.db.session.add_all([p_a, p_b])
            app_module.db.session.flush()
            save_memberships_for_user(iso.id, [p_a.id], app_module.db, ProjectMembership=ProjectMembership)
            app_module.db.session.commit()

            with app_module.app.test_client() as client:
                _login_client(client, iso, app_module.app)
                rv = client.get(f'/api/schedule?project_id={p_b.id}')
                self.assertEqual(rv.status_code, 403, rv.get_json())


if __name__ == '__main__':
    unittest.main()
