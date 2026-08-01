"""Bidder plan room — subcontractor registration, approval, and published opportunities."""
from __future__ import annotations

from datetime import datetime


def define_bidder_network_models(db):
    class BidderNetworkRegistration(db.Model):
        __tablename__ = 'bidder_network_registration'
        id = db.Column(db.Integer, primary_key=True)
        status = db.Column(db.String(20), default='pending', index=True)  # pending | approved | rejected
        company_name = db.Column(db.String(200), nullable=False)
        contact_name = db.Column(db.String(200), nullable=False)
        email = db.Column(db.String(255), nullable=False, index=True)
        phone = db.Column(db.String(40))
        password_hash = db.Column(db.String(256))
        specialties_json = db.Column(db.Text)  # JSON list of trade/specialty labels
        comments = db.Column(db.Text)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True, index=True)
        reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        reviewed_at = db.Column(db.DateTime)
        rejection_reason = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class BidderNetworkDocument(db.Model):
        __tablename__ = 'bidder_network_document'
        id = db.Column(db.Integer, primary_key=True)
        registration_id = db.Column(db.Integer, db.ForeignKey('bidder_network_registration.id'), nullable=False, index=True)
        original_filename = db.Column(db.String(300))
        stored_filename = db.Column(db.String(300), nullable=False)
        content_type = db.Column(db.String(120))
        size_bytes = db.Column(db.Integer, default=0)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class PlanRoomClarification(db.Model):
        __tablename__ = 'plan_room_clarification'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
        bid_package_id = db.Column(db.Integer, db.ForeignKey('bid_package.id'), nullable=True, index=True)
        asked_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        asker_company = db.Column(db.String(200))
        asker_name = db.Column(db.String(200))
        subject = db.Column(db.String(300))
        question_text = db.Column(db.Text, nullable=False)
        answer_text = db.Column(db.Text)
        answered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        answered_at = db.Column(db.DateTime)
        is_public = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class PlanRoomAddendumAck(db.Model):
        __tablename__ = 'plan_room_addendum_ack'
        id = db.Column(db.Integer, primary_key=True)
        addendum_id = db.Column(db.Integer, db.ForeignKey('bid_package_addendum.id'), nullable=False, index=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
        acknowledged_at = db.Column(db.DateTime, default=datetime.utcnow)

    class PlanRoomExternalSyncLog(db.Model):
        __tablename__ = 'plan_room_external_sync_log'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
        provider = db.Column(db.String(40), nullable=False)  # buildingconnected | tradetapp
        direction = db.Column(db.String(20), default='export')
        status = db.Column(db.String(20), default='success')
        summary_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    return {
        'BidderNetworkRegistration': BidderNetworkRegistration,
        'BidderNetworkDocument': BidderNetworkDocument,
        'PlanRoomClarification': PlanRoomClarification,
        'PlanRoomAddendumAck': PlanRoomAddendumAck,
        'PlanRoomExternalSyncLog': PlanRoomExternalSyncLog,
    }
