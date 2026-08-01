"""
Construction market segments for marketing — profile drives templates, sources, and messaging.

Based on common U.S. GC/trade market splits (residential, commercial, government/public,
industrial, healthcare, education, infrastructure, specialty subcontractor).
"""
from __future__ import annotations

from typing import Any

# Stable ids — used in settings, leads, and campaign segments
CONSTRUCTION_MARKET_IDS = (
    'residential',
    'multifamily',
    'commercial',
    'government',
    'industrial',
    'healthcare',
    'education',
    'infrastructure',
    'specialty_trade',
)

CONSTRUCTION_MARKETS: list[dict[str, Any]] = [
    {
        'id': 'residential',
        'label': 'Residential',
        'summary': 'Custom homes, remodels, additions — homeowner-led sales cycles.',
        'typical_project_types': ['Custom home', 'Remodel', 'Addition', 'Kitchen/bath'],
        'lead_sources': ['houzz', 'referral', 'website', 'paid_ads'],
        'pipeline_emphasis': 'Short cycle, visual portfolio, reviews and referrals.',
        'campaign_themes': ['seasonal_capacity', 'post_project_referral', 'design_build'],
        'content_pillars': ['before_after', 'client_testimonials', 'warranty_trust'],
        'seo_focus': ['local remodeler', 'custom home builder', 'design-build'],
        'portal_tone': 'Warm, photo-rich updates for homeowners.',
    },
    {
        'id': 'multifamily',
        'label': 'Multifamily residential',
        'summary': 'Apartments, condos, townhomes — developer and property-owner driven.',
        'typical_project_types': ['Wood-frame MF', 'Podium', 'Tenant improvement'],
        'lead_sources': ['referral', 'dodge', 'constructconnect', 'rfp'],
        'pipeline_emphasis': 'Repeat developers, pro forma and schedule proof.',
        'campaign_themes': ['developer_outreach', 'unit_delivery_milestone'],
        'content_pillars': ['schedule_metrics', 'safety', 'similar_communities'],
        'seo_focus': ['multifamily contractor', 'apartment builder'],
        'portal_tone': 'Professional; milestone and draw-friendly.',
    },
    {
        'id': 'commercial',
        'label': 'Commercial',
        'summary': 'Office, retail, mixed-use — relationship and portfolio driven.',
        'typical_project_types': ['Office TI', 'Retail', 'Mixed-use', 'Warehouse (light)'],
        'lead_sources': ['dodge', 'constructconnect', 'referral', 'rfp', 'website'],
        'pipeline_emphasis': 'RFP/ITB, case studies, team credentials.',
        'campaign_themes': ['bid_invite', 'market_sector_capabilities'],
        'content_pillars': ['case_studies', 'safety_stats', 'similar_buildings'],
        'seo_focus': ['commercial general contractor', 'TI contractor'],
        'portal_tone': 'Formal approvals and documentation.',
    },
    {
        'id': 'government',
        'label': 'Government / public',
        'summary': 'Municipal, state, federal — compliance, bonding, and formal bids.',
        'typical_project_types': ['Municipal', 'Federal', 'Public schools', 'Public safety'],
        'lead_sources': ['dodge', 'constructconnect', 'rfp', 'website'],
        'pipeline_emphasis': 'Formal procurement, DBE/MBE goals, past performance.',
        'campaign_themes': ['capabilities_statement', 'public_sector_experience'],
        'content_pillars': ['safety', 'compliance', 'public_references'],
        'seo_focus': ['municipal contractor', 'public works GC'],
        'portal_tone': 'Transparency, records, and audit-friendly updates.',
    },
    {
        'id': 'industrial',
        'label': 'Industrial',
        'summary': 'Manufacturing, distribution, process — technical and schedule critical.',
        'typical_project_types': ['Manufacturing plant', 'Distribution center', 'Process'],
        'lead_sources': ['dodge', 'constructconnect', 'referral', 'rfp'],
        'pipeline_emphasis': 'Technical qualifications, shutdown windows.',
        'campaign_themes': ['industrial_capabilities', 'safety_zero_incident'],
        'content_pillars': ['complexity_solved', 'schedule', 'team_certs'],
        'seo_focus': ['industrial contractor', 'plant construction'],
        'portal_tone': 'Safety and commissioning focused.',
    },
    {
        'id': 'healthcare',
        'label': 'Healthcare',
        'summary': 'Hospitals, clinics, MOBs — ICRA, infection control, occupied facilities.',
        'typical_project_types': ['Hospital', 'Clinic', 'MOB', 'Renovation (occupied)'],
        'lead_sources': ['dodge', 'constructconnect', 'referral', 'rfp'],
        'pipeline_emphasis': 'Healthcare references, safety, phased work.',
        'campaign_themes': ['healthcare_experience', 'occupied_renovation'],
        'content_pillars': ['healthcare_portfolio', 'safety', 'minimal_disruption'],
        'seo_focus': ['healthcare construction', 'hospital contractor'],
        'portal_tone': 'Clinical stakeholder communication.',
    },
    {
        'id': 'education',
        'label': 'Education',
        'summary': 'K-12, higher ed, bond programs — seasonal and community visibility.',
        'typical_project_types': ['K-12', 'Higher ed', 'Athletic', 'Bond program'],
        'lead_sources': ['dodge', 'constructconnect', 'rfp', 'referral'],
        'pipeline_emphasis': 'Summer/winter breaks, bond messaging, community trust.',
        'campaign_themes': ['back_to_school_readiness', 'bond_program_delivery'],
        'content_pillars': ['education_portfolio', 'safety', 'community'],
        'seo_focus': ['school construction', 'campus contractor'],
        'portal_tone': 'District-friendly updates and approvals.',
    },
    {
        'id': 'infrastructure',
        'label': 'Infrastructure / heavy civil',
        'summary': 'Roads, bridges, utilities, water — public funding and DOT work.',
        'typical_project_types': ['Highway', 'Bridge', 'Utility', 'Water/wastewater'],
        'lead_sources': ['dodge', 'constructconnect', 'rfp', 'website'],
        'pipeline_emphasis': 'Past performance, equipment, bonding.',
        'campaign_themes': ['public_infrastructure', 'safety_record'],
        'content_pillars': ['project_scale', 'community_benefit', 'safety'],
        'seo_focus': ['heavy civil contractor', 'infrastructure'],
        'portal_tone': 'Public communication and milestone focused.',
    },
    {
        'id': 'specialty_trade',
        'label': 'Specialty trade / subcontractor',
        'summary': 'Single-trade focus — GC relationships, takeoff, and service area.',
        'typical_project_types': ['Electrical', 'Mechanical', 'Concrete', 'Roofing', 'Other trade'],
        'lead_sources': ['referral', 'website', 'rfp', 'paid_ads'],
        'pipeline_emphasis': 'GC partnerships, service area, responsiveness.',
        'campaign_themes': ['gc_partner_outreach', 'service_area_capacity'],
        'content_pillars': ['trade_expertise', 'safety', 'crew_capacity'],
        'seo_focus': ['subcontractor', 'commercial trade contractor'],
        'portal_tone': 'Light client portal; GC coordination emphasis.',
    },
]

