"""Grid/cell-based title block parser for construction drawing PDFs.

Architectural title blocks (Bluebeam AutoMark style) place the **value above**
a small **label at the bottom of each cell**:
  ┌─────────────────┐
  │   A-212         │  ← largest text = drawing / sheet number
  │ Drawing No.     │  ← tiny label tucked in bottom of cell
  └─────────────────┘
  ┌─────────────────┐
  │ Interior Elev.  │  ← drawing name (cell directly above)
  │ Drawing Name:   │
  └─────────────────┘

Detection strategy (Bluebeam region + spatial index):
1. Locate bottom-right title-block column via vector frame lines + x-position
2. Cluster text into vertical cells (y-gap splits or vector rectangles)
3. Within each cell: bottom line = label, largest font above = value
4. Sheet number from southernmost cell with "Drawing No" label
5. Drawing name from cell stacked directly above that cell
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from drawing_persistence import (
    ARCH_SCALE_RE,
    DATE_FALLBACK_RE,
    DATE_RE,
    RATIO_SCALE_RE,
    REV_ISSUE_RE,
    REV_NO_RE,
    REVISION_LOOSE_RE,
    REVISION_RE,
    TITLE_HINT_RE,
    extract_drawing_date_from_text,
    extract_revision_from_text,
    extract_scale_from_text,
    is_plausible_drawing_sheet,
    normalize_sheet_number,
)

# A-212, A-102, S-201, A-102a (optional suffix letter)
DRAWING_NUMBER_VALUE_RE = re.compile(
    r'^([A-Z]{1,3})-(\d{1,4})([A-Za-z])?$',
    re.I,
)
DRAWING_NUMBER_LOOSE_RE = re.compile(
    r'\b([A-Z]{1,3})\s*-\s*(\d{1,4})([A-Za-z])?\b',
    re.I,
)
CSI_SHEET_IN_CELL_RE = re.compile(r'^([A-Z]{1,3})-(\d{1,2})\.(\d{2})$', re.I)

DRAWING_NO_LABEL_RE = re.compile(
    r'^drawing\s*(?:no\.?|num(?:ber)?)\s*:?\s*$',
    re.I,
)
SHEET_NO_LABEL_RE = re.compile(
    r'^(?:sheet|sht|dwg)\s*(?:no\.?|num(?:ber)?)\s*:?\s*$',
    re.I,
)
DRAWING_NAME_LABEL_RE = re.compile(
    r'^drawing\s*name\s*:?\s*$',
    re.I,
)
PROJECT_NO_LABEL_RE = re.compile(
    r'^(?:project|job)\s*(?:no\.?|num(?:ber)?)\s*:?\s*$',
    re.I,
)
PROJECT_TYPE_LABEL_RE = re.compile(
    r'(?:project\s*type|building\s*type|type\s*of\s*(?:project|work|construction)|'
    r'occupancy|facility\s*type|construction\s*type)',
    re.I,
)
REV_LABEL_BOTTOM_RE = re.compile(
    r'^rev(?:ision)?\s*(?:no\.?|num(?:ber)?)?\s*:?\s*$',
    re.I,
)
NOTE_FRAGMENT_RE = re.compile(
    r'\b(DEMO(?:\'?D)?|REINFORCING|CONTRACTOR|INSTALL|VERIFY|REFER|SEE\s+STRUCTURAL|TO\s+BE)\b',
    re.I,
)
PROJECT_NUMBER_VALUE_RE = re.compile(r'^[A-Z0-9][A-Z0-9\-./]{2,24}$', re.I)


@dataclass
class WordSpan:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int = 0
    line: int = 0
    font_size: float = 0.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return max(1.0, self.y1 - self.y0)


@dataclass
class TextLine:
    y0: float
    y1: float
    x0: float
    x1: float
    text: str
    words: list[WordSpan]
    height: float
    font_size: float = 0.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class GridRect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def width(self) -> float:
        return max(1.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(1.0, self.y1 - self.y0)

    def contains_point(self, x: float, y: float, pad: float = 2.0) -> bool:
        return (self.x0 - pad) <= x <= (self.x1 + pad) and (self.y0 - pad) <= y <= (self.y1 + pad)


@dataclass
class LabeledCell:
    """One title-block grid cell: value text above, label text at bottom."""
    x0: float
    y0: float
    x1: float
    y1: float
    lines: list[TextLine]
    label_text: str = ''
    label_kind: str | None = None
    value_text: str = ''
    value_height: float = 0.0
    value_font_size: float = 0.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _spans_from_dict(page, min_y_ratio: float = 0.50) -> list[WordSpan]:
    """Extract positioned text spans with font sizes from PDF dict output."""
    page_h = page.rect.height
    spans: list[WordSpan] = []
    try:
        payload = page.get_text('dict') or {}
    except Exception:
        return spans
    for b_idx, block in enumerate(payload.get('blocks') or []):
        if block.get('type') != 0:
            continue
        for l_idx, line in enumerate(block.get('lines') or []):
            for span in line.get('spans') or []:
                text = str(span.get('text') or '').strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span.get('bbox') or (0, 0, 0, 0)
                x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
                if y0 < page_h * min_y_ratio:
                    continue
                size = float(span.get('size') or max(1.0, y1 - y0))
                spans.append(WordSpan(x0, y0, x1, y1, text, b_idx, l_idx, size))
    return spans


def _words_from_page(page, min_y_ratio: float = 0.52) -> list[WordSpan]:
    """Fallback word list when dict spans are unavailable."""
    spans = _spans_from_dict(page, min_y_ratio)
    if spans:
        return spans
    page_h = page.rect.height
    words: list[WordSpan] = []
    for item in page.get_text('words') or []:
        if len(item) < 5:
            continue
        x0, y0, x1, y1, text = float(item[0]), float(item[1]), float(item[2]), float(item[3]), str(item[4]).strip()
        if not text or y0 < page_h * min_y_ratio:
            continue
        h = max(1.0, y1 - y0)
        words.append(WordSpan(
            x0, y0, x1, y1, text,
            int(item[5]) if len(item) > 5 else 0,
            int(item[6]) if len(item) > 6 else 0,
            h,
        ))
    return words


def _median_height(words: list[WordSpan]) -> float:
    return statistics.median([w.height for w in words]) if words else 8.0


def _median_font_size(words: list[WordSpan]) -> float:
    sizes = [w.font_size for w in words if w.font_size > 0]
    return statistics.median(sizes) if sizes else _median_height(words)


def _cluster_words_into_lines(words: list[WordSpan], y_tol: float) -> list[TextLine]:
    if not words:
        return []
    sorted_w = sorted(words, key=lambda w: (w.cy, w.x0))
    lines: list[TextLine] = []
    bucket: list[WordSpan] = []
    row_y = None
    for w in sorted_w:
        if row_y is None or abs(w.cy - row_y) <= y_tol:
            bucket.append(w)
            row_y = w.cy if row_y is None else (row_y + w.cy) / 2
        else:
            bucket.sort(key=lambda x: x.x0)
            sizes = [x.font_size for x in bucket if x.font_size > 0]
            lines.append(TextLine(
                min(x.y0 for x in bucket), max(x.y1 for x in bucket),
                min(x.x0 for x in bucket), max(x.x1 for x in bucket),
                ' '.join(x.text for x in bucket), bucket,
                max(x.height for x in bucket),
                max(sizes) if sizes else max(x.height for x in bucket),
            ))
            bucket = [w]
            row_y = w.cy
    if bucket:
        bucket.sort(key=lambda x: x.x0)
        sizes = [x.font_size for x in bucket if x.font_size > 0]
        lines.append(TextLine(
            min(x.y0 for x in bucket), max(x.y1 for x in bucket),
            min(x.x0 for x in bucket), max(x.x1 for x in bucket),
            ' '.join(x.text for x in bucket), bucket,
            max(x.height for x in bucket),
            max(sizes) if sizes else max(x.height for x in bucket),
        ))
    return lines


def _classify_bottom_label(text: str) -> str | None:
    t = text.strip()
    if not t:
        return None
    if DRAWING_NO_LABEL_RE.match(t) or SHEET_NO_LABEL_RE.match(t):
        return 'drawing_number'
    if DRAWING_NAME_LABEL_RE.match(t):
        return 'drawing_name'
    if PROJECT_NO_LABEL_RE.match(t):
        return 'project_number'
    if PROJECT_TYPE_LABEL_RE.search(t):
        return 'project_type'
    if REV_LABEL_BOTTOM_RE.match(t) or REVISION_RE.match(t):
        return 'revision'
    return None


def _lines_to_labeled_cell(lines: list[TextLine], med_h: float, med_size: float) -> LabeledCell | None:
    if not lines:
        return None
    lines = sorted(lines, key=lambda ln: ln.y0)
    x0 = min(ln.x0 for ln in lines)
    x1 = max(ln.x1 for ln in lines)
    y0 = min(ln.y0 for ln in lines)
    y1 = max(ln.y1 for ln in lines)

    label_kind = None
    label_text = ''
    label_idx = None
    label_size = med_size

    # Label is on the bottom line(s) — much smaller font than the value above
    for i in range(len(lines) - 1, max(-1, len(lines) - 3), -1):
        ln = lines[i]
        kind = _classify_bottom_label(ln.text)
        if kind:
            label_kind = kind
            label_text = ln.text.strip()
            label_idx = i
            label_size = ln.font_size or ln.height
            break
        lower = ln.text.lower()
        fs = ln.font_size or ln.height
        is_small = fs <= med_size * 0.78 or ln.height <= med_h * 0.72
        if is_small:
            if 'drawing' in lower and ('no' in lower or 'number' in lower or 'num' in lower):
                label_kind = 'drawing_number'
                label_text = ln.text.strip()
                label_idx = i
                label_size = fs
                break
            if 'drawing' in lower and 'name' in lower:
                label_kind = 'drawing_name'
                label_text = ln.text.strip()
                label_idx = i
                label_size = fs
                break
            if 'project' in lower and ('no' in lower or 'number' in lower or 'num' in lower):
                label_kind = 'project_number'
                label_text = ln.text.strip()
                label_idx = i
                label_size = fs
                break
            if PROJECT_TYPE_LABEL_RE.search(ln.text):
                label_kind = 'project_type'
                label_text = ln.text.strip()
                label_idx = i
                label_size = fs
                break

    value_lines = lines[:label_idx] if label_idx is not None else []
    if not value_lines and label_idx is None:
        return None

    value_text = ''
    value_height = 0.0
    value_font_size = 0.0
    if value_lines:
        # Value = largest font line(s) above the label (typically 3–5× label size)
        size_threshold = max(med_size * 0.85, label_size * 1.35)
        large = [ln for ln in value_lines if (ln.font_size or ln.height) >= size_threshold]
        if not large:
            large = [max(value_lines, key=lambda ln: (ln.font_size or ln.height, len(ln.text)))]
        large.sort(key=lambda ln: ln.y0)
        value_text = ' '.join(ln.text.strip() for ln in large).strip()
        value_height = max(ln.height for ln in large)
        value_font_size = max(ln.font_size or ln.height for ln in large)

    return LabeledCell(
        x0, y0, x1, y1, lines, label_text, label_kind, value_text, value_height, value_font_size,
    )


def _cluster_lines_into_cells(lines: list[TextLine], cell_gap: float) -> list[LabeledCell]:
    if not lines:
        return []
    lines = sorted(lines, key=lambda ln: ln.y0)
    med_h = statistics.median([ln.height for ln in lines]) if lines else 8.0
    med_size = statistics.median([ln.font_size or ln.height for ln in lines]) if lines else med_h
    groups: list[list[TextLine]] = []
    current: list[TextLine] = [lines[0]]
    for prev, ln in zip(lines, lines[1:]):
        if ln.y0 - prev.y1 > cell_gap:
            groups.append(current)
            current = [ln]
        else:
            current.append(ln)
    groups.append(current)

    cells: list[LabeledCell] = []
    for group in groups:
        cell = _lines_to_labeled_cell(group, med_h, med_size)
        if cell and (cell.label_kind or cell.value_text):
            cells.append(cell)
    return cells


def _extract_vector_segments(page) -> tuple[list[float], list[float]]:
    """Horizontal and vertical line positions in bottom-right title block."""
    page_w, page_h = page.rect.width, page.rect.height
    x_min = page_w * 0.45
    y_min = page_h * 0.52
    horiz: list[float] = []
    vert: list[float] = []
    try:
        for drawing in page.get_drawings() or []:
            for item in drawing.get('items') or []:
                if not item:
                    continue
                op = item[0]
                if op == 'l' and len(item) >= 3:
                    p1, p2 = item[1], item[2]
                    x1, y1 = float(p1.x), float(p1.y)
                    x2, y2 = float(p2.x), float(p2.y)
                    if max(x1, x2) < x_min or max(y1, y2) < y_min:
                        continue
                    if abs(y1 - y2) < 1.5 and abs(x1 - x2) > 8:
                        horiz.append((y1 + y2) / 2)
                    elif abs(x1 - x2) < 1.5 and abs(y1 - y2) > 8:
                        vert.append((x1 + x2) / 2)
                elif op == 're' and len(item) >= 2:
                    r = item[1]
                    rx0, ry0, rx1, ry1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
                    if rx1 < x_min or ry1 < y_min:
                        continue
                    horiz.extend([ry0, ry1])
                    vert.extend([rx0, rx1])
    except Exception:
        pass
    return sorted(set(round(y, 1) for y in horiz)), sorted(set(round(x, 1) for x in vert))


def _right_column_bounds(page_w: float, page_h: float, vert_lines: list[float]) -> tuple[float, float]:
    """X bounds for the rightmost title-block column (sheet number column)."""
    br_verts = [x for x in vert_lines if x >= page_w * 0.55]
    if len(br_verts) >= 2:
        br_verts.sort()
        # Rightmost band between last two vertical frame lines
        x0 = br_verts[-2]
        x1 = br_verts[-1]
        if x1 - x0 >= page_w * 0.06:
            return x0, x1
    return page_w * 0.68, page_w * 0.995


def _cells_from_vector_grid(
    horiz_lines: list[float],
    vert_lines: list[float],
    col_x0: float,
    col_x1: float,
    page_h: float,
) -> list[GridRect]:
    """Build rectangular cells from intersecting frame lines in the right column."""
    y_lines = [y for y in horiz_lines if y >= page_h * 0.52]
    x_lines = [x for x in vert_lines if col_x0 - 5 <= x <= col_x1 + 5]
    if len(y_lines) < 2:
        return []
    y_lines = sorted(y_lines)
    rects: list[GridRect] = []
    for y0, y1 in zip(y_lines, y_lines[1:]):
        if y1 - y0 < page_h * 0.018:
            continue
        if y1 < page_h * 0.55:
            continue
        rects.append(GridRect(col_x0, y0, col_x1, y1))
    return rects


def _assign_lines_to_vector_cells(lines: list[TextLine], rects: list[GridRect]) -> list[LabeledCell]:
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: r.y0)
    grouped: dict[int, list[TextLine]] = {i: [] for i in range(len(rects))}
    for ln in lines:
        cy = ln.cy
        cx = (ln.x0 + ln.x1) / 2
        for i, rect in enumerate(rects):
            if rect.contains_point(cx, cy):
                grouped[i].append(ln)
                break
    cells: list[LabeledCell] = []
    all_lines = [ln for g in grouped.values() for ln in g]
    med_h = statistics.median([ln.height for ln in all_lines]) if all_lines else 8.0
    med_size = statistics.median([ln.font_size or ln.height for ln in all_lines]) if all_lines else med_h
    for i, rect in enumerate(rects):
        group = grouped.get(i) or []
        if not group:
            continue
        cell = _lines_to_labeled_cell(group, med_h, med_size)
        if cell:
            cell.x0, cell.y0, cell.x1, cell.y1 = rect.x0, rect.y0, rect.x1, rect.y1
            if cell.label_kind or cell.value_text:
                cells.append(cell)
    return cells


def _merge_cell_lists(primary: list[LabeledCell], secondary: list[LabeledCell]) -> list[LabeledCell]:
    """Prefer primary cells; add secondary cells that don't overlap existing ones."""
    merged = list(primary)
    for sec in secondary:
        overlap = False
        for pri in primary:
            if abs(sec.cy - pri.cy) < 8 and abs(sec.cx - pri.cx) < 20:
                if pri.label_kind and not sec.label_kind:
                    overlap = True
                    break
                if pri.value_text and sec.value_text and pri.label_kind:
                    overlap = True
                    break
        if not overlap:
            merged.append(sec)
    return merged


