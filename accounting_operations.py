"""Operational workflows for Tax, Fixed Assets, Inventory, PO, and OE modules."""
from __future__ import annotations

import json
from datetime import date


def _parse_lines(lines_json):
    if not lines_json:
        return []
    try:
        data = json.loads(lines_json)
        return data if isinstance(data, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _save_lines(lines):
    return json.dumps(lines or [])


def serialize_tax_group(g):
    return {
        'id': g.id,
        'code': g.code,
        'description': g.description,
        'rate_percent': float(g.rate_percent or 0),
        'authority': g.authority or '',
        'tax_type': getattr(g, 'tax_type', None) or 'sales',
        'applies_to': getattr(g, 'applies_to', None) or 'both',
        'is_active': bool(getattr(g, 'is_active', True)),
    }


def serialize_asset(a):
    cost = float(a.acquisition_cost or 0)
    accum = float(a.accumulated_depreciation or 0)
    salvage = float(getattr(a, 'salvage_value', 0) or 0)
    return {
        'id': a.id,
        'asset_number': a.asset_number,
        'description': a.description or '',
        'acquisition_date': a.acquisition_date.isoformat() if a.acquisition_date else None,
        'acquisition_cost': cost,
        'accumulated_depreciation': accum,
        'net_book_value': round(max(cost - accum, 0), 2),
        'salvage_value': salvage,
        'useful_life_months': int(a.useful_life_months or 60),
        'depreciation_method': a.depreciation_method or 'straight_line',
        'monthly_depreciation': round((cost - salvage) / max(int(a.useful_life_months or 60), 1), 2),
        'book': a.book or 'GAAP',
        'status': a.status,
        'location': getattr(a, 'location', None) or '',
        'serial_number': getattr(a, 'serial_number', None) or '',
        'in_service_date': a.in_service_date.isoformat() if getattr(a, 'in_service_date', None) else None,
    }


def serialize_po(o, vendors=None):
    vendors = vendors or {}
    vname = ''
    if o.vendor_id and vendors.get(o.vendor_id):
        vname = vendors[o.vendor_id]
    lines = _parse_lines(o.lines_json)
    return {
        'id': o.id,
        'po_number': o.po_number,
        'status': o.status,
        'vendor_id': o.vendor_id,
        'vendor_name': vname,
        'total_amount': float(o.total_amount or 0),
        'project_id': o.project_id,
        'order_date': o.order_date.isoformat() if o.order_date else None,
        'lines': lines,
        'qty_received': sum(float(ln.get('qty_received') or 0) for ln in lines),
        'qty_ordered': sum(float(ln.get('qty') or 0) for ln in lines),
    }


def serialize_oe(o, customers=None):
    customers = customers or {}
    cname = ''
    if o.customer_id and customers.get(o.customer_id):
        cname = customers[o.customer_id]
    lines = _parse_lines(o.lines_json)
    return {
        'id': o.id,
        'order_number': o.order_number,
        'status': o.status,
        'customer_id': o.customer_id,
        'customer_name': cname,
        'total_amount': float(o.total_amount or 0),
        'project_id': o.project_id,
        'order_date': o.order_date.isoformat() if o.order_date else None,
        'lines': lines,
        'qty_shipped': sum(float(ln.get('qty_shipped') or 0) for ln in lines),
    }


def serialize_inventory_item(i):
    ext = float(i.qty_on_hand or 0) * float(i.unit_cost or 0)
    return {
        'id': i.id,
        'item_number': i.item_number,
        'description': i.description,
        'uom': i.uom or 'EA',
        'qty_on_hand': float(i.qty_on_hand or 0),
        'unit_cost': float(i.unit_cost or 0),
        'extended_value': round(ext, 2),
        'status': i.status,
    }


def calculate_tax(db, models, ledger_id, *, amount, tax_group_code=None, tax_group_id=None):
    AcctTaxGroup = models['AcctTaxGroup']
    g = None
    if tax_group_id:
        g = AcctTaxGroup.query.filter_by(ledger_id=ledger_id, id=tax_group_id).first()
    elif tax_group_code:
        g = AcctTaxGroup.query.filter_by(ledger_id=ledger_id, code=tax_group_code.strip()).first()
    if not g or not getattr(g, 'is_active', True):
        return {'taxable': float(amount or 0), 'tax_amount': 0.0, 'total': float(amount or 0), 'rate_percent': 0}
    rate = float(g.rate_percent or 0)
    taxable = float(amount or 0)
    tax_amt = round(taxable * rate / 100.0, 2)
    return {
        'tax_group': serialize_tax_group(g),
        'taxable': taxable,
        'tax_amount': tax_amt,
        'total': round(taxable + tax_amt, 2),
        'rate_percent': rate,
    }


def tax_liability_summary(db, models, ledger_id):
    """Estimate tax exposure from vendor/customer tax group assignments (informational)."""
    AcctTaxGroup = models['AcctTaxGroup']
    AcctVendor = models['AcctVendor']
    AcctAPDocument = models['AcctAPDocument']
    groups = {g.code: serialize_tax_group(g) for g in AcctTaxGroup.query.filter_by(ledger_id=ledger_id).all()}
    ap_open = 0.0
    for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id).filter(
        AcctAPDocument.status.in_(['Open', 'Partial'])
    ).all():
        ap_open += float(d.amount or 0) - float(d.amount_paid or 0)
    vendor_groups = {}
    for v in AcctVendor.query.filter_by(ledger_id=ledger_id).all():
        if v.tax_group:
            vendor_groups[v.tax_group] = vendor_groups.get(v.tax_group, 0) + 1
    return {
        'tax_groups': list(groups.values()),
        'open_ap_base': round(ap_open, 2),
        'vendors_by_tax_group': vendor_groups,
    }


