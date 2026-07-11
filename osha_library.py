"""Curated OSHA safety reference library shown on the Safety page.

Bundled items ship as PDFs in static/osha and are always available offline.
Reference items link to official OSHA pages/publications and can be saved into the
project's Documents on demand.
"""
from __future__ import annotations

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
]


def library_for_page(static_url_for):
    """Return the library with a resolved local URL for bundled files."""
    out = []
    for item in OSHA_LIBRARY:
        entry = dict(item)
        if item.get('bundled_file'):
            entry['local_url'] = static_url_for(f"osha/{item['bundled_file']}")
        out.append(entry)
    return out
