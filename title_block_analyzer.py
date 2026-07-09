"""Advanced title-block analysis for construction drawing PDFs.

Uses spatial layout, label-value pairing, multi-region OCR, and consensus voting
to extract sheet number, drawing name, and revision from title blocks.
"""
from __future__ import annotations

import io
import re
from typing import Any

from drawing_persistence import (
    ARCH_SCALE_RE,
    CSI_SHEET_RE,
    DATE_FALLBACK_RE,
    DATE_RE,
    DRAWING_NAME_INLINE_RE,
    DRAWING_NAME_LABEL_RE,
    LABEL_ONLY_RE,
    PROJECT_LABEL_RE,
    RATIO_SCALE_RE,
    REV_ISSUE_RE,
    REV_NO_RE,
    REVISION_LOOSE_RE,
    REVISION_RE,
    SHEET_LABEL_RE,
    SHEET_NO_LABEL_RE,
    SHEET_RE,
    TITLE_BLOCK_RE,
    TITLE_HINT_RE,
    extract_drawing_date_from_text,
    extract_revision_from_text,
    extract_scale_from_text,
    is_plausible_drawing_sheet,
    normalize_sheet_number,
)

# Dedicated title-block field labels
SHEET_LABEL_PATTERNS = (
    re.compile(r'^(?:SHEET|SHT|SH\.?)\s*(?:NO\.?|NUM(?:BER)?|#)\s*[:#.]?\s*(.*)$', re.I),
    re.compile(r'^(?:DWG|DRAWING)\s*(?:NO\.?|NUM(?:BER)?|#)\s*[:#.]?\s*(.*)$', re.I),
    re.compile(r'^SHEET\s*[:#]\s*(.*)$', re.I),
)
DRAWING_NAME_LABEL_PATTERNS = (
    re.compile(r'^(?:DRAWING\s*NAME|DRAWING\s*TITLE|SHEET\s*NAME|SHEET\s*TITLE)\s*[:#.]?\s*(.*)$', re.I),
)
REV_LABEL_PATTERNS = (
    re.compile(r'^(?:REV(?:ISION)?\.?|REVISION)\s*(?:NO\.?|NUM(?:BER)?|#)?\s*[:#.]?\s*(.*)$', re.I),
    re.compile(r'^(?:CURRENT|LATEST|ISSUE)\s*(?:REV(?:ISION)?)?\.?\s*[:#.]?\s*(.*)$', re.I),
)

OCR_PSM_MODES = ('--psm 6', '--psm 7', '--psm 11', '--psm 12')
OCR_MATRIX = 4.5


def _score_title_block_position(x0: float, y0: float, page_w: float, page_h: float) -> float:
    if page_w <= 0 or page_h <= 0:
        return 0.0
    return (x0 / page_w) * 0.55 + (y0 / page_h) * 0.45


def _is_label_only_line(text: str) -> bool:
    if not text:
        return True
    t = text.strip()
    if LABEL_ONLY_RE.match(t):
        return True
    if DRAWING_NAME_LABEL_RE.fullmatch(t):
        return True
    if SHEET_NO_LABEL_RE.match(t) and not _sheet_candidates_from_text(t, 0.5):
        return True
    return False


def _sheet_candidates_from_text(text: str, position_score: float = 0.5) -> list[tuple[float, str]]:
    found: list[tuple[float, str]] = []
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
    if len(compact) <= 14:
        cand = normalize_sheet_number(compact)
        if cand and is_plausible_drawing_sheet(cand):
            found.append((position_score + 0.08, cand))
    return found


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


def _build_title_block_lines(words: list, page_h: float, min_y_ratio: float = 0.52) -> list[dict]:
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


def _plain_text_lines(text: str) -> list[dict]:
    lines = []
    for i, raw in enumerate((text or '').splitlines()):
        line = raw.strip()
        if line:
            lines.append({'y': float(i), 'x': 0.0, 'text': line})
    return lines


