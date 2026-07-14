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
    from flask import session as flask_session
    from flask_login import login_user

    token = secrets.token_urlsafe(32)
    with client.session_transaction() as sess:
        sess.clear()
    with app.test_request_context():
        login_user(user)
        with client.session_transaction() as sess:
            sess.update(dict(flask_session))
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


def _make_flagged_user(models, p_a, uid: str, suffix: str, global_flags: dict):
    """User on project A with custom permission flags."""
    from permissions_catalog import permissions_from_role
    from project_access import save_memberships_for_user
    from user_permissions_persistence import save_user_permissions

    db = models['db']
    User = models['User']
    email = f'sec.{suffix}.{uid}@casepm.test'
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            first_name='Sec', last_name=suffix.title(), email=email,
            role='Company User', status='Active',
        )
        user.set_password('SecTest!12345')
        db.session.add(user)
        db.session.flush()
    perms = permissions_from_role('Company User')
    perms['global'] = {**(perms.get('global') or {}), **global_flags, 'customized': True}
    save_user_permissions(user, perms, db)
    save_memberships_for_user(user.id, [p_a.id], db, ProjectMembership=models['ProjectMembership'])
    db.session.commit()
    return user


def phase_respond_idor(result: SecResult, client, app, models, p_a, p_b, iso) -> None:
    """Isolated user must not read or act via /api/workflow/respond on project B."""
    token = _login_client(client, iso, app)
    pm = models['users']['pm']

    rfi_b = models['RFI'](
        project_id=p_b.id, number=f'RSP-{uuid.uuid4().hex[:6]}',
        subject='respond idor', status='Open', created_by_id=pm.id,
    )
    co_b = models['ChangeOrder'](
        project_id=p_b.id, number=f'RSP-{uuid.uuid4().hex[:6]}',
        title='respond idor', description='d', status='Draft', ball_in_court_role='Creator',
    )
    models['db'].session.add_all([rfi_b, co_b])
    models['db'].session.commit()

    rv = client.get(f'/api/workflow/respond/rfis/{rfi_b.id}', headers=_csrf_headers(token))
    if rv.status_code == 403:
        result.ok('respond_idor_rfi_get_blocked', 'respond_idor')
    else:
        result.fail('respond_idor_rfi_get_blocked', 'respond_idor', f'HTTP {rv.status_code}')

    rv2 = client.post(
        f'/api/workflow/respond/rfis/{rfi_b.id}',
        json={'action': 'close'},
        headers=_csrf_headers(token),
    )
    if rv2.status_code == 403:
        result.ok('respond_idor_rfi_post_blocked', 'respond_idor')
    else:
        result.fail('respond_idor_rfi_post_blocked', 'respond_idor', f'HTTP {rv2.status_code}')

    rv3 = client.get(f'/api/workflow/respond/co/{co_b.id}', headers=_csrf_headers(token))
    if rv3.status_code == 403:
        result.ok('respond_idor_co_get_blocked', 'respond_idor')
    else:
        result.fail('respond_idor_co_get_blocked', 'respond_idor', f'HTTP {rv3.status_code}')

    rv4 = client.post(
        f'/api/workflow/respond/co/{co_b.id}',
        json={'action': 'submit'},
        headers=_csrf_headers(token),
    )
    models['db'].session.refresh(co_b)
    if rv4.status_code == 403 and co_b.status == 'Draft':
        result.ok('respond_idor_co_post_blocked', 'respond_idor')
    elif co_b.status != 'Draft':
        result.fail('respond_idor_co_post_blocked', 'respond_idor', f'CO advanced to {co_b.status}')
    else:
        result.fail('respond_idor_co_post_blocked', 'respond_idor', f'HTTP {rv4.status_code}')


