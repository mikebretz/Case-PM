"""Transmittal cover sheet PDF generation."""
from __future__ import annotations

import io
from datetime import datetime

import fitz


def build_transmittal_pdf(record, project=None, recipients=None):
    """Build a transmittal cover sheet PDF as bytes."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    margin = 54
    y = margin

    def line(text, size=11, bold=False):
        nonlocal y
        page.insert_text((margin, y), str(text or ''), fontsize=size, fontname='helv' if not bold else 'hebo')
        y += size + 8

    line('TRANSMITTAL', size=18, bold=True)
    y += 4
    line(f'Project: {(project.name if project else "—")}', size=12, bold=True)
    if project and getattr(project, 'number', None):
        line(f'Project #: {project.number}')
    line(f'Date: {datetime.utcnow().strftime("%B %d, %Y")}')
    y += 8
    line(f'Subject: {record.get("title") or "—"}', bold=True)
    line(f'Transmittal #: {record.get("number") or record.get("id") or "—"}')
    line(f'Purpose: {record.get("purpose") or "For Review"}')
    line(f'To: {record.get("to_party") or "—"}')
    if record.get('cc_party'):
        line(f'CC: {record.get("cc_party")}')
    if record.get('due_date'):
        line(f'Response Due: {record.get("due_date")}')
    y += 8
    line('Required Action:', bold=True)
    req = record.get('required_action') or record.get('notes') or 'Please review and acknowledge receipt.'
    for chunk in _wrap(req, 90):
        line(chunk)
    y += 10
    line('Distribution:', bold=True)
    recs = recipients or []
    if not recs:
        line('—')
    else:
        for r in recs:
            status = r.get('status') or 'Pending'
            line(f'• {r.get("name") or r.get("email")} — {status}')
    y += 16
    line('Acknowledgment', bold=True)
    line('Recipient: _____________________________   Date: ______________')
    line('Signature: _____________________________')

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _wrap(text, width):
    words = str(text or '').split()
    lines, cur = [], []
    for w in words:
        if sum(len(x) for x in cur) + len(cur) + len(w) > width:
            lines.append(' '.join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(' '.join(cur))
    return lines or ['']