def _title_block_clips(page_w: float, page_h: float) -> dict[str, Any]:
    """Named regions for sheet #, drawing name, revision, and full block."""
    import fitz
    return {
        'sheet_number': [
            fitz.Rect(page_w * 0.68, page_h * 0.82, page_w * 0.99, page_h * 0.97),
            fitz.Rect(page_w * 0.62, page_h * 0.78, page_w * 0.99, page_h * 0.95),
            fitz.Rect(page_w * 0.55, page_h * 0.72, page_w, page_h),
        ],
        'drawing_name': [
            fitz.Rect(page_w * 0.52, page_h * 0.70, page_w * 0.99, page_h * 0.84),
            fitz.Rect(page_w * 0.48, page_h * 0.62, page_w * 0.99, page_h * 0.78),
            fitz.Rect(page_w * 0.35, page_h * 0.68, page_w, page_h * 0.86),
        ],
        'revision': [
            fitz.Rect(page_w * 0.72, page_h * 0.58, page_w * 0.99, page_h * 0.78),
            fitz.Rect(page_w * 0.65, page_h * 0.55, page_w, page_h * 0.72),
            fitz.Rect(page_w * 0.5, page_h * 0.55, page_w, page_h * 0.68),
        ],
        'full_block': [
            fitz.Rect(page_w * 0.45, page_h * 0.55, page_w, page_h),
            fitz.Rect(0, page_h * 0.65, page_w, page_h),
            fitz.Rect(page_w * 0.3, page_h * 0.55, page_w, page_h),
        ],
    }


def _ocr_clip(page, clip, psm_modes: tuple[str, ...] = OCR_PSM_MODES) -> str:
    try:
        from PIL import Image
        import pytesseract
        import fitz
    except ImportError:
        return ''
    chunks = []
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(OCR_MATRIX, OCR_MATRIX), clip=clip, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes('png')))
        for psm in psm_modes:
            try:
                chunk = pytesseract.image_to_string(img, config=psm) or ''
                if chunk.strip():
                    chunks.append(chunk)
            except Exception:
                continue
    except Exception:
        pass
    return '\n'.join(chunks)


def ocr_title_block_fields(pdf_path: str, page_index: int = 0) -> dict[str, str]:
    """Run targeted OCR on sheet-number, drawing-name, and revision regions."""
    result = {'sheet_number': '', 'drawing_name': '', 'revision': '', 'full': ''}
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            doc.close()
            return result
        page = doc[page_index]
        rect = page.rect
        clips = _title_block_clips(rect.width, rect.height)
        for field, regions in clips.items():
            parts = []
            for clip in regions:
                text = _ocr_clip(page, clip)
                if text.strip():
                    parts.append(text)
            result[field if field != 'full_block' else 'full'] = '\n'.join(parts)
        doc.close()
    except Exception:
        pass
    return result


def _extract_labeled_value(lines: list[dict], label_patterns: tuple, validator=None) -> str | None:
    """Pair label lines with adjacent values (same line tail or next line)."""
    for i, ln in enumerate(lines):
        text = ln['text'].strip()
        for pat in label_patterns:
            m = pat.match(text)
            if not m:
                continue
            tail = (m.group(1) or '').strip()
            if tail and (validator is None or validator(tail)):
                return tail
            if i + 1 < len(lines):
                nxt = lines[i + 1]['text'].strip()
                if nxt and (validator is None or validator(nxt)):
                    return nxt
            if i > 0:
                prev = lines[i - 1]['text'].strip()
                if prev and (validator is None or validator(prev)):
                    return prev
    return None


def _find_sheet_line_index(lines: list[dict], sheet_number: str | None) -> int | None:
    if not sheet_number:
        return None
    sheet_key = sheet_number.replace('-', '').replace('.', '').replace(' ', '').upper()
    for i, ln in enumerate(lines):
        text = ln['text'].strip()
        compact = text.replace('-', '').replace(' ', '').replace('.', '').upper()
        if sheet_key and sheet_key in compact:
            return i
        for _score, cand in _sheet_candidates_from_text(text, 0.85):
            if cand == sheet_number:
                return i
    return None


