"""Burn document markups onto PDF pages for printing."""
from __future__ import annotations

import json
import math

import fitz


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _parse_color(value) -> tuple[float, float, float]:
    s = (value or '#38bdf8').strip()
    if s.startswith('#') and len(s) >= 7:
        return (
            int(s[1:3], 16) / 255.0,
            int(s[3:5], 16) / 255.0,
            int(s[5:7], 16) / 255.0,
        )
    return (0.22, 0.74, 0.97)


def _resolve_geom(geom: dict, page_w: float, page_h: float) -> dict:
    if not geom:
        return {}
    out = dict(geom)
    if geom.get('nx') is not None:
        out['x'] = float(geom['nx']) * page_w
    if geom.get('ny') is not None:
        out['y'] = float(geom['ny']) * page_h
    if geom.get('nw') is not None:
        out['w'] = float(geom['nw']) * page_w
    if geom.get('nh') is not None:
        out['h'] = float(geom['nh']) * page_h
    if geom.get('npoints'):
        out['points'] = [
            float(v) * (page_w if i % 2 == 0 else page_h)
            for i, v in enumerate(geom['npoints'])
        ]
    elif geom.get('points') and geom.get('canvasW') and geom.get('canvasH'):
        cw = float(geom['canvasW']) or page_w
        ch = float(geom['canvasH']) or page_h
        out['points'] = [
            (float(v) / cw) * page_w if i % 2 == 0 else (float(v) / ch) * page_h
            for i, v in enumerate(geom['points'])
        ]
    if geom.get('x') is not None and 'nx' not in geom and geom.get('canvasW'):
        cw = float(geom['canvasW']) or page_w
        ch = float(geom['canvasH']) or page_h
        out['x'] = (float(geom['x']) / cw) * page_w
        out['y'] = (float(geom['y']) / ch) * page_h
        if geom.get('w') is not None:
            out['w'] = (float(geom['w']) / cw) * page_w
        if geom.get('h') is not None:
            out['h'] = (float(geom['h']) / ch) * page_h
    return out


def _revision_cloud_path(x: float, y: float, w: float, h: float, scallop: float = 18) -> list[tuple[float, float]]:
    r = max(6.0, min(scallop, w / 4, h / 4))
    if w < r * 2 or h < r * 2:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def edge(x1, y1, x2, y2):
        pts = [(x1, y1)]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1:
            return pts
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        dist = 0.0
        cx, cy = x1, y1
        while dist + 0.25 < length:
            step = min(r * 2, length - dist)
            pts.append((cx + ux * step, cy + uy * step))
            cx += ux * step
            cy += uy * step
            dist += step
        pts.append((x2, y2))
        return pts

    path = edge(x, y + h, x, y)
    path.extend(edge(x, y, x + w, y)[1:])
    path.extend(edge(x + w, y, x + w, y + h)[1:])
    path.extend(edge(x + w, y + h, x, y + h)[1:])
    return path


def _markup_dict(markup) -> dict:
    if isinstance(markup, dict):
        geom = markup.get('geometry') or {}
        style = markup.get('style') or {}
        return {
            'markup_type': markup.get('markup_type') or 'line',
            'geometry': geom,
            'style': style,
            'label': markup.get('label'),
            'measurement_value': markup.get('measurement_value'),
            'measurement_unit': markup.get('measurement_unit'),
        }
    return {
        'markup_type': getattr(markup, 'markup_type', None) or 'line',
        'geometry': _parse_json(getattr(markup, 'geometry_json', None), {}),
        'style': _parse_json(getattr(markup, 'style_json', None), {}),
        'label': getattr(markup, 'label', None),
        'measurement_value': getattr(markup, 'measurement_value', None),
        'measurement_unit': getattr(markup, 'measurement_unit', None),
    }


