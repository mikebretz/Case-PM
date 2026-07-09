"""Grid/cell-based title block parser for construction drawing PDFs.

Typical architectural title block (bottom-right inside frame):

  ┌──────────────────────────────────────────┐
  │         Exterior Elevations               │  value above label
  │         Drawing Name:                     │
  ├──────────────┬───────────────────────────┤
  │ Date: 05/23/25│ Project No.                │  project: label above value
  │ Type: RETROFIT│ 2024.0565                  │
  │ Drawn By: AM  ├───────────────────────────┤
  │ Checked By: LS│         A-201              │  sheet: value above label
  │               │         Drawing No.        │
  └──────────────┴───────────────────────────┘

Detection strategy (Bluebeam region + spatial index):
1. Parse the full bottom-right title block (not just the narrow sheet column)
2. Split metadata left column vs identifier right column
3. Drawing name from full-width top band with "Drawing Name:" label at bottom
4. Sheet number from bottom-right cell with "Drawing No." label at bottom
5. Project number from right column cell with "Project No." label at top
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
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

# Aldi / typical arch title block sits in the bottom-right corner inside the frame.
CORNER_X0_RATIO = 0.86
CORNER_Y0_RATIO = 0.62
CORNER_X1_RATIO = 0.985
# Wider fallback when corner has almost no text (non-standard layouts).
TITLE_BLOCK_X0_RATIO = CORNER_X0_RATIO
TITLE_BLOCK_Y0_RATIO = CORNER_Y0_RATIO

LOCAL_TITLE_HINT_RE = re.compile(
    r'\b(PLAN|PLANS|ELEVATION|ELEVATIONS|SECTION|SECTIONS|DETAIL|DETAILS|SCHEDULE|SCHEDULES|'
    r'FLOOR|ROOF|SITE|CEILING|FOUNDATION|FRAMING|RCP|REFLECTED|WINDOW|LIGHTING|DIAGRAM|DIAGRAMS|'
    r'ALARM|CONDUIT|POWER|PANEL|MECHANICAL|ELECTRICAL|STRUCTURAL|INTERIOR|EXTERIOR|'
    r'SEQUENCE|OPERATIONS|OPERATION|SCHEMATIC|LAYOUT|GENERAL|NOTES|LEGEND|INDEX|COVER|'
    r'PLUMBING|HVAC|VENT|ROOF|PIPING|SANITARY|DOMESTIC|FIRE|SPRINKLER)\b',
    re.I,
)
NOTE_SPEC_TITLE_RE = re.compile(
    r'\b(ASME|ASTM|ANSI|NOMINAL|POUNDS?|SPECIFICATION|HOSE|LOW\s*CAL|DUTY|CAPACITY|'
    r'RATED|GALLONS?|PSI|KPA|TORQUE|LOAD|CALIBER|CALIBRATION|CONTRACTOR\s*SHALL)\b',
    re.I,
)
STRIP_X0_RATIO = 0.62
STRIP_Y0_RATIO = 0.52
NAME_STACK_CONNECTORS = frozenset({'OF', 'AND', 'OR', '&', 'THE', 'FOR', 'TO', 'AT', 'ON', 'A', 'AN'})
GLUED_SHEET_CODE_RE = re.compile(r'^[A-Z]{3,10}\d{1,4}$', re.I)
OPAQUE_SHEET_CODE_RE = re.compile(r'^(?=.*\d)[A-Z0-9]{3,14}$', re.I)
WIDE_CORNER_X0_RATIO = 0.72
STAMP_FOOTER_RE = re.compile(
    r'^[A-Z]{2,14}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}|'
    r'\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?',
    re.I,
)
CONTINUATION_LINE_RE = re.compile(r'^(?:and|or|&|\+|/|-)\b', re.I)

DRAWING_NUMBER_VALUE_RE = re.compile(
    r'^([A-Z]{1,4})-(\d{1,4})([A-Za-z])?$',
    re.I,
)
DRAWING_NUMBER_LOOSE_RE = re.compile(
    r'\b([A-Z]{1,4})\s*-\s*(\d{1,4})([A-Za-z])?\b',
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
SHEET_ONLY_LABEL_RE = re.compile(
    r'^sheet\s*:?\s*$',
    re.I,
)
CUSTOM_SHEET_VALUE_RE = re.compile(
    r'^([A-Z]{2,8})-?(\d{1,4})$',
    re.I,
)
DRAWING_NAME_LABEL_RE = re.compile(
    r'^drawing\s*name\s*:?\s*$',
    re.I,
)
PAGE_NAME_LABEL_RE = re.compile(
    r'^(?:page|sheet)\s*name\s*:?\s*$',
    re.I,
)
PAGE_NO_LABEL_RE = re.compile(
    r'^(?:page|sheet)\s*(?:no\.?|num(?:ber)?)\s*:?\s*$',
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
TYPE_INLINE_RE = re.compile(
    r'^type\s*:?\s*(.+)$',
    re.I,
)
METADATA_INLINE_RE = re.compile(
    r'^(?:date|drawn\s*by|checked\s*by|designed\s*by|approved\s*by|scale|rev(?:ision)?)\s*:',
    re.I,
)
SKIP_UPWARD_RE = re.compile(
    r'^(?:date|drawn\s*by|checked\s*by|designed\s*by|approved\s*by|type)\s*:?',
    re.I,
)
BREAK_UPWARD_RE = re.compile(
    r'(?:project\s*name\s*&\s*location|drawing\s*no|drawing\s*name|project\s*no|page\s*no|page\s*name|sheet\s*no|sheet\s*name)\b',
    re.I,
)
DATE_INLINE_RE = re.compile(
    r'\bdate\s*:\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b',
    re.I,
)
PROJECT_NAME_LOCATION_RE = re.compile(r'project\s*name\s*&\s*location', re.I)
REV_LABEL_BOTTOM_RE = re.compile(
    r'^rev(?:ision)?\s*(?:no\.?|num(?:ber)?)?\s*:?\s*$',
    re.I,
)
NOTE_FRAGMENT_RE = re.compile(
    r'\b(DEMO(?:\'?D)?|REINFORCING|CONTRACTOR|INSTALL|VERIFY|REFER|SEE\s+STRUCTURAL|TO\s+BE)\b',
    re.I,
)
PROJECT_NUMBER_VALUE_RE = re.compile(r'^[A-Z0-9][A-Z0-9\-./]{2,24}$', re.I)
DOTTED_PROJECT_NO_RE = re.compile(r'^\d{4}\.\d{3,5}$')
WORK_TYPE_VALUE_RE = re.compile(
    r'^(?:RETROFIT|NEW(?:\s+CONSTRUCTION)?|RENOVATION|ADDITION|TI|BUILD[- ]?OUT|TENANT(?:\s+IMPROVEMENT)?|'
    r'COMMERCIAL|RESIDENTIAL|ALTERATION|DEMOLITION|REPAIR)$',
    re.I,
)
INITIALS_RE = re.compile(r'^[A-Z]{1,3}$')


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
class LabelAnchor:
    kind: str
    line_idx: int
    line: 'TextLine'
    value_direction: str  # 'above' or 'below'


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
    column: str = 'full'

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def width(self) -> float:
        return max(1.0, self.x1 - self.x0)


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

    def contains_point(self, x: float, y: float, pad: float = 2.0) -> bool:
        return (self.x0 - pad) <= x <= (self.x1 + pad) and (self.y0 - pad) <= y <= (self.y1 + pad)


@dataclass
class LabeledCell:
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
    column: str = 'full'

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def width(self) -> float:
        return max(1.0, self.x1 - self.x0)


def _in_corner_box(cx: float, cy: float, page_w: float, page_h: float) -> bool:
    return (
        page_w * CORNER_X0_RATIO <= cx <= page_w * CORNER_X1_RATIO
        and page_h * CORNER_Y0_RATIO <= cy <= page_h * 0.995
    )


def _corner_spans(spans: list[WordSpan], page_w: float, page_h: float) -> list[WordSpan]:
    return [s for s in spans if _in_corner_box(s.cx, s.cy, page_w, page_h)]


def _title_block_spans(spans: list[WordSpan], page_w: float, page_h: float) -> list[WordSpan]:
    """Prefer bottom-right corner; widen when SHEET: label sits in a vertical strip."""
    corner = _corner_spans(spans, page_w, page_h)
    wide = [
        s for s in spans
        if page_w * WIDE_CORNER_X0_RATIO <= s.cx <= page_w * CORNER_X1_RATIO
        and s.cy >= page_h * 0.60
    ]
    has_sheet_label = any(SHEET_ONLY_LABEL_RE.match(s.text.strip()) for s in wide)
    if has_sheet_label and len(wide) >= 3:
        return wide
    if len(corner) >= 6:
        return corner
    return [
        s for s in spans
        if s.cx >= page_w * 0.40
        and s.cy >= page_h * 0.45
        and s.cx <= page_w * CORNER_X1_RATIO
    ]


def _is_stamp_or_footer(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if STAMP_FOOTER_RE.search(t):
        return True
    if re.search(r'\b\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)\b', t, re.I):
        return True
    return False


def _is_drawing_name_label_text(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if re.search(r'project\s*name', t, re.I):
        return False
    if DRAWING_NAME_LABEL_RE.match(t) or PAGE_NAME_LABEL_RE.match(t):
        return True
    return bool(re.search(r'(?:drawing|sheet|page)\s*name\s*:?\s*$', t, re.I))


def _is_drawing_number_label_text(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if SHEET_ONLY_LABEL_RE.match(t):
        return True
    if DRAWING_NO_LABEL_RE.match(t) or SHEET_NO_LABEL_RE.match(t) or PAGE_NO_LABEL_RE.match(t):
        return True
    return bool(re.search(r'(?:drawing|sheet|page|dwg|sht)\s*(?:no|num|number)\.?\s*:?\s*$', t, re.I))


def _sheet_label_value_direction(text: str) -> str:
    """Most layouts put the sheet number above the label; plain SHEET: puts it below."""
    t = text.strip()
    if SHEET_ONLY_LABEL_RE.match(t):
        return 'below'
    return 'above'


def _is_name_continuation_line(text: str) -> bool:
    t = text.strip()
    return bool(CONTINUATION_LINE_RE.match(t) or t.startswith('&'))


def _strip_spans_for_sheet_label(page, page_w: float, page_h: float) -> list[WordSpan]:
    """Bottom-right vertical strip where SHEET: / stacked sheet names often live."""
    spans = _spans_from_dict(page, min_y_ratio=STRIP_Y0_RATIO)
    if not spans:
        spans = _words_from_page(page, min_y_ratio=STRIP_Y0_RATIO)
    return [
        s for s in spans
        if page_w * STRIP_X0_RATIO <= s.cx <= page_w * CORNER_X1_RATIO
        and s.cy >= page_h * STRIP_Y0_RATIO
        and not _is_stamp_or_footer(s.text)
    ]


def _lines_from_spans(spans: list[WordSpan]) -> list[TextLine]:
    if not spans:
        return []
    med_h = _median_height(spans)
    med_size = _median_font_size(spans)
    y_tol = max(2.5, med_h * 0.42)
    return _cluster_words_into_lines(spans, y_tol)


def _has_sheet_only_label(lines: list[TextLine]) -> bool:
    return any(SHEET_ONLY_LABEL_RE.match(ln.text.strip()) for ln in lines)


def _dict_lines_from_page(page) -> tuple[list[TextLine], float, float, float]:
    """Build text lines from PDF dict block/line indices (most reliable for title blocks)."""
    page_w, page_h = page.rect.width, page.rect.height

    strip_spans = _strip_spans_for_sheet_label(page, page_w, page_h)
    if strip_spans:
        strip_lines = _lines_from_spans(strip_spans)
        if _has_sheet_only_label(strip_lines):
            strip_med = _median_font_size(strip_spans)
            return strip_lines, page_w, page_h, strip_med

    spans = _spans_from_dict(page, min_y_ratio=CORNER_Y0_RATIO)
    tb_spans = _title_block_spans(spans, page_w, page_h)
    tb_spans = [s for s in tb_spans if not _is_stamp_or_footer(s.text)]
    if not tb_spans:
        return [], page_w, page_h, 8.0

    groups: dict[tuple[int, int], list[WordSpan]] = {}
    for s in tb_spans:
        groups.setdefault((s.block, s.line), []).append(s)

    lines: list[TextLine] = []
    for parts in groups.values():
        parts.sort(key=lambda p: p.x0)
        text = ' '.join(p.text for p in parts).strip()
        if not text or _is_stamp_or_footer(text):
            continue
        sizes = [p.font_size for p in parts if p.font_size > 0]
        lines.append(TextLine(
            min(p.y0 for p in parts), max(p.y1 for p in parts),
            min(p.x0 for p in parts), max(p.x1 for p in parts),
            text, parts,
            max(p.height for p in parts),
            max(sizes) if sizes else max(p.height for p in parts),
            'full',
        ))
    lines.sort(key=lambda ln: ln.y0)
    med_size = _median_font_size(tb_spans)
    return lines, page_w, page_h, med_size


def _spans_from_dict(page, min_y_ratio: float = TITLE_BLOCK_Y0_RATIO) -> list[WordSpan]:
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


def _words_from_page(page, min_y_ratio: float = TITLE_BLOCK_Y0_RATIO) -> list[WordSpan]:
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


def _cluster_words_into_lines(words: list[WordSpan], y_tol: float, column: str = 'full') -> list[TextLine]:
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
                column,
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
            column,
        ))
    return lines


def _classify_bottom_label(text: str) -> str | None:
    t = text.strip()
    if not t:
        return None
    if SHEET_ONLY_LABEL_RE.match(t) or DRAWING_NO_LABEL_RE.match(t) or SHEET_NO_LABEL_RE.match(t) or PAGE_NO_LABEL_RE.match(t):
        return 'drawing_number'
    if DRAWING_NAME_LABEL_RE.match(t) or PAGE_NAME_LABEL_RE.match(t):
        return 'drawing_name'
    if PROJECT_NO_LABEL_RE.match(t):
        return 'project_number'
    if PROJECT_TYPE_LABEL_RE.search(t):
        return 'project_type'
    if REV_LABEL_BOTTOM_RE.match(t) or REVISION_RE.match(t):
        return 'revision'
    return None


def _classify_top_label(text: str) -> str | None:
    t = text.strip()
    if PROJECT_NO_LABEL_RE.match(t):
        return 'project_number'
    if PROJECT_TYPE_LABEL_RE.search(t):
        return 'project_type'
    return None


def _is_metadata_value(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if DATE_FALLBACK_RE.fullmatch(t):
        return True
    if WORK_TYPE_VALUE_RE.match(t):
        return True
    if INITIALS_RE.match(t) and t.upper() not in NAME_STACK_CONNECTORS:
        return True
    if METADATA_INLINE_RE.match(t):
        return True
    if TYPE_INLINE_RE.match(t):
        return True
    return False


def _line_from_words(words: list[WordSpan], column: str) -> TextLine | None:
    if not words:
        return None
    words = sorted(words, key=lambda w: w.x0)
    sizes = [w.font_size for w in words if w.font_size > 0]
    return TextLine(
        min(w.y0 for w in words), max(w.y1 for w in words),
        min(w.x0 for w in words), max(w.x1 for w in words),
        ' '.join(w.text for w in words), words,
        max(w.height for w in words),
        max(sizes) if sizes else max(w.height for w in words),
        column,
    )


def _split_line_by_columns(line: TextLine, split_x: float) -> list[TextLine]:
    """Split a horizontal text line into left / right / full segments."""
    text = line.text.strip()
    if DRAWING_NAME_LABEL_RE.search(text) or _classify_bottom_label(text) == 'drawing_name':
        line.column = 'full'
        return [line]
    if _normalize_drawing_number(text) and line.cx >= split_x:
        line.column = 'right'
        return [line]

    left_words = [w for w in line.words if w.cx < split_x]
    right_words = [w for w in line.words if w.cx >= split_x]
    out: list[TextLine] = []
    left_ln = _line_from_words(left_words, 'left')
    right_ln = _line_from_words(right_words, 'right')
    if left_ln and left_ln.text.strip():
        out.append(left_ln)
    if right_ln and right_ln.text.strip() and not _is_metadata_value(right_ln.text):
        out.append(right_ln)
    if not out:
        line.column = 'full'
        out.append(line)
    return out


def _column_split_x(page_w: float, vert_lines: list[float]) -> float:
    """X coordinate separating metadata column from identifier column."""
    candidates = [x for x in vert_lines if page_w * 0.48 <= x <= page_w * 0.78]
    if candidates:
        candidates.sort()
        return candidates[0]
    return page_w * 0.62


def _lines_to_labeled_cell(lines: list[TextLine], med_h: float, med_size: float) -> LabeledCell | None:
    if not lines:
        return None
    lines = sorted(lines, key=lambda ln: ln.y0)
    x0 = min(ln.x0 for ln in lines)
    x1 = max(ln.x1 for ln in lines)
    y0 = min(ln.y0 for ln in lines)
    y1 = max(ln.y1 for ln in lines)
    column = lines[0].column if lines else 'full'

    label_kind = None
    label_text = ''
    label_idx = None
    label_size = med_size
    label_position = 'bottom'

    # Top-label pattern (Project No. above 2024.0565)
    top_kind = _classify_top_label(lines[0].text)
    if top_kind:
        label_kind = top_kind
        label_text = lines[0].text.strip()
        label_idx = 0
        label_size = lines[0].font_size or lines[0].height
        label_position = 'top'

    # Bottom-label pattern (value above Drawing No. / Drawing Name:)
    if label_idx is None:
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
                    label_position = 'top' if i == 0 else 'bottom'
                    break
                if PROJECT_TYPE_LABEL_RE.search(ln.text):
                    label_kind = 'project_type'
                    label_text = ln.text.strip()
                    label_idx = i
                    label_size = fs
                    break

    if label_idx is None:
        return None

    if label_position == 'top':
        value_lines = lines[label_idx + 1:]
    else:
        value_lines = lines[:label_idx]

    value_text = ''
    value_height = 0.0
    value_font_size = 0.0
    if value_lines:
        size_threshold = max(med_size * 0.82, label_size * 1.25)
        large = [ln for ln in value_lines if (ln.font_size or ln.height) >= size_threshold]
        if not large:
            large = [max(value_lines, key=lambda ln: (ln.font_size or ln.height, len(ln.text)))]
        large.sort(key=lambda ln: ln.y0)
        value_text = ' '.join(ln.text.strip() for ln in large).strip()
        value_height = max(ln.height for ln in large)
        value_font_size = max(ln.font_size or ln.height for ln in large)

    if not value_text:
        return None

    return LabeledCell(
        x0, y0, x1, y1, lines, label_text, label_kind, value_text, value_height, value_font_size, column,
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
        if cell:
            cells.append(cell)
    return cells


def _extract_vector_segments(page) -> tuple[list[float], list[float]]:
    page_w, page_h = page.rect.width, page.rect.height
    x_min = page_w * CORNER_X0_RATIO
    y_min = page_h * CORNER_Y0_RATIO
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


def _right_column_bounds(page_w: float, vert_lines: list[float]) -> tuple[float, float]:
    br_verts = [x for x in vert_lines if x >= page_w * 0.55]
    if len(br_verts) >= 2:
        br_verts.sort()
        x0, x1 = br_verts[-2], br_verts[-1]
        if x1 - x0 >= page_w * 0.05:
            return x0, x1
    split_x = _column_split_x(page_w, vert_lines)
    return split_x, page_w * 0.995


def _identify_name_band_indices(lines: list[TextLine], cell_gap: float) -> set[int]:
    """Lines belonging to the full-width drawing name row."""
    indices: set[int] = set()
    for i, ln in enumerate(lines):
        if _classify_bottom_label(ln.text) == 'drawing_name' or DRAWING_NAME_LABEL_RE.search(ln.text):
            indices.add(i)
            for j in range(i - 1, -1, -1):
                prev = lines[j]
                if ln.y0 - prev.y1 <= cell_gap * 1.6:
                    indices.add(j)
                else:
                    break
    return indices


def _build_title_block(page) -> tuple[float, float, list[LabeledCell]]:
    """Parse full title block: name band + right identifier column."""
    page_w, page_h = page.rect.width, page.rect.height
    words = _words_from_page(page)
    if not words:
        return page_w, page_h, []

    tb_words = _title_block_spans(words, page_w, page_h)
    tb_words = [w for w in tb_words if not _is_stamp_or_footer(w.text)]
    if not tb_words:
        return page_w, page_h, []

    horiz, vert = _extract_vector_segments(page)
    split_x = _column_split_x(page_w, vert)
    right_x0, right_x1 = _right_column_bounds(page_w, vert)

    med_h = _median_height(tb_words)
    med_size = _median_font_size(tb_words)
    y_tol = max(2.5, med_h * 0.42)
    cell_gap = max(6.0, med_size * 0.90, med_h * 1.10)

    raw_lines = _cluster_words_into_lines(tb_words, y_tol)
    name_band_idxs = _identify_name_band_indices(raw_lines, cell_gap)

    tb_x0 = page_w * CORNER_X0_RATIO
    tb_left = min(w.x0 for w in tb_words)
    tb_width = max(page_w * CORNER_X1_RATIO, max(w.x1 for w in tb_words)) - tb_left
    split_lines: list[TextLine] = []
    for i, ln in enumerate(raw_lines):
        if i in name_band_idxs:
            ln.column = 'full'
            split_lines.append(ln)
            continue
        if ln.width >= tb_width * 0.45 and ln.x0 <= tb_left + tb_width * 0.10:
            ln.column = 'full'
            split_lines.append(ln)
        elif ln.cx >= split_x:
            if not _is_metadata_value(ln.text):
                ln.column = 'right'
                split_lines.append(ln)
        elif ln.x1 <= split_x - 4:
            ln.column = 'left'
            continue
        else:
            split_lines.extend(_split_line_by_columns(ln, split_x))

    full_lines = [ln for ln in split_lines if ln.column == 'full']
    right_lines = [ln for ln in split_lines if ln.column == 'right' and ln.cx >= right_x0 - 6]
    if len(right_lines) < 2:
        right_lines = [ln for ln in split_lines if ln.column == 'right']

    name_cells = _cluster_lines_into_cells(full_lines, cell_gap)
    right_cells = _cluster_lines_into_cells(right_lines, cell_gap)

    cells: list[LabeledCell] = []
    seen: set[tuple] = set()
    for cell in name_cells + right_cells:
        key = (round(cell.y0, 1), cell.label_kind, cell.value_text, cell.column)
        if key not in seen:
            cells.append(cell)
            seen.add(key)
    return page_w, page_h, cells


def _is_project_number_value(text: str) -> bool:
    t = text.strip().replace(' ', '')
    return bool(DOTTED_PROJECT_NO_RE.match(t))


def _detect_label_anchors(lines: list[TextLine]) -> list[LabelAnchor]:
    """Find drawing/page name and number labels anywhere in the title block."""
    anchors: list[LabelAnchor] = []
    for i, ln in enumerate(lines):
        t = ln.text.strip()
        if not t:
            continue
        if _is_drawing_name_label_text(t):
            anchors.append(LabelAnchor('drawing_name', i, ln, 'above'))
        elif _is_drawing_number_label_text(t):
            anchors.append(LabelAnchor(
                'drawing_number', i, ln, _sheet_label_value_direction(t),
            ))
        elif PROJECT_NO_LABEL_RE.match(t) or re.search(r'^(?:project|job)\s*(?:no|num|number)\.?\s*:?\s*$', t, re.I):
            anchors.append(LabelAnchor('project_number', i, ln, 'below'))
    return anchors


def _horizontal_alignment(anchor: TextLine, candidate: TextLine, page_w: float, kind: str) -> float:
    overlap = min(anchor.x1, candidate.x1) - max(anchor.x0, candidate.x0)
    if kind == 'drawing_name':
        if overlap > 0:
            return 1.0
        if abs(candidate.cx - anchor.cx) <= page_w * 0.28:
            return 0.85
        if candidate.cx >= anchor.x0 - page_w * 0.08:
            return 0.55
        return 0.15
    if overlap > 0:
        return 1.0
    if abs(candidate.cx - anchor.cx) <= page_w * 0.14:
        return 0.9
    return 0.2


def _should_skip_upward_line(text: str, kind: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if _is_stamp_or_footer(t):
        return True
    if SKIP_UPWARD_RE.match(t):
        return True
    if TYPE_INLINE_RE.match(t):
        return True
    if _is_metadata_value(t):
        return True
    if kind == 'drawing_number' and _is_project_number_value(t):
        return True
    if kind == 'drawing_name' and re.search(r'^(?:aldi|store\s*#|polk\s*county)\b', t, re.I):
        return True
    if kind == 'drawing_name' and re.search(r'\b(?:loop\s*rd|fax|haines\s*city)\b', t, re.I):
        return True
    return False


def _should_break_upward_walk(text: str, kind: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if PROJECT_NAME_LOCATION_RE.search(t):
        return True
    if BREAK_UPWARD_RE.search(t):
        return True
    if kind == 'drawing_name' and _classify_bottom_label(t) == 'drawing_number':
        return True
    return False


def _is_label_line(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    return bool(
        _classify_bottom_label(t)
        or _classify_top_label(t)
        or METADATA_INLINE_RE.match(t)
        or TYPE_INLINE_RE.match(t)
    )


def _large_text_near_label(
    lines: list[TextLine],
    anchor: LabelAnchor,
    page_w: float,
    med_size: float,
    *,
    max_lines: int = 8,
    max_gap: float = 40.0,
) -> str:
    """Collect the largest text line(s) adjacent to a label anchor."""
    idx = anchor.line_idx
    direction = anchor.value_direction
    anchor_ln = anchor.line
    collected: list[tuple[float, float, TextLine]] = []

    if direction == 'above':
        indices = range(idx - 1, max(-1, idx - max_lines - 1), -1)
        edge = anchor_ln.y0
    else:
        indices = range(idx + 1, min(len(lines), idx + max_lines + 1))
        edge = anchor_ln.y1

    for j in indices:
        ln = lines[j]
        if direction == 'above':
            if _should_break_upward_walk(ln.text, anchor.kind):
                break
            if _should_skip_upward_line(ln.text, anchor.kind):
                continue
        elif _is_label_line(ln.text) and not _is_name_continuation_line(ln.text):
            continue
        elif _is_metadata_value(ln.text) or _is_stamp_or_footer(ln.text):
            continue
        gap = abs(edge - (ln.y1 if direction == 'above' else ln.y0))
        if collected and gap > max_gap:
            break
        size = ln.font_size or ln.height
        align = _horizontal_alignment(anchor_ln, ln, page_w, anchor.kind)
        if align < 0.15 and not _is_name_continuation_line(ln.text):
            continue
        if anchor.kind == 'drawing_number' and _is_project_number_value(ln.text):
            continue
        if anchor.kind == 'drawing_name':
            min_name_size = max(med_size * 1.05, 16.0)
            if size < min_name_size and not _is_name_continuation_line(ln.text):
                continue
        if anchor.kind == 'drawing_number':
            maybe = _normalize_sheet_from_title_block(ln.text)
            if not maybe and size < med_size * 0.82:
                continue
        collected.append((align, size, ln))
        edge = ln.y0 if direction == 'above' else ln.y1

    if not collected:
        return ''

    collected.sort(key=lambda t: t[2].y0)
    if anchor.kind == 'drawing_number':
        sheet_matches = [
            (align, size, ln)
            for align, size, ln in collected
            if _normalize_sheet_from_title_block(ln.text)
        ]
        if sheet_matches:
            best = max(sheet_matches, key=lambda t: (t[1], t[0]))
            return best[2].text.strip()
        best = max(collected, key=lambda t: (t[1], t[0]))
        return best[2].text.strip()

    parts: list[str] = []
    for _, _, ln in collected:
        text = ln.text.strip()
        if not text:
            continue
        if parts and _is_name_continuation_line(text):
            parts.append(text)
        elif not parts:
            parts.append(text)
        elif (ln.font_size or ln.height) >= med_size * 0.72:
            parts.append(text)
    return ' '.join(parts).strip()


def _extract_by_label_proximity(
    lines: list[TextLine],
    page_w: float,
    page_h: float,
    med_size: float,
) -> dict[str, Any]:
    """Primary extraction: nearest large text to drawing/page name & number labels."""
    out: dict[str, Any] = {
        'sheet_number': None,
        'drawing_name': '',
        'project_number': None,
        'confidence': {'sheet': 0.0, 'name': 0.0, 'project': 0.0},
        'sheet_label_anchored': False,
    }
    if not lines:
        return out

    anchors = _detect_label_anchors(lines)
    sheet_scores: list[tuple[float, str]] = []
    name_scores: list[tuple[float, str]] = []
    labeled_sheet = False
    labeled_name = False

    sheet_anchor_for_name: LabelAnchor | None = None

    for anchor in anchors:
        value = _large_text_near_label(lines, anchor, page_w, med_size)
        if not value:
            continue
        if anchor.kind == 'drawing_number':
            is_sheet_only = bool(SHEET_ONLY_LABEL_RE.match(anchor.line.text.strip()))
            sheet = (
                _normalize_anchored_sheet_value(value)
                if is_sheet_only
                else _normalize_sheet_from_title_block(value)
            )
            if sheet and not _is_project_number_value(value):
                labeled_sheet = True
                if is_sheet_only:
                    out['sheet_label_anchored'] = True
                    sheet_anchor_for_name = anchor
                pos = (anchor.line.cy / page_h) * 0.55 + (anchor.line.cx / page_w) * 0.45
                size = anchor.line.font_size or anchor.line.height
                score = (8.5 if is_sheet_only else 3.5) + pos + size * 0.03
                sheet_scores.append((score, sheet))
        elif anchor.kind == 'drawing_name':
            if _is_plausible_drawing_title(value, None):
                labeled_name = True
                pos = 1.0 - (anchor.line.cy / page_h) * 0.35
                best_size = max(
                    (ln.font_size or ln.height)
                    for ln in lines[max(0, anchor.line_idx - 6):anchor.line_idx]
                ) if anchor.line_idx else anchor.line.font_size
                name_scores.append((3.0 + pos + best_size * 0.02, value))
        elif anchor.kind == 'project_number':
            if _is_plausible_project_number(value):
                out['project_number'] = value.strip().upper()
                out['confidence']['project'] = 1.5

    if sheet_scores:
        sheet_scores.sort(key=lambda t: t[0], reverse=True)
        out['sheet_number'] = sheet_scores[0][1]
        out['confidence']['sheet'] = sheet_scores[0][0]

    if name_scores:
        name_scores.sort(key=lambda t: t[0], reverse=True)
        out['drawing_name'] = name_scores[0][1][:200]
        out['confidence']['name'] = name_scores[0][0]

    if not out['drawing_name'] and (sheet_scores or out.get('sheet_label_anchored')):
        sheet_anchor = sheet_anchor_for_name or next(
            (a for a in anchors if a.kind == 'drawing_number'),
            None,
        )
        inferred = _infer_drawing_name_above_sheet(lines, sheet_anchor, med_size)
        if inferred:
            out['drawing_name'] = inferred
            out['confidence']['name'] = 3.2 if out.get('sheet_label_anchored') else 2.8
            labeled_name = True

    out['label_anchored'] = labeled_sheet and (labeled_name or bool(out['drawing_name']))
    if out.get('sheet_label_anchored') and out.get('sheet_number'):
        out['label_anchored'] = True
    return out


def _extract_date_from_lines(lines: list[TextLine]):
    for ln in lines:
        m = DATE_INLINE_RE.search(ln.text)
        if m:
            parsed = extract_drawing_date_from_text(m.group(1))
            if parsed:
                return parsed
    return None


def _title_block_lines_from_page(page) -> tuple[float, float, list[TextLine], float]:
    dict_lines, page_w, page_h, med_size = _dict_lines_from_page(page)
    if dict_lines:
        return page_w, page_h, dict_lines, med_size
    page_w, page_h = page.rect.width, page.rect.height
    words = _words_from_page(page)
    tb_words = _title_block_spans(words, page_w, page_h)
    tb_words = [w for w in tb_words if not _is_stamp_or_footer(w.text)]
    med_h = _median_height(tb_words) if tb_words else 8.0
    med_size = _median_font_size(tb_words) if tb_words else med_h
    y_tol = max(2.5, med_h * 0.42)
    lines = _cluster_words_into_lines(tb_words, y_tol)
    return page_w, page_h, lines, med_size


def _is_name_stack_line(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.upper() in NAME_STACK_CONNECTORS:
        return True
    return _is_plausible_drawing_title(t, None)


def _normalize_anchored_sheet_value(raw: str) -> str | None:
    """Sheet numbers read directly from a SHEET:/Drawing No. label cell."""
    if not raw:
        return None
    compact = re.sub(r'\s+', '', raw.upper())
    if GLUED_SHEET_CODE_RE.match(compact) or OPAQUE_SHEET_CODE_RE.match(compact):
        return compact
    return _normalize_drawing_number(raw)


def _normalize_custom_sheet_code(raw: str) -> str | None:
    """Project-specific sheet IDs like OPDSP1 / OPDBAS2 from a SHEET: title block."""
    if not raw:
        return None
    compact = re.sub(r'\s+', '', raw.upper())
    if GLUED_SHEET_CODE_RE.match(compact) or OPAQUE_SHEET_CODE_RE.match(compact):
        return compact
    m = CUSTOM_SHEET_VALUE_RE.match(compact)
    if m:
        return f'{m.group(1).upper()}-{m.group(2)}'
    return None


def _normalize_drawing_number(raw: str) -> str | None:
    if not raw:
        return None
    compact = re.sub(r'\s+', '', raw.upper())
    m = DRAWING_NUMBER_VALUE_RE.match(compact)
    if m:
        suffix = (m.group(3) or '').upper()
        sheet = f'{m.group(1).upper()}-{m.group(2)}' + (suffix if suffix else '')
        if is_plausible_drawing_sheet(sheet) or re.match(r'^[A-Z]{1,4}-\d{1,4}[A-Za-z]?$', sheet):
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
        if is_plausible_drawing_sheet(sheet) or re.match(r'^[A-Z]{1,4}-\d{1,4}[A-Za-z]?$', sheet):
            return sheet
    cand = normalize_sheet_number(compact)
    if cand and is_plausible_drawing_sheet(cand):
        return cand
    return _normalize_custom_sheet_code(compact)


def _normalize_sheet_from_title_block(raw: str) -> str | None:
    return _normalize_drawing_number(raw)


def _infer_drawing_name_above_sheet(
    lines: list[TextLine],
    sheet_anchor: LabelAnchor | None,
    med_size: float,
) -> str:
    """Layouts with only SHEET: — large drawing title sits in the box above, no name label."""
    if not sheet_anchor:
        return ''
    parts: list[str] = []
    edge = sheet_anchor.line.y0
    anchor_x0 = sheet_anchor.line.x0
    anchor_x1 = sheet_anchor.line.x1
    for j in range(sheet_anchor.line_idx - 1, max(-1, sheet_anchor.line_idx - 14), -1):
        ln = lines[j]
        if _should_break_upward_walk(ln.text, 'drawing_name'):
            break
        if _should_skip_upward_line(ln.text, 'drawing_name'):
            continue
        if _is_drawing_number_label_text(ln.text) or _normalize_anchored_sheet_value(ln.text):
            break
        overlap = min(anchor_x1, ln.x1) - max(anchor_x0, ln.x0)
        if overlap <= 0 and abs(ln.cx - sheet_anchor.line.cx) > max(anchor_x1 - anchor_x0, 40) * 1.8:
            if parts:
                break
            continue
        gap = edge - ln.y1
        if parts and gap > 40:
            break
        size = ln.font_size or ln.height
        min_size = max(med_size * 0.72, 9.0) if parts else max(med_size * 0.85, 11.0)
        if size < min_size and not (
            parts and ln.text.strip().upper() in NAME_STACK_CONNECTORS
        ):
            continue
        text = ln.text.strip()
        if not _is_name_stack_line(text):
            continue
        parts.insert(0, text)
        edge = ln.y0
    return ' '.join(parts).strip()[:200]


def _is_plausible_drawing_title(text: str, sheet_number: str | None) -> bool:
    if not text or len(text) < 3 or len(text) > 180:
        return False
    t = text.strip()
    upper = t.upper()
    if PROJECT_TYPE_LABEL_RE.search(t):
        return False
    if METADATA_INLINE_RE.search(t):
        return False
    m = TYPE_INLINE_RE.match(t)
    if m and WORK_TYPE_VALUE_RE.match((m.group(1) or '').strip()):
        return False
    if WORK_TYPE_VALUE_RE.match(t):
        return False
    if INITIALS_RE.match(t):
        return False
    if _normalize_anchored_sheet_value(t) and ' ' not in t:
        return False
    if PROJECT_NUMBER_VALUE_RE.match(t.replace(' ', '')) and '.' in t:
        return False
    if sheet_number and sheet_number.upper().replace('-', '') in upper.replace('-', '').replace(' ', ''):
        return False
    if REVISION_RE.search(t) or REV_NO_RE.search(t):
        return False
    if DATE_RE.search(t) or DATE_FALLBACK_RE.fullmatch(t):
        return False
    if ARCH_SCALE_RE.search(t) or RATIO_SCALE_RE.search(t):
        return False
    if NOTE_SPEC_TITLE_RE.search(t):
        return False
    if re.search(r'\b\d{1,3}[,.]?\d*\s*(?:LBS?|POUNDS?|KG|PSI)\b', t, re.I):
        return False
    if re.match(r'^(?:NEW|RENOVATION|ADDITION|TI|BUILD[- ]?OUT|TENANT|COMMERCIAL|RESIDENTIAL)\b', upper):
        if not TITLE_HINT_RE.search(t) and not LOCAL_TITLE_HINT_RE.search(t):
            return False
    if TITLE_HINT_RE.search(t) or LOCAL_TITLE_HINT_RE.search(t):
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
    """Southernmost-right cell with Drawing No label."""
    right_cells = [
        c for c in cells
        if c.column in ('right', 'full') and (c.cx >= page_w * 0.58 or c.label_kind == 'drawing_number')
    ]
    candidates: list[tuple[float, LabeledCell]] = []
    for cell in right_cells:
        score = (cell.cy / page_h) * 0.60 + (cell.cx / page_w) * 0.40
        if cell.label_kind == 'drawing_number':
            candidates.append((score + 3.0 + cell.value_font_size * 0.02, cell))
        elif cell.value_text and _normalize_drawing_number(cell.value_text):
            if cell.label_kind in (None, 'project_number'):
                continue
            candidates.append((score + cell.value_font_size * 0.05 + 1.0, cell))
    if not candidates:
        for cell in right_cells:
            if cell.value_text and _normalize_drawing_number(cell.value_text):
                score = (cell.cy / page_h) * 0.60 + (cell.cx / page_w) * 0.40
                candidates.append((score + cell.value_font_size * 0.05, cell))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _find_drawing_name_cell(
    cells: list[LabeledCell],
    sheet_cell: LabeledCell | None,
    page_w: float,
) -> LabeledCell | None:
    """Drawing name from full-width top band — not the metadata left column."""
    name_cells = [
        c for c in cells
        if c.label_kind == 'drawing_name' and c.value_text
        and c.column in ('full', 'right')
    ]
    if name_cells:
        name_cells.sort(key=lambda c: (-(c.width / max(page_w, 1)), c.y0, -c.value_font_size))
        for cell in name_cells:
            if _is_plausible_drawing_title(cell.value_text, None):
                return cell

    if sheet_cell:
        above = [
            c for c in cells
            if c.cy < sheet_cell.cy
            and c.value_text
            and c.label_kind not in ('project_type', 'project_number', 'drawing_number', 'revision', None)
            and c.column in ('full', 'right')
        ]
        above.sort(key=lambda c: (c.y0, -(c.width / max(page_w, 1)), -(c.value_font_size or 0)))
        for cell in above:
            if cell.label_kind == 'drawing_name' or _is_plausible_drawing_title(cell.value_text, None):
                return cell
    return None


def _ocr_title_block(pdf_path: str, page_index: int) -> list[LabeledCell]:
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
        clip = fitz.Rect(
            rect.width * CORNER_X0_RATIO,
            rect.height * CORNER_Y0_RATIO,
            rect.width * CORNER_X1_RATIO,
            rect.height * 0.995,
        )
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
                pseudo_words.append(WordSpan(x0, y0, x1, y1, text, font_size=h * scale_y))
            if pseudo_words:
                med_h = _median_height(pseudo_words)
                med_size = _median_font_size(pseudo_words)
                lines = _cluster_words_into_lines(pseudo_words, max(3.0, med_h * 0.5))
                split_x = clip.x0 + clip.width * 0.55
                split_lines: list[TextLine] = []
                for ln in lines:
                    if ln.width >= clip.width * 0.50:
                        ln.column = 'full'
                        split_lines.append(ln)
                    elif ln.cx >= split_x:
                        ln.column = 'right'
                        split_lines.append(ln)
                    else:
                        split_lines.extend(_split_line_by_columns(ln, split_x))
                full_cells = _cluster_lines_into_cells([l for l in split_lines if l.column == 'full'], max(8.0, med_size * 1.0))
                right_cells = _cluster_lines_into_cells([l for l in split_lines if l.column == 'right'], max(8.0, med_size * 1.0))
                cells.extend(full_cells)
                cells.extend(right_cells)
        doc.close()
    except Exception:
        pass
    return cells


def analyze_title_block_grid(pdf_path: str, page_index: int = 0) -> dict[str, Any]:
    """Bluebeam-style title block extraction from full name band + right column."""
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
        'label_anchored': False,
        'sheet_label_anchored': False,
    }
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            doc.close()
            return result
        page = doc[page_index]
        embedded = page.get_text('text') or ''
        page_w, page_h, tb_lines, med_size = _title_block_lines_from_page(page)
        page_w, page_h, cells = _build_title_block(page)
        proximity = _extract_by_label_proximity(tb_lines, page_w, page_h, med_size)
        doc.close()
    except Exception:
        return result

    if len(cells) < 2:
        ocr_cells = _ocr_title_block(pdf_path, page_index)
        seen = {(round(c.y0, 1), c.label_kind, c.value_text) for c in cells}
        for c in ocr_cells:
            key = (round(c.y0, 1), c.label_kind, c.value_text)
            if key not in seen:
                cells.append(c)
                seen.add(key)

    result['grid_cells'] = len(cells)

    sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
    final_sheet = proximity.get('sheet_number')
    sheet_conf = float((proximity.get('confidence') or {}).get('sheet', 0))
    if sheet_cell:
        cell_sheet = _normalize_drawing_number(sheet_cell.value_text)
        cell_conf = 0.0
        if cell_sheet:
            cell_conf = 2.2 + sheet_cell.value_font_size * 0.04
            if sheet_cell.label_kind == 'drawing_number':
                cell_conf += 0.8
        if not final_sheet or cell_conf > sheet_conf:
            final_sheet = cell_sheet
            sheet_conf = cell_conf

    name_cell = _find_drawing_name_cell(cells, sheet_cell, page_w)
    drawing_name = (proximity.get('drawing_name') or '').strip()
    name_conf = float((proximity.get('confidence') or {}).get('name', 0))
    if name_cell and name_cell.value_text:
        candidate = name_cell.value_text.strip()
        if _is_plausible_drawing_title(candidate, final_sheet):
            cell_conf = 2.0 + name_cell.value_font_size * 0.03
            if name_cell.label_kind == 'drawing_name':
                cell_conf += 0.8
            if name_cell.column == 'full':
                cell_conf += 0.4
            if not drawing_name or cell_conf > name_conf:
                drawing_name = candidate[:200]
                name_conf = cell_conf

    project_number = proximity.get('project_number')
    if not project_number:
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
    corner_date = _extract_date_from_lines(tb_lines)
    result['drawing_date'] = corner_date or extract_drawing_date_from_text(
        '\n'.join(ln.text for ln in tb_lines if not _is_stamp_or_footer(ln.text))
    )
    result['scale'] = extract_scale_from_text(merged_text)
    result['text_preview'] = merged_text[:400]
    result['label_anchored'] = bool(
        proximity.get('label_anchored')
        or proximity.get('sheet_label_anchored')
        or (final_sheet and drawing_name and sheet_conf >= 3.0 and name_conf >= 2.5)
    )
    result['sheet_label_anchored'] = bool(proximity.get('sheet_label_anchored'))
    result['confidence'] = {
        'sheet': round(sheet_conf, 2),
        'name': round(name_conf, 2),
        'project': 1.4 if project_number else 0,
        'revision': 1.1 if revision else 0,
    }
    return result


# Backward-compatible exports
build_title_block_grid = _build_title_block