def _extract_drawing_name_from_lines(lines: list[dict], sheet_number: str | None) -> str:
    if not lines:
        return ''

    labeled = _extract_labeled_value(
        lines, DRAWING_NAME_LABEL_PATTERNS,
        validator=lambda t: _is_plausible_drawing_title(t, sheet_number),
    )
    if labeled:
        return labeled[:200]

    for ln in lines:
        m = DRAWING_NAME_INLINE_RE.match(ln['text'].strip())
        if m and _is_plausible_drawing_title(m.group(1).strip(), sheet_number):
            return m.group(1).strip()[:200]

    sheet_idx = _find_sheet_line_index(lines, sheet_number)
    if sheet_idx is not None and sheet_idx > 0:
        for j in range(sheet_idx - 1, max(-1, sheet_idx - 4), -1):
            candidate = lines[j]['text'].strip()
            if _is_plausible_drawing_title(candidate, sheet_number):
                return candidate[:200]

    # Right-column title block: longest plausible line above sheet row
    if sheet_idx is not None:
        best = ''
        for j in range(0, sheet_idx):
            candidate = lines[j]['text'].strip()
            if _is_plausible_drawing_title(candidate, sheet_number) and len(candidate) > len(best):
                best = candidate
        if best:
            return best[:200]
    return ''


def _extract_sheet_number_from_lines(lines: list[dict], page_w: float = 0, page_h: float = 0) -> str | None:
    labeled = _extract_labeled_value(
        lines, SHEET_LABEL_PATTERNS,
        validator=lambda t: bool(_sheet_candidates_from_text(t, 0.95)),
    )
    if labeled:
        for _score, cand in _sheet_candidates_from_text(labeled, 1.0):
            return cand

    candidates: list[tuple[float, str]] = []
    for i, ln in enumerate(lines):
        text = ln['text'].strip()
        m = SHEET_NO_LABEL_RE.search(text)
        if m:
            tail = m.group(1).strip()
            for score, cand in _sheet_candidates_from_text(tail, 0.95):
                candidates.append((score + 0.25, cand))
            for score, cand in _sheet_candidates_from_text(text, 0.9):
                candidates.append((score, cand))
        if DRAWING_NAME_LABEL_RE.search(text):
            continue
        pos = _score_title_block_position(ln.get('x', 0), ln.get('y', 0), page_w or 1000, page_h or 1000)
        for score, cand in _sheet_candidates_from_text(text, pos + 0.1):
            bonus = 0.3 if page_h and ln.get('y', 0) >= page_h * 0.72 else 0.0
            candidates.append((score + bonus, cand))
        if i + 1 < len(lines):
            nxt = lines[i + 1]['text'].strip()
            if SHEET_NO_LABEL_RE.search(text) or re.search(r'^(SHEET|DWG|DRAWING)\s*NO', text, re.I):
                for score, cand in _sheet_candidates_from_text(nxt, 0.94):
                    candidates.append((score + 0.2, cand))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _parse_revision_token(raw: str) -> str | None:
    if not raw:
        return None
    token = raw.strip().strip(':.#').upper()
    if re.fullmatch(r'\d{1,3}', token):
        return token
    if re.fullmatch(r'[A-Z]', token):
        return token
    return None


def _extract_revision_from_lines(lines: list[dict], embedded: str = '') -> str | None:
    scored: list[tuple[float, str]] = []

    labeled = _extract_labeled_value(lines, REV_LABEL_PATTERNS, validator=_parse_revision_token)
    if labeled:
        tok = _parse_revision_token(labeled)
        if tok:
            scored.append((1.2, tok))

    for ln in lines:
        text = ln['text']
        pos = ln.get('y', 0)
        for pattern in (REV_NO_RE, REVISION_RE, REVISION_LOOSE_RE, REV_ISSUE_RE):
            m = pattern.search(text)
            if m:
                tok = _parse_revision_token(str(m.group(1)))
                if tok:
                    scored.append((0.9 + pos * 0.0001, tok))
        parts = text.upper().split()
        for i, part in enumerate(parts):
            if part in ('REV', 'REV.', 'REVISION', 'REVISION:') and i + 1 < len(parts):
                tok = _parse_revision_token(parts[i + 1])
                if tok:
                    scored.append((0.85, tok))

    # Revision table: collect standalone rev tokens on bottom title-block rows
    rev_tokens = []
    for ln in lines[-12:]:
        for part in re.split(r'[\s|/]+', ln['text']):
            tok = _parse_revision_token(part)
            if tok:
                rev_tokens.append(tok)
    if rev_tokens:
        numeric = [int(t) for t in rev_tokens if t.isdigit()]
        if numeric:
            scored.append((1.05, str(max(numeric))))
        else:
            scored.append((0.95, rev_tokens[-1]))

    for line in reversed((embedded or '').splitlines()[-60:]):
        for pattern in (REV_NO_RE, REVISION_RE, REVISION_LOOSE_RE, REV_ISSUE_RE):
            m = pattern.search(line)
            if m:
                tok = _parse_revision_token(str(m.group(1)))
                if tok:
                    scored.append((0.7, tok))

    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]


