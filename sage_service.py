"""Sage 300 CRE sync processor — posts or simulates posting for pay app / CO events."""
from __future__ import annotations

import json
import os
from datetime import datetime

# Internal-only events that may post without accounting review
SAGE_AUTO_POST_EXEMPT = frozenset({
    'AccountingReconciled',
    'ManualSync',
    'BudgetSaved',
    'BudgetPublished',
    'BudgetSageSync',
})
# Map event types to Sage document categories (CRE module conventions)
SAGE_EVENT_MAP = {
    'G702Submitted': {'module': 'ProgressBilling', 'action': 'submit'},
    'G702Approved': {'module': 'ProgressBilling', 'action': 'post_ar'},
    'SubPayAppSubmitted': {'module': 'SubcontractorBilling', 'action': 'submit'},
    'SubPayAppApproved': {'module': 'SubcontractorBilling', 'action': 'post_ap'},
    'ChangeOrderApproved': {'module': 'PCO', 'action': 'post'},
    'PCOSubmitted': {'module': 'PCO', 'action': 'submit'},
    'PCOPromoted': {'module': 'PCO', 'action': 'promote'},
    'ChangeOrderSubmitted': {'module': 'PCO', 'action': 'submit_co'},
    'CommitmentChangeOrderSubmitted': {'module': 'Subcontracts', 'action': 'submit_cco'},
    'CommitmentChangeOrderApproved': {'module': 'Subcontracts', 'action': 'post_cco'},
    'ChangeEventCreated': {'module': 'PCO', 'action': 'change_event'},
    'RFQSubmitted': {'module': 'Subcontracts', 'action': 'submit_rfq'},
    'RFQQuoted': {'module': 'Subcontracts', 'action': 'quote_rfq'},
    'CPCOSubmitted': {'module': 'Subcontracts', 'action': 'submit_cpco'},
    'CPCOPromoted': {'module': 'Subcontracts', 'action': 'promote_cpco'},
    'CORSubmitted': {'module': 'PCO', 'action': 'submit_cor'},
    'CORApproved': {'module': 'PCO', 'action': 'approve_cor'},
    'BudgetSaved': {'module': 'JobCost', 'action': 'save_budget'},
    'BudgetPublished': {'module': 'JobCost', 'action': 'publish_budget'},
    'BudgetSageSync': {'module': 'JobCost', 'action': 'sync_cost_codes'},
    'AccountingReconciled': {'module': 'JobCost', 'action': 'reconcile_actuals'},
    'CommitmentSubmitted': {'module': 'AP', 'action': 'submit_commitment'},
    'CommitmentApproved': {'module': 'AP', 'action': 'post_commitment'},
    'CommitmentApprovalStep': {'module': 'AP', 'action': 'approval_step'},
    'CommitmentRejected': {'module': 'AP', 'action': 'reject_commitment'},
    'CommitmentVoided': {'module': 'AP', 'action': 'void_commitment'},
    'CommitmentUpdated': {'module': 'AP', 'action': 'update_commitment'},
    'CommitmentDocuSignSent': {'module': 'AP', 'action': 'docusign_sent'},
    'CommitmentExecuted': {'module': 'AP', 'action': 'commitment_executed'},
    'ManualSync': {'module': 'General', 'action': 'sync'},
}

# Sage CRE module/action overrides by commitment document type
COMMITMENT_SAGE_TYPE_MAP = {
    'Purchase Order': {'module': 'AP', 'doc_type': 'purchase_order', 'submit': 'create_po', 'post': 'post_po'},
    'Subcontract': {'module': 'Subcontracts', 'doc_type': 'subcontract', 'submit': 'create_subcontract', 'post': 'post_subcontract'},
    'Material Supply': {'module': 'AP', 'doc_type': 'material_order', 'submit': 'create_material_order', 'post': 'post_material_order'},
    'Service Agreement': {'module': 'AP', 'doc_type': 'service_agreement', 'submit': 'create_service_agreement', 'post': 'post_service_agreement'},
}