def _build_bottom_right_column(page) -> tuple[float, float, list[LabeledCell]]:
    """Words in the rightmost title-block column → vertically stacked labeled cells."""
    page_w, page_h = page.rect.width, page.rect.height
    words = _words_from_page(page, min_y_ratio=0.50)
    if not words:
        return page_w, page_h, []

    horiz, vert = _extract_vector_segments(page)
    col_x0, col_x1 = _right_column_bounds(page_w, page_h, vert)

    col_words = [w for w in words if w.cx >= col_x0 and w.cy >= page_h * 0.52]
    if len(col_words) < 2:
        col_words = [w for w in words if w.cx >= page_w * 0.58 and w.cy >= page_h * 0.58]
        col_x0 = page_w * 0.58

    med_h = _median_height(col_words)
    med_size = _median_font_size(col_words)
    y_tol = max(2.5, med_h * 0.42)
    cell_gap = max(6.0, med_size * 0.95, med_h * 1.15)

    lines = _cluster_words_into_lines(col_words, y_tol)

    vector_rects = _cells_from_vector_grid(horiz, vert, col_x0, col_x1, page_h)
    vector_cells = _assign_lines_to_vector_cells(lines, vector_rects) if vector_rects else []
    gap_cells = _cluster_lines_into_cells(lines, cell_gap)

    if vector_cells and len(vector_cells) >= 2:
        cells = _merge_cell_lists(vector_cells, gap_cells)
    else:
        cells = gap_cells

    return page_w, page_h, cells


