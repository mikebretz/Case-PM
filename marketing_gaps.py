"""Close remaining marketing research gaps — brand, portal pack, PDF/DocuSign, SEO, referrals, profit ROI."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime

import fitz

from marketing_pillars import load_marketing_settings, save_marketing_settings
from marketing_services import _json_load, case_study_to_dict, export_case_study_html


WARRANTY_DOC_TYPES = frozenset({'warranty', 'manual', 'o&m', 'om', 'closeout', 'owner manual'})
PROGRESS_PHOTO_LIMIT = 24


def default_brand_kit(db, MarketingBrandKit) -> dict:
    row = MarketingBrandKit.query.filter_by(is_default=True).first()
    if row:
        return brand_kit_to_dict(row)
    row = MarketingBrandKit(
        name='Default',
        is_default=True,
        colors_json=json.dumps({'primary': '#059669', 'secondary': '#18181b'}),
        fonts_json=json.dumps({'heading': 'system-ui', 'body': 'system-ui'}),
        header_html='<header style="border-bottom:2px solid #059669;padding:1rem"><strong>{{company_name}}</strong></header>',
        footer_html='<footer style="margin-top:2rem;font-size:12px;color:#666">© {{year}} {{company_name}}</footer>',
    )
    db.session.add(row)
    db.session.flush()
    return brand_kit_to_dict(row)


def brand_kit_to_dict(row) -> dict:
    return {
        'id': row.id,
        'name': row.name,
        'is_default': row.is_default,
        'logo_url': row.logo_url,
        'colors': _json_load(row.colors_json, {}),
        'fonts': _json_load(row.fonts_json, {}),
        'header_html': row.header_html,
        'footer_html': row.footer_html,
    }


def upsert_brand_kit(db, MarketingBrandKit, body: dict, *, kit_id=None) -> dict:
    if kit_id:
        row = MarketingBrandKit.query.get(int(kit_id))
        if not row:
            raise ValueError('Brand kit not found')
    else:
        row = MarketingBrandKit()
        db.session.add(row)
    for field in ('name', 'logo_url', 'header_html', 'footer_html'):
        if field in body:
            setattr(row, field, body.get(field))
    if 'colors' in body:
        row.colors_json = json.dumps(body['colors'] or {})
    if 'fonts' in body:
        row.fonts_json = json.dumps(body['fonts'] or {})
    if body.get('is_default'):
        MarketingBrandKit.query.update({'is_default': False})
        row.is_default = True
    row.updated_at = datetime.utcnow()
    db.session.flush()
    return brand_kit_to_dict(row)


def apply_brand_to_html(db, MarketingBrandKit, html: str, *, company_name: str = 'Case PM') -> str:
    kit = MarketingBrandKit.query.filter_by(is_default=True).first()
    if not kit:
        return html
    hdr = (kit.header_html or '').replace('{{company_name}}', company_name).replace('{{year}}', str(datetime.utcnow().year))
    ftr = (kit.footer_html or '').replace('{{company_name}}', company_name).replace('{{year}}', str(datetime.utcnow().year))
    logo = f'<img src="{kit.logo_url}" alt="" style="max-height:48px"/>' if kit.logo_url else ''
    return f'{logo}{hdr}<div class="body">{html}</div>{ftr}'


def case_study_award_package(db, MarketingCaseStudy, MarketingBrandKit, case_study_id: int, Photo) -> dict:
    row = MarketingCaseStudy.query.get(int(case_study_id))
    if not row:
        raise ValueError('Case study not found')
    photos = []
    if Photo and row.project_id:
        photos = Photo.query.filter_by(project_id=row.project_id).limit(12).all()
    html = export_case_study_html(row, photos)
    html = apply_brand_to_html(db, MarketingBrandKit, html)
    bundle = {
        'case_study': case_study_to_dict(row),
        'branded_html': html,
        'metrics': _json_load(row.metrics_json),
        'submission_checklist': [
            'Project summary and client type',
            'Before/after or progress photos',
            'Schedule and budget highlights',
            'Safety / sustainability notes',
            'Team credits',
        ],
    }
    return bundle


def _doc_matches_closeout(doc) -> str | None:
    name = (doc.name or '').lower()
    dtype = (doc.document_type or '').lower()
    tags = _json_load(getattr(doc, 'tags_json', None), [])
    hay = ' '.join([name, dtype] + [str(t).lower() for t in tags])
    if any(x in hay for x in ('warranty', 'guarantee')):
        return 'warranty'
    if any(x in hay for x in ('manual', 'o&m', 'om ', 'operation', 'maintenance', 'closeout')):
        return 'manual'
    return None


def build_portal_marketing_pack(db, models, project_id: int) -> dict:
    MarketingPortalPack = models['MarketingPortalPack']
    MarketingReviewRequest = models['MarketingReviewRequest']
    MarketingCaseStudy = models['MarketingCaseStudy']
    Photo = models.get('Photo')
    Document = models.get('Document')
    Project = models.get('Project')
    pid = int(project_id)
    pack_row = MarketingPortalPack.query.filter_by(project_id=pid).first()
    proj = Project.query.get(pid) if Project else None
    photos = []
    if Photo:
        photos = [{
            'id': p.id,
            'url': f'/uploads/photos/{p.project_id}/{p.filename}',
            'caption': p.caption,
            'taken_date': p.taken_date.isoformat() if p.taken_date else None,
        } for p in Photo.query.filter_by(project_id=pid).order_by(Photo.created_at.desc()).limit(PROGRESS_PHOTO_LIMIT)]
    warranties, manuals = [], []
    if Document:
        for doc in Document.query.filter_by(project_id=pid).filter(Document.deleted_at.is_(None)).limit(200).all():
            kind = _doc_matches_closeout(doc)
            if not kind:
                continue
            entry = {
                'id': doc.id,
                'name': doc.name,
                'document_type': doc.document_type,
                'url': f'/documents?project_id={pid}&highlight={doc.id}',
            }
            if kind == 'warranty':
                warranties.append(entry)
            else:
                manuals.append(entry)
    if pack_row:
        for doc_id in _json_load(pack_row.warranty_doc_ids_json, []):
            if Document and not any(w['id'] == doc_id for w in warranties):
                d = Document.query.get(doc_id)
                if d:
                    warranties.append({'id': d.id, 'name': d.name, 'url': f'/documents?project_id={pid}'})
        for doc_id in _json_load(pack_row.manual_doc_ids_json, []):
            if Document and not any(m['id'] == doc_id for m in manuals):
                d = Document.query.get(doc_id)
                if d:
                    manuals.append({'id': d.id, 'name': d.name, 'url': f'/documents?project_id={pid}'})
    reviews = MarketingReviewRequest.query.filter_by(project_id=pid).order_by(MarketingReviewRequest.id.desc()).limit(5).all()
    settings = load_marketing_settings()
    platform_links = review_platform_links(settings, row_platform=None)
    return {
        'project_id': pid,
        'project_name': proj.name if proj else None,
        'progress_photos': photos,
        'warranties': warranties,
        'manuals': manuals,
        'review_requests': [{
            'id': r.id,
            'status': r.status,
            'platform': r.platform,
            'public_url': f'/public/marketing/review/{r.access_token}' if r.access_token else None,
            'platform_links': review_platform_links(settings, r.platform),
        } for r in reviews],
        'published_case_studies': [
            {'id': c.id, 'title': c.title, 'slug': c.slug, 'public_url': f'/public/marketing/case-study/{c.slug}'}
            for c in MarketingCaseStudy.query.filter_by(project_id=pid, status='published').limit(5)
        ],
        'share_testimonials_ok': pack_row.share_testimonials_ok if pack_row else True,
        'branding': _json_load(pack_row.branding_json, {}) if pack_row else {},
        'platform_review_links': platform_links,
    }


def upsert_portal_pack(db, MarketingPortalPack, project_id: int, body: dict) -> dict:
    row = MarketingPortalPack.query.filter_by(project_id=int(project_id)).first()
    if not row:
        row = MarketingPortalPack(project_id=int(project_id))
        db.session.add(row)
    if 'warranty_doc_ids' in body:
        row.warranty_doc_ids_json = json.dumps(body['warranty_doc_ids'] or [])
    if 'manual_doc_ids' in body:
        row.manual_doc_ids_json = json.dumps(body['manual_doc_ids'] or [])
    if 'share_testimonials_ok' in body:
        row.share_testimonials_ok = bool(body['share_testimonials_ok'])
    if 'branding' in body:
        row.branding_json = json.dumps(body['branding'] or {})
    row.updated_at = datetime.utcnow()
    db.session.flush()
    return {'project_id': row.project_id, 'ok': True}


def review_platform_links(settings: dict, platform: str | None) -> dict:
    google_place = settings.get('google_place_id') or ''
    houzz = settings.get('houzz_profile_url') or ''
    facebook = settings.get('facebook_page_url') or ''
    links = {
        'google': f'https://search.google.com/local/writereview?placeid={google_place}' if google_place else '',
        'houzz': houzz,
        'facebook': f'{facebook.rstrip("/")}/reviews' if facebook else '',
    }
    if platform and platform in links:
        return {platform: links[platform], **{k: v for k, v in links.items() if v}}
    return {k: v for k, v in links.items() if v}


def issue_referral_incentive(db, MarketingReferral, body: dict | None = None, *, referral_id: int) -> dict:
    row = MarketingReferral.query.get(int(referral_id))
    if not row:
        raise ValueError('Referral not found')
    row.status = 'issued'
    row.issued_at = datetime.utcnow()
    row.incentive_code = row.incentive_code or secrets.token_hex(4).upper()
    if body and body.get('notes'):
        row.notes = (row.notes or '') + '\n' + str(body['notes'])
    db.session.flush()
    return {
        'referral_id': row.id,
        'incentive_code': row.incentive_code,
        'incentive_value': row.incentive_value,
        'status': row.status,
    }


def redeem_referral_incentive(db, MarketingReferral, referral_id: int, code: str) -> dict:
    row = MarketingReferral.query.get(int(referral_id))
    if not row or (row.incentive_code or '').upper() != (code or '').upper():
        raise ValueError('Invalid referral code')
    row.status = 'redeemed'
    row.redeemed_at = datetime.utcnow()
    db.session.flush()
    return {'referral_id': row.id, 'status': row.status}


def build_proposal_pdf(proposal_row, *, title: str | None = None) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    margin = 54
    y = margin
    text = re.sub('<[^>]+>', ' ', proposal_row.body_html or '')
    text = re.sub(r'\s+', ' ', text).strip()
    page.insert_text((margin, y), (title or proposal_row.title or 'Proposal')[:120], fontsize=16, fontname='hebo')
    y += 28
    for chunk in _wrap_text(text, 90):
        if y > 720:
            page = doc.new_page(width=612, height=792)
            y = margin
        page.insert_text((margin, y), chunk, fontsize=10, fontname='helv')
        y += 14
    buf = doc.tobytes()
    doc.close()
    return buf


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ''
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}'.strip()
    if cur:
        lines.append(cur)
    return lines or ['']


def save_proposal_pdf(proposal_row, pdf_bytes: bytes) -> str:
    folder = os.path.join('uploads', 'marketing', 'proposals')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'proposal_{proposal_row.id}.pdf')
    with open(path, 'wb') as fh:
        fh.write(pdf_bytes)
    proposal_row.pdf_path = path
    return path


def send_proposal_docusign(db, MarketingProposal, proposal_id: int, email: str, name: str) -> dict:
    from docusign_service import send_generic_envelope

    row = MarketingProposal.query.get(int(proposal_id))
    if not row:
        raise ValueError('Proposal not found')
    pdf = build_proposal_pdf(row)
    path = save_proposal_pdf(row, pdf)
    result = send_generic_envelope(
        signer_email=email.strip(),
        signer_name=name or email,
        email_subject=row.title or 'Construction Proposal',
        pdf_bytes=pdf,
        pdf_filename=os.path.basename(path),
    )
    if result.get('envelope_id'):
        row.esign_envelope_id = result['envelope_id']
        row.status = 'sent'
        row.sent_at = datetime.utcnow()
    eng = _json_load(row.engagement_json, {})
    eng['docusign'] = result
    row.engagement_json = json.dumps(eng)
    db.session.flush()
    return {'proposal_id': row.id, 'pdf_path': path, **result}


def enrich_analytics_profit(db, models, base: dict) -> dict:
    MarketingLead = models['MarketingLead']
    Project = models['Project']
    BudgetProjectState = models.get('BudgetProjectState')
    attributed = []
    total_revenue = 0.0
    total_margin_est = 0.0
    for L in MarketingLead.query.filter_by(stage='won').all():
        rev = float(L.estimated_value or 0)
        margin = None
        if L.project_id and Project:
            p = Project.query.get(L.project_id)
            if p and p.contract_value:
                rev = float(p.contract_value)
            if BudgetProjectState and p:
                try:
                    from budget_persistence import get_budget_state
                    _, budget = get_budget_state(BudgetProjectState, p.id)
                    if budget:
                        orig = sum(float(l.get('original_budget') or 0) for l in (budget.get('budgetLines') or []) if isinstance(l, dict))
                        if orig and rev:
                            margin = round((rev - orig) / rev, 3)
                            total_margin_est += (rev - orig)
                except Exception:
                    pass
        total_revenue += rev
        camp = L.campaign_id
        attributed.append({
            'lead_id': L.id,
            'source': L.source,
            'campaign_id': camp,
            'project_id': L.project_id,
            'revenue': rev,
            'margin_est': margin,
        })
    by_source_spend = {}
    for L in MarketingLead.query.all():
        by_source_spend[L.source or 'other'] = by_source_spend.get(L.source or 'other', 0) + 1
    base['won_job_attribution'] = attributed
    base['won_revenue_attributed'] = round(total_revenue, 2)
    base['estimated_gross_margin'] = round(total_margin_est, 2)
    base['portfolio_vs_delivery'] = {
        'portfolio_views': base.get('portfolio_page_views'),
        'active_projects': base.get('active_projects'),
        'won_jobs': len(attributed),
    }
    return base


def local_seo_audit(db, MarketingLandingPage, MarketingCaseStudy) -> dict:
    pages = MarketingLandingPage.query.filter_by(status='published').all()
    studies = MarketingCaseStudy.query.filter_by(status='published').count()
    issues, score = [], 100
    if not pages:
        issues.append('No published landing pages')
        score -= 30
    for p in pages:
        seo = _json_load(p.seo_json, {})
        if not seo.get('title'):
            issues.append(f'Page {p.slug}: missing SEO title')
            score -= 10
        if not seo.get('description'):
            issues.append(f'Page {p.slug}: missing meta description')
            score -= 10
    if studies < 3:
        issues.append('Publish at least 3 case studies for local proof')
        score -= 15
    settings = load_marketing_settings()
    if not settings.get('google_place_id'):
        issues.append('Set Google Place ID for review deep links')
        score -= 10
    return {'score': max(0, score), 'issues': issues, 'recommendations': [
        'Keep NAP (name/address/phone) consistent on landing pages',
        'Link published portfolio pages from your homepage',
        'Request reviews after closeout automation fires',
    ]}


def extended_marketing_settings(payload: dict | None = None) -> dict:
    base = load_marketing_settings()
    keys = (
        'google_place_id', 'houzz_profile_url', 'facebook_page_url',
        'dodge_webhook_enabled', 'constructconnect_webhook_enabled',
        'crm_auto_push', 'company_nap_json',
    )
    if payload:
        ps_patch = {k: payload.get(k) for k in keys if k in payload}
        save_marketing_settings({**payload, **ps_patch})
        base = load_marketing_settings()
    for k in keys:
        base.setdefault(k, '')
    base['company_nap'] = _json_load(base.get('company_nap_json') or '{}', {})
    return base


def run_scheduled_marketing_jobs(db, models, Project) -> dict:
    from marketing_pillars import run_project_automation

    results = {'automation': [], 'reviews_sent': 0}
    if not Project:
        return results
    for proj in Project.query.filter(Project.status.in_(['Active', 'Complete', 'Completed'])).limit(200).all():
        try:
            out = run_project_automation(db, models, Project, project_id=proj.id)
            if out.get('fired'):
                results['automation'].append({'project_id': proj.id, 'fired': out['fired']})
        except Exception:
            continue
    return results


def create_itb_lead(db, MarketingLead, body: dict, *, user_id=None) -> dict:
    """Invitation to bid / ITB — alias for inbound construction leads."""
    body = dict(body or {})
    body['source'] = 'rfp'
    body['metadata'] = {'itb_number': body.get('itb_number') or body.get('rfp_number'), 'bid_due': body.get('bid_due')}
    from marketing_services import upsert_lead
    return upsert_lead(db, MarketingLead, {
        'title': body.get('title') or f"ITB {body.get('itb_number') or 'inquiry'}",
        'contact_name': body.get('contact_name'),
        'email': body.get('email'),
        'phone': body.get('phone'),
        'stage': 'qualification',
        'probability': 35,
        'estimated_value': body.get('estimated_value'),
        'source': 'rfp',
        'metadata': body['metadata'],
    }, user_id=user_id)


def gaps_deploy_check() -> dict:
    try:
        import marketing_gaps as mg
        import marketing_integrations as mi
        assert callable(mg.build_portal_marketing_pack)
        assert callable(mi.ingest_integration_lead)
        return {'ok': True}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:200]}