def _project_sage_context(Project, project_id):
    from program_settings_persistence import merge_sage_context, load_sage_defaults

    project = Project.query.get(project_id)
    if not project:
        return {}
    details = {}
    if project.details_json:
        try:
            details = json.loads(project.details_json)
        except (TypeError, json.JSONDecodeError):
            details = {}
    sage = merge_sage_context(details, load_sage_defaults())
    return {
        'project_id': project_id,
        'project_name': project.name or '',
        'project_number': project.number or '',
        'sage_job_number': project.sage_job_number or project.accounting_project_number or '',
        'sage_contract_number': details.get('sage_contract_number', '') or sage.get('sage_contract_number', ''),
        'sage_billings_account': sage.get('sage_billings_account', ''),
        'sage_wip_account': sage.get('sage_wip_account', ''),
        'sage_revenue_account': sage.get('sage_revenue_account', ''),
        'sage_ar_customer_code': details.get('sage_ar_customer_code', '') or sage.get('sage_ar_customer_code', ''),
        'sage_account_set': sage.get('sage_account_set', ''),
        'sage_accounting_method': sage.get('sage_accounting_method', ''),
        'sage_default_tax_group': sage.get('sage_default_tax_group', ''),
        'sage_company_code': sage.get('sage_company_code', ''),
        'sage_database': sage.get('sage_database', ''),
        'sage_ap_vendor_prefix': sage.get('sage_ap_vendor_prefix', ''),
        'sage_cost_code_prefix': sage.get('sage_cost_code_prefix', ''),
        'sage_subcontract_liability_account': sage.get('sage_subcontract_liability_account', ''),
        'sage_default_cost_type': sage.get('sage_default_cost_type', ''),
        'sage_sync_enabled': sage.get('sage_sync_enabled', '1') != '0',
        'sage_defaults_source': 'program' if load_sage_defaults() else 'project',
        'contract_value': float(project.contract_value or 0),
        'original_contract_amount': details.get('original_contract_amount', ''),
        'prime_aia_form': details.get('prime_aia_form', ''),
        'owner_legal_name': details.get('owner_legal_name', '') or project.client or '',
        'contractor_legal_name': details.get('contractor_legal_name', ''),
        'catina_project_id': details.get('catina_project_id', ''),
    }


def build_sage_payload(event_type, project_ctx, payload):
    mapping = SAGE_EVENT_MAP.get(event_type, {'module': 'General', 'action': 'sync'})
    data = payload or {}
    # Commitment events: use type-specific Sage module/action when commitment_type present
    if (event_type.startswith('Commitment') or event_type.startswith('CommitmentChangeOrder')) and data.get('commitment_type'):
        type_map = COMMITMENT_SAGE_TYPE_MAP.get(data['commitment_type'], {})
        if type_map:
            mapping = dict(mapping)
            mapping['module'] = type_map.get('module', mapping['module'])
            if event_type in ('CommitmentSubmitted', 'CommitmentChangeOrderSubmitted'):
                mapping['action'] = type_map.get('submit', mapping['action'])
            elif event_type in ('CommitmentApproved', 'CommitmentExecuted', 'CommitmentChangeOrderApproved'):
                mapping['action'] = type_map.get('post', mapping['action'])
            data = {**data, 'sage_document_type': type_map.get('doc_type')}
    return {
        'source': 'CasePM',
        'event_type': event_type,
        'sage_module': mapping['module'],
        'sage_action': mapping['action'],
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'project': project_ctx,
        'data': data,
    }


def _try_live_post(sage_payload):
    """
    Attempt live Sage post when SAGE_API_URL is configured.
    Returns (success: bool, response: dict|None, error: str|None)
    """
    api_url = os.environ.get('SAGE_API_URL', '').strip()
    api_key = os.environ.get('SAGE_API_KEY', '').strip()
    if not api_url:
        return False, None, None

    try:
        import urllib.request
        req = urllib.request.Request(
            api_url.rstrip('/') + '/api/v1/transactions',
            data=json.dumps(sage_payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}' if api_key else '',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8')
            return True, json.loads(body) if body else {'status': 'ok'}, None
    except Exception as exc:
        return False, None, str(exc)