def record_inventory_movement(db, models, ledger_id, item_id, *, qty_delta, txn_type='adjust', unit_cost=None, reference='', project_id=None):
    AcctInventoryItem = models['AcctInventoryItem']
    AcctInventoryTransaction = models['AcctInventoryTransaction']
    item = AcctInventoryItem.query.get(item_id)
    if not item or item.ledger_id != ledger_id:
        raise ValueError('Item not found')
    new_qty = float(item.qty_on_hand or 0) + float(qty_delta)
    if new_qty < -0.0001:
        raise ValueError('Insufficient quantity on hand')
    if unit_cost is not None:
        item.unit_cost = float(unit_cost)
    item.qty_on_hand = new_qty
    txn = AcctInventoryTransaction(
        ledger_id=ledger_id,
        item_id=item.id,
        txn_type=txn_type,
        qty_delta=float(qty_delta),
        unit_cost=float(item.unit_cost or 0),
        reference=(reference or '')[:80],
        project_id=project_id,
    )
    db.session.add(txn)
    db.session.flush()
    return {'item': serialize_inventory_item(item), 'transaction_id': txn.id}


def po_recompute_total(lines):
    total = 0.0
    for ln in lines:
        qty = float(ln.get('qty') or 0)
        price = float(ln.get('unit_price') or 0)
        ln['line_total'] = round(qty * price, 2)
        total += ln['line_total']
    return round(total, 2)


def receive_purchase_order(db, models, ledger_id, po_id, *, lines_received=None):
    """Mark PO lines received; optional inventory receipt by item_number."""
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    AcctInventoryItem = models['AcctInventoryItem']
    po = AcctPurchaseOrder.query.get(po_id)
    if not po or po.ledger_id != ledger_id:
        raise ValueError('PO not found')
    lines = _parse_lines(po.lines_json)
    if not lines:
        raise ValueError('PO has no lines to receive')
    received_map = {int(x['line_index']): float(x.get('qty', 0)) for x in (lines_received or []) if 'line_index' in x}
    for idx, ln in enumerate(lines):
        qty = received_map.get(idx)
        if qty is None:
            continue
        ordered = float(ln.get('qty') or 0)
        already = float(ln.get('qty_received') or 0)
        add = min(qty, max(ordered - already, 0))
        if add <= 0:
            continue
        ln['qty_received'] = round(already + add, 4)
        item_no = (ln.get('item_number') or '').strip()
        if item_no:
            item = AcctInventoryItem.query.filter_by(ledger_id=ledger_id, item_number=item_no).first()
            if item:
                record_inventory_movement(
                    db, models, ledger_id, item.id,
                    qty_delta=add, txn_type='po_receipt',
                    unit_cost=ln.get('unit_price'),
                    reference=po.po_number,
                    project_id=po.project_id,
                )
    po.lines_json = _save_lines(lines)
    all_done = all(float(ln.get('qty_received') or 0) >= float(ln.get('qty') or 0) - 0.0001 for ln in lines)
    if all_done:
        po.status = 'Received'
    else:
        po.status = 'Partial'
    db.session.flush()
    return serialize_po(po)


