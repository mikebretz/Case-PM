"""Bidder plan room registration and approval."""
import sys
import unittest

sys.path.insert(0, '/workspace')


class BidderNetworkTests(unittest.TestCase):
    def test_package_manifest_roundtrip(self):
        from app import app, db, BidPackage
        from bidder_network_services import (
            default_package_manifest,
            parse_package_manifest,
            save_package_manifest,
            manifest_document_ids,
        )
        from bidder_network_persistence import ensure_bidder_network_schema

        with app.app_context():
            ensure_bidder_network_schema(db)
            pkg = BidPackage.query.first()
            if pkg:
                saved = save_package_manifest(pkg, default_package_manifest())
                self.assertIn('documents', saved)
                self.assertEqual(len(manifest_document_ids(saved)), 0)
                parsed = parse_package_manifest(pkg)
                self.assertEqual(parsed['itb']['timezone'], 'America/Denver')
                db.session.rollback()

    def test_sync_estimating_attachments(self):
        from app import app, db, BidPackage, Document, Project
        from bidder_network_persistence import ensure_bidder_network_schema
        from bidder_network_services import sync_package_manifest_from_estimating, manifest_document_ids, parse_package_manifest

        with app.app_context():
            ensure_bidder_network_schema(db)
            pkg = BidPackage.query.first()
            if not pkg:
                return
            pkg.attachments_json = '[]'
            out = sync_package_manifest_from_estimating(db, BidPackage, Document, pkg.id)
            self.assertIn('added', out)
            db.session.rollback()

    def test_clarification_flow(self):
        from app import app, db, Project
        from bidder_network_persistence import ensure_bidder_network_schema
        from plan_room_advanced_services import submit_clarification, answer_clarification, list_clarifications

        with app.app_context():
            ensure_bidder_network_schema(db)
            project = Project.query.first()
            user = __import__('app', fromlist=['User']).User.query.filter_by(role='Admin').first()
            if not project or not user:
                return
            out = submit_clarification(db, {
                'PlanRoomClarification': __import__('app', fromlist=['PlanRoomClarification']).PlanRoomClarification,
                'BidderNetworkRegistration': __import__('app', fromlist=['BidderNetworkRegistration']).BidderNetworkRegistration,
                'Project': Project,
            }, project.id, user, {'question_text': 'Is prevailing wage required?'})
            cid = out['clarification']['id']
            answer_clarification(db, __import__('app', fromlist=['PlanRoomClarification']).PlanRoomClarification, cid, user.id, {'answer_text': 'Yes, per ITB.'})
            listed = list_clarifications(db, __import__('app', fromlist=['PlanRoomClarification']).PlanRoomClarification, project.id)
            self.assertTrue(any(c['answer_text'] for c in listed['clarifications']))
            db.session.rollback()

    def test_registration_and_approve(self):
        from app import (
            app, db, BidderNetworkRegistration, BidderNetworkDocument,
            User, Company, BidPackage, Project, Estimate,
        )
        from bidder_network_persistence import ensure_bidder_network_schema
        from bidder_network_services import create_registration, approve_registration

        models = {
            'BidderNetworkRegistration': BidderNetworkRegistration,
            'BidderNetworkDocument': BidderNetworkDocument,
            'User': User,
            'Company': Company,
            'BidPackage': BidPackage,
            'Project': Project,
            'Estimate': Estimate,
        }

        with app.app_context():
            ensure_bidder_network_schema(db)
            email = 'bidder_test_unique@example.com'
            User.query.filter_by(email=email).delete()
            BidderNetworkRegistration.query.filter_by(email=email).delete()
            db.session.commit()

            out = create_registration(
                db, models,
                body={
                    'company_name': 'Test Electric LLC',
                    'contact_name': 'Sam Spark',
                    'email': email,
                    'phone': '555-0199',
                    'password': 'SecurePass1!',
                    'specialties': ['Electrical'],
                    'comments': 'Licensed statewide',
                },
                files=[],
                save_file_fn=lambda f, folder: None,
                upload_folder=app.config['UPLOAD_FOLDER'],
            )
            db.session.commit()
            self.assertEqual(out['registration']['status'], 'pending')

            reg_id = out['registration']['id']
            approve_registration(db, models, reg_id, reviewer_id=None)
            db.session.commit()

            row = BidderNetworkRegistration.query.get(reg_id)
            self.assertEqual(row.status, 'approved')
            user = User.query.filter_by(email=email).first()
            self.assertTrue(user)
            self.assertEqual(user.role, 'Plan Room Bidder')
            from portal_plan_room_access import is_plan_room_portal_user, plan_room_api_allowed
            self.assertTrue(is_plan_room_portal_user(user))
            self.assertFalse(plan_room_api_allowed('/api/projects', 'GET'))
            self.assertTrue(plan_room_api_allowed('/api/bidder-network/projects', 'GET'))


if __name__ == '__main__':
    unittest.main()
