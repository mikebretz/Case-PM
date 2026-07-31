"""A/P depth — vendor groups, recurring payables, 1099, 3-way match, void payment, withholding."""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_operations import _parse_lines


def serialize_vendor_group(g):
    return {'id': g.id, 'code': g.code, 'name': g.name, 'terms': g.terms, 'status': g.status}


def serialize_vendor_extended(v):
    from accounting_persistence import serialize_vendor
    base = serialize_vendor(v)
    base.update({
        'vendor_group_id': v.vendor_group_id,
        'tax_id': v.tax_id or '',
        'is_1099': bool(v.is_1099),
        'form_1099_type': v.form_1099_type or 'NEC',
        'default_withhold_percent': float(v.default_withhold_percent or 0),
    })
    return base


def patch_vendor_extended(v, body):
    if body.get('vendor_group_id') is not None:
        v.vendor_group_id = int(body['vendor_group_id']) if body['vendor_group_id'] else None
    if 'tax_id' in body:
        v.tax_id = str(body['tax_id'])[:30]
    if 'is_1099' in body:
        v.is_1099 = bool(body['is_1099'])
    if body.get('form_1099_type'):
        v.form_1099_type = str(body['form_1099_type'])[:10]
    if 'default_withhold_percent' in body:
        v.default_withhold_percent = max(0.0, float(body['default_withhold_percent'] or 0))
    return v


def compute_ap_invoice_amounts(gross, *, retainage_percent=0, withhold_percent=0):
    gross = round(float(gross or 0), 2)
    retainage = round(gross * float(retainage_percent or 0) / 100.0, 2)
    net_before_wh = round(gross - retainage, 2)
    withhold = round(net_before_wh * float(withhold_percent or 0) / 100.0, 2)
    payable = round(net_before_wh - withhold, 2)
    return {
        'gross_amount': gross,
        'retainage_amount': retainage,
        'withhold_amount': withhold,
        'amount': payable,
    }


def serialize_recurring_ap(r):
    return {
        'id': r.id,
        'vendor_id': r.vendor_id,
        'description': r.description,
        'amount': r.amount,
        'frequency': r.frequency,
        'next_run_date': r.next_run_date.isoformat() if r.next_run_date else None,
        'is_active': r.is_active,
        'document_number_prefix': r.document_number_prefix,
    }


def generate_recurring_ap_invoice(db, models, recurring):
    if not recurring.is_active:
        raise ValueError('Recurring payable inactive')
    AcctAPDocument = models['AcctAPDocument']
    n = AcctAPDocument.query.filter_by(ledger_id=recurring.ledger_id).count()
    doc = AcctAPDocument(
        ledger_id=recurring.ledger_id,
        vendor_id=recurring.vendor_id,
        document_number=f'{recurring.document_number_prefix}-{datetime.utcnow().strftime("%Y%m%d")}-{n + 1}',
        document_type='Invoice',
        document_date=recurring.next_run_date or date.today(),
        due_date=recurring.next_run_date or date.today(),
        amount=recurring.amount,
        gross_amount=recurring.amount,
        status='Open',
    )
    db.session.add(doc)
    recurring.last_run_date = doc.document_date
    if recurring.frequency == 'weekly':
        recurring.next_run_date = (recurring.next_run_date or date.today()).replace(day=min(28, (recurring.next_run_date or date.today()).day))
        from datetime import timedelta
        recurring.next_run_date = (recurring.next_run_date or date.today()) + timedelta(days=7)
    else:
        d = recurring.next_run_date or date.today()
        recurring.next_run_date = date(d.year + (1 if d.month == 12 else 0), (d.month % 12) + 1, min(d.day, 28))
    db.session.flush()
    return doc


