"""Project document storage — Dropbox-style folders, files, and share links."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

SYSTEM_FOLDERS = [
    {'system_key': 'printed-output', 'name': 'Printed Output', 'description': 'Auto-saved prints from Case PM (locked)'},
    {'system_key': 'contracts', 'name': 'Contracts', 'description': 'Project contracts and agreements (locked)'},
    {'system_key': 'specifications', 'name': 'Specifications', 'description': 'Spec books and divisions (locked)'},
    {'system_key': 'my-files', 'name': 'My Files', 'description': 'Your project uploads'},
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
                created_at DATETIME
            )
        """))

    if 'document_share_link' not in tables:
        db.session.execute(text("""
            CREATE TABLE document_share_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                token VARCHAR(80) NOT NULL UNIQUE,
                label VARCHAR(200),
                expires_at DATETIME,
                max_downloads INTEGER,
                download_count INTEGER DEFAULT 0,
                allow_download INTEGER DEFAULT 1,
                created_by_id INTEGER,
                created_at DATETIME,
                revoked_at DATETIME
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
                source_drawing_id INTEGER,
                source_sheet VARCHAR(80),
                source_metadata_json TEXT,
                uploaded_by_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME
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
        for sql in migrations:
            db.session.execute(text(sql))

    db.session.commit()


def storage_path(upload_root: str, project_id: int) -> str:
    path = os.path.join(upload_root, 'documents', str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


# Back-compat alias
def document_folder(upload_root: str, project_id: int) -> str:
    return storage_path(upload_root, project_id)


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


def folder_to_dict(folder, child_count: int = 0, file_count: int = 0) -> dict[str, Any]:
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
        'created_at': folder.created_at.isoformat() if folder.created_at else None,
    }


def document_to_dict(doc, project_name: str | None = None, folder_name: str | None = None) -> dict[str, Any]:
    meta = {}
    if doc.source_metadata_json:
        try:
            meta = json.loads(doc.source_metadata_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
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
        'is_system_locked': bool(getattr(doc, 'is_system_locked', False)),
        'can_delete': not bool(getattr(doc, 'is_system_locked', False)),
        'can_move': not bool(getattr(doc, 'is_system_locked', False)),
        'source_drawing_id': doc.source_drawing_id,
        'source_sheet': doc.source_sheet,
        'source_metadata': meta,
        'uploaded': doc.created_at.date().isoformat() if doc.created_at else None,
        'created_at': doc.created_at.isoformat() if doc.created_at else None,
        'updated_at': doc.updated_at.isoformat() if getattr(doc, 'updated_at', None) else None,
        'file_url': f'/uploads/documents/{doc.project_id}/{doc.filename}',
        'download_url': f'/api/documents/{doc.id}/download',
    }


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
        'expires_at': link.expires_at.isoformat() if link.expires_at else None,
        'max_downloads': link.max_downloads,
        'download_count': link.download_count or 0,
        'revoked': bool(link.revoked_at),
        'created_at': link.created_at.isoformat() if link.created_at else None,
    }


def new_share_token() -> str:
    return secrets.token_urlsafe(32)


def default_share_expiry(days: int = 30) -> datetime:
    return datetime.utcnow() + timedelta(days=days)


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
    if Document is not None:
        my_files = DocumentFolder.query.filter_by(
            project_id=int(project_id),
            system_key='my-files',
        ).first()
        if my_files:
            orphans = Document.query.filter_by(project_id=int(project_id), folder_id=None).all()
            for doc in orphans:
                doc.folder_id = my_files.id
            if orphans:
                db.session.commit()


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
