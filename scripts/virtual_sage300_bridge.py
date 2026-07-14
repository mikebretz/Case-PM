#!/usr/bin/env python3
"""
Virtual Sage 300 CRE bridge for Case PM integration testing.

Outbound (Case PM → Sage):
  POST /api/v1/transactions

Inbound (Sage → Case PM):
  GET  /api/v1/jobs/<job>/sub-payments
  GET  /api/v1/jobs/<job>/owner-billings
  GET  /api/v1/jobs/<job>/actuals
  GET  /api/v1/jobs/<job>/ledger
  GET  /api/v1/vendors
  GET  /api/v1/vendors/<code>
  GET  /api/v1/customers/<code>

Test helpers:
  GET  /api/v1/health
  GET  /api/v1/summary
  POST /api/v1/reset
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request

try:
    from sage_companies_service import SAGE_DEMO_DIRECTORY
except ImportError:
    SAGE_DEMO_DIRECTORY = []

API_KEY = os.environ.get('VIRTUAL_SAGE_API_KEY', 'virtual-sage-test-key').strip()
PORT = int(os.environ.get('VIRTUAL_SAGE_PORT', '8765'))

app = Flask(__name__)

STORE: dict = {
    'transactions': [],
    'vendors': {},
    'customers': {},
    'jobs': {},
}


def _auth_ok() -> bool:
    auth = (request.headers.get('Authorization') or '').strip()
    if not API_KEY:
        return True
    return auth == f'Bearer {API_KEY}'


def _seed_directory() -> None:
    for item in SAGE_DEMO_DIRECTORY:
        code = item.get('code', '')
        name = item.get('name', '')
        ctype = (item.get('company_type') or '').lower()
        entry = {
            'code': code,
            'name': name,
            'company_name': name,
            'company_type': item.get('company_type', 'Subcontractor'),
            'trade': item.get('trade', ''),
            'phone': item.get('phone', ''),
            'email': item.get('email', ''),
        }
        if 'client' in ctype or 'owner' in ctype:
            STORE['customers'][code] = entry
        else:
            STORE['vendors'][code] = entry


def _job_rec(job: str) -> dict:
    return STORE['jobs'].setdefault(job, {
        'job_number': job,
        'project_name': '',
        'budget_lines': [],
        'commitments': [],
        'change_orders': [],
        'pay_apps': [],
        'sub_payments': [],
        'owner_billings': [],
        'actuals_by_cost_code': defaultdict(float),
        'vendor_paid_totals': defaultdict(float),
        'modules_seen': set(),
    })


def _float_val(*candidates) -> float:
    for val in candidates:
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return 0.0


def _apply_transaction(payload: dict) -> dict:
    """Update virtual job ledger from a Case PM Sage payload."""
    project = payload.get('project') or {}
    job = (project.get('sage_job_number') or '').strip()
    if not job:
        return {}

    rec = _job_rec(job)
    if project.get('project_name'):
        rec['project_name'] = project.get('project_name')

    module = payload.get('sage_module') or ''
    action = payload.get('sage_action') or ''
    event_type = payload.get('event_type') or ''
    data = payload.get('data') or {}
    rec['modules_seen'].add(module)

    entry = {
        'event_type': event_type,
        'module': module,
        'action': action,
        'amount': _float_val(
            data.get('amount'), data.get('total_amount'), data.get('current_amount'), data.get('total'),
        ),
        'number': data.get('number') or data.get('commitment_number') or data.get('co_number'),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }

    if module == 'JobCost':
        rec['budget_lines'].append(entry)
        if event_type == 'AccountingReconciled':
            applied = _float_val(data.get('actual_cost_applied'), data.get('sync', {}).get('actual_cost_applied'))
            if applied:
                rec['actuals_by_cost_code']['__job_total__'] += applied
    elif module in ('AP', 'Subcontracts'):
        rec['commitments'].append(entry)
    elif module == 'PCO':
        rec['change_orders'].append(entry)
    elif module in ('ProgressBilling', 'SubcontractorBilling'):
        rec['pay_apps'].append(entry)

    if event_type == 'SubPayAppApproved':
        company_id = str(data.get('companyId') or data.get('company_id') or '')
        period = data.get('periodNumber') or data.get('period_number')
        amount = _float_val(data.get('total'), data.get('totalBilledThisPeriod'))
        pay = {
            'company_id': company_id,
            'period_number': period,
            'amount': amount,
            'event_type': event_type,
            'posted_at': entry['timestamp'],
        }
        rec['sub_payments'].append(pay)
        if company_id:
            rec['vendor_paid_totals'][company_id] += amount
        for alloc in data.get('allocations') or []:
            code = alloc.get('cost_code') or alloc.get('costCode')
            if code:
                rec['actuals_by_cost_code'][code] += _float_val(alloc.get('amount'))

    if event_type == 'SubPayAppSubmitted':
        amount = _float_val(data.get('total'), data.get('totalBilledThisPeriod'))
        if amount and not rec['sub_payments']:
            pass

    if event_type == 'G702Approved':
        amount = _float_val(data.get('amount_due'), data.get('total'), data.get('billing_total'))
        rec['owner_billings'].append({
            'period_number': data.get('periodNumber') or data.get('period_number'),
            'amount': amount,
            'event_type': event_type,
            'posted_at': entry['timestamp'],
        })

    if event_type == 'CommitmentApproved':
        for alloc in data.get('allocations') or []:
            code = alloc.get('cost_code')
            if code:
                rec['actuals_by_cost_code'].setdefault(code, 0.0)

    return {'job': job, 'module': module, 'action': action, 'event_type': event_type}


def _job_ledger_response(job: str) -> dict:
    rec = STORE['jobs'].get(job)
    if not rec:
        return {'job_number': job, 'found': False}
    actuals = dict(rec.get('actuals_by_cost_code') or {})
    if isinstance(actuals, defaultdict):
        actuals = dict(actuals)
    return {
        'job_number': job,
        'found': True,
        'project_name': rec.get('project_name', ''),
        'modules_seen': sorted(rec.get('modules_seen') or []),
        'sub_payments': list(rec.get('sub_payments') or []),
        'owner_billings': list(rec.get('owner_billings') or []),
        'actuals_by_cost_code': actuals,
        'vendor_paid_totals': dict(rec.get('vendor_paid_totals') or {}),
        'commitment_posts': len(rec.get('commitments') or []),
        'change_order_posts': len(rec.get('change_orders') or []),
        'pay_app_posts': len(rec.get('pay_apps') or []),
        'budget_posts': len(rec.get('budget_lines') or []),
        'transaction_count': sum(
            1 for t in STORE['transactions']
            if ((t.get('payload') or {}).get('project') or {}).get('sage_job_number') == job
        ),
    }


@app.route('/api/v1/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'virtual-sage-300-cre',
        'transactions': len(STORE['transactions']),
        'jobs': len(STORE['jobs']),
    })


@app.route('/api/v1/reset', methods=['POST'])
def reset():
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    STORE['transactions'] = []
    STORE['jobs'] = {}
    _seed_directory()
    return jsonify({'status': 'reset'})


@app.route('/api/v1/summary')
def summary():
    by_module: dict[str, int] = {}
    by_event: dict[str, int] = {}
    by_job: dict[str, int] = {}
    for txn in STORE['transactions']:
        payload = txn.get('payload') or {}
        mod = payload.get('sage_module') or 'Unknown'
        evt = payload.get('event_type') or 'Unknown'
        job = (payload.get('project') or {}).get('sage_job_number') or '—'
        by_module[mod] = by_module.get(mod, 0) + 1
        by_event[evt] = by_event.get(evt, 0) + 1
        by_job[job] = by_job.get(job, 0) + 1

    jobs_summary = {}
    for job_num, rec in STORE['jobs'].items():
        jobs_summary[job_num] = {
            'project_name': rec.get('project_name', ''),
            'modules_seen': sorted(rec.get('modules_seen') or []),
            'budget_posts': len(rec.get('budget_lines') or []),
            'commitment_posts': len(rec.get('commitments') or []),
            'change_order_posts': len(rec.get('change_orders') or []),
            'pay_app_posts': len(rec.get('pay_apps') or []),
            'sub_payments': len(rec.get('sub_payments') or []),
            'owner_billings': len(rec.get('owner_billings') or []),
        }

    return jsonify({
        'transaction_count': len(STORE['transactions']),
        'by_module': by_module,
        'by_event_type': by_event,
        'by_job': by_job,
        'jobs': jobs_summary,
    })


@app.route('/api/v1/jobs/<job>/ledger')
def job_ledger(job):
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify(_job_ledger_response(job))


@app.route('/api/v1/jobs/<job>/sub-payments')
def job_sub_payments(job):
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    ledger = _job_ledger_response(job)
    if not ledger.get('found'):
        return jsonify({'job_number': job, 'payments': [], 'vendor_totals': {}}), 404
    return jsonify({
        'job_number': job,
        'payments': ledger.get('sub_payments') or [],
        'vendor_totals': ledger.get('vendor_paid_totals') or {},
        'total_paid': sum((ledger.get('vendor_paid_totals') or {}).values()),
    })


@app.route('/api/v1/jobs/<job>/owner-billings')
def job_owner_billings(job):
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    ledger = _job_ledger_response(job)
    if not ledger.get('found'):
        return jsonify({'job_number': job, 'billings': []}), 404
    billings = ledger.get('owner_billings') or []
    return jsonify({
        'job_number': job,
        'billings': billings,
        'total_billed': sum(_float_val(b.get('amount')) for b in billings),
    })


@app.route('/api/v1/jobs/<job>/actuals')
def job_actuals(job):
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    ledger = _job_ledger_response(job)
    if not ledger.get('found'):
        return jsonify({'job_number': job, 'actuals_by_cost_code': {}}), 404
    actuals = ledger.get('actuals_by_cost_code') or {}
    return jsonify({
        'job_number': job,
        'actuals_by_cost_code': actuals,
        'total_actual': sum(_float_val(v) for v in actuals.values()),
    })


@app.route('/api/v1/vendors')
def list_vendors():
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify({'vendors': list(STORE['vendors'].values())})


@app.route('/api/v1/transactions', methods=['POST'])
def post_transaction():
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    if not payload.get('event_type'):
        return jsonify({'error': 'event_type required'}), 400

    project = payload.get('project') or {}
    if not (project.get('sage_job_number') or '').strip():
        return jsonify({'error': 'sage_job_number required'}), 422

    txn_id = f'VSAGE-{len(STORE["transactions"]) + 1:06d}'
    applied = _apply_transaction(payload)
    record = {
        'id': txn_id,
        'received_at': datetime.utcnow().isoformat() + 'Z',
        'payload': payload,
        'applied': applied,
    }
    STORE['transactions'].append(record)
    return jsonify({
        'status': 'posted',
        'transaction_id': txn_id,
        'sage_job_number': project.get('sage_job_number'),
        'sage_module': payload.get('sage_module'),
        'sage_action': payload.get('sage_action'),
        'event_type': payload.get('event_type'),
    })


@app.route('/api/v1/vendors/<code>')
def get_vendor(code):
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    entry = STORE['vendors'].get(code)
    if not entry:
        return jsonify({'error': 'not found'}), 404
    return jsonify(entry)


@app.route('/api/v1/customers/<code>')
def get_customer(code):
    if not _auth_ok():
        return jsonify({'error': 'unauthorized'}), 401
    entry = STORE['customers'].get(code)
    if not entry:
        return jsonify({'error': 'not found'}), 404
    return jsonify(entry)


def main():
    _seed_directory()
    print(f'Virtual Sage 300 CRE bridge listening on http://127.0.0.1:{PORT}')
    print('  POST /api/v1/transactions')
    print('  GET  /api/v1/jobs/<job>/sub-payments')
    print('  GET  /api/v1/jobs/<job>/actuals')
    print('  GET  /api/v1/summary')
    app.run(host='127.0.0.1', port=PORT, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
