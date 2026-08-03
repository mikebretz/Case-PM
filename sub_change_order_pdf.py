"""Fill the Case Contracting subcontract change order PDF (AcroForm)."""
from __future__ import annotations

import json
import os
from datetime import datetime

import fitz

from co_persistence import is_subcontract_co

# Layout tuned to match the SCO PDF (not pixel-perfect AcroForm bounds).
ORDER_DATE_RECT = fitz.Rect(388, 178, 492, 198)
ACCEPTANCE_DATE_COVER = fitz.Rect(226, 708, 342, 728)
ACCEPTANCE_DATE_TEXT_RECT = fitz.Rect(268, 709, 340, 727)
SIG_BLOCK_COVER = fitz.Rect(360, 700, 582, 746)
SIG_NAME_RECT = fitz.Rect(366, 704, 578, 722)
SIG_TITLE_RECT = fitz.Rect(366, 724, 578, 742)
SIGNATURE_IMAGE_RECT = fitz.Rect(366, 700, 578, 738)


def _fmt_money_plain(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    negative = amount < 0
    amount = abs(amount)
    text = f'{amount:,.2f}'
    return f'-{text}' if negative else text


def _parse_date(value):
    if not value:
        return None
    if hasattr(value, 'strftime'):
        return value
    raw = str(value).strip()[:19]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%dT%H:%M:%S'):
        try:
            chunk = raw[:10] if 'T' not in fmt else raw.replace('Z', '')
            return datetime.strptime(chunk, fmt)
        except ValueError:
            continue
    return None


def _fmt_date_display(value) -> str:
    dt = _parse_date(value)
    if not dt:
        return str(value).strip()[:10] if value else ''
    try:
        return dt.strftime('%-m/%-d/%Y') if os.name != 'nt' else dt.strftime('%#m/%#d/%Y')
    except ValueError:
        return dt.strftime('%m/%d/%Y')


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


def _resolve_vendor_company(co, Company=None, commitment=None):
    if Company is None:
        return None
    cid = getattr(co, 'company_id', None)
    if cid is not None and str(cid).strip() != '':
        try:
            row = Company.query.get(int(cid))
            if row:
                return row
        except (TypeError, ValueError):
            pass
    name = (getattr(co, 'company_name', None) or '').strip()
    if not name and commitment:
        name = (getattr(commitment, 'company_name', None) or '').strip()
    if name:
        return Company.query.filter_by(name=name).first()
    return None


def _company_address_lines(company) -> list[str]:
    if not company:
        return []
    lines: list[str] = []
    raw = getattr(company, 'details_json', None)
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            for key in ('address', 'street', 'mailing_address', 'address_line1', 'address_line2'):
                val = (data.get(key) or '').strip()
                if val and val not in lines:
                    lines.append(val)
            city = (data.get('city') or '').strip()
            state = (data.get('state') or '').strip()
            postal = (data.get('zip') or data.get('postal_code') or '').strip()
            city_line = city
            if city and state:
                city_line = f'{city}, {state}'
            elif state:
                city_line = state
            if postal:
                city_line = f'{city_line} {postal}'.strip() if city_line else postal
            if city_line and city_line not in lines:
                lines.append(city_line)
    return lines


def _to_subcontractor_block(co, commitment=None, vendor_company=None) -> str:
    """TO: company name and mailing address only."""
    name = (getattr(co, 'company_name', None) or '').strip()
    if not name and commitment:
        name = (getattr(commitment, 'company_name', None) or '').strip()
    if not name and vendor_company:
        name = (getattr(vendor_company, 'name', None) or '').strip()
    lines = []
    if name:
        lines.append(name)
    lines.extend(_company_address_lines(vendor_company))
    return '\n'.join(lines)


def _project_label(project) -> str:
    if not project:
        return ''
    name = (getattr(project, 'name', None) or '').strip()
    number = (getattr(project, 'number', None) or '').strip()
    if name and number:
        return f'{name}  {number}'
    return name or number


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


def _paint_white(page, rect: fitz.Rect) -> None:
    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)


def _overlay_text(page, rect: fitz.Rect, text: str, *, fontsize: float = 9, align: int = fitz.TEXT_ALIGN_LEFT) -> None:
    if not text:
        return
    page.insert_textbox(
        rect,
        text,
        fontsize=fontsize,
        fontname='helv',
        align=align,
    )


def _set_widget(widget, value, *, font_size: float | None = None) -> None:
    if font_size is not None:
        try:
            widget.text_fontsize = font_size
        except Exception:
            pass
    widget.field_value = '' if value is None else str(value)
    widget.update()


