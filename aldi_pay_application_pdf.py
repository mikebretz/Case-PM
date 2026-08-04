"""Fill ALDI pay application PDF (G702, G703, retainage, change order summaries)."""
from __future__ import annotations

import io
import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, Iterable

import fitz

# G702 application page (0) — money column right edge
G702_MONEY_X = 360.0
G702_MONEY_CELL_W = 92.0
G702_LINES = {
    'original': 258.9,
    'net_co': 268.3,
    'contract_sum': 277.7,
    'completed': 287.0,
    'retainage_work': 316.1,
    'retainage_stored': 334.8,
    'retainage_total': 366.3,
    'earned_less_ret': 376.7,
    'previous_payments': 395.4,
    'current_due': 404.8,
    'balance_finish': 414.1,
}
G702_HEADER = {
    'owner': (88, 82, 230, 94),
    'project': (283, 82, 385, 94),
    'app_no': (469, 82, 540, 94),
    'period_to': (442, 120, 540, 132),
    'project_nos': (442, 98, 540, 110),
}
G702_CO_SUMMARY = {
    'prev_add': (280, 460.9),
    'prev_ded': (345, 460.9),
    'this_add': (280, 477.6),
    'this_ded': (345, 477.6),
    'total_add': (280, 491.8),
    'total_ded': (345, 491.8),
}

G703_COL = {'c': 351.7, 'd': 415.8, 'e': 468.5, 'f': 525.0, 'g': 589.7, 'h': 645.0, 'i': 690.1, 'j': 751.0}
G703_COL_CELL_W = 58.0
G703_HEADER = {
    'app_no': (500, 68, 560, 80),
    'app_date': (500, 80, 580, 92),
    'period_to': (500, 92, 580, 104),
}

G702_PAGES = (0, 1)
G703_PAGES = (2, 3, 4)
CO_SUMMARY_BASE_PAGE = 5
CO_SUMMARY_PAGES_EACH = 3
MAX_CO_SUMMARY_SLOTS = 10

_PLACEHOLDER_DATE = re.compile(r'^(\d{1,2})/00/00$|^01/00/00$')
_MONEY_DEC = re.compile(r'^[\d,]+\.\d{2}$')


def default_template_path() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, 'static', 'templates', 'pay_applications', 'aldi_pay_app_template.pdf')


