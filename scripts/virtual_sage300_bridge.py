#!/usr/bin/env python3
"""
Virtual Sage 300 CRE bridge for Case PM integration testing.

Implements the HTTP contract expected by sage_service.py and sage_companies_service.py:
  POST /api/v1/transactions
  GET  /api/v1/vendors/<code>
  GET  /api/v1/customers/<code>
  GET  /api/v1/health
  GET  /api/v1/summary          (test helper — transaction ledger stats)
  POST /api/v1/reset            (test helper — clear ledger)

Run: python3 scripts/virtual_sage300_bridge.py
Env: VIRTUAL_SAGE_PORT (default 8765), VIRTUAL_SAGE_API_KEY (default virtual-sage-test-key)
"""
from __future__ import annotations

import json
import os
import sys
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


def _apply_transaction(payload: dict) -> dict:
    """Update virtual job ledger from a Case PM Sage payload."""
    project = payload.get('project') or {}
    job = (project.get('sage_job_number') or '').strip()
    if not job:
        return {}

    job_rec = STORE['jobs'].setdefault(job, {
        'job_number': job,
        'project_name': project.get('project_name', ''),
        'budget_lines': [],
        'commitments': [],
        'change_orders': [],
        'pay_apps': [],
        'modules_seen': set(),
    })
    module = payload.get('sage_module') or ''
    action = payload.get('sage_action') or ''
    event_type = payload.get('event_type') or ''
    data = payload.get('data') or {}
    job_rec['modules_seen'].add(module)

    entry = {
        'event_type': event_type,
        'module': module,
        'action': action,
        'amount': data.get('amount') or data.get('total_amount') or data.get('current_amount'),
        'number': data.get('number') or data.get('commitment_number') or data.get('co_number'),
    }

    if module == 'JobCost':
        job_rec['budget_lines'].append(entry)
    elif module in ('AP', 'Subcontracts'):
        job_rec['commitments'].append(entry)
    elif module == 'PCO':
        job_rec['change_orders'].append(entry)
    elif module in ('ProgressBilling', 'SubcontractorBilling'):
        job_rec['pay_apps'].append(entry)
    return {'job': job, 'module': module, 'action': action}


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
    """Test helper — ledger breakdown for integration validation."""
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
        }

    return jsonify({
        'transaction_count': len(STORE['transactions']),
        'by_module': by_module,
        'by_event_type': by_event,
        'by_job': by_job,
        'jobs': jobs_summary,
    })


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
    print(f'  POST /api/v1/transactions')
    print(f'  GET  /api/v1/summary')
    app.run(host='127.0.0.1', port=PORT, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
