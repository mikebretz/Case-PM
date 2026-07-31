"""Tier-2 platform features — mobile field, payments, OCR, push, 4D BIM, integrations."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date

import fitz

# In-memory SSE subscribers: user_id -> list of queues (simplified via generator polling)
_sse_last_check = {}


def notification_sse_stream(user_id, Notification, db):
    """Generator for Server-Sent Events notification updates."""
    last_id = 0
    yield 'event: ping\ndata: {}\n\n'
    while True:
        try:
            latest = Notification.query.filter_by(user_id=user_id).order_by(
                Notification.id.desc()
            ).first()
            if latest and latest.id > last_id:
                last_id = latest.id
                payload = json.dumps({
                    'id': latest.id,
                    'title': latest.title,
                    'message': latest.message,
                    'is_read': latest.is_read,
                })
                yield f'event: notification\ndata: {payload}\n\n'
            else:
                yield 'event: ping\ndata: {}\n\n'
        except Exception:
            yield 'event: ping\ndata: {}\n\n'
        time.sleep(4)


def save_push_subscription(db, PushSubscription, user_id, body):
    endpoint = body.get('endpoint')
    if not endpoint:
        raise ValueError('endpoint required')
    existing = PushSubscription.query.filter_by(user_id=user_id, endpoint=endpoint).first()
    if existing:
        existing.keys_json = json.dumps(body.get('keys') or {})
        db.session.commit()
        return existing
    row = PushSubscription(
        user_id=user_id,
        endpoint=endpoint,
        keys_json=json.dumps(body.get('keys') or {}),
    )
    db.session.add(row)
    db.session.commit()
    return row


def process_contractor_payment(amount, payee, method, project_id, user_id, metadata=None):
    """Process ACH/card via Stripe when configured, else simulate."""
    amount = float(amount or 0)
    if amount <= 0:
        raise ValueError('Amount must be positive')
    stripe_key = os.environ.get('STRIPE_SECRET_KEY', '').strip()
    ref = f'casepm-{uuid.uuid4().hex[:12]}'
    if stripe_key:
        try:
            import urllib.parse
            data = urllib.parse.urlencode({
                'amount': int(round(amount * 100)),
                'currency': 'usd',
                'description': f'Case PM payment — {payee}',
                'metadata[project_id]': str(project_id or ''),
                'metadata[user_id]': str(user_id or ''),
            }).encode()
            req = urllib.request.Request(
                'https://api.stripe.com/v1/payment_intents',
                data=data,
                headers={'Authorization': f'Bearer {stripe_key}', 'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            ref = result.get('id') or ref
            status = result.get('status') or 'processing'
            return {'ok': True, 'provider': 'stripe', 'reference': ref, 'status': status, 'amount': amount}
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ValueError(f'Stripe payment failed: {exc}') from exc
    return {
        'ok': True,
        'provider': 'simulated',
        'reference': ref,
        'status': 'simulated_ach',
        'amount': amount,
        'message': f'Simulated {method or "ACH"} payment of ${amount:,.2f} to {payee}. Set STRIPE_SECRET_KEY for live processing.',
    }


def build_transmittal_package(row, Project, upload_folder, attachment_paths=None):
    """Merge cover sheet + attachment PDFs into one package."""
    from extended_platform_persistence import _parse_json
    from transmittal_pdf import build_transmittal_pdf

    simple = _parse_json(row.simple_fields_json) or {}
    advanced = _parse_json(row.advanced_fields_json) or {}
    project = Project.query.get(row.project_id) if row.project_id else None
    cover = build_transmittal_pdf({**simple, **advanced, 'id': row.id, 'title': row.title}, project, [])

    merged = fitz.open(stream=cover, filetype='pdf')
    paths = attachment_paths or []
    att_ids = advanced.get('attachment_ids') or advanced.get('document_ids') or ''
    if isinstance(att_ids, str) and att_ids.strip():
        for part in re.split(r'[,\s]+', att_ids.strip()):
            if not part:
                continue
            try:
                from app import Document
                doc = Document.query.get(int(part))
                if doc and doc.stored_path and os.path.isfile(doc.stored_path) and doc.stored_path.lower().endswith('.pdf'):
                    paths.append(doc.stored_path)
            except (TypeError, ValueError):
                pass

    for path in paths:
        if os.path.isfile(path) and path.lower().endswith('.pdf'):
            try:
                att = fitz.open(path)
                merged.insert_pdf(att)
                att.close()
            except Exception:
                pass

    out = merged.tobytes()
    merged.close()
    return out


def ocr_invoice_pdf(file_path):
    """Extract invoice fields from PDF using PyMuPDF text (+ optional tesseract for scans)."""
    text = ''
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text() + '\n'
        doc.close()
    except Exception:
        pass
    if len(text.strip()) < 40 and os.environ.get('TESSERACT_CMD'):
        try:
            import pytesseract
            from PIL import Image
            import io
            doc = fitz.open(file_path)
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            text = pytesseract.image_to_string(img)
            doc.close()
        except Exception:
            pass

    amount = None
    m = re.search(r'(?:total|amount due|invoice total)[:\s]*\$?\s*([\d,]+\.?\d*)', text, re.I)
    if m:
        amount = float(m.group(1).replace(',', ''))
    inv_num = None
    m = re.search(r'(?:invoice\s*#?|inv\s*#?)[:\s]*([A-Z0-9\-]+)', text, re.I)
    if m:
        inv_num = m.group(1)
    vendor = None
    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    if lines:
        vendor = lines[0][:120]
    return {
        'raw_text': text[:4000],
        'invoice_number': inv_num,
        'amount': amount,
        'vendor_name': vendor,
    }


def match_invoice_to_commitment(ocr_data, Commitment, project_id):
    """Suggest commitment/SOV match from OCR extraction."""
    if not project_id or not Commitment:
        return []
    amount = ocr_data.get('amount')
    vendor = (ocr_data.get('vendor_name') or '').lower()
    matches = []
    for c in Commitment.query.filter_by(project_id=int(project_id)).limit(100):
        score = 0
        cname = (c.company_name or '').lower()
        if vendor and cname and (vendor in cname or cname in vendor):
            score += 50
        camt = float(c.current_amount or c.original_amount or 0)
        if amount and camt and abs(camt - amount) / max(camt, 1) < 0.15:
            score += 30
        if score > 0:
            matches.append({
                'commitment_id': c.id,
                'number': c.number,
                'company_name': c.company_name,
                'amount': camt,
                'score': score,
            })
    matches.sort(key=lambda x: -x['score'])
    return matches[:5]


def bim_4d_timeline(db, OperationsBimScheduleLink, OperationsBimAsset, asset_id, project_id):
    """Return schedule/cost links for 4D/5D viewer."""
    links = OperationsBimScheduleLink.query.filter_by(bim_asset_id=asset_id).all()
    if not links and project_id:
        # Seed demo links from schedule if none exist
        try:
            from app import ModuleState
            state = ModuleState.query.filter_by(module='schedule', state_key=f'project_{project_id}').first()
            if state and state.data_json:
                data = json.loads(state.data_json)
                tasks = (data.get('tasks') or data.get('activities') or [])[:20]
                for t in tasks:
                    link = OperationsBimScheduleLink(
                        bim_asset_id=asset_id,
                        project_id=project_id,
                        schedule_task_id=str(t.get('id') or t.get('uid') or ''),
                        task_name=t.get('name') or t.get('text') or 'Task',
                        start_date=_parse_date(t.get('start_date') or t.get('start')),
                        finish_date=_parse_date(t.get('end_date') or t.get('finish') or t.get('end')),
                        cost_code=t.get('cost_code') or '',
                        budget_amount=float(t.get('cost') or 0),
                    )
                    db.session.add(link)
                db.session.commit()
                links = OperationsBimScheduleLink.query.filter_by(bim_asset_id=asset_id).all()
        except Exception:
            pass
    asset = OperationsBimAsset.query.get(asset_id)
    return {
        'asset_id': asset_id,
        'title': asset.title if asset else '',
        'links': [{
            'id': l.id,
            'task_id': l.schedule_task_id,
            'task_name': l.task_name,
            'start_date': l.start_date.isoformat() if l.start_date else None,
            'finish_date': l.finish_date.isoformat() if l.finish_date else None,
            'cost_code': l.cost_code,
            'budget_amount': l.budget_amount,
            'element_id': l.model_element_id,
        } for l in links],
    }


def _parse_date(val):
    if not val:
        return None
    if isinstance(val, date):
        return val
    s = str(val)[:10]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def sync_procore_bidirectional(db, IntegrationSyncLog, project_id, user_id, models, direction='both'):
    """Pull and push RFIs/submittals with Procore."""
    from platform_gaps_services import _log_sync, _sync_procore
    logs = []
    if direction in ('pull', 'both'):
        logs.extend(_sync_procore(db, IntegrationSyncLog, project_id, user_id, models))
    Project = models['Project']
    RFI = models.get('RFI')
    api_url = (os.environ.get('PROCORE_API_URL') or '').rstrip('/')
    api_token = os.environ.get('PROCORE_API_TOKEN') or ''
    project = Project.query.get(project_id) if project_id else None
    procore_project_id = None
    if project and project.details_json:
        try:
            procore_project_id = json.loads(project.details_json).get('procore_project_id')
        except (TypeError, json.JSONDecodeError):
            pass
    if direction in ('push', 'both') and api_url and api_token and procore_project_id and RFI:
        pushed = 0
        for rfi in RFI.query.filter_by(project_id=project_id).filter(
            RFI.status.in_(['Open', 'Pending'])
        ).limit(10):
            if (rfi.reference or '').startswith('procore:'):
                continue
            try:
                body = json.dumps({
                    'rfi': {
                        'subject': rfi.subject,
                        'question': rfi.question or '',
                        'number': rfi.number,
                    }
                }).encode()
                req = urllib.request.Request(
                    f'{api_url}/rest/v1.0/projects/{procore_project_id}/rfis',
                    data=body,
                    headers={'Authorization': f'Bearer {api_token}', 'Content-Type': 'application/json'},
                    method='POST',
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode())
                rfi.reference = f'procore:{result.get("id", "")}'
                pushed += 1
            except Exception:
                pass
        db.session.commit()
        logs.append(_log_sync(db, IntegrationSyncLog, 'procore', 'push', 'rfis', project_id,
                              project_id, 'posted', f'Pushed {pushed} RFIs to Procore', user_id=user_id))
    return logs


def sync_autodesk_bidirectional(db, IntegrationSyncLog, project_id, user_id, models):
    """Autodesk Construction Cloud — model docs + issues sync."""
    aps_id = os.environ.get('AUTODESK_CLIENT_ID', '')
    aps_secret = os.environ.get('AUTODESK_CLIENT_SECRET', '')
    logs = []
    from platform_gaps_services import _log_sync
    if not aps_id or not aps_secret:
        logs.append(_log_sync(
            db, IntegrationSyncLog, 'autodesk', 'pull', 'docs', project_id,
            project_id, 'simulated',
            'Set AUTODESK_CLIENT_ID and AUTODESK_CLIENT_SECRET for live ACC sync.',
            user_id=user_id,
        ))
        return logs
    try:
        token_data = urllib.parse.urlencode({
            'client_id': aps_id,
            'client_secret': aps_secret,
            'grant_type': 'client_credentials',
            'scope': 'data:read',
        }).encode()
        req = urllib.request.Request(
            'https://developer.api.autodesk.com/authentication/v2/token',
            data=token_data,
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            token = json.loads(resp.read().decode()).get('access_token')
        if token:
            logs.append(_log_sync(db, IntegrationSyncLog, 'autodesk', 'pull', 'hub', project_id,
                                  project_id, 'posted', 'Authenticated with Autodesk Platform Services', user_id=user_id))
    except Exception as exc:
        logs.append(_log_sync(db, IntegrationSyncLog, 'autodesk', 'pull', 'hub', project_id,
                              project_id, 'error', str(exc), user_id=user_id))
    return logs


def client_portal_extended_feed(db, models, user, project_id):
    """Selections, draw requests, payments for owner portal."""
    from platform_gaps_services import build_client_portal_feed
    base = build_client_portal_feed(db, models, user, project_id)
    ClientPortalSelection = models['ClientPortalSelection']
    ClientPortalDrawRequest = models['ClientPortalDrawRequest']
    ClientPortalPayment = models['ClientPortalPayment']
    pid = int(project_id) if project_id else None
    selections, draws, payments = [], [], []
    if pid:
        selections = [{
            'id': s.id, 'title': s.title, 'category': s.category,
            'status': s.status, 'due_date': s.due_date.isoformat() if s.due_date else None,
            'selected_option': s.selected_option,
        } for s in ClientPortalSelection.query.filter_by(project_id=pid).order_by(ClientPortalSelection.created_at.desc()).limit(30)]
        draws = []
        for d in ClientPortalDrawRequest.query.filter_by(project_id=pid).limit(20):
            pkg = None
            if d.notes:
                try:
                    pkg = json.loads(d.notes)
                except (TypeError, json.JSONDecodeError):
                    pkg = None
            draws.append({
                'id': d.id, 'title': d.title, 'amount': d.amount, 'period': d.period, 'status': d.status,
                'package': pkg,
            })
        payments = [{
            'id': p.id, 'title': p.title, 'amount': p.amount, 'status': p.status, 'method': p.payment_method,
        } for p in ClientPortalPayment.query.filter_by(project_id=pid).limit(20)]
    base['selections'] = selections
    base['draw_requests'] = draws
    base['payments'] = payments
    return base


def process_field_offline_queue(db, models, user_id, items):
    """Sync offline field captures (daily log, punch, photos metadata)."""
    ExtendedModuleRecord = models['ExtendedModuleRecord']
    results = []
    for item in items or []:
        kind = item.get('type') or 'field_note'
        project_id = item.get('project_id')
        title = item.get('title') or f'Field capture {kind}'
        row = ExtendedModuleRecord(
            module_key='action_plans' if kind == 'punch' else 'tm_tickets',
            project_id=project_id,
            title=title,
            status='Submitted',
            simple_fields_json=json.dumps(item.get('simple') or {'notes': item.get('notes', '')}),
            advanced_fields_json=json.dumps(item.get('advanced') or {'offline_sync': True, 'captured_at': item.get('captured_at')}),
            created_by_id=user_id,
        )
        db.session.add(row)
        results.append({'type': kind, 'status': 'synced', 'title': title})
    db.session.commit()
    return {'synced': len(results), 'items': results}
