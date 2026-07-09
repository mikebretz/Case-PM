"""Drawing text and visual shape search across PDF sheets."""
from __future__ import annotations

import array
import base64
import io
import math
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from PIL import Image

from drawing_persistence import resolve_drawing_file_path


class DrawingSearchError(Exception):
    """User-visible search failure (missing deps, bad input, etc.)."""


REFINE_DPI = 120
COARSE_DPI = 52
MAX_REFINE_SHEETS = 40
COARSE_THRESHOLD_PAD = 0.14
COARSE_MAX_SIDE = 560
REFINE_MAX_SIDE = 1680
MAX_TEMPLATE_SIDE = 180


_NP = None
_NP_TRIED = False


def _numpy():
    """Return numpy module when installed; otherwise None."""
    global _NP, _NP_TRIED
    if _NP_TRIED:
        return _NP
    _NP_TRIED = True
    try:
        import numpy as np
        _NP = np
    except ImportError:
        _NP = None
    return _NP


def _pixmap_to_pil(pix) -> Image.Image:
    """Convert a PyMuPDF pixmap to a grayscale PIL image (handles stride safely)."""
    return Image.open(io.BytesIO(pix.tobytes('png'))).convert('L')


def _render_page_image(pdf_path: str, page_index: int = 0, dpi: int = 120):
    """Render a PDF page as a grayscale PIL image."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if page_index >= len(doc):
            return None, 0, 0
        page = doc[page_index]
        pw, ph = page.rect.width, page.rect.height
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        return _pixmap_to_pil(pix), pw, ph
    finally:
        doc.close()


def _cached_page_render(path: str, dpi: int, cache: dict, numpy_mode: bool, cache_lock: threading.Lock | None = None):
    """Render or reuse a cached page image for the current search request."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    key = (path, dpi, mtime, numpy_mode)
    if cache_lock:
        with cache_lock:
            if key in cache:
                return cache[key]
    elif key in cache:
        return cache[key]
    if numpy_mode:
        gray, pw, ph = _render_page_gray(path, 0, dpi=dpi)
        if gray is None:
            rendered = (None, 0, 0, None, True)
        else:
            gh, gw = gray.shape[:2]
            rendered = (gray, gw, gh, gray, False)
    else:
        sheet_pil, pw, ph = _render_page_image(path, 0, dpi=dpi)
        if sheet_pil is None:
            rendered = (None, 0, 0, None, True)
        else:
            gw, gh = sheet_pil.size
            rendered = (sheet_pil, gw, gh, sheet_pil, True)
    if cache_lock:
        with cache_lock:
            cache[key] = rendered
    else:
        cache[key] = rendered
    return rendered


def _render_page_gray(pdf_path: str, page_index: int = 0, dpi: int = 120):
    """Render a PDF page as a numpy grayscale array (requires numpy)."""
    np = _numpy()
    if np is None:
        return None, 0, 0
    import fitz

    doc = fitz.open(pdf_path)
    try:
        if page_index >= len(doc):
            return None, 0, 0
        page = doc[page_index]
        pw, ph = page.rect.width, page.rect.height
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        samples = np.frombuffer(pix.samples, dtype=np.uint8)
        row_bytes = pix.stride or pix.width
        if row_bytes * pix.height == len(samples):
            arr = samples.reshape(pix.height, row_bytes)
            if row_bytes != pix.width:
                arr = arr[:, :pix.width].copy()
        elif pix.width * pix.height == len(samples):
            arr = samples.reshape(pix.height, pix.width)
        else:
            arr = np.array(_pixmap_to_pil(pix), dtype=np.uint8)
        return arr, pw, ph
    finally:
        doc.close()