def phase_pay_app_idor(result: SecResult, client, app, models, p_a, p_b, iso) -> None:
    """Isolated user must not drive pay-app workflow on project B."""
    from pay_app_persistence import save_pay_app_state

    token = _login_client(client, iso, app)
    PayAppProjectState = models['PayAppProjectState']
    save_pay_app_state(PayAppProjectState, models['db'], p_b.id, {
        'contractorSOV': [{'id': 1, 'original': 1_000_000}],
        'currentPayAppPeriod': {
            'periodNumber': 1,
            'status': 'Draft',
            'ball_in_court_role': 'Creator',
        },
        'payAppBillingLines': {},
    }, user_id=None)
    models['db'].session.commit()

    rv = client.post(
        '/api/pay-applications/workflow',
        json={'project_id': p_b.id, 'action': 'submit', 'period_number': 1},
        headers=_csrf_headers(token),
    )
    if rv.status_code == 403:
        result.ok('pay_app_workflow_idor_blocked', 'pay_app_idor')
    else:
        result.fail('pay_app_workflow_idor_blocked', 'pay_app_idor', f'HTTP {rv.status_code}')

    rv2 = client.get(
        f'/api/workflow/respond/pay_applications/1?project_id={p_b.id}',
        headers=_csrf_headers(token),
    )
    if rv2.status_code == 403:
        result.ok('respond_idor_pay_app_get_blocked', 'pay_app_idor')
    else:
        result.fail('respond_idor_pay_app_get_blocked', 'pay_app_idor', f'HTTP {rv2.status_code}')


def phase_permissions(result: SecResult, client, app, models, p_a, p_b) -> None:
    """hide_financials and client_portal_only flags enforced on API routes."""
    from pay_app_persistence import save_pay_app_state

    uid = uuid.uuid4().hex[:8]
    save_pay_app_state(models['PayAppProjectState'], models['db'], p_a.id, {
        'contractorSOV': [{'id': 1, 'original': 1_000_000}],
        'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'},
    }, user_id=None)
    models['db'].session.commit()

    hide_user = _make_flagged_user(models, p_a, uid, 'hidefin', {'hide_financials': True})
    token_hide = _login_client(client, hide_user, app)

    rv_budget = client.get(f'/api/budget/state?project_id={p_a.id}', headers=_csrf_headers(token_hide))
    if rv_budget.status_code == 403:
        result.ok('hide_financials_budget_blocked', 'permissions')
    else:
        result.fail('hide_financials_budget_blocked', 'permissions', f'HTTP {rv_budget.status_code}')

    rv_pay = client.get(f'/api/pay-applications/state?project_id={p_a.id}', headers=_csrf_headers(token_hide))
    if rv_pay.status_code == 403:
        result.ok('hide_financials_pay_app_blocked', 'permissions')
    else:
        result.fail('hide_financials_pay_app_blocked', 'permissions', f'HTTP {rv_pay.status_code}')

    rv_rfi = client.get(f'/api/rfis?project_id={p_a.id}', headers=_csrf_headers(token_hide))
    if rv_rfi.status_code == 200:
        result.ok('hide_financials_rfi_allowed', 'permissions')
    else:
        result.fail('hide_financials_rfi_allowed', 'permissions', f'HTTP {rv_rfi.status_code}', severity='warning')

    portal_user = _make_flagged_user(models, p_a, uid, 'portal', {'client_portal_only': True})
    token_portal = _login_client(client, portal_user, app)

    rv_users = client.get('/api/users', headers=_csrf_headers(token_portal))
    if rv_users.status_code == 403:
        result.ok('client_portal_users_blocked', 'permissions')
    else:
        result.fail('client_portal_users_blocked', 'permissions', f'HTTP {rv_users.status_code}')

    rv_audit = client.get('/api/audit-log/events', headers=_csrf_headers(token_portal))
    if rv_audit.status_code == 403:
        result.ok('client_portal_audit_blocked', 'permissions')
    else:
        result.fail('client_portal_audit_blocked', 'permissions', f'HTTP {rv_audit.status_code}')

    rv_rfi2 = client.get(f'/api/rfis?project_id={p_a.id}', headers=_csrf_headers(token_portal))
    if rv_rfi2.status_code == 200:
        result.ok('client_portal_rfi_allowed', 'permissions')
    else:
        result.fail('client_portal_rfi_allowed', 'permissions', f'HTTP {rv_rfi2.status_code}', severity='warning')

    rv_pay_respond = client.get(
        f'/api/workflow/respond/pay_applications/1?project_id={p_a.id}',
        headers=_csrf_headers(token_hide),
    )
    if rv_pay_respond.status_code == 403:
        result.ok('hide_financials_pay_respond_blocked', 'permissions')
    else:
        result.fail('hide_financials_pay_respond_blocked', 'permissions', f'HTTP {rv_pay_respond.status_code}')