_MARKET_BY_ID = {m['id']: m for m in CONSTRUCTION_MARKETS}


def construction_markets_catalog() -> dict:
    return {
        'markets': CONSTRUCTION_MARKETS,
        'ids': list(CONSTRUCTION_MARKET_IDS),
        'default_id': 'commercial',
        'note': 'Set primary_construction_market in marketing settings to tailor templates and messaging.',
    }


def get_construction_market(market_id: str | None) -> dict:
    mid = (market_id or '').strip().lower()
    if mid not in _MARKET_BY_ID:
        mid = 'commercial'
    return dict(_MARKET_BY_ID[mid])


def resolve_marketing_markets(settings: dict) -> dict:
    primary = (settings.get('primary_construction_market') or 'commercial').strip().lower()
    if primary not in _MARKET_BY_ID:
        primary = 'commercial'
    secondary = settings.get('secondary_construction_markets') or []
    if isinstance(secondary, str):
        import json
        try:
            secondary = json.loads(secondary)
        except Exception:
            secondary = []
    secondary = [s for s in secondary if s in _MARKET_BY_ID and s != primary]
    return {
        'primary': primary,
        'secondary': secondary,
        'primary_profile': get_construction_market(primary),
        'secondary_profiles': [get_construction_market(s) for s in secondary],
    }


def marketing_scheme_payload(settings: dict) -> dict:
    """UI-ready scheme: how marketing should be formatted for this firm."""
    resolved = resolve_marketing_markets(settings)
    p = resolved['primary_profile']
    return {
        'resolved': resolved,
        'scheme': {
            'headline': f"Marketing profile: {p['label']}",
            'summary': p['summary'],
            'recommended_lead_sources': p['lead_sources'],
            'recommended_project_types': p['typical_project_types'],
            'campaign_themes': p['campaign_themes'],
            'content_pillars': p['content_pillars'],
            'seo_focus': p['seo_focus'],
            'portal_tone': p['portal_tone'],
            'pipeline_emphasis': p['pipeline_emphasis'],
        },
        'segment_defaults': {
            'source': p['lead_sources'][0] if p['lead_sources'] else 'website',
            'project_type': p['typical_project_types'][0] if p['typical_project_types'] else '',
        },
    }


def market_landing_hero(market_id: str) -> dict:
    p = get_construction_market(market_id)
    headlines = {
        'residential': ('Your home, built with care', 'Remodels, additions, and custom homes'),
        'multifamily': ('Multifamily delivery you can underwrite', 'Schedule certainty for developers'),
        'commercial': ('Commercial construction partner', 'Office, retail, and mixed-use'),
        'government': ('Trusted public sector builder', 'Compliance, safety, and transparent delivery'),
        'industrial': ('Industrial & manufacturing builds', 'Technical complexity, disciplined execution'),
        'healthcare': ('Healthcare construction specialists', 'Safe delivery in occupied facilities'),
        'education': ('Education facility experts', 'K-12, campus, and bond program experience'),
        'infrastructure': ('Infrastructure & civil', 'Roads, utilities, and public works'),
        'specialty_trade': ('Specialty trade partner', 'Responsive crews, GC-ready documentation'),
    }
    h, sub = headlines.get(market_id, ('Quality construction', p['summary'][:80]))
    return {'type': 'hero', 'headline': h, 'sub': sub, 'market_id': market_id}


