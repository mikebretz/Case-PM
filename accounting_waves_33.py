"""
Waves 57–60 — Distribution & inventory: PO, IC, OE, 3-way match v2.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import SAGE_MIRROR_CAPABILITIES, _ledger_settings, _save_ledger_settings, sage_sync_get
from accounting_waves_28 import load_fixture_row
from accounting_waves_29 import sage_pull_po_statuses, po_three_way_sage_summary


# --- Wave 57: PO depth ---

def po_standing_blanket_summary(db, models, ledger_id: int, limit: int = 50) -> dict:
    from accounting_ap_extended import _parse_lines

    AcctPurchaseOrder = models['AcctPurchaseOrder']
    standing = blanket = open_po = 0
    rows = []
    for po in AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id).order_by(AcctPurchaseOrder.id.desc()).limit(limit).all():
        meta = _parse_lines(po.lines_json)
        po_type = (getattr(po, 'po_type', None) or '').lower()
        if 'standing' in po_type:
            standing += 1
        if 'blanket' in po_type:
            blanket += 1
        if (po.status or 'Open') == 'Open':
            open_po += 1
        rows.append({
            'id': po.id,
            'po_number': po.po_number,
            'status': po.status,
            'total': float(po.total_amount or 0),
            'line_count': len(meta),
            'sage_sync': None,
        })
    return {'standing': standing, 'blanket': blanket, 'open': open_po, 'orders': rows[:25]}


def commitment_po_line_sync_summary(db, models, ledger_id: int, Commitment=None, limit: int = 30) -> dict:
    if not Commitment:
        return {'linked': 0, 'rows': []}
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    rows = []
    for c in Commitment.query.limit(limit).all():
        po = None
        ref = getattr(c, 'po_number', None) or getattr(c, 'commitment_number', None)
        if ref:
            po = AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id, po_number=str(ref)[:40]).first()
        rows.append({
            'commitment_id': c.id,
            'po_id': po.id if po else None,
            'po_number': po.po_number if po else ref,
            'matched': po is not None,
        })
    return {'linked': sum(1 for r in rows if r['matched']), 'rows': rows}


def sage_pull_po_receipt_lines(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    from sage300_web_client import get_resource
    from accounting_waves_24 import sage_write_guard

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'po', 'pull')
    resp = get_resource('PO', 'POReceipts', top=limit)
    if not resp.get('ok'):
        return {'lines': 0, 'mode': resp.get('mode')}
    lines = []
    for row in (resp.get('data') or {}).get('value') or []:
        lines.append({
            'po': row.get('PONumber'),
            'receipt': row.get('ReceiptNumber'),
            'item': row.get('ItemNumber'),
            'qty': row.get('QuantityReceived'),
        })
    settings['sage_po_receipt_lines'] = lines[-100:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_po_receipts', details={'lines': len(lines)})
    return {'lines': len(lines), 'mode': resp.get('mode'), 'sample': lines[:5]}


# --- Wave 58: IC serial/lot ---

def ic_serial_lot_register(db, models, ledger_id: int, item_number: str, serials: list, user_id=None) -> dict:
    AcctInventoryItem = models.get('AcctInventoryItem')
    if not AcctInventoryItem:
        return {'skipped': True}
    item = AcctInventoryItem.query.filter_by(ledger_id=ledger_id, item_number=item_number[:40]).first()
    if not item:
        raise ValueError('Item not found')
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.setdefault('ic_serial_lot', {})
    reg[item_number[:40]] = serials[:200]
    settings['ic_serial_lot'] = reg
    _save_ledger_settings(ledger, settings)
    if serials:
        item.track_lot_serial = 1
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='ic_serial_lot', details={'item': item_number, 'count': len(serials)})
    return {'item_number': item_number, 'serial_lot_count': len(serials)}


def ic_qty_cost_refresh_summary(db, models, ledger_id: int) -> dict:
    from accounting_waves_29 import sage_pull_distribution_inventory_status

    pull = sage_pull_distribution_inventory_status(db, models, ledger_id)
    AcctInventoryItem = models.get('AcctInventoryItem')
    count = AcctInventoryItem.query.filter_by(ledger_id=ledger_id).count() if AcctInventoryItem else 0
    return {'item_count': count, 'pull': pull}


# --- Wave 59: OE chain ---

def oe_order_chain_status(db, models, ledger_id: int, limit: int = 40) -> dict:
    AcctSalesOrder = models.get('AcctSalesOrder')
    if not AcctSalesOrder:
        return {'orders': []}
    chain = []
    for so in AcctSalesOrder.query.filter_by(ledger_id=ledger_id).order_by(AcctSalesOrder.id.desc()).limit(limit).all():
        meta = json.loads(so.details_json or '{}') if getattr(so, 'details_json', None) else {}
        chain.append({
            'order_number': so.order_number,
            'status': so.status,
            'total': float(so.total_amount or 0),
            'shipped': meta.get('shipped', False),
            'invoiced': meta.get('invoiced', False),
        })
    return {'orders': chain, 'open': sum(1 for o in chain if (o.get('status') or '') == 'Open')}


def oe_commission_export_queue(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    box = oe_order_chain_status(db, models, ledger_id)
    q = settings.get('sage_oe_commission_queue') or []
    for o in box.get('orders') or []:
        if o.get('invoiced'):
            q.append({'order': o.get('order_number'), 'total': o.get('total'), 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_oe_commission_queue'] = q[-50:]
    _save_ledger_settings(ledger, settings)
    return {'queued': len(q), 'queue': q[-10:]}


# --- Wave 60: 3-way match v2 ---

def three_way_match_line_grid(db, models, ledger_id: int, invoice_id: int) -> dict:
    from accounting_ap_extended import three_way_match, _parse_lines

    base = three_way_match(db, models, ledger_id, invoice_id)
    AcctAPDocument = models['AcctAPDocument']
    doc = AcctAPDocument.query.filter_by(id=int(invoice_id), ledger_id=ledger_id).first()
    inv_lines = _parse_lines(doc.lines_json) if doc and doc.lines_json else []
    po_lines = []
    if base.get('purchase_order_id'):
        po = models['AcctPurchaseOrder'].query.get(base['purchase_order_id'])
        if po:
            po_lines = _parse_lines(po.lines_json)
    grid = []
    for i, il in enumerate(inv_lines[:50]):
        pl = po_lines[i] if i < len(po_lines) else {}
        grid.append({
            'line': i + 1,
            'invoice_qty': il.get('qty') or il.get('quantity'),
            'invoice_amount': il.get('amount'),
            'po_qty': pl.get('qty') or pl.get('quantity'),
            'po_received': pl.get('qty_received'),
            'po_amount': pl.get('amount'),
        })
    return {**base, 'line_grid': grid, 'line_count': len(grid)}


def three_way_vendor_tolerance_report(db, models, ledger_id: int, limit: int = 25) -> dict:
    summary = po_three_way_sage_summary(db, models, ledger_id, limit=limit)
    AcctAPMatchTolerance = models.get('AcctAPMatchTolerance')
    tol = None
    if AcctAPMatchTolerance:
        tol = AcctAPMatchTolerance.query.filter_by(ledger_id=ledger_id).first()
    return {
        **summary,
        'amount_tolerance': float(tol.amount_tolerance or 1) if tol else 1.0,
        'percent_tolerance': float(tol.percent_tolerance or 5) if tol else 5.0,
    }


def validate_po_receipt_fixture() -> dict:
    data = load_fixture_row('po_receipt_line_sample.json')
    rows = data.get('value') or []
    if not rows:
        return {'ok': False}
    row = rows[0]
    ok = bool(row.get('PONumber') and row.get('QuantityReceived') is not None)
    return {'ok': ok, 'po': row.get('PONumber')}


def update_mirror_capabilities_wave_57_60() -> None:
    SAGE_MIRROR_CAPABILITIES['pj'] = {
        **SAGE_MIRROR_CAPABILITIES.get('pj', {}),
        'push': True,
        'notes': 'CRE PJ mirror queue + portfolio variance',
    }


update_mirror_capabilities_wave_57_60()


def cron_waves_57_60_maintenance(db, models, secret: str, Commitment=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    runs = []
    for ledger in AcctLedger.query.limit(5).all():
        runs.append({
            'ledger_id': ledger.id,
            'po_pull': sage_pull_po_statuses(db, models, ledger.id),
            'po_receipts': sage_pull_po_receipt_lines(db, models, ledger.id),
            'ic': ic_qty_cost_refresh_summary(db, models, ledger.id),
            'three_way': three_way_vendor_tolerance_report(db, models, ledger.id),
            'commitment': commitment_po_line_sync_summary(db, models, ledger.id, Commitment=Commitment),
        })
    return {'ledgers': runs}


def cron_waves_53_60_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None, Commitment=None) -> dict:
    from accounting_waves_31 import cron_waves_45_48_maintenance

    bank = cron_waves_45_48_maintenance(db, models, secret, Project=Project)
    from accounting_waves_32 import cron_waves_53_56_maintenance

    cre = cron_waves_53_56_maintenance(db, models, secret, Project=Project, PayAppProjectState=PayAppProjectState)
    dist = cron_waves_57_60_maintenance(db, models, secret, Commitment=Commitment)
    return {'bank_cash': bank, 'cre': cre, 'distribution': dist, 'deploy_v8': sage_mirror_deploy_check_v8()}


def sage_mirror_deploy_check_v8() -> dict:
    from accounting_waves_31 import sage_mirror_deploy_check_v7
    from accounting_waves_32 import validate_g702_lifecycle_fixture

    base = sage_mirror_deploy_check_v7()
    g702 = validate_g702_lifecycle_fixture()
    po = validate_po_receipt_fixture()
    ok = base.get('ok') and g702.get('ok') and po.get('ok')
    return {'ok': ok, 'v7': base, 'g702_fixture': g702, 'po_receipt_fixture': po}