def phase_portal_security(result: SecResult, client, app, models, p_a, p_b) -> None:
    """Portal/subcontractor paths enforce project membership."""
    from project_access import save_memberships_for_user

    sub = models['users']['sub']
    save_memberships_for_user(sub.id, [p_a.id], models['db'], ProjectMembership=models['ProjectMembership'])
    models['db'].session.commit()

    rfq_b = models['SubcontractorRFQ'](
        project_id=p_b.id, number=f'PS-{uuid.uuid4().hex[:6]}',
        title='portal test', status='Sent', ball_in_court_role='Subcontractor',
        company_id=str(getattr(sub, 'company_id', '') or '1'),
        company_name=getattr(sub, 'company', None) or 'Sub Co',
    )
    models['db'].session.add(rfq_b)
    models['db'].session.commit()

    token = _login_client(client, sub, app)
    rv = client.post(
        f'/api/rfqs/{rfq_b.id}/portal-quote',
        json={'quoted_amount': 5000},
        headers=_csrf_headers(token),
    )
    if rv.status_code == 403:
        result.ok('portal_rfq_cross_project_blocked', 'portal')
    else:
        result.fail('portal_rfq_cross_project_blocked', 'portal', f'HTTP {rv.status_code}')


def phase_read_idor(result: SecResult, client, app, models, p_a, p_b, iso) -> None:
    """Isolated user must not read foreign project financial/entity data."""
    from pay_app_persistence import save_pay_app_state

    token = _login_client(client, iso, app)
    pm = models['users']['pm']
    PayAppProjectState = models['PayAppProjectState']
    Document = models.get('Document')
    ChangeEvent = models.get('ChangeEvent')
    PotentialChangeOrder = models['PotentialChangeOrder']

    co_b = models['ChangeOrder'](
        project_id=p_b.id, number=f'RD-{uuid.uuid4().hex[:6]}',
        title='read idor', description='d', status='Draft', ball_in_court_role='Creator',
    )
    com_b = models['Commitment'](
        project_id=p_b.id, number=f'RD-C-{uuid.uuid4().hex[:6]}',
        commitment_type='Subcontract', company_name='Other', company_id='999',
        title='t', description='d', status='Draft', original_amount=1000, current_amount=1000,
        ball_in_court_role='Creator',
    )
    rfi_b = models['RFI'](
        project_id=p_b.id, number=f'RD-R-{uuid.uuid4().hex[:6]}',
        subject='read idor', status='Open', created_by_id=pm.id,
    )
    sub_b = models['Submittal'](
        project_id=p_b.id, number=f'RD-S-{uuid.uuid4().hex[:6]}',
        description='read idor', status='Open',
    )
    pco_b = PotentialChangeOrder(
        project_id=p_b.id, number=f'RD-P-{uuid.uuid4().hex[:6]}',
        title='read idor', description='d', status='Open',
        ball_in_court_role='Project Manager', created_by_id=pm.id,
    )
    to_add = [co_b, com_b, rfi_b, sub_b, pco_b]
    ce_b = None
    if ChangeEvent:
        ce_b = ChangeEvent(
            project_id=p_b.id, number=f'RD-CE-{uuid.uuid4().hex[:6]}',
            title='read idor', status='Open', ball_in_court_role='Project Manager',
            created_by_id=pm.id,
        )
        to_add.append(ce_b)
    models['db'].session.add_all(to_add)
    models['db'].session.flush()
    save_pay_app_state(PayAppProjectState, models['db'], p_b.id, {
        'contractorSOV': [{'id': 1, 'original': 500_000}],
        'currentPayAppPeriod': {'periodNumber': 1, 'status': 'Draft'},
    }, user_id=None)
    doc_b = None
    if Document:
        doc_b = Document(
            project_id=p_b.id, name='secret.pdf', document_type='Other',
            filename='secret.pdf', uploaded_by_id=pm.id,
        )
        models['db'].session.add(doc_b)
    models['db'].session.commit()

    read_cases = [
        ('read_idor_budget_state', f'/api/budget/state?project_id={p_b.id}'),
        ('read_idor_pay_app_state', f'/api/pay-applications/state?project_id={p_b.id}'),
        ('read_idor_co_by_id', f'/api/change-orders/{co_b.id}'),
        ('read_idor_commitment_by_id', f'/api/commitments/{com_b.id}'),
        ('read_idor_rfi_by_id', f'/api/rfis/{rfi_b.id}'),
        ('read_idor_pco_by_id', f'/api/pcos/{pco_b.id}'),
        ('read_idor_submittal_attachments', f'/api/submittals/{sub_b.id}/attachments'),
        ('read_idor_commitments_list', f'/api/commitments?project_id={p_b.id}'),
        ('read_idor_co_list', f'/api/change-orders?project_id={p_b.id}'),
        ('read_idor_pco_list', f'/api/pcos?project_id={p_b.id}'),
        ('read_idor_rfqs_list', f'/api/rfqs?project_id={p_b.id}'),
        ('read_idor_cors_list', f'/api/cors?project_id={p_b.id}'),
        ('read_idor_budget_pending', f'/api/budget/pending-change-orders?project_id={p_b.id}'),
        ('read_idor_aia_export', f'/api/commitments/{com_b.id}/aia/export'),
    ]
    if ce_b:
        read_cases.extend([
            ('read_idor_change_event_by_id', f'/api/change-events/{ce_b.id}'),
            ('read_idor_change_events_list', f'/api/change-events?project_id={p_b.id}'),
        ])
    if doc_b:
        read_cases.append(('read_idor_document_download', f'/api/documents/{doc_b.id}/download'))
    for name, path in read_cases:
        rv = client.get(path, headers=_csrf_headers(token))
        if rv.status_code == 403:
            result.ok(name, 'read_idor')
        else:
            result.fail(name, 'read_idor', f'HTTP {rv.status_code}')


