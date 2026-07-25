"""COR packages owner PCOs; SOV lines live on PCOs and roll up to COR (Procore model)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CorSovRollupTests(unittest.TestCase):
    def test_cor_rollup_from_linked_pcos(self):
        import app as app_module
        from app import db, Project, User, ChangeOrderRequest, PotentialChangeOrder, PCOAllocation
        from change_event_persistence import (
            ensure_change_event_schema,
            link_pcos_to_cor,
            cor_to_dict,
        )

        with app_module.app.app_context():
            ensure_change_event_schema(db.engine, db)
            uid = f'cor-rollup-{int(__import__("time").time() * 1000)}'
            user = User.query.filter_by(email='test@arch.com').first()
            self.assertIsNotNone(user)
            project = Project(number=f'COR-{uid}', name='COR SOV Test', status='Active')
            db.session.add(project)
            db.session.flush()

            def make_pco(title, amount):
                pco = PotentialChangeOrder(
                    project_id=project.id,
                    number=f'PCO-{uid}-{title[:3]}',
                    title=title,
                    estimated_amount=amount,
                    status='Open',
                    contract_type='Owner',
                    created_by_id=user.id,
                )
                db.session.add(pco)
                db.session.flush()
                db.session.add(PCOAllocation(
                    pco_id=pco.id, cost_code='03-3000', cost_type='Other',
                    amount=amount, description=f'SOV line for {title}',
                ))
                return pco

            pco1 = make_pco('Door upgrade', 1200.0)
            pco2 = make_pco('Frame revise', 800.0)
            cor = ChangeOrderRequest(
                project_id=project.id,
                number=f'COR-{uid}',
                title='Owner COR package',
                status='Draft',
                created_by_id=user.id,
            )
            db.session.add(cor)
            db.session.flush()

            link_pcos_to_cor(cor, [pco1.id, pco2.id], PotentialChangeOrder, PCOAllocation, db)
            db.session.commit()

            self.assertEqual(cor.amount, 2000.0)
            payload = cor_to_dict(cor, [], PotentialChangeOrder, PCOAllocation)
            self.assertFalse(payload['has_editable_sov'])
            self.assertEqual(len(payload['linked_pcos']), 2)
            self.assertEqual(len(payload['rollup_allocations']), 2)
            self.assertEqual(sum(r['amount'] for r in payload['rollup_allocations']), 2000.0)
            self.assertEqual(payload['allocations'], [])
            db.session.rollback()

    def test_finalize_cor_promotion_advances_linked_pcos(self):
        import app as app_module
        from app import db, Project, User, ChangeOrderRequest, PotentialChangeOrder, PCOAllocation
        from change_event_persistence import (
            ensure_change_event_schema,
            link_pcos_to_cor,
            finalize_cor_promotion,
        )

        with app_module.app.app_context():
            ensure_change_event_schema(db.engine, db)
            uid = f'cor-promo-{int(__import__("time").time() * 1000)}'
            user = User.query.filter_by(email='test@arch.com').first()
            self.assertIsNotNone(user)
            project = Project(number=f'CORP-{uid}', name='COR Promo Test', status='Active')
            db.session.add(project)
            db.session.flush()

            pco = PotentialChangeOrder(
                project_id=project.id,
                number=f'PCO-{uid}',
                title='Solo PCO',
                estimated_amount=500.0,
                status='Open',
                contract_type='Owner',
                created_by_id=user.id,
            )
            db.session.add(pco)
            db.session.flush()
            db.session.add(PCOAllocation(
                pco_id=pco.id, cost_code='03-3000', cost_type='Other', amount=500.0,
            ))

            cor = ChangeOrderRequest(
                project_id=project.id,
                number=f'COR-{uid}',
                title='Single PCO COR',
                status='Approved',
                amount=500.0,
                created_by_id=user.id,
            )
            db.session.add(cor)
            db.session.flush()
            link_pcos_to_cor(cor, [pco.id], PotentialChangeOrder, PCOAllocation, db)

            created = finalize_cor_promotion(
                cor, [], PotentialChangeOrder, PCOAllocation, db,
                lambda *a, **k: 'PCO-NEW', user.id,
            )
            self.assertIsNone(created)
            self.assertEqual(cor.status, 'Promoted')
            self.assertEqual(pco.status, 'Pending Review')
            db.session.rollback()


if __name__ == '__main__':
    unittest.main()
