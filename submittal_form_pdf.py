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