def three_way_match(db, models, ledger_id, invoice_id):
    """Match AP invoice to PO receipts (qty/amount tolerance)."""
    AcctAPDocument = models['AcctAPDocument']
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    AcctAPMatchTolerance = models.get('AcctAPMatchTolerance')
    tol_amt = 1.0
    tol_pct = 5.0
    if AcctAPMatchTolerance:
        t = AcctAPMatchTolerance.query.filter_by(ledger_id=ledger_id).first()
        if t:
            tol_amt = float(t.amount_tolerance or 1.0)
            tol_pct = float(t.percent_tolerance or 5.0)
    doc = AcctAPDocument.query.filter_by(id=int(invoice_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Invoice not found')
    po = None
    if doc.purchase_order_id:
        po = AcctPurchaseOrder.query.get(doc.purchase_order_id)
    elif doc.po_reference:
        po = AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id, po_number=doc.po_reference).first()
    if not po:
        return {
            'matched': False,
            'status': 'no_po',
            'message': 'No purchase order linked',
            'invoice_id': doc.id,
        }
    po_lines = _parse_lines(po.lines_json)
    po_total = float(po.total_amount or 0)
    inv_amt = float(doc.gross_amount or doc.amount or 0)
    qty_ok = True
    for pl in po_lines:
        ordered = float(pl.get('qty') or pl.get('quantity') or 0)
        received = float(pl.get('qty_received') or 0)
        if ordered > 0 and received < ordered * 0.99:
            qty_ok = False
    amount_ok = po_total <= 0 or abs(inv_amt - po_total) <= max(tol_amt, po_total * tol_pct / 100.0)
    matched = qty_ok and amount_ok
    return {
        'matched': matched,
        'status': 'matched' if matched else 'exception',
        'invoice_id': doc.id,
        'purchase_order_id': po.id,
        'po_number': po.po_number,
        'po_total': po_total,
        'invoice_amount': inv_amt,
        'qty_received_ok': qty_ok,
        'amount_within_tolerance': amount_ok,
        'tolerance': {'amount': tol_amt, 'percent': tol_pct},
        'lines': po_lines,
    }


def report_1099(db, models, ledger_id, tax_year):
    AcctVendor = models['AcctVendor']
    AcctAPPayment = models['AcctAPPayment']
    year = int(tax_year)
    vendors = AcctVendor.query.filter_by(ledger_id=ledger_id, is_1099=True).all()
    rows = []
    for v in vendors:
        payments = AcctAPPayment.query.filter_by(ledger_id=ledger_id, vendor_id=v.id, status='Posted').all()
        total = 0.0
        for p in payments:
            if p.payment_date and p.payment_date.year == year:
                total += float(p.amount or 0)
        if total >= 600 or total > 0:
            rows.append({
                'vendor_id': v.id,
                'vendor_code': v.code,
                'vendor_name': v.name,
                'tax_id': v.tax_id or '',
                'form_type': v.form_1099_type or 'NEC',
                'payments': round(total, 2),
            })
    return {'tax_year': year, 'vendors': rows}


def void_ap_payment(db, models, payment, reason='', user_id=None):
    if payment.status == 'Void':
        raise ValueError('Payment already voided')
    from accounting_posting import load_accounting_options, _account_by_number
    from accounting_persistence import next_batch_number, post_journal_batch
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctAPPaymentApply = models['AcctAPPaymentApply']
    AcctAPDocument = models['AcctAPDocument']
    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(payment.ledger_id)
    amt = float(payment.amount or 0)
    applies = AcctAPPaymentApply.query.filter_by(payment_id=payment.id).all()
    for app in applies:
        doc = AcctAPDocument.query.get(app.ap_document_id)
        if doc:
            doc.amount_paid = round(max(0, float(doc.amount_paid or 0) - float(app.amount or 0)), 2)
            if doc.amount_paid <= 0.01:
                doc.status = 'Open'
            else:
                doc.status = 'Partial'
    ap_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts['ap_account'])
    cash_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts['cash_account'])
    batch = AcctJournalBatch(
        ledger_id=payment.ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, payment.ledger_id),
        source='AP-VOID',
        description=f'Void payment {payment.payment_number}'[:300],
        batch_date=date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=1, account_id=cash_acct.id,
        description='Payment void', debit=amt, credit=0,
    ))
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=2, account_id=ap_acct.id,
        description='Payment void', debit=0, credit=amt,
    ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
    payment.status = 'Void'
    payment.void_reason = (reason or '')[:200]
    payment.voided_at = datetime.utcnow()
    db.session.flush()
    return {'payment_id': payment.id, 'reversal_batch_id': batch.id}