def ship_sales_order(db, models, ledger_id, order_id, *, lines_shipped=None):
    AcctSalesOrder = models['AcctSalesOrder']
    order = AcctSalesOrder.query.get(order_id)
    if not order or order.ledger_id != ledger_id:
        raise ValueError('Sales order not found')
    lines = _parse_lines(order.lines_json)
    if not lines:
        raise ValueError('Order has no lines')
    ship_map = {int(x['line_index']): float(x.get('qty', 0)) for x in (lines_shipped or []) if 'line_index' in x}
    for idx, ln in enumerate(lines):
        qty = ship_map.get(idx)
        if qty is None:
            continue
        ordered = float(ln.get('qty') or 0)
        already = float(ln.get('qty_shipped') or 0)
        add = min(qty, max(ordered - already, 0))
        if add <= 0:
            continue
        ln['qty_shipped'] = round(already + add, 4)
    order.lines_json = _save_lines(lines)
    all_done = all(float(ln.get('qty_shipped') or 0) >= float(ln.get('qty') or 0) - 0.0001 for ln in lines)
    order.status = 'Shipped' if all_done else 'Partial'
    db.session.flush()
    return serialize_oe(order)


def invoice_sales_order(db, models, ledger_id, order_id):
    from datetime import date as date_cls
    AcctSalesOrder = models['AcctSalesOrder']
    AcctARDocument = models['AcctARDocument']
    order = AcctSalesOrder.query.get(order_id)
    if not order or order.ledger_id != ledger_id:
        raise ValueError('Sales order not found')
    if not order.customer_id:
        raise ValueError('Sales order needs a customer')
    amount = float(order.total_amount or 0)
    if amount <= 0:
        lines = _parse_lines(order.lines_json)
        amount = po_recompute_total(lines)
        order.total_amount = amount
    inv = AcctARDocument(
        ledger_id=ledger_id,
        customer_id=order.customer_id,
        document_number=f'INV-{order.order_number}'[:40],
        document_date=date_cls.today(),
        due_date=date_cls.today(),
        amount=amount,
        status='Open',
        project_id=order.project_id,
    )
    db.session.add(inv)
    order.status = 'Invoiced'
    db.session.flush()
    return {'ar_document_id': inv.id, 'amount': amount, 'order': serialize_oe(order)}


def dispose_fixed_asset(db, models, ledger_id, asset_id, *, disposal_date=None, proceeds=0.0):
    from accounting_persistence import get_or_create_default_ledger
    from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options
    AcctFixedAsset = models['AcctFixedAsset']
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    asset = AcctFixedAsset.query.get(asset_id)
    if not asset or asset.ledger_id != ledger_id:
        raise ValueError('Asset not found')
    if asset.status == 'Disposed':
        raise ValueError('Asset already disposed')
    opts = load_accounting_options()
    ledger = get_or_create_default_ledger(db, AcctLedger)
    cost = float(asset.acquisition_cost or 0)
    accum = float(asset.accumulated_depreciation or 0)
    nbv = round(cost - accum, 2)
    proceeds = round(float(proceeds or 0), 2)
    equip = _account_by_number(AcctGLAccount, ledger.id, '1700')
    accum_acct = _account_by_number(AcctGLAccount, ledger.id, opts['accum_dep_account'])
    cash = _account_by_number(AcctGLAccount, ledger.id, opts['cash_account'])
    gain_loss = _account_by_number(AcctGLAccount, ledger.id, '6100') or _account_by_number(AcctGLAccount, ledger.id, '6000')
    lines = []
    if accum > 0:
        lines.append({'account_id': accum_acct.id, 'debit': accum, 'credit': 0, 'description': f'Dispose {asset.asset_number}'})
    if proceeds > 0:
        lines.append({'account_id': cash.id, 'debit': proceeds, 'credit': 0, 'description': 'Proceeds'})
    lines.append({'account_id': equip.id, 'debit': 0, 'credit': cost, 'description': 'Remove asset cost'})
    gl_diff = round(proceeds + accum - cost, 2)
    if gl_diff > 0:
        lines.append({'account_id': gain_loss.id, 'debit': 0, 'credit': gl_diff, 'description': 'Gain on disposal'})
    elif gl_diff < 0:
        lines.append({'account_id': gain_loss.id, 'debit': -gl_diff, 'credit': 0, 'description': 'Loss on disposal'})
    batch = _create_posted_batch(
        db, models, ledger_id=ledger.id, source='FA',
        description=f'Disposal {asset.asset_number}',
        lines=lines,
    )
    asset.status = 'Disposed'
    asset.accumulated_depreciation = cost
    db.session.flush()
    return {'journal_batch_id': batch.id, 'net_book_value': nbv, 'proceeds': proceeds, 'asset': serialize_asset(asset)}
