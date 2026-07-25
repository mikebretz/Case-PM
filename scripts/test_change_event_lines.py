"""Tests for Procore-style change event line items and bulk commitment CO creation."""
import unittest


class ChangeEventLineItemTests(unittest.TestCase):
    def test_bulk_create_groups_by_vendor_and_commitment(self):
        import app as app_module
        from app import db, Project, ChangeEvent, ChangeEventLineItem, ChangeOrder, User
        from change_event_persistence import (
            ensure_change_event_schema,
            save_change_event_line_items,
            bulk_create_commitment_cos_from_lines,
        )

        with app_module.app.app_context():
            ensure_change_event_schema(db.engine, db)
            uid = f'ce-bulk-{int(__import__("time").time() * 1000)}'
            pm = User.query.filter_by(email='test@arch.com').first()
            self.assertIsNotNone(pm)
            project = Project(number=f'CE-{uid}', name='CE Bulk Test', status='Active')
            db.session.add(project)
            db.session.flush()
            ce = ChangeEvent(
                project_id=project.id,
                number=f'CE-{uid}',
                title='Multi-sub change',
                status='Open',
                created_by_id=pm.id,
            )
            db.session.add(ce)
            db.session.flush()

            save_change_event_line_items(ce, [
                {'cost_code': '03-100', 'description': 'Concrete A', 'amount': 10000,
                 'company_name': 'Sub A', 'company_id': '1', 'linked_commitment_ref': 'SC-001'},
                {'cost_code': '03-200', 'description': 'Concrete B', 'amount': 5000,
                 'company_name': 'Sub A', 'company_id': '1', 'linked_commitment_ref': 'SC-001'},
                {'cost_code': '09-100', 'description': 'Drywall', 'amount': 8000,
                 'company_name': 'Sub B', 'company_id': '2', 'linked_commitment_ref': 'SC-002'},
            ], ChangeEventLineItem, db)
            db.session.commit()
            lines = ChangeEventLineItem.query.filter_by(change_event_id=ce.id).all()
            self.assertEqual(len(lines), 3)
            self.assertEqual(ce.rom_amount, 23000)

            created = bulk_create_commitment_cos_from_lines(
                ce, [l.id for l in lines],
                ChangeOrder, app_module.ChangeOrderAllocation, ChangeEventLineItem, db,
                app_module.generate_next_number, pm.id,
            )
            db.session.commit()
            self.assertEqual(len(created), 2)
            refs = {co.linked_commitment_ref for co in created}
            self.assertEqual(refs, {'SC-001', 'SC-002'})
            sc001 = next(c for c in created if c.linked_commitment_ref == 'SC-001')
            sc001_allocs = app_module.ChangeOrderAllocation.query.filter_by(change_order_id=sc001.id).all()
            self.assertEqual(len(sc001_allocs), 2)
            self.assertEqual(round(sum(a.amount for a in sc001_allocs), 2), 15000)

            for line in ChangeEventLineItem.query.filter_by(change_event_id=ce.id).all():
                self.assertTrue(line.linked_sco_id)
                self.assertEqual(line.status, 'In CCO')

            db.session.rollback()

    def test_bulk_create_rejects_duplicate_sco(self):
        import app as app_module
        from app import db, Project, ChangeEvent, ChangeEventLineItem, ChangeOrder, User
        from change_event_persistence import save_change_event_line_items, bulk_create_commitment_cos_from_lines, ensure_change_event_schema

        with app_module.app.app_context():
            ensure_change_event_schema(db.engine, db)
            uid = f'ce-dup-{int(__import__("time").time() * 1000)}'
            pm = User.query.filter_by(email='test@arch.com').first()
            project = Project(number=f'CE-DUP-{uid}', name='X', status='Active')
            db.session.add(project)
            db.session.flush()
            ce = ChangeEvent(project_id=project.id, number=f'CE-DUP-{uid}', title='t', status='Open', created_by_id=pm.id)
            db.session.add(ce)
            db.session.flush()
            save_change_event_line_items(ce, [
                {'cost_code': '01', 'amount': 1, 'company_name': 'A', 'linked_commitment_ref': 'SC-1'},
            ], ChangeEventLineItem, db)
            line = ChangeEventLineItem.query.filter_by(change_event_id=ce.id).first()
            bulk_create_commitment_cos_from_lines(
                ce, [line.id], ChangeOrder, app_module.ChangeOrderAllocation,
                ChangeEventLineItem, db, app_module.generate_next_number, pm.id,
            )
            db.session.commit()
            with self.assertRaises(ValueError):
                bulk_create_commitment_cos_from_lines(
                    ce, [line.id], ChangeOrder, app_module.ChangeOrderAllocation,
                    ChangeEventLineItem, db, app_module.generate_next_number, pm.id,
                )
            db.session.rollback()


if __name__ == '__main__':
    unittest.main()