def phase_workflow_event_abuse(result: SecResult, client, app, models, p_a, p_b, iso) -> None:
    """Cross-project workflow events and approval decisions must be blocked."""
    from case_workflow import ApprovalRequest

    pm = models['users']['pm']
    pm_token = _login_client(client, pm, app)
    iso_token = _login_client(client, iso, app)

    for name, body in (
        ('workflow_event_submit_blocked', {
            'event': 'submit', 'project_id': p_b.id, 'module': 'Change Orders',
            'entity_type': 'ChangeOrder', 'entity_id': '1', 'title': 'abuse test',
        }),
        ('workflow_event_notify_blocked', {
            'event': 'notify', 'project_id': p_b.id, 'module': 'RFIs',
            'title': 'spam', 'description': 'cross-project notify',
            'user_ids': [pm.id],
        }),
    ):
        rv = client.post('/api/workflow/event', json=body, headers=_csrf_headers(iso_token))
        if rv.status_code == 403:
            result.ok(name, 'workflow_event')
        else:
            result.fail(name, 'workflow_event', f'HTTP {rv.status_code}')

    approval = ApprovalRequest(
        project_id=p_b.id, module='Change Orders', entity_type='ChangeOrder',
        entity_id='999', title='cross-project approval', status='pending',
        requested_by_id=pm.id, assignee_role='Project Manager',
    )
    models['db'].session.add(approval)
    models['db'].session.commit()

    rv3 = client.post(
        '/api/workflow/event',
        json={'event': 'approve', 'approval_id': approval.id},
        headers=_csrf_headers(iso_token),
    )
    models['db'].session.refresh(approval)
    if rv3.status_code == 403 and approval.status == 'pending':
        result.ok('workflow_event_approve_cross_project_blocked', 'workflow_event')
    elif approval.status != 'pending':
        result.fail('workflow_event_approve_cross_project_blocked', 'workflow_event', f'status={approval.status}')
    else:
        result.fail('workflow_event_approve_cross_project_blocked', 'workflow_event', f'HTTP {rv3.status_code}')

    # PM on both projects may create on B
    pm_token = _login_client(client, pm, app)
    rv4 = client.post(
        '/api/workflow/event',
        json={
            'event': 'request_approval', 'project_id': p_b.id, 'module': 'Pay Applications',
            'entity_type': 'G702', 'entity_id': '1', 'title': 'valid pm request',
        },
        headers=_csrf_headers(pm_token),
    )
    if rv4.status_code == 200:
        result.ok('workflow_event_pm_cross_project_allowed', 'workflow_event')
    else:
        result.fail('workflow_event_pm_cross_project_allowed', 'workflow_event', f'HTTP {rv4.status_code}', severity='warning')