def _thumb_from_pil(img: Image.Image, x: int, y: int, w: int, h: int, max_size: int = 96) -> str:
    iw, ih = img.size
    x0 = max(0, min(x, iw - 1))
    y0 = max(0, min(y, ih - 1))
    x1 = max(x0 + 1, min(x + w, iw))
    y1 = max(y0 + 1, min(y + h, ih))
    crop = img.crop((x0, y0, x1, y1))
    if crop.width == 0 or crop.height == 0:
        return ''
    crop.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    crop.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


def _thumb_b64(gray, x: int, y: int, w: int, h: int, max_size: int = 96) -> str:
    np = _numpy()
    if np is not None and hasattr(gray, 'shape'):
        h_img, w_img = gray.shape[:2]
        x0 = max(0, min(x, w_img - 1))
        y0 = max(0, min(y, h_img - 1))
        x1 = max(x0 + 1, min(x + w, w_img))
        y1 = max(y0 + 1, min(y + h, h_img))
        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            return ''
        pil = Image.fromarray(crop)
    else:
        pil = gray
        return _thumb_from_pil(pil, x, y, w, h, max_size)
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
            page_img, _pw_pts, _ph_pts = _render_page_image(pdf_path, page_index, dpi=150)
            if page_img is not None:
                import pytesseract

                ocr = pytesseract.image_to_data(page_img, output_type=pytesseract.Output.DICT)
                w, h = page_img.size
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


def _decode_template_pil(template_b64: str) -> Image.Image:
    raw = base64.b64decode(template_b64.split(',')[-1] if ',' in template_b64 else template_b64)
    return Image.open(io.BytesIO(raw)).convert('L')


def _decode_template_array(template_b64: str):
    np = _numpy()
    if np is None:
        return None
    return np.array(_decode_template_pil(template_b64), dtype=np.uint8)


