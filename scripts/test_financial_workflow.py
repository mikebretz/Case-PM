#!/usr/bin/env python3
"""Unit tests for financial workflow hardening (pay apps, reconcile, CO numbering)."""
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


class G702SecurityTests(unittest.TestCase):
    def setUp(self):
        from pay_app_workflow import (
            _billing_amount_from_sov_state,
            _g702_threshold_amount,
            g702_workflow_action,
            validate_g702_submit_gates,
        )

        self.billing_amount = _billing_amount_from_sov_state
        self.threshold_amount = _g702_threshold_amount
        self.g702 = g702_workflow_action
        self.validate_g702 = validate_g702_submit_gates
        self.pm = SimpleNamespace(id=1, role='Project Manager')
        self.owner = SimpleNamespace(id=2, role='Owner')

    def test_threshold_ignores_spoofed_body_amount(self):
        state = {
            'contractorSOV': [{'id': 1, 'cost_code': '01-100'}],
            'payAppBillingLines': {'1': {'workThisPeriod': 3_600_000, 'materialsStored': 0}},
            'payAppRetainagePercent': 10,
        }
        self.assertGreater(self.threshold_amount(state), 3_000_000)
        period = {'status': 'Submitted', 'ball_in_court_role': 'Project Manager'}
        status, final = self.g702(period, 'approve', self.pm, amount=self.threshold_amount(state))
        self.assertEqual(status, 'Pending Owner')
        self.assertFalse(final)

    def test_g702_submit_blocked_without_lien_waivers(self):
        state = {
            'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'},
            'requireLienWaiverOnSubPayApp': True,
            'requireAllSubPayAppsBeforeG702Submit': True,
            'subcontractorSOV': {'101': [{'cost_code': '03-300'}]},
            'subSOVStatus': {'101': {'status': 'Approved'}},
            'subPayAppHistory': {
                '101': {'1': {'periodNumber': 1, 'status': 'Approved', 'totalBilledThisPeriod': 1000}},
            },
            'subLienWaivers': {},
        }
        with self.assertRaises(ValueError) as ctx:
            self.validate_g702(state)
        self.assertIn('lien waiver', str(ctx.exception).lower())

    def test_g702_submit_allowed_with_waivers(self):
        state = {
            'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'},
            'requireLienWaiverOnSubPayApp': True,
            'requireAllSubPayAppsBeforeG702Submit': True,
            'subcontractorSOV': {'101': [{'cost_code': '03-300'}]},
            'subSOVStatus': {'101': {'status': 'Approved'}},
            'subPayAppHistory': {
                '101': {'1': {'periodNumber': 1, 'status': 'Approved', 'totalBilledThisPeriod': 1000}},
            },
            'subLienWaivers': {'101': {'1': {'filename': 'waiver.pdf'}}},
        }
        self.validate_g702(state)


class ReconcileCanonicalKeyTests(unittest.TestCase):
    def test_compute_sub_sov_derivatives_uses_single_vendor_bucket(self):
        from accounting_reconcile import compute_sub_sov_derivatives, normalize_sub_sov_keys

        Commitment = SimpleNamespace
        com = Commitment(
            id=1, commitment_type='Subcontract', status='Approved',
            company_id='101', company_name='Concrete Sim Co', number='SC-1',
        )
        alloc = SimpleNamespace(cost_code='03-300', amount=1_000_000, description='Concrete')
        com_alloc_map = {1: [alloc]}
        existing = {
            '101': [{'cost_code': '03-300', 'from_commitment': 'SC-1'}],
            'Concrete Sim Co': [{'cost_code': '03-300', 'from_commitment': 'SC-1'}],
        }
        originals, changes, _display = compute_sub_sov_derivatives(
            [], [com], {}, com_alloc_map, existing, Commitment,
        )
        merged = normalize_sub_sov_keys(existing)
        self.assertIn('101', originals)
        self.assertNotIn('Concrete Sim Co', originals)
        self.assertEqual(len(merged), 1)


class ChangeOrderNumberScopeTests(unittest.TestCase):
    def test_same_co_number_allowed_on_different_projects(self):
        import app as app_module
        from app import db, ChangeOrder, Project
        from co_persistence import ensure_co_schema

        with app_module.app.app_context():
            ensure_co_schema(db.engine, db)
            p1 = Project(number='T-P1', name='Test P1', status='Active')
            p2 = Project(number='T-P2', name='Test P2', status='Active')
            db.session.add_all([p1, p2])
            db.session.flush()
            co1 = ChangeOrder(project_id=p1.id, number='CO-SCOPE-001', description='Test one', status='Draft')
            co2 = ChangeOrder(project_id=p2.id, number='CO-SCOPE-001', description='Test two', status='Draft')
            db.session.add_all([co1, co2])
            db.session.commit()
            self.assertNotEqual(co1.project_id, co2.project_id)
            self.assertEqual(co1.number, co2.number)
            db.session.delete(co1)
            db.session.delete(co2)
            db.session.delete(p1)
            db.session.delete(p2)
            db.session.commit()


if __name__ == '__main__':
    unittest.main()