def _fmt_money(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount < 0:
        return f'(${abs(amount):,.2f})'
    return f'${amount:,.2f}'


def _fmt_date_mdy(value) -> str:
    """Short US date: month/day/year (e.g. 7/31/2026)."""
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        dt = value
    else:
        raw = str(value).strip()[:10]
        dt = None
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return raw
    return f'{dt.month}/{dt.day}/{dt.year}'


def _norm_key(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (text or '').lower())


def _paint_white(page, rect: fitz.Rect, *, pad: float = 1.5) -> None:
    r = fitz.Rect(rect)
    r.x0 -= pad
    r.y0 -= pad
    r.x1 += pad
    r.y1 += pad
    page.draw_rect(r, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)


def _erase_rect(page, rect: fitz.Rect, *, pad: float = 1.5) -> None:
    _paint_white(page, rect, pad=pad)


def _erase_region(page, x0: float, y0: float, x1: float, y1: float) -> None:
    _erase_rect(page, fitz.Rect(x0, y0, x1, y1))


def _money_rects_from_words(words: list) -> list[fitz.Rect]:
    """Merge $ + amount word pairs into one cell rect."""
    rects: list[fitz.Rect] = []
    i = 0
    while i < len(words):
        w = words[i]
        token = w[4]
        if token == '$' and i + 1 < len(words) and _MONEY_DEC.match(words[i + 1][4]):
            nxt = words[i + 1]
            rects.append(fitz.Rect(w[0], min(w[1], nxt[1]), nxt[2], max(w[3], nxt[3])))
            i += 2
            continue
        if token.startswith('$') and re.search(r'\d', token):
            rects.append(fitz.Rect(w[0], w[1], w[2], w[3]))
        elif _MONEY_DEC.match(token) and i > 0 and words[i - 1][4] == '$':
            pass  # handled with $
        i += 1
    return rects


def _row_y_center(rect: fitz.Rect) -> float:
    return (rect.y0 + rect.y1) / 2


def _money_rects_on_page(page, *, y_center: float | None = None, y_tol: float = 4.5) -> list[fitz.Rect]:
    words = page.get_text('words')
    rects = _money_rects_from_words(words)
    if y_center is None:
        return rects
    return [r for r in rects if abs(_row_y_center(r) - y_center) <= y_tol]


def _scrub_money_cell(page, right_x: float, y: float, *, width: float | None = None) -> None:
    w = width or G702_MONEY_CELL_W
    _erase_region(page, right_x - w, y - 11, right_x + 2, y + 4)
    for rect in _money_rects_on_page(page, y_center=y):
        if rect.x1 <= right_x + 4 and rect.x0 >= right_x - w - 4:
            _erase_rect(page, rect)


def _scrub_g703_row(page, y: float) -> None:
    """Clear spreadsheet cells on one G703 row (money + percent placeholder)."""
    for col_x in G703_COL.values():
        _scrub_money_cell(page, col_x + G703_COL_CELL_W * 0.85, y, width=G703_COL_CELL_W)
    words = page.get_text('words')
    for w in words:
        if abs(w[1] - y) > 5 and abs(w[3] - y) > 5:
            continue
        token = w[4]
        if token in ('0', '0%') and G703_COL['h'] - 25 < w[0] < G703_COL['h'] + 25:
            _erase_rect(page, fitz.Rect(w[0], w[1], w[2], w[3]))


def _scrub_text_in_box(page, box: tuple[float, float, float, float]) -> None:
    x0, y0, x1, y1 = box
    for w in page.get_text('words'):
        cx = (w[0] + w[2]) / 2
        cy = (w[1] + w[3]) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            if w[4] in ('OWNER:', 'PROJECT:', 'APPLICATION', 'NO:', 'PERIOD', 'TO:', 'NOS:'):
                continue
            _erase_rect(page, fitz.Rect(w[0], w[1], w[2], w[3]))


def _scrub_placeholder_dates(page) -> None:
    for w in page.get_text('words'):
        if _PLACEHOLDER_DATE.match(w[4]) or w[4] == '01/00/00':
            _erase_rect(page, fitz.Rect(w[0], w[1], w[2], w[3]))


def _replace_brand_aldi(page, client_name: str) -> None:
    """Replace visible ALDI owner branding with the project client name."""
    name = (client_name or '').strip()
    if not name or name.upper() == 'ALDI':
        return
    for rect in page.search_for('ALDI'):
        _erase_rect(page, rect, pad=2)
        fontsize = max(7, min(11, rect.height + 2))
        page.insert_text(
            (rect.x0, rect.y1 - 1),
            name,
            fontsize=fontsize,
            fontname='helv',
            color=(0, 0, 0),
        )
    for rect in page.search_for('Aldi'):
        if rect.width < 20:
            continue
        _erase_rect(page, rect, pad=2)
        page.insert_text(
            (rect.x0, rect.y1 - 1),
            name,
            fontsize=max(7, min(10, rect.height + 2)),
            fontname='helv',
            color=(0, 0, 0),
        )


def _write_text(page, x, y, text, *, fontsize=9, right=False, max_width=None, erase_box=None):
    value = (text or '').strip()
    if not value:
        return
    if erase_box:
        _scrub_text_in_box(page, erase_box)
    if max_width:
        while value and fitz.get_text_length(value, fontname='helv', fontsize=fontsize) > max_width:
            value = value[:-2].rstrip() + '…' if len(value) > 2 else value[: max(0, len(value) - 1)]
    if right:
        width = fitz.get_text_length(value, fontname='helv', fontsize=fontsize)
        x = x - width
    page.insert_text((x, y), value, fontsize=fontsize, fontname='helv', color=(0, 0, 0))


def _replace_money(page, right_x: float, y: float, amount, *, blank_zero: bool = True, width: float | None = None) -> None:
    _scrub_money_cell(page, right_x, y, width=width)
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    if blank_zero and abs(value) < 0.005:
        return
    _write_text(page, right_x, y, _fmt_money(value), fontsize=9, right=True)


def _replace_text_cell(page, box: tuple[float, float, float, float], text: str, *, y_baseline: float | None = None) -> None:
    _scrub_text_in_box(page, box)
    x0, y0, x1, y1 = box
    y = y_baseline if y_baseline is not None else y1 - 2
    _write_text(page, x0, y, text, max_width=(x1 - x0))


@lru_cache(maxsize=2)
def _g703_row_index(template_path: str) -> dict[str, dict]:
    """Map normalized description keys to template row coordinates."""
    doc = fitz.open(template_path)
    index: dict[str, dict] = {}
    for pi in G703_PAGES:
        page = doc[pi]
        words = page.get_text('words')
        by_y: dict[float, list] = {}
        for w in words:
            y = round(w[1], 1)
            by_y.setdefault(y, []).append(w)
        for y, row_words in by_y.items():
            row_words.sort(key=lambda w: w[0])
            money_x = [w[0] for w in row_words if w[4].startswith('$') or w[4] == '$']
            if not money_x and not any(_MONEY_DEC.match(w[4]) for w in row_words):
                continue
            desc_parts = []
            for w in row_words:
                if w[4].startswith('$') or _MONEY_DEC.match(w[4]):
                    break
                if w[4] in ('0', '0%'):
                    continue
                desc_parts.append(w[4])
            desc = ' '.join(desc_parts).strip()
            if not desc or desc in ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'):
                continue
            if 'DIVISION' in desc or 'DESCRIPTION OF WORK' in desc:
                continue
            key = _norm_key(desc)
            if key and key not in index:
                index[key] = {'page': pi, 'y': y + 7, 'desc': desc}
    doc.close()
    return index


def _match_row(index: dict[str, dict], line: dict) -> dict | None:
    candidates = []
    cc = (line.get('cost_code') or '').strip()
    desc = (line.get('description') or '').strip()
    if cc:
        candidates.append(_norm_key(f'{cc} {desc}'))
        candidates.append(_norm_key(cc))
    candidates.append(_norm_key(desc))
    candidates.append(_norm_key(f'{line.get("division") or ""} {desc}'))
    for key in candidates:
        if key and key in index:
            return index[key]
    for key, row in index.items():
        if candidates and candidates[0] and (key in candidates[0] or candidates[0] in key):
            return row
    return None


def _prepare_filled_page(page, client_name: str) -> None:
    _replace_brand_aldi(page, client_name)
    _scrub_placeholder_dates(page)


def _fill_g702_page(page, payload: dict[str, Any]) -> None:
    project = payload.get('project') or {}
    period = payload.get('period') or {}
    g702 = payload.get('g702') or {}
    co = payload.get('co_summary') or {}
    period_end = _fmt_date_mdy(period.get('periodEnd'))

    _replace_text_cell(page, G702_HEADER['owner'], project.get('client_name') or project.get('owner') or '')
    _replace_text_cell(page, G702_HEADER['project'], project.get('name') or '')
    _replace_text_cell(page, G702_HEADER['app_no'], str(period.get('periodNumber') or ''))
    _replace_text_cell(page, G702_HEADER['period_to'], period_end)
    _replace_text_cell(page, G702_HEADER['project_nos'], project.get('project_numbers') or '')

    for key, y in G702_LINES.items():
        val = {
            'original': g702.get('g702Original'),
            'net_co': g702.get('g702ChangeOrders'),
            'contract_sum': g702.get('contractSumToDate'),
            'completed': g702.get('cumulativeCompleted'),
            'retainage_work': g702.get('retainageCompleted'),
            'retainage_stored': g702.get('retainageStored'),
            'retainage_total': g702.get('cumulativeRetainage'),
            'earned_less_ret': g702.get('earnedLessRetainage'),
            'previous_payments': g702.get('previousEarnedLessRetainage'),
            'current_due': g702.get('currentDue'),
            'balance_finish': g702.get('balanceToFinish'),
        }.get(key)
        _replace_money(page, G702_MONEY_X, y, val, blank_zero=True)

    if co:
        for (rx, ry), field in (
            (G702_CO_SUMMARY['prev_add'], 'prev_additions'),
            (G702_CO_SUMMARY['prev_ded'], 'prev_deductions'),
            (G702_CO_SUMMARY['this_add'], 'this_additions'),
            (G702_CO_SUMMARY['this_ded'], 'this_deductions'),
            (G702_CO_SUMMARY['total_add'], 'total_additions'),
            (G702_CO_SUMMARY['total_ded'], 'total_deductions'),
        ):
            _replace_money(page, rx, ry, co.get(field), blank_zero=True, width=72)


def _fill_g703_line(page, y: float, line: dict, retainage_rate: float) -> None:
    _scrub_g703_row(page, y)
    scheduled = float(line.get('scheduled') or 0)
    prev = float(line.get('prev_work') or 0)
    work = float(line.get('work_this_period') or 0)
    mat = float(line.get('materials_stored') or 0)
    completed = float(line.get('completed_to_date') or (prev + work + mat))
    pct = int(round((completed / scheduled) * 100)) if scheduled > 0 else 0
    balance = max(0.0, scheduled - completed)
    retainage = float(line.get('retainage') or ((work + mat) * retainage_rate))

    _replace_money(page, G703_COL['c'], y, scheduled, blank_zero=True, width=G703_COL_CELL_W)
    _replace_money(page, G703_COL['d'], y, prev, blank_zero=True, width=G703_COL_CELL_W)
    _replace_money(page, G703_COL['e'], y, work, blank_zero=True, width=G703_COL_CELL_W)
    _replace_money(page, G703_COL['f'], y, mat, blank_zero=True, width=G703_COL_CELL_W)
    _replace_money(page, G703_COL['g'], y, completed, blank_zero=True, width=G703_COL_CELL_W)
    if pct > 0:
        _scrub_money_cell(page, G703_COL['h'] + 10, y, width=20)
        _write_text(page, G703_COL['h'], y, f'{pct}%', fontsize=8)
    _replace_money(page, G703_COL['i'], y, balance, blank_zero=True, width=G703_COL_CELL_W)
    _replace_money(page, G703_COL['j'], y, retainage, blank_zero=True, width=G703_COL_CELL_W)


def _fill_g703_headers(page, period: dict) -> None:
    period_end = _fmt_date_mdy(period.get('periodEnd'))
    _replace_text_cell(page, G703_HEADER['app_no'], str(period.get('periodNumber') or ''))
    _replace_text_cell(page, G703_HEADER['app_date'], period_end)
    _replace_text_cell(page, G703_HEADER['period_to'], period_end)


def _fill_co_summary_banner(page, slot: int, period: dict, cos: list[dict], client_name: str) -> None:
    nums = ', '.join((c.get('number') or str(c.get('id') or '')) for c in cos[:6])
    title = f'Change Order Summary #{slot}'
    if nums:
        title += f' — {nums}'
    _erase_region(page, 28, 18, 420, 48)
    _write_text(page, 30, 28, title, fontsize=10, max_width=400)
    _write_text(page, 30, 40, _fmt_date_mdy(period.get('periodEnd')), fontsize=9)


def _page_list(co_summary_slot: int) -> list[int]:
    pages = list(G702_PAGES) + list(G703_PAGES)
    if co_summary_slot and 1 <= co_summary_slot <= MAX_CO_SUMMARY_SLOTS:
        start = CO_SUMMARY_BASE_PAGE + (co_summary_slot - 1) * CO_SUMMARY_PAGES_EACH
        pages.extend(range(start, start + CO_SUMMARY_PAGES_EACH))
    return pages


def generate_aldi_pay_application_pdf(payload: dict[str, Any], *, template_path: str | None = None) -> bytes:
    """Build pay app PDF from client-computed G702/G703 payload."""
    path = template_path or default_template_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(f'ALDI pay app template not found: {path}')

    row_index = _g703_row_index(path)
    src = fitz.open(path)
    out = fitz.open()
    period = payload.get('period') or {}
    g702 = payload.get('g702') or {}
    project = payload.get('project') or {}
    client_name = (
        project.get('client_name')
        or project.get('owner')
        or project.get('name')
        or ''
    )
    retainage_rate = float(g702.get('retainageRate') or 0.1)
    co_slot = int(payload.get('co_summary_slot') or 0)
    cos_this = payload.get('change_orders_this_period') or []
    g703_lines = payload.get('g703_lines') or []

    for page_no in _page_list(co_slot):
        if page_no >= src.page_count:
            continue
        src_page = src[page_no]
        page = out.new_page(width=src_page.rect.width, height=src_page.rect.height)
        page.show_pdf_page(page.rect, src, page_no)
        _prepare_filled_page(page, client_name)

        if page_no in G702_PAGES:
            _fill_g702_page(page, payload)
        elif page_no in G703_PAGES:
            _fill_g703_headers(page, period)
            for line in g703_lines:
                row = _match_row(row_index, line)
                if row and row['page'] == page_no:
                    _fill_g703_line(page, row['y'], line, retainage_rate)
        elif co_slot and page_no >= CO_SUMMARY_BASE_PAGE:
            slot_start = CO_SUMMARY_BASE_PAGE + (co_slot - 1) * CO_SUMMARY_PAGES_EACH
            if slot_start <= page_no < slot_start + CO_SUMMARY_PAGES_EACH:
                _fill_co_summary_banner(page, co_slot, period, cos_this, client_name)
                for line in g703_lines:
                    if not line.get('co_affected'):
                        continue
                    row = _match_row(row_index, line)
                    if row and row['page'] == page_no:
                        _fill_g703_line(page, row['y'], line, retainage_rate)

    src.close()
    buf = io.BytesIO()
    out.save(buf, deflate=True)
    out.close()
    return buf.getvalue()
