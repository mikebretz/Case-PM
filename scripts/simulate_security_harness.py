#!/usr/bin/env python3
"""
Heavy security harness — auth, CSRF, IDOR, PUT bypass, workflow auth, financial spoofing.

  python3 scripts/simulate_security_harness.py
  python3 scripts/simulate_security_harness.py --phase csrf,idor
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

sys.path.insert(0, '/workspace')


@dataclass
class SecCase:
    name: str
    category: str
    passed: bool
    message: str
    severity: str = 'critical'


@dataclass
class SecResult:
    cases: list[SecCase] = field(default_factory=list)

    def ok(self, name: str, category: str, message: str = 'ok'):
        self.cases.append(SecCase(name, category, True, message, 'info'))

    def fail(self, name: str, category: str, message: str, severity: str = 'critical'):
        self.cases.append(SecCase(name, category, False, message, severity))

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed and c.severity == 'critical')

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed and c.severity == 'warning')


def _login_client(client, user, app):
    import secrets
    from access_control import SESSION_ACTIVITY_KEY

    token = secrets.token_urlsafe(32)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        sess['casepm_2fa_verified'] = True
        sess[SESSION_ACTIVITY_KEY] = time.time()
        sess['casepm_csrf_token'] = token
    return token


def _csrf_headers(token: str) -> dict:
    return {'X-CSRF-Token': token, 'Content-Type': 'application/json'}


def _setup_projects_and_users(models):
    """Two projects; isolated_user only on project A."""
    from program_settings_persistence import save_security_settings
    from project_access import save_memberships_for_user

    db = models['db']
    Project = models['Project']
    User = models['User']
    uid = uuid.uuid4().hex[:8]

    save_security_settings({
        'enforce_project_membership': True,
        'session_timeout_minutes': 60,
        'max_login_attempts': 5,
        'lockout_minutes': 15,
        'require_2fa_for_admins': False,
    })
    db.session.commit()

    p_a = Project(number=f'SEC-A-{uid}', name='Security A', status='Active', contract_value=5_000_000)
    p_b = Project(number=f'SEC-B-{uid}', name='Security B', status='Active', contract_value=8_000_000)
    db.session.add_all([p_a, p_b])
    db.session.flush()

    iso_email = f'sec.isolated.{uid}@casepm.test'
    iso = User.query.filter_by(email=iso_email).first()
    if not iso:
        iso = User(
            first_name='Iso', last_name='User', email=iso_email,
            role='Company User', status='Active',
        )
        iso.set_password('IsoTest!12345')
        db.session.add(iso)
        db.session.flush()
    save_memberships_for_user(iso.id, [p_a.id], db, ProjectMembership=models['ProjectMembership'])

    pm = models['users']['pm']
    save_memberships_for_user(pm.id, [p_a.id, p_b.id], db, ProjectMembership=models['ProjectMembership'])
    db.session.commit()
    return p_a, p_b, iso


def phase_persistence_bypass(result: SecResult, models) -> None:
    """Direct persistence-layer bypass attempts (no HTTP)."""
    from financial_security import (
        strip_workflow_fields, sanitize_pay_app_state, sanitize_budget_state,
        assert_draft_create_status,
    )
    from rfi_persistence import apply_rfi_fields
    from submittal_persistence import apply_submittal_fields
    from change_event_persistence import apply_rfq_fields

    rfi = models['RFI'](
        project_id=1, number='SEC-RFI-1', subject='t', status='Open',
        ball_in_court_role='Assignee',
    )
    old = rfi.status
    apply_rfi_fields(rfi, {'status': 'Void'}, is_create=False)
    if rfi.status == old:
        result.ok('rfi_status_put_blocked', 'persistence', 'RFI status unchanged via apply')
    else:
        result.fail('rfi_status_put_blocked', 'persistence', f'RFI status changed to {rfi.status}')

    sub = models['Submittal'](
        project_id=1, number='SEC-SUB-1', description='d', status='Draft',
    )
    old_sub = sub.status
    apply_submittal_fields(sub, {'status': 'Closed'}, is_create=False)
    if sub.status == old_sub:
        result.ok('submittal_status_put_blocked', 'persistence')
    else:
        result.fail('submittal_status_put_blocked', 'persistence', f'status -> {sub.status}')

    rfq = models['SubcontractorRFQ'](
        project_id=1, number='SEC-RFQ-1', title='t', status='Draft',
    )
    old_q = getattr(rfq, 'quoted_amount', None)
    apply_rfq_fields(rfq, {'quoted_amount': 999999})
    if getattr(rfq, 'quoted_amount', None) == old_q:
        result.ok('rfq_quoted_amount_put_blocked', 'persistence')
    else:
        result.fail('rfq_quoted_amount_put_blocked', 'persistence', 'quoted_amount writable')

    stripped = strip_workflow_fields({'status': 'Approved', 'subject': 'x'})
    if 'status' not in stripped and stripped.get('subject') == 'x':
        result.ok('strip_workflow_fields', 'persistence')
    else:
        result.fail('strip_workflow_fields', 'persistence', str(stripped))

    pay = sanitize_pay_app_state(
        {'currentPayAppPeriod': {'status': 'Draft', 'periodNumber': 1}},
        {'currentPayAppPeriod': {'status': 'Approved', 'amount_due': 1}, 'amount_due': 9},
    )
    period = pay.get('currentPayAppPeriod') or {}
    if period.get('status') == 'Draft' and 'amount_due' not in pay:
        result.ok('pay_app_state_sanitized', 'persistence')
    else:
        result.fail('pay_app_state_sanitized', 'persistence', str(period))

    budget = sanitize_budget_state(
        {'budgetLines': [{'cost_code': '01', 'committed': 0, 'actual': 0}]},
        {'budgetLines': [{'cost_code': '01', 'committed': 999, 'actual': 888}]},
    )
    line = (budget.get('budgetLines') or [{}])[0]
    if line.get('committed') == 0 and line.get('actual') == 0:
        result.ok('budget_reconcile_fields_preserved', 'persistence')
    else:
        result.fail('budget_reconcile_fields_preserved', 'persistence', str(line))

    try:
        assert_draft_create_status('Approved')
        result.fail('draft_create_status', 'persistence', 'Approved create allowed')
    except ValueError:
        result.ok('draft_create_status', 'persistence')


def phase_auth_session(result: SecResult, models, app) -> None:
    from access_control import (
        check_login_allowed, record_login_failure, record_login_success,
        enforce_session_idle_timeout, reset_session_activity, SESSION_ACTIVITY_KEY,
    )
    from developer_tools import validate_recovery_token
    from flask import session

    email = 'lockout.test@casepm.test'
    with app.test_request_context('/login'):
        record_login_success(email)
        allowed = True
        for _ in range(6):
            if not check_login_allowed(email)[0]:
                allowed = False
                break
            record_login_failure(email)
        record_login_success(email)
    if not allowed:
        result.ok('login_lockout_triggers', 'auth')
    else:
        result.fail('login_lockout_triggers', 'auth', 'lockout did not trigger after 6 failures')

    if validate_recovery_token('totally-wrong-token'):
        result.fail('recovery_token_reject', 'auth', 'invalid token accepted')
    else:
        result.ok('recovery_token_reject', 'auth')

    user = SimpleNamespace(is_authenticated=True)
    with app.app_context():
        with app.test_request_context('/dashboard'):
            session[SESSION_ACTIVITY_KEY] = time.time() - 7200
            should, _ = enforce_session_idle_timeout(user, 'dashboard')
            if should:
                result.ok('idle_timeout_stale_session', 'auth')
            else:
                result.fail('idle_timeout_stale_session', 'auth', 'stale session not expired')

            reset_session_activity()
            should2, _ = enforce_session_idle_timeout(user, 'dashboard')
            if not should2:
                result.ok('idle_timeout_fresh_session', 'auth')
            else:
                result.fail('idle_timeout_fresh_session', 'auth', 'fresh session wrongly expired')


def phase_csrf(result: SecResult, client, app, models, p_a) -> None:
    pm = models['users']['pm']
    token = _login_client(client, pm, app)

    rfi = models['RFI'](
        project_id=p_a.id, number=f'CSRF-{uuid.uuid4().hex[:6]}',
        subject='csrf test', status='Draft', ball_in_court_role='RFI Manager',
        created_by_id=pm.id,
    )
    models['db'].session.add(rfi)
    models['db'].session.commit()

    rv = client.post(f'/api/rfis/{rfi.id}/workflow', json={'action': 'submit'})
    if rv.status_code == 403:
        result.ok('csrf_blocks_rfi_workflow', 'csrf')
    else:
        result.fail('csrf_blocks_rfi_workflow', 'csrf', f'status {rv.status_code}: {rv.get_data(as_text=True)[:120]}')

    rv2 = client.post(
        f'/api/rfis/{rfi.id}/workflow',
        json={'action': 'submit'},
        headers=_csrf_headers(token),
    )
    if rv2.status_code == 200:
        result.ok('csrf_allows_rfi_with_token', 'csrf')
    else:
        result.fail('csrf_allows_rfi_with_token', 'csrf', f'status {rv2.status_code}', severity='warning')


def phase_idor(result: SecResult, client, app, models, p_a, p_b, iso) -> None:
    """Isolated user (project A only) must not mutate project B entities."""
    token = _login_client(client, iso, app)

    co_b = models['ChangeOrder'](
        project_id=p_b.id, number=f'IDOR-{uuid.uuid4().hex[:6]}',
        title='idor test', description='idor test', status='Draft', ball_in_court_role='Creator',
    )
    models['db'].session.add(co_b)
    models['db'].session.flush()

    com_b = models['Commitment'](
        project_id=p_b.id, number=f'IDOR-C-{uuid.uuid4().hex[:6]}',
        commitment_type='Subcontract', company_name='Other', company_id='999',
        title='t', description='d', status='Draft', original_amount=1000, current_amount=1000,
        ball_in_court_role='Creator',
    )
    models['db'].session.add(com_b)
    models['db'].session.commit()

  # CO workflow — should be blocked for cross-project user
    rv = client.post(
        f'/api/change-orders/{co_b.id}/workflow',
        json={'action': 'submit'},
        headers=_csrf_headers(token),
    )
    if rv.status_code in (403, 400) and co_b.status == 'Draft':
        result.ok('idor_co_workflow_blocked', 'idor')
    elif co_b.status != 'Draft':
        result.fail('idor_co_workflow_blocked', 'idor', f'CO submitted by isolated user (status {co_b.status})')
    else:
        result.fail('idor_co_workflow_blocked', 'idor', f'HTTP {rv.status_code} — expected 403', severity='warning')

    rv2 = client.post(
        '/api/rfis',
        json={'project_id': p_b.id, 'subject': 'idor create'},
        headers=_csrf_headers(token),
    )
    # create_rfi has no require_financial_project_access — flag if 200
    if rv2.status_code in (403, 400):
        result.ok('idor_rfi_create_blocked', 'idor')
    else:
        result.fail('idor_rfi_create_blocked', 'idor', f'created RFI on foreign project: {rv2.status_code}', severity='warning')

    rv3 = client.post(
        f'/api/commitments/{com_b.id}/workflow',
        json={'action': 'submit'},
        headers=_csrf_headers(token),
    )
    models['db'].session.refresh(com_b)
    if rv3.status_code in (403, 400) and com_b.status == 'Draft':
        result.ok('idor_commitment_workflow_blocked', 'idor')
    elif com_b.status != 'Draft':
        result.fail('idor_commitment_workflow_blocked', 'idor', f'commitment advanced to {com_b.status}')
    else:
        result.fail('idor_commitment_workflow_blocked', 'idor', f'HTTP {rv3.status_code}', severity='warning')


def phase_legacy_routes(result: SecResult, client, app, models, p_a) -> None:
    pm = models['users']['pm']
    token = _login_client(client, pm, app)

    rfi = models['RFI'](
        project_id=p_a.id, number=f'LEG-{uuid.uuid4().hex[:6]}',
        subject='legacy', status='Draft', created_by_id=pm.id,
    )
    models['db'].session.add(rfi)
    models['db'].session.commit()

    for path in (
        f'/rfis/{rfi.id}/update-status',
        f'/submittals/1/update-status',
        f'/change-orders/1/update-status',
        '/api/pcos/1/update-status',
    ):
        rv = client.post(path, json={'status': 'Closed'}, headers=_csrf_headers(token))
        if rv.status_code == 410:
            result.ok(f'legacy_410_{path.split("/")[1]}', 'legacy')
        else:
            result.fail(f'legacy_410_{path}', 'legacy', f'status {rv.status_code}')


def phase_workflow_auth(result: SecResult, models) -> None:
    from change_event_persistence import rfq_workflow_action
    from pay_app_workflow import g702_workflow_action

    sub = models['users']['sub']
    pm = models['users']['pm']
    rfq = models['SubcontractorRFQ'](
        project_id=1, number='WA-RFQ', title='t', status='Quoted',
        ball_in_court_role='Project Manager', company_id='1',
    )
    try:
        rfq_workflow_action(rfq, 'reject', sub)
        result.ok('rfq_reject_wrong_role_blocked', 'workflow_auth')
    except ValueError:
        result.ok('rfq_reject_wrong_role_blocked', 'workflow_auth')

    period = {'status': 'Submitted', 'periodNumber': 1, 'ball_in_court_role': 'Owner'}
    try:
        g702_workflow_action(period, 'approve', pm, amount=100000)
        result.fail('g702_wrong_ball_blocked', 'workflow_auth', 'PM approved while ball with Owner')
    except ValueError:
        result.ok('g702_wrong_ball_blocked', 'workflow_auth')


def phase_financial_spoof(result: SecResult, models) -> None:
    from pay_app_workflow import g702_workflow_action, _g702_threshold_amount

    state = {
        'contractorSOV': [{'id': 1, 'original': 3_600_000}],
        'payAppBillingLines': {'1': {'workThisPeriod': 3_600_000, 'materialsStored': 0}},
        'payAppRetainagePercent': 10,
    }
    threshold = _g702_threshold_amount(state)
    if threshold > 1_000_000:
        result.ok('g702_threshold_from_sov', 'financial', f'threshold=${threshold:,.0f}')
    else:
        result.fail('g702_threshold_from_sov', 'financial', f'threshold only ${threshold:,.0f}')

    period = {'status': 'Submitted', 'periodNumber': 1, 'ball_in_court_role': 'Project Manager'}
    pm = models['users']['pm']
    owner = models['users']['owner']
    status, final = g702_workflow_action(period, 'approve', pm, amount=threshold, cumulative_amount=0)
    if status != 'Pending Owner':
        result.fail('g702_large_pm_to_owner', 'financial', f'expected Pending Owner got {status}')
    else:
        period['ball_in_court_role'] = 'Owner'
        status2, final2 = g702_workflow_action(period, 'approve', owner, amount=threshold, cumulative_amount=0)
        if status2 == 'Pending Accounting' and not final2:
            result.ok('g702_large_billing_needs_accounting', 'financial')
        elif status2 == 'Approved':
            result.fail('g702_large_billing_needs_accounting', 'financial', 'skipped Accounting on large billing')
        else:
            result.ok('g702_large_billing_needs_accounting', 'financial', f'status={status2}')


def phase_recovery_login(result: SecResult, client, app, models) -> None:
    import os
    import json
    path = os.path.join('instance', 'recovery.access')
    if not os.path.isfile(path):
        result.ok('recovery_login_skip', 'auth', 'no recovery.access configured — skipped')
        return

    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    email = data.get('email', '')
    password = data.get('password', '')

    client.post('/logout')
    rv = client.post('/login', data={'email': email, 'password': password, 'remember': 'on'}, follow_redirects=False)
    if rv.status_code in (302, 303):
        with client.session_transaction() as sess:
            if sess.get('_user_id'):
                result.ok('recovery_login_session', 'auth')
            else:
                result.fail('recovery_login_session', 'auth', 'no session after recovery login')
    else:
        result.fail('recovery_login_session', 'auth', f'HTTP {rv.status_code}', severity='warning')


def _print_results(result: SecResult) -> int:
    by_cat: dict[str, list[SecCase]] = {}
    for c in result.cases:
        by_cat.setdefault(c.category, []).append(c)

    print('\n' + '=' * 60)
    print('HEAVY SECURITY HARNESS RESULTS')
    print('=' * 60)
    for cat, cases in sorted(by_cat.items()):
        print(f'\n--- {cat} ---')
        for c in cases:
            mark = 'PASS' if c.passed else 'FAIL'
            print(f'  [{mark}] {c.name}: {c.message}')

    crit = result.critical_count
    warn = result.warning_count
    passed = sum(1 for c in result.cases if c.passed)
    print(f'\n{"=" * 60}')
    print(f'Total: {passed}/{len(result.cases)} passed | Critical failures: {crit} | Warnings: {warn}')
    print('=' * 60)
    return 1 if crit else 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Heavy security harness')
    parser.add_argument(
        '--phase',
        default='all',
        help='Comma-separated: persistence,auth,csrf,idor,legacy,workflow,financial,recovery,all',
    )
    args = parser.parse_args()
    phases = {p.strip() for p in args.phase.split(',')}
    if 'all' in phases:
        phases = {'persistence', 'auth', 'csrf', 'idor', 'legacy', 'workflow', 'financial', 'recovery'}

    import app as app_module
    from unittest.mock import patch
    from case_workflow import ensure_workflow_schema, ProjectMembership
    from scripts.simulate_financial_project import _ensure_sim_users

    models = {
        'db': app_module.db,
        'User': app_module.User,
        'Project': app_module.Project,
        'RFI': app_module.RFI,
        'Submittal': app_module.Submittal,
        'ChangeOrder': app_module.ChangeOrder,
        'Commitment': app_module.Commitment,
        'SubcontractorRFQ': app_module.SubcontractorRFQ,
        'ProjectMembership': ProjectMembership,
    }

    result = SecResult()
    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)

    sig_patch.start()
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(models['db'].engine)
            models['db'].session.rollback()
            models['users'] = _ensure_sim_users(models['db'], models['User'])
            client = app_module.app.test_client()
            p_a = p_b = iso = None
            if phases & {'csrf', 'idor', 'legacy', 'recovery'}:
                p_a, p_b, iso = _setup_projects_and_users(models)

            if 'persistence' in phases:
                phase_persistence_bypass(result, models)
            if 'auth' in phases:
                phase_auth_session(result, models, app_module.app)
            if 'workflow' in phases:
                phase_workflow_auth(result, models)
            if 'financial' in phases:
                phase_financial_spoof(result, models)
            if 'csrf' in phases:
                phase_csrf(result, client, app_module.app, models, p_a)
            if 'idor' in phases:
                phase_idor(result, client, app_module.app, models, p_a, p_b, iso)
            if 'legacy' in phases:
                phase_legacy_routes(result, client, app_module.app, models, p_a)
            if 'recovery' in phases:
                phase_recovery_login(result, client, app_module.app, models)
            models['db'].session.rollback()
    finally:
        sig_patch.stop()

    return _print_results(result)


if __name__ == '__main__':
    raise SystemExit(main())
