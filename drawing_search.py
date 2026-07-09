"""Drawing text and visual shape search across PDF sheets."""
from __future__ import annotations

import base64
import io
import re
from typing import Any

from PIL import Image

from drawing_persistence import resolve_drawing_file_path


class DrawingSearchError(Exception):
    """User-visible search failure (missing deps, bad input, etc.)."""


def _np():
    try:
        import numpy as np
    except ImportError as exc:
        raise DrawingSearchError(
            'Drawing search requires numpy. Run: pip install -r requirements.txt'
        ) from exc
    return np


def _pixmap_to_gray_array(pix):
    """Convert a PyMuPDF grayscale pixmap to a 2-D uint8 array."""
    np = _np()
    samples = np.frombuffer(pix.samples, dtype=np.uint8)
    row_bytes = pix.stride or pix.width
    if row_bytes * pix.height != len(samples):
        if pix.width * pix.height == len(samples):
            return samples.reshape(pix.height, pix.width)
        raise DrawingSearchError('Could not decode PDF page image for search')
    arr = samples.reshape(pix.height, row_bytes)
    if row_bytes != pix.width:
        arr = arr[:, :pix.width].copy()
    return arr


def _render_page_gray(pdf_path: str, page_index: int = 0, dpi: int = 120):
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if page_index >= len(doc):
            return None, 0, 0
        page = doc[page_index]
        pw, ph = page.rect.width, page.rect.height
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        arr = _pixmap_to_gray_array(pix)
        return arr, pw, ph
    finally:
        doc.close()


def _thumb_b64(gray, x: int, y: int, w: int, h: int, max_size: int = 96) -> str:
    h_img, w_img = gray.shape[:2]
    x0 = max(0, min(x, w_img - 1))
    y0 = max(0, min(y, h_img - 1))
    x1 = max(x0 + 1, min(x + w, w_img))
    y1 = max(y0 + 1, min(y + h, h_img))
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        return ''
    pil = Image.fromarray(crop)
    pil.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    pil.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


def extract_page_text_lines(pdf_path: str, page_index: int = 0) -> list[dict[str, Any]]:
    """Return text lines with normalized bounding boxes (0–1)."""
    import fitz

    lines_out: list[dict[str, Any]] = []
    try:
        doc = fitz.open(pdf_path)
        try:
            if page_index >= len(doc):
                return lines_out
            page = doc[page_index]
            pw, ph = page.rect.width, page.rect.height
            if pw <= 0 or ph <= 0:
                return lines_out
            data = page.get_text('dict') or {}
            for block in data.get('blocks', []):
                if block.get('type') != 0:
                    continue
                for line in block.get('lines', []):
                    parts = [s.get('text', '') for s in line.get('spans', [])]
                    text = ''.join(parts).strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = line.get('bbox', (0, 0, 0, 0))
                    lines_out.append({
                        'text': text,
                        'nx': float(x0 / pw),
                        'ny': float(y0 / ph),
                        'nw': float(max(0.001, (x1 - x0) / pw)),
                        'nh': float(max(0.001, (y1 - y0) / ph)),
                    })
        finally:
            doc.close()
    except Exception:
        pass

    if len(lines_out) < 2:
        try:
            gray, _pw_pts, _ph_pts = _render_page_gray(pdf_path, page_index, dpi=150)
            if gray is not None:
                import pytesseract

                pil = Image.fromarray(gray)
                ocr = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT)
                h, w = gray.shape[:2]
                by_line: dict[tuple[int, int, int], list[str]] = {}
                boxes: dict[tuple[int, int, int], list[int]] = {}
                n = len(ocr.get('text', []))
                for i in range(n):
                    txt = (ocr['text'][i] or '').strip()
                    if not txt:
                        continue
                    key = (ocr['block_num'][i], ocr['par_num'][i], ocr['line_num'][i])
                    by_line.setdefault(key, []).append(txt)
                    x, y, bw, bh = ocr['left'][i], ocr['top'][i], ocr['width'][i], ocr['height'][i]
                    boxes.setdefault(key, [x, y, x + bw, y + bh])
                    b = boxes[key]
                    b[0] = min(b[0], x)
                    b[1] = min(b[1], y)
                    b[2] = max(b[2], x + bw)
                    b[3] = max(b[3], y + bh)
                for key, words in by_line.items():
                    text = ' '.join(words).strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = boxes[key]
                    lines_out.append({
                        'text': text,
                        'nx': float(x0 / w),
                        'ny': float(y0 / h),
                        'nw': float(max(0.001, (x1 - x0) / w)),
                        'nh': float(max(0.001, (y1 - y0) / h)),
                    })
        except Exception:
            pass
    return lines_out


