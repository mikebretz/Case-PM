"""
Subcontractor portal — COI / lien waiver uploads tied to pay app state and AP compliance.
"""
from __future__ import annotations

import json
from datetime import datetime


def register_sub_lien_waiver(
    PayAppProjectState,
    db,
    project_id: int,
    company_id: int,
    *,
    filename: str,
    period: str = '',
    user_id=None,
) -> dict:
    from pay_app_persistence import get_pay_app_state, save_pay_app_state

    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    waivers = state.setdefault('subLienWaivers', {})
    key = str(int(company_id))
    bucket = waivers.get(key) if isinstance(waivers.get(key), dict) else {}
    period_key = (period or 'general').strip() or 'general'
    bucket[period_key] = {
        'filename': filename[:200],
        'file': filename[:200],
        'uploaded_at': datetime.utcnow().isoformat() + 'Z',
        'uploaded_by_id': user_id,
    }
    waivers[key] = bucket
    state['subLienWaivers'] = waivers
    save_pay_app_state(PayAppProjectState, db, int(project_id), state, user_id=user_id)
    return {'project_id': int(project_id), 'company_id': int(company_id), 'period': period_key, 'filename': filename}


def register_sub_coi_reference(
    db,
    COI,
    company_id: int,
    *,
    expiration_date,
    file_path: str,
) -> dict:
    if not COI:
        raise ValueError('COI model not available')
    row = COI(
        company_id=int(company_id),
        expiration_date=expiration_date,
        file_path=file_path[:300],
    )
    db.session.add(row)
    db.session.flush()
    return {'coi_id': row.id, 'company_id': int(company_id)}
