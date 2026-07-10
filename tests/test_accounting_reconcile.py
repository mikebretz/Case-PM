"""Tests for bidirectional accounting reconciliation."""
import unittest

from accounting_reconcile import (
    _co_links_to_commitment,
    apply_budget_reconcile,
    apply_contractor_sov_reconcile,
    compute_budget_derivatives,
    compute_contractor_sov_co_amounts,
    reconcile_commitment_approved_changes,
)


class FakeCO:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.status = kwargs.get('status', 'Approved')
        self.amount = kwargs.get('amount', 0)
        self.cost_code = kwargs.get('cost_code')
        self.number = kwargs.get('number', 'CO-001')
        self.description = kwargs.get('description', '')
        self.company_id = kwargs.get('company_id')
        self.company_name = kwargs.get('company_name')
        self.contract_type = kwargs.get('contract_type')
        self.linked_commitment_ref = kwargs.get('linked_commitment_ref')


class FakeAlloc:
    def __init__(self, cost_code, amount, cost_type='Other'):
        self.cost_code = cost_code
        self.amount = amount
        self.cost_type = cost_type


class FakeCommitment:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 10)
        self.number = kwargs.get('number', 'SC-001')
        self.commitment_type = kwargs.get('commitment_type', 'Subcontract')
        self.status = kwargs.get('status', 'Approved')
        self.original_amount = kwargs.get('original_amount', 100000)
        self.approved_changes = kwargs.get('approved_changes', 0)
        self.current_amount = kwargs.get('current_amount', 100000)
        self.company_id = kwargs.get('company_id', '42')
        self.company_name = kwargs.get('company_name', 'Titan Electrical')


class AccountingReconcileTests(unittest.TestCase):
    def test_compute_budget_derivatives_approved_co(self):
        co = FakeCO(status='Approved')
        targets = compute_budget_derivatives(
            [co], [], {1: [FakeAlloc('26-1000', 5000)]}, {},
        )
        key = ('261000', 'Other')
        self.assertEqual(targets[key]['approved_changes'], 5000)

    def test_compute_budget_derivatives_pending_commitment(self):
        com = FakeCommitment(status='Submitted')
        targets = compute_budget_derivatives(
            [], [com], {}, {10: [FakeAlloc('26-1000', 3000)]},
        )
        key = ('261000', 'Subcontract')
        self.assertEqual(targets[key]['pending'], 3000)

    def test_apply_budget_reconcile_zeros_removed_co(self):
        state = {
            'budgetLines': [{
                'cost_code': '26-1000',
                'cost_type': 'Other',
                'original_budget': 10000,
                'approved_changes': 999,
                'pending': 0,
                'committed': 0,
            }],
        }
        state = apply_budget_reconcile(state, {})
        self.assertEqual(state['budgetLines'][0]['approved_changes'], 0)

    def test_contractor_sov_recompute(self):
        co = FakeCO(status='Approved')
        totals, display = compute_contractor_sov_co_amounts(
            [co], {1: [FakeAlloc('03-1000', 2500)]},
        )
        self.assertEqual(totals['031000'], 2500)
        state = apply_contractor_sov_reconcile({'contractorSOV': []}, totals, display)
        self.assertEqual(state['contractorSOV'][0]['co_amount'], 2500)

    def test_co_links_to_commitment_by_ref(self):
        co = FakeCO(linked_commitment_ref='SC-001')
        com = FakeCommitment(number='SC-001')
        self.assertTrue(_co_links_to_commitment(co, com))

    def test_commitment_approved_changes_from_linked_co(self):
        co = FakeCO(
            status='Approved',
            linked_commitment_ref='SC-001',
            contract_type='Subcontract',
            company_id='42',
        )
        com = FakeCommitment(approved_changes=0, current_amount=100000)
        updates = reconcile_commitment_approved_changes(
            [co], [com], {1: [FakeAlloc('26-1000', 7500)]},
        )
        self.assertEqual(len(updates), 1)
        self.assertEqual(com.approved_changes, 7500)
        self.assertEqual(com.current_amount, 107500)


if __name__ == '__main__':
    unittest.main()