def _score_word_as_sheet(word: str, x0: float, y0: float, page_w: float, page_h: float) -> list[tuple[float, str]]:
    in_tb = y0 >= page_h * 0.62 or (x0 >= page_w * 0.48 and y0 >= page_h * 0.5)
    if not in_tb:
        return []
    pos = _score_title_block_position(x0, y0, page_w, page_h)
    return _sheet_candidates_from_text(word, pos)


def _vote_sheet_number(sources: list[tuple[float, str | None]]) -> tuple[str | None, str]:
    votes: dict[str, float] = {}
    best_method = 'none'
    for weight, sheet in sources:
        if sheet and is_plausible_drawing_sheet(sheet):
            votes[sheet] = votes.get(sheet, 0.0) + weight
    if not votes:
        return None, 'none'
    winner = max(votes.items(), key=lambda kv: kv[1])
    if winner[1] >= 1.0:
        best_method = 'layout'
    elif winner[1] >= 0.75:
        best_method = 'ocr'
    else:
        best_method = 'heuristic'
    return winner[0], best_method


def _vote_drawing_name(sources: list[tuple[float, str]]) -> str:
    votes: dict[str, float] = {}
    for weight, name in sources:
        n = (name or '').strip()
        if len(n) >= 3:
            votes[n] = votes.get(n, 0.0) + weight
    if not votes:
        return ''
    return max(votes.items(), key=lambda kv: (kv[1], len(kv[0])))[0][:200]


def _vote_revision(sources: list[tuple[float, str | None]]) -> str | None:
    votes: dict[str, float] = {}
    for weight, rev in sources:
        if rev:
            votes[str(rev).upper()] = votes.get(str(rev).upper(), 0.0) + weight
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]