def _normalize_drawing_number(raw: str) -> str | None:
    if not raw:
        return None
    compact = re.sub(r'\s+', '', raw.upper())
    m = DRAWING_NUMBER_VALUE_RE.match(compact)
    if m:
        suffix = (m.group(3) or '').upper()
        sheet = f'{m.group(1).upper()}-{m.group(2)}' + (suffix if suffix else '')
        if is_plausible_drawing_sheet(sheet) or re.match(r'^[A-Z]{1,3}-\d{1,4}[A-Z]?$', sheet):
            return sheet
    m = CSI_SHEET_IN_CELL_RE.match(compact)
    if m:
        cand = normalize_sheet_number(f'{m.group(1)}-{m.group(2)}.{m.group(3)}')
        if cand:
            return cand
    m = DRAWING_NUMBER_LOOSE_RE.search(raw)
    if m:
        suffix = (m.group(3) or '').upper()
        sheet = f'{m.group(1).upper()}-{m.group(2)}' + (suffix if suffix else '')
        if is_plausible_drawing_sheet(sheet) or re.match(r'^[A-Z]{1,3}-\d{1,4}[A-Z]?$', sheet):
            return sheet
    cand = normalize_sheet_number(compact)
    if cand and is_plausible_drawing_sheet(cand):
        return cand
    return None