def create_and_process_sage_event(
    SageSyncEvent,
    Project,
    db,
    project_id,
    event_type,
    message='',
    payload=None,
    user_id=None,
    auto_process=True,
    Commitment=None,
    require_accounting_review=False,
    defer_commit=False,
):
    ctx = _project_sage_context(Project, project_id)
    sage_payload = build_sage_payload(event_type, ctx, payload)
    data = payload or {}
    idempotency_key = data.get('idempotency_key')
    if idempotency_key and SageSyncEvent is not None:
        recent = (
            SageSyncEvent.query
            .filter_by(project_id=project_id, event_type=event_type)
            .order_by(SageSyncEvent.created_at.desc())
            .limit(25)
            .all()
        )
        for ev in recent:
            try:
                pl = json.loads(ev.payload_json or '{}')
                inner = pl.get('data') if isinstance(pl.get('data'), dict) else pl
                if (inner or {}).get('idempotency_key') == idempotency_key and ev.status in ('posted', 'simulated', 'queued'):
                    return ev
            except (TypeError, json.JSONDecodeError):
                continue

    financial_events = {
        'ChangeOrderApproved', 'CommitmentChangeOrderApproved', 'CommitmentApproved',
        'G702Approved', 'SubPayAppApproved', 'CPCOPromoted', 'CORApproved', 'PCOPromoted',
        'ChangeOrderSubmitted', 'CommitmentChangeOrderSubmitted', 'PCOSubmitted',
        'CPCOSubmitted', 'CORSubmitted', 'RFQSubmitted', 'RFQQuoted', 'ChangeEventCreated',
    }
    # All Sage export events require Contractor Accounting review before auto-posting
    needs_review = require_accounting_review or event_type not in SAGE_AUTO_POST_EXEMPT

    event = SageSyncEvent(
        project_id=project_id,
        event_type=event_type,
        status='queued',
        sage_job_number=ctx.get('sage_job_number') or '',
        message=message or f'{event_type} queued',
        payload_json=json.dumps(sage_payload),
        created_by_id=user_id,
        accounting_status='pending_review' if needs_review else 'accepted',
    )
    db.session.add(event)
    db.session.flush()

    if auto_process and not needs_review:
        process_sage_event(event, db, Commitment=Commitment)
    elif needs_review:
        try:
            from change_event_persistence import notify_accounting_erp_review
            notify_accounting_erp_review(event, Project, db, User=None)
        except Exception:
            pass

    if defer_commit:
        db.session.flush()
    else:
        db.session.commit()
    return event


def process_sage_event(event, db, Commitment=None):
    if not event or event.status == 'posted':
        return event
    if getattr(event, 'accounting_status', None) == 'pending_review':
        return event

    if not event.sage_job_number:
        event.status = 'pending_config'
        event.error_text = 'Project sage_job_number not configured'
        if Commitment:
            _mirror_commitment_sage_status(db, Commitment, event)
        db.session.commit()
        return event

    try:
        payload = json.loads(event.payload_json or '{}')
    except (TypeError, json.JSONDecodeError):
        payload = {}

    ok, response, error = _try_live_post(payload)
    if ok:
        event.status = 'posted'
        event.posted_at = datetime.utcnow()
        event.response_json = json.dumps(response or {})
        event.error_text = None
    elif error:
        event.status = 'error'
        event.error_text = error
    else:
        event.status = 'simulated'
        event.posted_at = datetime.utcnow()
        event.response_json = json.dumps({
            'simulated': True,
            'note': 'SAGE_API_URL not set; transaction validated and logged for manual import or future connector',
            'sage_job': event.sage_job_number,
        })

    if Commitment:
        _mirror_commitment_sage_status(db, Commitment, event)
    db.session.commit()
    return event


