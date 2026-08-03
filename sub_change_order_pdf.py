"""Fill the Case Contracting subcontract change order PDF (AcroForm)."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import fitz

from co_persistence import is_subcontract_co


def _fmt_money_plain(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    negative = amount < 0
    amount = abs(amount)
    text = f'{amount:,.2f}'
    return f'-{text}' if negative else text


def _fmt_date_short(value) -> str:
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%m/%d/%Y')
    raw = str(value).strip()[:10]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            return datetime.strptime(raw, fmt).strftime('%m/%d/%Y')
        except ValueError:
            continue
    return raw


def _order_number_for_form(co) -> str:
    raw = (getattr(co, 'number', None) or '').strip()
    if not raw:
        return ''
    upper = raw.upper()
    for prefix in ('SCO-', 'SCO', 'SUB-CO-', 'SUBCO-'):
        if upper.startswith(prefix):
            return raw[len(prefix):].lstrip('-')
    return raw


def _resolve_commitment(co, Commitment=None):
    if Commitment is None:
        return None
    ref = (getattr(co, 'linked_commitment_ref', None) or '').strip()
    if not ref:
        return None
    return Commitment.query.filter_by(project_id=co.project_id, number=ref).first()


def _matches_sub_co_scope(candidate, co) -> bool:
    ref = (getattr(co, 'linked_commitment_ref', None) or '').strip()
    cref = (getattr(candidate, 'linked_commitment_ref', None) or '').strip()
    if ref and cref and ref != cref:
        return False
    co_cid = getattr(co, 'company_id', None)
    c_cid = getattr(candidate, 'company_id', None)
    if co_cid and c_cid and str(co_cid) != str(c_cid):
        return False
    co_name = (getattr(co, 'company_name', None) or '').strip().lower()
    c_name = (getattr(candidate, 'company_name', None) or '').strip().lower()
    if co_name and c_name and co_name != c_name:
        return False
    return True


def _sum_prior_approved_sub_cos(co, ChangeOrder=None) -> float:
    if ChangeOrder is None:
        return 0.0
    total = 0.0
    rows = ChangeOrder.query.filter_by(project_id=co.project_id).all()
    current_id = getattr(co, 'id', None)
    for row in rows:
        if not is_subcontract_co(row):
            continue
        if (row.status or '') != 'Approved':
            continue
        if current_id and row.id == current_id:
            continue
        if not _matches_sub_co_scope(row, co):
            continue
        total += float(row.amount or 0)
    return round(total, 2)


def _build_description(co, allocations=None) -> str:
    parts = []
    title = (getattr(co, 'title', None) or '').strip()
    desc = (getattr(co, 'description', None) or '').strip()
    if title and title != desc:
        parts.append(title)
    if desc:
        parts.append(desc)
    notes = (getattr(co, 'notes', None) or '').strip()
    if notes:
        parts.append(notes)
    for alloc in allocations or []:
        if not isinstance(alloc, dict):
            continue
        cc = (alloc.get('cost_code') or '').strip()
        line_desc = (alloc.get('description') or '').strip()
        amt = alloc.get('amount')
        label = ' — '.join(x for x in (cc, line_desc) if x) or 'Line item'
        parts.append(f'{label}: {_fmt_money_plain(amt)}')
    return '\n'.join(parts)


def _project_label(project) -> str:
    if not project:
        return ''
    name = (getattr(project, 'name', None) or '').strip()
    number = (getattr(project, 'number', None) or '').strip()
    if name and number:
        return f'{name} {number}'
    return name or number


def _to_subcontractor_block(co, commitment=None) -> str:
    lines = []
    sub_name = (getattr(co, 'company_name', None) or '').strip()
    if not sub_name and commitment:
        sub_name = (getattr(commitment, 'company_name', None) or '').strip()
    if sub_name:
        lines.append(sub_name)
    contact = (getattr(co, 'contact_name', None) or '').strip()
    if not contact and commitment:
        contact = (getattr(commitment, 'contact_name', None) or '').strip()
    if contact:
        lines.append(f'Attn: {contact}')
    email = (getattr(co, 'contact_email', None) or '').strip()
    if not email and commitment:
        email = (getattr(commitment, 'contact_email', None) or '').strip()
    if email:
        lines.append(email)
    phone = (getattr(co, 'contact_phone', None) or '').strip()
    if not phone and commitment:
        phone = (getattr(commitment, 'contact_phone', None) or '').strip()
    if phone:
        lines.append(phone)
    return '\n'.join(lines)


def fill_sub_change_order_pdf(
    co,
    *,
    template_path: str,
    project=None,
    company_info=None,
    allocations=None,
    Commitment=None,
    ChangeOrder=None,
) -> bytes:
    if not os.path.isfile(template_path):
        raise FileNotFoundError('Subcontract change order template PDF is missing.')

    commitment = _resolve_commitment(co, Commitment)
    original = float(getattr(commitment, 'original_amount', 0) or 0) if commitment else 0.0
    previous = _sum_prior_approved_sub_cos(co, ChangeOrder)
    this_amount = float(getattr(co, 'amount', 0) or 0)
    total = round(original + previous + this_amount, 2)

    co_date = getattr(co, 'date', None) or getattr(co, 'approved_at', None)
    field_values = {
        'Text7': _order_number_for_form(co),
        'Text8': _fmt_date_short(co_date),
        'Text1': _to_subcontractor_block(co, commitment),
        'Text2': _project_label(project),
        'Text9': _fmt_money_plain(original),
        'Text10': _fmt_money_plain(previous),
        'Text11': _fmt_money_plain(this_amount),
        'Text3': _fmt_money_plain(total),
        'Text5': _build_description(co, allocations),
        'Text6': _fmt_money_plain(this_amount),
    }

    doc = fitz.open(template_path)
    try:
        page = doc[0]
        for widget in page.widgets() or []:
            val = field_values.get(widget.field_name)
            if val is None:
                continue
            widget.field_value = val
            widget.update()
        return doc.tobytes(deflate=True)
    finally:
        doc.close()
