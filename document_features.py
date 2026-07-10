"""Advanced document features: hashing, templates, retention, image→PDF."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any


DEFAULT_SHARE_EXPIRY_DAYS = 30
MAX_SHARE_EXPIRY_DAYS = 365
DEFAULT_RETENTION_YEARS = 7


def file_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def project_document_settings(project) -> dict[str, Any]:
    details = project.get_details() if project and hasattr(project, 'get_details') else {}
    docs = details.get('documents') or {}
    return {
        'share_requires_approval': bool(docs.get('share_requires_approval', False)),
        'default_share_expiry_days': min(
            int(docs.get('default_share_expiry_days') or DEFAULT_SHARE_EXPIRY_DAYS),
            MAX_SHARE_EXPIRY_DAYS,
        ),
        'max_share_expiry_days': min(
            int(docs.get('max_share_expiry_days') or MAX_SHARE_EXPIRY_DAYS),
            MAX_SHARE_EXPIRY_DAYS,
        ),
        'retention_years': int(docs.get('retention_years') or DEFAULT_RETENTION_YEARS),
    }


def clamp_share_expiry_days(days: int | None, settings: dict[str, Any] | None = None) -> int:
    settings = settings or {}
    default = int(settings.get('default_share_expiry_days') or DEFAULT_SHARE_EXPIRY_DAYS)
    maximum = int(settings.get('max_share_expiry_days') or MAX_SHARE_EXPIRY_DAYS)
    try:
        value = int(days if days is not None else default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def retention_until_from_years(years: int) -> datetime:
    return datetime.utcnow() + timedelta(days=max(1, int(years)) * 365)


def image_bytes_to_pdf(file_bytes: bytes) -> bytes:
    """Convert PNG/JPEG bytes to a single-page PDF."""
    import fitz

    src = fitz.open(stream=file_bytes, filetype='png')
    if src.page_count < 1:
        src = fitz.open(stream=file_bytes, filetype='jpeg')
    page = src[0]
    rect = page.rect
    pdf = fitz.open()
    out = pdf.new_page(width=rect.width, height=rect.height)
    out.insert_image(out.rect, stream=file_bytes)
    data = pdf.tobytes()
    pdf.close()
    src.close()
    return data


def apply_folder_template(db, DocumentFolder, template, project_id: int, user_id: int | None) -> list[int]:
    """Create folders from a template definition. Returns new folder ids."""
    spec = template.folders_json
    if isinstance(spec, str):
        spec = json.loads(spec or '[]')
    created: list[int] = []

    def create_nodes(nodes, parent_id=None):
        for node in nodes or []:
            name = (node.get('name') or '').strip()
            if not name:
                continue
            folder = DocumentFolder(
                project_id=int(project_id),
                parent_id=parent_id,
                name=name[:200],
                is_system=False,
                created_by_id=user_id,
                created_at=datetime.utcnow(),
            )
            db.session.add(folder)
            db.session.flush()
            created.append(folder.id)
            create_nodes(node.get('children') or [], folder.id)

    create_nodes(spec)
    return created


def parse_tags(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip()[:80] for t in raw if str(t).strip()][:50]
    if isinstance(raw, str):
        return [t.strip()[:80] for t in raw.split(',') if t.strip()][:50]
    return []
