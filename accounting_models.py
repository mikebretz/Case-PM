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
        parent_ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=True, index=True)
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
        segments_json = db.Column(db.Text)

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
        vendor_group_id = db.Column(db.Integer, db.ForeignKey('acct_vendor_group.id'), nullable=True, index=True)
        tax_id = db.Column(db.String(30))
        is_1099 = db.Column(db.Boolean, default=False)
        form_1099_type = db.Column(db.String(10), default='NEC')
        default_withhold_percent = db.Column(db.Float, default=0)
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctVendorGroup(db.Model):
        __tablename__ = 'acct_vendor_group'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        name = db.Column(db.String(120), nullable=False)
        terms = db.Column(db.String(40))
        status = db.Column(db.String(20), default='Active')

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
        customer_group_id = db.Column(db.Integer, db.ForeignKey('acct_customer_group.id'), nullable=True, index=True)
        credit_hold = db.Column(db.Boolean, default=False)
        national_account_code = db.Column(db.String(40))
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctCustomerGroup(db.Model):
        __tablename__ = 'acct_customer_group'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        name = db.Column(db.String(120), nullable=False)
        credit_limit = db.Column(db.Float, default=0)
        status = db.Column(db.String(20), default='Active')

    class AcctCustomerShipTo(db.Model):
        __tablename__ = 'acct_customer_ship_to'
        id = db.Column(db.Integer, primary_key=True)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        name = db.Column(db.String(120), nullable=False)
        address_json = db.Column(db.Text)
        is_default = db.Column(db.Boolean, default=False)
        status = db.Column(db.String(20), default='Active')

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
        purchase_order_id = db.Column(db.Integer, db.ForeignKey('acct_purchase_order.id'), nullable=True, index=True)
        retainage_amount = db.Column(db.Float, default=0)
        withhold_amount = db.Column(db.Float, default=0)
        gross_amount = db.Column(db.Float, default=0)
        currency_code = db.Column(db.String(3), default='USD')
        fx_rate = db.Column(db.Float, default=1.0)
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctAPRecurringPayable(db.Model):
        __tablename__ = 'acct_ap_recurring_payable'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        vendor_id = db.Column(db.Integer, db.ForeignKey('acct_vendor.id'), nullable=False)
        description = db.Column(db.String(200))
        amount = db.Column(db.Float, default=0)
        frequency = db.Column(db.String(20), default='monthly')  # monthly, weekly
        next_run_date = db.Column(db.Date)
        last_run_date = db.Column(db.Date, nullable=True)
        is_active = db.Column(db.Boolean, default=True)
        document_number_prefix = db.Column(db.String(30), default='REC-AP')

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
        ship_to_id = db.Column(db.Integer, db.ForeignKey('acct_customer_ship_to.id'), nullable=True)
        parent_document_id = db.Column(db.Integer, db.ForeignKey('acct_ar_document.id'), nullable=True)
        currency_code = db.Column(db.String(3), default='USD')
        fx_rate = db.Column(db.Float, default=1.0)
        details_json = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctARRecurringInvoice(db.Model):
        __tablename__ = 'acct_ar_recurring_invoice'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False)
        description = db.Column(db.String(200))
        amount = db.Column(db.Float, default=0)
        frequency = db.Column(db.String(20), default='monthly')
        next_run_date = db.Column(db.Date)
        last_run_date = db.Column(db.Date, nullable=True)
        is_active = db.Column(db.Boolean, default=True)
        document_number_prefix = db.Column(db.String(30), default='REC-AR')

    class AcctARDunningLog(db.Model):
        __tablename__ = 'acct_ar_dunning_log'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False)
        level = db.Column(db.Integer, default=1)
        message = db.Column(db.String(500))
        sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctARReceiptBatch(db.Model):
        __tablename__ = 'acct_ar_receipt_batch'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        batch_number = db.Column(db.String(30), nullable=False)
        batch_date = db.Column(db.Date)
        status = db.Column(db.String(20), default='Open')
        posted_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctARReceiptBatchLine(db.Model):
        __tablename__ = 'acct_ar_receipt_batch_line'
        id = db.Column(db.Integer, primary_key=True)
        batch_id = db.Column(db.Integer, db.ForeignKey('acct_ar_receipt_batch.id'), nullable=False, index=True)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False)
        ar_document_id = db.Column(db.Integer, db.ForeignKey('acct_ar_document.id'), nullable=True)
        amount = db.Column(db.Float, default=0)
        payment_method = db.Column(db.String(20), default='ACH')

    class AcctGLBudget(db.Model):
        __tablename__ = 'acct_gl_budget'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        name = db.Column(db.String(80), nullable=False)
        fiscal_year = db.Column(db.Integer, nullable=False)
        status = db.Column(db.String(20), default='Active')

    class AcctGLBudgetLine(db.Model):
        __tablename__ = 'acct_gl_budget_line'
        id = db.Column(db.Integer, primary_key=True)
        budget_id = db.Column(db.Integer, db.ForeignKey('acct_gl_budget.id'), nullable=False, index=True)
        account_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=False)
        period_key = db.Column(db.String(7), nullable=False)  # YYYY-MM
        amount = db.Column(db.Float, default=0)

    class AcctGLRecurringJournal(db.Model):
        __tablename__ = 'acct_gl_recurring_journal'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(30), nullable=False)
        description = db.Column(db.String(300))
        frequency = db.Column(db.String(20), default='monthly')
        next_run_date = db.Column(db.Date)
        last_run_date = db.Column(db.Date, nullable=True)
        source = db.Column(db.String(20), default='GL')
        lines_json = db.Column(db.Text)
        is_active = db.Column(db.Boolean, default=True)

    class AcctGLAllocationTemplate(db.Model):
        __tablename__ = 'acct_gl_allocation_template'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(30), nullable=False)
        description = db.Column(db.String(300))
        pool_account_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=True)
        lines_json = db.Column(db.Text)
        is_active = db.Column(db.Boolean, default=True)

    class AcctIntercompanyEntry(db.Model):
        __tablename__ = 'acct_intercompany_entry'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        entry_number = db.Column(db.String(30), nullable=False)
        counterparty_ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=True)
        from_account_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=False)
        to_account_id = db.Column(db.Integer, db.ForeignKey('acct_gl_account.id'), nullable=False)
        amount = db.Column(db.Float, default=0)
        description = db.Column(db.String(300))
        entry_date = db.Column(db.Date)
        status = db.Column(db.String(20), default='Open')
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
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
        matched_payment_id = db.Column(db.Integer, db.ForeignKey('acct_ap_payment.id'), nullable=True)
        matched_receipt_id = db.Column(db.Integer, db.ForeignKey('acct_ar_receipt.id'), nullable=True)
        statement_ref = db.Column(db.String(80))

    class AcctTaxGroup(db.Model):
        __tablename__ = 'acct_tax_group'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        description = db.Column(db.String(200))
        rate_percent = db.Column(db.Float, default=0)
        authority = db.Column(db.String(80))
        tax_type = db.Column(db.String(20), default='sales')  # sales, use, withholding
        applies_to = db.Column(db.String(10), default='both')  # ap, ar, both
        is_active = db.Column(db.Boolean, default=True)

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

    class AcctInventoryTransaction(db.Model):
        __tablename__ = 'acct_inventory_transaction'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        item_id = db.Column(db.Integer, db.ForeignKey('acct_inventory_item.id'), nullable=False, index=True)
        txn_type = db.Column(db.String(20), default='adjust')  # receive, issue, adjust, po_receipt
        qty_delta = db.Column(db.Float, default=0)
        unit_cost = db.Column(db.Float, default=0)
        reference = db.Column(db.String(80))
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        accumulated_depreciation = db.Column(db.Float, default=0)
        useful_life_months = db.Column(db.Integer, default=60)
        depreciation_method = db.Column(db.String(30), default='straight_line')
        book = db.Column(db.String(20), default='GAAP')
        status = db.Column(db.String(20), default='Active')
        location = db.Column(db.String(120))
        serial_number = db.Column(db.String(80))
        salvage_value = db.Column(db.Float, default=0)
        in_service_date = db.Column(db.Date, nullable=True)

    class AcctPostLink(db.Model):
        """Idempotent link from construction events to accounting documents."""
        __tablename__ = 'acct_post_link'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        source_type = db.Column(db.String(40), nullable=False)
        source_key = db.Column(db.String(120), nullable=False, index=True)
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        ap_document_id = db.Column(db.Integer, db.ForeignKey('acct_ap_document.id'), nullable=True)
        ar_document_id = db.Column(db.Integer, db.ForeignKey('acct_ar_document.id'), nullable=True)
        purchase_order_id = db.Column(db.Integer, db.ForeignKey('acct_purchase_order.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctAPPayment(db.Model):
        __tablename__ = 'acct_ap_payment'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        payment_number = db.Column(db.String(40), nullable=False)
        vendor_id = db.Column(db.Integer, db.ForeignKey('acct_vendor.id'), nullable=False)
        payment_date = db.Column(db.Date)
        amount = db.Column(db.Float, default=0)
        payment_method = db.Column(db.String(20), default='Check')
        bank_account_id = db.Column(db.Integer, db.ForeignKey('acct_bank_account.id'), nullable=True)
        status = db.Column(db.String(20), default='Posted')
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        payment_batch_id = db.Column(db.Integer, db.ForeignKey('acct_payment_batch.id'), nullable=True, index=True)
        check_number = db.Column(db.String(20), nullable=True)
        void_reason = db.Column(db.String(200), nullable=True)
        voided_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctPaymentBatch(db.Model):
        """AP payment batch — checks, ACH, wire (Payment Processing)."""
        __tablename__ = 'acct_payment_batch'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        batch_number = db.Column(db.String(30), nullable=False)
        status = db.Column(db.String(20), default='Open')  # Open, Posted, Cancelled
        payment_date = db.Column(db.Date)
        payment_method = db.Column(db.String(20), default='Check')
        bank_account_id = db.Column(db.Integer, db.ForeignKey('acct_bank_account.id'), nullable=True)
        check_number_start = db.Column(db.String(20), nullable=True)
        total_amount = db.Column(db.Float, default=0)
        notes = db.Column(db.Text)
        posted_at = db.Column(db.DateTime, nullable=True)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctPaymentBatchLine(db.Model):
        __tablename__ = 'acct_payment_batch_line'
        id = db.Column(db.Integer, primary_key=True)
        batch_id = db.Column(db.Integer, db.ForeignKey('acct_payment_batch.id'), nullable=False, index=True)
        vendor_id = db.Column(db.Integer, db.ForeignKey('acct_vendor.id'), nullable=False)
        ap_document_id = db.Column(db.Integer, db.ForeignKey('acct_ap_document.id'), nullable=True)
        amount = db.Column(db.Float, default=0)
        check_number = db.Column(db.String(20), nullable=True)
        reference = db.Column(db.String(80))

    class AcctPayNowLink(db.Model):
        """Customer invoice pay link (card/ACH portal)."""
        __tablename__ = 'acct_pay_now_link'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        token = db.Column(db.String(64), unique=True, nullable=False, index=True)
        ar_document_id = db.Column(db.Integer, db.ForeignKey('acct_ar_document.id'), nullable=False)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False)
        amount = db.Column(db.Float, default=0)
        status = db.Column(db.String(20), default='Pending')  # Pending, Paid, Cancelled, Expired
        payment_method = db.Column(db.String(20), default='card')
        expires_at = db.Column(db.DateTime, nullable=True)
        paid_at = db.Column(db.DateTime, nullable=True)
        ar_receipt_id = db.Column(db.Integer, db.ForeignKey('acct_ar_receipt.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctConsolidationRun(db.Model):
        __tablename__ = 'acct_consolidation_run'
        id = db.Column(db.Integer, primary_key=True)
        parent_ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        run_number = db.Column(db.String(30), nullable=False)
        period_end = db.Column(db.Date)
        status = db.Column(db.String(20), default='Open')  # Open, Posted
        elimination_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        rollup_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        details_json = db.Column(db.Text)
        posted_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctAPPaymentApply(db.Model):
        __tablename__ = 'acct_ap_payment_apply'
        id = db.Column(db.Integer, primary_key=True)
        payment_id = db.Column(db.Integer, db.ForeignKey('acct_ap_payment.id'), nullable=False, index=True)
        ap_document_id = db.Column(db.Integer, db.ForeignKey('acct_ap_document.id'), nullable=False)
        amount = db.Column(db.Float, default=0)

    class AcctARReceipt(db.Model):
        __tablename__ = 'acct_ar_receipt'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        receipt_number = db.Column(db.String(40), nullable=False)
        customer_id = db.Column(db.Integer, db.ForeignKey('acct_customer.id'), nullable=False)
        receipt_date = db.Column(db.Date)
        amount = db.Column(db.Float, default=0)
        payment_method = db.Column(db.String(20), default='ACH')
        bank_account_id = db.Column(db.Integer, db.ForeignKey('acct_bank_account.id'), nullable=True)
        status = db.Column(db.String(20), default='Posted')
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctARReceiptApply(db.Model):
        __tablename__ = 'acct_ar_receipt_apply'
        id = db.Column(db.Integer, primary_key=True)
        receipt_id = db.Column(db.Integer, db.ForeignKey('acct_ar_receipt.id'), nullable=False, index=True)
        ar_document_id = db.Column(db.Integer, db.ForeignKey('acct_ar_document.id'), nullable=False)
        amount = db.Column(db.Float, default=0)

    class AcctDepreciationRun(db.Model):
        __tablename__ = 'acct_depreciation_run'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        run_number = db.Column(db.String(30), nullable=False)
        period_date = db.Column(db.Date)
        status = db.Column(db.String(20), default='Posted')
        total_amount = db.Column(db.Float, default=0)
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctReportDefinition(db.Model):
        """Saved custom report — filters and layout for Accounting → Reports."""
        __tablename__ = 'acct_report_definition'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        name = db.Column(db.String(120), nullable=False)
        report_type = db.Column(db.String(40), nullable=False)
        filters_json = db.Column(db.Text)
        columns_json = db.Column(db.Text)
        is_favorite = db.Column(db.Boolean, default=False)
        created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class AcctPayrollRun(db.Model):
        __tablename__ = 'acct_payroll_run'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        run_number = db.Column(db.String(30), nullable=False)
        pay_date = db.Column(db.Date)
        period_start = db.Column(db.Date, nullable=True)
        period_end = db.Column(db.Date, nullable=True)
        pay_frequency = db.Column(db.String(20), default='biweekly')  # weekly, biweekly, semimonthly, monthly
        status = db.Column(db.String(20), default='Open')
        total_gross = db.Column(db.Float, default=0)
        total_net = db.Column(db.Float, default=0)
        total_taxes = db.Column(db.Float, default=0)
        total_deductions = db.Column(db.Float, default=0)
        total_employer_taxes = db.Column(db.Float, default=0)
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        notes = db.Column(db.Text)

    class AcctPayrollEmployee(db.Model):
        __tablename__ = 'acct_payroll_employee'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        employee_number = db.Column(db.String(30), nullable=False)
        first_name = db.Column(db.String(80), nullable=False)
        last_name = db.Column(db.String(80), nullable=False)
        status = db.Column(db.String(20), default='Active')
        pay_type = db.Column(db.String(20), default='hourly')  # hourly, salary
        hourly_rate = db.Column(db.Float, default=0)
        annual_salary = db.Column(db.Float, default=0)
        default_project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        department = db.Column(db.String(80))
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        federal_wh_percent = db.Column(db.Float, default=22.0)
        state_wh_percent = db.Column(db.Float, default=5.0)
        payment_method = db.Column(db.String(20), default='direct_deposit')
        bank_account_last4 = db.Column(db.String(4))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctPayrollDeduction(db.Model):
        __tablename__ = 'acct_payroll_deduction'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        code = db.Column(db.String(20), nullable=False)
        description = db.Column(db.String(200))
        deduction_type = db.Column(db.String(20), default='posttax')  # pretax, posttax
        calc_method = db.Column(db.String(10), default='fixed')  # fixed, percent
        amount = db.Column(db.Float, default=0)
        percent = db.Column(db.Float, default=0)
        is_active = db.Column(db.Boolean, default=True)

    class AcctPayrollEmployeeDeduction(db.Model):
        __tablename__ = 'acct_payroll_employee_deduction'
        id = db.Column(db.Integer, primary_key=True)
        employee_id = db.Column(db.Integer, db.ForeignKey('acct_payroll_employee.id'), nullable=False, index=True)
        deduction_id = db.Column(db.Integer, db.ForeignKey('acct_payroll_deduction.id'), nullable=False)
        override_amount = db.Column(db.Float, nullable=True)

    class AcctPayrollRunLine(db.Model):
        __tablename__ = 'acct_payroll_run_line'
        id = db.Column(db.Integer, primary_key=True)
        run_id = db.Column(db.Integer, db.ForeignKey('acct_payroll_run.id'), nullable=False, index=True)
        employee_id = db.Column(db.Integer, db.ForeignKey('acct_payroll_employee.id'), nullable=False)
        hours_regular = db.Column(db.Float, default=0)
        hours_overtime = db.Column(db.Float, default=0)
        gross_pay = db.Column(db.Float, default=0)
        federal_wh = db.Column(db.Float, default=0)
        state_wh = db.Column(db.Float, default=0)
        fica_employee = db.Column(db.Float, default=0)
        medicare_employee = db.Column(db.Float, default=0)
        other_deductions = db.Column(db.Float, default=0)
        net_pay = db.Column(db.Float, default=0)
        employer_fica = db.Column(db.Float, default=0)
        employer_medicare = db.Column(db.Float, default=0)
        project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
        check_number = db.Column(db.String(20))
        payment_method = db.Column(db.String(20))
        details_json = db.Column(db.Text)

    class AcctCurrencyRate(db.Model):
        __tablename__ = 'acct_currency_rate'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        currency_code = db.Column(db.String(3), nullable=False)
        rate_date = db.Column(db.Date, nullable=False)
        rate_to_functional = db.Column(db.Float, default=1.0)
        source = db.Column(db.String(40), default='manual')
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class AcctRevaluationRun(db.Model):
        __tablename__ = 'acct_revaluation_run'
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('acct_ledger.id'), nullable=False, index=True)
        run_number = db.Column(db.String(30), nullable=False)
        period_end = db.Column(db.Date)
        status = db.Column(db.String(20), default='Posted')
        journal_batch_id = db.Column(db.Integer, db.ForeignKey('acct_journal_batch.id'), nullable=True)
        details_json = db.Column(db.Text)
        posted_at = db.Column(db.DateTime, default=datetime.utcnow)

    return {
        'AcctLedger': AcctLedger,
        'AcctGLAccount': AcctGLAccount,
        'AcctJournalBatch': AcctJournalBatch,
        'AcctJournalLine': AcctJournalLine,
        'AcctVendor': AcctVendor,
        'AcctVendorGroup': AcctVendorGroup,
        'AcctCustomer': AcctCustomer,
        'AcctCustomerGroup': AcctCustomerGroup,
        'AcctCustomerShipTo': AcctCustomerShipTo,
        'AcctAPDocument': AcctAPDocument,
        'AcctAPRecurringPayable': AcctAPRecurringPayable,
        'AcctARDocument': AcctARDocument,
        'AcctARRecurringInvoice': AcctARRecurringInvoice,
        'AcctARDunningLog': AcctARDunningLog,
        'AcctARReceiptBatch': AcctARReceiptBatch,
        'AcctARReceiptBatchLine': AcctARReceiptBatchLine,
        'AcctGLBudget': AcctGLBudget,
        'AcctGLBudgetLine': AcctGLBudgetLine,
        'AcctGLRecurringJournal': AcctGLRecurringJournal,
        'AcctGLAllocationTemplate': AcctGLAllocationTemplate,
        'AcctIntercompanyEntry': AcctIntercompanyEntry,
        'AcctBankAccount': AcctBankAccount,
        'AcctBankTransaction': AcctBankTransaction,
        'AcctTaxGroup': AcctTaxGroup,
        'AcctInventoryItem': AcctInventoryItem,
        'AcctInventoryTransaction': AcctInventoryTransaction,
        'AcctPurchaseOrder': AcctPurchaseOrder,
        'AcctSalesOrder': AcctSalesOrder,
        'AcctFixedAsset': AcctFixedAsset,
        'AcctPostLink': AcctPostLink,
        'AcctAPPayment': AcctAPPayment,
        'AcctAPPaymentApply': AcctAPPaymentApply,
        'AcctARReceipt': AcctARReceipt,
        'AcctARReceiptApply': AcctARReceiptApply,
        'AcctDepreciationRun': AcctDepreciationRun,
        'AcctReportDefinition': AcctReportDefinition,
        'AcctPayrollRun': AcctPayrollRun,
        'AcctPayrollEmployee': AcctPayrollEmployee,
        'AcctPayrollDeduction': AcctPayrollDeduction,
        'AcctPayrollEmployeeDeduction': AcctPayrollEmployeeDeduction,
        'AcctPayrollRunLine': AcctPayrollRunLine,
        'AcctPaymentBatch': AcctPaymentBatch,
        'AcctPaymentBatchLine': AcctPaymentBatchLine,
        'AcctPayNowLink': AcctPayNowLink,
        'AcctConsolidationRun': AcctConsolidationRun,
        'AcctCurrencyRate': AcctCurrencyRate,
        'AcctRevaluationRun': AcctRevaluationRun,
    }
