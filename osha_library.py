"""Curated OSHA safety reference library shown on the Safety page.

Bundled items ship as PDFs in static/osha and are always available offline.
Reference items link to official OSHA pages/publications and can be saved into the
project's Documents on demand.
"""
from __future__ import annotations

import os
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Bundled PDFs live in static/osha/<file>. `pdf_url` (official source) lets us also
# file them into project Documents. `topic_url` is the stable official landing page.
OSHA_LIBRARY = [
    {
        'key': 'osha3165',
        'title': 'Job Safety and Health: It\'s the Law (Poster)',
        'category': 'Required Postings',
        'pub': 'OSHA 3165',
        'description': 'The federal OSHA workplace poster every jobsite must display.',
        'bundled_file': 'osha3165-job-safety-health-poster.pdf',
        'pdf_url': 'https://www.osha.gov/sites/default/files/publications/osha3165.pdf',
        'topic_url': 'https://www.osha.gov/publications/poster',
    },
    {
        'key': 'osha3071',
        'title': 'Job Hazard Analysis',
        'category': 'Programs & Planning',
        'pub': 'OSHA 3071',
        'description': 'How to identify hazards before they cause injury — the basis of a JHA/JSA.',
        'bundled_file': 'osha3071-job-hazard-analysis.pdf',
        'pdf_url': 'https://www.osha.gov/sites/default/files/publications/osha3071.pdf',
        'topic_url': 'https://www.osha.gov/publications/all',
    },
    {
        'key': 'osha3151',
        'title': 'Personal Protective Equipment',
        'category': 'PPE',
        'pub': 'OSHA 3151',
        'description': 'Selecting and using PPE — eye, head, hand, foot, and hearing protection.',
        'bundled_file': 'osha3151-personal-protective-equipment.pdf',
        'pdf_url': 'https://www.osha.gov/sites/default/files/publications/osha3151.pdf',
        'topic_url': 'https://www.osha.gov/personal-protective-equipment',
    },
    # Reference topics (official pages) — key construction focus areas.
    {
        'key': 'fall-protection',
        'title': 'Fall Protection in Construction',
        'category': 'Focus Four',
        'pub': '',
        'description': 'Fall protection standards, guardrails, PFAS, and the leading cause of construction fatalities.',
        'topic_url': 'https://www.osha.gov/fall-protection',
    },
    {
        'key': 'silica',
        'title': 'Respirable Crystalline Silica',
        'category': 'Health',
        'pub': '',
        'description': 'Table 1 controls, exposure limits, and the written exposure control plan.',
        'topic_url': 'https://www.osha.gov/silica-crystalline',
    },
    {
        'key': 'excavation',
        'title': 'Trenching & Excavation Safety',
        'category': 'Focus Four',
        'pub': '',
        'description': 'Protective systems, sloping/shoring, and competent-person requirements.',
        'topic_url': 'https://www.osha.gov/trenching-excavation',
    },
    {
        'key': 'scaffolding',
        'title': 'Scaffolding',
        'category': 'Construction',
        'pub': '',
        'description': 'Scaffold design, capacity, access, and fall protection requirements.',
        'topic_url': 'https://www.osha.gov/scaffolding',
    },
    {
        'key': 'electrical',
        'title': 'Electrical Safety',
        'category': 'Focus Four',
        'pub': '',
        'description': 'Lockout/tagout, GFCI, and safe work practices around electricity.',
        'topic_url': 'https://www.osha.gov/electrical',
    },
    {
        'key': 'struck-by',
        'title': 'Struck-By Hazards',
        'category': 'Focus Four',
        'pub': '',
        'description': 'Vehicles, falling/flying objects, and masonry walls — the struck-by focus four.',
        'topic_url': 'https://www.osha.gov/struck-by',
    },
    {
        'key': 'heat',
        'title': 'Heat Illness Prevention',
        'category': 'Health',
        'pub': '',
        'description': 'Water, rest, shade — acclimatization and heat emergency response.',
        'topic_url': 'https://www.osha.gov/heat',
    },
    {
        'key': 'hazcom',
        'title': 'Hazard Communication (HazCom / GHS)',
        'category': 'Health',
        'pub': '',
        'description': 'Safety Data Sheets, labeling, and the written hazard communication program.',
        'topic_url': 'https://www.osha.gov/hazard-communication',
    },
    {
        'key': 'recordkeeping',
        'title': 'Injury & Illness Recordkeeping (300/300A/301)',
        'category': 'Recordkeeping',
        'pub': '',
        'description': 'OSHA 300 log, 300A summary posting, and 301 incident reports.',
        'topic_url': 'https://www.osha.gov/recordkeeping',
    },
    {
        'key': 'confined-space',
        'title': 'Confined Spaces in Construction',
        'category': 'Construction',
        'pub': 'OSHA 3914',
        'description': 'Permit-required confined spaces, atmospheric testing, attendants, and rescue planning.',
        'pdf_url': 'https://www.osha.gov/sites/default/files/publications/OSHA3914.pdf',
        'topic_url': 'https://www.osha.gov/confined-spaces',
    },
    {
        'key': 'ladders',
        'title': 'Portable Ladder Safety',
        'category': 'Focus Four',
        'pub': 'OSHA 3124',
        'description': 'Ladder selection, setup angle, load limits, and inspection before use.',
        'pdf_url': 'https://www.osha.gov/sites/default/files/publications/osha3124.pdf',
        'topic_url': 'https://www.osha.gov/ladders',
    },
    {
        'key': 'cranes',
        'title': 'Cranes & Derricks in Construction',
        'category': 'Construction',
        'pub': '',
        'description': 'Qualified riggers, load charts, swing radius, and crane assembly/disassembly.',
        'topic_url': 'https://www.osha.gov/cranes-derricks',
    },
    {
        'key': 'steel-erection',
        'title': 'Steel Erection',
        'category': 'Construction',
        'pub': '',
        'description': 'Controlled decking zones, connector safety, and fall protection during steel work.',
        'topic_url': 'https://www.osha.gov/steel-erection',
    },
    {
        'key': 'welding',
        'title': 'Welding, Cutting & Brazing',
        'category': 'Construction',
        'pub': '',
        'description': 'Hot work permits, fire watch, ventilation, and eye/face protection.',
        'topic_url': 'https://www.osha.gov/welding-cutting-brazing',
    },
    {
        'key': 'noise',
        'title': 'Occupational Noise Exposure',
        'category': 'Health',
        'pub': '',
        'description': 'Hearing conservation program, monitoring, and hearing protection.',
        'topic_url': 'https://www.osha.gov/noise',
    },
    {
        'key': 'lockout-tagout',
        'title': 'Control of Hazardous Energy (LOTO)',
        'category': 'Construction',
        'pub': 'OSHA 3120',
        'description': 'Lockout/tagout procedures for servicing equipment and preventing unexpected energization.',
        'pdf_url': 'https://www.osha.gov/sites/default/files/publications/osha3120.pdf',
        'topic_url': 'https://www.osha.gov/control-hazardous-energy',
    },
    {
        'key': 'aerial-lifts',
        'title': 'Aerial Lifts & MEWPs',
        'category': 'Construction',
        'pub': '',
        'description': 'Fall protection on lifts, ground conditions, and operator training requirements.',
        'topic_url': 'https://www.osha.gov/aerial-lifts',
    },
    {
        'key': 'construction-focus-four',
        'title': 'Construction Focus Four Hazards',
        'category': 'Focus Four',
        'pub': '',
        'description': 'Overview of falls, struck-by, caught-in/between, and electrocution — the top construction killers.',
        'topic_url': 'https://www.osha.gov/construction/focus-four',
    },
]