def _mirror_commitment_sage_status(db, Commitment, event):
    try:
        payload = json.loads(event.payload_json or '{}')
    except (TypeError, json.JSONDecodeError):
        return
    data = payload.get('data') if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return
    cid = data.get('commitment_id')
    if not cid:
        return
    c = Commitment.query.get(int(cid))
    if not c:
        return
    if event.status == 'posted':
        c.sage_sync_status = 'sage_posted'
    elif event.status == 'simulated':
        c.sage_sync_status = 'sage_simulated'
    elif event.status == 'error':
        c.sage_sync_status = f"sage_error:{(event.error_text or '')[:48]}"
    elif event.status == 'pending_config':
        c.sage_sync_status = 'sage_pending_config'
    else:
        c.sage_sync_status = f'sage_{event.status}'
    db.session.flush()


def sage_event_to_dict(event):
    return {
        'id': event.id,
        'project_id': event.project_id,
        'event_type': event.event_type,
        'status': event.status,
        'accounting_status': getattr(event, 'accounting_status', None) or 'accepted',
        'accounting_notes': getattr(event, 'accounting_notes', None),
        'accounting_reviewed_at': event.accounting_reviewed_at.isoformat() if getattr(event, 'accounting_reviewed_at', None) else None,
        'sage_job_number': event.sage_job_number,
        'message': event.message,
        'payload': json.loads(event.payload_json) if event.payload_json else None,
        'response': json.loads(event.response_json) if event.response_json else None,
        'error': event.error_text,
        'created_at': event.created_at.isoformat() if event.created_at else None,
        'posted_at': event.posted_at.isoformat() if event.posted_at else None,
    }


def latest_sage_events_by_project(SageSyncEvent, project_ids):
    """Most recent SageSyncEvent per project_id (one query)."""
    if not project_ids:
        return {}
    events = (
        SageSyncEvent.query
        .filter(SageSyncEvent.project_id.in_(project_ids))
        .order_by(SageSyncEvent.created_at.desc())
        .all()
    )
    by_project = {}
    for event in events:
        if event.project_id not in by_project:
            by_project[event.project_id] = event
    return by_project


def project_sage_sync_status(project, latest_event=None):
    """Human-readable Sage 300 sync status for a project row."""
    details = project.get_details() if project and hasattr(project, 'get_details') else {}
    if details.get('sage_sync_enabled') == '0':
        return {
            'status': 'disabled',
            'label': 'Off',
            'class': 'text-zinc-500',
            'detail': 'Sage sync disabled for this project',
        }

    job = (
        (getattr(project, 'sage_job_number', None) or '')
        or (getattr(project, 'accounting_project_number', None) or '')
    ).strip()
    if not job:
        return {
            'status': 'no_job',
            'label': 'No job #',
            'class': 'text-amber-400',
            'detail': 'Set Sage job number on project',
        }

    if not latest_event:
        return {
            'status': 'ready',
            'label': 'Ready',
            'class': 'text-zinc-400',
            'detail': f'Job {job} — no sync events yet',
        }

    event_type = latest_event.event_type or 'Sync'
    status = latest_event.status or 'queued'
    if status == 'posted':
        return {
            'status': 'posted',
            'label': 'Synced',
            'class': 'text-emerald-400',
            'detail': f'{event_type} · posted',
        }
    if status == 'simulated':
        return {
            'status': 'simulated',
            'label': 'Logged',
            'class': 'text-sky-400',
            'detail': f'{event_type} · queued for Sage API',
        }
    if status == 'error':
        err = (latest_event.error_text or '')[:60]
        return {
            'status': 'error',
            'label': 'Error',
            'class': 'text-red-400',
            'detail': err or f'{event_type} failed',
        }
    if status == 'pending_config':
        return {
            'status': 'pending_config',
            'label': 'Config',
            'class': 'text-amber-400',
            'detail': latest_event.error_text or 'Sage job not configured',
        }
    if status == 'queued':
        return {
            'status': 'queued',
            'label': 'Queued',
            'class': 'text-amber-400',
            'detail': event_type,
        }
    return {
        'status': status,
        'label': status.replace('_', ' ').title(),
        'class': 'text-zinc-400',
        'detail': event_type,
    }


