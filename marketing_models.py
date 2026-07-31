"""Construction marketing — leads, portfolio, campaigns, reputation, DAM metadata."""
from __future__ import annotations

from datetime import datetime


MARKETING_LEAD_STAGES = (
    'inquiry', 'qualification', 'proposal', 'negotiation', 'won', 'lost',
)
MARKETING_LEAD_SOURCES = (
    'website', 'houzz', 'referral', 'dodge', 'constructconnect', 'paid_ads', 'rfp', 'other',
)


def define_marketing_models(db):
    class MarketingLead(db.Model):
        __tablename__ = 'marketing_lead'
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(300), nullable=False)
        contact_name = db.Column(db.String(200))
        email = db.Column(db.String(200))
        phone = db.Column(db.String(40))
        company_name = db.Column(db.String(200))
        source = db.Column(db.String(40), default='website')
        stage = db.Column(db.String(40), default='inquiry')
        probability = db.Column(db.Integer, default=20)
        estimated_value = db.Column(db.Float, default=0)
        project_type = db.Column(db.String(80))
        location_city = db.Column(db.String(100))
        location_state = db.Column(db.String(50))
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True, index=True)
        estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=True, index=True)
        referral_lead_id = db.Column(db.Integer, db.ForeignKey('marketing_lead.id'), nullable=True)
        bid_package_id = db.Column(db.Integer, db.ForeignKey('bid_package.id'), nullable=True, index=True)
        campaign_id = db.Column(db.Integer, db.ForeignKey('marketing_campaign.id'), nullable=True)
        landing_page_id = db.Column(db.Integer, nullable=True)
        attribution_json = db.Column(db.Text)
        construction_market = db.Column(db.String(40), index=True)
        notes = db.Column(db.Text)
        metadata_json = db.Column(db.Text)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        closed_at = db.Column(db.DateTime)

    class MarketingCaseStudy(db.Model):
        __tablename__ = 'marketing_case_study'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
        title = db.Column(db.String(300), nullable=False)
        slug = db.Column(db.String(120), index=True)
        status = db.Column(db.String(30), default='draft')
        summary = db.Column(db.Text)
        metrics_json = db.Column(db.Text)
        tags_json = db.Column(db.Text)
        team_credits_json = db.Column(db.Text)
        gallery_json = db.Column(db.Text)
        before_after_json = db.Column(db.Text)
        videos_json = db.Column(db.Text)
        client_type = db.Column(db.String(80))
        style_tags_json = db.Column(db.Text)
        challenges_json = db.Column(db.Text)
        view_count = db.Column(db.Integer, default=0)
        template_key = db.Column(db.String(40), default='default')
        version = db.Column(db.Integer, default=1)
        published_at = db.Column(db.DateTime)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class MarketingCampaign(db.Model):
        __tablename__ = 'marketing_campaign'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        channel = db.Column(db.String(20), default='email')
        template_key = db.Column(db.String(40))
        campaign_type = db.Column(db.String(40), default='one_time')
        segment_json = db.Column(db.Text)
        subject = db.Column(db.String(300))
        body_html = db.Column(db.Text)
        body_text = db.Column(db.Text)
        status = db.Column(db.String(30), default='draft')
        stats_json = db.Column(db.Text)
        sent_at = db.Column(db.DateTime)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingReviewRequest(db.Model):
        __tablename__ = 'marketing_review_request'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
        platform = db.Column(db.String(40), default='google')
        status = db.Column(db.String(30), default='pending')
        rating = db.Column(db.Integer)
        testimonial_text = db.Column(db.Text)
        public_share_ok = db.Column(db.Boolean, default=False)
        referral_incentive = db.Column(db.String(120))
        access_token = db.Column(db.String(64), index=True)
        trigger_milestone = db.Column(db.String(80))
        client_email = db.Column(db.String(200))
        requested_at = db.Column(db.DateTime, default=datetime.utcnow)
        completed_at = db.Column(db.DateTime)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    class MarketingAsset(db.Model):
        __tablename__ = 'marketing_asset'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True, index=True)
        photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=True, index=True)
        title = db.Column(db.String(300))
        asset_type = db.Column(db.String(40), default='photo')
        tags_json = db.Column(db.Text)
        use_cases_json = db.Column(db.Text)
        document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=True)
        external_url = db.Column(db.String(500))
        phase = db.Column(db.String(80))
        trade = db.Column(db.String(80))
        meta_json = db.Column(db.Text)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingCollateralTemplate(db.Model):
        __tablename__ = 'marketing_collateral_template'
        id = db.Column(db.Integer, primary_key=True)
        key = db.Column(db.String(40), unique=True, nullable=False)
        name = db.Column(db.String(200))
        body_html = db.Column(db.Text)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class MarketingCampaignRecipient(db.Model):
        __tablename__ = 'marketing_campaign_recipient'
        id = db.Column(db.Integer, primary_key=True)
        campaign_id = db.Column(db.Integer, db.ForeignKey('marketing_campaign.id'), nullable=False, index=True)
        lead_id = db.Column(db.Integer, db.ForeignKey('marketing_lead.id'), nullable=True)
        email = db.Column(db.String(200))
        phone = db.Column(db.String(40))
        channel = db.Column(db.String(20), default='email')
        token = db.Column(db.String(64), unique=True, index=True)
        opened_at = db.Column(db.DateTime)
        clicked_at = db.Column(db.DateTime)
        converted_at = db.Column(db.DateTime)
        status = db.Column(db.String(30), default='queued')
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingAutomationRule(db.Model):
        __tablename__ = 'marketing_automation_rule'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(200), nullable=False)
        trigger_type = db.Column(db.String(40), nullable=False)
        trigger_value = db.Column(db.String(80))
        action_type = db.Column(db.String(40), nullable=False)
        action_config_json = db.Column(db.Text)
        enabled = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingReferral(db.Model):
        __tablename__ = 'marketing_referral'
        id = db.Column(db.Integer, primary_key=True)
        referrer_lead_id = db.Column(db.Integer, db.ForeignKey('marketing_lead.id'), nullable=True)
        referred_lead_id = db.Column(db.Integer, db.ForeignKey('marketing_lead.id'), nullable=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        incentive_type = db.Column(db.String(40))
        incentive_value = db.Column(db.Float, default=0)
        status = db.Column(db.String(30), default='pending')
        notes = db.Column(db.Text)
        incentive_code = db.Column(db.String(40))
        issued_at = db.Column(db.DateTime)
        redeemed_at = db.Column(db.DateTime)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingProposal(db.Model):
        __tablename__ = 'marketing_proposal'
        id = db.Column(db.Integer, primary_key=True)
        lead_id = db.Column(db.Integer, db.ForeignKey('marketing_lead.id'), nullable=True)
        estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False, index=True)
        title = db.Column(db.String(300))
        template_key = db.Column(db.String(40), default='proposal')
        body_html = db.Column(db.Text)
        status = db.Column(db.String(30), default='draft')
        access_token = db.Column(db.String(64), unique=True, index=True)
        view_count = db.Column(db.Integer, default=0)
        last_viewed_at = db.Column(db.DateTime)
        signed_at = db.Column(db.DateTime)
        esign_envelope_id = db.Column(db.String(120))
        pdf_path = db.Column(db.String(400))
        engagement_json = db.Column(db.Text)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        sent_at = db.Column(db.DateTime)

    class MarketingContentBlock(db.Model):
        __tablename__ = 'marketing_content_block'
        id = db.Column(db.Integer, primary_key=True)
        category = db.Column(db.String(40), index=True)
        title = db.Column(db.String(200), nullable=False)
        body_html = db.Column(db.Text)
        meta_json = db.Column(db.Text)
        sort_order = db.Column(db.Integer, default=0)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class MarketingLandingPage(db.Model):
        __tablename__ = 'marketing_landing_page'
        id = db.Column(db.Integer, primary_key=True)
        slug = db.Column(db.String(120), unique=True, index=True)
        title = db.Column(db.String(300), nullable=False)
        status = db.Column(db.String(30), default='draft')
        sections_json = db.Column(db.Text)
        lead_form_json = db.Column(db.Text)
        seo_json = db.Column(db.Text)
        view_count = db.Column(db.Integer, default=0)
        published_at = db.Column(db.DateTime)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingSpend(db.Model):
        __tablename__ = 'marketing_spend'
        id = db.Column(db.Integer, primary_key=True)
        channel = db.Column(db.String(80))
        label = db.Column(db.String(200))
        amount = db.Column(db.Float, default=0)
        period_start = db.Column(db.Date)
        period_end = db.Column(db.Date)
        campaign_id = db.Column(db.Integer, db.ForeignKey('marketing_campaign.id'), nullable=True)
        notes = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingCampaignTemplate(db.Model):
        __tablename__ = 'marketing_campaign_template'
        id = db.Column(db.Integer, primary_key=True)
        key = db.Column(db.String(40), unique=True, nullable=False)
        name = db.Column(db.String(200))
        channel = db.Column(db.String(20), default='email')
        subject = db.Column(db.String(300))
        body_html = db.Column(db.Text)
        body_text = db.Column(db.Text)
        segment_json = db.Column(db.Text)

    class MarketingBrandKit(db.Model):
        __tablename__ = 'marketing_brand_kit'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(120), default='Default')
        is_default = db.Column(db.Boolean, default=True)
        logo_url = db.Column(db.String(500))
        colors_json = db.Column(db.Text)
        fonts_json = db.Column(db.Text)
        header_html = db.Column(db.Text)
        footer_html = db.Column(db.Text)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class MarketingPortalPack(db.Model):
        __tablename__ = 'marketing_portal_pack'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), unique=True, nullable=False, index=True)
        warranty_doc_ids_json = db.Column(db.Text)
        manual_doc_ids_json = db.Column(db.Text)
        share_testimonials_ok = db.Column(db.Boolean, default=True)
        branding_json = db.Column(db.Text)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    return {
        'MarketingLead': MarketingLead,
        'MarketingCaseStudy': MarketingCaseStudy,
        'MarketingCampaign': MarketingCampaign,
        'MarketingReviewRequest': MarketingReviewRequest,
        'MarketingAsset': MarketingAsset,
        'MarketingCollateralTemplate': MarketingCollateralTemplate,
        'MarketingCampaignRecipient': MarketingCampaignRecipient,
        'MarketingAutomationRule': MarketingAutomationRule,
        'MarketingReferral': MarketingReferral,
        'MarketingProposal': MarketingProposal,
        'MarketingContentBlock': MarketingContentBlock,
        'MarketingLandingPage': MarketingLandingPage,
        'MarketingSpend': MarketingSpend,
        'MarketingCampaignTemplate': MarketingCampaignTemplate,
        'MarketingBrandKit': MarketingBrandKit,
        'MarketingPortalPack': MarketingPortalPack,
    }
