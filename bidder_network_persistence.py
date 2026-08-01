"""Schema for bidder plan room tables and bid package publish flags."""
from __future__ import annotations

from sqlalchemy import inspect, text


def ensure_bidder_network_schema(db):
    db.create_all()

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if 'bid_package' in tables:
        existing = {c['name'] for c in inspector.get_columns('bid_package')}
        if 'network_published' not in existing:
            db.session.execute(text('ALTER TABLE bid_package ADD COLUMN network_published INTEGER DEFAULT 0'))
        if 'network_summary' not in existing:
            db.session.execute(text('ALTER TABLE bid_package ADD COLUMN network_summary TEXT'))
        if 'network_manifest_json' not in existing:
            db.session.execute(text('ALTER TABLE bid_package ADD COLUMN network_manifest_json TEXT'))
    db.session.commit()
