"""Plan room advanced features: Q&A, addenda ack, zip, ITB broadcast, external export."""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime

from bidder_network_services import (
    gather_plan_documents,
    plan_room_meta,
    plan_room_project_detail,
    project_in_plan_room,
)


def _registration_display(reg):
    if not reg:
        return ''
    return reg.company_name or ''


def clarification_to_dict(row) -> dict:
    return {
        'id': row.id,
        'project_id': row.project_id,
        'bid_package_id': row.bid_package_id,
        'subject': row.subject or '',
        'question_text': row.question_text,
        'answer_text': row.answer_text or '',
        'asker_company': row.asker_company or '',
        'asker_name': row.asker_name or '',
        'is_public': bool(row.is_public),
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'answered_at': row.answered_at.isoformat() if row.answered_at else None,
    }


def list_clarifications(db, PlanRoomClarification, project_id: int, *, public_only: bool = True) -> dict:
    q = PlanRoomClarification.query.filter_by(project_id=int(project_id)).order_by(PlanRoomClarification.id.desc())
    if public_only:
        q = q.filter(PlanRoomClarification.is_public.is_(True))
    rows = q.limit(200).all()
    return {'clarifications': [clarification_to_dict(r) for r in rows]}


def submit_clarification(db, models, project_id: int, user, body: dict) -> dict:
    PlanRoomClarification = models['PlanRoomClarification']
    BidderNetworkRegistration = models['BidderNetworkRegistration']
    Project = models['Project']
    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    text = (body.get('question_text') or body.get('question') or '').strip()
    if not text:
        raise ValueError('Question is required')
    subject = (body.get('subject') or 'Plan clarification').strip()[:300]
    reg = BidderNetworkRegistration.query.filter_by(user_id=user.id, status='approved').first()
    row = PlanRoomClarification(
        project_id=int(project_id),
        bid_package_id=body.get('bid_package_id'),
        asked_by_user_id=user.id,
        asker_company=reg.company_name if reg else (getattr(user, 'company', None) or ''),
        asker_name=reg.contact_name if reg else f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip(),
        subject=subject,
        question_text=text,
        is_public=True,
    )
    db.session.add(row)
    db.session.flush()
    return {'ok': True, 'clarification': clarification_to_dict(row)}


def answer_clarification(db, PlanRoomClarification, clarification_id: int, staff_user_id: int, body: dict) -> dict:
    row = PlanRoomClarification.query.get(int(clarification_id))
    if not row:
        raise ValueError('Question not found')
    answer = (body.get('answer_text') or body.get('answer') or '').strip()
    if not answer:
        raise ValueError('Answer is required')
    row.answer_text = answer
    row.answered_by_id = staff_user_id
    row.answered_at = datetime.utcnow()
    row.is_public = bool(body.get('is_public', True))
    return {'ok': True, 'clarification': clarification_to_dict(row)}


def user_addendum_ack_ids(db, PlanRoomAddendumAck, user_id: int, addendum_ids: list) -> set:
    if not addendum_ids:
        return set()
    rows = PlanRoomAddendumAck.query.filter(
        PlanRoomAddendumAck.user_id == int(user_id),
        PlanRoomAddendumAck.addendum_id.in_([int(x) for x in addendum_ids]),
    ).all()
    return {r.addendum_id for r in rows}


def acknowledge_addendum(db, PlanRoomAddendumAck, user_id: int, addendum_id: int) -> dict:
    existing = PlanRoomAddendumAck.query.filter_by(user_id=int(user_id), addendum_id=int(addendum_id)).first()
    if existing:
        return {'ok': True, 'already': True}
    db.session.add(PlanRoomAddendumAck(user_id=int(user_id), addendum_id=int(addendum_id)))
    return {'ok': True}


def enrich_addenda_with_acks(addenda: list, acked_ids: set) -> list:
    out = []
    for a in addenda:
        item = dict(a)
        item['requires_acknowledgment'] = True
        item['acknowledged'] = int(a.get('id', 0)) in acked_ids
        out.append(item)
    return out


def zip_plan_documents(db, models, project_id: int, *, package_id: int | None, upload_folder: str) -> tuple[bytes, str]:
    Document = models['Document']
    BidPackage = models['BidPackage']
    Project = models['Project']
    BidPackageAddendum = models['BidPackageAddendum']

    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    if package_id:
        pkg = BidPackage.query.get(int(package_id))
        if not pkg or int(pkg.project_id) != int(project_id):
            raise ValueError('Package not found')
        packages = [pkg]
        label = (pkg.number or pkg.title or f'package-{pkg.id}').replace('/', '-')
    else:
        packages = BidPackage.query.filter(
            BidPackage.project_id == int(project.id),
            BidPackage.network_published.is_(True),
        ).order_by(BidPackage.due_date.asc(), BidPackage.id).all()
        if not packages:
            packages = BidPackage.query.filter_by(project_id=project.id).all()
        label = project.number or f'project-{project.id}'
    docs = gather_plan_documents(db, Document, BidPackageAddendum, project, packages)
    if not docs:
        raise ValueError('No documents to download')

    buf = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            doc = Document.query.get(d['id'])
            if not doc:
                continue
            directory = os.path.join(upload_folder, 'documents', str(project.id))
            path = os.path.join(directory, doc.filename)
            if not os.path.isfile(path):
                continue
            fname = doc.original_filename or doc.filename or f'doc-{doc.id}'
            base = fname
            n = 1
            while fname in used_names:
                stem, dot, ext = base.rpartition('.')
                fname = f'{stem}_{n}.{ext}' if dot else f'{base}_{n}'
                n += 1
            used_names.add(fname)
            zf.write(path, arcname=fname)
    buf.seek(0)
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in label)[:60]
    return buf.getvalue(), f'plan-room-{safe}.zip'