def search_text(
    drawings: list,
    query: str,
    upload_root: str | None = None,
    max_results: int = 200,
) -> list[dict[str, Any]]:
    q = (query or '').strip()
    if len(q) < 2:
        return []
    q_lower = q.lower()
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    results: list[dict[str, Any]] = []
    for d in drawings:
        rev = d.get('_rev')
        path = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
        if not path:
            continue
        try:
            lines = extract_page_text_lines(path, 0)
        except Exception:
            continue
        for line in lines:
            if q_lower not in line['text'].lower() and not pattern.search(line['text']):
                continue
            snippet = line['text']
            m = pattern.search(snippet)
            if m:
                start = max(0, m.start() - 24)
                end = min(len(snippet), m.end() + 24)
                snippet = snippet[start:end]
                if start > 0:
                    snippet = '…' + snippet
                if end < len(line['text']):
                    snippet = snippet + '…'
            results.append({
                'drawing_id': d['id'],
                'sheet_number': d.get('sheet_number'),
                'title': d.get('title'),
                'line_text': line['text'],
                'snippet': snippet,
                'nx': line['nx'],
                'ny': line['ny'],
                'nw': line['nw'],
                'nh': line['nh'],
                'page': 0,
            })
            if len(results) >= max_results:
                return results
    return results


def _decode_template(template_b64: str):
    np = _np()
    raw = base64.b64decode(template_b64.split(',')[-1] if ',' in template_b64 else template_b64)
    pil = Image.open(io.BytesIO(raw)).convert('L')
    return np.array(pil, dtype=np.uint8)


def _interior_mask(h: int, w: int, margin_ratio: float = 0.1):
    np = _np()
    mask = np.ones((h, w), dtype=np.uint8) * 255
    margin = max(2, int(min(h, w) * margin_ratio))
    mask[:margin, :] = 0
    mask[-margin:, :] = 0
    mask[:, :margin] = 0
    mask[:, -margin:] = 0
    return mask


