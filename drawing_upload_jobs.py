"""Background drawing set upload jobs with live progress."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

_jobs: dict[str, 'DrawingUploadJob'] = {}
_lock = threading.Lock()

ASYNC_UPLOAD_PAGE_THRESHOLD = 8


@dataclass
class DrawingUploadJob:
    id: str
    project_id: int
    total_pages: int
    status: str = 'queued'
    processed_pages: int = 0
    current_page: int = 0
    message: str = 'Queued'
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            'job_id': self.id,
            'status': self.status,
            'total_pages': self.total_pages,
            'processed_pages': self.processed_pages,
            'current_page': self.current_page,
            'message': self.message,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


def create_job(project_id: int, total_pages: int) -> DrawingUploadJob:
    job = DrawingUploadJob(
        id=uuid.uuid4().hex,
        project_id=int(project_id),
        total_pages=int(total_pages),
        message=f'Preparing {total_pages} pages…',
    )
    with _lock:
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> DrawingUploadJob | None:
    with _lock:
        return _jobs.get(job_id)


def _update_job(job_id: str, **fields) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = datetime.utcnow().isoformat()


def start_job(job_id: str, worker: Callable[[], None]) -> None:
    def run():
        _update_job(job_id, status='processing', message='Import started')
        try:
            worker()
        except Exception as exc:
            _update_job(job_id, status='error', error=str(exc), message='Import failed')

    thread = threading.Thread(target=run, name=f'drawing-upload-{job_id[:8]}', daemon=True)
    thread.start()


def mark_progress(job_id: str, processed: int, total: int, current_page: int, message: str | None = None) -> None:
    _update_job(
        job_id,
        processed_pages=processed,
        total_pages=total,
        current_page=current_page,
        message=message or f'Imported {processed} of {total} sheets…',
    )


def mark_complete(job_id: str, result: dict[str, Any]) -> None:
    _update_job(
        job_id,
        status='complete',
        processed_pages=result.get('created_count') or len(result.get('pages') or []),
        message='Import complete',
        result=result,
        error=None,
    )


def should_run_async(page_count: int) -> bool:
    return int(page_count or 0) > ASYNC_UPLOAD_PAGE_THRESHOLD