def _sage_http_get(path: str) -> dict | None:
    """GET from Sage bridge API. Returns None when not configured or on failure."""
    api_url = os.environ.get('SAGE_API_URL', '').strip()
    api_key = os.environ.get('SAGE_API_KEY', '').strip()
    if not api_url:
        return None
    try:
        import urllib.parse
        import urllib.request
        url = api_url.rstrip('/') + path
        req = urllib.request.Request(
            url,
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {api_key}' if api_key else '',
            },
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8')
            return json.loads(body) if body else {}
    except Exception:
        return None


def pull_sage_job_ledger(sage_job_number: str) -> dict:
    """Pull full job ledger from Sage (sub payments, owner billings, actuals)."""
    import urllib.parse

    job = (sage_job_number or '').strip()
    if not job:
        return {'found': False, 'error': 'sage_job_number required'}
    quoted = urllib.parse.quote(job)
    ledger = _sage_http_get(f'/api/v1/jobs/{quoted}/ledger')
    if ledger and ledger.get('found'):
        return ledger
    sub = _sage_http_get(f'/api/v1/jobs/{quoted}/sub-payments') or {}
    owner = _sage_http_get(f'/api/v1/jobs/{quoted}/owner-billings') or {}
    actuals = _sage_http_get(f'/api/v1/jobs/{quoted}/actuals') or {}
    if not any([sub.get('payments'), owner.get('billings'), actuals.get('actuals_by_cost_code')]):
        return {'found': False, 'job_number': job, 'mode': 'unavailable'}
    return {
        'found': True,
        'job_number': job,
        'sub_payments': sub.get('payments') or [],
        'vendor_paid_totals': sub.get('vendor_totals') or {},
        'owner_billings': owner.get('billings') or [],
        'actuals_by_cost_code': actuals.get('actuals_by_cost_code') or {},
    }


