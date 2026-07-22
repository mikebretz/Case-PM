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

    def test_canonicalize_merges_split_vendor_buckets(self):
        from pay_app_persistence import canonicalize_sub_sov_vendor_keys
        from types import SimpleNamespace

        Commitment = SimpleNamespace
        com = Commitment(
            id=1, commitment_type='Subcontract', status='Approved',
            company_id='42', company_name='Acme', number='SC-1',
        )
        state = {
            'subcontractorSOV': {
                'local-5': [{
                    'id': 1, 'cost_code': '03-300', 'description': 'Concrete',
                    'original_commitment': 50_000, 'change_orders': 0,
                }],
            },
            'subSOVStatus': {
                'local-5': {
                    'status': 'Approved',
                    'companyName': 'Acme',
                    'companyId': '42',
                    'localCompanyId': 'local-5',
                },
            },
        }
        canonicalize_sub_sov_vendor_keys(state, [com])
        self.assertIn('42', state['subcontractorSOV'])
        self.assertIn('42', state['subSOVStatus'])
        self.assertEqual(len(state['subcontractorSOV']['42']), 1)
        self.assertEqual(state['subcontractorSOV']['42'][0]['original_commitment'], 50_000)

    def test_approved_sov_survives_reconcile_and_prune(self):
        from accounting_reconcile import apply_sub_sov_reconcile, compute_sub_sov_derivatives
        from pay_app_persistence import canonicalize_sub_sov_vendor_keys, prune_unregistered_sub_sov
        from types import SimpleNamespace

        Commitment = SimpleNamespace
        com = Commitment(
            id=1, commitment_type='Subcontract', status='Approved',
            company_id='42', company_name='Acme', number='SC-1',
            original_amount=100_000, current_amount=100_000,
        )
        state = {
            'subcontractorSOV': {
                '42': [{
                    'id': 1, 'cost_code': '03-300', 'description': 'Concrete',
                    'original_commitment': 50_000, 'change_orders': 0,
                }],
            },
            'subSOVStatus': {'42': {'status': 'Approved', 'companyName': 'Acme', 'companyId': '42'}},
        }
        originals, changes, display = compute_sub_sov_derivatives(
            [], [com], {}, {}, state['subcontractorSOV'], Commitment,
        )
        state = apply_sub_sov_reconcile(dict(state), originals, changes, display)
        state = canonicalize_sub_sov_vendor_keys(state, [com])
        out = prune_unregistered_sub_sov(state, [com])
        lines = out['subcontractorSOV'].get('42') or []
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['original_commitment'], 50_000)

    def test_normalize_pay_period_starts_at_one_without_history(self):
        from pay_app_persistence import normalize_current_pay_app_period
        state = {
            'currentPayAppPeriod': {'periodNumber': 7, 'status': 'Draft'},
            'payAppHistory': [],
        }
        out = normalize_current_pay_app_period(state)
        self.assertEqual(out['currentPayAppPeriod']['periodNumber'], 1)

    def test_reconcile_new_line_ids_are_numeric(self):
        from accounting_reconcile import apply_sub_sov_reconcile, compute_sub_sov_derivatives
        from types import SimpleNamespace

        Commitment = SimpleNamespace
        com = Commitment(
            id=1, commitment_type='Subcontract', status='Approved',
            company_id='42', company_name='Acme', number='SC-1',
            original_amount=100_000, current_amount=100_000,
        )
        state = {
            'subcontractorSOV': {'42': []},
            'subSOVStatus': {'42': {'status': 'Approved', 'companyName': 'Acme', 'companyId': '42'}},
        }
        originals = {'42': {'03300': 25_000}}
        changes = {}
        display = {'42': {'03300': '03-300'}}
        state = apply_sub_sov_reconcile(dict(state), originals, changes, display)
        lines = state['subcontractorSOV'].get('42') or []
        self.assertEqual(len(lines), 1)
        line_id = lines[0]['id']
        self.assertIsInstance(line_id, int)
        self.assertNotIn('recon-', str(line_id))


class CommitmentValidationTests(unittest.TestCase):
    def test_validate_commitment_allocations_requires_cost_code(self):
        from commitment_persistence import validate_commitment_allocations
        self.assertEqual(len(validate_commitment_allocations([])), 1)
        self.assertEqual(len(validate_commitment_allocations([{'amount': 1000}])), 1)
        self.assertEqual(validate_commitment_allocations([{'cost_code': '03-300', 'amount': 1000}]), [])


