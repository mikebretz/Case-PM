"""Extended platform ORM model — single flexible table for 20+ module types."""
from datetime import datetime


def define_extended_platform_model(db):
    class ExtendedModuleRecord(db.Model):
        __tablename__ = 'extended_module_record'
        id = db.Column(db.Integer, primary_key=True)
        module_key = db.Column(db.String(40), nullable=False, index=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True, index=True)
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True, index=True)
        number = db.Column(db.String(40))
        title = db.Column(db.String(300))
        status = db.Column(db.String(40), default='Draft')
        record_date = db.Column(db.Date)
        amount = db.Column(db.Float, default=0)
        simple_fields_json = db.Column(db.Text)
        advanced_fields_json = db.Column(db.Text)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    return ExtendedModuleRecord
