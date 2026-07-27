"""Extended platform services — AI chat, report builder, payments, BIM."""
from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import datetime

REPORT_DATA_SOURCES = {
    'projects': {
        'label': 'Projects',
        'columns': ['id', 'name', 'status', 'contract_value', 'city', 'state'],
    },
    'commitments': {
        'label': 'Commitments',
        'columns': ['number', 'company_name', 'commitment_type', 'status', 'current_amount', 'invoiced_amount'],
    },
    'rfis': {
        'label': 'RFIs',
        'columns': ['number', 'subject', 'status', 'priority', 'due_date', 'ball_in_court_role'],
    },
    'change_orders': {
        'label': 'Change Orders',
        'columns': ['number', 'title', 'status', 'amount', 'contract_type', 'company_name'],
    },
    'operations': {
        'label': 'Operations Center Items',
        'columns': ['module_key', 'title', 'status', 'amount', 'record_date'],
    },
    'punch': {
        'label': 'Punch Items',
        'columns': ['number', 'description', 'status', 'priority', 'location', 'due_date'],
    },
}


def report_catalog():
    return {
        'sources': [
            {'key': k, 'label': v['label'], 'columns': v['columns']}
            for k, v in REPORT_DATA_SOURCES.items()
        ]
    }


def run_report(definition, db, models, project_id=None):
    """Execute a saved report definition and return rows + CSV."""
    from extended_platform_persistence import _parse_json

    adv = definition if isinstance(definition, dict) else _parse_json(getattr(definition, 'advanced_fields_json', None))
    if not isinstance(adv, dict):
        adv = {}
    source = (adv.get('data_source') or adv.get('report_type') or 'operations').lower()
    columns = adv.get('columns_json')
    if isinstance(columns, str):
        try:
            columns = json.loads(columns)
        except json.JSONDecodeError:
            columns = None
    if not columns:
        columns = REPORT_DATA_SOURCES.get(source, REPORT_DATA_SOURCES['operations'])['columns']

    rows = _query_report_source(source, columns, models, project_id)
    filters = adv.get('filters_json') or {}
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except json.JSONDecodeError:
            filters = {}
    status_filter = (filters.get('status') or '').strip()
    if status_filter:
        rows = [r for r in rows if str(r.get('status', '')).lower() == status_filter.lower()]

    csv_buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(csv_buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return {
        'source': source,
        'columns': columns,
        'row_count': len(rows),
        'rows': rows[:500],
        'csv': csv_buf.getvalue(),
        'generated_at': datetime.utcnow().isoformat() + 'Z',
    }


def _query_report_source(source, columns, models, project_id):
    Project = models['Project']
    Commitment = models['Commitment']
    RFI = models.get('RFI')
    ChangeOrder = models['ChangeOrder']
    ExtendedModuleRecord = models['ExtendedModuleRecord']
    PunchItem = models.get('PunchItem')
    rows = []

    if source == 'projects':
        q = Project.query
        for p in q.all():
            rows.append({c: getattr(p, c, None) for c in columns if hasattr(p, c)})
    elif source == 'commitments' and project_id:
        for c in Commitment.query.filter_by(project_id=int(project_id)).all():
            rows.append({col: getattr(c, col, None) for col in columns})
    elif source == 'rfis' and RFI and project_id:
        for r in RFI.query.filter_by(project_id=int(project_id)).all():
            row = {col: getattr(r, col, None) for col in columns}
            if 'due_date' in row and row['due_date']:
                row['due_date'] = row['due_date'].isoformat() if hasattr(row['due_date'], 'isoformat') else row['due_date']
            rows.append(row)
    elif source == 'change_orders' and project_id:
        for c in ChangeOrder.query.filter_by(project_id=int(project_id)).all():
            rows.append({col: getattr(c, col, None) for col in columns})
    elif source == 'punch' and PunchItem and project_id:
        for p in PunchItem.query.filter_by(project_id=int(project_id)).all():
            row = {col: getattr(p, col, None) for col in columns}
            if 'due_date' in row and row['due_date']:
                row['due_date'] = row['due_date'].isoformat() if hasattr(row['due_date'], 'isoformat') else row['due_date']
            rows.append(row)
    else:
        q = ExtendedModuleRecord.query
        if project_id:
            q = q.filter_by(project_id=int(project_id))
        for r in q.order_by(ExtendedModuleRecord.updated_at.desc()).limit(500).all():
            row = {
                'module_key': r.module_key,
                'title': r.title,
                'status': r.status,
                'amount': r.amount,
                'record_date': r.record_date.isoformat() if r.record_date else None,
            }
            rows.append({col: row.get(col) for col in columns})
    return rows


def ai_chat(db, models, project_id, thread_id, message, user_id):
    """Multi-turn AI assistant with project context (on-platform, no external API)."""
    from extended_platform_persistence import generate_ai_insight

    OperationsAiMessage = models['OperationsAiMessage']
    Project = models['Project']
    ExtendedModuleRecord = models['ExtendedModuleRecord']
    RFI = models.get('RFI')
    ChangeOrder = models['ChangeOrder']

    if not thread_id:
        thread_id = str(uuid.uuid4())
    user_msg = OperationsAiMessage(
        thread_id=thread_id,
        project_id=project_id,
        role='user',
        content=(message or '').strip(),
        created_by_id=user_id,
    )
    db.session.add(user_msg)
    db.session.flush()

    history = OperationsAiMessage.query.filter_by(thread_id=thread_id).order_by(
        OperationsAiMessage.id.asc()
    ).limit(20).all()
    prior = [h.content for h in history if h.role == 'user'][-3:]

    base = generate_ai_insight(
        project_id, 'ai_insights', message, Project, ExtendedModuleRecord, RFI, ChangeOrder,
    )
    from llm_service import chat_completion, llm_configured
    history_msgs = [{'role': h.role, 'content': h.content} for h in history if h.content][-8:]
    system = (
        'You are an expert construction project management assistant for Case PM. '
        'Answer questions about schedule, billing, RFIs, change orders, safety, and job cost. '
        'Be concise and actionable. Use bullet points when listing risks or next steps.'
    )
    llm_messages = history_msgs + [{'role': 'user', 'content': (message or '').strip()}]
    llm_text, provider = chat_completion(llm_messages, system_prompt=system)
    response = llm_text if llm_text else base
    asst = OperationsAiMessage(
        thread_id=thread_id,
        project_id=project_id,
        role='assistant',
        content=response,
        created_by_id=user_id,
    )
    db.session.add(asst)
    db.session.commit()
    return {
        'thread_id': thread_id,
        'response': response,
        'provider': provider if llm_text else 'rules',
        'llm_configured': llm_configured(),
        'messages': [{'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat() if m.created_at else None} for m in history + [asst]],
    }


def get_ai_thread(OperationsAiMessage, thread_id):
    msgs = OperationsAiMessage.query.filter_by(thread_id=thread_id).order_by(OperationsAiMessage.id.asc()).all()
    return [{'id': m.id, 'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat() if m.created_at else None} for m in msgs]


def process_payment_batch(db, models, batch_record, user_id):
    """Process payment batch: validate lien waivers, create lines, queue Sage event."""
    from extended_platform_persistence import _parse_json
    from pay_app_persistence import get_pay_app_state

    OperationsPaymentLine = models['OperationsPaymentLine']
    PayAppProjectState = models['PayAppProjectState']
    SageSyncEvent = models['SageSyncEvent']
    Project = models['Project']
    ExtendedModuleRecord = models['ExtendedModuleRecord']

    project_id = batch_record.project_id
    adv = _parse_json(batch_record.advanced_fields_json)
    invoice_ids = adv.get('invoice_ids') or []
    if isinstance(invoice_ids, str):
        try:
            invoice_ids = json.loads(invoice_ids)
        except json.JSONDecodeError:
            invoice_ids = [x.strip() for x in invoice_ids.split(',') if x.strip()]

    lines = []
    total = 0.0
    warnings = []

    _, pay_state = get_pay_app_state(PayAppProjectState, project_id) if project_id else ({}, {})
    sub_lien = (pay_state or {}).get('subLienWaivers') or {}

    for iid in invoice_ids:
        try:
            inv = ExtendedModuleRecord.query.filter_by(id=int(iid), module_key='vendor_invoices').first()
        except (TypeError, ValueError):
            inv = None
        if not inv:
            warnings.append(f'Invoice {iid} not found')
            continue
        amt = float(inv.amount or 0)
        total += amt
        inv_adv = _parse_json(inv.advanced_fields_json)
        vendor = inv_adv.get('vendor_name') or inv.title
        lien_ok = bool(sub_lien)  # simplified: warn if no lien data at all
        if not lien_ok:
            warnings.append(f'No lien waiver on file for {vendor} — verify before paying')
        line = OperationsPaymentLine(
            batch_record_id=batch_record.id,
            vendor_name=vendor,
            invoice_record_id=inv.id,
            amount=amt,
            status='Pending' if warnings else 'Ready',
            lien_waiver_ok=lien_ok,
        )
        db.session.add(line)
        lines.append(line)

    if not lines and batch_record.amount:
        line = OperationsPaymentLine(
            batch_record_id=batch_record.id,
            vendor_name=adv.get('payee') or 'Batch payee',
            amount=float(batch_record.amount or 0),
            status='Ready',
            lien_waiver_ok=True,
        )
        db.session.add(line)
        lines.append(line)
        total = float(batch_record.amount or 0)

    batch_record.status = 'Processed'
    batch_record.amount = total or batch_record.amount
    db.session.flush()

    if SageSyncEvent and Project and project_id:
        from sage_service import create_and_process_sage_event
        create_and_process_sage_event(
            SageSyncEvent, Project, db, project_id,
            'SubPayAppApproved',
            message=f'Payment batch {batch_record.number or batch_record.id} processed — ${total:,.2f}',
            payload={
                'batch_id': batch_record.id,
                'total': total,
                'line_count': len(lines),
                'idempotency_key': f'pay-batch-{batch_record.id}',
            },
            user_id=user_id,
        )

    db.session.commit()
    return {
        'total': total,
        'line_count': len(lines),
        'warnings': warnings,
        'lines': [{'vendor': l.vendor_name, 'amount': l.amount, 'status': l.status} for l in lines],
    }


def save_bim_asset(db, OperationsBimAsset, project_id, file_storage, upload_folder, user_id, meta=None):
    """Store BIM/model file and create asset record."""
    meta = meta or {}
    ext = (file_storage.filename or '').rsplit('.', 1)[-1].lower()
    allowed = {'glb', 'gltf', 'ifc', 'obj', 'fbx', 'pdf', 'dwg'}
    if ext not in allowed:
        raise ValueError(f'Unsupported model type .{ext}. Use: {", ".join(sorted(allowed))}')

    folder = os.path.join(upload_folder, 'bim', str(project_id or 'portfolio'))
    os.makedirs(folder, exist_ok=True)
    safe_name = f'{uuid.uuid4().hex[:12]}_{file_storage.filename}'
    path = os.path.join(folder, safe_name)
    file_storage.save(path)
    size = os.path.getsize(path)

    asset = OperationsBimAsset(
        project_id=project_id,
        filename=file_storage.filename,
        stored_path=path,
        file_ext=ext,
        file_size=size,
        discipline=(meta.get('discipline') or '').strip() or None,
        title=(meta.get('title') or file_storage.filename or 'Model').strip(),
        revision=(meta.get('revision') or '').strip() or None,
        created_by_id=user_id,
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def serialize_bim_asset(asset, url_for_fn=None):
    viewer = 'pdf' if asset.file_ext == 'pdf' else '3d' if asset.file_ext in ('glb', 'gltf', 'obj') else 'download'
    url = f'/api/operations/bim/{asset.id}/file' if asset.id else None
    return {
        'id': asset.id,
        'project_id': asset.project_id,
        'title': asset.title,
        'filename': asset.filename,
        'revision': asset.revision,
        'discipline': asset.discipline,
        'file_ext': asset.file_ext,
        'file_size': asset.file_size,
        'viewer_type': viewer,
        'file_url': url,
        'created_at': asset.created_at.isoformat() if asset.created_at else None,
    }