def apply_sage_pull_to_project(
    project_id,
    *,
    Project,
    Commitment,
    BudgetProjectState,
    PayAppProjectState,
    db,
    user_id=None,
    SageSyncEvent=None,
    ChangeOrder=None,
    ChangeOrderAllocation=None,
    CommitmentAllocation=None,
):
    """
    Pull sub payments and actuals from Sage and reconcile Case PM state.
    Returns a report with matched/mismatched vendor payments and budget actuals.
    """
    project = Project.query.get(project_id)
    if not project:
        return {'ok': False, 'error': 'project not found'}

    job = (project.sage_job_number or project.accounting_project_number or '').strip()
    if not job:
        return {'ok': False, 'error': 'sage_job_number not configured'}

    ledger = pull_sage_job_ledger(job)
    if not ledger.get('found'):
        return {
            'ok': True,
            'mode': 'simulated',
            'job_number': job,
            'note': 'SAGE_API_URL not set or Sage has no ledger for this job',
        }

    from accounting_reconcile import reconcile_project_accounting

    from pay_app_persistence import get_pay_app_state

    commitments = Commitment.query.filter_by(project_id=project_id).all()
    _, pay_state = get_pay_app_state(PayAppProjectState, project_id)
    vendor_totals = ledger.get('vendor_paid_totals') or {}

    sage_invoiced_updates = []
    for com in commitments:
        if com.commitment_type != 'Subcontract':
            continue
        cid = str(com.company_id or '').strip()
        sage_paid = float(vendor_totals.get(cid) or 0)
        if sage_paid <= 0:
            continue
        case_invoiced = float(getattr(com, 'invoiced_amount', 0) or 0)
        sage_invoiced_updates.append({
            'commitment_id': com.id,
            'number': com.number,
            'company_id': cid,
            'case_invoiced': case_invoiced,
            'sage_paid': sage_paid,
            'delta': round(sage_paid - case_invoiced, 2),
            'matched': abs(sage_paid - case_invoiced) < 500,
        })

    recon = reconcile_project_accounting(
        project_id, user_id,
        ChangeOrder=ChangeOrder,
        ChangeOrderAllocation=ChangeOrderAllocation,
        Commitment=Commitment,
        CommitmentAllocation=CommitmentAllocation,
        BudgetProjectState=BudgetProjectState,
        PayAppProjectState=PayAppProjectState,
        db=db,
    )

    sub_payments = ledger.get('sub_payments') or []
    total_sage_sub_paid = sum(float(p.get('amount') or 0) for p in sub_payments)
    sub_hist = pay_state.get('subPayAppHistory') or {}
    case_billed_by_vendor: dict[str, float] = {}
    for company_key, company_hist in sub_hist.items():
        vendor_total = 0.0
        for period_entry in (company_hist or {}).values():
            if isinstance(period_entry, dict) and period_entry.get('status') == 'Approved':
                vendor_total += float(period_entry.get('totalBilledThisPeriod') or 0)
        if vendor_total > 0:
            case_billed_by_vendor[str(company_key)] = vendor_total
    total_case_sub_billed = sum(case_billed_by_vendor.values())

    vendor_payment_checks = []
    for company_id, sage_paid in vendor_totals.items():
        sage_paid = float(sage_paid or 0)
        if sage_paid <= 0:
            continue
        case_billed = float(case_billed_by_vendor.get(str(company_id)) or 0)
        vendor_payment_checks.append({
            'company_id': str(company_id),
            'case_billed': case_billed,
            'sage_paid': sage_paid,
            'delta': round(sage_paid - case_billed, 2),
            'matched': abs(sage_paid - case_billed) < max(500, case_billed * 0.02),
        })

    # Fall back to commitment invoiced totals when pay-app history is sparse
    if not vendor_payment_checks and sage_invoiced_updates:
        vendor_payment_checks = [
            {
                'company_id': v['company_id'],
                'case_billed': v['case_invoiced'],
                'sage_paid': v['sage_paid'],
                'delta': v['delta'],
                'matched': v['matched'],
            }
            for v in sage_invoiced_updates
            if v.get('sage_paid', 0) > 0
        ]

    pull_ok = total_sage_sub_paid > 0 and (total_case_sub_billed > 0 or bool(vendor_payment_checks))
    payment_match = pull_ok and (
        not vendor_payment_checks
        or all(v.get('matched') for v in vendor_payment_checks)
    )

    if SageSyncEvent is not None:
        create_and_process_sage_event(
            SageSyncEvent, Project, db, project_id,
            'ManualSync',
            message=f'Sage pull — {len(sub_payments)} sub payments, ${total_sage_sub_paid:,.0f} paid',
            payload={
                'direction': 'inbound',
                'sub_payments_count': len(sub_payments),
                'total_sage_sub_paid': total_sage_sub_paid,
                'total_case_sub_billed': total_case_sub_billed,
                'vendor_totals': vendor_totals,
                'owner_billings_count': len(ledger.get('owner_billings') or []),
            },
            user_id=user_id,
        )

    return {
        'ok': True,
        'mode': 'live',
        'job_number': job,
        'sub_payments_count': len(sub_payments),
        'total_sage_sub_paid': total_sage_sub_paid,
        'total_case_sub_billed': total_case_sub_billed,
        'payment_match': payment_match,
        'vendor_payment_checks': vendor_payment_checks,
        'vendor_invoiced_checks': sage_invoiced_updates,
        'owner_billings_count': len(ledger.get('owner_billings') or []),
        'actuals_by_cost_code': ledger.get('actuals_by_cost_code') or {},
        'reconcile': {
            'actual_cost_applied': recon.get('actual_cost_applied'),
            'invoiced_updates': recon.get('invoiced_updates'),
        },
    }
