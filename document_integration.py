"""Mirror module uploads into Documents system folders and notify the project team."""
from __future__ import annotations

import mimetypes
import os
from typing import Any


def guess_mime(filename: str, fallback: str = 'application/octet-stream') -> str:
    mt, _ = mimetypes.guess_type(filename or '')
    return mt or fallback


def notify_documents_team(
    db,
    User,
    project_id: int,
    *,
    title: str,
    message: str,
    link: str | None = None,
    module: str = 'Documents',
    roles: tuple = ('Admin', 'Project Manager'),
) -> None:
    """In-app notification + internal message for project managers."""
    try:
        import case_workflow as cw
    except Exception:
        return
    action = link or f'/documents?project_id={project_id}'
    notified: set[int] = set()
    for user in User.query.filter_by(status='Active').all():
        if user.role not in roles and user.role != 'Admin':
            continue
        if user.id in notified:
            continue
        notified.add(user.id)
        cw.notify_user(user.id, title, message, action)
        cw.create_internal_message(
            user.id,
            folder='updates',
            msg_type='update',
            subject=title,
            preview=message[:500],
            body=f'<p>{message}</p>',
            project_id=int(project_id),
            from_label='Case PM Documents',
            module=module,
            action_url=action,
            action_label='Open Documents',
        )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def mirror_file_path(
    mirror_fn,
    project_id: int,
    path: str,
    name: str,
    original_filename: str,
    system_folder_key: str,
    document_type: str = 'Other',
    source_metadata: dict | None = None,
):
    """Read a file from disk and mirror it via ``mirror_fn`` (e.g. ``_mirror_to_system_folder``)."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, 'rb') as fh:
        return mirror_fn(
            project_id, fh.read(), name, original_filename,
            system_folder_key, document_type, source_metadata,
        )


def iter_folder_documents(
    Document,
    DocumentFolder,
    upload_root: str,
    folder_id: int,
    arc_prefix: str = '',
    active_docs=None,
    active_folders=None,
) -> list[tuple[str, str]]:
    """Build (zip_arcname, absolute_file_path) for a folder tree."""
    if active_docs is None:
        active_docs = Document.query.filter(Document.deleted_at.is_(None))
    if active_folders is None:
        active_folders = DocumentFolder.query.filter(DocumentFolder.deleted_at.is_(None))

    folder = active_folders.filter_by(id=folder_id).first()
    if not folder:
        return []

    entries: list[tuple[str, str]] = []
    for doc in active_docs.filter_by(folder_id=folder_id).all():
        directory = os.path.join(upload_root, 'documents', str(doc.project_id))
        path = os.path.join(directory, doc.filename)
        if os.path.isfile(path):
            safe_name = (doc.original_filename or doc.name or doc.filename).replace('\\', '/').split('/')[-1]
            entries.append((f'{arc_prefix}{safe_name}', path))

    for child in active_folders.filter_by(parent_id=folder_id).order_by(DocumentFolder.name).all():
        child_prefix = f'{arc_prefix}{child.name}/'
        entries.extend(iter_folder_documents(
            Document, DocumentFolder, upload_root, child.id, child_prefix, active_docs, active_folders,
        ))
    return entries
