#!/usr/bin/env python3
"""Smoke test for ALDI pay application PDF generation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aldi_pay_application_pdf import generate_aldi_pay_application_pdf, default_template_path


def main():
    path = default_template_path()
    if not os.path.isfile(path):
        print('SKIP: template missing', path)
        return 0
    payload = {
        'period': {'periodNumber': 1, 'periodStart': '2026-07-01', 'periodEnd': '2026-07-31'},
        'project': {
            'owner': 'ALDI',
            'name': 'ALDI #318',
            'project_numbers': '318',
            'address': '6600 North Socrum Loop Rd, Lakeland, FL',
        },
        'g702': {
            'g702Original': 1_250_000.0,
            'g702ChangeOrders': 0.0,
            'contractSumToDate': 1_250_000.0,
            'cumulativeCompleted': 125_000.0,
            'retainageCompleted': 12_500.0,
            'retainageStored': 0.0,
            'cumulativeRetainage': 12_500.0,
            'earnedLessRetainage': 112_500.0,
            'previousEarnedLessRetainage': 0.0,
            'currentDue': 112_500.0,
            'balanceToFinish': 1_137_500.0,
            'retainageRate': 0.1,
        },
        'co_summary': None,
        'co_summary_slot': 0,
        'change_orders_this_period': [],
        'g703_lines': [
            {
                'cost_code': '950074',
                'description': 'General Requirements (Total Div 1)',
                'scheduled': 50_000,
                'prev_work': 0,
                'work_this_period': 5_000,
                'materials_stored': 0,
                'completed_to_date': 5_000,
                'retainage': 500,
            },
        ],
    }
    pdf = generate_aldi_pay_application_pdf(payload)
    assert pdf[:4] == b'%PDF', 'not a PDF'
    from aldi_pay_application_pdf import _fmt_date_mdy
    assert _fmt_date_mdy('2026-07-31') == '7/31/2026'
    out = os.path.join(os.path.dirname(__file__), '_aldi_pay_app_test_out.pdf')
    with open(out, 'wb') as fh:
        fh.write(pdf)
    print('OK wrote', out, 'bytes', len(pdf))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
