#!/usr/bin/env python3
"""Tests for subcontract change order PDF template."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SubChangeOrderPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import fitz  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('pymupdf not installed')

    def test_fill_sub_co_pdf_produces_bytes(self):
        from sub_change_order_pdf import fill_sub_change_order_pdf

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'static', 'templates', 'change_orders', 'sub_co_template.pdf',
        )
        self.assertTrue(os.path.isfile(template_path), 'Sub CO template PDF must exist')

        co = SimpleNamespace(
            id=5,
            project_id=1,
            number='SCO-12',
            title='Added roof drains',
            description='Install four additional roof drains per RFI 44.',
            company_name='ABC Roofing LLC',
            contact_name='Jane Smith',
            date=date(2026, 8, 1),
            amount=8750.0,
            status='Approved',
            linked_commitment_ref='SUB-101',
            company_id='vendor-1',
            notes='',
        )
        commitment = SimpleNamespace(
            number='SUB-101',
            original_amount=125000.0,
            company_name='ABC Roofing LLC',
        )
        project = SimpleNamespace(name='ALDI Lakeland', number='640')
        prior = SimpleNamespace(
            id=3,
            project_id=1,
            number='SCO-10',
            amount=2500.0,
            status='Approved',
            contract_type='Subcontract',
            linked_commitment_ref='SUB-101',
            company_id='vendor-1',
            company_name='ABC Roofing LLC',
        )

        class FakeCommitmentQuery:
            def filter_by(self, project_id=None, number=None):
                return self

            def first(self):
                return commitment

        class FakeCoQuery:
            def filter_by(self, **kwargs):
                return self

            def all(self):
                return [prior, co]

        class FakeCommitment:
            query = FakeCommitmentQuery()

        class FakeChangeOrder:
            query = FakeCoQuery()

        pdf = fill_sub_change_order_pdf(
            co,
            template_path=template_path,
            project=project,
            allocations=[{'cost_code': '07-100', 'description': 'Roofing', 'amount': 8750}],
            Commitment=FakeCommitment,
            ChangeOrder=FakeChangeOrder,
        )
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 5000)

        import fitz
        doc = fitz.open(stream=pdf, filetype='pdf')
        try:
            page = doc[0]
            text = page.get_text()
            self.assertIn('ABC Roofing', text)
            self.assertIn('12', text)
        finally:
            doc.close()


if __name__ == '__main__':
    unittest.main()
