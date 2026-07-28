#!/usr/bin/env python3
"""Tests for ALDI change order template PDF generation."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AldiChangeOrderPdfTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    try:
      import fitz  # noqa: F401
    except ImportError:
      raise unittest.SkipTest('pymupdf not installed')

  def test_fill_aldi_pdf_produces_bytes(self):
    from aldi_change_order_pdf import fill_aldi_change_order_pdf

    template_path = os.path.join(
      os.path.dirname(os.path.dirname(__file__)),
      'static', 'templates', 'change_orders', 'aldi_co_template.pdf',
    )
    self.assertTrue(os.path.isfile(template_path), 'ALDI template PDF must exist')

    co = SimpleNamespace(
      number='CO-101',
      title='Additional storefront glazing',
      description='Revise storefront framing per bulletin 3.',
      company_name='Case Construction LLC',
      date=date(2026, 9, 8),
      linked_drawing_revision='CCD-44',
      change_event_id=None,
      amount=12500.0,
    )
    project = SimpleNamespace(number='ALDI-2291', name='ALDI Store 2291', client='ALDI')
    pdf = fill_aldi_change_order_pdf(
      co,
      template_path=template_path,
      project=project,
      company_info={'company_name': 'Case Construction LLC'},
      allocations=[
        {'company_name': 'ABC Electric', 'cost_type': 'Labor', 'description': 'Temp power', 'cost_code': '26-100', 'amount': 1200},
        {'company_name': 'ABC Electric', 'cost_type': 'Material', 'description': 'Panel upgrade', 'cost_code': '26-100', 'amount': 800},
        {'company_name': 'XYZ Concrete', 'cost_type': 'Subcontract', 'description': 'Slab patch', 'cost_code': '03-300', 'amount': 4500},
      ],
    )
    self.assertTrue(pdf.startswith(b'%PDF'))
    self.assertGreater(len(pdf), 10000)

    import fitz
    doc = fitz.open(stream=pdf, filetype='pdf')
    try:
      self.assertGreaterEqual(doc.page_count, 2)
      text = '\n'.join(doc[i].get_text() for i in range(min(2, doc.page_count)))
      self.assertRegex(text, r'(?:^|\n)101(?:\n|$)')
      self.assertIn('ABC Electric', text)
    finally:
      doc.close()

  def test_seed_template_row(self):
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy

    app = Flask(__name__)
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)

    class ChangeOrderTemplate(db.Model):
      __tablename__ = 'change_order_template'
      id = db.Column(db.Integer, primary_key=True)
      slug = db.Column(db.String(80), nullable=False, unique=True)
      name = db.Column(db.String(200), nullable=False)
      company_key = db.Column(db.String(120))
      description = db.Column(db.Text)
      template_pdf_path = db.Column(db.String(500), nullable=False)
      engine = db.Column(db.String(80), nullable=False, default='aldi_v1')
      field_map_json = db.Column(db.Text)
      page_layout_json = db.Column(db.Text)
      is_active = db.Column(db.Boolean, default=True)
      is_default = db.Column(db.Boolean, default=False)
      created_by_id = db.Column(db.Integer)
      created_at = db.Column(db.DateTime)
      updated_at = db.Column(db.DateTime)

    with app.app_context():
      from change_order_template_persistence import ensure_change_order_template_schema, template_to_dict
      ensure_change_order_template_schema(db.engine, db, ChangeOrderTemplate)
      row = ChangeOrderTemplate.query.filter_by(slug='aldi_co').first()
      self.assertIsNotNone(row)
      payload = template_to_dict(row)
      self.assertEqual(payload['company_key'], 'ALDI')
      self.assertTrue(payload['is_default'])

    os.unlink(db_path)

  def test_co_number_formatting(self):
    from aldi_change_order_pdf import _format_co_number_for_form
    self.assertEqual(_format_co_number_for_form('CO-001'), '1')
    self.assertEqual(_format_co_number_for_form('CO-012'), '12')
    self.assertEqual(_format_co_number_for_form('3'), '3')


  def test_register_template_helpers(self):
    from change_order_template_persistence import _slugify_template_name, save_template_pdf_file
    import tempfile

    self.assertEqual(_slugify_template_name('ALDI Change Order'), 'aldi_change_order')
    with tempfile.TemporaryDirectory() as tmp:
      static_dir = os.path.join(tmp, 'static')
      rel = save_template_pdf_file('test_tpl', b'%PDF-1.4 test', static_folder=static_dir)
      self.assertTrue(rel.endswith('test_tpl.pdf'))
      self.assertTrue(os.path.isfile(os.path.join(static_dir, 'templates', 'change_orders', 'test_tpl.pdf')))


if __name__ == '__main__':
  unittest.main()