def vendor_activity_detail(db, models, ledger_id, vendor_id):
    from accounting_persistence import serialize_ap_doc
    AcctVendor = models['AcctVendor']
    AcctAPDocument = models['AcctAPDocument']
    AcctAPPayment = models['AcctAPPayment']
    AcctAPPaymentApply = models['AcctAPPaymentApply']
    v = AcctVendor.query.filter_by(id=int(vendor_id), ledger_id=ledger_id).first()
    if not v:
        raise ValueError('Vendor not found')
    invoices = [serialize_ap_doc(d) for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, vendor_id=v.id).order_by(AcctAPDocument.document_date.desc()).limit(100).all()]
    payments = []
    for p in AcctAPPayment.query.filter_by(ledger_id=ledger_id, vendor_id=v.id).order_by(AcctAPPayment.id.desc()).limit(50).all():
        apps = AcctAPPaymentApply.query.filter_by(payment_id=p.id).all()
        payments.append({
            'id': p.id,
            'payment_number': p.payment_number,
            'payment_date': p.payment_date.isoformat() if p.payment_date else None,
            'amount': p.amount,
            'status': p.status,
            'applications': [{'ap_document_id': a.ap_document_id, 'amount': a.amount} for a in apps],
        })
    return {'vendor': serialize_vendor_extended(v), 'invoices': invoices, 'payments': payments}


def nacha_ach_file(db, models, ledger_id, payment_ids, *, company_name='CASE PM', company_id='1234567890', dest_routing='021000021', dest_account='123456789'):
    """Generate simplified NACHA-style ACH credit file for AP payments."""
    AcctAPPayment = models['AcctAPPayment']
    AcctVendor = models['AcctVendor']
    lines = []
    lines.append(
        '101' + dest_routing[:9].ljust(9) + company_id[:10].ljust(10)
        + datetime.utcnow().strftime('%y%m%d%H%M') + '094101' + dest_routing[:8].ljust(8) + company_name[:23].ljust(23)
    )
    lines.append(
        '5200' + company_name[:16].ljust(16) + ' ' * 20 + company_id[:10].ljust(10) + 'PPD' + 'VENDOR PAY'.ljust(10)
        + datetime.utcnow().strftime('%y%m%d') + datetime.utcnow().strftime('%y%m%d') + '   1' + dest_routing[:8] + '0000001'
    )
    entry = 0
    total = 0
    for pid in payment_ids:
        p = AcctAPPayment.query.filter_by(id=int(pid), ledger_id=ledger_id, status='Posted').first()
        if not p:
            continue
        v = AcctVendor.query.get(p.vendor_id)
        entry += 1
        cents = int(round(float(p.amount or 0) * 100))
        total += cents
        name = (v.name if v else 'Vendor')[:22].ljust(22)
        trace = (v.code[:15] if v else 'VENDOR').ljust(15)
        lines.append(
            '622' + dest_routing[:8] + '0' + dest_account[:17].ljust(17) + f'{cents:010d}'
            + p.payment_number[:15].ljust(15) + name + '  0' + trace
        )
    if entry == 0:
        raise ValueError('No posted payments selected')
    lines.append(
        '820' + f'{entry:06d}' + f'{entry:06d}' + f'{total:012d}' + f'{total:012d}'
        + company_id[:10].ljust(10) + ' ' * 25 + dest_routing[:8] + '0000001'
    )
    lines.append('9000001' + f'{entry + 2:06d}' + f'{entry:06d}' + f'{total:012d}' + f'{total:012d}' + ' ' * 39)
    return '\n'.join(lines)


def get_match_tolerance(models, ledger_id):
    AcctAPMatchTolerance = models['AcctAPMatchTolerance']
    t = AcctAPMatchTolerance.query.filter_by(ledger_id=ledger_id).first()
    if not t:
        return {'amount_tolerance': 1.0, 'percent_tolerance': 5.0}
    return {'amount_tolerance': float(t.amount_tolerance or 1), 'percent_tolerance': float(t.percent_tolerance or 5)}


