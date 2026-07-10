"""Tests for change order → subcontractor SOV sync."""
import unittest

from pay_app_persistence import (
    apply_co_to_subcontractor_sov,
    normalize_cost_code,
    resolve_sub_sov_targets_for_allocation,
)


class FakeCO:
    project_id = 1
    company_id = '42'
    company_name = 'Titan Electrical'
    contract_type = 'Subcontract'
    linked_commitment_ref = None
    number = 'CO-007'


class FakeAlloc:
    cost_code = '26-1000'
    amount = 5000
    description = 'Added circuits'


class FakeCommitment:
    pass


class CoSubSovSyncTests(unittest.TestCase):
    def test_apply_co_to_existing_sub_line(self):
        state = {
            'subcontractorSOV': {
                '42': [{
                    'id': 'line-1',
                    'cost_code': '26-1000',
                    'description': 'Electrical',
                    'original_commitment': 100000,
                    'change_orders': 0,
                    'scheduled_value': 100000,
                }],
            },
        }
        state, applied = apply_co_to_subcontractor_sov(
            state, '42', 5000, '26-1000', 'Added circuits', 'CO-007',
        )
        self.assertEqual(applied, 5000)
        line = state['subcontractorSOV']['42'][0]
        self.assertEqual(line['change_orders'], 5000)
        self.assertEqual(line['scheduled_value'], 105000)
        self.assertEqual(line['from_change_order'], 'CO-007')

    def test_apply_co_creates_line_without_original_commitment(self):
        state = {'subcontractorSOV': {'42': []}}
        state, applied = apply_co_to_subcontractor_sov(
            state, '42', 2500, '26-2000', 'Extra scope', 'CO-008',
        )
        self.assertEqual(applied, 2500)
        lines = state['subcontractorSOV']['42']
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['original_commitment'], 0)
        self.assertEqual(lines[0]['change_orders'], 2500)

    def test_resolve_targets_by_cost_code_match(self):
        sub_sov = {
            '42': [{'cost_code': '26-1000', 'original_commitment': 1}],
            '99': [{'cost_code': '03-1000', 'original_commitment': 1}],
        }
        targets = resolve_sub_sov_targets_for_allocation(FakeCO(), sub_sov, FakeAlloc(), FakeCommitment)
        self.assertIn('42', targets)

    def test_idempotent_sub_line(self):
        state = {
            'subcontractorSOV': {
                '42': [{
                    'cost_code': '26-1000',
                    'original_commitment': 0,
                    'change_orders': 5000,
                    'from_change_order': 'CO-007',
                }],
            },
        }
        state, applied = apply_co_to_subcontractor_sov(
            state, '42', 5000, '26-1000', 'Added circuits', 'CO-007',
        )
        self.assertEqual(applied, 0.0)
        self.assertEqual(state['subcontractorSOV']['42'][0]['change_orders'], 5000)


if __name__ == '__main__':
    unittest.main()