def _bundled_path(bundled_file: str, static_root: str | None = None) -> str | None:
    if not bundled_file:
        return None
    root = static_root or os.path.join(os.path.dirname(__file__), 'static', 'osha')
    path = os.path.join(root, bundled_file)
    return path if os.path.isfile(path) else None


def library_for_page(static_url_for):
    """Return the library with a resolved local URL for bundled files."""
    out = []
    for item in OSHA_LIBRARY:
        entry = dict(item)
        if item.get('bundled_file'):
            entry['local_url'] = static_url_for(f"osha/{item['bundled_file']}")
            path = _bundled_path(item['bundled_file'])
            if path:
                entry['bundled_mtime'] = datetime.fromtimestamp(
                    os.path.getmtime(path), tz=timezone.utc
                ).isoformat()
        out.append(entry)
    return out


def check_library_updates(static_root: str | None = None, timeout: int = 10):
    """Compare bundled PDFs against official OSHA sources (HEAD request)."""
    checked_at = datetime.now(timezone.utc).isoformat()
    results = []
    for item in OSHA_LIBRARY:
        entry = {
            'key': item['key'],
            'title': item['title'],
            'category': item.get('category') or '',
            'pub': item.get('pub') or '',
            'has_bundled': bool(item.get('bundled_file')),
            'has_official_pdf': bool(item.get('pdf_url')),
            'topic_url': item.get('topic_url') or '',
            'status': 'reference',
            'checked_at': checked_at,
        }
        bundled_path = _bundled_path(item.get('bundled_file') or '', static_root)
        if bundled_path:
            entry['bundled_mtime'] = datetime.fromtimestamp(
                os.path.getmtime(bundled_path), tz=timezone.utc
            ).isoformat()
            entry['bundled_size'] = os.path.getsize(bundled_path)
        pdf_url = item.get('pdf_url')
        if pdf_url:
            try:
                req = urllib.request.Request(pdf_url, method='HEAD', headers={'User-Agent': 'CasePM/1.0'})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    lm = resp.headers.get('Last-Modified')
                    cl = resp.headers.get('Content-Length')
                    entry['remote_last_modified'] = lm
                    if cl:
                        try:
                            entry['remote_size'] = int(cl)
                        except (TypeError, ValueError):
                            pass
                    if lm and bundled_path:
                        remote_dt = parsedate_to_datetime(lm)
                        if remote_dt.tzinfo is None:
                            remote_dt = remote_dt.replace(tzinfo=timezone.utc)
                        local_dt = datetime.fromtimestamp(os.path.getmtime(bundled_path), tz=timezone.utc)
                        if remote_dt > local_dt:
                            entry['status'] = 'update_available'
                        else:
                            entry['status'] = 'current'
                    elif bundled_path:
                        entry['status'] = 'current'
                    else:
                        entry['status'] = 'online_only'
            except Exception as exc:
                entry['status'] = 'unreachable'
                entry['error'] = str(exc)[:160]
        elif item.get('topic_url'):
            entry['status'] = 'reference'
        results.append(entry)
    summary = {
        'checked_at': checked_at,
        'total': len(results),
        'update_available': sum(1 for r in results if r['status'] == 'update_available'),
        'current': sum(1 for r in results if r['status'] == 'current'),
        'reference': sum(1 for r in results if r['status'] in ('reference', 'online_only')),
        'unreachable': sum(1 for r in results if r['status'] == 'unreachable'),
    }
    return {'summary': summary, 'items': results}