def set_match_tolerance(db, models, ledger_id, body):
    AcctAPMatchTolerance = models['AcctAPMatchTolerance']
    t = AcctAPMatchTolerance.query.filter_by(ledger_id=ledger_id).first()
    if not t:
        t = AcctAPMatchTolerance(ledger_id=ledger_id)
        db.session.add(t)
    if 'amount_tolerance' in body:
        t.amount_tolerance = max(0, float(body['amount_tolerance'] or 0))
    if 'percent_tolerance' in body:
        t.percent_tolerance = max(0, float(body['percent_tolerance'] or 0))
    db.session.flush()
    return t


def release_retainage(db, models, ledger_id, invoice_id, amount, user_id=None):
    """Release retainage on AP invoice — increases payable amount."""
    AcctAPDocument = models['AcctAPDocument']
    doc = AcctAPDocument.query.filter_by(id=int(invoice_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Invoice not found')
    amt = round(float(amount or 0), 2)
    retain = float(doc.retainage_amount or 0)
    if amt <= 0 or amt > retain + 0.01:
        raise ValueError('Invalid retainage release amount')
    doc.retainage_amount = round(retain - amt, 2)
    doc.amount = round(float(doc.amount or 0) + amt, 2)
    try:
        meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        meta = {}
    meta.setdefault('retainage_releases', []).append({
        'amount': amt, 'date': date.today().isoformat(), 'user_id': user_id,
    })
    doc.details_json = json.dumps(meta)
    db.session.flush()
    return {'invoice_id': doc.id, 'released': amt, 'retainage_remaining': doc.retainage_amount}


def apply_payment_discount(db, models, payment, discount_amount, user_id=None):
    """Record early-payment discount on AP payment (reduces cash, posts to discount account)."""
    from accounting_posting import load_accounting_options, _account_by_number
    from accounting_persistence import next_batch_number, post_journal_batch
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctLedger = models['AcctLedger']
    disc = round(float(discount_amount or 0), 2)
    if disc <= 0:
        raise ValueError('discount_amount required')
    opts = load_accounting_options()
    ledger = AcctLedger.query.get(payment.ledger_id)
    ap_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts['ap_account'])
    cash_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts['cash_account'])
    disc_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts.get('purchase_discount_account') or '5090')
    pay_amt = float(payment.amount or 0)
    batch = AcctJournalBatch(
        ledger_id=payment.ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, payment.ledger_id),
        source='AP-DISC',
        description=f'Payment discount {payment.payment_number}'[:300],
        batch_date=payment.payment_date or date.today(),
        status='Open',
    )
    db.session.add(batch)
    db.session.flush()
    db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=ap_acct.id, debit=pay_amt, credit=0, description='Payment'))
    db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=disc_acct.id, debit=0, credit=disc, description='Discount'))
    db.session.add(AcctJournalLine(batch_id=batch.id, line_number=3, account_id=cash_acct.id, debit=0, credit=round(pay_amt - disc, 2), description='Cash'))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
    return {'discount_batch_id': batch.id, 'discount': disc}


def export_1099_efile(db, models, ledger_id, tax_year):
    """IRS FIRE–style transmission file plus JSON summary."""
    from accounting_gl_ap_ar_complete import export_1099_fire_transmission

    content = export_1099_fire_transmission(db, models, ledger_id, tax_year)
    data = report_1099(db, models, ledger_id, tax_year)
    return {
        'tax_year': int(tax_year),
        'format': 'fire_fixed_width',
        'content': content,
        'vendor_count': len(data.get('vendors') or []),
        'vendors': data.get('vendors') or [],
    }


