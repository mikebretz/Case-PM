"""
Unified posting from construction workflows into built-in G/L, A/P, and A/R.

Called from pay apps, commitments, and (optionally) after Sage queue events.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from accounting_persistence import (
    get_or_create_default_ledger,
    next_batch_number,
    post_journal_batch,
    seed_chart_of_accounts,
)

SUPPLEMENTAL_ACCOUNTS = [
    ('1710', 'Accumulated Depreciation', 'asset', 'credit'),
    ('5350', 'Depreciation Expense', 'expense', 'debit'),
]


def load_accounting_options():
    from program_settings_persistence import load_accounting_defaults
    d = load_accounting_defaults()
    return {
        'auto_post_enabled': str(d.get('auto_post_enabled', '1')) != '0',
        'cash_account': d.get('cash_account', '1000'),
        'ar_account': d.get('ar_account', '1100'),
        'ap_account': d.get('ap_account', '2000'),
        'revenue_account': d.get('revenue_account', '4000'),
        'subcontract_expense': d.get('subcontract_expense', '5100'),
        'materials_expense': d.get('materials_expense', '5200'),
        'payroll_liability': d.get('payroll_liability', '2300'),
        'labor_expense': d.get('labor_expense', '5000'),
        'accum_dep_account': d.get('accum_dep_account', '1710'),
        'depreciation_expense': d.get('depreciation_expense', '5350'),
    }


def _ensure_supplemental_accounts(db, AcctLedger, AcctGLAccount, ledger_id):
    for num, desc, atype, normal in SUPPLEMENTAL_ACCOUNTS:
        exists = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number=num).first()
        if not exists:
            db.session.add(AcctGLAccount(
                ledger_id=ledger_id,
                account_number=num,
                description=desc,
                account_type=atype,
                normal_balance=normal,
                is_posting=True,
                status='Active',
            ))
    db.session.flush()


def _account_by_number(AcctGLAccount, ledger_id, number):
    row = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number=str(number)).first()
    if not row:
        raise ValueError(f'G/L account {number} not found — open Accounting → G/L to seed chart')
    return row


def _existing_link(AcctPostLink, ledger_id, source_key):
    return AcctPostLink.query.filter_by(ledger_id=ledger_id, source_key=source_key).first()


def _create_posted_batch(
    db,
    models,
    *,
    ledger_id,
    source,
    description,
    lines,
    user_id=None,
):
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    batch = AcctJournalBatch(
        ledger_id=ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, ledger_id),
        source=source,
        description=description[:300],
        batch_date=date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    for i, ln in enumerate(lines, start=1):
        db.session.add(AcctJournalLine(
            batch_id=batch.id,
            line_number=i,
            account_id=ln['account_id'],
            description=ln.get('description') or '',
            debit=float(ln.get('debit') or 0),
            credit=float(ln.get('credit') or 0),
            project_id=ln.get('project_id'),
            reference=ln.get('reference') or '',
        ))
    db.session.flush()
    post_journal_batch(db, batch, AcctJournalLine)
    return batch


def _get_or_create_vendor(db, models, ledger_id, company_id, Company=None):
    AcctVendor = models['AcctVendor']
    if company_id and Company:
        try:
            com = Company.query.get(int(company_id))
        except (TypeError, ValueError):
            com = None
        if com:
            existing = AcctVendor.query.filter_by(ledger_id=ledger_id, company_id=com.id).first()
            if existing:
                return existing
            code = f'V-{com.id}'
            from sage_companies_service import resolve_sage_number
            details = {}
            if com.details_json:
                try:
                    details = json.loads(com.details_json)
                except (TypeError, json.JSONDecodeError):
                    details = {}
            sage_code = resolve_sage_number(
                com.type or '', details.get('external_id', ''),
                details.get('sage_ap_vendor_code', ''),
                details.get('sage_ar_customer_code', ''),
                details.get('sage_number', ''),
            )
            if sage_code:
                code = sage_code[:30]
            v = AcctVendor(
                ledger_id=ledger_id,
                code=code,
                name=com.name or code,
                company_id=com.id,
                status='Active',
            )
            db.session.add(v)
            db.session.flush()
            return v
    code = f'V-{company_id or "UNK"}'
    v = AcctVendor.query.filter_by(ledger_id=ledger_id, code=code).first()
    if v:
        return v
    v = AcctVendor(ledger_id=ledger_id, code=code[:30], name=f'Vendor {company_id}', status='Active')
    db.session.add(v)
    db.session.flush()
    return v


def _get_or_create_customer(db, models, ledger_id, project, Project):
    AcctCustomer = models['AcctCustomer']
    from program_settings_persistence import load_sage_defaults, merge_sage_context

    details = project.get_details() if hasattr(project, 'get_details') else {}
    sage = merge_sage_context(details, load_sage_defaults())
    code = (details.get('sage_ar_customer_code') or sage.get('sage_ar_customer_code') or '').strip()
    name = (details.get('owner_legal_name') or project.client or project.name or 'Owner').strip()
    if not code:
        code = f'C-P{project.id}'
    c = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=code[:30]).first()
    if c:
        return c
    c = AcctCustomer(ledger_id=ledger_id, code=code[:30], name=name[:200], status='Active')
    db.session.add(c)
    db.session.flush()
    return c


def _float_amount(*vals):
    for v in vals:
        if v is None:
            continue
        try:
            f = float(v)
            if f != 0:
                return round(f, 2)
        except (TypeError, ValueError):
            continue
    return 0.0


def process_construction_event(
    event_type,
    project_id,
    payload,
    *,
    db,
    models,
    user_id=None,
    Project=None,
    Company=None,
    commitment=None,
):
    """
    Post approved construction financials into built-in accounting.
    Returns dict with posted=True/False and document references.
    """
    opts = load_accounting_options()
    if not opts['auto_post_enabled']:
        return {'posted': False, 'skipped': 'auto_post_disabled'}

    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctPostLink = models['AcctPostLink']
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    AcctPurchaseOrder = models['AcctPurchaseOrder']

    ledger = get_or_create_default_ledger(db, AcctLedger)
    seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)
    _ensure_supplemental_accounts(db, AcctLedger, AcctGLAccount, ledger.id)

    data = payload or {}
    idem = (data.get('idempotency_key') or '').strip()
    if not idem:
        idem = f'{event_type}:{project_id}:{data.get("periodNumber") or data.get("company_id") or data.get("commitment_id") or ""}'

    if _existing_link(AcctPostLink, ledger.id, idem):
        return {'posted': False, 'skipped': 'already_posted', 'source_key': idem}

    project = Project.query.get(int(project_id)) if Project and project_id else None
    result = {'posted': False, 'source_key': idem, 'event_type': event_type}

    if event_type == 'G702Approved':
        amount = _float_amount(
            data.get('amount_due'), data.get('amountDue'), data.get('amount'),
            data.get('total'), data.get('billing_total'),
        )
        if amount <= 0 or not project:
            return {**result, 'skipped': 'no_amount_or_project'}
        period = data.get('periodNumber') or data.get('period_number') or ''
        customer = _get_or_create_customer(db, models, ledger.id, project, Project)
        doc_num = f'G702-P{project_id}-{period}'
        ar_doc = AcctARDocument(
            ledger_id=ledger.id,
            customer_id=customer.id,
            document_number=doc_num[:40],
            document_type='ProgressBilling',
            document_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            amount=amount,
            status='Open',
            project_id=project_id,
            details_json=json.dumps({'event': event_type, 'source_key': idem}),
        )
        db.session.add(ar_doc)
        db.session.flush()
        ar_acct = _account_by_number(AcctGLAccount, ledger.id, opts['ar_account'])
        rev_acct = _account_by_number(AcctGLAccount, ledger.id, opts['revenue_account'])
        batch = _create_posted_batch(
            db, models, ledger_id=ledger.id, source='AR',
            description=f'Owner billing G702 period {period}',
            user_id=user_id,
            lines=[
                {'account_id': ar_acct.id, 'debit': amount, 'credit': 0, 'project_id': project_id, 'reference': doc_num},
                {'account_id': rev_acct.id, 'debit': 0, 'credit': amount, 'project_id': project_id, 'reference': doc_num},
            ],
        )
        link = AcctPostLink(
            ledger_id=ledger.id, source_type=event_type, source_key=idem,
            journal_batch_id=batch.id, ar_document_id=ar_doc.id,
        )
        db.session.add(link)
        result.update({'posted': True, 'ar_document_id': ar_doc.id, 'journal_batch_id': batch.id})

    elif event_type == 'SubPayAppApproved':
        amount = _float_amount(
            data.get('total'), data.get('totalBilledThisPeriod'),
            data.get('amount'),
        )
        company_id = data.get('companyId') or data.get('company_id') or ''
        period = data.get('periodNumber') or data.get('period_number') or ''
        if amount <= 0:
            return {**result, 'skipped': 'no_amount'}
        vendor = _get_or_create_vendor(db, models, ledger.id, company_id, Company=Company)
        doc_num = f'SUB-P{project_id}-{company_id}-P{period}'[:40]
        ap_doc = AcctAPDocument(
            ledger_id=ledger.id,
            vendor_id=vendor.id,
            document_number=doc_num,
            document_type='SubPayApp',
            document_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            amount=amount,
            status='Open',
            project_id=project_id,
            details_json=json.dumps({'event': event_type, 'source_key': idem}),
        )
        db.session.add(ap_doc)
        db.session.flush()
        exp_acct = _account_by_number(AcctGLAccount, ledger.id, opts['subcontract_expense'])
        ap_acct = _account_by_number(AcctGLAccount, ledger.id, opts['ap_account'])
        batch = _create_posted_batch(
            db, models, ledger_id=ledger.id, source='AP',
            description=f'Subcontractor pay app company {company_id} period {period}',
            user_id=user_id,
            lines=[
                {'account_id': exp_acct.id, 'debit': amount, 'credit': 0, 'project_id': project_id},
                {'account_id': ap_acct.id, 'debit': 0, 'credit': amount, 'project_id': project_id},
            ],
        )
        link = AcctPostLink(
            ledger_id=ledger.id, source_type=event_type, source_key=idem,
            journal_batch_id=batch.id, ap_document_id=ap_doc.id,
        )
        db.session.add(link)
        result.update({'posted': True, 'ap_document_id': ap_doc.id, 'journal_batch_id': batch.id})

    elif event_type == 'CommitmentApproved' and commitment is not None:
        amount = _float_amount(
            getattr(commitment, 'current_amount', None),
            getattr(commitment, 'original_amount', None),
            data.get('amount'), data.get('total_amount'),
        )
        company_id = getattr(commitment, 'company_id', None) or data.get('company_id')
        vendor = _get_or_create_vendor(db, models, ledger.id, company_id, Company=Company)
        po_num = (getattr(commitment, 'number', None) or data.get('number') or f'CMT-{commitment.id}')[:40]
        po = AcctPurchaseOrder(
            ledger_id=ledger.id,
            vendor_id=vendor.id,
            po_number=po_num,
            status='Open',
            order_date=date.today(),
            total_amount=amount,
            project_id=getattr(commitment, 'project_id', project_id),
            lines_json=json.dumps({'commitment_id': commitment.id, 'type': getattr(commitment, 'commitment_type', '')}),
        )
        db.session.add(po)
        db.session.flush()
        if amount > 0:
            exp_num = opts['materials_expense'] if (getattr(commitment, 'commitment_type', '') == 'Purchase Order') else opts['subcontract_expense']
            exp_acct = _account_by_number(AcctGLAccount, ledger.id, exp_num)
            ap_acct = _account_by_number(AcctGLAccount, ledger.id, opts['ap_account'])
            batch = _create_posted_batch(
                db, models, ledger_id=ledger.id, source='PO',
                description=f'Commitment {po_num} approved — encumbrance',
                user_id=user_id,
                lines=[
                    {'account_id': exp_acct.id, 'debit': amount, 'credit': 0, 'project_id': po.project_id},
                    {'account_id': ap_acct.id, 'debit': 0, 'credit': amount, 'project_id': po.project_id},
                ],
            )
            ap_doc = AcctAPDocument(
                ledger_id=ledger.id,
                vendor_id=vendor.id,
                document_number=f'ENC-{po_num}'[:40],
                document_type='Commitment',
                document_date=date.today(),
                amount=amount,
                status='Open',
                project_id=po.project_id,
                po_reference=po_num,
                details_json=json.dumps({'commitment_id': commitment.id, 'encumbrance': True}),
            )
            db.session.add(ap_doc)
            db.session.flush()
            link = AcctPostLink(
                ledger_id=ledger.id, source_type=event_type, source_key=idem,
                journal_batch_id=batch.id, ap_document_id=ap_doc.id, purchase_order_id=po.id,
            )
        else:
            link = AcctPostLink(
                ledger_id=ledger.id, source_type=event_type, source_key=idem,
                purchase_order_id=po.id,
            )
            batch = None
            ap_doc = None
        db.session.add(link)
        result.update({
            'posted': True,
            'purchase_order_id': po.id,
            'ap_document_id': ap_doc.id if amount > 0 else None,
            'journal_batch_id': batch.id if batch else None,
        })
    else:
        return {**result, 'skipped': 'unsupported_event'}

    db.session.flush()
    return result


def create_ap_payment(
    db,
    models,
    *,
    vendor_id,
    amount,
    applications,
    payment_method='Check',
    bank_account_id=None,
    user_id=None,
):
    """Pay vendor invoices: Dr AP, Cr Cash; update invoice paid amounts."""
    opts = load_accounting_options()
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctAPDocument = models['AcctAPDocument']
    AcctAPPayment = models['AcctAPPayment']
    AcctAPPaymentApply = models['AcctAPPaymentApply']
    AcctBankAccount = models['AcctBankAccount']
    AcctBankTransaction = models['AcctBankTransaction']

    ledger = get_or_create_default_ledger(db, AcctLedger)
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError('amount required')

    pay_num = f'AP-PAY-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
    payment = AcctAPPayment(
        ledger_id=ledger.id,
        payment_number=pay_num,
        vendor_id=int(vendor_id),
        payment_date=date.today(),
        amount=amount,
        payment_method=payment_method,
        bank_account_id=bank_account_id,
        status='Posted',
    )
    db.session.add(payment)
    db.session.flush()

    applied = 0.0
    for app in applications or []:
        doc_id = int(app['ap_document_id'])
        app_amt = round(float(app.get('amount') or 0), 2)
        if app_amt <= 0:
            continue
        doc = AcctAPDocument.query.get(doc_id)
        if not doc:
            continue
        doc.amount_paid = round(float(doc.amount_paid or 0) + app_amt, 2)
        if doc.amount_paid >= float(doc.amount or 0) - 0.01:
            doc.status = 'Paid'
        else:
            doc.status = 'Partial'
        db.session.add(AcctAPPaymentApply(payment_id=payment.id, ap_document_id=doc_id, amount=app_amt))
        applied += app_amt

    ap_acct = _account_by_number(AcctGLAccount, ledger.id, opts['ap_account'])
    cash_acct = _account_by_number(AcctGLAccount, ledger.id, opts['cash_account'])
    batch = _create_posted_batch(
        db, models, ledger_id=ledger.id, source='AP-PAY',
        description=f'AP Payment {pay_num}',
        user_id=user_id,
        lines=[
            {'account_id': ap_acct.id, 'debit': amount, 'credit': 0},
            {'account_id': cash_acct.id, 'debit': 0, 'credit': amount},
        ],
    )
    payment.journal_batch_id = batch.id

    if bank_account_id:
        bank = AcctBankAccount.query.get(int(bank_account_id))
        if bank:
            bt = AcctBankTransaction(
                bank_account_id=bank.id,
                transaction_date=date.today(),
                description=f'AP Payment {pay_num}',
                amount=-amount,
                transaction_type='Payment',
                reconciled=False,
                matched_payment_id=payment.id,
                reference=pay_num,
            )
            db.session.add(bt)

    db.session.flush()
    return {'payment': payment, 'journal_batch_id': batch.id, 'applied': applied}


def create_ar_receipt(
    db,
    models,
    *,
    customer_id,
    amount,
    applications,
    payment_method='ACH',
    bank_account_id=None,
    user_id=None,
):
    opts = load_accounting_options()
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctARDocument = models['AcctARDocument']
    AcctARReceipt = models['AcctARReceipt']
    AcctARReceiptApply = models['AcctARReceiptApply']
    AcctBankAccount = models['AcctBankAccount']
    AcctBankTransaction = models['AcctBankTransaction']

    ledger = get_or_create_default_ledger(db, AcctLedger)
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError('amount required')

    rcpt_num = f'AR-RCPT-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
    receipt = AcctARReceipt(
        ledger_id=ledger.id,
        receipt_number=rcpt_num,
        customer_id=int(customer_id),
        receipt_date=date.today(),
        amount=amount,
        payment_method=payment_method,
        bank_account_id=bank_account_id,
        status='Posted',
    )
    db.session.add(receipt)
    db.session.flush()

    for app in applications or []:
        doc_id = int(app['ar_document_id'])
        app_amt = round(float(app.get('amount') or 0), 2)
        if app_amt <= 0:
            continue
        doc = AcctARDocument.query.get(doc_id)
        if not doc:
            continue
        doc.amount_paid = round(float(doc.amount_paid or 0) + app_amt, 2)
        if doc.amount_paid >= float(doc.amount or 0) - 0.01:
            doc.status = 'Paid'
        else:
            doc.status = 'Partial'
        db.session.add(AcctARReceiptApply(receipt_id=receipt.id, ar_document_id=doc_id, amount=app_amt))

    cash_acct = _account_by_number(AcctGLAccount, ledger.id, opts['cash_account'])
    ar_acct = _account_by_number(AcctGLAccount, ledger.id, opts['ar_account'])
    batch = _create_posted_batch(
        db, models, ledger_id=ledger.id, source='AR-RCPT',
        description=f'AR Receipt {rcpt_num}',
        user_id=user_id,
        lines=[
            {'account_id': cash_acct.id, 'debit': amount, 'credit': 0},
            {'account_id': ar_acct.id, 'debit': 0, 'credit': amount},
        ],
    )
    receipt.journal_batch_id = batch.id

    if bank_account_id:
        bank = AcctBankAccount.query.get(int(bank_account_id))
        if bank:
            db.session.add(AcctBankTransaction(
                bank_account_id=bank.id,
                transaction_date=date.today(),
                description=f'AR Receipt {rcpt_num}',
                amount=amount,
                transaction_type='Receipt',
                reconciled=False,
                matched_receipt_id=receipt.id,
                reference=rcpt_num,
            ))

    db.session.flush()
    return {'receipt': receipt, 'journal_batch_id': batch.id}


def reconcile_bank_transactions(db, models, bank_account_id, transaction_ids, *, user_id=None):
    AcctBankTransaction = models['AcctBankTransaction']
    AcctBankAccount = models['AcctBankAccount']
    bank = AcctBankAccount.query.get_or_404(int(bank_account_id))
    ids = [int(x) for x in (transaction_ids or [])]
    updated = 0
    for tid in ids:
        tx = AcctBankTransaction.query.filter_by(id=tid, bank_account_id=bank.id).first()
        if tx and not tx.reconciled:
            tx.reconciled = True
            updated += 1
    bank.last_reconciled_date = date.today()
    db.session.flush()
    return {'reconciled_count': updated, 'bank_account_id': bank.id}


def run_payroll_post(db, models, payroll_run_id, *, user_id=None):
    opts = load_accounting_options()
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    run = AcctPayrollRun.query.get_or_404(int(payroll_run_id))
    if run.status == 'Posted':
        raise ValueError('Payroll run already posted')

    lines = AcctPayrollRunLine.query.filter_by(run_id=run.id).all()
    if lines:
        from accounting_payroll import recalculate_run
        recalculate_run(db, models, run.id)

    gross = round(float(run.total_gross or 0), 2)
    net = round(float(run.total_net or 0), 2)
    taxes = round(float(getattr(run, 'total_taxes', 0) or 0), 2)
    deductions = round(float(getattr(run, 'total_deductions', 0) or 0), 2)
    employer = round(float(getattr(run, 'total_employer_taxes', 0) or 0), 2)

    if gross <= 0:
        raise ValueError('Payroll run has no gross wages — add employees and calculate first')

    ledger = get_or_create_default_ledger(db, AcctLedger)
    labor = _account_by_number(AcctGLAccount, ledger.id, opts['labor_expense'])
    liability = _account_by_number(AcctGLAccount, ledger.id, opts['payroll_liability'])
    cash = _account_by_number(AcctGLAccount, ledger.id, opts['cash_account'])

    je_lines = []
    if lines:
        by_project: dict[int | None, float] = {}
        for ln in lines:
            pid = ln.project_id
            by_project[pid] = by_project.get(pid, 0) + float(ln.gross_pay or 0)
        for pid, amt in by_project.items():
            if amt <= 0:
                continue
            je_lines.append({
                'account_id': labor.id,
                'debit': round(amt, 2),
                'credit': 0,
                'project_id': pid,
                'description': f'Payroll labor PR {run.run_number}',
            })
    else:
        je_lines.append({'account_id': labor.id, 'debit': gross, 'credit': 0})

    if employer > 0:
        je_lines.append({
            'account_id': labor.id,
            'debit': employer,
            'credit': 0,
            'description': 'Employer FICA/Medicare',
        })

    liability_credit = round(taxes + deductions + employer, 2)
    if liability_credit > 0:
        je_lines.append({
            'account_id': liability.id,
            'debit': 0,
            'credit': liability_credit,
            'description': 'Payroll taxes, deductions & employer share',
        })
    if net > 0:
        je_lines.append({'account_id': cash.id, 'debit': 0, 'credit': net, 'description': 'Net pay disbursement'})

    batch = _create_posted_batch(
        db, models, ledger_id=ledger.id, source='PR',
        description=f'Payroll {run.run_number}',
        user_id=user_id,
        lines=je_lines,
    )
    run.status = 'Posted'
    run.journal_batch_id = batch.id
    db.session.flush()
    return {
        'journal_batch_id': batch.id,
        'payroll_run_id': run.id,
        'lines_posted': len(lines),
        'job_cost_projects': len({ln.project_id for ln in lines if ln.project_id}),
    }


def run_depreciation(db, models, *, user_id=None):
    opts = load_accounting_options()
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctFixedAsset = models['AcctFixedAsset']
    AcctDepreciationRun = models['AcctDepreciationRun']

    ledger = get_or_create_default_ledger(db, AcctLedger)
    _ensure_supplemental_accounts(db, AcctLedger, AcctGLAccount, ledger.id)
    dep_exp = _account_by_number(AcctGLAccount, ledger.id, opts['depreciation_expense'])
    accum = _account_by_number(AcctGLAccount, ledger.id, opts['accum_dep_account'])

    total = 0.0
    lines_meta = []
    assets = AcctFixedAsset.query.filter_by(ledger_id=ledger.id, status='Active').all()
    for asset in assets:
        cost = float(asset.acquisition_cost or 0)
        accum_amt = float(asset.accumulated_depreciation or 0)
        salvage = float(getattr(asset, 'salvage_value', 0) or 0)
        book = cost - accum_amt
        months = int(asset.useful_life_months or 60) or 60
        depreciable = max(cost - salvage, 0)
        monthly = round(depreciable / months, 2) if months else 0
        if monthly <= 0 or book <= 0:
            continue
        dep = min(monthly, book)
        asset.accumulated_depreciation = round(accum_amt + dep, 2)
        if asset.accumulated_depreciation >= cost - 0.01:
            asset.status = 'Fully Depreciated'
        total += dep
        lines_meta.append({'asset_id': asset.id, 'amount': dep})

    total = round(total, 2)
    if total <= 0:
        raise ValueError('No depreciable amount for active assets')

    run_num = f'DEP-{datetime.utcnow().strftime("%Y%m")}'
    batch = _create_posted_batch(
        db, models, ledger_id=ledger.id, source='FA',
        description=f'Depreciation run {run_num}',
        user_id=user_id,
        lines=[
            {'account_id': dep_exp.id, 'debit': total, 'credit': 0},
            {'account_id': accum.id, 'debit': 0, 'credit': total},
        ],
    )
    dep_run = AcctDepreciationRun(
        ledger_id=ledger.id,
        run_number=run_num,
        period_date=date.today(),
        status='Posted',
        total_amount=total,
        journal_batch_id=batch.id,
    )
    db.session.add(dep_run)
    db.session.flush()
    return {'depreciation_run_id': dep_run.id, 'journal_batch_id': batch.id, 'total': total, 'assets': lines_meta}