def _is_plausible_drawing_title(text: str, sheet_number: str | None) -> bool:
    if not text or len(text) < 3 or len(text) > 180:
        return False
    t = text.strip()
    upper = t.upper()
    if PROJECT_TYPE_LABEL_RE.search(t):
        return False
    if _normalize_drawing_number(t):
        return False
    if sheet_number and sheet_number.upper().replace('-', '') in upper.replace('-', '').replace(' ', ''):
        return False
    if REVISION_RE.search(t) or REV_NO_RE.search(t):
        return False
    if DATE_RE.search(t) or DATE_FALLBACK_RE.fullmatch(t):
        return False
    if ARCH_SCALE_RE.search(t) or RATIO_SCALE_RE.search(t):
        return False
    if NOTE_FRAGMENT_RE.search(t) and not TITLE_HINT_RE.search(t):
        return False
    if re.match(r'^(?:NEW|RENOVATION|ADDITION|TI|BUILD[- ]?OUT|TENANT|COMMERCIAL|RESIDENTIAL)\b', upper):
        if not TITLE_HINT_RE.search(t):
            return False
    if TITLE_HINT_RE.search(t):
        return True
    if len(t) >= 6 and re.search(r'[A-Za-z]{3,}', t):
        return True
    return False


def _is_plausible_project_number(text: str) -> bool:
    if not text or len(text) < 3 or len(text) > 30:
        return False
    t = text.strip().upper()
    if _normalize_drawing_number(t):
        return False
    if PROJECT_TYPE_LABEL_RE.search(t):
        return False
    return bool(PROJECT_NUMBER_VALUE_RE.match(t.replace(' ', '')))