def _normalize_template(
    template_pil: Image.Image,
    render_scale: float | None = None,
    snip_w: float | None = None,
    snip_h: float | None = None,
    refine_dpi: int = REFINE_DPI,
) -> Image.Image:
    """Scale a canvas snip to the pixel size expected at refine DPI."""
    tw, th = template_pil.size
    if render_scale and render_scale > 0:
        if snip_w and snip_h and snip_w >= 4 and snip_h >= 4:
            target_w = max(6, int(round(snip_w * refine_dpi / 72.0 / render_scale)))
            target_h = max(6, int(round(snip_h * refine_dpi / 72.0 / render_scale)))
        else:
            ratio = (refine_dpi / 72.0) / render_scale
            target_w = max(6, int(round(tw * ratio)))
            target_h = max(6, int(round(th * ratio)))
        if abs(target_w - tw) > 1 or abs(target_h - th) > 1:
            template_pil = template_pil.resize((target_w, target_h), Image.Resampling.LANCZOS)
    max_side = max(template_pil.size)
    if max_side > MAX_TEMPLATE_SIDE:
        scale = MAX_TEMPLATE_SIDE / max_side
        template_pil = template_pil.resize(
            (max(6, int(template_pil.width * scale)), max(6, int(template_pil.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return template_pil


def _pil_to_gray_array(img: Image.Image):
    np = _numpy()
    if np is None:
        return None
    return np.array(img, dtype=np.uint8)


def _resize_gray(gray, max_side: int):
    np = _numpy()
    if np is None:
        return gray, 1.0
    gh, gw = gray.shape[:2]
    if max(gh, gw) <= max_side:
        return gray, 1.0
    scale = max_side / max(gh, gw)
    import cv2
    resized = cv2.resize(
        gray,
        (max(1, int(gw * scale)), max(1, int(gh * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _interior_mask(h: int, w: int, margin_ratio: float = 0.1):
    np = _numpy()
    mask = np.ones((h, w), dtype=np.uint8) * 255
    margin = max(2, int(min(h, w) * margin_ratio))
    mask[:margin, :] = 0
    mask[-margin:, :] = 0
    mask[:, :margin] = 0
    mask[:, -margin:] = 0
    return mask


def _match_template_cv(gray, template, threshold: float = 0.82):
    """OpenCV template match when available."""
    np = _numpy()
    if np is None:
        return None
    th, tw = template.shape[:2]
    gh, gw = gray.shape[:2]
    if th < 8 or tw < 8 or th >= gh or tw >= gw:
        return []

    inv_scale = 1.0
    gray, scale = _resize_gray(gray, REFINE_MAX_SIDE)
    if scale != 1.0:
        import cv2
        template = cv2.resize(
            template,
            (max(1, int(tw * scale)), max(1, int(th * scale))),
            interpolation=cv2.INTER_AREA,
        )
        inv_scale = 1.0 / scale
        th, tw = template.shape[:2]
        gh, gw = gray.shape[:2]
        if th >= gh or tw >= gw:
            return []

    mask = _interior_mask(th, tw, margin_ratio=0.12)
    try:
        import cv2

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED, mask=mask)
        loc = np.where(result >= threshold)
        matches = []
        for y, x in zip(*loc):
            score = float(result[y, x])
            matches.append((int(x * inv_scale), int(y * inv_scale), score))
        matches.sort(key=lambda m: m[2], reverse=True)
        filtered = []
        min_dist = max(th, tw) * 0.55 * inv_scale
        for x, y, score in matches:
            if any(abs(x - fx) < min_dist and abs(y - fy) < min_dist for fx, fy, _ in filtered):
                continue
            filtered.append((x, y, score))
            if len(filtered) >= 24:
                break
        return filtered
    except Exception:
        return None


def _coarse_peak_score_cv(gray, template) -> float:
    """Fast best-score probe for coarse screening (no hit enumeration)."""
    np = _numpy()
    if np is None:
        return 0.0
    th, tw = template.shape[:2]
    gh, gw = gray.shape[:2]
    if th < 6 or tw < 6 or th >= gh or tw >= gw:
        return 0.0
    gray, scale = _resize_gray(gray, COARSE_MAX_SIDE)
    if scale != 1.0:
        import cv2
        template = cv2.resize(
            template,
            (max(1, int(tw * scale)), max(1, int(th * scale))),
            interpolation=cv2.INTER_AREA,
        )
        th, tw = template.shape[:2]
        gh, gw = gray.shape[:2]
        if th >= gh or tw >= gw:
            return 0.0
    try:
        import cv2
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        return float(cv2.minMaxLoc(result)[1])
    except Exception:
        return 0.0


def _coarse_peak_score_pil(sheet: Image.Image, template: Image.Image) -> float:
    sw, sh = sheet.size
    tw, th = template.size
    if th < 6 or tw < 6 or th >= sh or tw >= sw:
        return 0.0
    max_side = COARSE_MAX_SIDE
    inv_scale = 1.0
    if max(sw, sh) > max_side:
        scale = max_side / max(sw, sh)
        inv_scale = 1.0 / scale
        sheet = sheet.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.Resampling.BILINEAR)
        template = template.resize((max(1, int(tw * scale)), max(1, int(th * scale))), Image.Resampling.BILINEAR)
        sw, sh = sheet.size
        tw, th = template.size
    sheet_data = array.array('B', sheet.tobytes())
    tmpl_data = array.array('B', template.tobytes())
    n = tw * th
    t_mean = sum(tmpl_data) / n
    t_centered = array.array('f', (0.0,) * n)
    t_norm = 0.0
    for i in range(n):
        d = tmpl_data[i] - t_mean
        t_centered[i] = d
        t_norm += d * d
    t_norm = math.sqrt(t_norm) or 1.0
    margin = max(1, int(min(tw, th) * 0.08))
    inner_w = tw - 2 * margin
    inner_h = th - 2 * margin
    if inner_w < 4 or inner_h < 4:
        margin = 0
        inner_w, inner_h = tw, th
    inner_n = inner_w * inner_h
    step = max(3, min(tw, th) // 5)
    best = -1.0
    for y in range(0, sh - th, step):
        for x in range(0, sw - tw, step):
            score = _ncc_score_at(
                sheet_data, sw, t_centered, t_norm, tw, th, x, y,
                margin, inner_w, inner_h, inner_n,
            )
            if score > best:
                best = score
    return float(best)


def _match_template_numpy(gray, template, threshold: float = 0.82):
    np = _numpy()
    if np is None:
        return None
    th, tw = template.shape[:2]
    gh, gw = gray.shape[:2]
    if th < 8 or tw < 8 or th >= gh or tw >= gw:
        return []

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


def _ncc_score_at(
    sheet_data: array.array,
    sw: int,
    t_centered: array.array,
    t_norm: float,
    tw: int,
    th: int,
    x: int,
    y: int,
    margin: int,
    inner_w: int,
    inner_h: int,
    inner_n: int,
) -> float:
    base_y = y * sw
    patch_centered = array.array('f', (0.0,) * inner_n)
    idx = 0
    s_sum = 0.0
    for dy in range(margin, th - margin if margin else th):
        row = base_y + dy * sw + x + margin
        for dx in range(inner_w):
            sv = sheet_data[row + dx]
            s_sum += sv
            patch_centered[idx] = sv
            idx += 1
    s_mean = s_sum / inner_n
    s_norm = 0.0
    for i in range(inner_n):
        d = patch_centered[i] - s_mean
        patch_centered[i] = d
        s_norm += d * d
    s_norm = math.sqrt(s_norm) or 1.0
    cross = 0.0
    for dy in range(inner_h):
        for dx in range(inner_w):
            cross += patch_centered[dy * inner_w + dx] * t_centered[(dy + margin) * tw + (dx + margin)]
    return cross / (s_norm * t_norm)


def _match_template_pil(sheet: Image.Image, template: Image.Image, threshold: float = 0.82):
    """Pure-PIL normalized cross-correlation (no numpy/opencv required)."""
    sw, sh = sheet.size
    tw, th = template.size
    if th < 8 or tw < 8 or th >= sh or tw >= sw:
        return []

    inv_scale = 1.0
    max_side = 2400
    if max(sw, sh) > max_side:
        scale = max_side / max(sw, sh)
        inv_scale = 1.0 / scale
        sheet = sheet.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.Resampling.BILINEAR)
        template = template.resize((max(1, int(tw * scale)), max(1, int(th * scale))), Image.Resampling.BILINEAR)
        sw, sh = sheet.size
        tw, th = template.size
        if th < 8 or tw < 8 or th >= sh or tw >= sw:
            return []

    sheet_data = array.array('B', sheet.tobytes())
    tmpl_data = array.array('B', template.tobytes())
    n = tw * th
    t_mean = sum(tmpl_data) / n
    t_centered = array.array('f', (0.0,) * n)
    t_norm = 0.0
    for i in range(n):
        d = tmpl_data[i] - t_mean
        t_centered[i] = d
        t_norm += d * d
    t_norm = math.sqrt(t_norm) or 1.0

    margin = max(2, int(min(tw, th) * 0.12))
    inner_w = tw - 2 * margin
    inner_h = th - 2 * margin
    if inner_w < 4 or inner_h < 4:
        margin = 0
        inner_w, inner_h = tw, th
    inner_n = inner_w * inner_h

    step = max(2, min(tw, th) // 8)
    rough: list[tuple[int, int, float]] = []
    best_score = -1.0
    best_xy = (0, 0)
    for y in range(0, sh - th, step):
        for x in range(0, sw - tw, step):
            score = _ncc_score_at(
                sheet_data, sw, t_centered, t_norm, tw, th, x, y,
                margin, inner_w, inner_h, inner_n,
            )
            if score > best_score:
                best_score = score
                best_xy = (x, y)
            if score >= threshold:
                rough.append((x, y, float(score)))

    refine_radius = max(step, 12)
    seeds: list[tuple[int, int, float]] = list(rough[:8])
    if not any(s[0] == best_xy[0] and s[1] == best_xy[1] for s in seeds):
        seeds.insert(0, (best_xy[0], best_xy[1], best_score))
    matches: list[tuple[int, int, float]] = []
    seen_seed: set[tuple[int, int]] = set()
    for sx, sy, _ in seeds:
        if (sx, sy) in seen_seed:
            continue
        seen_seed.add((sx, sy))
        for y in range(max(0, sy - refine_radius), min(sh - th, sy + refine_radius) + 1, 2):
            for x in range(max(0, sx - refine_radius), min(sw - tw, sx + refine_radius) + 1, 2):
                score = _ncc_score_at(
                    sheet_data, sw, t_centered, t_norm, tw, th, x, y,
                    margin, inner_w, inner_h, inner_n,
                )
                if score >= threshold:
                    ox = int(x * inv_scale)
                    oy = int(y * inv_scale)
                    matches.append((ox, oy, float(score)))

    matches.sort(key=lambda m: m[2], reverse=True)
    filtered = []
    min_dist = max(int(tw * inv_scale), int(th * inv_scale)) * 0.55
    for x, y, score in matches:
        if any(abs(x - fx) < min_dist and abs(y - fy) < min_dist for fx, fy, _ in filtered):
            continue
        filtered.append((x, y, score))
        if len(filtered) >= 16:
            break
    return filtered


def _match_template(gray, template, threshold: float = 0.82):
    hits = _match_template_cv(gray, template, threshold)
    if hits is not None:
        return hits
    hits = _match_template_numpy(gray, template, threshold)
    if hits is not None:
        return hits
    return []


def _coarse_screen_sheet(
    drawing: dict,
    path: str,
    template_pil: Image.Image,
    template_arr,
    coarse_template_pil: Image.Image,
    coarse_template_arr,
    use_numpy: bool,
    cache: dict,
    cache_lock: threading.Lock | None,
) -> tuple[dict, str, float]:
    rendered, _gw, _gh, _thumb_src, _thumb_is_pil = _cached_page_render(
        path, COARSE_DPI, cache, use_numpy, cache_lock,
    )
    if rendered is None:
        return drawing, path, 0.0
    try:
        if use_numpy:
            score = _coarse_peak_score_cv(rendered, coarse_template_arr)
        else:
            score = _coarse_peak_score_pil(rendered, coarse_template_pil)
    except Exception:
        score = 0.0
    return drawing, path, score


def _search_shape_on_sheet(
    drawing: dict,
    path: str,
    template_pil: Image.Image,
    template_arr,
    tw: int,
    th: int,
    threshold: float,
    use_numpy: bool,
    dpi: int,
    cache: dict,
    cache_lock: threading.Lock | None = None,
) -> list[dict[str, Any]]:
    """Search one sheet; safe to run in a worker thread."""
    rendered, gw, gh, thumb_src, thumb_is_pil = _cached_page_render(
        path, dpi, cache, use_numpy, cache_lock,
    )
    if rendered is None or not gw or not gh:
        return []
    try:
        if use_numpy:
            hits = _match_template(rendered, template_arr, threshold=threshold)
        else:
            hits = _match_template_pil(rendered, template_pil, threshold=threshold)
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for x, y, score in hits:
        if thumb_is_pil:
            thumb = _thumb_from_pil(thumb_src, x, y, tw, th)
        else:
            thumb = _thumb_b64(thumb_src, x, y, tw, th)
        out.append({
            'drawing_id': drawing['id'],
            'sheet_number': drawing.get('sheet_number'),
            'title': drawing.get('title'),
            'nx': float(x / gw),
            'ny': float(y / gh),
            'nw': float(tw / gw),
            'nh': float(th / gh),
            'score': round(score, 3),
            'page': 0,
            'thumb': thumb,
        })
    return out


def search_shape(
    drawings: list,
    template_b64: str,
    upload_root: str | None = None,
    threshold: float = 0.82,
    max_results: int = 120,
    max_sheets: int = 80,
    render_scale: float | None = None,
    snip_w: float | None = None,
    snip_h: float | None = None,
) -> list[dict[str, Any]]:
    try:
        template_pil = _decode_template_pil(template_b64)
    except Exception as exc:
        raise DrawingSearchError('Invalid shape template — snip a box on the sheet and try again') from exc
    template_pil = _normalize_template(template_pil, render_scale, snip_w, snip_h, REFINE_DPI)
    tw, th = template_pil.size
    if th < 6 or tw < 6:
        return []

    template_arr = _pil_to_gray_array(template_pil)
    use_numpy = template_arr is not None
    render_cache: dict = {}
    cache_lock = threading.Lock()

    coarse_ratio = COARSE_DPI / REFINE_DPI
    coarse_w = max(6, int(round(tw * coarse_ratio)))
    coarse_h = max(6, int(round(th * coarse_ratio)))
    coarse_template_pil = template_pil.resize((coarse_w, coarse_h), Image.Resampling.BILINEAR)
    coarse_template_arr = _pil_to_gray_array(coarse_template_pil) if use_numpy else None

    jobs: list[tuple[dict, str]] = []
    for d in drawings[:max_sheets]:
        rev = d.get('_rev')
        path = resolve_drawing_file_path(rev.file_path if rev else None, upload_root)
        if path:
            jobs.append((d, path))

    if not jobs:
        return []

    refine_jobs = jobs
    coarse_threshold = max(0.55, threshold - COARSE_THRESHOLD_PAD)

    # Multi-sheet project search: quick low-DPI screen, then refine only promising sheets.
    if len(jobs) > 1:
        workers = min(8, max(1, os.cpu_count() or 2), len(jobs))
        screened: list[tuple[float, dict, str]] = []
        if workers == 1:
            for d, path in jobs:
                _d, _path, score = _coarse_screen_sheet(
                    d, path, template_pil, template_arr,
                    coarse_template_pil, coarse_template_arr,
                    use_numpy, render_cache, cache_lock,
                )
                screened.append((score, _d, _path))
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(
                        _coarse_screen_sheet,
                        d, path, template_pil, template_arr,
                        coarse_template_pil, coarse_template_arr,
                        use_numpy, render_cache, cache_lock,
                    )
                    for d, path in jobs
                ]
                for fut in as_completed(futures):
                    try:
                        _d, _path, score = fut.result()
                        screened.append((score, _d, _path))
                    except Exception:
                        continue

        screened.sort(key=lambda item: item[0], reverse=True)
        candidates = [(d, path) for score, d, path in screened if score >= coarse_threshold]
        if not candidates:
            candidates = [(d, path) for _score, d, path in screened[:12]]
        else:
            candidates = candidates[:MAX_REFINE_SHEETS]
        refine_jobs = candidates

    results: list[dict[str, Any]] = []
    workers = min(8, max(1, os.cpu_count() or 2), len(refine_jobs))
    if workers == 1 or len(refine_jobs) == 1:
        for d, path in refine_jobs:
            results.extend(_search_shape_on_sheet(
                d, path, template_pil, template_arr, tw, th, threshold, use_numpy,
                REFINE_DPI, render_cache, cache_lock,
            ))
            if len(results) >= max_results:
                return sorted(results, key=lambda r: r['score'], reverse=True)[:max_results]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _search_shape_on_sheet,
                    d, path, template_pil, template_arr, tw, th, threshold, use_numpy,
                    REFINE_DPI, render_cache, cache_lock,
                ): d
                for d, path in refine_jobs
            }
            for fut in as_completed(futures):
                try:
                    results.extend(fut.result())
                except Exception:
                    continue
                if len(results) >= max_results:
                    for pending in futures:
                        pending.cancel()
                    break

    return sorted(results, key=lambda r: r['score'], reverse=True)[:max_results]


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