def analyze_title_block(pdf_path: str, page_index: int = 0) -> dict:
    """Full title-block analysis with layout + multi-region OCR consensus."""
    result: dict[str, Any] = {
        'sheet_number': None,
        'drawing_name': '',
        'title': '',
        'revision': None,
        'drawing_date': None,
        'scale': None,
        'method': 'none',
        'text_preview': '',
        'confidence': {},
    }

    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_index >= len(doc):
            doc.close()
            return result
        page = doc[page_index]
        rect = page.rect
        page_w, page_h = rect.width, rect.height
        embedded = page.get_text('text') or page.get_text() or ''
        words = page.get_text('words') or []
        tb_lines = _build_title_block_lines(words, page_h)
        doc.close()
    except Exception:
        return result

    sheet_sources: list[tuple[float, str | None]] = []
    name_sources: list[tuple[float, str]] = []
    rev_sources: list[tuple[float, str | None]] = []

    # Layout-based sheet detection
    sheet_scores: list[tuple[float, str]] = []
    for item in words:
        if len(item) < 5:
            continue
        x0, y0, word = float(item[0]), float(item[1]), str(item[4]).strip()
        if word:
            sheet_scores.extend(_score_word_as_sheet(word, x0, y0, page_w, page_h))

    by_line: dict[tuple, list] = {}
    for item in words:
        if len(item) < 8:
            continue
        x0, y0, blk, ln, word = float(item[0]), float(item[1]), int(item[5]), int(item[6]), str(item[4])
        if y0 < page_h * 0.58:
            continue
        by_line.setdefault((blk, ln), []).append((x0, word))
    for parts in by_line.values():
        parts.sort(key=lambda p: p[0])
        joined = ' '.join(p[1] for p in parts)
        pos = _score_title_block_position(parts[0][0], page_h * 0.85, page_w, page_h)
        sheet_scores.extend(_sheet_candidates_from_text(joined, pos + 0.18))

    labeled_sheet = _extract_sheet_number_from_lines(tb_lines, page_w, page_h)
    if labeled_sheet:
        sheet_sources.append((1.15, labeled_sheet))
    for score, cand in sheet_scores:
        sheet_sources.append((score, cand))

    layout_name = _extract_drawing_name_from_lines(tb_lines, labeled_sheet)
    if layout_name:
        name_sources.append((1.1, layout_name))

    layout_rev = _extract_revision_from_lines(tb_lines, embedded)
    if layout_rev:
        rev_sources.append((1.0, layout_rev))

    # Targeted OCR per field
    ocr_fields = ocr_title_block_fields(pdf_path, page_index)
    merged_text = '\n'.join(filter(None, [embedded, ocr_fields.get('full', '')]))

    for field_key, weight in (('sheet_number', 1.05), ('drawing_name', 1.08), ('revision', 1.02)):
        ocr_text = ocr_fields.get(field_key, '')
        if not ocr_text:
            continue
        ocr_lines = _plain_text_lines(ocr_text)
        if field_key == 'sheet_number':
            ocr_sheet = _extract_sheet_number_from_lines(ocr_lines, page_w, page_h)
            if not ocr_sheet:
                for line in ocr_lines:
                    for score, cand in _sheet_candidates_from_text(line['text'], 0.88):
                        if cand:
                            ocr_sheet = cand
                            break
            if ocr_sheet:
                sheet_sources.append((weight, ocr_sheet))
        elif field_key == 'drawing_name':
            ocr_name = _extract_drawing_name_from_lines(ocr_lines, labeled_sheet)
            if ocr_name:
                name_sources.append((weight, ocr_name))
        else:
            ocr_rev = _extract_revision_from_lines(ocr_lines, ocr_text)
            if ocr_rev:
                rev_sources.append((weight, ocr_rev))

    # Embedded text tail — only title-block lines, never full-page body
    for ln in tb_lines:
        for score, cand in _sheet_candidates_from_text(ln['text'], 0.75):
            sheet_sources.append((score * 0.6, cand))

    sheet, method = _vote_sheet_number(sheet_sources)
    if not sheet:
        for line in list(embedded.splitlines()[:20]) + list(reversed(embedded.splitlines()[-40:])):
            for score, cand in _sheet_candidates_from_text(line, 0.55):
                sheet_sources.append((score * 0.5, cand))
        sheet, method = _vote_sheet_number(sheet_sources)

    if sheet:
        # Re-run name extraction with final sheet number
        layout_name = _extract_drawing_name_from_lines(tb_lines, sheet)
        if layout_name:
            name_sources.append((1.12, layout_name))
        for field_key in ('drawing_name', 'full'):
            ocr_text = ocr_fields.get(field_key, '')
            if ocr_text:
                ocr_name = _extract_drawing_name_from_lines(_plain_text_lines(ocr_text), sheet)
                if ocr_name:
                    name_sources.append((1.06 if field_key == 'drawing_name' else 0.9, ocr_name))

    drawing_name = _vote_drawing_name(name_sources)
    revision = _vote_revision(rev_sources)
    if not revision:
        revision = extract_revision_from_text(merged_text)

    result['sheet_number'] = sheet
    result['drawing_name'] = drawing_name
    result['title'] = drawing_name
    result['revision'] = revision
    result['method'] = method
    result['drawing_date'] = extract_drawing_date_from_text(merged_text)
    result['scale'] = extract_scale_from_text(merged_text)
    result['text_preview'] = merged_text[:400]
    result['confidence'] = {
        'sheet': round(max((w for w, s in sheet_sources if s == sheet), default=0), 2) if sheet else 0,
        'name': round(max((w for w, n in name_sources if n == drawing_name), default=0), 2) if drawing_name else 0,
        'revision': round(max((w for w, r in rev_sources if r == revision), default=0), 2) if revision else 0,
    }
    return result
