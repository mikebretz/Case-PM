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
REVISION_RE = re.compile(
    r'(?:REV(?:ISION)?\.?|REVISION)\s*[#:.]?\s*(\d{1,3}|[A-Z])',
    re.IGNORECASE,
)
# Filename / OCR false positives (e.g. "Drawings_Rev_3.pdf" → not sheet REV-3)
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
    sheet = f'{prefix}-{num}'
    if not is_plausible_drawing_sheet(sheet):
        return None
    return sheet


def is_plausible_drawing_sheet(sheet_number: str) -> bool:
    if not sheet_number or '-' not in sheet_number:
        return False
    prefix = sheet_number.split('-')[0].upper()
    if prefix in INVALID_SHEET_PREFIXES:
        return False
    if prefix in VALID_SHEET_PREFIXES:
        return True
    # Allow other 1–3 letter prefixes if numeric part looks like a sheet index
    num_part = sheet_number.split('-', 1)[1]
    return bool(re.match(r'^\d{1,4}', num_part)) and prefix.isalpha() and len(prefix) <= 3


def extract_revision_from_text(text: str) -> str | None:
    if not text:
        return None
    for line in (text.splitlines() or [])[-40:]:
        m = REVISION_RE.search(line)
        if m:
            return str(m.group(1)).upper()
    m = REVISION_RE.search(text)
    return str(m.group(1)).upper() if m else None


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
    candidates = []
    m = TITLE_BLOCK_RE.search(text)
    if m:
        candidates.append(normalize_sheet_number(m.group(1)))
    lines = text.splitlines()
    for line in list(lines[:20]) + list(reversed(lines[-40:])):
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
    ocr_text = ''
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
            return sheet, embedded

        rect = page.rect
        clips = [
            fitz.Rect(rect.width * 0.55, rect.height * 0.72, rect.width, rect.height),
            fitz.Rect(0, rect.height * 0.72, rect.width * 0.45, rect.height),
            fitz.Rect(rect.width * 0.35, rect.height * 0.65, rect.width, rect.height),
        ]
        try:
            import pytesseract
            from PIL import Image
            import io
        except ImportError:
            return None, embedded

        for clip in clips:
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=clip, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes('png')))
                chunk = pytesseract.image_to_string(img) or ''
                ocr_text += '\n' + chunk
                sheet = extract_sheet_from_pdf_text(chunk)
                if sheet:
                    return sheet, ocr_text
                sheet = normalize_sheet_number(chunk)
                if sheet:
                    return sheet, ocr_text
            except Exception:
                continue
        return extract_sheet_from_pdf_text(ocr_text), ocr_text
    except Exception:
        return None, ocr_text


def detect_sheet_number(
    pdf_path: str,
    filename: str | None = None,
    page_text: str | None = None,
    page_index: int = 0,
    from_combined_set: bool = False,
) -> tuple[str | None, str, str, str | None]:
    """Returns (sheet_number, text, method, revision_from_sheet)."""
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
    sheet, ocr_text = ocr_extract_sheet_from_pdf(pdf_path, page_index)
    combined_text = '\n'.join(filter(None, [page_text, ocr_text]))
    rev = revision or extract_revision_from_text(combined_text)
    if sheet and is_plausible_drawing_sheet(sheet):
        return sheet, combined_text or page_text or '', 'ocr', rev
    return None, combined_text or page_text or ocr_text or '', 'none', rev


def analyze_pdf_page(pdf_path: str, page_index: int = 0, from_combined_set: bool = False, source_filename: str | None = None) -> dict:
    """Analyze one page for sheet metadata (used during set upload)."""
    text = ''
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        if page_index < len(reader.pages):
            text = reader.pages[page_index].extract_text() or ''
    except Exception:
        pass
    sheet, full_text, method, revision = detect_sheet_number(
        pdf_path, source_filename, text, page_index, from_combined_set=from_combined_set,
    )
    title = extract_title_from_text(full_text, sheet)
    return {
        'page_index': page_index,
        'sheet_number': sheet,
        'revision': revision,
        'title': title,
        'discipline': discipline_from_sheet(sheet) if sheet else None,
        'detection_method': method,
        'text_preview': (full_text or '')[:240],
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
    sheet_revision=None,
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
        rev_num = str(sheet_revision) if sheet_revision is not None else '0'
    else:
        old_rev = DrawingRevision.query.filter_by(drawing_id=drawing.id, is_current=True).first()
        if old_rev:
            old_rev.is_current = False
            old_rev.superseded_at = now
        if sheet_revision is not None:
            rev_num = str(sheet_revision)
        else:
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
):
    """Import one or more split PDF pages into the drawing register."""
    created = []
    needs_review = []

    for page in pages:
        meta = analyze_pdf_page(
            page['file_path'],
            page_index=0,
            from_combined_set=from_combined_set,
            source_filename=None if from_combined_set else original_filename,
        )
        sheet_number = manual_sheet or meta.get('sheet_number')
        if sheet_number:
            sheet_number = normalize_sheet_number(sheet_number) or sheet_number
        if not sheet_number or not is_plausible_drawing_sheet(sheet_number):
            needs_review.append({
                'page': page['page_index'] + 1,
                'file': page.get('filename') or os.path.basename(page['file_path']),
                'text_preview': meta.get('text_preview'),
                'detected_revision': meta.get('revision'),
                'detection_method': meta.get('detection_method'),
            })
            continue

        page_text = page.get('text') or meta.get('text_preview') or ''
        title = manual_title or meta.get('title') or extract_title_from_text(page_text, sheet_number)
        drawing, rev, _old = upsert_drawing_from_upload(
            db, Drawing, DrawingRevision, DrawingMarkup,
            project_id=int(project_id),
            sheet_number=sheet_number,
            title=title,
            discipline=meta.get('discipline') or discipline_from_sheet(sheet_number),
            file_path=page['file_path'],
            original_filename=original_filename,
            set_name=set_name,
            drawing_date=None,
            received_date=date.today(),
            upload_source=upload_source,
            uploaded_by_id=uploaded_by_id,
            notes=f'Page {page["page_index"] + 1} of {original_filename}' if from_combined_set else '',
            sheet_revision=meta.get('revision'),
        )
        created.append({
            'id': drawing.id,
            'sheet_number': drawing.sheet_number,
            'title': drawing.title,
            'revision_label': rev.revision_label,
            'revision_number': rev.revision_number,
            'discipline': drawing.discipline,
            'page': page['page_index'] + 1,
            'detection_method': meta.get('detection_method'),
        })

    return created, needs_review


def delete_drawing_record(db, Drawing, DrawingRevision, DrawingMarkup, drawing):
    """Remove drawing, revisions, markups, and page files from disk."""
    drawing_id = drawing.id
    revisions = DrawingRevision.query.filter_by(drawing_id=drawing_id).all()
    paths = {rev.file_path for rev in revisions if rev.file_path}
    dirs = set()
    for p in paths:
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
            dirs.add(os.path.dirname(p))
    DrawingMarkup.query.filter_by(drawing_id=drawing_id).delete()
    DrawingRevision.query.filter_by(drawing_id=drawing_id).delete()
    db.session.delete(drawing)
    for d in dirs:
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass

