"""Drawing persistence, PDF processing, revision tracking, and markup helpers."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, date

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
    r'\b([A-Z]{1,3})[-_.\s]?(\d{1,4}(?:\.\d{2})?)\b',
    re.IGNORECASE,
)
TITLE_BLOCK_RE = re.compile(
    r'(?:SHEET|DRAWING|DWG\.?\s*NO\.?)[:\s#]*([A-Z]{1,3}[-_.\s]?\d{1,4}(?:\.\d{2})?)',
    re.IGNORECASE,
)


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
    text = str(raw).strip().upper().replace('_', '-').replace('.', '-')
    m = SHEET_RE.search(text)
    if not m:
        return None
    prefix, num = m.group(1).upper(), m.group(2).replace('.', '-')
    return f'{prefix}-{num}'


def section_prefix(sheet_number: str) -> str:
    if not sheet_number:
        return 'OTHER'
    return sheet_number.split('-')[0].upper()


def discipline_from_sheet(sheet_number: str) -> str:
    if not sheet_number:
        return 'General'
    prefix = section_prefix(sheet_number)
    return DISCIPLINE_MAP.get(prefix, 'General')


def sort_key_for_sheet(sheet_number: str) -> str:
    if not sheet_number:
        return 'ZZZZ-9999'
    norm = normalize_sheet_number(sheet_number) or sheet_number
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
    m = TITLE_BLOCK_RE.search(text)
    if m:
        return normalize_sheet_number(m.group(1))
    for line in text.splitlines()[:40]:
        found = normalize_sheet_number(line)
        if found:
            return found
    return normalize_sheet_number(text[:500])


def extract_title_from_text(text: str, sheet_number: str | None) -> str:
    if not text:
        return ''
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines[:25]:
        if sheet_number and sheet_number.replace('-', '') in ln.replace('-', '').replace(' ', ''):
            continue
        if len(ln) > 8 and not SHEET_RE.fullmatch(ln.replace(' ', '-')):
            if 'SHEET' not in ln.upper() and 'DRAWING' not in ln.upper():
                return ln[:200]
    return ''


def split_pdf_to_pages(source_path: str, out_dir: str) -> list[dict]:
    """Split a PDF into single-page files. Returns metadata per page."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise RuntimeError('pypdf is required for drawing set uploads. Install with: pip install pypdf')

    os.makedirs(out_dir, exist_ok=True)
    reader = PdfReader(source_path)
    results = []
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


def drawing_to_dict(drawing, current_rev=None, revision_count=0, markup_count=0, linked_rfis=None):
    rev = current_rev
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
        'file_url': f'/api/drawings/{drawing.id}/file' if rev else None,
        'thumbnail_url': f'/api/drawings/{drawing.id}/thumbnail',
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
    """Copy published markups (not sketches) to new revision — Procore-style inheritance."""
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
):
    """Create or revise a drawing sheet from an uploaded page."""
    sheet_number = normalize_sheet_number(sheet_number) or sheet_number
    if not sheet_number:
        raise ValueError('Could not determine sheet number')

    drawing = Drawing.query.filter_by(project_id=project_id, sheet_number=sheet_number).first()
    now = datetime.utcnow()
    old_rev = None

    if not drawing:
        drawing = Drawing(
            project_id=project_id,
            sheet_number=sheet_number,
            title=title or f'Sheet {sheet_number}',
            discipline=discipline or discipline_from_sheet(sheet_number),
            section_prefix=section_prefix(sheet_number),
            sort_key=sort_key_for_sheet(sheet_number),
            status='Current',
            created_at=now,
            updated_at=now,
        )
        db.session.add(drawing)
        db.session.flush()
        rev_num = '0'
    else:
        old_rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
        if old_rev:
            old_rev.is_current = False
            old_rev.superseded_at = now
        rev_num = next_revision_number(
            DrawingRevision.query.filter_by(drawing_id=drawing.id).all()
        )
        drawing.title = title or drawing.title
        drawing.discipline = discipline or drawing.discipline
        drawing.status = 'Current'
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
    db.session.flush()
    drawing.current_revision_id = new_rev.id

    if old_rev:
        inherit_markups_to_revision(db, DrawingMarkup, drawing.id, old_rev.id, new_rev.id)

    return drawing, new_rev, old_rev
