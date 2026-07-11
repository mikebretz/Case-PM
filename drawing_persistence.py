"""Drawing persistence, PDF processing, revision tracking, and markup helpers."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, date

from db_sqlite import commit_with_retry, flush_with_retry

try:
    from sqlalchemy.exc import IntegrityError
except ImportError:
    IntegrityError = Exception  # type: ignore

DISCIPLINE_MAP = {
    'A': 'Architectural',
    'AD': 'Architectural',
    'AR': 'Architectural',
    'S': 'Structural',
    'ST': 'Structural',
    'M': 'Mechanical',
    'H': 'Mechanical',
    'HVAC': 'Mechanical',
    'E': 'Electrical',
    'EL': 'Electrical',
    'P': 'Plumbing',
    'PL': 'Plumbing',
    'FP': 'Fire Protection',
    'FA': 'Fire Protection',
    'C': 'Civil',
    'CI': 'Civil',
    'L': 'Landscape',
    'LA': 'Landscape',
    'G': 'General',
    'T': 'Telecom',
    'I': 'Interiors',
}

SHEET_RE = re.compile(
    r'\b([A-Z]{1,3})[-_.\s]?(\d{1,4}(?:\.\d{1,2})?)\b',
    re.IGNORECASE,
)
CSI_SHEET_RE = re.compile(
    r'\b([A-Z]{1,3})[-_.\s]?(\d{1,2})\.(\d{1,2})\b',
    re.IGNORECASE,
)
TITLE_BLOCK_RE = re.compile(
    r'(?:SHEET|DRAWING|DWG\.?\s*NO\.?|SHT\.?)[:\s#]*([A-Z]{1,3}[-_.\s]?\d{1,4}(?:\.\d{1,2})?)',
    re.IGNORECASE,
)
REVISION_RE = re.compile(
    r'(?:REV(?:ISION)?\.?|REVISION)\s*[#:.]?\s*(\d{1,3})',
    re.IGNORECASE,
)
REVISION_LOOSE_RE = re.compile(
    r'(?:^|\s)(?:REV|REVISION)\s*[#:.]?\s*(\d{1,3})(?:\s|$)',
    re.IGNORECASE,
)
SHEET_LABEL_RE = re.compile(
    r'(?:SHEET|SHT|DWG|DRAWING)\s*(?:NO|NUM|NUMBER|#)?',
    re.IGNORECASE,
)
TITLE_HINT_RE = re.compile(
    r'\b(PLAN|ELEVATION|SECTION|DETAIL|SCHEDULE|FLOOR|ROOF|SITE|CEILING|FOUNDATION|FRAMING|RCP|REFLECTED)\b',
    re.IGNORECASE,
)
DRAWING_NAME_LABEL_RE = re.compile(
    r'(?:DRAWING\s*NAME|DRAWING\s*TITLE|SHEET\s*NAME|SHEET\s*TITLE|TITLE\s*OF\s*DRAWING)',
    re.IGNORECASE,
)
DRAWING_NAME_INLINE_RE = re.compile(
    r'(?:DRAWING\s*NAME|DRAWING\s*TITLE|SHEET\s*NAME|SHEET\s*TITLE)\s*[:#]?\s*(.+)$',
    re.IGNORECASE,
)
SHEET_NO_LABEL_RE = re.compile(
    r'(?:SHEET|SH\.?|SHT\.?|DWG\.?|DRAWING)\s*(?:NO\.?|NUM(?:BER)?|#)\s*[:#]?\s*(.+)$',
    re.IGNORECASE,
)
PROJECT_LABEL_RE = re.compile(
    r'(?:PROJECT|JOB)\s*(?:NO\.?|NUM(?:BER)?|NAME|#)',
    re.IGNORECASE,
)
LABEL_ONLY_RE = re.compile(
    r'^(?:DRAWING\s*NAME|DRAWING\s*TITLE|SHEET\s*NAME|SHEET\s*TITLE|SHEET|SH\.?|SHT\.?|DWG\.?|'
    r'DRAWING|PROJECT|JOB|DATE|SCALE|REV(?:ISION)?|REVISION|CHECKED|DRAWN|DESIGNED|APPROVED|'
    r'SHEET\s*NO\.?|DRAWING\s*NO\.?)\s*[:#.]?\s*$',
    re.IGNORECASE,
)
REV_NO_RE = re.compile(
    r'REV(?:ISION)?\.?\s*(?:NO\.?|NUM|NUMBER|#)\s*[:.]?\s*(\d{1,3})',
    re.IGNORECASE,
)
REV_ISSUE_RE = re.compile(
    r'(?:ISSUE|CURRENT|LATEST)\s*(?:REV(?:ISION)?)?\.?\s*[#:.]?\s*(\d{1,3})',
    re.IGNORECASE,
)
REV_OCR_MISREAD_RE = re.compile(
    r'REV(?:ISION)?\.?\s*[#:.]?\s*([IL|!])',
    re.IGNORECASE,
)
ARCH_SCALE_RE = re.compile(
    r'(\d+)\s*/\s*(\d+)\s*["\u201d]?\s*=\s*(\d+)\s*(?:[\'\u2019\-]\s*(\d{1,2})|[\'\u2019])?',
    re.IGNORECASE,
)
RATIO_SCALE_RE = re.compile(
    r'(?:SCALE\s*[:=]?\s*)?1\s*[:/]\s*(\d{1,4})',
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r'(?:DATE|DRAWN|ISSUE(?:D)?|REVISION\s+DATE|PROJECT\s+DATE)[:\s#]*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})',
    re.IGNORECASE,
)
DATE_FALLBACK_RE = re.compile(r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b')
# Filename / OCR false positives (e.g. "Drawings_Rev_3.pdf" → not sheet REV-3)
INVALID_NOTE_SHEET_PREFIXES = frozenset({'LF', 'SF', 'SM', 'SY', 'KG', 'LB', 'GA', 'PSI'})
INVALID_SHEET_PREFIXES = frozenset({'REV', 'RE', 'R'})
VALID_SHEET_PREFIXES = frozenset(DISCIPLINE_MAP.keys()) | frozenset({
    'A', 'S', 'M', 'E', 'P', 'C', 'G', 'L', 'T', 'I', 'H', 'FP', 'FA', 'AD', 'AR', 'ST', 'EL', 'PL', 'CI', 'LA', 'HVAC',
})


def ensure_drawing_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if 'drawing' not in tables:
        return
    cols = {c['name'] for c in inspector.get_columns('drawing')}
    additions = {
        'section_prefix': 'VARCHAR(10)',
        'thumbnail_path': 'VARCHAR(500)',
        'sort_key': 'VARCHAR(40)',
    }
    for name, col_type in additions.items():
        if name not in cols:
            db.session.execute(text(f'ALTER TABLE drawing ADD COLUMN {name} {col_type}'))
    if 'punch_item' in tables:
        punch_cols = {c['name'] for c in inspector.get_columns('punch_item')}
        if 'plan_pins_json' not in punch_cols:
            db.session.execute(text('ALTER TABLE punch_item ADD COLUMN plan_pins_json TEXT'))
    db.session.commit()


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)


def normalize_sheet_number(raw: str) -> str | None:
    if not raw:
        return None
    text = str(raw).strip().upper().replace(' ', '')

    # CSI / architectural: A1.01, S2.01, AD1.02
    m = CSI_SHEET_RE.search(text)
    if m:
        sheet = f'{m.group(1)}-{m.group(2)}.{m.group(3)}'
        if is_plausible_drawing_sheet(sheet):
            return sheet

    # Compact: A101, AD102, S201
    m = re.match(r'^([A-Z]{1,3})(\d{3,4})$', text.replace('-', '').replace('_', ''))
    if m:
        sheet = f'{m.group(1)}-{m.group(2)}'
        if is_plausible_drawing_sheet(sheet):
            return sheet

    text = text.replace('_', '-')
    m = SHEET_RE.search(text)
    if not m:
        return None
    prefix, num = m.group(1).upper(), m.group(2)
    if '.' in num:
        sheet = f'{prefix}-{num}'
    else:
        sheet = f'{prefix}-{num}'
    if not is_plausible_drawing_sheet(sheet):
        return None
    return sheet


def is_plausible_drawing_sheet(sheet_number: str) -> bool:
    if not sheet_number:
        return False
    if sheet_number.startswith('UNASSIGNED-'):
        return True
    upper = sheet_number.upper()
    # Reject note fragments like insulation callouts (IN-0.5, 1/2 IN, etc.).
    if re.search(r'-\d*\.\d', upper):
        return False
    if '-' not in sheet_number:
        return bool(
            re.match(r'^[A-Z]{3,10}\d{1,4}$', upper)
            or re.match(r'^(?=.*\d)[A-Z0-9]{3,14}$', upper)
        )
    prefix = sheet_number.split('-')[0].upper()
    if prefix in INVALID_SHEET_PREFIXES:
        return False
    if prefix in INVALID_NOTE_SHEET_PREFIXES:
        return False
    if prefix in {'IN', 'FT', 'MM', 'CM'}:
        return False
    if prefix in VALID_SHEET_PREFIXES:
        return True
    num_part = sheet_number.split('-', 1)[1]
    if bool(re.match(r'^\d{1,4}', num_part)) and prefix.isalpha() and len(prefix) <= 4:
        return True
    # Project-specific sheet IDs from SHEET: title blocks (e.g. OPDBAS-2, OPDSP-1).
    return bool(re.match(r'^[A-Z]{2,8}-\d{1,4}$', upper))


def normalize_revision_number(raw: str | None) -> str | None:
    """Return numeric revision only (1, 2, 3). Maps common OCR misreads like L/I to 1."""
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text:
        return None
    if text in {'I', 'L', '|', '!' }:
        return '1'
    if re.fullmatch(r'\d{1,3}', text):
        return str(int(text))
    return None


def extract_revision_from_text(text: str) -> str | None:
    if not text:
        return None
    for line in (text.splitlines() or [])[-50:]:
        for pattern in (REVISION_RE, REVISION_LOOSE_RE, REV_OCR_MISREAD_RE):
            m = pattern.search(line)
            if m:
                rev = normalize_revision_number(m.group(1))
                if rev is not None:
                    return rev
    m = REVISION_RE.search(text) or REVISION_LOOSE_RE.search(text) or REV_OCR_MISREAD_RE.search(text)
    if m:
        return normalize_revision_number(m.group(1))
    return None


def _plain_text_lines(text: str) -> list[dict]:
    """Turn plain OCR/text into pseudo layout lines for title-block heuristics."""
    lines = []
    for i, raw in enumerate((text or '').splitlines()):
        line = raw.strip()
        if line:
            lines.append({'y': float(i), 'x': 0.0, 'text': line})
    return lines


def _merge_title_block_from_ocr(result: dict, ocr_text: str, embedded: str) -> dict:
    """Fill missing title-block fields from OCR output."""
    if not ocr_text:
        return result
    ocr_lines = _plain_text_lines(ocr_text)
    merged = '\n'.join(filter(None, [embedded, ocr_text]))
    if not result.get('revision'):
        result['revision'] = _extract_revision_from_lines(ocr_lines, ocr_text) or extract_revision_from_text(ocr_text)
    if not result.get('title'):
        title = _extract_drawing_title_from_lines(ocr_lines, result.get('sheet_number'), ocr_text)
        if title:
            result['title'] = title
            result['drawing_name'] = title
    if not result.get('sheet_number'):
        labeled = _extract_sheet_number_from_lines(ocr_lines)
        if labeled and is_plausible_drawing_sheet(labeled):
            result['sheet_number'] = labeled
            result['method'] = 'ocr'
    if not result.get('revision'):
        result['revision'] = _extract_revision_from_lines(ocr_lines, ocr_text) or extract_revision_from_text(ocr_text)
    if not result.get('scale'):
        scale = extract_scale_from_text(merged)
        if scale:
            result['scale'] = scale
    if not result.get('drawing_date'):
        result['drawing_date'] = extract_drawing_date_from_text(ocr_text)
    result['text_preview'] = merged[:400]
    return result


def _build_title_block_lines(words, page_h: float, min_y_ratio: float = 0.52) -> list[dict]:
    """Group positioned words into title-block text lines (top to bottom)."""
    by_line: dict[tuple, list] = {}
    for item in words:
        if len(item) < 8:
            continue
        x0, y0, blk, ln, word = float(item[0]), float(item[1]), int(item[5]), int(item[6]), str(item[4]).strip()
        if not word or y0 < page_h * min_y_ratio:
            continue
        by_line.setdefault((blk, ln), []).append((x0, y0, word))
    lines = []
    for parts in by_line.values():
        parts.sort(key=lambda p: p[0])
        text = ' '.join(p[2] for p in parts).strip()
        if not text:
            continue
        avg_y = sum(p[1] for p in parts) / len(parts)
        avg_x = sum(p[0] for p in parts) / len(parts)
        lines.append({'y': avg_y, 'x': avg_x, 'text': text})
    lines.sort(key=lambda ln: ln['y'])
    return lines


def extract_scale_from_text(text: str) -> dict | None:
    """Parse drawing scale from title block text. Returns pdf points per real foot."""
    if not text:
        return None
    for line in text.splitlines():
        m = ARCH_SCALE_RE.search(line)
        if m:
            num, denom, feet, inches = m.groups()
            paper_in = int(num) / max(int(denom), 1)
            real_ft = int(feet) + (int(inches or 0) / 12.0 if inches else 0)
            if real_ft <= 0:
                real_ft = 1.0
            pdf_pts_per_foot = (paper_in / real_ft) * 72.0
            label = m.group(0).strip()
            return {
                'scale_text': label,
                'pdf_points_per_foot': round(pdf_pts_per_foot, 4),
                'unit': 'ft',
                'method': 'architectural',
            }
    m = RATIO_SCALE_RE.search(text)
    if m:
        ratio = int(m.group(1))
        if ratio > 0:
            # 1:N on 1"=N feet style site plans → 1 paper inch = N feet → pts/foot = 72/N
            pdf_pts_per_foot = 72.0 / ratio
            return {
                'scale_text': f'1:{ratio}',
                'pdf_points_per_foot': round(pdf_pts_per_foot, 4),
                'unit': 'ft',
                'method': 'ratio',
            }
    return None


def _is_label_only_line(text: str) -> bool:
    if not text:
        return True
    t = text.strip()
    if LABEL_ONLY_RE.match(t):
        return True
    if DRAWING_NAME_LABEL_RE.fullmatch(t.strip()):
        return True
    if SHEET_NO_LABEL_RE.match(t) and not _sheet_candidates_from_text(t, 0.5):
        return True
    return False


def _extract_sheet_number_from_lines(lines: list[dict], page_w: float = 0, page_h: float = 0) -> str | None:
    """Extract sheet number from labeled title-block lines (SHEET NO, DWG NO, etc.)."""
    candidates: list[tuple[float, str]] = []
    for i, ln in enumerate(lines):
        text = ln['text'].strip()
        m = SHEET_NO_LABEL_RE.search(text)
        if m:
            tail = m.group(1).strip()
            for score, cand in _sheet_candidates_from_text(tail, 0.95):
                candidates.append((score + 0.2, cand))
            for score, cand in _sheet_candidates_from_text(text, 0.9):
                candidates.append((score, cand))
        if DRAWING_NAME_LABEL_RE.search(text):
            continue
        if PROJECT_LABEL_RE.search(text) and not SHEET_NO_LABEL_RE.search(text):
            continue
        pos = _score_title_block_position(ln.get('x', 0), ln.get('y', 0), page_w or 1000, page_h or 1000)
        for score, cand in _sheet_candidates_from_text(text, pos + 0.1):
            if page_h and ln.get('y', 0) >= page_h * 0.68:
                candidates.append((score + 0.25, cand))
            else:
                candidates.append((score, cand))
        if i + 1 < len(lines):
            nxt = lines[i + 1]['text'].strip()
            if SHEET_NO_LABEL_RE.search(text) or re.search(r'^(SHEET|DWG|DRAWING)\s*NO', text, re.I):
                for score, cand in _sheet_candidates_from_text(nxt, 0.92):
                    candidates.append((score + 0.15, cand))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _extract_drawing_title_from_lines(lines: list[dict], sheet_number: str | None, embedded: str) -> str:
    """Drawing name from title block — typically above sheet number or after DRAWING NAME label."""
    if not lines:
        return ''
    sheet_key = (sheet_number or '').replace('-', '').replace('.', '').replace(' ', '').upper()
    sheet_line_idx = None

    for i, ln in enumerate(lines):
        text = ln['text'].strip()
        compact = text.replace('-', '').replace(' ', '').replace('.', '').upper()
        if sheet_key and sheet_key in compact:
            sheet_line_idx = i
            break
        for _score, cand in _sheet_candidates_from_text(text, 0.85):
            if sheet_number and cand == sheet_number:
                sheet_line_idx = i
                break
        if sheet_line_idx is not None:
            break

    # Label on one line, value on the next (DRAWING NAME / SHEET NAME)
    for i, ln in enumerate(lines):
        text = ln['text'].strip()
        m = DRAWING_NAME_INLINE_RE.match(text)
        if m:
            val = m.group(1).strip()
            if _is_plausible_drawing_title(val, sheet_number):
                return val[:200]
        if DRAWING_NAME_LABEL_RE.search(text) and not DRAWING_NAME_INLINE_RE.match(text):
            if i > 0:
                above = lines[i - 1]['text'].strip()
                if _is_plausible_drawing_title(above, sheet_number):
                    return above[:200]
            if i + 1 < len(lines):
                below = lines[i + 1]['text'].strip()
                if _is_plausible_drawing_title(below, sheet_number):
                    return below[:200]

    # Value directly above sheet number row (most common architectural layout)
    if sheet_line_idx is not None and sheet_line_idx > 0:
        for j in range(sheet_line_idx - 1, max(-1, sheet_line_idx - 3), -1):
            candidate = lines[j]['text'].strip()
            if _is_plausible_drawing_title(candidate, sheet_number):
                return candidate[:200]

    return ''


def _is_plausible_drawing_title(text: str, sheet_number: str | None) -> bool:
    if not text or len(text) < 3 or len(text) > 160:
        return False
    t = text.strip()
    if _is_label_only_line(t):
        return False
    upper = t.upper()
    if sheet_number and sheet_number.upper().replace('-', '') in upper.replace('-', '').replace(' ', ''):
        return False
    if SHEET_NO_LABEL_RE.search(t) and _sheet_candidates_from_text(t, 0.5):
        return False
    if PROJECT_LABEL_RE.search(upper) and not TITLE_HINT_RE.search(t):
        return False
    if SHEET_LABEL_RE.search(upper) and not TITLE_HINT_RE.search(t):
        return False
    if REVISION_RE.search(t) or REV_NO_RE.search(t) or REV_ISSUE_RE.search(t):
        return False
    if DATE_RE.search(t) or DATE_FALLBACK_RE.fullmatch(t.strip()):
        return False
    if ARCH_SCALE_RE.search(t) or RATIO_SCALE_RE.search(t):
        return False
    if upper in ('REV', 'REVISION', 'DATE', 'SCALE', 'DRAWN BY', 'CHECKED BY', 'SHEET', 'DRAWING', 'NA', 'N/A'):
        return False
    if re.fullmatch(r'[\d\s./\-#:]+', t):
        return False
    if TITLE_HINT_RE.search(t):
        return True
    if t.isupper() and len(t) >= 6 and not re.fullmatch(r'[\d\s./-]+', t):
        return True
    if len(t) >= 8 and re.search(r'[A-Za-z]{4,}', t):
        return True
    return False


def _extract_revision_from_lines(lines: list[dict], embedded: str) -> str | None:
    rev_candidates: list[str] = []
    for ln in lines:
        text = ln['text']
        for pattern in (REV_NO_RE, REVISION_RE, REVISION_LOOSE_RE, REV_ISSUE_RE, REV_OCR_MISREAD_RE):
            m = pattern.search(text)
            if m:
                rev = normalize_revision_number(m.group(1))
                if rev is not None:
                    rev_candidates.append(rev)
        parts = text.upper().split()
        for i, part in enumerate(parts):
            if part in ('REV', 'REV.', 'REVISION', 'REVISION:') and i + 1 < len(parts):
                nxt = parts[i + 1].strip(':.#')
                rev = normalize_revision_number(nxt)
                if rev is not None:
                    rev_candidates.append(rev)
    for line in reversed(embedded.splitlines()[-80:]):
        for pattern in (REV_NO_RE, REVISION_RE, REVISION_LOOSE_RE, REV_ISSUE_RE, REV_OCR_MISREAD_RE):
            m = pattern.search(line)
            if m:
                rev = normalize_revision_number(m.group(1))
                if rev is not None:
                    rev_candidates.append(rev)
    return rev_candidates[0] if rev_candidates else None


def _score_title_block_position(x0: float, y0: float, page_w: float, page_h: float) -> float:
    """Higher score = more likely title-block location (bottom-right)."""
    if page_w <= 0 or page_h <= 0:
        return 0.0
    return (x0 / page_w) * 0.55 + (y0 / page_h) * 0.45


def _sheet_candidates_from_text(text: str, position_score: float = 0.5) -> list[tuple[float, str]]:
    found = []
    if not text:
        return found
    compact = re.sub(r'\s+', '', text.upper())
    for pattern in (CSI_SHEET_RE, SHEET_RE):
        for match in pattern.finditer(text):
            if pattern is CSI_SHEET_RE:
                cand = normalize_sheet_number(f'{match.group(1)}-{match.group(2)}.{match.group(3)}')
            else:
                cand = normalize_sheet_number(f'{match.group(1)}-{match.group(2)}')
            if cand and is_plausible_drawing_sheet(cand):
                found.append((position_score, cand))
    m = TITLE_BLOCK_RE.search(text)
    if m:
        cand = normalize_sheet_number(m.group(1))
        if cand and is_plausible_drawing_sheet(cand):
            found.append((position_score + 0.1, cand))
    if len(compact) <= 12:
        cand = normalize_sheet_number(compact)
        if cand and is_plausible_drawing_sheet(cand):
            found.append((position_score + 0.05, cand))
    return found


def extract_title_block_metadata(pdf_path: str, page_index: int = 0) -> dict:
    """Spatial title-block analysis (sheet #, title, revision, date)."""
    try:
        from title_block_analyzer import analyze_title_block
        return analyze_title_block(pdf_path, page_index)
    except Exception:
        pass
    return {
        'sheet_number': None,
        'title': '',
        'revision': None,
        'drawing_date': None,
        'method': 'none',
        'text_preview': '',
    }


def ocr_title_block_regions(pdf_path: str, page_index: int = 0) -> str:
    """High-DPI OCR on common title-block regions."""
    try:
        from title_block_analyzer import ocr_title_block_fields
        fields = ocr_title_block_fields(pdf_path, page_index)
        return '\n'.join(filter(None, [
            fields.get('sheet_number', ''),
            fields.get('drawing_name', ''),
            fields.get('revision', ''),
            fields.get('full', ''),
        ]))
    except Exception:
        pass
    return ''


def resolve_drawing_file_path(file_path: str | None, upload_root: str | None = None) -> str | None:
    """Resolve a revision PDF path even if stored relatively or moved."""
    if not file_path:
        return None
    candidates = [file_path]
    if not os.path.isabs(file_path):
        candidates.append(os.path.abspath(file_path))
    if upload_root:
        candidates.append(os.path.join(upload_root, file_path))
        candidates.append(os.path.join(upload_root, 'drawings', file_path))
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path):
            return os.path.abspath(path)
    return None


