"""Extended platform ORM models."""
from datetime import datetime


def define_extended_platform_models(db):
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

    class OperationsAiMessage(db.Model):
        __tablename__ = 'operations_ai_message'
        id = db.Column(db.Integer, primary_key=True)
        thread_id = db.Column(db.String(64), nullable=False, index=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        role = db.Column(db.String(20), default='user')
        content = db.Column(db.Text)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class OperationsPaymentLine(db.Model):
        __tablename__ = 'operations_payment_line'
        id = db.Column(db.Integer, primary_key=True)
        batch_record_id = db.Column(db.Integer, db.ForeignKey('extended_module_record.id'), nullable=False)
        vendor_name = db.Column(db.String(200))
        invoice_record_id = db.Column(db.Integer, nullable=True)
        amount = db.Column(db.Float, default=0)
        status = db.Column(db.String(30), default='Pending')
        lien_waiver_ok = db.Column(db.Boolean, default=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class OperationsReportRun(db.Model):
        __tablename__ = 'operations_report_run'
        id = db.Column(db.Integer, primary_key=True)
        report_record_id = db.Column(db.Integer, db.ForeignKey('extended_module_record.id'), nullable=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        source = db.Column(db.String(40))
        row_count = db.Column(db.Integer, default=0)
        result_json = db.Column(db.Text)
        csv_text = db.Column(db.Text)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class OperationsBimAsset(db.Model):
        __tablename__ = 'operations_bim_asset'
        id = db.Column(db.Integer, primary_key=True)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        title = db.Column(db.String(300))
        filename = db.Column(db.String(300))
        stored_path = db.Column(db.String(500))
        file_ext = db.Column(db.String(20))
        file_size = db.Column(db.Integer, default=0)
        discipline = db.Column(db.String(80))
        revision = db.Column(db.String(40))
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    return {
        'ExtendedModuleRecord': ExtendedModuleRecord,
        'OperationsAiMessage': OperationsAiMessage,
        'OperationsPaymentLine': OperationsPaymentLine,
        'OperationsReportRun': OperationsReportRun,
        'OperationsBimAsset': OperationsBimAsset,
    }