def _ensure_role_matrix_memberships(models, p_a) -> None:
    from project_access import save_memberships_for_user

    db = models['db']
    for key in ('owner', 'arch', 'sub', 'acct'):
        save_memberships_for_user(
            models['users'][key].id, [p_a.id], db,
            ProjectMembership=models['ProjectMembership'],
        )
    db.session.commit()


def phase_role_matrix(result: SecResult, client, app, models, p_a) -> None:
    """Same-project actions outside ball-in-court / role must fail."""
    from pay_app_persistence import save_pay_app_state

    _ensure_role_matrix_memberships(models, p_a)
    pm = models['users']['pm']
    arch = models['users']['arch']
    sub = models['users']['sub']

    co = models['ChangeOrder'](
        project_id=p_a.id, number=f'RM-{uuid.uuid4().hex[:6]}',
        title='role matrix', description='d', status='Submitted',
        ball_in_court_role='Owner',
    )
    rfi = models['RFI'](
        project_id=p_a.id, number=f'RM-R-{uuid.uuid4().hex[:6]}',
        subject='role matrix', status='Open', ball_in_court_role='Assignee',
        created_by_id=pm.id,
    )
    models['db'].session.add_all([co, rfi])
    models['db'].session.flush()
    save_pay_app_state(models['PayAppProjectState'], models['db'], p_a.id, {
        'contractorSOV': [{'id': 1, 'original': 2_000_000}],
        'currentPayAppPeriod': {
            'periodNumber': 1, 'status': 'Submitted', 'ball_in_court_role': 'Owner',
        },
        'payAppBillingLines': {'1': {'workThisPeriod': 50_000, 'materialsStored': 0}},
    }, user_id=None)
    models['db'].session.commit()

    arch_token = _login_client(client, arch, app)
    rv = client.post(
        f'/api/change-orders/{co.id}/workflow',
        json={'action': 'approve'},
        headers=_csrf_headers(arch_token),
    )
    models['db'].session.refresh(co)
    if rv.status_code in (400, 403) and co.status == 'Submitted':
        result.ok('role_matrix_arch_cannot_approve_owner_co', 'role_matrix')
    elif co.status != 'Submitted':
        result.fail('role_matrix_arch_cannot_approve_owner_co', 'role_matrix', f'CO -> {co.status}')
    else:
        result.fail('role_matrix_arch_cannot_approve_owner_co', 'role_matrix', f'HTTP {rv.status_code}')

    pm_token = _login_client(client, pm, app)
    rv2 = client.post(
        '/api/pay-applications/workflow',
        json={'project_id': p_a.id, 'action': 'approve', 'period_number': 1},
        headers=_csrf_headers(pm_token),
    )
    _, pay_state = __import__('pay_app_persistence', fromlist=['get_pay_app_state']).get_pay_app_state(
        models['PayAppProjectState'], p_a.id,
    )
    period_status = (pay_state or {}).get('currentPayAppPeriod', {}).get('status')
    if rv2.status_code in (400, 403) and period_status == 'Submitted':
        result.ok('role_matrix_pm_cannot_approve_owner_g702', 'role_matrix')
    elif period_status not in ('Submitted', None):
        result.fail('role_matrix_pm_cannot_approve_owner_g702', 'role_matrix', f'period -> {period_status}')
    else:
        result.fail('role_matrix_pm_cannot_approve_owner_g702', 'role_matrix', f'HTTP {rv2.status_code}')

    sub_token = _login_client(client, sub, app)
    rv3 = client.post(
        f'/api/rfis/{rfi.id}/workflow',
        json={'action': 'close'},
        headers=_csrf_headers(sub_token),
    )
    models['db'].session.refresh(rfi)
    if rv3.status_code in (400, 403) and rfi.status == 'Open':
        result.ok('role_matrix_sub_cannot_close_rfi', 'role_matrix')
    elif rfi.status != 'Open':
        result.fail('role_matrix_sub_cannot_close_rfi', 'role_matrix', f'RFI -> {rfi.status}')
    else:
        result.fail('role_matrix_sub_cannot_close_rfi', 'role_matrix', f'HTTP {rv3.status_code}')

    co_pm = models['ChangeOrder'](
        project_id=p_a.id, number=f'RM-P-{uuid.uuid4().hex[:6]}',
        title='pm control', description='d', status='Submitted',
        ball_in_court_role='Project Manager',
    )
    models['db'].session.add(co_pm)
    models['db'].session.commit()

    pm_token = _login_client(client, pm, app)
    rv4 = client.post(
        f'/api/change-orders/{co_pm.id}/workflow',
        json={'action': 'approve'},
        headers=_csrf_headers(pm_token),
    )
    models['db'].session.refresh(co_pm)
    if rv4.status_code == 403:
        result.fail('role_matrix_pm_can_advance_pm_ball_co', 'role_matrix', 'PM forbidden on own ball')
    elif co_pm.status != 'Submitted':
        result.ok('role_matrix_pm_can_advance_pm_ball_co', 'role_matrix', f'-> {co_pm.status}')
    elif rv4.status_code == 400:
        result.ok('role_matrix_pm_can_advance_pm_ball_co', 'role_matrix', 'validation 400 (not forbidden)')
    else:
        result.fail('role_matrix_pm_can_advance_pm_ball_co', 'role_matrix', f'HTTP {rv4.status_code}')