def extract_drawing_date_from_text(text: str) -> date | None:
    if not text:
        return None
    for line in (text.splitlines() or [])[-50:]:
        m = DATE_RE.search(line)
        if m:
            parsed = _parse_date_token(m.group(1))
            if parsed:
                return parsed
    for line in reversed((text.splitlines() or [])[-20:]):
        m = DATE_FALLBACK_RE.search(line)
        if m:
            parsed = _parse_date_token(m.group(1))
            if parsed:
                return parsed
    return None


def _parse_date_token(token: str) -> date | None:
    if not token:
        return None
    for fmt in ('%m/%d/%Y', '%m-%d-%Y', '%m.%d.%Y', '%m/%d/%y', '%m-%d-%y', '%m.%d.%y'):
        try:
            return datetime.strptime(token.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _missing_pdf_libraries() -> list[str]:
    """Return requirement specifiers for PDF libraries that are not importable."""
    missing = []
    try:
        import fitz  # noqa: F401
    except ImportError:
        missing.append('pymupdf>=1.24.0')
    try:
        from pypdf import PdfReader  # noqa: F401
    except ImportError:
        missing.append('pypdf>=4.0.0')
    return missing


def ensure_drawing_dependencies() -> None:
    """Install PDF libraries needed for drawing set upload/split if they are missing."""
    missing = _missing_pdf_libraries()
    if not missing:
        return
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', *missing],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )
    except Exception as exc:
        pkgs = ' and '.join(missing)
        raise RuntimeError(
            f'PDF libraries ({pkgs}) are required for drawing uploads. '
            f'Run: {sys.executable} -m pip install -r requirements.txt'
        ) from exc
    still_missing = _missing_pdf_libraries()
    if still_missing:
        pkgs = ' and '.join(still_missing)
        raise RuntimeError(
            f'PDF libraries ({pkgs}) could not be loaded after install. '
            f'Run: {sys.executable} -m pip install -r requirements.txt'
        )


def extract_pdf_page_text(pdf_path: str, page_index: int = 0) -> str:
    """Extract embedded text from a PDF page (PyMuPDF first, then pypdf)."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_index < len(doc):
            text = doc[page_index].get_text('text') or doc[page_index].get_text() or ''
            doc.close()
            if text.strip():
                return text
        else:
            doc.close()
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        if page_index < len(reader.pages):
            return reader.pages[page_index].extract_text() or ''
    except Exception:
        pass
    return ''


def provisional_sheet_number(set_name: str, page_index: int, upload_stamp: str) -> str:
    slug = re.sub(r'[^A-Z0-9]', '', (set_name or 'SET').upper())[:8] or 'SET'
    stamp = re.sub(r'[^0-9]', '', upload_stamp or '')[-6:] or '000000'
    return f'UNASSIGNED-{slug}-{stamp}-P{page_index + 1:04d}'


def preserve_assigned_sheet_number(raw: str) -> str:
    """Normalize detected sheet numbers without stripping upload disambiguators.

    ``normalize_sheet_number('S-1-P002')`` incorrectly returns ``S-1`` because the
    regex matches the leading sheet token. That caused UNIQUE constraint failures when
    multiple pages in one upload were assigned distinct suffixes.
    """
    if not raw:
        return raw
    s = str(raw).strip().upper()
    if s.startswith('UNASSIGNED-'):
        return s
    if re.search(r'-P\d{3,4}$', s):
        return s
    m = re.match(r'^(.+)-(\d+)$', s)
    if m:
        base = normalize_sheet_number(m.group(1)) or m.group(1)
        suffix = m.group(2)
        if suffix.isdigit() and int(suffix) >= 2 and is_plausible_drawing_sheet(base):
            return f'{base}-{suffix}'
    normalized = normalize_sheet_number(s)
    return normalized or s


def ensure_unique_sheet_number(
    Drawing,
    project_id: int,
    sheet_number: str,
    reserved: set[str] | None = None,
    page_index: int | None = None,
) -> str:
    """Avoid unique-constraint collisions by suffixing -P002, -P003, etc.

  ``reserved`` tracks sheet numbers already assigned in the current upload batch
  (before they are flushed to the database).
  """
    taken = {str(s).upper() for s in (reserved or set())}
    base = sheet_number
    candidate = base
    n = 2

    def _is_taken(name: str) -> bool:
        key = preserve_assigned_sheet_number(name).upper()
        if key in taken:
            return True
        return Drawing.query.filter_by(project_id=int(project_id), sheet_number=key).first() is not None

    while _is_taken(candidate):
        if page_index is not None:
            candidate = f'{base}-P{page_index + n:03d}'
        else:
            candidate = f'{base}-P{n:03d}'
        n += 1
    return preserve_assigned_sheet_number(candidate)


def section_prefix(sheet_number: str) -> str:
    if not sheet_number:
        return 'OTHER'
    base = re.sub(r'-P\d{3,4}$', '', sheet_number, flags=re.I)
    m = re.match(r'^(.+)-(\d+)$', base)
    if m and m.group(2).isdigit() and int(m.group(2)) >= 2:
        base = m.group(1)
    return base.split('-')[0].upper()


def discipline_from_sheet(sheet_number: str) -> str:
    if not sheet_number:
        return 'General'
    prefix = section_prefix(sheet_number)
    return DISCIPLINE_MAP.get(prefix, 'General')


def sort_key_for_sheet(sheet_number: str) -> str:
    if not sheet_number:
        return 'ZZZZ-9999'
    base = re.sub(r'-P\d{3,4}$', '', sheet_number, flags=re.I)
    m = re.match(r'^(.+)-(\d+)$', base)
    if m and m.group(2).isdigit() and int(m.group(2)) >= 2:
        base = m.group(1)
    norm = normalize_sheet_number(base) or base
    parts = norm.split('-', 1)
    prefix = parts[0]
    num = parts[1] if len(parts) > 1 else '0'
    num_clean = re.sub(r'\D', '', num) or '0'
    return f'{prefix}-{int(num_clean):04d}'


def extract_sheet_from_filename(filename: str) -> str | None:
    base = os.path.splitext(os.path.basename(filename))[0]
    return normalize_sheet_number(base)


def extract_sheet_from_pdf_text(text: str) -> str | None:
    if not text:
        return None
    candidates = []
    m = TITLE_BLOCK_RE.search(text)
    if m:
        candidates.append(normalize_sheet_number(m.group(1)))
    lines = text.splitlines()
    for line in list(lines[:25]) + list(reversed(lines[-50:])):
        for match in CSI_SHEET_RE.finditer(line):
            cand = normalize_sheet_number(f'{match.group(1)}-{match.group(2)}.{match.group(3)}')
            if cand:
                candidates.append(cand)
        for match in SHEET_RE.finditer(line):
            cand = normalize_sheet_number(f'{match.group(1)}-{match.group(2)}')
            if cand:
                candidates.append(cand)
    for cand in candidates:
        if cand and is_plausible_drawing_sheet(cand):
            return cand
    return None


def ocr_extract_sheet_from_pdf(pdf_path: str, page_index: int = 0) -> tuple[str | None, str]:
    """Render title-block region with PyMuPDF and run Tesseract OCR when available."""
    ocr_text = ocr_title_block_regions(pdf_path, page_index)
    if ocr_text:
        sheet = extract_sheet_from_pdf_text(ocr_text)
        if sheet:
            return sheet, ocr_text
        layout = extract_title_block_metadata(pdf_path, page_index)
        if layout.get('sheet_number'):
            return layout['sheet_number'], ocr_text
    try:
        import fitz
    except ImportError:
        return None, ocr_text

    try:
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            return None, ocr_text
        page = doc[page_index]
        embedded = page.get_text() or ''
        sheet = extract_sheet_from_pdf_text(embedded)
        if sheet:
            doc.close()
            return sheet, embedded
        doc.close()
    except Exception:
        pass
    return extract_sheet_from_pdf_text(ocr_text), ocr_text


def detect_sheet_number(
    pdf_path: str,
    filename: str | None = None,
    page_text: str | None = None,
    page_index: int = 0,
    from_combined_set: bool = False,
    skip_ocr: bool = False,
) -> tuple[str | None, str, str, str | None]:
    """Returns (sheet_number, text, method, revision_from_sheet)."""
    if not page_text:
        page_text = extract_pdf_page_text(pdf_path, page_index)
    revision = extract_revision_from_text(page_text or '')
    if filename and not from_combined_set:
        sheet = extract_sheet_from_filename(filename)
        if sheet and is_plausible_drawing_sheet(sheet):
            return sheet, page_text or '', 'filename', revision
    if page_text:
        sheet = extract_sheet_from_pdf_text(page_text)
        if sheet:
            rev = revision or extract_revision_from_text(page_text)
            return sheet, page_text, 'pdf_text', rev
    if skip_ocr:
        return None, page_text or '', 'pdf_text', revision
    sheet, ocr_text = ocr_extract_sheet_from_pdf(pdf_path, page_index)
    combined_text = '\n'.join(filter(None, [page_text, ocr_text]))
    rev = revision or extract_revision_from_text(combined_text)
    if sheet and is_plausible_drawing_sheet(sheet):
        return sheet, combined_text or page_text or '', 'ocr', rev
    return None, combined_text or page_text or ocr_text or '', 'none', rev


def analyze_pdf_page_fast(
    pdf_path: str,
    page_index: int = 0,
    *,
    page_text: str | None = None,
    from_combined_set: bool = False,
    source_filename: str | None = None,
) -> dict:
    """Fast metadata extraction for large drawing sets — embedded PDF text only, no OCR."""
    text = page_text or extract_pdf_page_text(pdf_path, page_index)
    sheet, full_text, method, revision = detect_sheet_number(
        pdf_path,
        source_filename,
        text,
        page_index,
        from_combined_set=from_combined_set,
        skip_ocr=True,
    )
    title = extract_drawing_name_from_text(full_text or text or '', sheet) or ''
    drawing_date = extract_drawing_date_from_text(full_text or text or '')
    scale = extract_scale_from_text(full_text or text or '')
    return {
        'page_index': page_index,
        'sheet_number': sheet,
        'revision': revision,
        'title': title,
        'drawing_name': title,
        'project_number': None,
        'drawing_date': drawing_date,
        'scale': scale,
        'discipline': discipline_from_sheet(sheet) if sheet else None,
        'detection_method': method,
        'detection_confidence': {},
        'text_preview': (full_text or text or '')[:240],
    }


def analyze_pdf_page(
    pdf_path: str,
    page_index: int = 0,
    from_combined_set: bool = False,
    source_filename: str | None = None,
    *,
    set_upload: bool = False,
) -> dict:
    """Analyze one page for sheet metadata (used during set upload).

    When set_upload=True, prioritizes bottom-right title block grid/OCR and avoids
    redundant full-page OCR passes when sheet number and drawing name are found.
    """
    layout = extract_title_block_metadata(pdf_path, page_index)
    layout_conf = layout.get('confidence') or {}
    sheet_conf = float(layout_conf.get('sheet', 0) or 0)
    name_conf = float(layout_conf.get('name', 0) or 0)
    layout_trusted = (
        bool(layout.get('sheet_label_anchored'))
        or bool(layout.get('label_anchored'))
        or sheet_conf >= 3.0
        or name_conf >= 2.5
    )
    sheet_label_locked = bool(layout.get('sheet_label_anchored'))
    layout_title = (layout.get('drawing_name') or layout.get('title') or '').strip()
    layout_has_sheet = bool(layout.get('sheet_number') and is_plausible_drawing_sheet(layout['sheet_number']))
    layout_has_title = len(layout_title) >= 3
    layout_complete = layout_has_sheet and layout_has_title and (
        layout_trusted or sheet_label_locked or (sheet_conf >= 2.0 and name_conf >= 1.8)
    )

    text = extract_pdf_page_text(pdf_path, page_index)
    sheet, full_text, method, revision = detect_sheet_number(
        pdf_path,
        source_filename,
        text,
        page_index,
        from_combined_set=from_combined_set,
        skip_ocr=layout_complete or sheet_label_locked or (layout_has_sheet and sheet_conf >= 2.0),
    )

    if sheet_label_locked and layout.get('sheet_number'):
        sheet = layout['sheet_number']
        method = layout.get('method') or 'grid'
    elif layout.get('sheet_number'):
        if layout_trusted or not sheet or sheet_conf >= 1.2:
            sheet = layout['sheet_number']
            method = layout.get('method') or method

    if not sheet and not sheet_label_locked and not layout_complete:
        ocr_sheet, ocr_text = ocr_extract_sheet_from_pdf(pdf_path, page_index)
        if ocr_sheet:
            sheet = ocr_sheet
            method = 'ocr'
            full_text = '\n'.join(filter(None, [full_text, ocr_text]))

    if layout.get('revision'):
        revision = layout['revision']
    elif not revision:
        revision = extract_revision_from_text(full_text or text or layout.get('text_preview', ''))

    title = layout_title
    if sheet_label_locked:
        if not title:
            title = layout.get('title') or ''
    elif (not title or (name_conf < 2.0 and not layout_trusted)) and not layout_trusted:
        title = extract_drawing_name_from_text(full_text or text or '', sheet) or title
    drawing_date = layout.get('drawing_date') or extract_drawing_date_from_text(full_text or text or '')
    scale = layout.get('scale') or extract_scale_from_text(full_text or text or '')

    layout_has_sheet = bool(sheet and is_plausible_drawing_sheet(sheet))
    layout_has_title = bool(title and len(str(title).strip()) >= 3)
    skip_extra_ocr = set_upload and layout_has_sheet and layout_has_title and (
        layout_complete
        or sheet_label_locked
        or (sheet_conf >= 2.0 and name_conf >= 2.0)
    )

    if not skip_extra_ocr:
        ocr_text = ocr_title_block_regions(pdf_path, page_index)
        if ocr_text:
            full_text = '\n'.join(filter(None, [full_text, text, ocr_text]))
            ocr_lines = _plain_text_lines(ocr_text)
            if not revision:
                revision = _extract_revision_from_lines(ocr_lines, ocr_text) or extract_revision_from_text(ocr_text)
            if (not title or len(title) < 4) and not layout_trusted and not sheet_label_locked and name_conf < 2.0:
                ocr_title = _extract_drawing_title_from_lines(ocr_lines, sheet, ocr_text)
                if ocr_title:
                    title = ocr_title
            if not sheet and not sheet_label_locked:
                ocr_sheet = extract_sheet_from_pdf_text(ocr_text)
                if ocr_sheet and is_plausible_drawing_sheet(ocr_sheet):
                    sheet = ocr_sheet
                    method = 'ocr'
            if not scale:
                scale = extract_scale_from_text(full_text)
    project_number = layout.get('project_number')
    return {
        'page_index': page_index,
        'sheet_number': sheet,
        'revision': revision,
        'title': title,
        'drawing_name': title,
        'project_number': project_number,
        'drawing_date': drawing_date,
        'scale': scale,
        'discipline': discipline_from_sheet(sheet) if sheet else None,
        'detection_method': method,
        'detection_confidence': layout.get('confidence') or {},
        'text_preview': (full_text or text or layout.get('text_preview') or '')[:240],
    }


def collect_takeoff_items(DrawingMarkup, Drawing, project_id, drawing_id=None):
    """Gather measure/area takeoff markups for budget export."""
    q = db_query_markups(DrawingMarkup, Drawing, project_id, drawing_id)
    items = []
    for m, drawing in q:
        if m.markup_type not in ('measure', 'rect', 'cloud'):
            continue
        geom = _parse_json(m.geometry_json, {})
        val = m.measurement_value
        unit = m.measurement_unit or 'ft'
        label = m.label or m.markup_type
        if m.markup_type in ('rect', 'cloud') and geom.get('w') and geom.get('h') and not val:
            val = round((geom.get('w', 0) * geom.get('h', 0)) / 100, 2)
            unit = 'sq ft (scaled)'
        if val is None and m.markup_type == 'measure':
            continue
        items.append({
            'markup_id': m.id,
            'drawing_id': drawing.id,
            'sheet_number': drawing.sheet_number,
            'description': f'{drawing.sheet_number} — {label}',
            'quantity': val,
            'unit': unit,
            'markup_type': m.markup_type,
        })
    return items


def db_query_markups(DrawingMarkup, Drawing, project_id, drawing_id=None):
    q = DrawingMarkup.query.join(Drawing, DrawingMarkup.drawing_id == Drawing.id).filter(
        Drawing.project_id == int(project_id)
    )
    if drawing_id:
        q = q.filter(DrawingMarkup.drawing_id == int(drawing_id))
    return q.with_entities(DrawingMarkup, Drawing).all()


def export_takeoff_to_budget_state(existing_state, takeoff_items, cost_code='01-000', cost_type='Subcontract'):
    """Merge takeoff lines into budgetLines bundle."""
    state = dict(existing_state or {})
    lines = list(state.get('budgetLines') or [])
    audit = list(state.get('budgetAuditLog') or [])
    for item in takeoff_items:
        desc = item['description']
        qty = item.get('quantity') or 0
        unit = item.get('unit') or 'ft'
        note = f'Takeoff: {qty} {unit} from {item["sheet_number"]}'
        existing = next((l for l in lines if l.get('cost_code') == cost_code and note in (l.get('notes') or '')), None)
        if existing:
            continue
        lines.append({
            'id': int(datetime.utcnow().timestamp() * 1000) + item['markup_id'],
            'cost_code': cost_code,
            'description': desc[:120],
            'cost_type': cost_type,
            'original_budget': 0,
            'approved_changes': 0,
            'pending': 0,
            'notes': note,
            'actual': 0,
            'syncStatus': 'Not Synced',
            'percent_complete': 0,
            'takeoff_qty': qty,
            'takeoff_unit': unit,
            'takeoff_sheet': item['sheet_number'],
            'source': 'drawings_takeoff',
        })
        audit.append({
            'timestamp': datetime.utcnow().isoformat(),
            'action': 'TAKEOFF_IMPORTED',
            'details': {'sheet': item['sheet_number'], 'quantity': qty, 'unit': unit, 'description': desc},
        })
    state['budgetLines'] = lines
    state['budgetAuditLog'] = audit
    return state


def extract_drawing_name_from_text(text: str, sheet_number: str | None) -> str:
    """Last-resort drawing name — only scan title-block tail, never random page text."""
    if not text:
        return ''
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-40:] if len(lines) > 40 else lines
    pseudo = [{'y': float(i), 'x': 0.0, 'text': ln} for i, ln in enumerate(tail)]
    found = _extract_drawing_title_from_lines(pseudo, sheet_number, text)
    return found[:200] if found else ''


def extract_title_from_text(text: str, sheet_number: str | None) -> str:
    """Alias for drawing name extraction."""
    return extract_drawing_name_from_text(text, sheet_number)


def _count_pdf_pages_fitz(source_path: str) -> int:
    try:
        import fitz
        doc = fitz.open(source_path)
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return 0


def _count_pdf_pages_pypdf(source_path: str) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(source_path).pages)
    except Exception:
        return 0


def prepare_upload_pages(source_path: str, batch_dir: str) -> dict:
    """Split a PDF into individual page files for import (always attempts split).

    Returns {'pages': [...], 'expected_page_count': int, 'split_engine': str, 'warnings': [...]}.
    """
    ensure_drawing_dependencies()
    os.makedirs(batch_dir, exist_ok=True)
    fitz_count = _count_pdf_pages_fitz(source_path)
    pypdf_count = _count_pdf_pages_pypdf(source_path)
    expected_pages = max(fitz_count, pypdf_count, 1)
    warnings: list[str] = []
    split_engine = 'pymupdf'

    pages_fitz = split_pdf_to_pages(source_path, batch_dir) if fitz_count else []
    pages_pypdf = []
    if pypdf_count and (expected_pages > 1 and len(pages_fitz) < expected_pages or not pages_fitz):
        pages_pypdf = split_pdf_to_pages_pypdf(source_path, batch_dir)

    if len(pages_pypdf) > len(pages_fitz):
        pages = pages_pypdf
        split_engine = 'pypdf'
        if fitz_count and fitz_count < pypdf_count:
            warnings.append(
                f'PyMuPDF reported {fitz_count} pages but pypdf found {pypdf_count}; used pypdf split.'
            )
    else:
        pages = pages_fitz or pages_pypdf
        split_engine = 'pymupdf' if pages is pages_fitz and pages_fitz else 'pypdf'

    if expected_pages > 1 and len(pages) < expected_pages:
        warnings.append(
            f'Expected {expected_pages} pages but split produced {len(pages)} — some sheets may be missing.'
        )

    if not pages:
        text = extract_pdf_page_text(source_path, 0)
        pages = [{
            'page_index': 0,
            'file_path': source_path,
            'filename': os.path.basename(source_path),
            'text': text,
        }]
        split_engine = 'single'

    for page in pages:
        page['split_engine'] = split_engine

    return {
        'pages': pages,
        'expected_page_count': expected_pages,
        'split_engine': split_engine,
        'warnings': warnings,
    }


def count_pdf_pages(source_path: str) -> int:
    counts = []
    try:
        import fitz
        doc = fitz.open(source_path)
        counts.append(len(doc))
        doc.close()
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        counts.append(len(PdfReader(source_path).pages))
    except Exception:
        pass
    return max(counts) if counts else 1


def split_pdf_to_pages_pypdf(source_path: str, out_dir: str) -> list[dict]:
    """Split using pypdf only (fallback when PyMuPDF split under-counts pages)."""
    ensure_drawing_dependencies()
    os.makedirs(out_dir, exist_ok=True)
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise RuntimeError(
            f'pypdf is required for drawing set uploads. '
            f'Run: {sys.executable} -m pip install -r requirements.txt'
        ) from exc

    results = []
    reader = PdfReader(source_path)
    for idx, page in enumerate(reader.pages):
        writer = PdfWriter()
        writer.add_page(page)
        out_name = f'page_{idx + 1:04d}.pdf'
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, 'wb') as out_f:
            writer.write(out_f)
        try:
            text = page.extract_text() or ''
        except Exception:
            text = ''
        results.append({
            'page_index': idx,
            'file_path': out_path,
            'filename': out_name,
            'text': text,
        })
    return results


def split_pdf_to_pages(source_path: str, out_dir: str) -> list[dict]:
    """Split a PDF into single-page files. Returns metadata per page."""
    ensure_drawing_dependencies()
    os.makedirs(out_dir, exist_ok=True)
    results = []
    fitz_error = None

    try:
        import fitz
        doc = fitz.open(source_path)
        for idx in range(len(doc)):
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=idx, to_page=idx)
            out_name = f'page_{idx + 1:04d}.pdf'
            out_path = os.path.join(out_dir, out_name)
            new_doc.save(out_path)
            new_doc.close()
            text = doc[idx].get_text('text') or doc[idx].get_text() or ''
            results.append({
                'page_index': idx,
                'file_path': out_path,
                'filename': out_name,
                'text': text,
            })
        doc.close()
        if results:
            return results
    except Exception as exc:
        fitz_error = exc

    try:
        return split_pdf_to_pages_pypdf(source_path, out_dir)
    except Exception as exc:
        if fitz_error:
            raise RuntimeError(
                f'Could not split PDF with PyMuPDF ({fitz_error}) or pypdf ({exc}). '
                f'Run: {sys.executable} -m pip install -r requirements.txt'
            ) from exc
        raise


def next_revision_number(existing_revisions: list) -> str:
    if not existing_revisions:
        return '0'
    nums = []
    for rev in existing_revisions:
        label = str(getattr(rev, 'revision_number', '') or '0')
        if label.isdigit():
            nums.append(int(label))
        elif len(label) == 1 and label.isalpha():
            nums.append(ord(label.upper()) - ord('A'))
    n = max(nums) + 1 if nums else 1
    return str(n)


def revision_to_dict(rev):
    return {
        'id': rev.id,
        'drawing_id': rev.drawing_id,
        'revision_number': rev.revision_number,
        'revision_label': rev.revision_label,
        'drawing_date': _iso(rev.drawing_date),
        'received_date': _iso(rev.received_date),
        'set_name': rev.set_name,
        'file_path': rev.file_path,
        'original_filename': rev.original_filename,
        'is_current': bool(rev.is_current),
        'superseded_at': _iso(rev.superseded_at),
        'upload_source': rev.upload_source,
        'uploaded_at': _iso(rev.uploaded_at),
        'notes': rev.notes,
    }


def markup_to_dict(m):
    return {
        'id': m.id,
        'drawing_id': m.drawing_id,
        'revision_id': m.revision_id,
        'user_id': m.user_id,
        'user_name': m.user_name,
        'layer': m.layer,
        'markup_type': m.markup_type,
        'geometry': _parse_json(m.geometry_json, {}),
        'style': _parse_json(m.style_json, {}),
        'label': m.label,
        'linked_rfi_id': m.linked_rfi_id,
        'measurement_value': m.measurement_value,
        'measurement_unit': m.measurement_unit,
        'created_at': _iso(m.created_at),
        'published_at': _iso(m.published_at),
    }


def build_plan_pin_entry(drawing, markup_id, geom, label=None):
    pin_x = geom.get('anchorX', geom.get('x', 0))
    pin_y = geom.get('anchorY', geom.get('y', 0))
    return {
        'drawing_id': drawing.id,
        'drawing_sheet': drawing.sheet_number,
        'x': pin_x,
        'y': pin_y,
        'nx': geom.get('nanchorX', geom.get('nx')),
        'ny': geom.get('nanchorY', geom.get('ny')),
        'markup_id': markup_id,
        'note': label or '',
        'created_at': datetime.utcnow().isoformat(),
    }


def _append_plan_pin(record, attr, entry):
    pins = _parse_json(getattr(record, attr, None), [])
    markup_id = entry.get('markup_id')
    if markup_id is not None:
        pins = [p for p in pins if p.get('markup_id') != markup_id]
    pins.append(entry)
    setattr(record, attr, json.dumps(pins))


def _remove_plan_pin(record, attr, markup_id):
    pins = _parse_json(getattr(record, attr, None), [])
    filtered = [p for p in pins if p.get('markup_id') != markup_id]
    if len(filtered) == len(pins):
        return False
    setattr(record, attr, json.dumps(filtered))
    return True


def link_pin_markup(markup, drawing, geom, label, *, RFI, ChangeOrder, PunchItem):
    """Attach a drawing pin markup to its parent RFI / CO / punch list record."""
    if not markup or not drawing:
        return
    entry = build_plan_pin_entry(drawing, markup.id, geom or {}, label)
    mt = markup.markup_type
    if mt == 'rfi_pin' and markup.linked_rfi_id:
        rfi = RFI.query.get(markup.linked_rfi_id)
        if rfi:
            _append_plan_pin(rfi, 'plan_pins_json', entry)
            rfi.drawing_reference = drawing.sheet_number
    elif mt == 'co_pin':
        co_id = (geom or {}).get('linkedCoId')
        if co_id:
            co = ChangeOrder.query.get(int(co_id))
            if co:
                _append_plan_pin(co, 'plan_pins_json', entry)
    elif mt == 'punch_pin':
        punch_id = (geom or {}).get('linkedPunchId')
        if punch_id:
            item = PunchItem.query.get(int(punch_id))
            if item:
                _append_plan_pin(item, 'plan_pins_json', entry)


def unlink_pin_markup(markup, *, RFI, ChangeOrder, PunchItem):
    """Remove plan pin reference from parent record when markup is deleted."""
    if not markup:
        return
    geom = _parse_json(markup.geometry_json, {})
    markup_id = markup.id
    mt = markup.markup_type
    if mt == 'rfi_pin' and markup.linked_rfi_id:
        rfi = RFI.query.get(markup.linked_rfi_id)
        if rfi:
            _remove_plan_pin(rfi, 'plan_pins_json', markup_id)
    elif mt == 'co_pin':
        co_id = geom.get('linkedCoId')
        if co_id:
            co = ChangeOrder.query.get(int(co_id))
            if co:
                _remove_plan_pin(co, 'plan_pins_json', markup_id)
    elif mt == 'punch_pin':
        punch_id = geom.get('linkedPunchId')
        if punch_id:
            item = PunchItem.query.get(int(punch_id))
            if item:
                _remove_plan_pin(item, 'plan_pins_json', markup_id)


def parse_drawing_date(val):
    if val is None or val == '':
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    text = str(val).strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def update_drawing_metadata(db, Drawing, DrawingRevision, DrawingMarkup, drawing, data):
    """Update drawing sheet fields and current revision metadata."""
    rev = None
    if drawing.current_revision_id:
        rev = DrawingRevision.query.get(drawing.current_revision_id)
    if not rev:
        rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()

    if 'sheet_number' in data:
        raw = str(data.get('sheet_number') or '').strip()
        if raw:
            new_sheet = normalize_sheet_number(raw) or raw.upper()
            if new_sheet != drawing.sheet_number:
                conflict = Drawing.query.filter_by(
                    project_id=drawing.project_id,
                    sheet_number=new_sheet,
                ).filter(Drawing.id != drawing.id).first()
                if conflict:
                    raise ValueError(f'Sheet number {new_sheet} already exists on this project')
                drawing.sheet_number = new_sheet
                if 'section_prefix' not in data:
                    drawing.section_prefix = section_prefix(new_sheet)
                drawing.sort_key = sort_key_for_sheet(new_sheet)
                if 'discipline' not in data:
                    drawing.discipline = discipline_from_sheet(new_sheet)

    for field in ('title', 'discipline', 'section_prefix', 'status'):
        if field in data:
            val = data[field]
            setattr(drawing, field, (str(val).strip() if val not in (None, '') else None) if field != 'status' else (str(val).strip() or drawing.status))

    if rev:
        if 'revision_label' in data:
            label = str(data.get('revision_label') or '').strip()
            if label:
                rev.revision_label = label
        if 'revision_number' in data:
            num = str(data.get('revision_number') or '').strip()
            if num:
                rev.revision_number = num
        if 'set_name' in data:
            rev.set_name = str(data.get('set_name') or '').strip() or None
        if 'drawing_date' in data:
            rev.drawing_date = parse_drawing_date(data.get('drawing_date'))
        if 'received_date' in data:
            rev.received_date = parse_drawing_date(data.get('received_date'))

    drawing.updated_at = datetime.utcnow()
    rev_count = DrawingRevision.query.filter_by(drawing_id=drawing.id).count()
    markup_count = DrawingMarkup.query.filter_by(drawing_id=drawing.id).count()
    return drawing, rev, rev_count, markup_count


def drawing_to_dict(drawing, current_rev=None, revision_count=0, markup_count=0, linked_rfis=None):
    rev = current_rev
    upload_root = os.environ.get('CASEPM_UPLOAD_ROOT') or 'uploads'
    rev_path = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
    return {
        'id': drawing.id,
        'project_id': drawing.project_id,
        'sheet_number': drawing.sheet_number,
        'title': drawing.title,
        'discipline': drawing.discipline,
        'section_prefix': drawing.section_prefix or section_prefix(drawing.sheet_number),
        'status': drawing.status,
        'sort_key': drawing.sort_key or sort_key_for_sheet(drawing.sheet_number),
        'revision_number': rev.revision_number if rev else None,
        'revision_label': rev.revision_label if rev else None,
        'drawing_date': _iso(rev.drawing_date) if rev else None,
        'received_date': _iso(rev.received_date) if rev else None,
        'set_name': rev.set_name if rev else None,
        'current_revision_id': drawing.current_revision_id,
        'revision_count': revision_count,
        'markup_count': markup_count,
        'file_url': f'/api/drawings/{drawing.id}/file' if rev and rev_path else None,
        'has_thumbnail': bool(drawing.thumbnail_path and os.path.isfile(drawing.thumbnail_path)),
        'thumbnail_url': (
            f'/api/drawings/{drawing.id}/thumbnail'
            if drawing.thumbnail_path and os.path.isfile(drawing.thumbnail_path)
            else None
        ),
        'updated_at': _iso(drawing.updated_at),
        'linked_rfis': linked_rfis or [],
    }


def compute_drawing_dashboard(Drawing, DrawingRevision, project_id):
    drawings = Drawing.query.filter_by(project_id=project_id).all()
    current = [d for d in drawings if d.status == 'Current']
    sections = {}
    for d in drawings:
        sec = d.section_prefix or section_prefix(d.sheet_number)
        sections[sec] = sections.get(sec, 0) + 1
    rev_count = DrawingRevision.query.join(Drawing).filter(Drawing.project_id == project_id).count()
    return {
        'total_sheets': len(drawings),
        'current_sheets': len(current),
        'sections': sections,
        'section_count': len(sections),
        'total_revisions': rev_count,
        'for_review': sum(1 for d in drawings if d.status == 'For Review'),
        'superseded': sum(1 for d in drawings if d.status == 'Superseded'),
    }


def group_drawings_by_section(drawings_dicts):
    grouped = {}
    for d in drawings_dicts:
        sec = d.get('section_prefix') or 'OTHER'
        grouped.setdefault(sec, []).append(d)
    for sec in grouped:
        grouped[sec].sort(key=lambda x: x.get('sort_key') or x.get('sheet_number', ''))
    return dict(sorted(grouped.items(), key=lambda kv: kv[0]))


def inherit_markups_to_revision(db, DrawingMarkup, drawing_id, old_revision_id, new_revision_id):
    """Copy published markups (not sketches) to new revision."""
    if not old_revision_id:
        return
    markups = DrawingMarkup.query.filter_by(
        drawing_id=drawing_id,
        revision_id=old_revision_id,
        layer='published',
    ).all()
    for m in markups:
        if m.markup_type == 'sketch':
            continue
        clone = DrawingMarkup(
            drawing_id=drawing_id,
            revision_id=new_revision_id,
            user_id=m.user_id,
            user_name=m.user_name,
            layer=m.layer,
            markup_type=m.markup_type,
            geometry_json=m.geometry_json,
            style_json=m.style_json,
            label=m.label,
            linked_rfi_id=m.linked_rfi_id,
            measurement_value=m.measurement_value,
            measurement_unit=m.measurement_unit,
            published_at=m.published_at or datetime.utcnow(),
        )
        db.session.add(clone)


def upsert_drawing_from_upload(
    db,
    Drawing,
    DrawingRevision,
    DrawingMarkup,
    *,
    project_id,
    sheet_number,
    title,
    discipline,
    file_path,
    original_filename,
    set_name,
    drawing_date,
    received_date,
    upload_source,
    uploaded_by_id,
    notes='',
    sheet_revision=None,
    status='Current',
    force_new=False,
):
    """Create or revise a drawing sheet from an uploaded page."""
    sheet_number = preserve_assigned_sheet_number(sheet_number)
    if not sheet_number:
        raise ValueError('Could not determine sheet number')
    if file_path:
        file_path = resolve_drawing_file_path(file_path) or os.path.abspath(file_path)

    drawing = None if force_new else Drawing.query.filter_by(project_id=project_id, sheet_number=sheet_number).first()
    now = datetime.utcnow()
    old_rev = None
    sheet_status = status or 'Current'

    if not drawing:
        drawing = Drawing(
            project_id=project_id,
            sheet_number=sheet_number,
            title=title or f'Sheet {sheet_number}',
            discipline=discipline or discipline_from_sheet(sheet_number),
            section_prefix=section_prefix(sheet_number),
            sort_key=sort_key_for_sheet(sheet_number),
            status=sheet_status,
            created_at=now,
            updated_at=now,
        )
        db.session.add(drawing)
        flush_with_retry(db.session)
        rev_num = str(normalize_revision_number(sheet_revision) or sheet_revision or '0')
    else:
        old_rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
        if old_rev:
            old_rev.is_current = False
            old_rev.superseded_at = now
        if sheet_revision is not None:
            rev_num = str(normalize_revision_number(sheet_revision) or sheet_revision)
        else:
            rev_num = next_revision_number(
                DrawingRevision.query.filter_by(drawing_id=drawing.id).all()
            )
        drawing.title = title or drawing.title
        drawing.discipline = discipline or drawing.discipline
        drawing.status = sheet_status if sheet_status == 'For Review' else 'Current'
        drawing.updated_at = now

    rev_label = f'Rev {rev_num}'
    new_rev = DrawingRevision(
        drawing_id=drawing.id,
        revision_number=rev_num,
        revision_label=rev_label,
        drawing_date=drawing_date,
        received_date=received_date or date.today(),
        set_name=set_name,
        file_path=file_path,
        original_filename=original_filename,
        is_current=True,
        upload_source=upload_source,
        uploaded_by_id=uploaded_by_id,
        uploaded_at=now,
        notes=notes,
    )
    db.session.add(new_rev)
    flush_with_retry(db.session)
    drawing.current_revision_id = new_rev.id

    if old_rev:
        inherit_markups_to_revision(db, DrawingMarkup, drawing.id, old_rev.id, new_rev.id)

    return drawing, new_rev, old_rev


def process_pages_from_upload(
    db,
    Drawing,
    DrawingRevision,
    DrawingMarkup,
    *,
    project_id,
    pages,
    original_filename,
    set_name,
    uploaded_by_id,
    from_combined_set,
    upload_source,
    manual_sheet=None,
    manual_title=None,
    upload_stamp=None,
    fast_analysis=False,
    progress_callback=None,
):
    """Import one or more split PDF pages into the drawing register."""
    created = []
    needs_review = []
    stamp = upload_stamp or datetime.utcnow().strftime('%Y%m%d%H%M%S')
    batch_assigned: set[str] = set()
    batch_detected: set[str] = set()
    total_pages = len(pages)

    try:
        from title_block_analyzer import clear_title_block_ocr_cache
        clear_title_block_ocr_cache()
    except ImportError:
        clear_title_block_ocr_cache = None

    for page in pages:
        meta = analyze_pdf_page(
            page['file_path'],
            page_index=0,
            from_combined_set=from_combined_set,
            source_filename=None if from_combined_set else original_filename,
            set_upload=from_combined_set and not fast_analysis,
        ) if not fast_analysis else analyze_pdf_page_fast(
            page['file_path'],
            page_index=0,
            page_text=page.get('text'),
            from_combined_set=from_combined_set,
            source_filename=None if from_combined_set else original_filename,
        )
        detected_sheet = meta.get('sheet_number')
        if manual_sheet:
            sheet_number = normalize_sheet_number(manual_sheet) or manual_sheet
            sheet_status = 'Current'
        elif detected_sheet and is_plausible_drawing_sheet(detected_sheet):
            sheet_number = detected_sheet
            sheet_status = 'Current'
        else:
            sheet_number = provisional_sheet_number(set_name, page['page_index'], stamp)
            sheet_status = 'For Review'
            needs_review.append({
                'page': page['page_index'] + 1,
                'file': page.get('filename') or os.path.basename(page['file_path']),
                'assigned_sheet': sheet_number,
                'text_preview': meta.get('text_preview'),
                'detected_revision': meta.get('revision'),
                'detected_date': _iso(meta.get('drawing_date')),
                'detection_method': meta.get('detection_method'),
            })

        if from_combined_set:
            base_key = (normalize_sheet_number(sheet_number) or sheet_number or '').upper()
            if base_key and base_key in batch_detected:
                sheet_number = ensure_unique_sheet_number(
                    Drawing, project_id, sheet_number, reserved=batch_assigned,
                    page_index=page['page_index'],
                )
            if base_key:
                batch_detected.add(base_key)

        sheet_number = preserve_assigned_sheet_number(sheet_number)
        reserved_key = sheet_number.upper()
        existing = Drawing.query.filter_by(project_id=int(project_id), sheet_number=sheet_number).first()
        force_new_for_page = from_combined_set

        if reserved_key in batch_assigned:
            sheet_number = ensure_unique_sheet_number(
                Drawing, project_id, sheet_number, reserved=batch_assigned,
                page_index=page['page_index'],
            )
            sheet_number = preserve_assigned_sheet_number(sheet_number)
            force_new_for_page = True
        elif existing:
            # Sheet already on project — add a revision instead of inserting a duplicate row
            force_new_for_page = False
        else:
            sheet_number = ensure_unique_sheet_number(
                Drawing, project_id, sheet_number, reserved=batch_assigned,
                page_index=page['page_index'],
            )
            sheet_number = preserve_assigned_sheet_number(sheet_number)

        batch_assigned.add(sheet_number.upper())

        page_text = page.get('text') or meta.get('text_preview') or ''
        title = manual_title or meta.get('drawing_name') or meta.get('title') or extract_drawing_name_from_text(page_text, sheet_number)
        if sheet_status == 'For Review' and not title:
            title = f'Page {page["page_index"] + 1} — assign sheet number'
        page_notes = ''
        if from_combined_set:
            page_notes = f'Page {page["page_index"] + 1} of {original_filename}'
        if meta.get('project_number'):
            page_notes = f'{page_notes} · Project No. {meta["project_number"]}'.strip(' ·')

        drawing, rev, _old = None, None, None
        for _upsert_attempt in range(4):
            try:
                drawing, rev, _old = upsert_drawing_from_upload(
                    db, Drawing, DrawingRevision, DrawingMarkup,
                    project_id=int(project_id),
                    sheet_number=sheet_number,
                    title=title,
                    discipline=meta.get('discipline') or discipline_from_sheet(sheet_number),
                    file_path=page['file_path'],
                    original_filename=original_filename,
                    set_name=set_name,
                    drawing_date=meta.get('drawing_date'),
                    received_date=date.today(),
                    upload_source=upload_source,
                    uploaded_by_id=uploaded_by_id,
                    notes=page_notes,
                    sheet_revision=meta.get('revision'),
                    status=sheet_status,
                    force_new=force_new_for_page,
                )
                break
            except IntegrityError:
                db.session.rollback()
                sheet_number = ensure_unique_sheet_number(
                    Drawing, project_id, sheet_number, reserved=batch_assigned,
                    page_index=page['page_index'],
                )
                sheet_number = preserve_assigned_sheet_number(sheet_number)
                force_new_for_page = True
                batch_assigned.add(sheet_number.upper())
        if drawing is None or rev is None:
            raise ValueError(f'Could not assign a unique sheet number for page {page["page_index"] + 1}')
        created.append({
            'id': drawing.id,
            'sheet_number': drawing.sheet_number,
            'title': drawing.title,
            'revision_label': rev.revision_label,
            'revision_number': rev.revision_number,
            'drawing_date': _iso(meta.get('drawing_date')),
            'discipline': drawing.discipline,
            'page': page['page_index'] + 1,
            'detection_method': meta.get('detection_method'),
            'project_number': meta.get('project_number'),
            'detection_confidence': meta.get('detection_confidence'),
            'needs_review': sheet_status == 'For Review',
            'status': drawing.status,
        })
        # Commit each sheet immediately for multi-page sets so OCR between pages
        # does not hold a SQLite write lock open for the entire batch.
        if from_combined_set:
            commit_with_retry(db.session)
        elif len(created) % 25 == 0:
            flush_with_retry(db.session)

        if progress_callback:
            progress_callback(len(created), total_pages, page['page_index'] + 1)

    if clear_title_block_ocr_cache:
        clear_title_block_ocr_cache()

    return created, needs_review


def current_revision_for_drawing(DrawingRevision, drawing):
    rev = DrawingRevision.query.get(drawing.current_revision_id) if drawing.current_revision_id else None
    if not rev:
        rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
    return rev


def drawing_set_name(rev) -> str:
    return (rev.set_name if rev else None) or 'Unnamed Set'


def drawings_by_set_name(db, Drawing, DrawingRevision, project_id, set_name):
    """Return drawings whose current revision belongs to the given set name."""
    target = (set_name or '').strip() or 'Unnamed Set'
    matches = []
    for drawing in Drawing.query.filter_by(project_id=int(project_id)).order_by(Drawing.sheet_number).all():
        rev = current_revision_for_drawing(DrawingRevision, drawing)
        if drawing_set_name(rev) == target:
            matches.append(drawing)
    return matches


def delete_drawings_by_set_name(db, Drawing, DrawingRevision, DrawingMarkup, project_id, set_name, upload_root=None, *, RFI=None, ChangeOrder=None, PunchItem=None):
    """Delete every sheet whose current revision belongs to the given drawing set name."""
    target = (set_name or '').strip() or 'Unnamed Set'
    drawings = drawings_by_set_name(db, Drawing, DrawingRevision, project_id, target)
    deleted_ids = []
    for drawing in drawings:
        delete_drawing_record(
            db, Drawing, DrawingRevision, DrawingMarkup, drawing, upload_root=upload_root,
            RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
        )
        deleted_ids.append(drawing.id)
    return deleted_ids


def delete_drawings_bulk(db, Drawing, DrawingRevision, DrawingMarkup, project_id, drawing_ids, upload_root=None, *, RFI=None, ChangeOrder=None, PunchItem=None):
    """Delete multiple drawing sheets by id."""
    deleted_ids = []
    for drawing_id in drawing_ids:
        drawing = Drawing.query.filter_by(id=int(drawing_id), project_id=int(project_id)).first()
        if not drawing:
            continue
        delete_drawing_record(
            db, Drawing, DrawingRevision, DrawingMarkup, drawing, upload_root=upload_root,
            RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
        )
        deleted_ids.append(drawing.id)
    return deleted_ids


def delete_drawing_record(db, Drawing, DrawingRevision, DrawingMarkup, drawing, upload_root=None, *, RFI=None, ChangeOrder=None, PunchItem=None):
    """Remove drawing, revisions, markups, and page files from disk."""
    drawing_id = drawing.id
    revisions = DrawingRevision.query.filter_by(drawing_id=drawing_id).all()
    paths = set()
    for rev in revisions:
        if rev.file_path:
            resolved = resolve_drawing_file_path(rev.file_path, upload_root)
            paths.add(resolved or rev.file_path)
    if drawing.thumbnail_path:
        thumb = resolve_drawing_file_path(drawing.thumbnail_path, upload_root)
        paths.add(thumb or drawing.thumbnail_path)
    dirs = set()
    for p in paths:
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
            dirs.add(os.path.dirname(p))
    pin_markups = DrawingMarkup.query.filter(
        DrawingMarkup.drawing_id == drawing_id,
        DrawingMarkup.markup_type.in_(('rfi_pin', 'co_pin', 'punch_pin')),
    ).all()
    if pin_markups and RFI and ChangeOrder and PunchItem:
        for m in pin_markups:
            unlink_pin_markup(m, RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem)
    DrawingMarkup.query.filter_by(drawing_id=drawing_id).delete(synchronize_session=False)
    drawing.current_revision_id = None
    db.session.flush()
    DrawingRevision.query.filter_by(drawing_id=drawing_id).delete(synchronize_session=False)
    db.session.delete(drawing)
    for d in dirs:
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass

