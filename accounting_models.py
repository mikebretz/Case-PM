"""Built-in Case PM accounting suite — ORM models (Sage 300–class ERP, standalone)."""
from __future__ import annotations

from datetime import datetime


def define_accounting_models(db):
    class AcctLedger(db.Model):
        """Company / entity books (multi-company)."""
        __tablename__ = 'acct_ledger'
        id = db.Column(db.Integer, primary_key=True)
        code = db.Column(db.String(20), unique=True, nullable=False)
        name = db.Column(db.String(200), nullable=False)
        base_currency = db.Column(db.String(3), default='USD')
        fiscal_year_end_month = db.Column(db.Integer, default=12)
        is_active = db.Column(db.Boolean, default=True)
        settings_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctGLAccount(db.Model):
        __tablename__ = 'acct_gl_account'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        account_number = db.Column(db.String(40), nullable=False, index=True)
        description = db.Column(db.String(200), nullable=False)
        account_type = db.Column(db.String(20), nullable=False)  # asset, liability, equity, revenue, expense
        normal_balance = db.Column(db.String(10), default='debit')
        parent_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=True)
        segments_json = db.Column(db.Text)
        status = db.Column(db.String(20), default='Active')
        is_posting = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctJournalBatch(db.Model):
        __tablename__ = 'acct_journal_batch'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        batch_number = db.Column(db.String(30), nullable=False)
        source = db.Column(db.String(40), default='GL')
        description = db.Column(db.String(300))
        batch_date = db.Column(db.Date)
        status = db.Column(db.String(20), default='Open')  # Open, Posted, Void
        posted_at = db.Column(db.DateTime, nullable=True)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctJournalLine(db.Model):
        __tablename__ = 'acct_journal_line'
        id = db.Column(db.Integer, primary_key=True)
        batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=False, index=True)
        line_number = db.Column(db.Integer, default=1)
        account_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=False)
        description = db.Column(db.String(300))
        debit = db.Column(db.Float, default=0)
        credit = db.Column(db.Float, default=0)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        reference = db.Column(db.String(80))

    class AcctVendor(db.Model):
        __tablename__ = 'acct_vendor'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(30), nullable=False)
        name = db.Column(db.String(200), nullable=False)
        terms = db.Column(db.String(40))
        tax_group = db.Column(db.String(40))
        email = db.Column(db.String(120))
        phone = db.Column(db.String(40))
        status = db.Column(db.String(20), default='Active')
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctCustomer(db.Model):
        __tablename__ = 'acct_customer'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(30), nullable=False)
        name = db.Column(db.String(200), nullable=False)
        terms = db.Column(db.String(40))
        tax_group = db.Column(db.String(40))
        credit_limit = db.Column(db.Float, default=0)
        email = db.Column(db.String(120))
        status = db.Column(db.String(20), default='Active')
        company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=True)
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctAPDocument(db.Model):
        __tablename__ = 'acct_ap_document'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        vendor_id = db.Column(db.Integer, db.ForeignKey('acct_vendor.id'), nullable=False)
        document_number = db.Column(db.String(40), nullable=False)
        document_type = db.Column(db.String(20), default='Invoice')
        document_date = db.Column(db.Date)
        due_date = db.Column(db.Date)
        amount = db.Column(db.Float, default=0)
        amount_paid = db.Column(db.Float, default=0)
        status = db.Column(db.String(20), default='Open')
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        po_reference = db.Column(db.String(40))
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctARDocument(db.Model):
        __tablename__ = 'acct_ar_document'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False)
        document_number = db.Column(db.String(40), nullable=False)
        document_type = db.Column(db.String(20), default='Invoice')
        document_date = db.Column(db.Date)
        due_date = db.Column(db.Date)
        amount = db.Column(db.Float, default=0)
        amount_paid = db.Column(db.Float, default=0)
        status = db.Column(db.String(20), default='Open')
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctBankAccount(db.Model):
        __tablename__ = 'acct_bank_account'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        name = db.Column(db.String(200), nullable=False)
        gl_account_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=True)
        currency = db.Column(db.String(3), default='USD')
        last_reconciled_date = db.Column(db.Date, nullable=True)
        status = db.Column(db.String(20), default='Active')

    class AcctBankTransaction(db.Model):
        __tablename__ = 'acct_bank_transaction'
        id = db.Column(db.Integer, primary_key=True)
        bank_account_id = db.Column(db.Integer, db.ForeignKey('acct_bank_account.id'), nullable=False, index=True)
        transaction_date = db.Column(db.Date)
        description = db.Column(db.String(300))
        amount = db.Column(db.Float, default=0)
        transaction_type = db.Column(db.String(20), default='Payment')
        reconciled = db.Column(db.Boolean, default=False)
        reference = db.Column(db.String(80))

    class AcctTaxGroup(db.Model):
        __tablename__ = 'acct_tax_group'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        description = db.Column(db.String(200))
        rate_percent = db.Column(db.Float, default=0)
        authority = db.Column(db.String(80))

    class AcctInventoryItem(db.Model):
        __tablename__ = 'acct_inventory_item'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        item_number = db.Column(db.String(40), nullable=False)
        description = db.Column(db.String(300))
        uom = db.Column(db.String(10), default='EA')
        qty_on_hand = db.Column(db.Float, default=0)
        unit_cost = db.Column(db.Float, default=0)
        status = db.Column(db.String(20), default='Active')

    class AcctPurchaseOrder(db.Model):
        __tablename__ = 'acct_purchase_order'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        vendor_id = db.Column(db.Integer, db.ForeignKey('acct_vendor.id'), nullable=True)
        po_number = db.Column(db.String(40), nullable=False)
        status = db.Column(db.String(20), default='Open')
        order_date = db.Column(db.Date)
        total_amount = db.Column(db.Float, default=0)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        lines_json = db.Column(db.Text)

    class AcctSalesOrder(db.Model):
        __tablename__ = 'acct_sales_order'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=True)
        order_number = db.Column(db.String(40), nullable=False)
        status = db.Column(db.String(20), default='Open')
        order_date = db.Column(db.Date)
        total_amount = db.Column(db.Float, default=0)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        lines_json = db.Column(db.Text)

    class AcctFixedAsset(db.Model):
        __tablename__ = 'acct_fixed_asset'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        asset_number = db.Column(db.String(40), nullable=False)
        description = db.Column(db.String(300))
        acquisition_date = db.Column(db.Date)
        acquisition_cost = db.Column(db.Float, default=0)
        book = db.Column(db.String(20), default='GAAP')
        status = db.Column(db.String(20), default='Active')

    class AcctPayrollRun(db.Model):
        __tablename__ = 'acct_payroll_run'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        run_number = db.Column(db.String(30), nullable=False)
        pay_date = db.Column(db.Date)
        status = db.Column(db.String(20), default='Open')
        total_gross = db.Column(db.Float, default=0)
        total_net = db.Column(db.Float, default=0)

    return {
        'AcctLedger': AcctLedger,
        'AcctGLAccount': AcctGLAccount,
        'AcctJournalBatch': AcctJournalBatch,
        'AcctJournalLine': AcctJournalLine,
        'AcctVendor': AcctVendor,
        'AcctCustomer': AcctCustomer,
        'AcctAPDocument': AcctAPDocument,
        'AcctARDocument': AcctARDocument,
        'AcctBankAccount': AcctBankAccount,
        'AcctBankTransaction': AcctBankTransaction,
        'AcctTaxGroup': AcctTaxGroup,
        'AcctInventoryItem': AcctInventoryItem,
        'AcctPurchaseOrder': AcctPurchaseOrder,
        'AcctSalesOrder': AcctSalesOrder,
        'AcctFixedAsset': AcctFixedAsset,
        'AcctPayrollRun': AcctPayrollRun,
    }
