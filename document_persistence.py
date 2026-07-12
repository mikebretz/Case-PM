"""Project document storage — Dropbox-style folders, files, and share links."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

SYSTEM_FOLDERS = [
    {'system_key': 'printed-output', 'name': 'Printed Output', 'description': 'Auto-saved prints from Case PM (locked)'},
    {'system_key': 'contracts', 'name': 'Contracts', 'description': 'Project contracts and agreements (locked)'},
    {'system_key': 'specifications', 'name': 'Specifications', 'description': 'Spec books and divisions (locked)'},
    {'system_key': 'drawings', 'name': 'Drawings', 'description': 'Drawing sets, sheets, and exports from the Drawings module (locked)'},
    {'system_key': 'rfis', 'name': 'RFIs', 'description': 'RFI attachments and exports (locked)'},
    {'system_key': 'submittals', 'name': 'Submittals', 'description': 'Submittal packages and shop drawings (locked)'},
    {'system_key': 'photos', 'name': 'Photos', 'description': 'Project photos and site images (locked)'},
    {'system_key': 'daily-logs', 'name': 'Daily Logs', 'description': 'Daily log attachments and exports (locked)'},
    {'system_key': 'safety', 'name': 'Safety', 'description': 'Safety records and OSHA reference documents (locked)'},
    {'system_key': 'meeting-minutes', 'name': 'Meeting Minutes', 'description': 'OAC, superintendent, and project meeting records (locked)'},
    {'system_key': 'my-files', 'name': 'My Files', 'description': 'Your project uploads'},
]

SYSTEM_SUBFOLDERS = [
    {'system_key': 'drawing-sets', 'name': 'Drawing Sets', 'parent_key': 'drawings', 'description': 'Full drawing sheets exported for sharing'},
    {'system_key': 'drawing-snips', 'name': 'Snips', 'parent_key': 'drawings', 'description': 'Snips captured from the Drawings viewer'},
]

LARGE_FILE_LINK_THRESHOLD = 10 * 1024 * 1024  # 10 MB — email offers link instead


def ensure_document_schema(engine, db) -> None:
    """Create or migrate document tables."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if 'document_folder' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_folder (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                parent_id INTEGER,
                name VARCHAR(200) NOT NULL,
                is_system INTEGER NOT NULL DEFAULT 0,
                system_key VARCHAR(80),
                created_by_id INTEGER,
                created_at DATETIME,
                deleted_at DATETIME
            )
        """))

    if 'document_share_link' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_share_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                token VARCHAR(80) NOT NULL UNIQUE,
                label VARCHAR(200),
                password_hash VARCHAR(256),
                expires_at DATETIME,
                max_downloads INTEGER,
                download_count INTEGER DEFAULT 0,
                allow_download INTEGER DEFAULT 1,
                created_by_id INTEGER,
                created_at DATETIME,
                revoked_at DATETIME
            )
        """))

    if 'document_folder_share_link' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_folder_share_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL,
                token VARCHAR(80) NOT NULL UNIQUE,
                label VARCHAR(200),
                password_hash VARCHAR(256),
                expires_at DATETIME,
                max_downloads INTEGER,
                download_count INTEGER DEFAULT 0,
                allow_browse INTEGER DEFAULT 1,
                allow_download INTEGER DEFAULT 1,
                allow_upload INTEGER DEFAULT 0,
                created_by_id INTEGER,
                created_at DATETIME,
                revoked_at DATETIME
            )
        """))

    if 'document_version' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                version_no INTEGER NOT NULL,
                filename VARCHAR(300) NOT NULL,
                original_filename VARCHAR(300),
                file_size INTEGER DEFAULT 0,
                mime_type VARCHAR(120),
                uploaded_by_id INTEGER,
                notes VARCHAR(500),
                created_at DATETIME
            )
        """))

    if 'document_comment' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_comment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))

    if 'document_activity' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                document_id INTEGER,
                folder_id INTEGER,
                user_id INTEGER,
                action VARCHAR(80) NOT NULL,
                detail_json TEXT,
                created_at DATETIME
            )
        """))

    if 'document_folder_permission' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_folder_permission (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                can_view INTEGER DEFAULT 1,
                can_upload INTEGER DEFAULT 0,
                can_manage INTEGER DEFAULT 0,
                created_at DATETIME,
                UNIQUE(folder_id, user_id)
            )
        """))

    if 'document' not in tables:
        db.session.execute(text("""
            CREATE TABLE document (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                folder_id INTEGER,
                name VARCHAR(300) NOT NULL,
                document_type VARCHAR(80) NOT NULL DEFAULT 'Other',
                filename VARCHAR(300) NOT NULL,
                original_filename VARCHAR(300),
                file_size INTEGER DEFAULT 0,
                mime_type VARCHAR(120),
                is_system_locked INTEGER DEFAULT 0,
                version_count INTEGER DEFAULT 1,
                source_drawing_id INTEGER,
                source_sheet VARCHAR(80),
                source_metadata_json TEXT,
                uploaded_by_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME,
                deleted_at DATETIME
            )
        """))
    else:
        cols = {c['name'] for c in insp.get_columns('document')}
        migrations = []
        if 'folder_id' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN folder_id INTEGER')
        if 'is_system_locked' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN is_system_locked INTEGER DEFAULT 0')
        if 'updated_at' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN updated_at DATETIME')
        if 'deleted_at' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN deleted_at DATETIME')
        if 'version_count' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN version_count INTEGER DEFAULT 1')
        if 'checked_out_by_id' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN checked_out_by_id INTEGER')
        if 'checked_out_at' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN checked_out_at DATETIME')
        if 'checkout_note' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN checkout_note VARCHAR(500)')
        if 'tags_json' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN tags_json TEXT')
        if 'custom_metadata_json' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN custom_metadata_json TEXT')
        if 'content_hash' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN content_hash VARCHAR(64)')
        if 'retention_until' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN retention_until DATETIME')
        if 'legal_hold' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN legal_hold INTEGER DEFAULT 0')
        if 'editor_kind' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN editor_kind VARCHAR(20)')
        if 'editor_content' not in cols:
            migrations.append('ALTER TABLE document ADD COLUMN editor_content TEXT')
        for sql in migrations:
            db.session.execute(text(sql))

        if 'document_folder' in tables:
            fcols = {c['name'] for c in insp.get_columns('document_folder')}
            if 'deleted_at' not in fcols:
                db.session.execute(text('ALTER TABLE document_folder ADD COLUMN deleted_at DATETIME'))

        if 'document_share_link' in tables:
            scols = {c['name'] for c in insp.get_columns('document_share_link')}
            if 'password_hash' not in scols:
                db.session.execute(text('ALTER TABLE document_share_link ADD COLUMN password_hash VARCHAR(256)'))
            if 'approval_status' not in scols:
                db.session.execute(text("ALTER TABLE document_share_link ADD COLUMN approval_status VARCHAR(20) DEFAULT 'approved'"))
            if 'approved_by_id' not in scols:
                db.session.execute(text('ALTER TABLE document_share_link ADD COLUMN approved_by_id INTEGER'))
            if 'approved_at' not in scols:
                db.session.execute(text('ALTER TABLE document_share_link ADD COLUMN approved_at DATETIME'))

        if 'document_folder_share_link' in tables:
            fscols = {c['name'] for c in insp.get_columns('document_folder_share_link')}
            if 'password_hash' not in fscols:
                db.session.execute(text('ALTER TABLE document_folder_share_link ADD COLUMN password_hash VARCHAR(256)'))
            if 'approval_status' not in fscols:
                db.session.execute(text("ALTER TABLE document_folder_share_link ADD COLUMN approval_status VARCHAR(20) DEFAULT 'approved'"))
            if 'approved_by_id' not in fscols:
                db.session.execute(text('ALTER TABLE document_folder_share_link ADD COLUMN approved_by_id INTEGER'))
            if 'approved_at' not in fscols:
                db.session.execute(text('ALTER TABLE document_folder_share_link ADD COLUMN approved_at DATETIME'))

    if 'document_folder_template' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_folder_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                project_type VARCHAR(80),
                description VARCHAR(500),
                folders_json TEXT NOT NULL,
                is_system INTEGER DEFAULT 0,
                created_at DATETIME
            )
        """))
        # Seed default templates
        defaults = [
            ('Commercial GC', 'Commercial', 'Standard commercial job folders', json.dumps([
                {'name': '01 — Bidding', 'children': [{'name': 'Estimates'}, {'name': 'Proposals'}]},
                {'name': '02 — Contracts', 'children': [{'name': 'Prime Contract'}, {'name': 'Subcontracts'}]},
                {'name': '03 — Meetings', 'children': [{'name': 'OAC Minutes'}, {'name': 'Internal'}]},
                {'name': '04 — Closeout', 'children': [{'name': 'Warranties'}, {'name': 'O&M Manuals'}]},
            ])),
            ('Healthcare', 'Healthcare', 'Healthcare / OSHPD style folders', json.dumps([
                {'name': 'Compliance', 'children': [{'name': 'ICRA'}, {'name': 'Inspections'}]},
                {'name': 'Commissioning', 'children': [{'name': 'TAB Reports'}, {'name': 'Functional Tests'}]},
            ])),
        ]
        for name, ptype, desc, folders in defaults:
            db.session.execute(
                text('INSERT INTO document_folder_template (name, project_type, description, folders_json, is_system, created_at) VALUES (:n,:t,:d,:f,1,:c)'),
                {'n': name, 't': ptype, 'd': desc, 'f': folders, 'c': datetime.utcnow().isoformat()},
            )

    if 'document_markup' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_markup (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                user_id INTEGER,
                user_name VARCHAR(150),
                layer VARCHAR(20) DEFAULT 'personal',
                markup_type VARCHAR(30) NOT NULL,
                geometry_json TEXT,
                style_json TEXT,
                label VARCHAR(300),
                measurement_value FLOAT,
                measurement_unit VARCHAR(20),
                created_at DATETIME,
                published_at DATETIME
            )
        """))

    db.session.commit()


