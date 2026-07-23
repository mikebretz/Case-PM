"""Fill the official Submittal_Form.pdf template for printing."""
from __future__ import annotations

import os
from datetime import datetime

import fitz


def _format_spec_digits(spec_section: str) -> str:
    digits = ''.join(ch for ch in str(spec_section or '') if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    return digits or str(spec_section or '').strip()


def _format_sent_date(value) -> str:
    if not value:
        return datetime.utcnow().strftime('%-m/%-d/%Y') if os.name != 'nt' else datetime.utcnow().strftime('%#m/%#d/%Y')
    raw = str(value).strip()[:10]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime('%-m/%-d/%Y') if os.name != 'nt' else dt.strftime('%#m/%#d/%Y')
        except ValueError:
            continue
    return raw


def _contractor_block(company_info: dict | None) -> str:
    info = company_info or {}
    lines = []
    for key in ('company_name', 'dba_name'):
        name = (info.get(key) or '').strip()
        if name:
            lines.append(name)
            break
    address = (info.get('company_address') or '').strip()
    if address:
        lines.append(address)
    city = (info.get('company_city') or '').strip()
    state = (info.get('company_state') or '').strip()
    zip_code = (info.get('company_zip') or '').strip()
    city_line = ', '.join(part for part in (city, state) if part)
    if city_line and zip_code:
        city_line = f'{city_line} {zip_code}'
    elif zip_code:
        city_line = zip_code
    if city_line:
        lines.append(city_line)
    phone = (info.get('company_phone') or '').strip()
    if phone:
        lines.append(phone)
    return '\n'.join(lines)


def build_submittal_form_field_values(submittal, project=None, company_info=None, details=None) -> dict[str, str]:
    """Map a Submittal row to the PDF AcroForm field names."""
    details = details if isinstance(details, dict) else {}
    if not details:
        try:
            import json
            raw = getattr(submittal, 'details_json', None)
            details = json.loads(raw) if raw else {}
        except Exception:
            details = {}

    spec_digits = _format_spec_digits(getattr(submittal, 'spec_section', None) or details.get('specSection'))
    section_name = (details.get('sectionName') or '').strip()
    spec_title = f'{spec_digits} - {section_name}'.strip(' -') if section_name else spec_digits

    paragraph = (details.get('paragraph') or '').strip()
    spec_number = spec_digits
    if paragraph:
        spec_number = f'{spec_digits}-{paragraph}' if spec_digits else paragraph

    project_name = ''
    if project is not None:
        project_name = (getattr(project, 'name', None) or '').strip()
    if not project_name:
        project_name = (details.get('jobName') or '').strip()

    submittal_title = (details.get('type') or getattr(submittal, 'description', None) or '').strip()
    number = (getattr(submittal, 'number', None) or '').strip()
    rev = str(details.get('rev') or '0').strip() or '0'

    sent_raw = getattr(submittal, 'date', None)
    if sent_raw and hasattr(sent_raw, 'isoformat'):
        sent_raw = sent_raw.isoformat()
    if not sent_raw:
        sent_raw = details.get('dateReceived') or details.get('notifiedDate')

    return {
        'Job Number#1': project_name,
        'Spec Section Title#1': spec_title,
        'Submittal Title#1': submittal_title,
        'Spec Section Number#1': spec_number,
        'Submittal Number#1': number,
        'Revision Number#1': rev,
        'Sent Date#1': _format_sent_date(sent_raw),
        'Contractor Field#1': _contractor_block(company_info),
        'Architect Field#1': (details.get('architectStamp') or details.get('referredTo') or '').strip(),
        'Engineer Field#1': (details.get('engineerStamp') or '').strip(),
    }


def _parse_submittal_details(submittal) -> dict:
    try:
        import json
        raw = getattr(submittal, 'details_json', None)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _widget_rect(page, field_name: str):
    for widget in page.widgets() or []:
        if widget.field_name == field_name:
            return widget.rect
    return None


def _load_signature_bytes(signature_path: str | None, upload_folder: str | None = None) -> bytes | None:
    if not signature_path:
        return None
    candidates = [signature_path]
    if upload_folder:
        candidates.append(os.path.join(upload_folder, signature_path))
        candidates.append(os.path.join(upload_folder, 'signatures', os.path.basename(signature_path)))
    base_dir = os.path.dirname(__file__)
    candidates.append(os.path.join(base_dir, signature_path))
    candidates.append(os.path.join(base_dir, 'uploads', 'signatures', os.path.basename(signature_path)))
    for path in candidates:
        if path and os.path.isfile(path):
            with open(path, 'rb') as fh:
                return fh.read()
    return None


def _format_review_datetime(value: str | None) -> str:
    raw = (value or '').strip()
    if not raw:
        return datetime.utcnow().strftime('%m/%d/%Y %I:%M %p')
    try:
        dt = datetime.fromisoformat(raw.replace('Z', ''))
        return dt.strftime('%m/%d/%Y %I:%M %p')
    except ValueError:
        return raw.replace('T', ' ')[:19]


def _draw_page_footer(page, page_num: int, total_pages: int) -> None:
    label = f'Page {page_num} of {total_pages}'
    page.insert_text(
        (page.rect.width - 90, page.rect.height - 28),
        label,
        fontsize=8,
        fontname='helv',
        color=(0.35, 0.35, 0.35),
    )


def _draw_contractor_review_stamp(page, rect, stamp: dict, *, upload_folder: str | None = None) -> None:
    """Draw a review-style stamp in the contractor stamp area."""
    if not rect:
        return
    border = (0.12, 0.45, 0.78)
    fill = (0.93, 0.97, 1.0)
    inset = fitz.Rect(rect.x0 + 4, rect.y0 + 4, rect.x1 - 4, rect.y1 - 4)
    shape = page.new_shape()
    shape.draw_rect(inset)
    shape.finish(color=border, width=2, fill=fill)
    shape.commit()

    page.insert_text(
        (inset.x0 + 8, inset.y0 + 16),
        'REVIEWED',
        fontsize=11,
        fontname='helv',
        color=border,
    )

    signature_bytes = _load_signature_bytes(stamp.get('signature_path'), upload_folder=upload_folder)
    text_y = inset.y0 + 34
    if signature_bytes:
        img_rect = fitz.Rect(inset.x0 + 10, inset.y0 + 22, inset.x1 - 10, inset.y0 + 78)
        try:
            page.insert_image(img_rect, stream=signature_bytes, keep_proportion=True)
            text_y = inset.y0 + 86
        except Exception:
            signature_bytes = None
    if not signature_bytes:
        page.insert_text(
            (inset.x0 + 8, text_y),
            'Reviewed by',
            fontsize=7,
            fontname='helv',
            color=(0.35, 0.35, 0.35),
        )
        page.insert_text(
            (inset.x0 + 8, text_y + 12),
            (stamp.get('reviewed_by_name') or 'User')[:40],
            fontsize=9,
            fontname='helv',
            color=border,
        )
        text_y += 28

    reviewed_at = _format_review_datetime(stamp.get('reviewed_at'))
    page.insert_text(
        (inset.x0 + 8, inset.y1 - 10),
        reviewed_at,
        fontsize=7,
        fontname='helv',
        color=(0.4, 0.4, 0.4),
    )


def _party_comment_bucket(party: str | None, user_role: str | None = None) -> str:
    label = f'{party or ""} {user_role or ""}'.lower()
    if 'owner' in label:
        return 'owner'
    if 'engineer' in label and 'architect' not in label:
        return 'engineer'
    if 'architect' in label or 'a/e' in label or 'design professional' in label:
        return 'architect'
    if 'contractor' in label or 'project manager' in label or label.strip() in ('pm', 'reviewer'):
        return 'contractor'
    return 'contractor'


def _group_review_comments(submissions, review_comments: str | None = None) -> dict[str, list[str]]:
    grouped = {
        'contractor': [],
        'architect': [],
        'engineer': [],
        'owner': [],
    }
    for sub in submissions or []:
        bucket = _party_comment_bucket(sub.get('party'), sub.get('user_role'))
        stamp = _format_review_datetime(sub.get('created_at'))
        name = sub.get('user_name') or 'User'
        header = f'{stamp} — {name}'
        if sub.get('decision'):
            header += f' — {sub["decision"]}'
        grouped[bucket].append(header)
        body = (sub.get('body') or '').strip()
        if body:
            grouped[bucket].extend(line.strip() for line in body.splitlines() if line.strip())
        grouped[bucket].append('')
    official = (review_comments or '').strip()
    if official:
        grouped['architect'].append(official)
        grouped['architect'].append('')
    return grouped


def _fill_submittal_cover_page(
    page,
    submittal,
    project=None,
    company_info=None,
    *,
    details=None,
    blank_ae: bool = False,
    use_contractor_stamp: bool = False,
    upload_folder: str | None = None,
) -> fitz.Rect | None:
    """Fill AcroForm widgets on the cover page; optionally reserve contractor stamp area."""
    details = details if isinstance(details, dict) else _parse_submittal_details(submittal)
    values = build_submittal_form_field_values(submittal, project=project, company_info=company_info, details=details)
    contractor_stamp = details.get('contractorReviewStamp') if use_contractor_stamp else None
    if contractor_stamp:
        values['Contractor Field#1'] = ''
    if blank_ae:
        values['Architect Field#1'] = ''
        values['Engineer Field#1'] = ''
    for widget in page.widgets() or []:
        val = values.get(widget.field_name)
        if val is None:
            continue
        widget.field_value = val
        widget.update()
    stamp_rect = _widget_rect(page, 'Contractor Field#1')
    if contractor_stamp and stamp_rect:
        _draw_contractor_review_stamp(page, stamp_rect, contractor_stamp, upload_folder=upload_folder)
    return stamp_rect


def _append_submittal_comments_page(
    doc,
    submittal,
    project=None,
    *,
    details=None,
    submissions=None,
    review_comments: str | None = None,
    page_num: int = 2,
    total_pages: int = 2,
) -> None:
    """Second page: comment sections without stamp boxes."""
    details = details if isinstance(details, dict) else _parse_submittal_details(submittal)
    values = build_submittal_form_field_values(submittal, project=project, company_info=None, details=details)
    page = doc.new_page(width=612, height=792)
    page.insert_text((36, 48), 'SUBMITTAL', fontsize=18, fontname='helv', color=(0, 0, 0))
    meta = (
        f"Submittal No: {values.get('Submittal Number#1', '')}    "
        f"Rev: {values.get('Revision Number#1', '')}    "
        f"Spec: {values.get('Spec Section Title#1', '')}"
    )
    page.insert_text((36, 72), meta[:120], fontsize=9, fontname='helv', color=(0.2, 0.2, 0.2))
    page.insert_text((36, 88), values.get('Submittal Title#1', '')[:100], fontsize=9, fontname='helv', color=(0.2, 0.2, 0.2))

    grouped = _group_review_comments(submissions, review_comments)
    sections = (
        ('Contractor Comments', 'contractor'),
        ('Architect Comments', 'architect'),
        ('Engineer Comments', 'engineer'),
        ('Owner Comments', 'owner'),
    )
    y = 112
    box_height = 118
    for title, key in sections:
        page.insert_text((36, y), title, fontsize=10, fontname='helv', color=(0.1, 0.1, 0.1))
        y += 6
        box = fitz.Rect(36, y, 576, y + box_height)
        shape = page.new_shape()
        shape.draw_rect(box)
        shape.finish(color=(0.55, 0.55, 0.55), width=0.75, fill=(1, 1, 1))
        shape.commit()
        lines = grouped.get(key) or []
        if not lines:
            lines = ['(No comments recorded.)']
        ty = y + 14
        for line in lines:
            if ty > box.y1 - 8:
                break
            page.insert_text((44, ty), line[:100], fontsize=8, fontname='helv', color=(0.15, 0.15, 0.15))
            ty += 11
        y += box_height + 14

    _draw_page_footer(page, page_num, total_pages)


def fill_submittal_form_pdf(submittal, project=None, company_info=None, template_path: str | None = None) -> bytes:
    """Return filled Submittal_Form.pdf bytes."""
    if template_path is None:
        template_path = os.path.join(
            os.path.dirname(__file__), 'static', 'forms', 'Submittal_Form.pdf',
        )
    if not os.path.isfile(template_path):
        raise FileNotFoundError('Submittal form template is missing.')

    doc = fitz.open(template_path)
    try:
        details = _parse_submittal_details(submittal)
        use_stamp = bool(details.get('contractorReviewStamp'))
        _fill_submittal_cover_page(
            doc[0],
            submittal,
            project=project,
            company_info=company_info,
            details=details,
            use_contractor_stamp=use_stamp,
        )
        return doc.tobytes()
    finally:
        doc.close()


def _is_pdf_bytes(data: bytes) -> bool:
    return bool(data) and data[:4] == b'%PDF'


def _is_image_bytes(data: bytes) -> bool:
    if not data:
        return False
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    if data[:3] == b'\xff\xd8\xff':
        return True
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return True
    return False


def _read_attachment_bytes(attachment: dict, *, submittal_id: int, project_id: int, upload_folder: str, Document=None) -> bytes | None:
    if not attachment or not isinstance(attachment, dict):
        return None
    doc_id = attachment.get('document_id')
    if doc_id and Document is not None:
        doc = Document.query.get(int(doc_id))
        if not doc or doc.deleted_at:
            return None
        path = os.path.join(upload_folder, 'documents', str(project_id), doc.filename)
        if os.path.isfile(path):
            with open(path, 'rb') as fh:
                return fh.read()
        return None
    filename = (attachment.get('filename') or '').strip()
    if not filename:
        return None
    path = os.path.join(upload_folder, 'submittals', str(submittal_id), filename)
    if not os.path.isfile(path):
        return None
    with open(path, 'rb') as fh:
        return fh.read()


def _append_bytes_to_pdf(merged: fitz.Document, data: bytes) -> None:
    if not data:
        return
    if _is_pdf_bytes(data):
        src = fitz.open(stream=data, filetype='pdf')
        try:
            merged.insert_pdf(src)
        finally:
            src.close()
        return
    if _is_image_bytes(data):
        from document_features import image_bytes_to_pdf
        img_pdf = image_bytes_to_pdf(data)
        src = fitz.open(stream=img_pdf, filetype='pdf')
        try:
            merged.insert_pdf(src)
        finally:
            src.close()


def build_submittal_print_pdf(
    submittal,
    project=None,
    company_info=None,
    attachments=None,
    *,
    upload_folder: str,
    Document=None,
    template_path: str | None = None,
) -> bytes:
    """Filled submittal cover (with review stamp when applicable), comments page, then attachments."""
    if template_path is None:
        template_path = os.path.join(
            os.path.dirname(__file__), 'static', 'forms', 'Submittal_Form.pdf',
        )
    if not os.path.isfile(template_path):
        raise FileNotFoundError('Submittal form template is missing.')

    details = _parse_submittal_details(submittal)
    submissions = details.get('reviewSubmissions') or details.get('review_submissions') or []
    review_comments = (getattr(submittal, 'review_comments', None) or '').strip()
    use_stamp = bool(details.get('contractorReviewStamp'))

    doc = fitz.open(template_path)
    try:
        _fill_submittal_cover_page(
            doc[0],
            submittal,
            project=project,
            company_info=company_info,
            details=details,
            use_contractor_stamp=use_stamp,
            upload_folder=upload_folder,
        )
        _draw_page_footer(doc[0], 1, 2)
        _append_submittal_comments_page(
            doc,
            submittal,
            project=project,
            details=details,
            submissions=submissions,
            review_comments=review_comments,
            page_num=2,
            total_pages=2,
        )
        project_id = getattr(submittal, 'project_id', None) or getattr(project, 'id', None)
        submittal_id = getattr(submittal, 'id', None)
        for attachment in attachments or []:
            try:
                data = _read_attachment_bytes(
                    attachment,
                    submittal_id=int(submittal_id),
                    project_id=int(project_id),
                    upload_folder=upload_folder,
                    Document=Document,
                )
                _append_bytes_to_pdf(doc, data)
            except Exception:
                continue
        return doc.tobytes()
    finally:
        doc.close()


def build_submittal_review_sheet_pdf(
    submittal,
    project=None,
    company_info=None,
    *,
    template_path: str | None = None,
    upload_folder: str | None = None,
) -> bytes:
    """Two-page review sheet: cover with contractor review stamp, then comment sections."""
    if template_path is None:
        template_path = os.path.join(
            os.path.dirname(__file__), 'static', 'forms', 'Submittal_Form.pdf',
        )
    if not os.path.isfile(template_path):
        raise FileNotFoundError('Submittal form template is missing.')

    details = _parse_submittal_details(submittal)
    submissions = details.get('reviewSubmissions') or details.get('review_submissions') or []
    review_comments = (getattr(submittal, 'review_comments', None) or '').strip()
    use_stamp = bool(details.get('contractorReviewStamp'))

    doc = fitz.open(template_path)
    try:
        _fill_submittal_cover_page(
            doc[0],
            submittal,
            project=project,
            company_info=company_info,
            details=details,
            blank_ae=True,
            use_contractor_stamp=use_stamp,
            upload_folder=upload_folder,
        )
        _draw_page_footer(doc[0], 1, 2)
        _append_submittal_comments_page(
            doc,
            submittal,
            project=project,
            details=details,
            submissions=submissions,
            review_comments=review_comments,
            page_num=2,
            total_pages=2,
        )
        return doc.tobytes()
    finally:
        doc.close()