def report_1099_printable_html(db, models, ledger_id, tax_year):
    data = report_1099(db, models, ledger_id, tax_year)
    rows = ''.join(
        f'<tr><td>{v.get("vendor_code", "")}</td><td>{v.get("vendor_name", "")}</td>'
        f'<td>{v.get("tax_id", "")}</td><td>{v.get("form_type", "NEC")}</td>'
        f'<td style="text-align:right">{v.get("payments", 0):,.2f}</td></tr>'
        for v in data.get('vendors') or []
    )
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>1099 {tax_year}</title>
    <style>table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ccc;padding:6px;font-size:12px}}</style></head>
    <body><h1>Form 1099 summary — {tax_year}</h1>
    <table><thead><tr><th>Code</th><th>Vendor</th><th>Tax ID</th><th>Form</th><th>Payments</th></tr></thead>
    <tbody>{rows or "<tr><td colspan=5>None</td></tr>"}</tbody></table>
    <script>window.onload=function(){{window.print()}}</script></body></html>'''


def parse_payment_terms_discount(terms):
    """Parse 2/10 net 30 style terms -> discount percent and days."""
    t = (terms or '').lower().replace(' ', '')
    if '/' not in t:
        return None
    try:
        disc_part, rest = t.split('/', 1)
        pct = float(disc_part)
        days = 10
        if 'net' in rest:
            import re
            m = re.search(r'(\d+)', rest)
            if m:
                days = int(m.group(1))
        return {'discount_percent': pct, 'discount_days': min(days, 30)}
    except (TypeError, ValueError):
        return None


def compute_withholding_for_invoice(db, models, ledger_id, vendor_id, gross):
    AcctWithholdingRule = models['AcctWithholdingRule']
    AcctVendor = models['AcctVendor']
    v = AcctVendor.query.filter_by(id=int(vendor_id), ledger_id=ledger_id).first()
    gross = float(gross or 0)
    pct = float(v.default_withhold_percent or 0) if v else 0
    rules = AcctWithholdingRule.query.filter_by(ledger_id=ledger_id, is_active=True).all()
    for r in rules:
        if v and r.vendor_group_id and v.vendor_group_id == r.vendor_group_id:
            pct = max(pct, float(r.withhold_percent or 0))
        elif not r.vendor_group_id:
            pct = max(pct, float(r.withhold_percent or 0))
    threshold = 0.0
    for r in rules:
        threshold = max(threshold, float(r.threshold_amount or 0))
    if threshold and gross < threshold:
        return {'withhold_percent': 0, 'withhold_amount': 0}
    amt = round(gross * pct / 100.0, 2)
    return {'withhold_percent': pct, 'withhold_amount': amt}


def serialize_withholding_rule(r):
    return {
        'id': r.id, 'name': r.name, 'vendor_group_id': r.vendor_group_id,
        'withhold_percent': r.withhold_percent, 'threshold_amount': r.threshold_amount,
        'is_active': r.is_active,
    }


def upsert_withholding_rule(db, models, ledger_id, body, rule_id=None):
    AcctWithholdingRule = models['AcctWithholdingRule']
    if rule_id:
        r = AcctWithholdingRule.query.filter_by(id=int(rule_id), ledger_id=ledger_id).first()
        if not r:
            raise ValueError('Rule not found')
    else:
        r = AcctWithholdingRule(ledger_id=ledger_id, name=(body.get('name') or 'Rule')[:80])
        db.session.add(r)
    r.name = (body.get('name') or r.name)[:80]
    r.vendor_group_id = int(body['vendor_group_id']) if body.get('vendor_group_id') else None
    r.withhold_percent = float(body.get('withhold_percent') or r.withhold_percent or 0)
    r.threshold_amount = float(body.get('threshold_amount') or 0)
    if 'is_active' in body:
        r.is_active = bool(body['is_active'])
    db.session.flush()
    return r


def ap_match_workbench(db, models, ledger_id):
    AcctAPDocument = models['AcctAPDocument']
    AcctVendor = models['AcctVendor']
    rows = []
    for doc in AcctAPDocument.query.filter_by(ledger_id=ledger_id, document_type='Invoice').filter(
        AcctAPDocument.status.in_(['Open', 'Partial'])
    ).limit(200).all():
        m = three_way_match(db, models, ledger_id, doc.id)
        v = AcctVendor.query.get(doc.vendor_id)
        rows.append({
            'invoice_id': doc.id,
            'document_number': doc.document_number,
            'vendor_code': v.code if v else '',
            'amount': doc.amount,
            **m,
        })
    return {'exceptions': [r for r in rows if not r.get('matched')], 'all': rows}
