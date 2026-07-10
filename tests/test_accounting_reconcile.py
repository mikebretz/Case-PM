"""Tests for bidirectional accounting reconciliation."""
import unittest

from accounting_reconcile import (
    _co_links_to_commitment,
    apply_budget_actual_reconcile,
    apply_budget_reconcile,
    apply_contractor_sov_reconcile,
    compute_budget_actual_targets,
    compute_budget_derivatives,
    compute_contractor_sov_co_amounts,
    compute_company_invoiced_totals,
    normalize_sub_sov_keys,
    reconcile_commitment_approved_changes,
    reconcile_commitment_invoiced_amounts,
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
        self.invoiced_amount = kwargs.get('invoiced_amount', 0)


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

    def test_normalize_sub_sov_keys_merges_duplicate_vendor(self):
        sub_sov = {
            '42': [{'cost_code': '26-1000', 'billed_to_date': 1000, 'original_commitment': 50000}],
            'Titan Electrical': [{'cost_code': '26-1000', 'billed_to_date': 2000, 'original_commitment': 0}],
        }
        merged = normalize_sub_sov_keys(sub_sov)
        self.assertEqual(len(merged), 2)
        total_billed = sum(
            float(l.get('billed_to_date') or 0)
            for lines in merged.values() for l in lines
        )
        self.assertEqual(total_billed, 3000)

    def test_compute_budget_actual_targets_from_sub_sov(self):
        pay_state = {
            'subcontractorSOV': {
                '42': [{
                    'cost_code': '26-1000',
                    'billed_to_date': 12000,
                    'co_billed_to_date': 3000,
                }],
            },
        }
        targets = compute_budget_actual_targets(pay_state, [], {})
        key = ('261000', 'Subcontract')
        self.assertEqual(targets[key], 15000)

    def test_apply_budget_actual_reconcile(self):
        state = {
            'budgetLines': [{
                'cost_code': '26-1000',
                'cost_type': 'Subcontract',
                'original_budget': 50000,
                'actual': 0,
            }],
        }
        key = ('261000', 'Subcontract')
        state = apply_budget_actual_reconcile(state, {key: 15000})
        self.assertEqual(state['budgetLines'][0]['actual'], 15000)
        self.assertEqual(state['budgetLines'][0]['actual_source'], 'reconciled')

    def test_compute_company_invoiced_totals(self):
        com = FakeCommitment(company_id='42', commitment_type='Subcontract')
        pay_state = {
            'subPayAppHistory': {
                '42': {
                    '1': {'status': 'Approved', 'totalBilledThisPeriod': 8500},
                    '2': {'status': 'Pending Approval', 'totalBilledThisPeriod': 1000},
                },
            },
        }
        totals = compute_company_invoiced_totals(pay_state, [com])
        self.assertEqual(totals[com.id], 8500)

    def test_reconcile_commitment_invoiced_amounts(self):
        com = FakeCommitment(company_id='42', invoiced_amount=0)
        pay_state = {
            'subPayAppHistory': {
                '42': {'1': {'status': 'Approved', 'totalBilledThisPeriod': 12000}},
            },
        }
        updates = reconcile_commitment_invoiced_amounts([com], pay_state)
        self.assertEqual(len(updates), 1)
        self.assertEqual(com.invoiced_amount, 12000)


if __name__ == '__main__':
    unittest.main()