def market_campaign_templates(market_id: str) -> list[tuple[str, str, str, str]]:
    """key, name, subject, body_html"""
    p = get_construction_market(market_id)
    label = p['label']
    return [
        (
            f'market_{market_id}_intro',
            f'{label} — introduction',
            f'{label} capabilities',
            f'<p>We specialize in {label.lower()} work. {{project_type}} in {{city}} is a strong fit for our team.</p>',
        ),
        (
            f'market_{market_id}_portfolio',
            f'{label} — portfolio highlight',
            'Recent project highlights',
            f'<p>See how we deliver {label.lower()} projects on schedule with clear communication.</p>',
        ),
        (
            f'market_{market_id}_review',
            f'{label} — review request',
            'How did we do?',
            '<p>Your feedback helps other owners choose the right team. Thank you for trusting us.</p>',
        ),
    ]


def market_content_blocks(market_id: str) -> list[tuple[str, str, str]]:
    """category, title, body_html"""
    p = get_construction_market(market_id)
    return [
        (
            'company_story',
            f'Why {p["label"]}',
            f'<p>{p["summary"]}</p><p><em>{p["pipeline_emphasis"]}</em></p>',
        ),
        (
            'safety',
            f'Safety on {p["label"].lower()} jobs',
            '<p>Documented safety program, toolbox talks, and job-specific planning on every site.</p>',
        ),
        (
            'market_fit',
            'Project types we pursue',
            '<ul>' + ''.join(f'<li>{t}</li>' for t in p['typical_project_types'][:6]) + '</ul>',
        ),
    ]


def apply_construction_market_scheme(db, models, market_id: str, *, secondary: list[str] | None = None) -> dict:
    """
    Seed/update market-specific campaign templates and content blocks.
    Caller should save settings (primary_construction_market) separately.
    """
    from marketing_pillars import upsert_landing_page

    MarketingCampaignTemplate = models['MarketingCampaignTemplate']
    MarketingContentBlock = models['MarketingContentBlock']
    MarketingLandingPage = models.get('MarketingLandingPage')
    MarketingCaseStudy = models.get('MarketingCaseStudy')

    mid = market_id if market_id in _MARKET_BY_ID else 'commercial'
    created = {'templates': 0, 'content': 0, 'landing': False}

    for key, name, subject, html in market_campaign_templates(mid):
        row = MarketingCampaignTemplate.query.filter_by(key=key).first()
        if not row:
            db.session.add(MarketingCampaignTemplate(
                key=key, name=name, channel='email', subject=subject, body_html=html,
                body_text=subject, segment_json='{"stage": "inquiry"}',
            ))
            created['templates'] += 1
        else:
            row.name = name
            row.subject = subject
            row.body_html = html

    for cat, title, html in market_content_blocks(mid):
        row = MarketingContentBlock.query.filter_by(category=cat, title=title).first()
        if not row:
            db.session.add(MarketingContentBlock(category=cat, title=title, body_html=html, sort_order=0))
            created['content'] += 1

    if MarketingLandingPage and MarketingCaseStudy:
        hero = market_landing_hero(mid)
        studies = MarketingCaseStudy.query.filter_by(status='published').limit(6).all()
        existing_home = MarketingLandingPage.query.filter_by(slug='home').first()
        upsert_landing_page(db, MarketingLandingPage, {
            'slug': 'home',
            'title': f'Case PM — {get_construction_market(mid)["label"]}',
            'sections': [
                hero,
                {'type': 'portfolio', 'case_study_ids': [c.id for c in studies]},
                {'type': 'cta', 'text': 'Request a consultation'},
            ],
            'lead_form': {'fields': ['contact_name', 'email', 'phone', 'notes'], 'construction_market': mid},
            'seo': {
                'title': get_construction_market(mid)['seo_focus'][0] if get_construction_market(mid)['seo_focus'] else '',
                'description': get_construction_market(mid)['summary'],
                'keywords': get_construction_market(mid)['seo_focus'],
            },
            'status': 'published',
        }, page_id=existing_home.id if existing_home else None)
        created['landing'] = True

    db.session.flush()
    created['market_id'] = mid
    created['secondary'] = secondary or []
    return created


def default_lead_fields_for_market(settings: dict) -> dict:
    scheme = marketing_scheme_payload(settings)
    return {
        'source': scheme['segment_defaults']['source'],
        'project_type': scheme['segment_defaults']['project_type'],
        'construction_market': resolve_marketing_markets(settings)['primary'],
    }
