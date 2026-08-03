"""Fill the ALDI Change Order PDF template from change order / change event data."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import fitz

LABOR_TYPES = frozenset({'labor'})
MATERIAL_TYPES = frozenset({'material', 'equipment', 'subcontract', 'other', 'general conditions'})
GC_MATERIAL_TYPES = frozenset({'material', 'equipment'})

# Page 1 — summary form (letter size, points).
PAGE1 = {
    'store': (118, 98),
    'co_number': (468, 98),
    'contractor': (118, 112),
    'ccd': (468, 112),
    'scope': (118, 125),
    'description_box': fitz.Rect(118, 132, 580, 188),
    'sub_rows': [
        {'name': (58, y), 'labor': 278, 'materials': 378, 'cost': 528, 'y': y}
        for y in (218, 234, 250, 266, 282, 298, 314, 330)
    ],
    'total_sub_costs': (528, 330),
    'gc_op_5': (528, 343),
    'gc_material_rows': [{'desc': (22, y), 'cost': 528, 'y': y} for y in (383, 397, 411, 425, 439, 453)],
    'total_gc_material': (528, 468),
    'gc_op_10': (528, 492),
    'total_sub_and_material': (528, 518),
    'total_gc_op': (528, 531),
    'total_adjustment': (528, 549),
}

# Subcontractor breakdown — page 2 (Sub #1) uses slightly different columns than pages 3–6.
SUB_PAGE1 = {
    'name': (118, 78),
    'scope': (118, 105),
    'labor_rows': [
        {'desc': (30, y), 'cost': 575, 'y': y}
        for y in (156, 174, 192, 210, 228, 246)
    ],
    'labor_subtotal': (575, 356),
    'material_rows': [
        {'desc': (30, y), 'cost': 575, 'y': y}
        for y in (389, 407, 425, 443, 461, 479, 497, 515, 533, 551, 569)
    ],
    'material_subtotal': (575, 677),
}

SUB_PAGE_OTHER = {
    'name': (118, 80),
    'scope': (118, 107),
    'labor_rows': [
        {'desc': (30, y), 'cost': 572, 'y': y}
        for y in (161, 179, 197, 215, 233, 251)
    ],
    'labor_subtotal': (572, 370),
    'material_rows': [
        {'desc': (30, y), 'cost': 572, 'y': y}
        for y in (414, 432, 450, 468, 486, 504, 522, 540, 558, 576, 594)
    ],
    'material_subtotal': (572, 714),
}

GC_MATERIAL_PAGE = {
    'rows': [
        {'desc': (30, y), 'cost': 572, 'y': y}
        for y in (88, 106, 124, 142, 160, 178, 196, 214, 232, 250, 268, 286, 304, 322, 340, 358, 376, 394, 412, 430, 448, 466, 484, 502, 520, 538, 556, 574)
    ],
    'subtotal': (572, 604),
}


def _format_co_number_for_form(number) -> str:
    """ALDI form expects a simple sequence number (1, 2, 3), not CO-001."""
    raw = (number or '').strip()
    if not raw:
        return ''
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits:
        try:
            return str(int(digits))
        except ValueError:
            pass
    return raw


def _fmt_money(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount < 0:
        return f'(${abs(amount):,.2f})'
    return f'${amount:,.2f}'


def _fmt_date(value) -> str:
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%-d-%b') if os.name != 'nt' else value.strftime('%#d-%b')
    raw = str(value).strip()[:10]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime('%-d-%b') if os.name != 'nt' else dt.strftime('%#d-%b')
        except ValueError:
            continue
    return raw


def _norm_cost_type(value: str) -> str:
    return (value or '').strip().lower()


def _is_labor(cost_type: str) -> bool:
    return _norm_cost_type(cost_type) in LABOR_TYPES


def _is_gc_material(cost_type: str) -> bool:
    return _norm_cost_type(cost_type) in GC_MATERIAL_TYPES


def _line_amount(item) -> float:
    if isinstance(item, dict):
        for key in ('amount', 'quoted_amount'):
            val = item.get(key)
            if val not in (None, ''):
                return float(val or 0)
        return 0.0
    for attr in ('amount', 'quoted_amount'):
        val = getattr(item, attr, None)
        if val not in (None, ''):
            return float(val or 0)
    return 0.0


def _line_desc(item) -> str:
    if isinstance(item, dict):
        parts = [item.get('description') or '', item.get('cost_code') or '']
    else:
        parts = [getattr(item, 'description', None) or '', getattr(item, 'cost_code', None) or '']
    text = ' — '.join(p.strip() for p in parts if p and str(p).strip())
    return text[:120]


def _line_company(item) -> str:
    if isinstance(item, dict):
        return (item.get('company_name') or '').strip()
    return (getattr(item, 'company_name', None) or '').strip()


def _group_key(item):
    cid = ''
    if isinstance(item, dict):
        cid = str(item.get('company_id') or '').strip()
        name = (item.get('company_name') or '').strip().lower()
    else:
        cid = str(getattr(item, 'company_id', None) or '').strip()
        name = (getattr(item, 'company_name', None) or '').strip().lower()
    return cid or name or 'unknown'


def _group_line_items(line_items):
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in line_items or []:
        key = _group_key(item)
        if key not in groups:
            groups[key] = {
                'company_name': _line_company(item) or 'Subcontractor',
                'labor_lines': [],
                'material_lines': [],
                'labor_total': 0.0,
                'material_total': 0.0,
            }
            order.append(key)
        bucket = groups[key]
        amount = _line_amount(item)
        desc = _line_desc(item)
        cost_type = _norm_cost_type(item.get('cost_type') if isinstance(item, dict) else getattr(item, 'cost_type', ''))
        if _is_labor(cost_type):
            bucket['labor_lines'].append({'description': desc, 'amount': amount})
            bucket['labor_total'] += amount
        else:
            bucket['material_lines'].append({'description': desc, 'amount': amount})
            bucket['material_total'] += amount
    return [groups[k] for k in order]


def _group_allocations(allocations):
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in allocations or []:
        name = (item.get('company_name') if isinstance(item, dict) else getattr(item, 'company_name', None)) or ''
        key = name.strip().lower() or f'alloc-{len(order)}'
        if key not in groups:
            groups[key] = {
                'company_name': name.strip() or 'Subcontractor',
                'labor_lines': [],
                'material_lines': [],
                'labor_total': 0.0,
                'material_total': 0.0,
            }
            order.append(key)
        bucket = groups[key]
        amount = _line_amount(item)
        desc = _line_desc(item)
        cost_type = _norm_cost_type(item.get('cost_type') if isinstance(item, dict) else getattr(item, 'cost_type', ''))
        if _is_labor(cost_type):
            bucket['labor_lines'].append({'description': desc, 'amount': amount})
            bucket['labor_total'] += amount
        else:
            bucket['material_lines'].append({'description': desc, 'amount': amount})
            bucket['material_total'] += amount
    return [groups[k] for k in order]


def _group_linked_sub_cos(sub_cos):
    groups = []
    for sub in sub_cos or []:
        amount = float(sub.get('amount') or 0)
        groups.append({
            'company_name': (sub.get('company_name') or 'Subcontractor').strip(),
            'labor_lines': [],
            'material_lines': [{'description': sub.get('title') or sub.get('description') or sub.get('number') or '', 'amount': amount}],
            'labor_total': 0.0,
            'material_total': amount,
        })
    return groups


def _gc_material_lines(line_items, allocations):
    lines = []
    for item in line_items or []:
        cost_type = _norm_cost_type(item.get('cost_type') if isinstance(item, dict) else getattr(item, 'cost_type', ''))
        if _is_gc_material(cost_type) and not _line_company(item):
            lines.append({'description': _line_desc(item), 'amount': _line_amount(item)})
    for item in allocations or []:
        cost_type = _norm_cost_type(item.get('cost_type') if isinstance(item, dict) else getattr(item, 'cost_type', ''))
        company = (item.get('company_name') if isinstance(item, dict) else getattr(item, 'company_name', None)) or ''
        if _is_gc_material(cost_type) and not company.strip():
            lines.append({'description': _line_desc(item), 'amount': _line_amount(item)})
    if not lines:
        for item in allocations or []:
            cost_type = _norm_cost_type(item.get('cost_type') if isinstance(item, dict) else getattr(item, 'cost_type', ''))
            if _is_gc_material(cost_type):
                lines.append({'description': _line_desc(item), 'amount': _line_amount(item)})
    return lines


def _write_text(page, x, y, text, *, fontsize=9, right=False, max_width=None):
    value = (text or '').strip()
    if not value:
        return
    if max_width:
        while value and fitz.get_text_length(value, fontname='helv', fontsize=fontsize) > max_width:
            value = value[:-2].rstrip() + '…' if len(value) > 2 else value[: max(0, len(value) - 1)]
    if right:
        width = fitz.get_text_length(value, fontname='helv', fontsize=fontsize)
        x = x - width
    page.insert_text((x, y), value, fontsize=fontsize, fontname='helv', color=(0, 0, 0))


def _write_money(page, right_x, y, amount, *, blank_zero=True):
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    if blank_zero and abs(value) < 0.005:
        return
    _write_text(page, right_x, y, _fmt_money(value), fontsize=9, right=True)


def _write_multiline(page, rect: fitz.Rect, text, *, fontsize=9, line_height=11):
    value = (text or '').strip()
    if not value:
        return
    words = value.split()
    lines = []
    current = ''
    max_width = rect.width - 4
    for word in words:
        trial = f'{current} {word}'.strip()
        if fitz.get_text_length(trial, fontname='helv', fontsize=fontsize) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    y = rect.y0 + fontsize + 1
    for line in lines:
        if y > rect.y1:
            break
        page.insert_text((rect.x0 + 2, y), line, fontsize=fontsize, fontname='helv', color=(0, 0, 0))
        y += line_height


def _fill_summary_page(page, *, co, project, subs, gc_material_lines, company_info=None):
    info = company_info or {}
    store = ''
    if project is not None:
        store = (getattr(project, 'number', None) or '').strip()
        if not store:
            details = getattr(project, 'get_details', lambda: {})()
            store = (details.get('store_number') or details.get('storeNumber') or '').strip()
    # General contractor goes in the Contractor field — not the owner and not the signature block.
    contractor = (info.get('company_name') or info.get('dba_name') or '').strip()

    _write_text(page, *PAGE1['store'], store)
    _write_text(page, *PAGE1['co_number'], _format_co_number_for_form(getattr(co, 'number', None)))
    _write_text(page, *PAGE1['contractor'], contractor)
    _write_text(page, *PAGE1['ccd'], getattr(co, 'linked_drawing_revision', None) or getattr(co, 'reason', None) or '')
    scope = (getattr(co, 'title', None) or '').strip()
    _write_text(page, *PAGE1['scope'], scope, max_width=340)
    description = (getattr(co, 'description', None) or scope or '').strip()
    _write_multiline(page, PAGE1['description_box'], description)

    sub_total = 0.0
    for idx, row in enumerate(subs[: len(PAGE1['sub_rows'])]):
        cfg = PAGE1['sub_rows'][idx]
        labor = float(row.get('labor_total') or 0)
        material = float(row.get('material_total') or 0)
        cost = labor + material
        sub_total += cost
        _write_text(page, cfg['name'][0], cfg['y'], row.get('company_name') or '', max_width=145)
        _write_money(page, cfg['labor'], cfg['y'], labor)
        _write_money(page, cfg['materials'], cfg['y'], material)
        _write_money(page, cfg['cost'], cfg['y'], cost)

    gc_material_total = sum(float(x.get('amount') or 0) for x in gc_material_lines)
    gc_op_5 = round(sub_total * 0.05, 2)
    gc_op_10 = round((sub_total + gc_material_total) * 0.10, 2)
    total_sub_material = sub_total + gc_material_total
    total_gc_op = gc_op_5 + gc_op_10
    total_adjustment = total_sub_material + total_gc_op

    _write_money(page, *PAGE1['total_sub_costs'], sub_total)
    _write_money(page, *PAGE1['gc_op_5'], gc_op_5)
    for idx, line in enumerate(gc_material_lines[: len(PAGE1['gc_material_rows'])]):
        cfg = PAGE1['gc_material_rows'][idx]
        _write_text(page, cfg['desc'][0], cfg['y'], line.get('description') or '', max_width=300)
        _write_money(page, cfg['cost'], cfg['y'], line.get('amount'))
    _write_money(page, *PAGE1['total_gc_material'], gc_material_total)
    _write_money(page, *PAGE1['gc_op_10'], gc_op_10)
    _write_money(page, *PAGE1['total_sub_and_material'], total_sub_material)
    _write_money(page, *PAGE1['total_gc_op'], total_gc_op)
    _write_money(page, *PAGE1['total_adjustment'], total_adjustment)


def _fill_sub_page(page, sub: dict, *, sub_index: int):
    layout = SUB_PAGE1 if sub_index == 0 else SUB_PAGE_OTHER
    _write_text(page, *layout['name'], sub.get('company_name') or '')
    scope = ''
    if sub.get('labor_lines'):
        scope = sub['labor_lines'][0].get('description') or ''
    elif sub.get('material_lines'):
        scope = sub['material_lines'][0].get('description') or ''
    _write_text(page, *layout['scope'], scope, max_width=420)

    labor_total = 0.0
    for idx, line in enumerate((sub.get('labor_lines') or [])[: len(layout['labor_rows'])]):
        cfg = layout['labor_rows'][idx]
        amount = float(line.get('amount') or 0)
        labor_total += amount
        _write_text(page, cfg['desc'][0], cfg['y'], line.get('description') or '', max_width=210)
        _write_money(page, cfg['cost'], cfg['y'], amount)
    _write_money(page, *layout['labor_subtotal'], labor_total or sub.get('labor_total'))

    material_total = 0.0
    for idx, line in enumerate((sub.get('material_lines') or [])[: len(layout['material_rows'])]):
        cfg = layout['material_rows'][idx]
        amount = float(line.get('amount') or 0)
        material_total += amount
        _write_text(page, cfg['desc'][0], cfg['y'], line.get('description') or '', max_width=210)
        _write_money(page, cfg['cost'], cfg['y'], amount)
    _write_money(page, *layout['material_subtotal'], material_total or sub.get('material_total'))


def _fill_gc_material_page(page, lines):
    total = 0.0
    for idx, line in enumerate(lines[: len(GC_MATERIAL_PAGE['rows'])]):
        cfg = GC_MATERIAL_PAGE['rows'][idx]
        amount = float(line.get('amount') or 0)
        total += amount
        _write_text(page, cfg['desc'][0], cfg['y'], line.get('description') or '', max_width=320)
        _write_money(page, cfg['cost'], cfg['y'], amount)
    if not total:
        total = sum(float(x.get('amount') or 0) for x in lines)
    _write_money(page, *GC_MATERIAL_PAGE['subtotal'], total)


def build_print_context(co, *, ChangeEvent=None, ChangeEventLineItem=None, ChangeOrder=None,
                        allocations=None, linked_sub_cos=None, project=None):
    line_items = []
    change_event = None
    ce_id = getattr(co, 'change_event_id', None)
    if ce_id and ChangeEvent is not None:
        change_event = ChangeEvent.query.get(int(ce_id))
        if change_event and ChangeEventLineItem is not None:
            line_items = ChangeEventLineItem.query.filter_by(change_event_id=change_event.id).order_by(
                ChangeEventLineItem.sort_order, ChangeEventLineItem.id,
            ).all()

    subs = _group_line_items(line_items)
    if not subs and allocations:
        subs = _group_allocations(allocations)
    if not subs and linked_sub_cos:
        subs = _group_linked_sub_cos(linked_sub_cos)

    gc_material_lines = _gc_material_lines(line_items, allocations)
    return {
        'change_event': change_event,
        'line_items': line_items,
        'subs': subs,
        'gc_material_lines': gc_material_lines,
        'project': project,
    }


def fill_aldi_change_order_pdf(
    co,
    *,
    template_path: str,
    project=None,
    company_info=None,
    allocations=None,
    linked_sub_cos=None,
    ChangeEvent=None,
    ChangeEventLineItem=None,
    ChangeOrder=None,
    page_layout: dict | None = None,
) -> bytes:
    if not os.path.isfile(template_path):
        raise FileNotFoundError('ALDI change order template PDF is missing.')

    layout = page_layout or {
        'summary_page': 0,
        'sub_pages': [1, 2, 3, 4, 5],
        'gc_material_page': 7,
        'max_subs': 5,
    }
    ctx = build_print_context(
        co,
        ChangeEvent=ChangeEvent,
        ChangeEventLineItem=ChangeEventLineItem,
        ChangeOrder=ChangeOrder,
        allocations=allocations,
        linked_sub_cos=linked_sub_cos,
        project=project,
    )
    subs = ctx['subs'][: int(layout.get('max_subs') or 5)]
    gc_lines = ctx['gc_material_lines']

    template = fitz.open(template_path)
    output = fitz.open()
    try:
        summary_idx = int(layout.get('summary_page', 0))
        p1 = output.new_page(width=template[summary_idx].rect.width, height=template[summary_idx].rect.height)
        p1.show_pdf_page(p1.rect, template, summary_idx)
        _fill_summary_page(
            p1,
            co=co,
            project=project or ctx.get('project'),
            subs=subs,
            gc_material_lines=gc_lines,
            company_info=company_info,
        )

        sub_page_indices = list(layout.get('sub_pages') or [1, 2, 3, 4, 5])
        for i, sub in enumerate(subs):
            if i >= len(sub_page_indices):
                break
            src_idx = int(sub_page_indices[i])
            if src_idx >= template.page_count:
                continue
            page = output.new_page(width=template[src_idx].rect.width, height=template[src_idx].rect.height)
            page.show_pdf_page(page.rect, template, src_idx)
            _fill_sub_page(page, sub, sub_index=i)

        if gc_lines:
            gc_idx = int(layout.get('gc_material_page', 7))
            if gc_idx < template.page_count:
                page = output.new_page(width=template[gc_idx].rect.width, height=template[gc_idx].rect.height)
                page.show_pdf_page(page.rect, template, gc_idx)
                _fill_gc_material_page(page, gc_lines)

        return output.tobytes()
    finally:
        output.close()
        template.close()


def build_change_order_template_pdf(
    co,
    template_row,
    *,
    base_dir=None,
    project=None,
    company_info=None,
    allocations=None,
    linked_sub_cos=None,
    ChangeEvent=None,
    ChangeEventLineItem=None,
    ChangeOrder=None,
    Commitment=None,
    Company=None,
    print_options=None,
) -> bytes:
    from change_order_template_persistence import resolve_template_pdf_path
    import json

    template_path = resolve_template_pdf_path(template_row, base_dir=base_dir)
    engine = (template_row.engine or 'aldi_v1').strip().lower()
    layout = {}
    try:
        layout = json.loads(template_row.page_layout_json) if template_row.page_layout_json else {}
    except (TypeError, json.JSONDecodeError):
        layout = {}

    if engine in ('aldi', 'aldi_v1', 'aldi_co'):
        return fill_aldi_change_order_pdf(
            co,
            template_path=template_path,
            project=project,
            company_info=company_info,
            allocations=allocations,
            linked_sub_cos=linked_sub_cos,
            ChangeEvent=ChangeEvent,
            ChangeEventLineItem=ChangeEventLineItem,
            ChangeOrder=ChangeOrder,
            page_layout=layout,
        )
    if engine in ('sub_co', 'sub_co_v1', 'subcontract_co'):
        from sub_change_order_pdf import fill_sub_change_order_pdf
        return fill_sub_change_order_pdf(
            co,
            template_path=template_path,
            project=project,
            company_info=company_info,
            allocations=allocations,
            Commitment=Commitment,
            ChangeOrder=ChangeOrder,
            Company=Company,
            print_options=print_options,
        )
    raise ValueError(f'Unsupported change order template engine: {engine}')