def _parse_revision_token(raw: str) -> str | None:
    if not raw:
        return None
    token = raw.strip().strip(':.#').upper()
    if re.fullmatch(r'\d{1,3}', token):
        return token
    if re.fullmatch(r'[A-Z]', token):
        return token
    return None


def _find_drawing_number_cell(cells: list[LabeledCell], page_w: float, page_h: float) -> LabeledCell | None:
    """Southernmost-right cell with Drawing No label or largest BR sheet value."""
    candidates: list[tuple[float, LabeledCell]] = []
    for cell in cells:
        score = (cell.cy / page_h) * 0.55 + (cell.cx / page_w) * 0.45
        if cell.label_kind == 'drawing_number':
            candidates.append((score + 2.5 + cell.value_font_size * 0.02, cell))
        elif cell.value_text and _normalize_drawing_number(cell.value_text):
            candidates.append((score + cell.value_font_size * 0.06 + 1.2, cell))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _find_drawing_name_cell(
    cells: list[LabeledCell],
    sheet_cell: LabeledCell | None,
    page_w: float,
) -> LabeledCell | None:
    """Cell directly above the sheet-number cell with Drawing Name label."""
    if not cells:
        return None

    name_cells = [c for c in cells if c.label_kind == 'drawing_name' and c.value_text]
    if sheet_cell:
        col_band = max(28.0, (sheet_cell.x1 - sheet_cell.x0) * 0.55, page_w * 0.08)
        above_labeled = [
            c for c in name_cells
            if c.cy < sheet_cell.cy
            and abs(c.cx - sheet_cell.cx) <= col_band
        ]
        if above_labeled:
            above_labeled.sort(key=lambda c: sheet_cell.cy - c.cy)
            return above_labeled[0]

    if sheet_cell:
        col_band = max(28.0, (sheet_cell.x1 - sheet_cell.x0) * 0.55, page_w * 0.08)
        stacked = [
            c for c in cells
            if c.cy < sheet_cell.cy
            and abs(c.cx - sheet_cell.cx) <= col_band
            and c.value_text
            and c.label_kind not in ('project_type', 'project_number', 'drawing_number', 'revision')
        ]
        if stacked:
            stacked.sort(key=lambda c: (sheet_cell.cy - c.cy, -(c.value_font_size or c.value_height)))
            for c in stacked:
                if _is_plausible_drawing_title(c.value_text, None):
                    return c

    if name_cells:
        name_cells.sort(key=lambda c: c.cy, reverse=True)
        return name_cells[0]
    return None