class PutBypassTests(unittest.TestCase):
    def test_strip_workflow_fields_removes_status(self):
        from financial_security import strip_workflow_fields
        cleaned = strip_workflow_fields({'status': 'Approved', 'title': 'Test'})
        self.assertNotIn('status', cleaned)
        self.assertEqual(cleaned['title'], 'Test')

    def test_sanitize_pay_app_blocks_status_spoof(self):
        from financial_security import sanitize_pay_app_state
        existing = {
            'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft', 'ball_in_court_role': 'Creator'},
            'subSOVStatus': {'101': {'status': 'Draft'}},
        }
        patch = {
            'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Approved', 'ball_in_court_role': None},
            'subSOVStatus': {'101': {'status': 'Approved'}},
        }
        merged = sanitize_pay_app_state(existing, patch)
        self.assertEqual(merged['currentPayAppPeriod']['status'], 'Draft')
        self.assertEqual(merged['subSOVStatus']['101']['status'], 'Draft')

    def test_sanitize_pay_app_strips_amount_due(self):
        from financial_security import sanitize_pay_app_state
        merged = sanitize_pay_app_state(
            {'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'}},
            {'currentPayAppPeriod': {'periodNumber': 1, 'amount_due': 1000}},
        )
        self.assertNotIn('amount_due', merged['currentPayAppPeriod'])

    def test_apply_co_fields_ignores_status(self):
        import app as app_module
        from app import ChangeOrder, db
        from co_persistence import apply_co_fields
        with app_module.app.app_context():
            co = ChangeOrder(project_id=1, number='T-1', description='t', status='Draft')
            apply_co_fields(co, {'status': 'Approved', 'ball_in_court_role': None})
            self.assertEqual(co.status, 'Draft')

    def test_assert_draft_create_status_blocks_approved(self):
        from financial_security import assert_draft_create_status
        with self.assertRaises(ValueError):
            assert_draft_create_status('Approved')


class G702GateScopeTests(unittest.TestCase):
    def test_billed_scope_ignores_unbilled_subs(self):
        from pay_app_workflow import validate_g702_submit_gates
        state = {
            'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'},
            'requireAllSubPayAppsBeforeG702Submit': True,
            'requireLienWaiverOnSubPayApp': False,
            'g702PayAppGateScope': 'billed_this_period',
            'subcontractorSOV': {
                '101': [{'cost_code': '03-300', 'work_this_period': 5000}],
                '102': [{'cost_code': '09-250', 'work_this_period': 0}],
            },
            'subSOVStatus': {'101': {'status': 'Approved'}, '102': {'status': 'Approved'}},
            'subPayAppHistory': {
                '101': {'1': {'periodNumber': 1, 'status': 'Approved', 'totalBilledThisPeriod': 5000}},
            },
        }
        validate_g702_submit_gates(state)

    def test_all_subs_scope_blocks_unbilled(self):
        from pay_app_workflow import validate_g702_submit_gates
        state = {
            'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'},
            'requireAllSubPayAppsBeforeG702Submit': True,
            'requireLienWaiverOnSubPayApp': False,
            'g702PayAppGateScope': 'all_approved_subs',
            'subcontractorSOV': {
                '101': [{'cost_code': '03-300'}],
                '102': [{'cost_code': '09-250'}],
            },
            'subSOVStatus': {'101': {'status': 'Approved'}, '102': {'status': 'Approved'}},
            'subPayAppHistory': {
                '101': {'1': {'periodNumber': 1, 'status': 'Approved', 'totalBilledThisPeriod': 5000}},
            },
        }
        with self.assertRaises(ValueError) as ctx:
            validate_g702_submit_gates(state)
        self.assertIn('missing pay applications', str(ctx.exception).lower())


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


class RfqSecurityTests(unittest.TestCase):
    def test_rfq_reject_requires_ball_in_court(self):
        from change_event_persistence import rfq_workflow_action
        from types import SimpleNamespace
        rfq = SimpleNamespace(
            status='Quoted', ball_in_court_role='Project Manager', quoted_amount=1000,
        )
        sub = SimpleNamespace(id=1, role='Subcontractor Accountant')
        with self.assertRaises(ValueError):
            rfq_workflow_action(rfq, 'reject', sub)

    def test_apply_rfq_fields_ignores_quoted_amount(self):
        from change_event_persistence import apply_rfq_fields
        from types import SimpleNamespace
        rfq = SimpleNamespace(quoted_amount=5000.0, status='Quoted')
        apply_rfq_fields(rfq, {'quoted_amount': 1.0})
        self.assertEqual(rfq.quoted_amount, 5000.0)


class RfiSecurityTests(unittest.TestCase):
    def test_apply_rfi_fields_ignores_status_on_update(self):
        from rfi_persistence import apply_rfi_fields
        from types import SimpleNamespace
        rfi = SimpleNamespace(status='Closed', ball_in_court_role=None)
        apply_rfi_fields(rfi, {'status': 'Void'})
        self.assertEqual(rfi.status, 'Closed')


class SubmittalSecurityTests(unittest.TestCase):
    def test_apply_submittal_fields_ignores_status_on_update(self):
        from submittal_persistence import apply_submittal_fields
        from types import SimpleNamespace
        sub = SimpleNamespace(status='Closed', ball_in_court=None)
        apply_submittal_fields(sub, {'status': 'Draft'}, is_create=False)
        self.assertEqual(sub.status, 'Closed')


if __name__ == '__main__':
    unittest.main()
