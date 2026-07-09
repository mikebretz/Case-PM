"""Grid/cell-based title block parser for construction drawing PDFs.

Clusters positioned words into title-block rows and cells, then extracts:
- Sheet / drawing number (largest text, bottom-right, letter-dash-3-digits)
- Drawing name (same cell as DRAWING NAME label)
- Project number (same cell as PROJECT / JOB NO label)
- Revision, scale, date from labeled cells
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
    DRAWING_NAME_LABEL_RE,
    PROJECT_LABEL_RE,
    RATIO_SCALE_RE,
    REV_ISSUE_RE,
    REV_NO_RE,
    REVISION_LOOSE_RE,
    REVISION_RE,
    SHEET_NO_LABEL_RE,
    TITLE_HINT_RE,
    extract_drawing_date_from_text,
    extract_revision_from_text,
    extract_scale_from_text,
    is_plausible_drawing_sheet,
    normalize_sheet_number,
)

# Architectural sheet index: A-101, S-201 (letter + dash + 3 digits)
STANDARD_SHEET_RE = re.compile(r'^([A-Z]{1,3})-(\d{3})$', re.I)
STANDARD_SHEET_LOOSE_RE = re.compile(r'\b([A-Z]{1,3})\s*[-_.]\s*(\d{3})\b', re.I)
CSI_SHEET_IN_CELL_RE = re.compile(r'^([A-Z]{1,3})-(\d{1,2})\.(\d{2})$', re.I)

PROJECT_NO_LABEL_RE = re.compile(
    r'^(?:PROJECT|JOB)\s*(?:NO\.?|NUM(?:BER)?|#)\s*[:#.]?\s*(.*)$',
    re.I,
)
DRAWING_NAME_CELL_LABEL_RE = re.compile(
    r'^(?:DRAWING\s*NAME|DRAWING\s*TITLE|SHEET\s*NAME|SHEET\s*TITLE|TITLE\s*OF\s*DRAWING)\s*[:#.]?\s*(.*)$',
    re.I,
)
SHEET_NO_CELL_LABEL_RE = re.compile(
    r'^(?:SHEET|SHT|SH\.?|DWG\.?|DRAWING)\s*(?:NO\.?|NUM(?:BER)?|#)\s*[:#.]?\s*(.*)$',
    re.I,
)
REV_CELL_LABEL_RE = re.compile(
    r'^(?:REV(?:ISION)?\.?|CURRENT\s*REV)\s*(?:NO\.?|NUM(?:BER)?|#)?\s*[:#.]?\s*(.*)$',
    re.I,
)
LABEL_ONLY_CELL_RE = re.compile(
    r'^(?:DRAWING\s*NAME|DRAWING\s*TITLE|SHEET\s*NAME|PROJECT|JOB|DATE|SCALE|REV(?:ISION)?|'
    r'SHEET|DWG|DRAWING|CHECKED|DRAWN|DESIGNED|APPROVED)\s*(?:NO\.?|NUM(?:BER)?|#|NAME)?\s*[:#.]?\s*$',
    re.I,
)
NOTE_FRAGMENT_RE = re.compile(
    r'\b(DEMO(?:\'?D)?|REINFORCING|CONTRACTOR|INSTALL|VERIFY|REFER|SEE\s+STRUCTURAL|TO\s+BE|EXISTING)\b',
    re.I,
)
PROJECT_NUMBER_VALUE_RE = re.compile(
    r'^([A-Z0-9][A-Z0-9\-./]{2,24})$',
    re.I,
)


@dataclass
class WordSpan:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int = 0
    line: int = 0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return max(1.0, self.y1 - self.y0)

    @property
    def width(self) -> float:
        return max(1.0, self.x1 - self.x0)


@dataclass
class GridCell:
    row: int
    col: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    words: list[WordSpan] = field(default_factory=list)
    font_height: float = 0.0
    label_kind: str | None = None

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class TitleBlockGrid:
    page_w: float
    page_h: float
    cells: list[GridCell]
    words: list[WordSpan]
    rows: list[list[GridCell]]


def _words_from_page(page, min_y_ratio: float = 0.50) -> list[WordSpan]:
    page_h = page.rect.height
    words: list[WordSpan] = []
    for item in page.get_text('words') or []:
        if len(item) < 5:
            continue
        x0, y0, x1, y1, text = float(item[0]), float(item[1]), float(item[2]), float(item[3]), str(item[4]).strip()
        if not text or y0 < page_h * min_y_ratio:
            continue
        blk = int(item[5]) if len(item) > 5 else 0
        ln = int(item[6]) if len(item) > 6 else 0
        words.append(WordSpan(x0, y0, x1, y1, text, blk, ln))
    return words


def _median_word_height(words: list[WordSpan]) -> float:
    if not words:
        return 8.0
    return statistics.median(w.height for w in words)


def _cluster_rows(words: list[WordSpan], y_tol: float) -> list[list[WordSpan]]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w.cy, w.x0))
    rows: list[list[WordSpan]] = []
    current: list[WordSpan] = []
    row_y = None
    for w in sorted_words:
        if row_y is None or abs(w.cy - row_y) <= y_tol:
            current.append(w)
            row_y = w.cy if row_y is None else (row_y + w.cy) / 2
        else:
            rows.append(sorted(current, key=lambda x: x.x0))
            current = [w]
            row_y = w.cy
    if current:
        rows.append(sorted(current, key=lambda x: x.x0))
    return rows


def _split_row_into_cells(row_words: list[WordSpan], gap_threshold: float) -> list[list[WordSpan]]:
    if not row_words:
        return []
    cells: list[list[WordSpan]] = []
    current: list[WordSpan] = [row_words[0]]
    for prev, w in zip(row_words, row_words[1:]):
        gap = w.x0 - prev.x1
        if gap > gap_threshold:
            cells.append(current)
            current = [w]
        else:
            current.append(w)
    cells.append(current)
    return cells


def build_title_block_grid(page, min_y_ratio: float = 0.50) -> TitleBlockGrid:
    """Cluster title-block words into a row/column cell grid."""
    rect = page.rect
    page_w, page_h = rect.width, rect.height
    words = _words_from_page(page, min_y_ratio=min_y_ratio)
    med_h = _median_word_height(words)
    y_tol = max(3.0, med_h * 0.55)
    gap_threshold = max(8.0, med_h * 1.8)

    rows_raw = _cluster_rows(words, y_tol)
    cells: list[GridCell] = []
    grid_rows: list[list[GridCell]] = []

    for ri, row_words in enumerate(rows_raw):
        row_cells: list[GridCell] = []
        for ci, cell_words in enumerate(_split_row_into_cells(row_words, gap_threshold)):
            x0 = min(w.x0 for w in cell_words)
            y0 = min(w.y0 for w in cell_words)
            x1 = max(w.x1 for w in cell_words)
            y1 = max(w.y1 for w in cell_words)
            text = ' '.join(w.text for w in cell_words).strip()
            font_h = max(w.height for w in cell_words)
            cell = GridCell(ri, ci, x0, y0, x1, y1, text, cell_words, font_h)
            row_cells.append(cell)
            cells.append(cell)
        if row_cells:
            grid_rows.append(row_cells)
    return TitleBlockGrid(page_w, page_h, cells, words, grid_rows)


def _classify_cell_labels(grid: TitleBlockGrid) -> None:
    for cell in grid.cells:
        t = cell.text.strip()
        upper = t.upper()
        if DRAWING_NAME_CELL_LABEL_RE.match(t) or DRAWING_NAME_LABEL_RE.search(upper):
            cell.label_kind = 'drawing_name'
        elif SHEET_NO_CELL_LABEL_RE.match(t) or SHEET_NO_LABEL_RE.search(upper):
            cell.label_kind = 'sheet_number'
        elif PROJECT_NO_LABEL_RE.match(t) or PROJECT_LABEL_RE.search(upper):
            cell.label_kind = 'project_number'
        elif REV_CELL_LABEL_RE.match(t) or REVISION_RE.search(upper):
            cell.label_kind = 'revision'
        elif re.search(r'\bSCALE\b', upper):
            cell.label_kind = 'scale'
        elif DATE_RE.search(t):
            cell.label_kind = 'date'


def _normalize_standard_sheet(prefix: str, digits: str) -> str | None:
    sheet = f'{prefix.upper()}-{digits}'
    if is_plausible_drawing_sheet(sheet):
        return sheet
    return None


def _sheet_from_text(text: str) -> str | None:
    if not text:
        return None
    compact = re.sub(r'\s+', '', text.upper())
    m = STANDARD_SHEET_RE.match(compact)
    if m:
        return _normalize_standard_sheet(m.group(1), m.group(2))
    m = CSI_SHEET_IN_CELL_RE.match(compact)
    if m:
        cand = normalize_sheet_number(f'{m.group(1)}-{m.group(2)}.{m.group(3)}')
        if cand and is_plausible_drawing_sheet(cand):
            return cand
    m = STANDARD_SHEET_LOOSE_RE.search(text)
    if m:
        return _normalize_standard_sheet(m.group(1), m.group(2))
    cand = normalize_sheet_number(compact)
    if cand and is_plausible_drawing_sheet(cand):
        return cand
    return None


def _bottom_right_score(cell: GridCell, page_w: float, page_h: float) -> float:
    if page_w <= 0 or page_h <= 0:
        return 0.0
    x_score = cell.cx / page_w
    y_score = cell.cy / page_h
    return x_score * 0.55 + y_score * 0.45


def _find_largest_bottom_right_sheet(grid: TitleBlockGrid) -> tuple[str | None, float]:
    """Sheet number = largest-font plausible sheet text in bottom-right title block."""
    page_w, page_h = grid.page_w, grid.page_h
    candidates: list[tuple[float, str]] = []

    br_words = [
        w for w in grid.words
        if w.cx >= page_w * 0.58 and w.cy >= page_h * 0.68
    ]
    br_rows = _cluster_rows(br_words, max(3.0, _median_word_height(br_words) * 0.55))
    for row in br_rows:
        line_text = ' '.join(w.text for w in row)
        sheet = _sheet_from_text(line_text)
        if sheet:
            font_h = max(w.height for w in row)
            pos = _bottom_right_score(
                GridCell(0, 0, row[0].x0, row[0].y0, row[-1].x1, row[-1].y1, line_text, row, font_h),
                page_w, page_h,
            )
            candidates.append((font_h * 2.2 + pos * 120, sheet))

    for cell in grid.cells:
        if cell.cx < page_w * 0.52 or cell.cy < page_h * 0.62:
            continue
        sheet = _sheet_from_text(cell.text)
        if sheet:
            pos = _bottom_right_score(cell, page_w, page_h)
            candidates.append((cell.font_height * 2.0 + pos * 100, sheet))
        for w in cell.words:
            sheet = _sheet_from_text(w.text)
            if sheet:
                pos = _bottom_right_score(cell, page_w, page_h)
                candidates.append((w.height * 2.5 + pos * 110, sheet))

    if not candidates:
        return None, 0.0
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1], candidates[0][0]


def _strip_label_from_cell(text: str, label_re: re.Pattern) -> str:
    m = label_re.match(text.strip())
    if m:
        return (m.group(1) or '').strip()
    parts = label_re.split(text.strip(), maxsplit=1)
    if len(parts) > 1:
        return parts[-1].strip(' :.#')
    return ''


def _same_cell_value(cell: GridCell, label_re: re.Pattern, validator=None) -> str | None:
    """Value co-located with a label in one title-block cell."""
    text = cell.text.strip()
    if not text:
        return None
    inline = _strip_label_from_cell(text, label_re)
    if inline and (validator is None or validator(inline)):
        return inline
    if LABEL_ONLY_CELL_RE.match(text):
        return None
    upper = text.upper()
    if label_re.match(text):
        return None
    if validator is None or validator(text):
        return text
    return None


def _adjacent_cell_value(grid: TitleBlockGrid, cell: GridCell, validator=None) -> str | None:
    """Value in cell immediately to the right, or below in same column band."""
    page_w = grid.page_w
    col_band = max(20.0, (cell.x1 - cell.x0) * 0.35)
    best = None
    best_dist = 1e9
    for other in grid.cells:
        if other is cell:
            continue
        same_row = abs(other.cy - cell.cy) <= max(4.0, cell.font_height * 0.65)
        right_neighbor = same_row and other.x0 >= cell.x1 - 2 and other.x0 - cell.x1 < page_w * 0.15
        below_neighbor = other.y0 >= cell.y1 - 2 and abs(other.cx - cell.cx) <= col_band
        if not (right_neighbor or below_neighbor):
            continue
        val = other.text.strip()
        if not val or LABEL_ONLY_CELL_RE.match(val):
            continue
        if validator and not validator(val):
            continue
        dist = abs(other.x0 - cell.x1) + abs(other.y0 - cell.y1)
        if dist < best_dist:
            best_dist = dist
            best = val
    return best


def _extract_labeled_field(
    grid: TitleBlockGrid,
    label_re: re.Pattern,
    label_kind: str,
    validator=None,
) -> str | None:
    for cell in grid.cells:
        if cell.label_kind != label_kind and not label_re.match(cell.text.strip()):
            continue
        val = _same_cell_value(cell, label_re, validator=validator)
        if val:
            return val
        val = _adjacent_cell_value(grid, cell, validator=validator)
        if val:
            return val
    return None


def _is_plausible_drawing_title(text: str, sheet_number: str | None) -> bool:
    if not text or len(text) < 3 or len(text) > 180:
        return False
    t = text.strip()
    if LABEL_ONLY_CELL_RE.match(t):
        return False
    upper = t.upper()
    if sheet_number and sheet_number.upper().replace('-', '') in upper.replace('-', '').replace(' ', ''):
        return False
    if _sheet_from_text(t):
        return False
    if REVISION_RE.search(t) or REV_NO_RE.search(t):
        return False
    if DATE_RE.search(t) or DATE_FALLBACK_RE.fullmatch(t):
        return False
    if ARCH_SCALE_RE.search(t) or RATIO_SCALE_RE.search(t):
        return False
    if NOTE_FRAGMENT_RE.search(t) and not TITLE_HINT_RE.search(t):
        return False
    if t.upper().startswith('FROM ') and not TITLE_HINT_RE.search(t):
        return False
    if TITLE_HINT_RE.search(t):
        return True
    if t.isupper() and len(t) >= 5:
        return True
    if len(t) >= 8 and re.search(r'[A-Za-z]{4,}', t):
        return True
    return False


def _is_plausible_project_number(text: str) -> bool:
    if not text or len(text) < 3 or len(text) > 30:
        return False
    t = text.strip().upper()
    if LABEL_ONLY_CELL_RE.match(t):
        return False
    if _sheet_from_text(t):
        return False
    if DATE_FALLBACK_RE.fullmatch(t):
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


def analyze_title_block_grid(pdf_path: str, page_index: int = 0) -> dict[str, Any]:
    """Primary grid-based title block analysis."""
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
        grid = build_title_block_grid(page, min_y_ratio=0.48)
        _classify_cell_labels(grid)
        doc.close()
    except Exception:
        return result

    result['grid_cells'] = len(grid.cells)
    merged_parts = [embedded] + [c.text for c in grid.cells if c.text]

    sheet, sheet_score = _find_largest_bottom_right_sheet(grid)
    labeled_sheet = _extract_labeled_field(
        grid, SHEET_NO_CELL_LABEL_RE, 'sheet_number',
        validator=lambda t: _sheet_from_text(t) is not None,
    )
    if labeled_sheet:
        labeled_sheet = _sheet_from_text(labeled_sheet) or labeled_sheet

    sheet_sources: list[tuple[float, str | None]] = []
    if sheet:
        sheet_sources.append((sheet_score / 100 + 1.3, sheet))
    if labeled_sheet:
        sheet_sources.append((1.45, labeled_sheet))

    final_sheet = None
    if sheet_sources:
        sheet_sources.sort(key=lambda t: t[0], reverse=True)
        final_sheet = sheet_sources[0][1]

    drawing_name = _extract_labeled_field(
        grid, DRAWING_NAME_CELL_LABEL_RE, 'drawing_name',
        validator=lambda t: _is_plausible_drawing_title(t, final_sheet),
    )
    if not drawing_name:
        for cell in grid.cells:
            if cell.label_kind != 'drawing_name':
                continue
            val = _same_cell_value(cell, DRAWING_NAME_CELL_LABEL_RE)
            if val and _is_plausible_drawing_title(val, final_sheet):
                drawing_name = val
                break
            chunk = ' '.join(
                x.text for x in cell.words
                if not DRAWING_NAME_LABEL_RE.search(x.text) and not LABEL_ONLY_CELL_RE.match(x.text)
            ).strip()
            if chunk and _is_plausible_drawing_title(chunk, final_sheet):
                drawing_name = chunk
                break

    if not drawing_name and final_sheet:
        sheet_cells = [c for c in grid.cells if _sheet_from_text(c.text) == final_sheet]
        for sc in sheet_cells:
            for cell in grid.cells:
                if cell.cy >= sc.cy:
                    continue
                if abs(cell.cx - sc.cx) <= grid.page_w * 0.2 and cell.cy < sc.cy:
                    if _is_plausible_drawing_title(cell.text, final_sheet):
                        drawing_name = cell.text.strip()
                        break
            if drawing_name:
                break

    project_number = _extract_labeled_field(
        grid, PROJECT_NO_LABEL_RE, 'project_number',
        validator=_is_plausible_project_number,
    )

    revision_raw = _extract_labeled_field(
        grid, REV_CELL_LABEL_RE, 'revision',
        validator=lambda t: _parse_revision_token(t) is not None,
    )
    revision = _parse_revision_token(revision_raw) if revision_raw else None
    if not revision:
        for cell in grid.cells:
            for pat in (REV_NO_RE, REVISION_RE, REVISION_LOOSE_RE, REV_ISSUE_RE):
                m = pat.search(cell.text)
                if m:
                    revision = _parse_revision_token(str(m.group(1)))
                    if revision:
                        break
            if revision:
                break
    if not revision:
        revision = extract_revision_from_text('\n'.join(merged_parts))

    merged_text = '\n'.join(merged_parts)
    result['sheet_number'] = final_sheet
    result['drawing_name'] = (drawing_name or '')[:200]
    result['title'] = result['drawing_name']
    result['project_number'] = project_number
    result['revision'] = revision
    result['drawing_date'] = extract_drawing_date_from_text(merged_text)
    result['scale'] = extract_scale_from_text(merged_text)
    result['text_preview'] = merged_text[:400]
    result['confidence'] = {
        'sheet': round(sheet_sources[0][0], 2) if sheet_sources else 0,
        'name': 1.35 if drawing_name else 0,
        'project': 1.3 if project_number else 0,
        'revision': 1.1 if revision else 0,
    }
    return result