def _ocr_bottom_right_column(pdf_path: str, page_index: int) -> list[LabeledCell]:
    """High-DPI OCR fallback on the bottom-right column with word bounding boxes."""
    cells: list[LabeledCell] = []
    try:
        import fitz
        import io
        from PIL import Image
        import pytesseract
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            doc.close()
            return cells
        page = doc[page_index]
        rect = page.rect
        clip = fitz.Rect(rect.width * 0.62, rect.height * 0.52, rect.width * 0.995, rect.height * 0.995)
        matrix = fitz.Matrix(5.0, 5.0)
        pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes('png')))
        scale_x = clip.width / img.width
        scale_y = clip.height / img.height
        for psm in ('--psm 6', '--psm 4', '--psm 11'):
            try:
                data = pytesseract.image_to_data(img, config=psm, output_type=pytesseract.Output.DICT)
            except Exception:
                continue
            pseudo_words: list[WordSpan] = []
            n = len(data.get('text') or [])
            for i in range(n):
                text = str(data['text'][i] or '').strip()
                if not text or int(data.get('conf', [0])[i] or 0) < 35:
                    continue
                x = float(data['left'][i])
                y = float(data['top'][i])
                w = float(data['width'][i])
                h = float(data['height'][i])
                x0 = clip.x0 + x * scale_x
                y0 = clip.y0 + y * scale_y
                x1 = x0 + w * scale_x
                y1 = y0 + h * scale_y
                fs = h * scale_y
                pseudo_words.append(WordSpan(x0, y0, x1, y1, text, font_size=fs))
            if pseudo_words:
                med_h = _median_height(pseudo_words)
                med_size = _median_font_size(pseudo_words)
                lines = _cluster_words_into_lines(pseudo_words, max(3.0, med_h * 0.5))
                for group in _cluster_lines_into_cells(lines, max(8.0, med_size * 1.1)):
                    cells.append(group)
        doc.close()
    except Exception:
        pass
    return cells


