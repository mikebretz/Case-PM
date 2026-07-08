"""Sage 300 CRE sync processor — posts or simulates posting for pay app / CO events."""
from __future__ import annotations

import json
import os
from datetime import datetime

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
    'BudgetSaved': {'module': 'JobCost', 'action': 'save_budget'},
    'BudgetPublished': {'module': 'JobCost', 'action': 'publish_budget'},
    'BudgetSageSync': {'module': 'JobCost', 'action': 'sync_cost_codes'},
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
    project = Project.query.get(project_id)
    if not project:
        return {}
    details = {}
    if project.details_json:
        try:
            details = json.loads(project.details_json)
        except (TypeError, json.JSONDecodeError):
            details = {}
    return {
        'project_id': project_id,
        'sage_job_number': project.sage_job_number or project.accounting_project_number or '',
        'sage_contract_number': details.get('sage_contract_number', ''),
        'sage_billings_account': details.get('sage_billings_account', ''),
        'sage_wip_account': details.get('sage_wip_account', ''),
        'sage_ar_customer_code': details.get('sage_ar_customer_code', ''),
    }


def build_sage_payload(event_type, project_ctx, payload):
    mapping = SAGE_EVENT_MAP.get(event_type, {'module': 'General', 'action': 'sync'})
    data = payload or {}
    # Commitment events: use type-specific Sage module/action when commitment_type present
    if event_type.startswith('Commitment') and data.get('commitment_type'):
        type_map = COMMITMENT_SAGE_TYPE_MAP.get(data['commitment_type'], {})
        if type_map:
            mapping = dict(mapping)
            mapping['module'] = type_map.get('module', mapping['module'])
            if event_type == 'CommitmentSubmitted':
                mapping['action'] = type_map.get('submit', mapping['action'])
            elif event_type in ('CommitmentApproved', 'CommitmentExecuted'):
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
):
    ctx = _project_sage_context(Project, project_id)
    sage_payload = build_sage_payload(event_type, ctx, payload)

    event = SageSyncEvent(
        project_id=project_id,
        event_type=event_type,
        status='queued',
        sage_job_number=ctx.get('sage_job_number') or '',
        message=message or f'{event_type} queued',
        payload_json=json.dumps(sage_payload),
        created_by_id=user_id,
    )
    db.session.add(event)
    db.session.flush()

    if auto_process:
        process_sage_event(event, db, Commitment=Commitment)

    db.session.commit()
    return event


def process_sage_event(event, db, Commitment=None):
    if not event or event.status == 'posted':
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
        'sage_job_number': event.sage_job_number,
        'message': event.message,
        'payload': json.loads(event.payload_json) if event.payload_json else None,
        'response': json.loads(event.response_json) if event.response_json else None,
        'error': event.error_text,
        'created_at': event.created_at.isoformat() if event.created_at else None,
        'posted_at': event.posted_at.isoformat() if event.posted_at else None,
    }
