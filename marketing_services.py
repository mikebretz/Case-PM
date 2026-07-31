"""Construction marketing services — portfolio, pipeline, reputation, campaigns, DAM."""
from __future__ import annotations

import json
import re
from datetime import datetime

from marketing_models import MARKETING_LEAD_SOURCES, MARKETING_LEAD_STAGES


def _json_load(raw, default=None):
    if default is None:
        default = {}
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _slugify(text: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return (s[:100] or 'case-study')


def lead_to_dict(row) -> dict:
    return {
        'id': row.id,
        'title': row.title,
        'contact_name': row.contact_name,
        'email': row.email,
        'phone': row.phone,
        'company_name': row.company_name,
        'source': row.source,
        'stage': row.stage,
        'probability': row.probability,
        'estimated_value': row.estimated_value,
        'project_type': row.project_type,
        'construction_market': getattr(row, 'construction_market', None),
        'location_city': row.location_city,
        'location_state': row.location_state,
        'project_id': row.project_id,
        'estimate_id': row.estimate_id,
        'referral_lead_id': row.referral_lead_id,
        'notes': row.notes,
        'metadata': _json_load(row.metadata_json),
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
        'closed_at': row.closed_at.isoformat() if row.closed_at else None,
    }


def list_leads(db, MarketingLead, *, stage: str | None = None, limit: int = 200) -> dict:
    q = MarketingLead.query.order_by(MarketingLead.updated_at.desc())
    if stage:
        q = q.filter_by(stage=stage)
    rows = q.limit(limit).all()
    return {'leads': [lead_to_dict(r) for r in rows], 'stages': list(MARKETING_LEAD_STAGES), 'sources': list(MARKETING_LEAD_SOURCES)}


def upsert_lead(db, MarketingLead, body: dict, *, user_id=None, lead_id: int | None = None) -> dict:
    if lead_id:
        row = MarketingLead.query.get(int(lead_id))
        if not row:
            raise ValueError('Lead not found')
    else:
        row = MarketingLead(created_by_id=user_id)
        db.session.add(row)
    for field in (
        'title', 'contact_name', 'email', 'phone', 'company_name', 'notes',
        'project_type', 'location_city', 'location_state', 'construction_market',
    ):
        if field in body:
            setattr(row, field, (body.get(field) or '')[:300] if field != 'notes' else body.get(field))
    if 'source' in body and body['source'] in MARKETING_LEAD_SOURCES:
        row.source = body['source']
    if 'stage' in body and body['stage'] in MARKETING_LEAD_STAGES:
        row.stage = body['stage']
        if body['stage'] in ('won', 'lost'):
            row.closed_at = datetime.utcnow()
    if 'probability' in body:
        row.probability = max(0, min(100, int(body['probability'])))
    if 'estimated_value' in body:
        row.estimated_value = round(float(body['estimated_value'] or 0), 2)
    if 'project_id' in body:
        row.project_id = int(body['project_id']) if body.get('project_id') else None
    if 'estimate_id' in body:
        row.estimate_id = int(body['estimate_id']) if body.get('estimate_id') else None
    if 'metadata' in body:
        row.metadata_json = json.dumps(body['metadata'] or {})
    if 'construction_market' in body and body.get('construction_market'):
        row.construction_market = str(body['construction_market'])[:40]
    elif not lead_id:
        try:
            from marketing_construction_markets import default_lead_fields_for_market
            from marketing_pillars import load_marketing_settings
            defaults = default_lead_fields_for_market(load_marketing_settings())
            row.construction_market = defaults.get('construction_market')
            if 'source' not in body and defaults.get('source') in MARKETING_LEAD_SOURCES:
                row.source = defaults['source']
            if not row.project_type and defaults.get('project_type'):
                row.project_type = defaults['project_type'][:80]
        except Exception:
            pass
    if not row.title:
        row.title = (body.get('contact_name') or body.get('company_name') or 'New lead')[:300]
    row.updated_at = datetime.utcnow()
    db.session.flush()
    out = lead_to_dict(row)
    try:
        from marketing_pillars import load_marketing_settings
        from marketing_integrations import push_lead_to_crm
        if load_marketing_settings().get('crm_auto_push'):
            push_lead_to_crm(out)
    except Exception:
        pass
    return out


def move_lead_stage(db, MarketingLead, lead_id: int, stage: str, *, user_id=None) -> dict:
    return upsert_lead(db, MarketingLead, {'stage': stage}, user_id=user_id, lead_id=lead_id)


def convert_lead_to_estimate(db, MarketingLead, Estimate, Project, lead_id: int, *, user_id=None) -> dict:
    lead = MarketingLead.query.get(int(lead_id))
    if not lead:
        raise ValueError('Lead not found')
    pid = lead.project_id
    if not pid:
        proj = Project(
            name=(lead.title or 'New opportunity')[:200],
            client=lead.company_name or lead.contact_name,
            city=lead.location_city,
            state=lead.location_state,
            status='Bidding',
            project_type=lead.project_type,
            contract_value=lead.estimated_value,
        )
        db.session.add(proj)
        db.session.flush()
        pid = proj.id
        lead.project_id = pid
    est = Estimate(
        project_id=pid,
        title=f"Estimate — {lead.title}"[:200],
        status='Draft',
        created_by_id=user_id,
    )
    db.session.add(est)
    db.session.flush()
    lead.estimate_id = est.id
    lead.stage = 'proposal'
    lead.probability = max(lead.probability or 0, 40)
    lead.updated_at = datetime.utcnow()
    return {'lead': lead_to_dict(lead), 'estimate_id': est.id, 'project_id': pid}


def pipeline_analytics(db, MarketingLead) -> dict:
    leads = MarketingLead.query.all()
    by_stage = {s: [] for s in MARKETING_LEAD_STAGES}
    by_source = {}
    weighted = 0.0
    for L in leads:
        by_stage.setdefault(L.stage or 'inquiry', []).append(L)
        by_source[L.source or 'other'] = by_source.get(L.source or 'other', 0) + 1
        if L.stage not in ('won', 'lost'):
            weighted += float(L.estimated_value or 0) * (int(L.probability or 0) / 100.0)
    won = len(by_stage.get('won', []))
    lost = len(by_stage.get('lost', []))
    closed = won + lost
    return {
        'at': datetime.utcnow().isoformat() + 'Z',
        'lead_count': len(leads),
        'pipeline_weighted_value': round(weighted, 2),
        'by_stage': {k: len(v) for k, v in by_stage.items()},
        'by_source': by_source,
        'win_rate': round(won / closed, 3) if closed else None,
        'forecast_note': 'Weighted value = open opportunities × probability%.',
    }


def case_study_to_dict(row) -> dict:
    return {
        'id': row.id,
        'project_id': row.project_id,
        'title': row.title,
        'slug': row.slug,
        'status': row.status,
        'summary': row.summary,
        'metrics': _json_load(row.metrics_json),
        'tags': _json_load(row.tags_json, []),
        'team_credits': _json_load(row.team_credits_json, []),
        'gallery': _json_load(getattr(row, 'gallery_json', None), []),
        'before_after': _json_load(getattr(row, 'before_after_json', None), []),
        'videos': _json_load(getattr(row, 'videos_json', None), []),
        'client_type': getattr(row, 'client_type', None),
        'style_tags': _json_load(getattr(row, 'style_tags_json', None), []),
        'challenges': _json_load(getattr(row, 'challenges_json', None), []),
        'view_count': int(getattr(row, 'view_count', None) or 0),
        'template_key': row.template_key,
        'version': row.version,
        'published_at': row.published_at.isoformat() if row.published_at else None,
    }


def build_case_study_from_project(
    db, MarketingCaseStudy, Project, Photo, BudgetProjectState, PayAppProjectState,
    project_id: int, *, user_id=None, title: str | None = None,
) -> dict:
    proj = Project.query.get(int(project_id))
    if not proj:
        raise ValueError('Project not found')
    photos = Photo.query.filter_by(project_id=proj.id).order_by(Photo.created_at.desc()).limit(24).all()
    metrics = {
        'contract_value': proj.contract_value,
        'percent_complete': proj.percent_complete,
        'start_date': proj.start_date.isoformat() if proj.start_date else None,
        'end_date': proj.end_date.isoformat() if proj.end_date else None,
        'location': proj.location_label() if hasattr(proj, 'location_label') else f'{proj.city}, {proj.state}',
        'photo_count': len(photos),
    }
    try:
        from budget_persistence import get_budget_state
        _, budget = get_budget_state(BudgetProjectState, proj.id) if BudgetProjectState else (None, {})
        if budget:
            metrics['budget_original'] = sum(
                float(l.get('original_budget') or l.get('original') or 0)
                for l in (budget.get('budgetLines') or []) if isinstance(l, dict)
            )
    except Exception:
        pass
    tags = [t for t in [proj.project_type, proj.stage, proj.status] if t]
    summary_parts = [
        f"{proj.name} — {proj.client or 'Client'}",
        (proj.description or '').strip()[:500],
    ]
    existing = MarketingCaseStudy.query.filter_by(project_id=proj.id).order_by(MarketingCaseStudy.version.desc()).first()
    version = (existing.version + 1) if existing else 1
    row = MarketingCaseStudy(
        project_id=proj.id,
        title=(title or f"{proj.name} — Portfolio")[:300],
        slug=_slugify(proj.name),
        status='draft',
        summary='\n\n'.join(p for p in summary_parts if p),
        metrics_json=json.dumps(metrics),
        tags_json=json.dumps(tags),
        team_credits_json=json.dumps([{'role': 'Project Manager', 'name': proj.project_manager}] if proj.project_manager else []),
        version=version,
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    try:
        from marketing_pillars import enrich_case_study_from_project
        enrich_case_study_from_project(db, MarketingCaseStudy, row, Project, Photo)
    except Exception:
        pass
    out = case_study_to_dict(row)
    out['photo_ids'] = [p.id for p in photos]
    out['embed_html'] = export_case_study_html(row, photos)
    return out


def export_case_study_html(case_study, photos=None) -> str:
    metrics = _json_load(case_study.metrics_json)
    tags = _json_load(case_study.tags_json, [])
    imgs = ''
    if photos:
        for p in photos[:12]:
            imgs += f'<figure><img src="/uploads/photos/{p.project_id}/{p.filename}" alt="" style="max-width:100%;margin:8px 0"/><figcaption>{p.caption or ""}</figcaption></figure>'
    return f"""<article class="case-study" data-slug="{case_study.slug}">
<h1>{case_study.title}</h1>
<p class="tags">{', '.join(tags)}</p>
<div class="summary">{case_study.summary or ''}</div>
<ul class="metrics">
<li>Contract: {metrics.get('contract_value')}</li>
<li>Complete: {metrics.get('percent_complete')}%</li>
<li>Location: {metrics.get('location')}</li>
</ul>
<div class="gallery">{imgs}</div>
</article>"""


def list_case_studies(db, MarketingCaseStudy, *, status: str | None = None, limit: int = 100) -> dict:
    q = MarketingCaseStudy.query.order_by(MarketingCaseStudy.created_at.desc())
    if status:
        q = q.filter_by(status=status)
    return {'case_studies': [case_study_to_dict(r) for r in q.limit(limit).all()]}


def publish_case_study(db, MarketingCaseStudy, case_study_id: int) -> dict:
    row = MarketingCaseStudy.query.get(int(case_study_id))
    if not row:
        raise ValueError('Case study not found')
    row.status = 'published'
    row.published_at = datetime.utcnow()
    return case_study_to_dict(row)


def sync_dam_from_project_photos(db, MarketingAsset, Photo, project_id: int, *, user_id=None) -> dict:
    created = 0
    for p in Photo.query.filter_by(project_id=int(project_id)).order_by(Photo.id.desc()).limit(100).all():
        exists = MarketingAsset.query.filter_by(photo_id=p.id).first()
        if exists:
            continue
        tags = [x for x in [p.category, p.location] if x]
        row = MarketingAsset(
            project_id=p.project_id,
            photo_id=p.id,
            title=(p.caption or p.filename or f'Photo {p.id}')[:300],
            asset_type='photo',
            tags_json=json.dumps(tags),
            use_cases_json=json.dumps(['portfolio', 'proposal', 'social']),
            created_by_id=user_id,
        )
        db.session.add(row)
        created += 1
    db.session.flush()
    return {'synced': created}


def list_marketing_assets(
    db, MarketingAsset, Photo, *, project_id: int | None = None, tag: str | None = None, limit: int = 200,
) -> dict:
    q = MarketingAsset.query.order_by(MarketingAsset.id.desc())
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    rows = q.limit(limit).all()
    assets = []
    for r in rows:
        tags = _json_load(r.tags_json, [])
        if tag and tag not in tags:
            continue
        preview_url = None
        if r.photo_id and Photo:
            ph = Photo.query.get(r.photo_id)
            if ph and ph.filename:
                preview_url = f'/uploads/photos/{r.project_id}/{ph.filename}'
        assets.append({
            'id': r.id,
            'project_id': r.project_id,
            'photo_id': r.photo_id,
            'title': r.title,
            'asset_type': r.asset_type,
            'tags': tags,
            'use_cases': _json_load(r.use_cases_json, []),
            'preview_url': preview_url,
        })
    return {'assets': assets, 'count': len(assets)}


def capture_public_lead(db, MarketingLead, body: dict) -> dict:
    payload = {
        'title': body.get('title') or body.get('project_description') or 'Website inquiry',
        'contact_name': body.get('contact_name') or body.get('name'),
        'email': body.get('email'),
        'phone': body.get('phone'),
        'company_name': body.get('company_name'),
        'project_type': body.get('project_type'),
        'location_city': body.get('location_city') or body.get('city'),
        'location_state': body.get('location_state') or body.get('state'),
        'notes': body.get('notes') or body.get('message'),
        'source': body.get('source') if body.get('source') in MARKETING_LEAD_SOURCES else 'website',
        'stage': 'inquiry',
        'estimated_value': body.get('estimated_value') or 0,
        'metadata': {
            'utm': body.get('utm') or {},
            'landing_page_id': body.get('landing_page_id'),
            'campaign_id': body.get('campaign_id'),
        },
    }
    out = upsert_lead(db, MarketingLead, payload)
    if body.get('landing_page_id'):
        lead = MarketingLead.query.get(out['id'])
        if lead:
            lead.landing_page_id = int(body['landing_page_id'])
            lead.attribution_json = json.dumps(payload['metadata'])
            db.session.flush()
            out = lead_to_dict(lead)
    return out


def published_case_study_by_slug(db, MarketingCaseStudy, Photo, slug: str) -> dict | None:
    row = MarketingCaseStudy.query.filter_by(slug=slug, status='published').order_by(
        MarketingCaseStudy.version.desc(),
    ).first()
    if not row:
        return None
    photos = []
    if Photo and row.project_id:
        photos = Photo.query.filter_by(project_id=row.project_id).order_by(Photo.created_at.desc()).limit(12).all()
    out = case_study_to_dict(row)
    out['embed_html'] = export_case_study_html(row, photos)
    return out


def create_review_request(db, MarketingReviewRequest, body: dict, *, user_id=None) -> dict:
    import secrets
    row = MarketingReviewRequest(
        project_id=int(body['project_id']),
        company_id=body.get('company_id'),
        platform=(body.get('platform') or 'google')[:40],
        status='pending',
        referral_incentive=(body.get('referral_incentive') or '')[:120],
        client_email=(body.get('client_email') or body.get('email') or '')[:200],
        access_token=secrets.token_urlsafe(24),
        trigger_milestone=(body.get('trigger_milestone') or '')[:80],
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    return review_to_dict(row)


def send_review_request_email(db, MarketingReviewRequest, review_id: int, email: str) -> dict:
    from email_notifications import send_workflow_email

    row = MarketingReviewRequest.query.get(int(review_id))
    if not row:
        raise ValueError('Review request not found')
    if not (email or '').strip():
        raise ValueError('email required')
    review_url = f'/public/marketing/review/{row.access_token}' if row.access_token else ''
    body = (
        f"Thank you for working with us on project #{row.project_id}. "
        "We would appreciate a brief review of your experience."
    )
    html = f'<p>{body}</p>'
    if review_url:
        html += f'<p><a href="{review_url}">Leave your feedback</a></p>'
    sent = send_workflow_email(email.strip(), 'Case PM — project feedback request', html, body + (f' {review_url}' if review_url else ''))
    row.status = 'sent'
    return {'sent': sent, 'review_id': row.id}


def complete_review(db, MarketingReviewRequest, review_id: int, body: dict) -> dict:
    row = MarketingReviewRequest.query.get(int(review_id))
    if not row:
        raise ValueError('Review request not found')
    row.rating = int(body['rating']) if body.get('rating') is not None else row.rating
    row.testimonial_text = (body.get('testimonial_text') or row.testimonial_text or '')[:4000]
    row.public_share_ok = bool(body.get('public_share_ok'))
    row.status = 'completed'
    row.completed_at = datetime.utcnow()
    return review_to_dict(row)


def review_to_dict(row) -> dict:
    return {
        'id': row.id,
        'project_id': row.project_id,
        'platform': row.platform,
        'status': row.status,
        'rating': row.rating,
        'testimonial_text': row.testimonial_text,
        'public_share_ok': row.public_share_ok,
        'referral_incentive': row.referral_incentive,
        'requested_at': row.requested_at.isoformat() if row.requested_at else None,
        'completed_at': row.completed_at.isoformat() if row.completed_at else None,
    }


def list_reviews(db, MarketingReviewRequest, *, public_only: bool = False, limit: int = 100) -> dict:
    q = MarketingReviewRequest.query.filter_by(status='completed').order_by(MarketingReviewRequest.completed_at.desc())
    rows = q.limit(limit).all()
    if public_only:
        rows = [r for r in rows if r.public_share_ok]
    return {'reviews': [review_to_dict(r) for r in rows]}


def campaign_to_dict(row) -> dict:
    return {
        'id': row.id,
        'name': row.name,
        'channel': row.channel,
        'segment': _json_load(row.segment_json),
        'subject': row.subject,
        'status': row.status,
        'stats': _json_load(row.stats_json),
        'sent_at': row.sent_at.isoformat() if row.sent_at else None,
    }


def upsert_campaign(db, MarketingCampaign, body: dict, *, user_id=None, campaign_id: int | None = None) -> dict:
    if campaign_id:
        row = MarketingCampaign.query.get(int(campaign_id))
        if not row:
            raise ValueError('Campaign not found')
    else:
        row = MarketingCampaign(created_by_id=user_id)
        db.session.add(row)
    for field in ('name', 'channel', 'subject', 'body_html', 'body_text', 'status'):
        if field in body:
            setattr(row, field, body.get(field))
    if 'segment' in body:
        row.segment_json = json.dumps(body['segment'] or {})
    db.session.flush()
    return campaign_to_dict(row)


def send_campaign(db, MarketingCampaign, MarketingLead, campaign_id: int, *, test_email: str | None = None) -> dict:
    from email_notifications import send_workflow_email

    row = MarketingCampaign.query.get(int(campaign_id))
    if not row:
        raise ValueError('Campaign not found')
    segment = _json_load(row.segment_json)
    recipients = []
    if test_email:
        recipients = [test_email.strip()]
    else:
        stage = segment.get('stage')
        source = segment.get('source')
        q = MarketingLead.query
        if stage:
            q = q.filter_by(stage=stage)
        if source:
            q = q.filter_by(source=source)
        recipients = [l.email for l in q.limit(200).all() if (l.email or '').strip()]
    sent = 0
    for email in recipients[:100]:
        if send_workflow_email(email, row.subject or row.name, row.body_html or f'<pre>{row.body_text}</pre>', row.body_text or ''):
            sent += 1
    row.status = 'sent'
    row.sent_at = datetime.utcnow()
    row.stats_json = json.dumps({'recipients': len(recipients), 'sent': sent})
    return campaign_to_dict(row)


def marketing_roi_dashboard(db, MarketingLead, MarketingCampaign, Project) -> dict:
    pipe = pipeline_analytics(db, MarketingLead)
    campaigns = MarketingCampaign.query.filter_by(status='sent').count()
    won_leads = MarketingLead.query.filter_by(stage='won').all()
    revenue_attributed = sum(float(L.estimated_value or 0) for L in won_leads)
    return {
        **pipe,
        'campaigns_sent': campaigns,
        'won_revenue_attributed': round(revenue_attributed, 2),
        'active_projects': Project.query.filter_by(status='Active').count() if Project else 0,
    }


def seed_collateral_templates(db, MarketingCollateralTemplate) -> dict:
    defaults = [
        ('default', 'Standard case study', '<h1>{{title}}</h1><p>{{summary}}</p>'),
        ('proposal', 'Proposal cover', '<h1>{{company}}</h1><p>{{project_name}}</p><p>{{safety_stats}}</p>'),
    ]
    created = 0
    for key, name, html in defaults:
        if MarketingCollateralTemplate.query.filter_by(key=key).first():
            continue
        db.session.add(MarketingCollateralTemplate(key=key, name=name, body_html=html))
        created += 1
    if created:
        db.session.flush()
    return {'seeded': created}


def marketing_module_catalog() -> dict:
    """Maps research pillars to implementation status."""
    from marketing_construction_markets import construction_markets_catalog
    return {
        'product': 'Case PM Marketing',
        'construction_markets': construction_markets_catalog(),
        'pillars': [
            {'id': 'portfolio', 'title': 'Project portfolio & case studies', 'status': 'live'},
            {'id': 'pipeline', 'title': 'Lead & opportunity pipeline', 'status': 'live'},
            {'id': 'portal_marketing', 'title': 'Client portal + reviews', 'status': 'live'},
            {'id': 'reputation', 'title': 'Reputation & referral tracking', 'status': 'live'},
            {'id': 'campaigns', 'title': 'Email & SMS campaign automation', 'status': 'live'},
            {'id': 'dam', 'title': 'Visual asset management', 'status': 'live'},
            {'id': 'collateral', 'title': 'Proposal & collateral tools', 'status': 'live'},
            {'id': 'web_leads', 'title': 'Website & lead capture', 'status': 'live'},
            {'id': 'analytics', 'title': 'Marketing ROI dashboards', 'status': 'live'},
            {'id': 'integrations', 'title': 'Houzz / Dodge / CRM integrations', 'status': 'live'},
        ],
        'doc': 'docs/MARKETING_MODULE.md',
    }


def marketing_deploy_check() -> dict:
    try:
        import marketing_services as ms  # noqa: F401
        import marketing_models  # noqa: F401
        from marketing_pillars import pillars_deploy_check

        assert callable(ms.build_case_study_from_project)
        assert callable(ms.pipeline_analytics)
        pillar = pillars_deploy_check()
        if not pillar.get('ok'):
            return pillar
        from marketing_gaps import gaps_deploy_check
        gap = gaps_deploy_check()
        if not gap.get('ok'):
            return gap
        from marketing_construction_markets import construction_markets_catalog
        assert construction_markets_catalog().get('markets')
        return {'ok': True}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:200]}
