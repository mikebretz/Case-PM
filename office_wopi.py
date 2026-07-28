"""WOPI handlers for LibreOffice Online (Collabora) document editing."""
from __future__ import annotations

import os
from datetime import datetime

from flask import Response, jsonify, request

from office_editor_service import (
    ensure_office_file_on_disk,
    extension_for_document,
    verify_wopi_token,
    wopi_check_file_info,
)


def _token_payload():
    token = request.args.get('access_token') or request.headers.get('X-WOPI-AccessToken') or ''
    return verify_wopi_token(token)


def _load_authorized_document(doc_id: int, *, Document, Project, User, db):
    payload = _token_payload()
    if not payload or int(payload.get('doc_id', -1)) != int(doc_id):
        return None, None, None, (jsonify({'error': 'Invalid or missing WOPI access token.'}), 401)
    user = User.query.get(int(payload['user_id']))
    if not user:
        return None, None, None, (jsonify({'error': 'Unknown user.'}), 403)
    doc = Document.query.get(doc_id)
    if not doc or doc.deleted_at:
        return None, None, None, (jsonify({'error': 'Document not found.'}), 404)
    try:
        from financial_security import require_financial_project_access
        require_financial_project_access(user, doc.project_id, Project)
    except (ValueError, PermissionError) as exc:
        return None, None, None, (jsonify({'error': str(exc)}), 403)
    return doc, user, payload, None


def handle_wopi_check_file_info(doc_id: int, *, Document, Project, User, db, upload_root: str):
    doc, user, payload, err = _load_authorized_document(doc_id, Document=Document, Project=Project, User=User, db=db)
    if err:
        return err
    write = bool(payload.get('write', True))
    path = ensure_office_file_on_disk(doc, upload_root=upload_root, User=User)
    db.session.commit()
    info = wopi_check_file_info(doc, user, file_path=path, write=write)
    return jsonify(info)


def handle_wopi_get_file(doc_id: int, *, Document, Project, User, db, upload_root: str):
    doc, user, _payload, err = _load_authorized_document(doc_id, Document=Document, Project=Project, User=User, db=db)
    if err:
        return err
    path = ensure_office_file_on_disk(doc, upload_root=upload_root, User=User)
    db.session.commit()
    if not os.path.isfile(path):
        return jsonify({'error': 'File missing on disk.'}), 404
    with open(path, 'rb') as fh:
        data = fh.read()
    ext = extension_for_document(doc)
    mime = doc.mime_type or (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        if ext in ('xlsx', 'xls', 'csv', 'ods')
        else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    return Response(data, mimetype=mime)


def handle_wopi_put_file(doc_id: int, *, Document, Project, User, db, upload_root: str):
    doc, user, payload, err = _load_authorized_document(doc_id, Document=Document, Project=Project, User=User, db=db)
    if err:
        return err
    if not payload.get('write', True):
        return jsonify({'error': 'Read-only WOPI token.'}), 403
    path = ensure_office_file_on_disk(doc, upload_root=upload_root, User=User)
    body = request.get_data()
    if not body:
        return jsonify({'error': 'Empty file body.'}), 400
    with open(path, 'wb') as fh:
        fh.write(body)
    doc.file_size = len(body)
    doc.updated_at = datetime.utcnow()
    doc.editor_content = None
    try:
        from document_features import file_content_hash
        doc.content_hash = file_content_hash(body)
    except Exception:
        pass
    db.session.commit()
    return jsonify({'LastModifiedTime': doc.updated_at.isoformat() + 'Z'})


def handle_wopi_file(doc_id: int, *, Document, Project, User, db, upload_root: str):
    override = (request.headers.get('X-WOPI-Override') or '').upper()
    if request.method == 'GET':
        return handle_wopi_check_file_info(doc_id, Document=Document, Project=Project, User=User, db=db, upload_root=upload_root)
    if request.method == 'POST' and override == 'PUT':
        return handle_wopi_put_file(doc_id, Document=Document, Project=Project, User=User, db=db, upload_root=upload_root)
    if request.method == 'POST' and override in ('LOCK', 'UNLOCK', 'REFRESH_LOCK', 'GET_LOCK'):
        return Response(status=200)
    return jsonify({'error': 'Unsupported WOPI operation.'}), 501


def handle_wopi_contents(doc_id: int, *, Document, Project, User, db, upload_root: str):
    if request.method in ('GET', 'HEAD'):
        return handle_wopi_get_file(doc_id, Document=Document, Project=Project, User=User, db=db, upload_root=upload_root)
    if request.method in ('POST', 'PUT'):
        return handle_wopi_put_file(doc_id, Document=Document, Project=Project, User=User, db=db, upload_root=upload_root)
    return jsonify({'error': 'Method not allowed.'}), 405
