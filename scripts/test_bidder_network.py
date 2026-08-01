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
            self.assertTrue(User.query.filter_by(email=email).first())


if __name__ == '__main__':
    unittest.main()