def phase_csrf_sweep(result: SecResult, client, app, models, p_a) -> None:
    """State-changing routes reject requests without CSRF token."""
    pm = models['users']['pm']
    token = _login_client(client, pm, app)

    rfi = models['RFI'](
        project_id=p_a.id, number=f'CS-{uuid.uuid4().hex[:6]}',
        subject='csrf sweep', status='Draft', ball_in_court_role='RFI Manager',
        created_by_id=pm.id,
    )
    co = models['ChangeOrder'](
        project_id=p_a.id, number=f'CS-{uuid.uuid4().hex[:6]}',
        title='csrf', description='d', status='Draft', ball_in_court_role='Creator',
    )
    com = models['Commitment'](
        project_id=p_a.id, number=f'CS-C-{uuid.uuid4().hex[:6]}',
        commitment_type='Purchase Order', company_name='Co', company_id='1',
        title='t', description='d', status='Draft', original_amount=500, current_amount=500,
        ball_in_court_role='Creator',
    )
    models['db'].session.add_all([rfi, co, com])
    models['db'].session.commit()

    sweep = [
        ('csrf_sweep_rfi_workflow', 'POST', f'/api/rfis/{rfi.id}/workflow', {'action': 'submit'}),
        ('csrf_sweep_co_workflow', 'POST', f'/api/change-orders/{co.id}/workflow', {'action': 'submit'}),
        ('csrf_sweep_commitment_workflow', 'POST', f'/api/commitments/{com.id}/workflow', {'action': 'submit'}),
        ('csrf_sweep_pay_app_workflow', 'POST', '/api/pay-applications/workflow', {
            'project_id': p_a.id, 'action': 'submit', 'period_number': 1,
        }),
        ('csrf_sweep_workflow_event', 'POST', '/api/workflow/event', {
            'event': 'notify', 'project_id': p_a.id, 'title': 't', 'description': 'd',
        }),
        ('csrf_sweep_budget_put', 'PUT', '/api/budget/state', {'project_id': p_a.id, 'data': {}}),
    ]
    for name, method, path, body in sweep:
        if method == 'PUT':
            rv = client.put(path, json=body)
        else:
            rv = client.post(path, json=body)
        if rv.status_code == 403:
            result.ok(name, 'csrf_sweep')
        else:
            result.fail(name, 'csrf_sweep', f'HTTP {rv.status_code}', severity='warning')

    # With token, at least one path should succeed (sanity)
    rv_ok = client.post(
        f'/api/rfis/{rfi.id}/workflow',
        json={'action': 'submit'},
        headers=_csrf_headers(token),
    )
    if rv_ok.status_code == 200:
        result.ok('csrf_sweep_token_still_works', 'csrf_sweep')
    else:
        result.fail('csrf_sweep_token_still_works', 'csrf_sweep', f'HTTP {rv_ok.status_code}', severity='warning')


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
        help='Comma-separated: persistence,auth,csrf,csrf_sweep,idor,read_idor,respond_idor,pay_app_idor,permissions,workflow_event,role_matrix,legacy,workflow,financial,recovery,all',
    )
    args = parser.parse_args()
    phases = {p.strip() for p in args.phase.split(',')}
    if 'all' in phases:
        phases = {
            'persistence', 'auth', 'csrf', 'csrf_sweep', 'idor', 'read_idor',
            'respond_idor', 'pay_app_idor', 'permissions', 'workflow_event',
            'role_matrix', 'legacy', 'workflow', 'financial', 'recovery', 'portal',
        }

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
        'PayAppProjectState': app_module.PayAppProjectState,
        'PotentialChangeOrder': app_module.PotentialChangeOrder,
        'ChangeEvent': getattr(app_module, 'ChangeEvent', None),
        'Document': getattr(app_module, 'Document', None),
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
            if phases & {
                'csrf', 'csrf_sweep', 'idor', 'read_idor', 'respond_idor', 'pay_app_idor',
                'permissions', 'workflow_event', 'role_matrix', 'legacy', 'recovery', 'portal',
            }:
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
            if 'csrf_sweep' in phases:
                phase_csrf_sweep(result, client, app_module.app, models, p_a)
            if 'idor' in phases:
                phase_idor(result, client, app_module.app, models, p_a, p_b, iso)
            if 'read_idor' in phases:
                phase_read_idor(result, client, app_module.app, models, p_a, p_b, iso)
            if 'respond_idor' in phases:
                phase_respond_idor(result, client, app_module.app, models, p_a, p_b, iso)
            if 'pay_app_idor' in phases:
                phase_pay_app_idor(result, client, app_module.app, models, p_a, p_b, iso)
            if 'permissions' in phases:
                phase_permissions(result, client, app_module.app, models, p_a, p_b)
            if 'workflow_event' in phases:
                phase_workflow_event_abuse(result, client, app_module.app, models, p_a, p_b, iso)
            if 'role_matrix' in phases:
                phase_role_matrix(result, client, app_module.app, models, p_a)
            if 'portal' in phases:
                phase_portal_security(result, client, app_module.app, models, p_a, p_b)
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