def analyze_title_block_grid(pdf_path: str, page_index: int = 0) -> dict[str, Any]:
    """Bluebeam-style bottom-right labeled cell extraction."""
    result: dict[str, Any] = {
        'sheet_number': None,
        'drawing_name': '',
        'title': '',
        'project_number': None,
        'revision': None,
        'drawing_date': None,
        'scale': None,
        'method': 'grid',
        'text_preview': '',
        'confidence': {},
        'grid_cells': 0,
    }
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            doc.close()
            return result
        page = doc[page_index]
        embedded = page.get_text('text') or ''
        page_w, page_h, cells = _build_bottom_right_column(page)
        doc.close()
    except Exception:
        return result

    if len(cells) < 2:
        ocr_cells = _ocr_bottom_right_column(pdf_path, page_index)
        seen = {(round(c.y0, 1), c.label_kind, c.value_text) for c in cells}
        for c in ocr_cells:
            key = (round(c.y0, 1), c.label_kind, c.value_text)
            if key not in seen:
                cells.append(c)
                seen.add(key)

    result['grid_cells'] = len(cells)

    sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
    final_sheet = None
    sheet_conf = 0.0
    if sheet_cell:
        final_sheet = _normalize_drawing_number(sheet_cell.value_text)
        if final_sheet:
            sheet_conf = 2.2 + sheet_cell.value_font_size * 0.04
            if sheet_cell.label_kind == 'drawing_number':
                sheet_conf += 0.8

    name_cell = _find_drawing_name_cell(cells, sheet_cell, page_w)
    drawing_name = ''
    name_conf = 0.0
    if name_cell and name_cell.value_text:
        candidate = name_cell.value_text.strip()
        if _is_plausible_drawing_title(candidate, final_sheet):
            drawing_name = candidate[:200]
            name_conf = 2.0 + name_cell.value_font_size * 0.03
            if name_cell.label_kind == 'drawing_name':
                name_conf += 0.8

    project_number = None
    for cell in cells:
        if cell.label_kind == 'project_number' and cell.value_text:
            if _is_plausible_project_number(cell.value_text):
                project_number = cell.value_text.strip().upper()
                break

    revision = None
    for cell in cells:
        if cell.label_kind == 'revision' and cell.value_text:
            revision = _parse_revision_token(cell.value_text)
            if revision:
                break
        for pat in (REV_NO_RE, REVISION_RE, REVISION_LOOSE_RE):
            m = pat.search(cell.value_text or '')
            if m:
                revision = _parse_revision_token(str(m.group(1)))
                if revision:
                    break

    merged_text = embedded + '\n' + '\n'.join(
        f'{c.value_text} / {c.label_text}' for c in cells if c.value_text or c.label_text
    )
    if not revision:
        revision = extract_revision_from_text(merged_text)

    result['sheet_number'] = final_sheet
    result['drawing_name'] = drawing_name
    result['title'] = drawing_name
    result['project_number'] = project_number
    result['revision'] = revision
    result['drawing_date'] = extract_drawing_date_from_text(merged_text)
    result['scale'] = extract_scale_from_text(merged_text)
    result['text_preview'] = merged_text[:400]
    result['confidence'] = {
        'sheet': round(sheet_conf, 2),
        'name': round(name_conf, 2),
        'project': 1.4 if project_number else 0,
        'revision': 1.1 if revision else 0,
    }
    return result


# Backward-compatible exports used by older imports
build_title_block_grid = _build_bottom_right_column