def document_markup_to_dict(m):
    import json
    def _parse(raw, default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return default
    def _iso(dt):
        return dt.isoformat() if dt else None
    return {
        'id': m.id,
        'document_id': m.document_id,
        'user_id': m.user_id,
        'user_name': m.user_name,
        'layer': m.layer,
        'markup_type': m.markup_type,
        'geometry': _parse(m.geometry_json, {}),
        'style': _parse(m.style_json, {}),
        'label': m.label,
        'measurement_value': m.measurement_value,
        'measurement_unit': m.measurement_unit,
        'created_at': _iso(m.created_at),
        'published_at': _iso(m.published_at),
    }


def storage_path(upload_root: str, project_id: int) -> str:
    path = os.path.join(upload_root, 'documents', str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def version_storage_path(upload_root: str, project_id: int, document_id: int) -> str:
    path = os.path.join(upload_root, 'documents', str(project_id), 'versions', str(document_id))
    os.makedirs(path, exist_ok=True)
    return path


document_folder = storage_path


def format_file_size(num_bytes: int | None) -> str:
    size = int(num_bytes or 0)
    if size < 1024:
        return f'{size} B'
    if size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    if size < 1024 * 1024 * 1024:
        return f'{size / (1024 * 1024):.1f} MB'
    return f'{size / (1024 * 1024 * 1024):.2f} GB'


def parse_file_size(size_str: str) -> int:
    if not size_str:
        return 0
    m = re.match(r'^([\d.]+)\s*(B|KB|MB|GB)?$', str(size_str).strip(), re.I)
    if not m:
        return 0
    val = float(m.group(1))
    unit = (m.group(2) or 'B').upper()
    mult = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3}
    return int(val * mult.get(unit, 1))


def hash_share_password(password: str | None) -> str | None:
    if not password:
        return None
    pwd = str(password).strip()
    return generate_password_hash(pwd) if pwd else None


def verify_share_password(password_hash: str | None, password: str | None) -> bool:
    if not password_hash:
        return True
    if not password:
        return False
    return check_password_hash(password_hash, str(password).strip())


def folder_to_dict(folder, child_count: int = 0, file_count: int = 0, preview_thumbs: list | None = None) -> dict[str, Any]:
    return {
        'id': folder.id,
        'project_id': folder.project_id,
        'parent_id': folder.parent_id,
        'name': folder.name,
        'is_system': bool(folder.is_system),
        'system_key': folder.system_key,
        'can_delete': not folder.is_system,
        'can_rename': not folder.is_system,
        'child_count': child_count,
        'file_count': file_count,
        'preview_thumbs': preview_thumbs or [],
        'created_at': folder.created_at.isoformat() if folder.created_at else None,
        'deleted_at': folder.deleted_at.isoformat() if getattr(folder, 'deleted_at', None) else None,
    }


def document_to_dict(
    doc,
    project_name: str | None = None,
    folder_name: str | None = None,
    uploaded_by_name: str | None = None,
    checkout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = {}
    if doc.source_metadata_json:
        try:
            meta = json.loads(doc.source_metadata_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
    co = checkout or {}
    return {
        'id': doc.id,
        'project_id': doc.project_id,
        'project_name': project_name,
        'folder_id': doc.folder_id,
        'folder_name': folder_name,
        'name': doc.name,
        'type': doc.document_type,
        'document_type': doc.document_type,
        'filename': doc.filename,
        'original_filename': doc.original_filename,
        'file_size': doc.file_size or 0,
        'size': format_file_size(doc.file_size),
        'mime_type': doc.mime_type,
        'version_count': getattr(doc, 'version_count', 1) or 1,
        'is_system_locked': bool(getattr(doc, 'is_system_locked', False)),
        'can_delete': (
            not bool(getattr(doc, 'is_system_locked', False))
            and not co.get('is_edit_locked')
            and not bool(getattr(doc, 'legal_hold', False))
        ),
        'can_move': (
            not bool(getattr(doc, 'is_system_locked', False))
            and not co.get('is_edit_locked')
            and not bool(getattr(doc, 'legal_hold', False))
        ),
        'checked_out_by_id': co.get('checked_out_by_id'),
        'checked_out_by_name': co.get('checked_out_by_name'),
        'checked_out_at': co.get('checked_out_at'),
        'checkout_note': co.get('checkout_note'),
        'is_checked_out': bool(co.get('is_checked_out')),
        'is_checked_out_by_me': bool(co.get('is_checked_out_by_me')),
        'is_edit_locked': bool(co.get('is_edit_locked')),
        'can_check_out': bool(co.get('can_check_out')),
        'can_check_in': bool(co.get('can_check_in')),
        'can_force_unlock': bool(co.get('can_force_unlock')),
        'tags': _parse_tags_field(getattr(doc, 'tags_json', None)),
        'custom_metadata': _parse_metadata_field(getattr(doc, 'custom_metadata_json', None)),
        'content_hash': getattr(doc, 'content_hash', None),
        'retention_until': doc.retention_until.isoformat() if getattr(doc, 'retention_until', None) else None,
        'legal_hold': bool(getattr(doc, 'legal_hold', False)),
        'source_drawing_id': doc.source_drawing_id,
        'source_sheet': doc.source_sheet,
        'source_metadata': meta,
        'uploaded_by_name': uploaded_by_name,
        'uploaded': doc.created_at.date().isoformat() if doc.created_at else None,
        'created_at': doc.created_at.isoformat() if doc.created_at else None,
        'updated_at': doc.updated_at.isoformat() if getattr(doc, 'updated_at', None) else None,
        'deleted_at': doc.deleted_at.isoformat() if getattr(doc, 'deleted_at', None) else None,
        'file_url': f'/uploads/documents/{doc.project_id}/{doc.filename}',
        'download_url': f'/api/documents/{doc.id}/download',
        'editor_kind': _editor_kind_for(doc),
    }


def _editor_kind_for(doc):
    """Which built-in editor can open this document (explicit or inferred by extension)."""
    explicit = getattr(doc, 'editor_kind', None)
    if explicit:
        return explicit
    name = (doc.original_filename or doc.filename or doc.name or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    if ext in ('xlsx', 'xls', 'csv'):
        return 'sheet'
    if ext in ('docx', 'doc', 'txt', 'rtf', 'html', 'htm'):
        return 'doc'
    return None


def share_link_to_dict(link, base_url: str = '') -> dict[str, Any]:
    share_url = f'{base_url}/share/{link.token}'
    download_url = f'{base_url}/share/{link.token}/download'
    return {
        'id': link.id,
        'document_id': link.document_id,
        'token': link.token,
        'label': link.label,
        'share_url': share_url,
        'download_url': download_url,
        'has_password': bool(getattr(link, 'password_hash', None)),
        'expires_at': link.expires_at.isoformat() if link.expires_at else None,
        'max_downloads': link.max_downloads,
        'download_count': link.download_count or 0,
        'revoked': bool(link.revoked_at),
        'approval_status': getattr(link, 'approval_status', None) or 'approved',
        'approved_at': link.approved_at.isoformat() if getattr(link, 'approved_at', None) else None,
        'created_at': link.created_at.isoformat() if link.created_at else None,
    }


def folder_share_link_to_dict(link, base_url: str = '') -> dict[str, Any]:
    share_url = f'{base_url}/share/folder/{link.token}'
    return {
        'id': link.id,
        'folder_id': link.folder_id,
        'token': link.token,
        'label': link.label,
        'share_url': share_url,
        'has_password': bool(getattr(link, 'password_hash', None)),
        'allow_browse': bool(getattr(link, 'allow_browse', True)),
        'allow_download': bool(getattr(link, 'allow_download', True)),
        'allow_upload': bool(getattr(link, 'allow_upload', False)),
        'expires_at': link.expires_at.isoformat() if link.expires_at else None,
        'max_downloads': link.max_downloads,
        'download_count': link.download_count or 0,
        'revoked': bool(link.revoked_at),
        'approval_status': getattr(link, 'approval_status', None) or 'approved',
        'approved_at': link.approved_at.isoformat() if getattr(link, 'approved_at', None) else None,
        'created_at': link.created_at.isoformat() if link.created_at else None,
    }


def version_to_dict(ver, uploaded_by_name: str | None = None) -> dict[str, Any]:
    return {
        'id': ver.id,
        'document_id': ver.document_id,
        'version_no': ver.version_no,
        'filename': ver.filename,
        'original_filename': ver.original_filename,
        'size': format_file_size(ver.file_size),
        'file_size': ver.file_size or 0,
        'mime_type': ver.mime_type,
        'notes': ver.notes,
        'uploaded_by_name': uploaded_by_name,
        'created_at': ver.created_at.isoformat() if ver.created_at else None,
    }


def comment_to_dict(comment, user_name: str | None = None) -> dict[str, Any]:
    return {
        'id': comment.id,
        'document_id': comment.document_id,
        'user_id': comment.user_id,
        'user_name': user_name,
        'body': comment.body,
        'created_at': comment.created_at.isoformat() if comment.created_at else None,
        'updated_at': comment.updated_at.isoformat() if getattr(comment, 'updated_at', None) else None,
    }


def activity_to_dict(act, user_name: str | None = None) -> dict[str, Any]:
    detail = {}
    if act.detail_json:
        try:
            detail = json.loads(act.detail_json)
        except (TypeError, json.JSONDecodeError):
            detail = {}
    return {
        'id': act.id,
        'project_id': act.project_id,
        'document_id': act.document_id,
        'folder_id': act.folder_id,
        'user_id': act.user_id,
        'user_name': user_name,
        'action': act.action,
        'detail': detail,
        'created_at': act.created_at.isoformat() if act.created_at else None,
    }


def permission_to_dict(perm, user_name: str | None = None, user_email: str | None = None) -> dict[str, Any]:
    return {
        'id': perm.id,
        'folder_id': perm.folder_id,
        'user_id': perm.user_id,
        'user_name': user_name,
        'user_email': user_email,
        'can_view': bool(perm.can_view),
        'can_upload': bool(perm.can_upload),
        'can_manage': bool(perm.can_manage),
        'created_at': perm.created_at.isoformat() if perm.created_at else None,
    }


def new_share_token() -> str:
    return secrets.token_urlsafe(32)


def default_share_expiry(days: int = 30) -> datetime:
    return datetime.utcnow() + timedelta(days=days)


def _parse_tags_field(raw) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [str(t).strip() for t in data if str(t).strip()][:50]
    return []


def _parse_metadata_field(raw) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def share_link_is_valid(link) -> bool:
    if link.revoked_at:
        return False
    status = getattr(link, 'approval_status', None) or 'approved'
    if status in ('pending', 'rejected'):
        return False
    if link.expires_at and link.expires_at < datetime.utcnow():
        return False
    if link.max_downloads and (link.download_count or 0) >= link.max_downloads:
        return False
    return True


def ensure_system_folders(db, DocumentFolder, project_id: int, user_id: int | None = None, Document=None) -> None:
    """Create locked system folders for a project if missing."""
    for spec in SYSTEM_FOLDERS:
        existing = DocumentFolder.query.filter_by(
            project_id=int(project_id),
            system_key=spec['system_key'],
        ).first()
        if existing:
            continue
        folder = DocumentFolder(
            project_id=int(project_id),
            parent_id=None,
            name=spec['name'],
            is_system=True,
            system_key=spec['system_key'],
            created_by_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.session.add(folder)
    db.session.commit()

    key_to_id = {
        f.system_key: f.id
        for f in DocumentFolder.query.filter_by(project_id=int(project_id), is_system=True).all()
        if f.system_key
    }
    for spec in SYSTEM_SUBFOLDERS:
        existing = DocumentFolder.query.filter_by(
            project_id=int(project_id),
            system_key=spec['system_key'],
        ).first()
        if existing:
            if existing.parent_id != key_to_id.get(spec['parent_key']):
                parent_id = key_to_id.get(spec['parent_key'])
                if parent_id:
                    existing.parent_id = parent_id
            continue
        parent_id = key_to_id.get(spec['parent_key'])
        if not parent_id:
            continue
        folder = DocumentFolder(
            project_id=int(project_id),
            parent_id=parent_id,
            name=spec['name'],
            is_system=True,
            system_key=spec['system_key'],
            created_by_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.session.add(folder)
    db.session.commit()

    if Document is not None:
        my_files = DocumentFolder.query.filter_by(
            project_id=int(project_id),
            system_key='my-files',
        ).first()
        if my_files:
            orphans = Document.query.filter_by(project_id=int(project_id), folder_id=None).filter(
                Document.deleted_at.is_(None) if hasattr(Document, 'deleted_at') else True,
            ).all()
            for doc in orphans:
                doc.folder_id = my_files.id
            if orphans:
                db.session.commit()


def get_or_create_child_folder(db, DocumentFolder, project_id: int, parent_id: int, name: str, user_id: int | None = None):
    """Return a project subfolder under parent_id, creating it when missing."""
    clean = (name or 'Unnamed').strip()[:200]
    if not clean:
        clean = 'Unnamed'
    q = DocumentFolder.query.filter_by(
        project_id=int(project_id),
        parent_id=int(parent_id),
        name=clean,
    )
    if hasattr(DocumentFolder, 'deleted_at'):
        q = q.filter(DocumentFolder.deleted_at.is_(None))
    existing = q.first()
    if existing:
        return existing
    folder = DocumentFolder(
        project_id=int(project_id),
        parent_id=int(parent_id),
        name=clean,
        is_system=False,
        system_key=None,
        created_by_id=user_id,
        created_at=datetime.utcnow(),
    )
    db.session.add(folder)
    db.session.flush()
    return folder


def resolve_folder_by_key(db, DocumentFolder, project_id: int, system_key: str):
    ensure_system_folders(db, DocumentFolder, project_id)
    return DocumentFolder.query.filter_by(
        project_id=int(project_id),
        system_key=system_key,
    ).first()


def folder_is_descendant(db, DocumentFolder, folder_id: int, ancestor_id: int) -> bool:
    """Return True if folder_id is inside ancestor_id (cycle guard for moves)."""
    if folder_id == ancestor_id:
        return True
    current = DocumentFolder.query.get(folder_id)
    seen = set()
    while current and current.parent_id:
        if current.parent_id == ancestor_id:
            return True
        if current.parent_id in seen:
            break
        seen.add(current.parent_id)
        current = DocumentFolder.query.get(current.parent_id)
    return False


def folder_is_under_root_share(db, DocumentFolder, folder_id: int, root_folder_id: int) -> bool:
    """True if folder_id is root or a descendant of root_folder_id."""
    if folder_id == root_folder_id:
        return True
    current = DocumentFolder.query.get(folder_id)
    seen = set()
    while current and current.parent_id:
        if current.parent_id == root_folder_id:
            return True
        if current.id in seen:
            break
        seen.add(current.id)
        current = DocumentFolder.query.get(current.parent_id)
    return False
