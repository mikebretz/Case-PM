"""SQLite reliability helpers — WAL mode, busy timeout, and lock retries."""

from __future__ import annotations

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError


def register_sqlite_pragmas() -> None:
    """Enable WAL and longer busy waits for all SQLite connections."""

    @event.listens_for(Engine, 'connect')
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=60000')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()


def _is_lock_error(exc: OperationalError) -> bool:
    msg = str(exc).lower()
    return 'database is locked' in msg or 'database is busy' in msg


def flush_with_retry(session, *, attempts: int = 12, base_delay: float = 0.05) -> None:
    """Flush SQLAlchemy session, retrying on SQLite lock contention."""
    for attempt in range(attempts):
        try:
            session.flush()
            return
        except OperationalError as exc:
            if not _is_lock_error(exc) or attempt >= attempts - 1:
                raise
            time.sleep(min(2.0, base_delay * (2 ** attempt)))


def commit_with_retry(session, *, attempts: int = 12, base_delay: float = 0.05) -> None:
    """Commit SQLAlchemy session, retrying on SQLite lock contention."""
    last_exc = None
    for attempt in range(attempts):
        try:
            session.commit()
            return
        except OperationalError as exc:
            last_exc = exc
            if not _is_lock_error(exc):
                session.rollback()
                raise
            if attempt >= attempts - 1:
                session.rollback()
                raise
            time.sleep(min(2.0, base_delay * (2 ** attempt)))
    if last_exc:
        raise last_exc
