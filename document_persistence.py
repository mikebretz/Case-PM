"""Project document storage helpers."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any


def ensure_document_schema(engine, db) -> None:
    """Create document table if missing (SQLite-safe)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if 'document' in insp.get_table_names():
        return
    db.session.execute(text("""
        CREATE TABLE document (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name VARCHAR(300) NOT NULL,
            document_type VARCHAR(80) NOT NULL DEFAULT 'Other',
            filename VARCHAR(300) NOT NULL,
            original_filename VARCHAR(300),
            file_size INTEGER DEFAULT 0,
            mime_type VARCHAR(120),
            source_drawing_id INTEGER,
            source_sheet VARCHAR(80),
            source_metadata_json TEXT,
            uploaded_by_id INTEGER,
            created_at DATETIME
        )
    """))
    db.session.commit()


def document_folder(upload_root: str, project_id: int) -> str:
    path = os.path.join(upload_root, 'documents', str(project_id))
    os.makedirs(path, exist_ok=True)
    return path


def format_file_size(num_bytes: int | None) -> str:
    size = int(num_bytes or 0)
    if size < 1024:
        return f'{size} B'
    if size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    return f'{size / (1024 * 1024):.1f} MB'


def document_to_dict(doc, project_name: str | None = None) -> dict[str, Any]:
    return {
        'id': doc.id,
        'project_id': doc.project_id,
        'project_name': project_name,
        'name': doc.name,
        'type': doc.document_type,
        'document_type': doc.document_type,
        'filename': doc.filename,
        'original_filename': doc.original_filename,
        'file_size': doc.file_size or 0,
        'size': format_file_size(doc.file_size),
        'mime_type': doc.mime_type,
        'source_drawing_id': doc.source_drawing_id,
        'source_sheet': doc.source_sheet,
        'source_metadata': json.loads(doc.source_metadata_json) if doc.source_metadata_json else {},
        'uploaded': doc.created_at.date().isoformat() if doc.created_at else None,
        'created_at': doc.created_at.isoformat() if doc.created_at else None,
        'file_url': f'/uploads/documents/{doc.project_id}/{doc.filename}',
    }
