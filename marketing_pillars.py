"""Marketing pillars 1–9 — portfolio, pipeline, portal, reputation, campaigns, DAM, proposals, web, analytics."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from urllib.parse import quote

from marketing_models import MARKETING_LEAD_STAGES, MARKETING_LEAD_SOURCES
from marketing_services import (
    _json_load,
    _slugify,
    case_study_to_dict,
    export_case_study_html,
    lead_to_dict,
    pipeline_analytics,
    review_to_dict,
)


def _token() -> str:
    return secrets.token_urlsafe(24)


def _base_url() -> str:
    return (os.environ.get('CASEPM_PUBLIC_BASE_URL') or '').rstrip('/') or ''


def seed_marketing_defaults(db, models) -> dict:
    """Campaign templates, automation rules, content library."""
    MarketingCampaignTemplate = models['MarketingCampaignTemplate']
    MarketingAutomationRule = models['MarketingAutomationRule']
    MarketingContentBlock = models['MarketingContentBlock']
    created = {'templates': 0, 'rules': 0, 'content': 0}

    templates = [
        ('seasonal', 'Seasonal outreach', 'Seasonal maintenance and project availability', '<p>Hello {{name}},</p><p>We have capacity this season for {{project_type}} work in {{city}}.</p>'),
        ('post_project', 'Post-project follow-up', 'Thank you and referral ask', '<p>Thank you for trusting us on {{project_name}}.</p><p>If you know someone planning a project, we would appreciate an introduction.</p>'),
        ('bid_invite', 'Bid invitation', 'Invite to preconstruction', '<p>We are bidding {{project_name}} and would value your input on scope.</p>'),
    ]
    for key, name, subject, html in templates:
        if MarketingCampaignTemplate.query.filter_by(key=key).first():
            continue
        db.session.add(MarketingCampaignTemplate(
            key=key, name=name, channel='email', subject=subject, body_html=html, body_text=re.sub('<[^>]+>', '', html),
            segment_json=json.dumps({'stage': 'inquiry'}),
        ))
        created['templates'] += 1

    rules = [
        ('Project closeout review', 'project_status', 'Complete', 'review_request', {'platform': 'google'}),
        ('90% complete review', 'project_percent', '90', 'review_request', {'platform': 'google'}),
    ]
    for name, ttype, tval, atype, acfg in rules:
        if MarketingAutomationRule.query.filter_by(name=name).first():
            continue
        db.session.add(MarketingAutomationRule(
            name=name, trigger_type=ttype, trigger_value=tval, action_type=atype,
            action_config_json=json.dumps(acfg), enabled=True,
        ))
        created['rules'] += 1

    blocks = [
        ('company_story', 'Our story', '<p>We deliver quality construction with transparent communication from bid through closeout.</p>'),
        ('safety', 'Safety record', '<p>EMR-focused safety program with daily toolbox talks and documented observations.</p>'),
        ('sustainability', 'Sustainability', '<p>Waste diversion, efficient equipment, and durable materials on every job.</p>'),
        ('team_bio', 'Leadership', '<p>Experienced project managers and superintendents on every active project.</p>'),
    ]
    for cat, title, html in blocks:
        if MarketingContentBlock.query.filter_by(category=cat, title=title).first():
            continue
        db.session.add(MarketingContentBlock(category=cat, title=title, body_html=html, sort_order=0))
        created['content'] += 1

    if any(created.values()):
        db.session.flush()
    return created


def enrich_case_study_from_project(
    db, MarketingCaseStudy, row, Project, Photo, *, body: dict | None = None,
) -> dict:
    body = body or {}
    proj = Project.query.get(row.project_id)
    photos = Photo.query.filter_by(project_id=row.project_id).order_by(Photo.created_at.desc()).limit(36).all()
    gallery = [{'photo_id': p.id, 'caption': p.caption, 'url': f'/uploads/photos/{p.project_id}/{p.filename}'} for p in photos]
    before_after = body.get('before_after') or _json_load(getattr(row, 'before_after_json', None), [])
    if not before_after and len(photos) >= 2:
        before_after = [{'label': 'Before', 'photo_id': photos[-1].id}, {'label': 'After', 'photo_id': photos[0].id}]
    videos = body.get('videos') or _json_load(getattr(row, 'videos_json', None), [])
    row.gallery_json = json.dumps(gallery)
    row.before_after_json = json.dumps(before_after)
    row.videos_json = json.dumps(videos)
    row.client_type = body.get('client_type') or (proj.client if proj else '')[:80]
    styles = body.get('style_tags') or [proj.project_type] if proj and proj.project_type else []
    row.style_tags_json = json.dumps([s for s in styles if s])
    challenges = body.get('challenges') or []
    row.challenges_json = json.dumps(challenges)
    if body.get('summary'):
        row.summary = body['summary']
    row.updated_at = datetime.utcnow()
    return case_study_to_dict(row)


def export_case_study_bundle(case_study, photos=None, *, base_url: str = '') -> dict:
    metrics = _json_load(case_study.metrics_json)
    tags = _json_load(case_study.tags_json, [])
    gallery = _json_load(getattr(case_study, 'gallery_json', None), [])
    html = export_case_study_html(case_study, photos)
    slug = case_study.slug
    public = f'{base_url}/public/marketing/case-study/{slug}' if base_url else f'/public/marketing/case-study/{slug}'
    linkedin = (
        f"{case_study.title}\n"
        f"{case_study.summary[:500] if case_study.summary else ''}\n"
        f"Location: {metrics.get('location', '')} · Value: {metrics.get('contract_value', '')}\n"
        f"{public}"
    )
    return {
        'html': html,
        'embed_code': f'<iframe src="{public}" width="100%" height="600" frameborder="0"></iframe>',
        'linkedin_text': linkedin,
        'json': case_study_to_dict(case_study) | {'gallery': gallery, 'public_url': public},
    }


def record_case_study_view(db, MarketingCaseStudy, slug: str) -> None:
    row = MarketingCaseStudy.query.filter_by(slug=slug, status='published').first()
    if row:
        row.view_count = int(row.view_count or 0) + 1
        db.session.flush()


def pipeline_forecast_advanced(db, MarketingLead) -> dict:
    base = pipeline_analytics(db, MarketingLead)
    leads = MarketingLead.query.all()
    hist = {}
    for src in MARKETING_LEAD_SOURCES:
        subset = [L for L in leads if (L.source or 'other') == src and L.stage in ('won', 'lost')]
        if not subset:
            continue
        won = sum(1 for L in subset if L.stage == 'won')
        hist[src] = {'closed': len(subset), 'won': won, 'close_rate': round(won / len(subset), 3)}
    stage_rates = {}
    for stage in MARKETING_LEAD_STAGES:
        if stage in ('won', 'lost'):
            continue
        progressed = [L for L in leads if L.stage in MARKETING_LEAD_STAGES[MARKETING_LEAD_STAGES.index(stage):]]
        if progressed:
            won = sum(1 for L in leads if L.stage == 'won' and L.source)
            stage_rates[stage] = round(won / max(len(leads), 1), 3)
    forecast = 0.0
    for L in leads:
        if L.stage in ('won', 'lost'):
            continue
        src_rate = (hist.get(L.source or 'other') or {}).get('close_rate') or 0.15
        prob = max(int(L.probability or 0) / 100.0, src_rate * 0.5)
        forecast += float(L.estimated_value or 0) * prob
    base['historical_close_by_source'] = hist
    base['forecast_with_history'] = round(forecast, 2)
    return base


def link_lead_to_bid_package(db, MarketingLead, BidPackage, Estimate, lead_id: int, bid_package_id: int) -> dict:
    lead = MarketingLead.query.get(int(lead_id))
    pkg = BidPackage.query.get(int(bid_package_id))
    if not lead or not pkg:
        raise ValueError('Lead or bid package not found')
    lead.bid_package_id = pkg.id
    if pkg.estimate_id and not lead.estimate_id:
        lead.estimate_id = pkg.estimate_id
        est = Estimate.query.get(pkg.estimate_id)
        if est and est.project_id:
            lead.project_id = est.project_id
    lead.source = lead.source or 'rfp'
    lead.stage = lead.stage or 'proposal'
    lead.updated_at = datetime.utcnow()
    return lead_to_dict(lead)


def create_lead_from_bid_package(db, MarketingLead, BidPackage, Estimate, bid_package_id: int, *, user_id=None, contact: dict | None = None) -> dict:
    pkg = BidPackage.query.get(int(bid_package_id))
    if not pkg:
        raise ValueError('Bid package not found')
    contact = contact or {}
    est = Estimate.query.get(pkg.estimate_id) if pkg.estimate_id else None
    title = contact.get('title') or f"RFP — {pkg.title or pkg.spec_section or pkg.id}"
    row = MarketingLead(
        title=title[:300],
        contact_name=contact.get('contact_name'),
        email=contact.get('email'),
        phone=contact.get('phone'),
        source='rfp',
        stage='qualification',
        probability=30,
        bid_package_id=pkg.id,
        estimate_id=pkg.estimate_id,
        project_id=est.project_id if est else None,
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    return lead_to_dict(row)


def run_project_automation(
    db, models, Project, *, project_id: int, user_id=None,
) -> dict:
    MarketingAutomationRule = models['MarketingAutomationRule']
    MarketingReviewRequest = models['MarketingReviewRequest']
    proj = Project.query.get(int(project_id))
    if not proj:
        raise ValueError('Project not found')
    fired = []
    for rule in MarketingAutomationRule.query.filter_by(enabled=True).all():
        if rule.trigger_type == 'project_status' and (proj.status or '') == (rule.trigger_value or ''):
            ok = True
        elif rule.trigger_type == 'project_percent':
            try:
                ok = int(proj.percent_complete or 0) >= int(rule.trigger_value or 0)
            except (TypeError, ValueError):
                ok = False
        else:
            ok = False
        if not ok:
            continue
        if rule.action_type == 'review_request':
            cfg = _json_load(rule.action_config_json)
            exists = MarketingReviewRequest.query.filter_by(
                project_id=proj.id, trigger_milestone=rule.name, status='pending',
            ).first()
            if exists:
                continue
            row = MarketingReviewRequest(
                project_id=proj.id,
                platform=cfg.get('platform') or 'google',
                status='pending',
                trigger_milestone=rule.name,
                access_token=_token(),
                created_by_id=user_id,
            )
            db.session.add(row)
            fired.append({'rule': rule.name, 'action': 'review_request', 'review_id': None})
            db.session.flush()
            fired[-1]['review_id'] = row.id
    return {'project_id': proj.id, 'fired': fired}


def register_referral(db, MarketingReferral, MarketingLead, body: dict, *, user_id=None) -> dict:
    ref_id = body.get('referrer_lead_id')
    new_lead = body.get('referred_lead') or {}
    if body.get('referred_lead_id'):
        referred = MarketingLead.query.get(int(body['referred_lead_id']))
    else:
        from marketing_services import upsert_lead
        referred = None
        out = upsert_lead(db, MarketingLead, {
            **new_lead,
            'source': 'referral',
            'stage': 'inquiry',
            'referral_lead_id': ref_id,
        }, user_id=user_id)
        referred = MarketingLead.query.get(out['id'])
    if not referred:
        raise ValueError('Referred lead required')
    if ref_id:
        referred.referral_lead_id = int(ref_id)
    row = MarketingReferral(
        referrer_lead_id=int(ref_id) if ref_id else None,
        referred_lead_id=referred.id,
        project_id=body.get('project_id'),
        incentive_type=body.get('incentive_type') or 'credit',
        incentive_value=float(body.get('incentive_value') or 0),
        status='pending',
        notes=body.get('notes'),
    )
    db.session.add(row)
    db.session.flush()
    return {'referral_id': row.id, 'referred_lead_id': referred.id}


def list_referrals(db, MarketingReferral, limit=100) -> dict:
    rows = MarketingReferral.query.order_by(MarketingReferral.id.desc()).limit(limit).all()
    return {
        'referrals': [{
            'id': r.id,
            'referrer_lead_id': r.referrer_lead_id,
            'referred_lead_id': r.referred_lead_id,
            'incentive_type': r.incentive_type,
            'incentive_value': r.incentive_value,
            'status': r.status,
        } for r in rows],
    }


def _wrap_tracked_links(html: str, base_url: str, token: str) -> str:
    def repl(m):
        url = m.group(1)
        if url.startswith('/api/marketing/track/'):
            return m.group(0)
        tracked = f'{base_url}/api/marketing/track/click/{token}?u={quote(url, safe="")}'
        return f'href="{tracked}"'

    return re.sub(r'href="([^"]+)"', repl, html or '')


def send_campaign_tracked(
    db, models, campaign_id: int, *, test_email: str | None = None, base_url: str = '',
) -> dict:
    from email_notifications import send_workflow_email

    MarketingCampaign = models['MarketingCampaign']
    MarketingLead = models['MarketingLead']
    MarketingCampaignRecipient = models['MarketingCampaignRecipient']

    row = MarketingCampaign.query.get(int(campaign_id))
    if not row:
        raise ValueError('Campaign not found')
    base_url = base_url or _base_url() or 'http://127.0.0.1:5000'
    segment = _json_load(row.segment_json)
    recipients = []
    if test_email:
        recipients = [{'email': test_email.strip(), 'lead_id': None}]
    else:
        q = MarketingLead.query
        if segment.get('stage'):
            q = q.filter_by(stage=segment['stage'])
        if segment.get('source'):
            q = q.filter_by(source=segment['source'])
        if segment.get('project_type'):
            q = q.filter_by(project_type=segment['project_type'])
        for L in q.limit(300).all():
            if (row.channel or 'email') == 'sms':
                if (L.phone or '').strip():
                    recipients.append({'lead_id': L.id, 'phone': L.phone.strip()})
            elif (L.email or '').strip():
                recipients.append({'email': L.email.strip(), 'lead_id': L.id})

    sent = opened = 0
    for rec in recipients[:200]:
        token = _token()
        channel = row.channel or 'email'
        if channel == 'sms':
            phone = rec.get('phone')
            if not phone and rec.get('lead_id'):
                L = MarketingLead.query.get(rec['lead_id'])
                phone = (L.phone or '').strip() if L else None
            if not phone:
                continue
            db_rec = MarketingCampaignRecipient(
                campaign_id=row.id, lead_id=rec.get('lead_id'), phone=phone,
                channel='sms', token=token, status='sent',
            )
            db.session.add(db_rec)
            db.session.flush()
            if send_sms(phone, row.body_text or row.subject or row.name):
                sent += 1
            continue
        email = rec.get('email')
        if not email:
            continue
        db_rec = MarketingCampaignRecipient(
            campaign_id=row.id,
            lead_id=rec.get('lead_id'),
            email=email,
            channel='email',
            token=token,
            status='sent',
        )
        db.session.add(db_rec)
        db.session.flush()
        pixel = f'{base_url}/api/marketing/track/open/{token}.gif'
        body_html = _wrap_tracked_links(row.body_html or f'<pre>{row.body_text}</pre>', base_url, token)
        body_html += f'<img src="{pixel}" width="1" height="1" alt="" style="display:none"/>'
        if send_workflow_email(email, row.subject or row.name, body_html, row.body_text or ''):
            sent += 1
    row.status = 'sent'
    row.sent_at = datetime.utcnow()
    row.stats_json = json.dumps({'recipients': len(recipients), 'sent': sent})
    return {'id': row.id, 'sent': sent, 'recipients': len(recipients)}


def send_sms(phone: str, message: str) -> bool:
    """Twilio or generic webhook when configured."""
    sid = os.environ.get('CASEPM_TWILIO_ACCOUNT_SID')
    token = os.environ.get('CASEPM_TWILIO_AUTH_TOKEN')
    from_num = os.environ.get('CASEPM_TWILIO_FROM')
    webhook = os.environ.get('CASEPM_SMS_WEBHOOK_URL')
    if sid and token and from_num:
        try:
            import urllib.request
            import urllib.parse
            data = urllib.parse.urlencode({
                'To': phone, 'From': from_num, 'Body': message[:1600],
            }).encode()
            req = urllib.request.Request(
                f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
                data=data,
                method='POST',
            )
            import base64
            auth = base64.b64encode(f'{sid}:{token}'.encode()).decode()
            req.add_header('Authorization', f'Basic {auth}')
            urllib.request.urlopen(req, timeout=15)
            return True
        except Exception:
            return False
    if webhook:
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(
                webhook,
                data=json.dumps({'phone': phone, 'message': message}).encode(),
                headers={'Content-Type': 'application/json'},
                method='POST',
            ), timeout=15)
            return True
        except Exception:
            return False
    return False


def track_campaign_open(db, MarketingCampaignRecipient, token: str) -> None:
    row = MarketingCampaignRecipient.query.filter_by(token=token).first()
    if row and not row.opened_at:
        row.opened_at = datetime.utcnow()
        db.session.flush()


def track_campaign_click(db, MarketingCampaignRecipient, MarketingLead, token: str, *, convert: bool = True) -> str | None:
    row = MarketingCampaignRecipient.query.filter_by(token=token).first()
    if not row:
        return None
    if not row.clicked_at:
        row.clicked_at = datetime.utcnow()
    if convert and row.lead_id and not row.converted_at:
        row.converted_at = datetime.utcnow()
        lead = MarketingLead.query.get(row.lead_id)
        if lead and lead.stage == 'inquiry':
            lead.stage = 'qualification'
            lead.probability = max(lead.probability or 0, 25)
    db.session.flush()
    return row.email


def search_assets(db, MarketingAsset, Photo, *, q: str = '', project_id=None, trade=None, phase=None, use_case=None, limit=200) -> dict:
    query = MarketingAsset.query.order_by(MarketingAsset.id.desc())
    if project_id:
        query = query.filter_by(project_id=int(project_id))
    rows = query.limit(500).all()
    ql = (q or '').lower()
    out = []
    for r in rows:
        tags = _json_load(r.tags_json, [])
        uses = _json_load(r.use_cases_json, [])
        if trade and (r.trade or '') != trade:
            continue
        if phase and (r.phase or '') != phase:
            continue
        if use_case and use_case not in uses:
            continue
        hay = ' '.join([r.title or '', r.asset_type or '', ' '.join(tags), r.trade or '', r.phase or '']).lower()
        if ql and ql not in hay:
            continue
        preview = None
        if r.photo_id and Photo:
            ph = Photo.query.get(r.photo_id)
            if ph:
                preview = f'/uploads/photos/{r.project_id}/{ph.filename}'
        out.append({
            'id': r.id, 'title': r.title, 'asset_type': r.asset_type, 'tags': tags,
            'use_cases': uses, 'preview_url': preview, 'external_url': r.external_url,
            'document_id': r.document_id, 'trade': r.trade, 'phase': r.phase,
        })
        if len(out) >= limit:
            break
    return {'assets': out, 'count': len(out)}


def register_asset(db, MarketingAsset, body: dict, *, user_id=None) -> dict:
    row = MarketingAsset(
        project_id=body.get('project_id'),
        photo_id=body.get('photo_id'),
        document_id=body.get('document_id'),
        external_url=(body.get('external_url') or '')[:500],
        title=(body.get('title') or 'Asset')[:300],
        asset_type=body.get('asset_type') or 'photo',
        phase=body.get('phase'),
        trade=body.get('trade'),
        tags_json=json.dumps(body.get('tags') or []),
        use_cases_json=json.dumps(body.get('use_cases') or ['portfolio']),
        meta_json=json.dumps(body.get('meta') or {}),
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    return {'id': row.id}


def build_proposal_from_estimate(
    db, models, estimate_id: int, *, lead_id=None, user_id=None, template_key='proposal',
) -> dict:
    MarketingProposal = models['MarketingProposal']
    MarketingContentBlock = models['MarketingContentBlock']
    MarketingCaseStudy = models['MarketingCaseStudy']
    Estimate = models['Estimate']
    EstimateLine = models.get('EstimateLine')
    Project = models['Project']

    est = Estimate.query.get(int(estimate_id))
    if not est:
        raise ValueError('Estimate not found')
    proj = Project.query.get(est.project_id) if est.project_id else None
    blocks = MarketingCaseStudy.query.filter_by(status='published').order_by(MarketingCaseStudy.view_count.desc()).limit(3).all()
    similar = ''.join(f'<li>{c.title}</li>' for c in blocks)
    library = MarketingContentBlock.query.order_by(MarketingContentBlock.sort_order).all()
    lib_html = ''.join(f'<section><h3>{b.title}</h3>{b.body_html or ""}</section>' for b in library[:6])
    lines_html = ''
    if EstimateLine:
        for ln in EstimateLine.query.filter_by(estimate_id=est.id).order_by(EstimateLine.sort_order).limit(40):
            lines_html += f'<tr><td>{ln.description or ""}</td><td>{ln.extended_cost or 0}</td></tr>'
    body_html = f"""
    <h1>{est.title or 'Proposal'}</h1>
    <p>Project: {proj.name if proj else est.project_id} · Client: {proj.client if proj else ''}</p>
    {lib_html}
    <h2>Estimate summary</h2>
    <p>Total: <strong>{est.total_amount or est.direct_cost_total or 0}</strong></p>
    <table><tbody>{lines_html}</tbody></table>
    <h2>Similar work</h2><ul>{similar}</ul>
    """
    row = MarketingProposal(
        estimate_id=est.id,
        lead_id=int(lead_id) if lead_id else None,
        title=f"Proposal — {est.title or est.id}"[:300],
        template_key=template_key,
        body_html=body_html,
        status='draft',
        access_token=_token(),
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    return proposal_to_dict(row)


def proposal_to_dict(row) -> dict:
    return {
        'id': row.id,
        'estimate_id': row.estimate_id,
        'lead_id': row.lead_id,
        'title': row.title,
        'status': row.status,
        'view_count': row.view_count,
        'access_token': row.access_token,
        'public_url': f'/public/marketing/proposal/{row.access_token}',
        'signed_at': row.signed_at.isoformat() if row.signed_at else None,
        'esign_envelope_id': row.esign_envelope_id,
    }


def send_proposal_email(db, MarketingProposal, proposal_id: int, email: str, *, base_url: str = '') -> dict:
    from email_notifications import send_workflow_email

    row = MarketingProposal.query.get(int(proposal_id))
    if not row:
        raise ValueError('Proposal not found')
    base_url = base_url or _base_url() or 'http://127.0.0.1:5000'
    url = f'{base_url}/public/marketing/proposal/{row.access_token}'
    html = f'<p>Please review our proposal:</p><p><a href="{url}">{row.title}</a></p>'
    sent = send_workflow_email(email.strip(), row.title or 'Case PM Proposal', html, f'View proposal: {url}')
    if sent:
        row.status = 'sent'
        row.sent_at = datetime.utcnow()
    return {'sent': sent, 'url': url}


def record_proposal_view(db, MarketingProposal, token: str) -> dict | None:
    row = MarketingProposal.query.filter_by(access_token=token).first()
    if not row:
        return None
    row.view_count = int(row.view_count or 0) + 1
    row.last_viewed_at = datetime.utcnow()
    eng = _json_load(row.engagement_json, {'views': []})
    eng['views'].append(datetime.utcnow().isoformat())
    row.engagement_json = json.dumps(eng[-50:])
    db.session.flush()
    return {'id': row.id, 'title': row.title, 'body_html': row.body_html, 'view_count': row.view_count}


def sign_proposal_token(db, MarketingProposal, token: str, body: dict) -> dict:
    row = MarketingProposal.query.filter_by(access_token=token).first()
    if not row:
        raise ValueError('Proposal not found')
    row.status = 'signed'
    row.signed_at = datetime.utcnow()
    eng = _json_load(row.engagement_json, {})
    eng['signature'] = body.get('signature_name') or body.get('name')
    row.engagement_json = json.dumps(eng)
    return proposal_to_dict(row)


def upsert_landing_page(db, MarketingLandingPage, body: dict, *, page_id=None) -> dict:
    if page_id:
        row = MarketingLandingPage.query.get(int(page_id))
        if not row:
            raise ValueError('Landing page not found')
    else:
        row = MarketingLandingPage()
        db.session.add(row)
    row.title = (body.get('title') or row.title or 'Landing page')[:300]
    row.slug = _slugify(body.get('slug') or row.slug or row.title)
    if body.get('sections') is not None:
        row.sections_json = json.dumps(body['sections'])
    if body.get('lead_form') is not None:
        row.lead_form_json = json.dumps(body['lead_form'])
    if body.get('seo') is not None:
        row.seo_json = json.dumps(body['seo'])
    if body.get('status'):
        row.status = body['status']
        if body['status'] == 'published' and not row.published_at:
            row.published_at = datetime.utcnow()
    return landing_page_to_dict(row)


def landing_page_to_dict(row) -> dict:
    return {
        'id': row.id,
        'slug': row.slug,
        'title': row.title,
        'status': row.status,
        'sections': _json_load(row.sections_json, []),
        'lead_form': _json_load(row.lead_form_json, {}),
        'seo': _json_load(row.seo_json, {}),
        'view_count': row.view_count,
        'public_url': f'/public/marketing/site/{row.slug}',
    }


def default_landing_page(db, MarketingLandingPage, MarketingCaseStudy) -> dict:
    existing = MarketingLandingPage.query.filter_by(slug='home').first()
    if existing:
        return landing_page_to_dict(existing)
    studies = MarketingCaseStudy.query.filter_by(status='published').limit(6).all()
    sections = [
        {'type': 'hero', 'headline': 'Quality construction', 'sub': 'Design-build and GC services'},
        {'type': 'portfolio', 'case_study_ids': [c.id for c in studies]},
        {'type': 'cta', 'text': 'Request a consultation'},
    ]
    return upsert_landing_page(db, MarketingLandingPage, {
        'title': 'Case PM — Home',
        'slug': 'home',
        'sections': sections,
        'lead_form': {'fields': ['contact_name', 'email', 'phone', 'notes']},
        'seo': {'title': 'Construction services', 'description': 'Local GC portfolio and lead capture'},
        'status': 'published',
    })


def record_landing_view(db, MarketingLandingPage, slug: str) -> dict | None:
    row = MarketingLandingPage.query.filter_by(slug=slug, status='published').first()
    if not row:
        return None
    row.view_count = int(row.view_count or 0) + 1
    db.session.flush()
    return landing_page_to_dict(row)


def record_spend(db, MarketingSpend, body: dict) -> dict:
    row = MarketingSpend(
        channel=body.get('channel'),
        label=body.get('label'),
        amount=float(body.get('amount') or 0),
        campaign_id=body.get('campaign_id'),
        notes=body.get('notes'),
    )
    db.session.add(row)
    db.session.flush()
    return {'id': row.id, 'amount': row.amount}


def marketing_analytics_full(db, models) -> dict:
    MarketingLead = models['MarketingLead']
    MarketingCampaign = models['MarketingCampaign']
    MarketingCampaignRecipient = models['MarketingCampaignRecipient']
    MarketingSpend = models['MarketingSpend']
    MarketingCaseStudy = models['MarketingCaseStudy']
    MarketingLandingPage = models['MarketingLandingPage']
    MarketingProposal = models['MarketingProposal']
    Project = models['Project']

    pipe = pipeline_forecast_advanced(db, MarketingLead)
    spend = sum(float(s.amount or 0) for s in MarketingSpend.query.all())
    leads = MarketingLead.query.count()
    won = MarketingLead.query.filter_by(stage='won').count()
    recips = MarketingCampaignRecipient.query.all()
    opens = sum(1 for r in recips if r.opened_at)
    clicks = sum(1 for r in recips if r.clicked_at)
    conversions = sum(1 for r in recips if r.converted_at)
    by_campaign = {}
    for L in MarketingLead.query.filter(MarketingLead.campaign_id.isnot(None)).all():
        by_campaign[L.campaign_id] = by_campaign.get(L.campaign_id, 0) + 1
    portfolio_views = sum(int(c.view_count or 0) for c in MarketingCaseStudy.query.all())
    landing_views = sum(int(p.view_count or 0) for p in MarketingLandingPage.query.all())
    proposal_views = sum(int(p.view_count or 0) for p in MarketingProposal.query.all())
    active_projects = Project.query.filter_by(status='Active').count() if Project else 0
    cpl = round(spend / leads, 2) if leads and spend else None
    base = {
        **pipe,
        'marketing_spend_total': round(spend, 2),
        'cost_per_lead': cpl,
        'campaign_opens': opens,
        'campaign_clicks': clicks,
        'campaign_conversions': conversions,
        'leads_by_campaign': by_campaign,
        'portfolio_page_views': portfolio_views,
        'landing_page_views': landing_views,
        'proposal_views': proposal_views,
        'active_projects': active_projects,
        'roi_note': 'Attributed revenue uses won lead values; connect spend entries for CPL.',
    }
    try:
        from marketing_gaps import enrich_analytics_profit
        base = enrich_analytics_profit(db, models, base)
    except Exception:
        pass
    return base


def enrich_client_portal_feed(db, models, base: dict, project_id: int | None) -> dict:
    if not project_id:
        return base
    try:
        from marketing_gaps import build_portal_marketing_pack
        base['marketing'] = build_portal_marketing_pack(db, models, int(project_id))
    except Exception:
        MarketingReviewRequest = models['MarketingReviewRequest']
        MarketingCaseStudy = models['MarketingCaseStudy']
        pid = int(project_id)
        base['marketing'] = {
            'review_requests': [],
            'published_case_studies': list(MarketingCaseStudy.query.filter_by(project_id=pid, status='published').limit(5)),
        }
    return base


def public_review_form(db, MarketingReviewRequest, token: str) -> dict | None:
    from marketing_gaps import review_platform_links
    row = MarketingReviewRequest.query.filter_by(access_token=token).first()
    if not row:
        return None
    return {
        'project_id': row.project_id,
        'platform': row.platform,
        'status': row.status,
        'referral_incentive': row.referral_incentive,
        'platform_links': review_platform_links(load_marketing_settings(), row.platform),
    }


def complete_public_review(db, MarketingReviewRequest, token: str, body: dict) -> dict:
    row = MarketingReviewRequest.query.filter_by(access_token=token).first()
    if not row:
        raise ValueError('Review not found')
    row.rating = int(body['rating']) if body.get('rating') is not None else row.rating
    row.testimonial_text = (body.get('testimonial_text') or '')[:4000]
    row.public_share_ok = bool(body.get('public_share_ok'))
    row.status = 'completed'
    row.completed_at = datetime.utcnow()
    return review_to_dict(row)


def testimonial_widget(db, MarketingReviewRequest, *, limit=12) -> dict:
    rows = MarketingReviewRequest.query.filter_by(status='completed', public_share_ok=True).order_by(
        MarketingReviewRequest.completed_at.desc(),
    ).limit(limit).all()
    return {'testimonials': [review_to_dict(r) for r in rows]}


def load_marketing_settings() -> dict:
    try:
        from program_settings_persistence import load_program_settings
        ps = load_program_settings() or {}
        m = ps.get('marketing') or {}
    except Exception:
        m = {}
    return {
        'google_business_profile_url': m.get('google_business_profile_url') or '',
        'google_place_id': m.get('google_place_id') or '',
        'houzz_profile_url': m.get('houzz_profile_url') or '',
        'facebook_page_url': m.get('facebook_page_url') or '',
        'review_syndication_enabled': bool(m.get('review_syndication_enabled')),
        'public_base_url': m.get('public_base_url') or os.environ.get('CASEPM_PUBLIC_BASE_URL') or '',
        'sms_configured': bool(os.environ.get('CASEPM_TWILIO_ACCOUNT_SID') or os.environ.get('CASEPM_SMS_WEBHOOK_URL')),
        'crm_auto_push': bool(m.get('crm_auto_push')),
        'company_nap_json': m.get('company_nap_json') or '{}',
        'dodge_webhook_enabled': bool(m.get('dodge_webhook_enabled')),
        'constructconnect_webhook_enabled': bool(m.get('constructconnect_webhook_enabled')),
        'primary_construction_market': (m.get('primary_construction_market') or 'commercial')[:40],
        'secondary_construction_markets': m.get('secondary_construction_markets') or [],
    }


def save_marketing_settings(payload: dict) -> dict:
    from program_settings_persistence import load_program_settings, save_program_settings
    ps = load_program_settings() or {}
    prev = ps.get('marketing') or {}
    ps['marketing'] = {
        **prev,
        'google_business_profile_url': (payload.get('google_business_profile_url') or prev.get('google_business_profile_url') or '')[:500],
        'google_place_id': (payload.get('google_place_id') or prev.get('google_place_id') or '')[:120],
        'houzz_profile_url': (payload.get('houzz_profile_url') or prev.get('houzz_profile_url') or '')[:500],
        'facebook_page_url': (payload.get('facebook_page_url') or prev.get('facebook_page_url') or '')[:500],
        'review_syndication_enabled': bool(payload.get('review_syndication_enabled', prev.get('review_syndication_enabled'))),
        'public_base_url': (payload.get('public_base_url') or prev.get('public_base_url') or '')[:300],
        'crm_auto_push': bool(payload.get('crm_auto_push', prev.get('crm_auto_push'))),
        'company_nap_json': payload.get('company_nap_json') if payload.get('company_nap_json') is not None else prev.get('company_nap_json', '{}'),
        'dodge_webhook_enabled': bool(payload.get('dodge_webhook_enabled', prev.get('dodge_webhook_enabled'))),
        'constructconnect_webhook_enabled': bool(payload.get('constructconnect_webhook_enabled', prev.get('constructconnect_webhook_enabled'))),
        'primary_construction_market': (payload.get('primary_construction_market') or prev.get('primary_construction_market') or 'commercial')[:40],
        'secondary_construction_markets': payload.get('secondary_construction_markets')
        if payload.get('secondary_construction_markets') is not None
        else prev.get('secondary_construction_markets') or [],
    }
    save_program_settings(ps)
    return load_marketing_settings()


def syndicate_reviews(db, MarketingReviewRequest) -> dict:
    """Push public testimonials to configured syndication (GBP link / webhook)."""
    settings = load_marketing_settings()
    reviews = testimonial_widget(db, MarketingReviewRequest, limit=20)
    webhook = os.environ.get('CASEPM_REVIEW_SYNDICATION_WEBHOOK')
    out = {'syndicated': len(reviews['testimonials']), 'google_business_profile_url': settings['google_business_profile_url']}
    if webhook and settings.get('review_syndication_enabled'):
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(
                webhook,
                data=json.dumps(reviews).encode(),
                headers={'Content-Type': 'application/json'},
                method='POST',
            ), timeout=15)
            out['webhook'] = 'sent'
        except Exception as exc:
            out['webhook_error'] = str(exc)[:120]
    return out


def pillars_deploy_check() -> dict:
    try:
        import marketing_pillars as mp
        assert callable(mp.marketing_analytics_full)
        assert callable(mp.send_campaign_tracked)
        return {'ok': True}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:200]}
