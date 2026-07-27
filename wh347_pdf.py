"""WH-347 certified payroll PDF generation with prevailing wage checks."""
from __future__ import annotations

import io
import json
from datetime import datetime

import fitz

# Federal prevailing wage baseline rates by trade (simplified — override per project)
DEFAULT_PREVAILING_RATES = {
    'carpenter': 42.50,
    'laborer': 38.25,
    'electrician': 48.75,
    'plumber': 47.00,
    'operator': 45.50,
    'foreman': 52.00,
    'default': 40.00,
}


def parse_workers(workers_json):
    if not workers_json:
        return []
    if isinstance(workers_json, list):
        return workers_json
    try:
        data = json.loads(workers_json)
        return data if isinstance(data, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def prevailing_wage_for_trade(trade, project_rate=None):
    if project_rate:
        return float(project_rate)
    key = (trade or '').strip().lower()
    for name, rate in DEFAULT_PREVAILING_RATES.items():
        if name in key:
            return rate
    return DEFAULT_PREVAILING_RATES['default']


def validate_prevailing_wage(workers, project_prevailing_rate=None):
    """Return list of violations where paid rate < prevailing."""
    violations = []
    for w in workers:
        trade = w.get('classification') or w.get('trade') or 'Laborer'
        hours = float(w.get('hours') or 0)
        gross = float(w.get('gross_pay') or 0)
        if hours <= 0:
            continue
        paid_rate = gross / hours
        required = prevailing_wage_for_trade(trade, project_prevailing_rate)
        if paid_rate + 0.01 < required:
            violations.append({
                'worker': w.get('name') or 'Unknown',
                'trade': trade,
                'paid_rate': round(paid_rate, 2),
                'required_rate': required,
                'shortfall': round(required - paid_rate, 2),
            })
    return violations


def build_wh347_pdf(record, project=None, workers=None):
    """Generate WH-347 style certified payroll report PDF."""
    adv = record.get('advanced') or {}
    simple = record.get('simple') or {}
    workers = workers if workers is not None else parse_workers(adv.get('workers_json'))
    project_rate = getattr(project, 'prevailing_wage', None) if project else None
    if project_rate is None and project and getattr(project, 'details_json', None):
        try:
            details = json.loads(project.details_json)
            project_rate = details.get('prevailing_wage_rate')
        except (TypeError, json.JSONDecodeError):
            pass

    violations = validate_prevailing_wage(workers, project_rate)
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)  # landscape
    margin = 36
    y = margin

    def txt(text, size=9, bold=False):
        nonlocal y
        page.insert_text((margin, y), str(text or '')[:120], fontsize=size, fontname='hebo' if bold else 'helv')
        y += size + 5

    txt('U.S. DEPARTMENT OF LABOR — WH-347 (Case PM)', size=14, bold=True)
    txt(f'Contractor: {adv.get("contractor_name") or simple.get("title") or "—"}', bold=True)
    txt(f'Project: {(project.name if project else "—")}   Week Ending: {simple.get("work_date") or record.get("record_date") or "—"}')
    txt(f'Payroll #: {adv.get("number") or record.get("number") or "—"}')
    y += 6
    txt('Employee          Classification       Hours    Gross Pay   Rate/hr   Prevailing   Status', bold=True)
    y += 2
    total_hours = 0.0
    total_gross = 0.0
    for w in workers[:25]:
        trade = w.get('classification') or w.get('trade') or 'Laborer'
        hours = float(w.get('hours') or 0)
        gross = float(w.get('gross_pay') or 0)
        rate = gross / hours if hours else 0
        prev = prevailing_wage_for_trade(trade, project_rate)
        ok = rate + 0.01 >= prev if hours else True
        total_hours += hours
        total_gross += gross
        txt(f'{str(w.get("name",""))[:16]:16} {str(trade)[:18]:18} {hours:7.1f} {gross:10.2f} {rate:8.2f} {prev:10.2f} {"OK" if ok else "LOW"}')
    y += 6
    txt(f'Totals: {total_hours:.1f} hours   ${total_gross:,.2f}', bold=True)
    if violations:
        y += 8
        txt(f'PREVAILING WAGE VIOLATIONS: {len(violations)}', bold=True)
        for v in violations[:8]:
            txt(f'  {v["worker"]} ({v["trade"]}): paid ${v["paid_rate"]}/hr, required ${v["required_rate"]}/hr')
    else:
        y += 8
        txt('Prevailing wage compliance: PASS', bold=True)
    y += 12
    txt('I certify that the payroll is correct and complete.', bold=True)
    txt(f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}')

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue(), violations