def _match_template(gray, template, threshold: float = 0.82):
    """Find template matches; prefers cv2 when available."""
    np = _np()
    th, tw = template.shape[:2]
    gh, gw = gray.shape[:2]
    if th < 8 or tw < 8 or th >= gh or tw >= gw:
        return []

    mask = _interior_mask(th, tw, margin_ratio=0.12)
    try:
        import cv2

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED, mask=mask)
        loc = np.where(result >= threshold)
        matches = []
        for y, x in zip(*loc):
            score = float(result[y, x])
            matches.append((x, y, score))
        matches.sort(key=lambda m: m[2], reverse=True)
        filtered = []
        min_dist = max(th, tw) * 0.55
        for x, y, score in matches:
            if any(abs(x - fx) < min_dist and abs(y - fy) < min_dist for fx, fy, _ in filtered):
                continue
            filtered.append((x, y, score))
            if len(filtered) >= 24:
                break
        return filtered
    except Exception:
        pass

    # Numpy fallback — downsample for speed
    scale = 0.5 if max(gh, gw) > 2000 else 1.0
    g = gray
    t = template
    if scale != 1.0:
        g = np.array(Image.fromarray(gray).resize(
            (int(gw * scale), int(gh * scale)), Image.Resampling.BILINEAR))
        t = np.array(Image.fromarray(template).resize(
            (int(tw * scale), int(th * scale)), Image.Resampling.BILINEAR))
    th, tw = t.shape[:2]
    gh, gw = g.shape[:2]
    if th >= gh or tw >= gw:
        return []
    t_f = t.astype(np.float32)
    t_f -= t_f.mean()
    denom = float(np.sqrt(np.sum(t_f * t_f)) or 1.0)
    matches = []
    step = max(2, int(min(th, tw) / 4))
    for y in range(0, gh - th, step):
        for x in range(0, gw - tw, step):
            patch = g[y:y + th, x:x + tw].astype(np.float32)
            patch -= patch.mean()
            num = np.sum(patch * t_f)
            den = float(np.sqrt(np.sum(patch * patch)) * denom)
            score = float(num / den) if den else 0.0
            if score >= threshold:
                matches.append((int(x / scale), int(y / scale), score))
    matches.sort(key=lambda m: m[2], reverse=True)
    filtered = []
    min_dist = max(th, tw) * 0.55 / scale
    for x, y, score in matches:
        if any(abs(x - fx) < min_dist and abs(y - fy) < min_dist for fx, fy, _ in filtered):
            continue
        filtered.append((x, y, score))
        if len(filtered) >= 16:
            break
    return filtered


def search_shape(
    drawings: list,
    template_b64: str,
    upload_root: str | None = None,
    threshold: float = 0.82,
    max_results: int = 120,
    max_sheets: int = 80,
) -> list[dict[str, Any]]:
    try:
        template = _decode_template(template_b64)
    except Exception as exc:
        raise DrawingSearchError('Invalid shape template image') from exc
    th, tw = template.shape[:2]
    if th < 6 or tw < 6:
        return []

    results: list[dict[str, Any]] = []
    for d in drawings[:max_sheets]:
        rev = d.get('_rev')
        path = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
        if not path:
            continue
        try:
            gray, _pw_pts, _ph_pts = _render_page_gray(path, 0, dpi=120)
        except Exception:
            continue
        if gray is None:
            continue
        gh, gw = gray.shape[:2]
        try:
            hits = _match_template(gray, template, threshold=threshold)
        except Exception:
            continue
        for x, y, score in hits:
            nx = float(x / gw)
            ny = float(y / gh)
            nw = float(tw / gw)
            nh = float(th / gh)
            thumb = _thumb_b64(gray, x, y, tw, th)
            results.append({
                'drawing_id': d['id'],
                'sheet_number': d.get('sheet_number'),
                'title': d.get('title'),
                'nx': nx,
                'ny': ny,
                'nw': nw,
                'nh': nh,
                'score': round(score, 3),
                'page': 0,
                'thumb': thumb,
            })
            if len(results) >= max_results:
                return sorted(results, key=lambda r: r['score'], reverse=True)
    return sorted(results, key=lambda r: r['score'], reverse=True)


def prepare_drawing_targets(Drawing, DrawingRevision, drawing_ids: list[int] | None, project_id: int):
    """Build list of dicts with attached revision for search."""
    q = Drawing.query.filter_by(project_id=int(project_id))
    if drawing_ids:
        q = q.filter(Drawing.id.in_(drawing_ids))
    out = []
    for drawing in q.order_by(Drawing.sort_key, Drawing.sheet_number).all():
        rev = None
        if drawing.current_revision_id:
            rev = DrawingRevision.query.get(drawing.current_revision_id)
        if not rev:
            rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
        if not rev:
            rev = DrawingRevision.query.filter_by(drawing_id=drawing.id).order_by(
                DrawingRevision.uploaded_at.desc()
            ).first()
        out.append({
            'id': drawing.id,
            'sheet_number': drawing.sheet_number,
            'title': drawing.title,
            '_rev': rev,
        })
    return out