def broadcast_plan_room_itb(db, models, project_id: int, *, package_id: int | None = None, notify_mode: str = 'both') -> dict:
    """Email / notify approved plan room bidders with ITB + plan room links."""
    Project = models['Project']
    BidPackage = models['BidPackage']
    BidderNetworkRegistration = models['BidderNetworkRegistration']
    User = models['User']

    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    meta = plan_room_meta(project)
    try:
        from email_notifications import send_workflow_email, notify_user_workflow, _base_url
        base = _base_url()
    except Exception:
        base = ''

    plan_url = f'{base}/plan-room/projects/{project.id}'
    login_url = f'{base}/login?next=/plan-room/projects/{project.id}'
    regs = BidderNetworkRegistration.query.filter_by(status='approved').all()
    pkg = BidPackage.query.get(int(package_id)) if package_id else None
    title = f'ITB: {project.name}'
    if pkg:
        title = f'ITB: {pkg.title or pkg.number} — {project.name}'
    body_text = meta.get('summary') or project.description or 'Plans and specifications are available in our electronic plan room.'
    sent = 0
    mode = (notify_mode or 'both').lower()

    for reg in regs:
        email = (reg.email or '').strip().lower()
        if not email:
            continue
        user = User.query.get(reg.user_id) if reg.user_id else None
        html = (
            f'<div style="font-family:sans-serif"><p>Hello {reg.contact_name or reg.company_name},</p>'
            f'<p>{body_text}</p><p><strong>Bid date:</strong> {meta.get("bid_date") or "See plan room"}</p>'
            f'<p><a href="{login_url}">Sign in to the plan room</a> · <a href="{plan_url}">View project</a></p></div>'
        )
        if mode in ('both', 'email'):
            try:
                send_workflow_email(email, title, html, body_text)
                sent += 1
            except Exception:
                pass
        if mode in ('both', 'in_app') and user:
            try:
                notify_user_workflow(
                    user,
                    title=title,
                    description=body_text[:500],
                    action_url=f'/plan-room/projects/{project.id}',
                    project_id=project.id,
                    module='Plan Room',
                    send_email=False,
                )
            except Exception:
                pass
    return {'ok': True, 'emails_sent': sent, 'recipients': len(regs)}


def export_external_network(db, models, project_id: int, provider: str, *, staff_user_id: int | None = None) -> dict:
    PlanRoomExternalSyncLog = models['PlanRoomExternalSyncLog']
    provider = (provider or 'buildingconnected').strip().lower()
    detail = plan_room_project_detail(db, models, int(project_id), staff_access=True)
    project = detail.get('project') or {}
    meta = detail.get('plan_room') or {}
    packages = detail.get('packages') or []
    export_payload = {
        'provider': provider,
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'project': {
            'id': project.get('id'),
            'number': project.get('number'),
            'name': project.get('name'),
            'location': project.get('location'),
            'bid_date': meta.get('bid_date'),
        },
        'itb': {
            'summary': meta.get('summary'),
            'instructions_html': meta.get('instructions_html'),
            'contact_email': meta.get('contact_email'),
        },
        'bid_packages': [
            {
                'id': p.get('id'),
                'number': p.get('number'),
                'title': p.get('title'),
                'spec_section': p.get('spec_section'),
                'due_date': p.get('due_date'),
            }
            for p in packages
        ],
        'documents': detail.get('documents') or [],
        'note': 'Import this JSON into your external network or use API when configured.',
    }
    log = PlanRoomExternalSyncLog(
        project_id=int(project_id),
        provider=provider,
        direction='export',
        status='success',
        summary_json=json.dumps({'document_count': len(export_payload['documents']), 'package_count': len(packages)}),
    )
    db.session.add(log)
    db.session.flush()
    return {
        'ok': True,
        'provider': provider,
        'export': export_payload,
        'log_id': log.id,
        'synced_at': log.created_at.isoformat() if log.created_at else None,
    }


def list_external_sync_logs(db, PlanRoomExternalSyncLog, project_id: int, limit=20) -> dict:
    rows = PlanRoomExternalSyncLog.query.filter_by(project_id=int(project_id)).order_by(
        PlanRoomExternalSyncLog.id.desc(),
    ).limit(limit).all()
    return {
        'logs': [{
            'id': r.id,
            'provider': r.provider,
            'direction': r.direction,
            'status': r.status,
            'summary': json.loads(r.summary_json) if r.summary_json else {},
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
    }