def _draw_markup_on_page(page, markup_data: dict) -> None:
    mtype = markup_data.get('markup_type') or 'line'
    style = markup_data.get('style') or {}
    geom = _resolve_geom(markup_data.get('geometry') or {}, page.rect.width, page.rect.height)
    color = _parse_color(style.get('color'))
    width = float(style.get('lineWidth') or 2)
    opacity = float(style.get('opacity') if style.get('opacity') is not None else 1.0)
    fill_op = float(style.get('fillOpacity') if style.get('fillOpacity') is not None else 0.25)
    scallop = float(style.get('cloudScallop') or 18)
    shape = page.new_shape()

    if mtype in ('line', 'arrow', 'measure') and geom.get('points'):
        pts = geom['points']
        if len(pts) >= 4:
            p1 = fitz.Point(pts[0], pts[1])
            p2 = fitz.Point(pts[2], pts[3])
            shape.draw_line(p1, p2)
            shape.finish(color=color, width=width, stroke_opacity=opacity)
            shape.commit()
            if mtype == 'measure' and markup_data.get('measurement_value') is not None:
                unit = markup_data.get('measurement_unit') or ''
                label = f"{markup_data['measurement_value']:.2f} {unit}".strip()
                mx = (pts[0] + pts[2]) / 2
                my = (pts[1] + pts[3]) / 2
                page.insert_text((mx, my - 4), label, fontsize=9, color=color)
        return

    if mtype in ('rect', 'highlight') and geom.get('w') is not None:
        rect = fitz.Rect(geom['x'], geom['y'], geom['x'] + geom['w'], geom['y'] + geom['h'])
        fill = (1.0, 0.8, 0.0) if mtype == 'highlight' else None
        fill_alpha = fill_op if mtype == 'highlight' else 0
        shape.draw_rect(rect)
        shape.finish(
            color=color,
            width=width,
            fill=fill,
            fill_opacity=fill_alpha,
            stroke_opacity=opacity,
        )
        shape.commit()
        return

    if mtype == 'cloud' and geom.get('w') is not None:
        path = _revision_cloud_path(geom['x'], geom['y'], geom['w'], geom['h'], scallop)
        if len(path) >= 2:
            for i in range(len(path) - 1):
                shape.draw_line(fitz.Point(path[i][0], path[i][1]), fitz.Point(path[i + 1][0], path[i + 1][1]))
            shape.finish(color=color, width=width, stroke_opacity=opacity)
            shape.commit()
        return

    if mtype == 'ellipse' and geom.get('w') is not None:
        rect = fitz.Rect(geom['x'], geom['y'], geom['x'] + geom['w'], geom['y'] + geom['h'])
        shape.draw_oval(rect)
        shape.finish(color=color, width=width, fill_opacity=fill_op, stroke_opacity=opacity)
        shape.commit()
        return

    if mtype in ('pen', 'sketch', 'polyline', 'polygon', 'area') and geom.get('points'):
        pts = geom['points']
        points = [fitz.Point(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
        if len(points) >= 2:
            closed = mtype in ('polygon', 'area')
            shape.draw_polyline(points)
            fill = (0.13, 0.77, 0.37) if mtype == 'area' else None
            shape.finish(
                color=color,
                width=width,
                fill=fill,
                fill_opacity=fill_op if mtype == 'area' else 0,
                stroke_opacity=opacity,
                closePath=closed,
            )
            shape.commit()
        return

    if mtype == 'crossout' and geom.get('w') is not None:
        x, y, w, h = geom['x'], geom['y'], geom['w'], geom.get('h') or geom['w']
        shape.draw_line(fitz.Point(x, y), fitz.Point(x + w, y + h))
        shape.draw_line(fitz.Point(x + w, y), fitz.Point(x, y + h))
        shape.finish(color=color, width=width, stroke_opacity=opacity)
        shape.commit()
        return

    if mtype in ('text', 'textbox') and geom.get('x') is not None:
        label = (markup_data.get('label') or '').strip()
        if not label:
            return
        fs = int(style.get('fontSize') or 12)
        tx = geom['x'] + 4
        ty = geom['y'] + fs
        page.insert_text((tx, ty), label[:500], fontsize=fs, color=color)
        return

    if mtype == 'stamp' and geom.get('x') is not None:
        tw = geom.get('w') or 110
        th = geom.get('h') or 32
        rect = fitz.Rect(geom['x'], geom['y'], geom['x'] + tw, geom['y'] + th)
        shape.draw_rect(rect)
        shape.finish(color=color, width=2, stroke_opacity=opacity)
        shape.commit()
        stamp_text = (markup_data.get('label') or style.get('stampType') or 'STAMP')[:40]
        page.insert_text(
            (geom['x'] + tw / 2 - len(stamp_text) * 2.5, geom['y'] + th / 2 + 4),
            stamp_text,
            fontsize=int(style.get('fontSize') or 11),
            color=color,
        )
        return


def burn_markups_onto_pdf_doc(doc: fitz.Document, markups, *, page_index: int = 0) -> None:
    """Draw markups onto a single page of an open PDF document."""
    if not markups or doc.page_count == 0:
        return
    idx = min(max(0, page_index), doc.page_count - 1)
    page = doc[idx]
    for raw in markups:
        try:
            _draw_markup_on_page(page, _markup_dict(raw))
        except Exception:
            continue


def burn_markups_onto_pdf_bytes(pdf_bytes: bytes, markups, *, page_index: int = 0) -> bytes:
    if not pdf_bytes or not markups:
        return pdf_bytes
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        burn_markups_onto_pdf_doc(doc, markups, page_index=page_index)
        return doc.tobytes()
    finally:
        doc.close()
