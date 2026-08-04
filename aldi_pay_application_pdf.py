"""Fill ALDI pay application PDF (G702, G703, retainage, change order summaries)."""
from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from typing import Any

import fitz

# G702 application page (0) — money column right edge
G702_MONEY_X = 360.0
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
    'owner': (88, 82),
    'project': (283, 82),
    'app_no': (469, 82),
    'period_to': (442, 120),
    'project_nos': (442, 98),
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
G703_HEADER = {
    'app_no': (520, 72),
    'app_date': (520, 84),
    'period_to': (520, 96),
}

G702_PAGES = (0, 1)
G703_PAGES = (2, 3, 4)
CO_SUMMARY_BASE_PAGE = 5
CO_SUMMARY_PAGES_EACH = 3
MAX_CO_SUMMARY_SLOTS = 10


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


def _norm_key(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (text or '').lower())


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


def _write_money(page, right_x, y, amount, *, blank_zero=False):
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    if blank_zero and abs(value) < 0.005:
        return
    _write_text(page, right_x, y, _fmt_money(value), fontsize=9, right=True)


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
            money_x = [w[0] for w in row_words if w[4].startswith('$')]
            if not money_x:
                continue
            desc_parts = []
            for w in row_words:
                if w[4].startswith('$'):
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
    # fuzzy: substring
    for key, row in index.items():
        if len(key) > 8 and key in candidates[0]:
            return row
        if candidates[0] and candidates[0] in key:
            return row
    return None


def _fill_g702_page(page, payload: dict[str, Any]) -> None:
    project = payload.get('project') or {}
    period = payload.get('period') or {}
    g702 = payload.get('g702') or {}
    co = payload.get('co_summary') or {}

    _write_text(page, *G702_HEADER['owner'], project.get('owner') or '', max_width=140)
    _write_text(page, *G702_HEADER['project'], project.get('name') or '', max_width=100)
    _write_text(page, *G702_HEADER['app_no'], str(period.get('periodNumber') or ''), max_width=60)
    _write_text(page, *G702_HEADER['period_to'], period.get('periodEnd') or '', max_width=80)
    _write_text(page, *G702_HEADER['project_nos'], project.get('project_numbers') or '', max_width=80)

    _write_money(page, G702_MONEY_X, G702_LINES['original'], g702.get('g702Original'))
    _write_money(page, G702_MONEY_X, G702_LINES['net_co'], g702.get('g702ChangeOrders'))
    _write_money(page, G702_MONEY_X, G702_LINES['contract_sum'], g702.get('contractSumToDate'))
    _write_money(page, G702_MONEY_X, G702_LINES['completed'], g702.get('cumulativeCompleted'))
    _write_money(page, G702_MONEY_X, G702_LINES['retainage_work'], g702.get('retainageCompleted'))
    _write_money(page, G702_MONEY_X, G702_LINES['retainage_stored'], g702.get('retainageStored'))
    _write_money(page, G702_MONEY_X, G702_LINES['retainage_total'], g702.get('cumulativeRetainage'))
    _write_money(page, G702_MONEY_X, G702_LINES['earned_less_ret'], g702.get('earnedLessRetainage'))
    _write_money(page, G702_MONEY_X, G702_LINES['previous_payments'], g702.get('previousEarnedLessRetainage'))
    _write_money(page, G702_MONEY_X, G702_LINES['current_due'], g702.get('currentDue'))
    _write_money(page, G702_MONEY_X, G702_LINES['balance_finish'], g702.get('balanceToFinish'))

    if co:
        _write_money(page, G702_CO_SUMMARY['prev_add'][0], G702_CO_SUMMARY['prev_add'][1], co.get('prev_additions'), blank_zero=True)
        _write_money(page, G702_CO_SUMMARY['prev_ded'][0], G702_CO_SUMMARY['prev_ded'][1], co.get('prev_deductions'), blank_zero=True)
        _write_money(page, G702_CO_SUMMARY['this_add'][0], G702_CO_SUMMARY['this_add'][1], co.get('this_additions'), blank_zero=True)
        _write_money(page, G702_CO_SUMMARY['this_ded'][0], G702_CO_SUMMARY['this_ded'][1], co.get('this_deductions'), blank_zero=True)
        _write_money(page, G702_CO_SUMMARY['total_add'][0], G702_CO_SUMMARY['total_add'][1], co.get('total_additions'), blank_zero=True)
        _write_money(page, G702_CO_SUMMARY['total_ded'][0], G702_CO_SUMMARY['total_ded'][1], co.get('total_deductions'), blank_zero=True)


def _fill_g703_line(page, y: float, line: dict, retainage_rate: float) -> None:
    scheduled = float(line.get('scheduled') or 0)
    prev = float(line.get('prev_work') or 0)
    work = float(line.get('work_this_period') or 0)
    mat = float(line.get('materials_stored') or 0)
    completed = float(line.get('completed_to_date') or (prev + work + mat))
    pct = int(round((completed / scheduled) * 100)) if scheduled > 0 else 0
    balance = max(0.0, scheduled - completed)
    retainage = float(line.get('retainage') or ((work + mat) * retainage_rate))

    _write_money(page, G703_COL['c'], y, scheduled, blank_zero=True)
    _write_money(page, G703_COL['d'], y, prev, blank_zero=True)
    _write_money(page, G703_COL['e'], y, work, blank_zero=True)
    _write_money(page, G703_COL['f'], y, mat, blank_zero=True)
    _write_money(page, G703_COL['g'], y, completed, blank_zero=True)
    _write_text(page, G703_COL['h'], y, f'{pct}%', fontsize=8)
    _write_money(page, G703_COL['i'], y, balance, blank_zero=True)
    _write_money(page, G703_COL['j'], y, retainage, blank_zero=True)


def _fill_g703_headers(page, period: dict) -> None:
    _write_text(page, G703_HEADER['app_no'][0], G703_HEADER['app_no'][1], str(period.get('periodNumber') or ''), max_width=40)
    _write_text(page, G703_HEADER['app_date'][0], G703_HEADER['app_date'][1], period.get('periodEnd') or '', max_width=60)
    _write_text(page, G703_HEADER['period_to'][0], G703_HEADER['period_to'][1], period.get('periodEnd') or '', max_width=60)


def _fill_co_summary_banner(page, slot: int, period: dict, cos: list[dict]) -> None:
    nums = ', '.join((c.get('number') or str(c.get('id') or '')) for c in cos[:6])
    title = f'Change Order Summary #{slot}'
    if nums:
        title += f' — {nums}'
    _write_text(page, 30, 28, title, fontsize=10, max_width=400)
    _write_text(page, 30, 40, period.get('periodEnd') or '', fontsize=9)


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
                _fill_co_summary_banner(page, co_slot, period, cos_this)
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
