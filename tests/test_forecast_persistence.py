"""Tests for forecast summary builder."""
import unittest
from datetime import date
from types import SimpleNamespace

from forecast_persistence import build_forecast_summary


class ForecastSummaryTests(unittest.TestCase):
    def test_build_summary_totals(self):
        project = SimpleNamespace(
            contract_value=1000000,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            get_details=lambda: {},
        )
        budget_state = {
            'budgetLines': [
                {'original_budget': 100000, 'approved_changes': 5000, 'pending': 2000, 'committed': 80000, 'actual': 40000},
                {'original_budget': 50000, 'approved_changes': 0, 'pending': 0, 'committed': 10000, 'actual': 10000},
            ],
        }
        pay_state = {
            'payAppHistory': [{'totalBilledThisPeriod': 25000}],
            'subPayAppHistory': {'42': {'1': {'totalBilledThisPeriod': 5000}}},
        }
        result = build_forecast_summary(project, budget_state, pay_state)
        self.assertEqual(result['original_budget'], 150000)
        self.assertEqual(result['approved_changes'], 5000)
        self.assertEqual(result['revised_budget'], 155000)
        self.assertEqual(result['actual_cost'], 50000)
        self.assertEqual(result['variance'], 105000)
        self.assertEqual(result['paid_out'], 30000)
        self.assertIn('full_job', result['projections'])

    def test_contract_includes_approved_change_orders(self):
        project = SimpleNamespace(
            contract_value=1000000,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            get_details=lambda: {},
        )
        result = build_forecast_summary(project, {'budgetLines': []}, {}, approved_co_total=75000)
        self.assertEqual(result['contract_amount'], 1075000)


if __name__ == '__main__':
    unittest.main()
