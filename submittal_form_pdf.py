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


def fill_submittal_form_pdf(submittal, project=None, company_info=None, template_path: str | None = None) -> bytes:
    """Return filled Submittal_Form.pdf bytes."""
    if template_path is None:
        template_path = os.path.join(
            os.path.dirname(__file__), 'static', 'forms', 'Submittal_Form.pdf',
        )
    if not os.path.isfile(template_path):
        raise FileNotFoundError('Submittal form template is missing.')

    values = build_submittal_form_field_values(submittal, project=project, company_info=company_info)
    doc = fitz.open(template_path)
    try:
        page = doc[0]
        for widget in page.widgets() or []:
            val = values.get(widget.field_name)
            if val is None:
                continue
            widget.field_value = val
            widget.update()
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
    """Filled submittal form followed by every attachment (PDF/image pages)."""
    form_bytes = fill_submittal_form_pdf(
        submittal,
        project=project,
        company_info=company_info,
        template_path=template_path,
    )
    merged = fitz.open(stream=form_bytes, filetype='pdf')
    try:
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
                _append_bytes_to_pdf(merged, data)
            except Exception:
                continue
        return merged.tobytes()
    finally:
        merged.close()