def _clear_signature_widgets(page) -> None:
    for widget in page.widgets() or []:
        if widget.field_name in ('ComboBox1', 'ComboBox2'):
            _set_widget(widget, '')


def _apply_signature_block(
    page,
    *,
    mode: str,
    signer_name: str = '',
    signer_title: str = '',
    signature_image_bytes: bytes | None = None,
    acceptance_date: str = '',
) -> None:
    mode = (mode or 'blank').strip().lower()
    name = (signer_name or '').strip()
    title = (signer_title or '').strip()

    _clear_signature_widgets(page)
    _paint_white(page, SIG_BLOCK_COVER)

    if mode == 'name' and (name or title):
        if name:
            _overlay_text(page, SIG_NAME_RECT, name, fontsize=10, align=fitz.TEXT_ALIGN_LEFT)
        if title:
            _overlay_text(page, SIG_TITLE_RECT, title, fontsize=9, align=fitz.TEXT_ALIGN_LEFT)
    elif mode == 'esign':
        if signature_image_bytes:
            try:
                page.insert_image(SIGNATURE_IMAGE_RECT, stream=signature_image_bytes, keep_proportion=True, overlay=True)
            except Exception:
                pass
        if name:
            _overlay_text(page, SIG_NAME_RECT, name, fontsize=10, align=fitz.TEXT_ALIGN_LEFT)
        if title:
            _overlay_text(page, SIG_TITLE_RECT, title, fontsize=9, align=fitz.TEXT_ALIGN_LEFT)

    if acceptance_date:
        _paint_white(page, ACCEPTANCE_DATE_COVER)
        _overlay_text(page, ACCEPTANCE_DATE_TEXT_RECT, acceptance_date, fontsize=10, align=fitz.TEXT_ALIGN_LEFT)


def _overlay_multiline_field(page, widget_name: str, text: str, *, fontsize: float = 9) -> None:
    rect = None
    for widget in page.widgets() or []:
        if widget.field_name == widget_name:
            rect = fitz.Rect(widget.rect)
            _set_widget(widget, '')
            break
    if rect and text:
        _overlay_text(page, rect, text, fontsize=fontsize, align=fitz.TEXT_ALIGN_LEFT)


def fill_sub_change_order_pdf(
    co,
    *,
    template_path: str,
    project=None,
    company_info=None,
    allocations=None,
    Commitment=None,
    ChangeOrder=None,
    Company=None,
    print_options: dict | None = None,
) -> bytes:
    if not os.path.isfile(template_path):
        raise FileNotFoundError('Subcontract change order template PDF is missing.')

    opts = print_options or {}
    commitment = _resolve_commitment(co, Commitment)
    vendor_company = _resolve_vendor_company(co, Company, commitment)
    original = float(getattr(commitment, 'original_amount', 0) or 0) if commitment else 0.0
    previous = _sum_prior_approved_sub_cos(co, ChangeOrder)
    this_amount = float(getattr(co, 'amount', 0) or 0)
    total = round(original + previous + this_amount, 2)

    co_date = getattr(co, 'date', None) or getattr(co, 'approved_at', None)
    order_date = opts.get('order_date') or co_date
    acceptance_raw = opts.get('acceptance_date') or opts.get('signed_date')
    acceptance_date = _fmt_date_display(acceptance_raw) if acceptance_raw else ''

    order_date_text = _fmt_date_display(order_date)
    to_text = _to_subcontractor_block(co, commitment, vendor_company)
    project_text = _project_label(project)

    field_values = {
        'Text7': _order_number_for_form(co),
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
        skip_widget_fill = {'Text1', 'Text2', 'Text8', 'ComboBox1', 'ComboBox2'}
        for widget in page.widgets() or []:
            if widget.field_name in skip_widget_fill:
                _set_widget(widget, '')
                continue
            val = field_values.get(widget.field_name)
            if val is None:
                continue
            _set_widget(widget, val, font_size=9)

        if order_date_text:
            _paint_white(page, ORDER_DATE_RECT)
            _overlay_text(page, ORDER_DATE_RECT, order_date_text, fontsize=10, align=fitz.TEXT_ALIGN_RIGHT)

        _overlay_multiline_field(page, 'Text1', to_text, fontsize=9)
        _overlay_multiline_field(page, 'Text2', project_text, fontsize=9)

        _apply_signature_block(
            page,
            mode=opts.get('signature_mode') or 'blank',
            signer_name=opts.get('signer_name') or '',
            signer_title=opts.get('signer_title') or '',
            signature_image_bytes=opts.get('signature_image_bytes'),
            acceptance_date=acceptance_date,
        )
        return doc.tobytes(deflate=True)
    finally:
        doc.close()
