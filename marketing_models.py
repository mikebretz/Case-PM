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
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class MarketingCollateralTemplate(db.Model):
        __tablename__ = 'marketing_collateral_template'
        id = db.Column(db.Integer, primary_key=True)
        key = db.Column(db.String(40), unique=True, nullable=False)
        name = db.Column(db.String(200))
        body_html = db.Column(db.Text)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    return {
        'MarketingLead': MarketingLead,
        'MarketingCaseStudy': MarketingCaseStudy,
        'MarketingCampaign': MarketingCampaign,
        'MarketingReviewRequest': MarketingReviewRequest,
        'MarketingAsset': MarketingAsset,
        'MarketingCollateralTemplate': MarketingCollateralTemplate,
    }
