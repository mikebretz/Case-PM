"""
Waves 33–36 — site packs, drift UX APIs, SoR depth, enterprise scale & month-close wizard.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timedelta

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_sync_get
from accounting_waves_25 import ap_invoice_sage_payload, ar_invoice_sage_payload
from accounting_waves_27 import (
    get_schema_profile,
    sage_drift_dashboard,
    sor_guard_extended,
)


# --- Wave 33 ---

def list_sage_profile_packs() -> dict:
    from sage300_profile_packs import list_profile_packs

    return {'packs': list_profile_packs(), 'builtin_ids': ['sage300_web_api_default']}


def apply_profile_pack(db, models, ledger_id: int, pack_id: str, user_id=None) -> dict:
    from sage300_profile_packs import get_pack

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    pack = get_pack(pack_id)
    settings['sage_schema_profile_id'] = pack_id[:60]
    settings['sage_schema_profile_custom'] = {
        'resources': pack.get('resources'),
        'fields': pack.get('fields'),
        'label': pack.get('label'),
    }
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_profile_pack', details={'pack_id': pack_id})
    return {'pack_id': pack_id, 'profile': get_schema_profile(settings)}


def sage_push_dry_run(db, models, ledger_id: int, document_type: str, document_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    profile = get_schema_profile(settings)
    issues = []
    AcctGLAccount = models['AcctGLAccount']
    local_nums = {a.account_number for a in AcctGLAccount.query.filter_by(ledger_id=ledger_id).limit(500).all()}
    if document_type == 'ap':
        doc = models['AcctAPDocument'].query.filter_by(id=document_id, ledger_id=ledger_id).first()
        vendor = models['AcctVendor'].query.get(doc.vendor_id) if doc and doc.vendor_id else None
        payload = ap_invoice_sage_payload(doc, vendor, settings) if doc else {}
    else:
        doc = models['AcctARDocument'].query.filter_by(id=document_id, ledger_id=ledger_id).first()
        cust = models['AcctCustomer'].query.get(doc.customer_id) if doc and doc.customer_id else None
        payload = ar_invoice_sage_payload(doc, cust, settings) if doc else {}
    if not doc:
        return {'ok': False, 'error': 'document not found'}
    if not payload.get('VendorNumber') and not payload.get('CustomerNumber'):
        issues.append('missing trading partner code')
    if float(payload.get('InvoiceAmount') or payload.get('InvoiceAmount') or 0) <= 0:
        issues.append('non-positive amount')
    seg = settings.get('sage_gl_segment_map') or {}
    if seg and not local_nums:
        issues.append('no local GL accounts')
    return {
        'ok': not issues,
        'dry_run': True,
        'payload': payload,
        'profile_id': settings.get('sage_schema_profile_id'),
        'resources': profile.get('resources'),
        'issues': issues,
    }


def sage_sync_health_score(db, models, ledger_id: int) -> dict:
    dash = sage_drift_dashboard(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    inbox = dash.get('inbox') or {}
    score = 100
    score -= min(40, (dash.get('parity_warning_count') or 0) * 5)
    score -= min(30, len(inbox.get('ap_push_errors') or []) * 3)
    score -= min(20, len(inbox.get('vendor_conflicts') or []) * 2)
    score -= min(10, len(inbox.get('gl_conflicts') or []) * 2)
    score = max(0, score)
    grade = 'A' if score >= 90 else 'B' if score >= 75 else 'C' if score >= 60 else 'D'
    out = {
        'score': score,
        'grade': grade,
        'open_ar': dash.get('open_ar'),
        'open_ap': dash.get('open_ap'),
        'external_keys': dash.get('external_key_count'),
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['sage_sync_health'] = out
    _save_ledger_settings(ledger, settings)
    return out


def sage_admin_runbook(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sor = settings.get('system_of_record') or 'casepm'
    steps = [
        'Configure Sage Web API URL and credentials in Program Settings.',
        'Apply a profile pack: POST /api/accounting/sage/profile-packs/apply.',
        'Pull masters: vendors, customers, GL (Sage hybrid toolbar).',
        'Push open AP/AR with idempotent live push; pull AR receipts v2 + AP payments.',
        'POST /api/accounting/cron/sage-production nightly.',
    ]
    if sor == 'sage':
        steps.insert(2, 'Case PM construction auto-post is restricted — use bridge or enable sage_allow_construction_casepm_post.')
    return {
        'system_of_record': sor,
        'recommended_cron': ['/api/accounting/cron/sage-mirror-full', '/api/accounting/cron/sage-production'],
        'steps': steps,
        'read_only_mode': settings.get('sage_read_only_mode') == '1',
    }


def load_fixture_row(fixture_name: str) -> dict:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), 'sage300_fixtures'))
    path = os.path.join(root, fixture_name)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def validate_fixture_against_profile(fixture_name: str, profile: dict) -> dict:
    data = load_fixture_row(fixture_name)
    rows = data.get('value') or []
    if not rows:
        return {'ok': False, 'error': 'empty fixture'}
    row = rows[0]
    fields = profile.get('fields') or {}
    found = {}
    for logical, keys in fields.items():
        for k in keys:
            if k in row:
                found[logical] = k
                break
    return {'ok': bool(found.get('invoice_number') or found.get('receipt_number')), 'mapped_fields': found}


# --- Wave 34 ---

def sage_drift_panel_payload(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    dash = sage_drift_dashboard(db, models, ledger_id)
    health = settings.get('sage_sync_health') or sage_sync_health_score(db, models, ledger_id)
    queue = settings.get('sage_construction_mirror_queue') or []
    return {
        'dashboard': dash,
        'health': health,
        'construction_queue': queue[-15:],
        'merge_resolutions': (settings.get('sage_merge_resolutions') or [])[-10:],
    }


def sage_merge_compare(db, models, ledger_id: int, entity_type: str, code: str) -> dict:
    from accounting_waves_19 import sage_vendor_conflict_review
    from accounting_waves_20 import sage_gl_account_conflict_review

    if entity_type == 'vendor':
        box = sage_vendor_conflict_review(db, models, ledger_id, limit=200)
        hits = [c for c in (box.get('conflicts') or []) if c.get('code') == code]
        return {'type': 'vendor', 'code': code, 'conflicts': hits}
    if entity_type == 'gl':
        box = sage_gl_account_conflict_review(db, models, ledger_id, limit=200)
        hits = [c for c in (box.get('conflicts') or []) if c.get('account_number') == code]
        return {'type': 'gl', 'code': code, 'conflicts': hits}
    return {'type': entity_type, 'code': code, 'conflicts': []}


def cron_weekly_drift_digest(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    sent = []
    for ledger in AcctLedger.query.limit(20).all():
        health = sage_sync_health_score(db, models, ledger.id)
        if health.get('score', 100) >= 90:
            continue
        try:
            from program_settings_persistence import load_program_settings
            from email_notifications import send_workflow_email

            email = (load_program_settings().get('email') or {}).get('admin_notification_email') or ''
            if email.strip():
                body = f'Weekly Sage drift: ledger {ledger.id} health {health.get("grade")} ({health.get("score")}).'
                send_workflow_email(email.strip(), 'Case PM — weekly Sage drift digest', f'<p>{body}</p>', body)
                sent.append(ledger.id)
        except Exception:
            pass
    return {'emailed_ledgers': sent}


def sage_sync_audit_export(db, models, ledger_id: int, limit: int = 100) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = (settings.get('sage_sync_log') or [])[-limit:]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['at', 'direction', 'entity', 'detail'])
    for row in log:
        w.writerow([
            row.get('at'),
            row.get('direction'),
            row.get('entity'),
            json.dumps({k: v for k, v in row.items() if k not in ('at', 'direction', 'entity')})[:200],
        ])
    return {'csv': buf.getvalue(), 'row_count': len(log)}


# --- Wave 35 ---

def assert_sor_for_posting(db, models, ledger_id: int, area: str) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    sor_guard_extended(_ledger_settings(ledger), area, 'casepm_write')


def assert_not_sage_read_only(db, models, ledger_id: int) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    if (_ledger_settings(ledger).get('sage_read_only_mode') or '') == '1':
        raise PermissionError('Sage read-only mode — local posting disabled')


def sage_payroll_banner_state(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sor = settings.get('payroll_system_of_record') or 'casepm'
    pr_push = settings.get('sage_pr_push_enabled') == '1'
    return {
        'payroll_system_of_record': sor,
        'sage_pr_push_enabled': pr_push,
        'banner': 'Payroll is maintained in Sage 300 — Case PM payroll post is disabled.' if sor == 'sage' and not pr_push else None,
        'casepm_locked': sor == 'sage' and not pr_push,
    }


def cron_wh347_project_scan(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    if not Project:
        return {'scanned': 0}
    from accounting_waves_26 import scheduled_wh347_sage_labor_compare

    we = date.today().isoformat()
    results = []
    for p in Project.query.filter_by(status='Active').limit(30).all():
        try:
            AcctLedger = models['AcctLedger']
            lid = AcctLedger.query.first().id if AcctLedger.query.first() else 1
            r = scheduled_wh347_sage_labor_compare(db, models, lid, p.id, we, Project=Project)
            warns = len(r.get('prevailing_compare_warnings') or [])
            if warns:
                results.append({'project_id': p.id, 'warnings': warns})
        except Exception as exc:
            results.append({'project_id': p.id, 'error': str(exc)[:80]})
    return {'week_ending': we, 'flagged': results}


def filing_bundle_download(db, models, ledger_id: int, tax_year: int, user_id=None) -> dict:
    from accounting_waves_27 import export_filing_bundle_1099_w2
    from accounting_parity_wave3 import export_w2_summary

    bundle = export_filing_bundle_1099_w2(db, models, ledger_id, tax_year, user_id=user_id)
    w2 = export_w2_summary(db, models, ledger_id, tax_year)
    w2_csv = io.StringIO()
    w = csv.writer(w2_csv)
    w.writerow(['employee_number', 'name', 'wages'])
    for emp in (w2.get('employees') or []):
        w.writerow([emp.get('employee_number'), emp.get('name'), emp.get('wages')])
    return {
        **bundle,
        'w2_csv': w2_csv.getvalue(),
        'download_filename': f'casepm-filing-{tax_year}.json',
        'bundle_json': json.dumps(bundle, indent=2),
    }


def set_document_line_tax(db, models, ledger_id: int, document_type: str, document_id: int, lines: list, user_id=None) -> dict:
    """Wave 35 — store tax components on document line array in details_json."""
    cls = models['AcctAPDocument'] if document_type == 'ap' else models['AcctARDocument']
    doc = cls.query.filter_by(id=int(document_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Document not found')
    meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
    meta['line_tax'] = lines[:200]
    doc.details_json = json.dumps(meta)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='line_tax_set', details={'document_id': doc.id, 'lines': len(lines)})
    return {'document_id': doc.id, 'line_count': len(lines)}


# --- Wave 36 ---

def resolve_ledger_for_company(db, models, company_code: str) -> dict:
    AcctLedger = models['AcctLedger']
    ledgers = AcctLedger.query.limit(50).all()
    for ledger in ledgers:
        settings = _ledger_settings(ledger)
        for co in settings.get('sage_companies') or []:
            code = co.get('code') if isinstance(co, dict) else str(co)
            if code and code.upper() == (company_code or '').upper():
                return {'ledger_id': ledger.id, 'company_code': code}
    first = ledgers[0] if ledgers else None
    return {'ledger_id': first.id if first else None, 'company_code': company_code, 'fallback': True}


def enforce_gl_security_policy(db, models, ledger_id: int, batch, user_id=None, role_key: str | None = None) -> None:
    from accounting_enforcement import enforce_gl_security_on_batch

    enforce_gl_security_on_batch(models, ledger_id, batch, user_id=user_id, role_key=role_key or 'accounting')


def paginated_open_documents(db, models, ledger_id: int, doc_type: str, offset: int = 0, limit: int = 50) -> dict:
    limit = min(200, max(1, int(limit)))
    offset = max(0, int(offset))
    if doc_type == 'ar':
        cls = models['AcctARDocument']
    else:
        cls = models['AcctAPDocument']
    q = cls.query.filter_by(ledger_id=ledger_id, status='Open').order_by(cls.id)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    items = [
        {
            'id': d.id,
            'number': d.document_number,
            'amount': float(d.amount or 0),
            'amount_paid': float(d.amount_paid or 0),
            'sage_state': sage_sync_get(d, 'sync_state'),
        }
        for d in rows
    ]
    return {'total': total, 'offset': offset, 'limit': limit, 'items': items}


def month_close_wizard_state(db, models, ledger_id: int) -> dict:
    from accounting_waves_23 import month_end_cash_checklist
    checklist = month_end_cash_checklist(db, models, ledger_id)
    health = sage_sync_health_score(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    steps = [
        {'id': 'bank', 'label': 'Close bank periods', 'done': bool((checklist.get('recent_bank_closes') or []))},
        {'id': 'sage_pull', 'label': 'Pull AR cash & AP payments from Sage', 'done': bool(settings.get('sage_last_auto_retry_at'))},
        {'id': 'health', 'label': 'Sage sync health B or better', 'done': (health.get('score') or 0) >= 75},
        {'id': 'reports', 'label': 'Schedule month-end reports', 'done': bool(settings.get('last_filing_bundle'))},
    ]
    ready = all(s['done'] for s in steps[:3])
    return {'steps': steps, 'ready': ready, 'checklist': checklist, 'health': health}


def save_sage_read_only_mode(db, models, ledger_id: int, enabled: bool, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_read_only_mode'] = '1' if enabled else '0'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_read_only', details={'enabled': enabled})
    return {'sage_read_only_mode': settings['sage_read_only_mode']}


def cron_waves_33_36_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_27 import cron_waves_29_32_maintenance

    base = cron_waves_29_32_maintenance(db, models, secret, Project=Project)
    digest = cron_weekly_drift_digest(db, models, secret)
    wh347 = cron_wh347_project_scan(db, models, secret, Project=Project)
    AcctLedger = models['AcctLedger']
    health = []
    for ledger in AcctLedger.query.limit(10).all():
        health.append(sage_sync_health_score(db, models, ledger.id))
    return {'base': base, 'weekly_digest': digest, 'wh347': wh347, 'health_scores': health}


def sage_mirror_deploy_check_v4() -> dict:
    from accounting_waves_27 import sage_mirror_deploy_check_v3

    base = sage_mirror_deploy_check_v3()
    fix = validate_fixture_against_profile('ar_receipt_batch_sample.json', get_pack_profile())
    ok = base.get('ok') and fix.get('ok')
    return {'ok': ok, 'v3': base, 'fixture_validation': fix}


def get_pack_profile() -> dict:
    from sage300_profile_packs import get_pack

    return get_pack('sage300_cre_2024')
