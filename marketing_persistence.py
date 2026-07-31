"""Marketing schema migrations for SQLite / existing deployments."""
from __future__ import annotations

from sqlalchemy import inspect, text


def ensure_marketing_schema(db):
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    def _add_columns(table: str, additions: dict[str, str]):
        if table not in tables:
            return
        existing = {c['name'] for c in inspector.get_columns(table)}
        for col, typedef in additions.items():
            if col not in existing:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {typedef}'))

    _add_columns('marketing_lead', {
        'bid_package_id': 'INTEGER',
        'campaign_id': 'INTEGER',
        'landing_page_id': 'INTEGER',
        'attribution_json': 'TEXT',
        'construction_market': 'VARCHAR(40)',
    })
    _add_columns('marketing_case_study', {
        'gallery_json': 'TEXT',
        'before_after_json': 'TEXT',
        'videos_json': 'TEXT',
        'client_type': 'VARCHAR(80)',
        'style_tags_json': 'TEXT',
        'challenges_json': 'TEXT',
        'view_count': 'INTEGER DEFAULT 0',
    })
    _add_columns('marketing_asset', {
        'document_id': 'INTEGER',
        'external_url': 'VARCHAR(500)',
        'phase': 'VARCHAR(80)',
        'trade': 'VARCHAR(80)',
        'meta_json': 'TEXT',
    })
    _add_columns('marketing_review_request', {
        'access_token': 'VARCHAR(64)',
        'trigger_milestone': 'VARCHAR(80)',
        'client_email': 'VARCHAR(200)',
    })
    _add_columns('marketing_campaign', {
        'template_key': 'VARCHAR(40)',
        'campaign_type': 'VARCHAR(40)',
    })
    _add_columns('marketing_referral', {
        'incentive_code': 'VARCHAR(40)',
        'issued_at': 'DATETIME',
        'redeemed_at': 'DATETIME',
    })
    _add_columns('marketing_proposal', {
        'pdf_path': 'VARCHAR(400)',
    })
    db.session.commit()
