"""Built-in accounting suite API routes."""
from __future__ import annotations


def register_accounting_routes(app, deps):
    db = deps['db']
    request = deps['request']
    jsonify = deps['jsonify']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps['get_current_project_id']
    Project = deps['Project']
    SageSyncEvent = deps.get('SageSyncEvent')

    models = {k: deps[k] for k in deps if k.startswith('Acct')}

    def _ledger_id():
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
        ledger = get_or_create_default_ledger(db, models['AcctLedger'])
        seed_chart_of_accounts(db, models['AcctLedger'], models['AcctGLAccount'], ledger)
        return ledger.id

    @app.route('/accounting')
    @login_required
    def accounting_page():
        from flask import render_template
        active = deps.get('get_active_project')()
        return render_template('accounting.html', active_project=active, page_module='accounting')

    @app.route('/api/accounting/catalog', methods=['GET'])
    @login_required
    def api_accounting_catalog():
        from accounting_module_service import get_catalog
        return jsonify(get_catalog())

    @app.route('/api/accounting/dashboard', methods=['GET'])
    @login_required
    def api_accounting_dashboard():
        from accounting_module_service import build_company_dashboard
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        return jsonify(build_company_dashboard(
            db, models, project_id=project_id, Project=Project, SageSyncEvent=SageSyncEvent,
        ))

    @app.route('/api/accounting/gl/accounts', methods=['GET', 'POST'])
    @login_required
    def api_acct_gl_accounts():
        from accounting_persistence import serialize_account
        AcctGLAccount = models['AcctGLAccount']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctGLAccount.query.filter_by(ledger_id=lid).order_by(AcctGLAccount.account_number).all()
            return jsonify({'accounts': [serialize_account(a) for a in rows]})
        body = request.get_json(silent=True) or {}
        acct = AcctGLAccount(
            ledger_id=lid,
            account_number=(body.get('account_number') or '').strip(),
            description=(body.get('description') or '').strip(),
            account_type=(body.get('account_type') or 'expense').strip(),
            normal_balance=body.get('normal_balance') or 'debit',
            status='Active',
            is_posting=body.get('is_posting', True),
        )
        if not acct.account_number or not acct.description:
            return jsonify({'error': 'account_number and description required'}), 400
        db.session.add(acct)
        db.session.commit()
        return jsonify({'ok': True, 'account': serialize_account(acct)})

    @app.route('/api/accounting/gl/batches', methods=['GET', 'POST'])
    @login_required
    def api_acct_gl_batches():
        from accounting_persistence import next_batch_number, serialize_batch, serialize_account
        from datetime import date as date_cls

        AcctJournalBatch = models['AcctJournalBatch']
        AcctJournalLine = models['AcctJournalLine']
        AcctGLAccount = models['AcctGLAccount']
        lid = _ledger_id()
        if request.method == 'GET':
            batches = AcctJournalBatch.query.filter_by(ledger_id=lid).order_by(
                AcctJournalBatch.created_at.desc()
            ).limit(100).all()
            out = []
            for b in batches:
                lines = AcctJournalLine.query.filter_by(batch_id=b.id).order_by(AcctJournalLine.line_number).all()
                line_data = []
                for ln in lines:
                    acct = AcctGLAccount.query.get(ln.account_id)
                    line_data.append({
                        'id': ln.id,
                        'line_number': ln.line_number,
                        'account_id': ln.account_id,
                        'account_number': acct.account_number if acct else '',
                        'description': ln.description,
                        'debit': ln.debit,
                        'credit': ln.credit,
                        'project_id': ln.project_id,
                    })
                out.append(serialize_batch(b, line_data))
            return jsonify({'batches': out})
        body = request.get_json(silent=True) or {}
        batch = AcctJournalBatch(
            ledger_id=lid,
            batch_number=body.get('batch_number') or next_batch_number(AcctJournalBatch, lid),
            source=body.get('source') or 'GL',
            description=body.get('description') or '',
            batch_date=date_cls.fromisoformat(body['batch_date']) if body.get('batch_date') else date_cls.today(),
            status='Open',
            created_by_id=getattr(current_user, 'id', None),
        )
        db.session.add(batch)
        db.session.flush()
        for i, ln in enumerate(body.get('lines') or [], start=1):
            db.session.add(AcctJournalLine(
                batch_id=batch.id,
                line_number=i,
                account_id=int(ln['account_id']),
                description=ln.get('description') or '',
                debit=float(ln.get('debit') or 0),
                credit=float(ln.get('credit') or 0),
                project_id=ln.get('project_id'),
            ))
        db.session.commit()
        return jsonify({'ok': True, 'batch': serialize_batch(batch)})

    @app.route('/api/accounting/gl/batches/<int:batch_id>/post', methods=['POST'])
    @login_required
    def api_acct_post_batch(batch_id):
        from accounting_persistence import post_journal_batch, serialize_batch
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        batch = models['AcctJournalBatch'].query.get_or_404(batch_id)
        try:
            post_journal_batch(db, batch, models['AcctJournalLine'])
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, 'batch': serialize_batch(batch)})

    @app.route('/api/accounting/ap/vendors', methods=['GET', 'POST'])
    @login_required
    def api_acct_ap_vendors():
        from accounting_persistence import serialize_vendor
        AcctVendor = models['AcctVendor']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctVendor.query.filter_by(ledger_id=lid).order_by(AcctVendor.code).all()
            return jsonify({'vendors': [serialize_vendor(v) for v in rows]})
        body = request.get_json(silent=True) or {}
        v = AcctVendor(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            name=(body.get('name') or '').strip(),
            terms=body.get('terms') or 'Net 30',
            tax_group=body.get('tax_group') or '',
            email=body.get('email') or '',
            phone=body.get('phone') or '',
        )
        if not v.code or not v.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(v)
        db.session.commit()
        return jsonify({'ok': True, 'vendor': serialize_vendor(v)})

    @app.route('/api/accounting/ap/invoices', methods=['GET', 'POST'])
    @login_required
    def api_acct_ap_invoices():
        from accounting_persistence import serialize_ap_doc
        from datetime import date as date_cls
        AcctAPDocument = models['AcctAPDocument']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctAPDocument.query.filter_by(ledger_id=lid).order_by(AcctAPDocument.created_at.desc()).limit(200).all()
            return jsonify({'invoices': [serialize_ap_doc(d) for d in rows]})
        body = request.get_json(silent=True) or {}
        doc = AcctAPDocument(
            ledger_id=lid,
            vendor_id=int(body['vendor_id']),
            document_number=(body.get('document_number') or '').strip(),
            document_date=date_cls.fromisoformat(body['document_date']) if body.get('document_date') else date_cls.today(),
            due_date=date_cls.fromisoformat(body['due_date']) if body.get('due_date') else None,
            amount=float(body.get('amount') or 0),
            project_id=body.get('project_id'),
            status='Open',
        )
        if not doc.document_number:
            return jsonify({'error': 'document_number required'}), 400
        db.session.add(doc)
        db.session.commit()
        return jsonify({'ok': True, 'invoice': serialize_ap_doc(doc)})

    @app.route('/api/accounting/ar/customers', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_customers():
        from accounting_persistence import serialize_customer
        AcctCustomer = models['AcctCustomer']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctCustomer.query.filter_by(ledger_id=lid).order_by(AcctCustomer.code).all()
            return jsonify({'customers': [serialize_customer(c) for c in rows]})
        body = request.get_json(silent=True) or {}
        c = AcctCustomer(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            name=(body.get('name') or '').strip(),
            terms=body.get('terms') or 'Net 30',
            credit_limit=float(body.get('credit_limit') or 0),
        )
        if not c.code or not c.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(c)
        db.session.commit()
        return jsonify({'ok': True, 'customer': serialize_customer(c)})

    @app.route('/api/accounting/ar/invoices', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_invoices():
        from accounting_persistence import serialize_ar_doc
        from datetime import date as date_cls
        AcctARDocument = models['AcctARDocument']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctARDocument.query.filter_by(ledger_id=lid).order_by(AcctARDocument.created_at.desc()).limit(200).all()
            return jsonify({'invoices': [serialize_ar_doc(d) for d in rows]})
        body = request.get_json(silent=True) or {}
        doc = AcctARDocument(
            ledger_id=lid,
            customer_id=int(body['customer_id']),
            document_number=(body.get('document_number') or '').strip(),
            document_date=date_cls.fromisoformat(body['document_date']) if body.get('document_date') else date_cls.today(),
            due_date=date_cls.fromisoformat(body['due_date']) if body.get('due_date') else None,
            amount=float(body.get('amount') or 0),
            project_id=body.get('project_id'),
            status='Open',
        )
        if not doc.document_number:
            return jsonify({'error': 'document_number required'}), 400
        db.session.add(doc)
        db.session.commit()
        return jsonify({'ok': True, 'invoice': serialize_ar_doc(doc)})

    @app.route('/api/accounting/bank/accounts', methods=['GET', 'POST'])
    @login_required
    def api_acct_bank_accounts():
        AcctBankAccount = models['AcctBankAccount']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctBankAccount.query.filter_by(ledger_id=lid).all()
            return jsonify({'accounts': [{
                'id': a.id, 'code': a.code, 'name': a.name, 'currency': a.currency, 'status': a.status,
            } for a in rows]})
        body = request.get_json(silent=True) or {}
        a = AcctBankAccount(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            name=(body.get('name') or '').strip(),
            currency=body.get('currency') or 'USD',
        )
        if not a.code or not a.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(a)
        db.session.commit()
        return jsonify({'ok': True, 'account': {'id': a.id, 'code': a.code, 'name': a.name}})

    @app.route('/api/accounting/tax/groups', methods=['GET', 'POST'])
    @login_required
    def api_acct_tax_groups():
        AcctTaxGroup = models['AcctTaxGroup']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctTaxGroup.query.filter_by(ledger_id=lid).all()
            return jsonify({'groups': [{
                'id': g.id, 'code': g.code, 'description': g.description,
                'rate_percent': g.rate_percent, 'authority': g.authority,
            } for g in rows]})
        body = request.get_json(silent=True) or {}
        g = AcctTaxGroup(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            description=body.get('description') or '',
            rate_percent=float(body.get('rate_percent') or 0),
            authority=body.get('authority') or '',
        )
        if not g.code:
            return jsonify({'error': 'code required'}), 400
        db.session.add(g)
        db.session.commit()
        return jsonify({'ok': True, 'group': {'id': g.id, 'code': g.code}})

    @app.route('/api/accounting/inventory/items', methods=['GET', 'POST'])
    @login_required
    def api_acct_inventory():
        AcctInventoryItem = models['AcctInventoryItem']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctInventoryItem.query.filter_by(ledger_id=lid).limit(500).all()
            return jsonify({'items': [{
                'id': i.id, 'item_number': i.item_number, 'description': i.description,
                'qty_on_hand': i.qty_on_hand, 'unit_cost': i.unit_cost, 'status': i.status,
            } for i in rows]})
        body = request.get_json(silent=True) or {}
        i = AcctInventoryItem(
            ledger_id=lid,
            item_number=(body.get('item_number') or '').strip(),
            description=body.get('description') or '',
            qty_on_hand=float(body.get('qty_on_hand') or 0),
            unit_cost=float(body.get('unit_cost') or 0),
        )
        if not i.item_number:
            return jsonify({'error': 'item_number required'}), 400
        db.session.add(i)
        db.session.commit()
        return jsonify({'ok': True, 'item': {'id': i.id, 'item_number': i.item_number}})

    @app.route('/api/accounting/inventory/items/<int:item_id>/adjust', methods=['POST'])
    @login_required
    def api_acct_inventory_adjust(item_id):
        """Receive (+) or issue (-) quantity on hand."""
        AcctInventoryItem = models['AcctInventoryItem']
        item = AcctInventoryItem.query.get_or_404(item_id)
        if item.ledger_id != _ledger_id():
            return jsonify({'error': 'Not found'}), 404
        body = request.get_json(silent=True) or {}
        delta = float(body.get('qty_delta') or 0)
        if delta == 0:
            return jsonify({'error': 'qty_delta required'}), 400
        item.qty_on_hand = float(item.qty_on_hand or 0) + delta
        if item.qty_on_hand < 0:
            db.session.rollback()
            return jsonify({'error': 'Insufficient quantity on hand'}), 400
        if body.get('unit_cost') is not None:
            item.unit_cost = float(body.get('unit_cost'))
        db.session.commit()
        return jsonify({'ok': True, 'item': {
            'id': item.id, 'qty_on_hand': item.qty_on_hand, 'unit_cost': item.unit_cost,
        }})

    @app.route('/api/accounting/po/orders', methods=['GET', 'POST'])
    @login_required
    def api_acct_po():
        from datetime import date as date_cls
        AcctPurchaseOrder = models['AcctPurchaseOrder']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPurchaseOrder.query.filter_by(ledger_id=lid).order_by(AcctPurchaseOrder.id.desc()).limit(200).all()
            return jsonify({'orders': [{
                'id': o.id, 'po_number': o.po_number, 'status': o.status,
                'vendor_id': o.vendor_id, 'total_amount': o.total_amount, 'project_id': o.project_id,
            } for o in rows]})
        body = request.get_json(silent=True) or {}
        o = AcctPurchaseOrder(
            ledger_id=lid,
            vendor_id=body.get('vendor_id'),
            po_number=(body.get('po_number') or '').strip(),
            order_date=date_cls.today(),
            total_amount=float(body.get('total_amount') or 0),
            project_id=body.get('project_id'),
            status='Open',
        )
        if not o.po_number:
            return jsonify({'error': 'po_number required'}), 400
        db.session.add(o)
        db.session.commit()
        return jsonify({'ok': True, 'order': {'id': o.id, 'po_number': o.po_number}})

    @app.route('/api/accounting/oe/orders', methods=['GET', 'POST'])
    @login_required
    def api_acct_oe():
        from datetime import date as date_cls
        AcctSalesOrder = models['AcctSalesOrder']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctSalesOrder.query.filter_by(ledger_id=lid).order_by(AcctSalesOrder.id.desc()).limit(200).all()
            return jsonify({'orders': [{
                'id': o.id, 'order_number': o.order_number, 'status': o.status,
                'customer_id': o.customer_id, 'total_amount': o.total_amount,
            } for o in rows]})
        body = request.get_json(silent=True) or {}
        o = AcctSalesOrder(
            ledger_id=lid,
            customer_id=body.get('customer_id'),
            order_number=(body.get('order_number') or '').strip(),
            order_date=date_cls.today(),
            total_amount=float(body.get('total_amount') or 0),
            project_id=body.get('project_id'),
            status='Open',
        )
        if not o.order_number:
            return jsonify({'error': 'order_number required'}), 400
        db.session.add(o)
        db.session.commit()
        return jsonify({'ok': True, 'order': {'id': o.id, 'order_number': o.order_number}})

    @app.route('/api/accounting/assets', methods=['GET', 'POST'])
    @login_required
    def api_acct_assets():
        from datetime import date as date_cls
        AcctFixedAsset = models['AcctFixedAsset']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctFixedAsset.query.filter_by(ledger_id=lid).all()
            return jsonify({'assets': [{
                'id': a.id, 'asset_number': a.asset_number, 'description': a.description,
                'acquisition_cost': a.acquisition_cost, 'book': a.book, 'status': a.status,
            } for a in rows]})
        body = request.get_json(silent=True) or {}
        a = AcctFixedAsset(
            ledger_id=lid,
            asset_number=(body.get('asset_number') or '').strip(),
            description=body.get('description') or '',
            acquisition_date=date_cls.today(),
            acquisition_cost=float(body.get('acquisition_cost') or 0),
        )
        if not a.asset_number:
            return jsonify({'error': 'asset_number required'}), 400
        db.session.add(a)
        db.session.commit()
        return jsonify({'ok': True, 'asset': {'id': a.id, 'asset_number': a.asset_number}})

    @app.route('/api/accounting/reports/trial-balance', methods=['GET'])
    @login_required
    def api_acct_trial_balance():
        from accounting_persistence import trial_balance
        lid = _ledger_id()
        rows = trial_balance(
            db, models['AcctGLAccount'], models['AcctJournalLine'],
            models['AcctJournalBatch'], lid,
        )
        return jsonify({'rows': rows})

    @app.route('/api/accounting/reports/ap-aging', methods=['GET'])
    @login_required
    def api_acct_ap_aging():
        from accounting_persistence import ap_aging
        return jsonify(ap_aging(models['AcctAPDocument'], _ledger_id()))

    @app.route('/api/accounting/reports/ar-aging', methods=['GET'])
    @login_required
    def api_acct_ar_aging():
        from accounting_persistence import ar_aging
        return jsonify(ar_aging(models['AcctARDocument'], _ledger_id()))

    @app.route('/api/accounting/integrations/sage', methods=['GET'])
    @login_required
    def api_acct_sage_integration():
        from accounting_erp_sync import sage_integration_status
        return jsonify(sage_integration_status())

    @app.route('/api/accounting/integrations/sage/erp-queue', methods=['GET'])
    @login_required
    def api_acct_sage_erp_queue():
        if not SageSyncEvent:
            return jsonify({'events': []})
        from sage_service import sage_event_to_dict
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        limit = min(request.args.get('limit', 100, type=int), 300)
        events = SageSyncEvent.query.filter_by(project_id=int(project_id)).order_by(
            SageSyncEvent.created_at.desc()
        ).limit(limit).all()
        return jsonify({'events': [sage_event_to_dict(e) for e in events]})

    @app.route('/api/accounting/ap/payments', methods=['GET', 'POST'])
    @login_required
    def api_acct_ap_payments():
        from financial_security import require_accounting_role
        from accounting_posting import create_ap_payment
        AcctAPPayment = models['AcctAPPayment']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctAPPayment.query.filter_by(ledger_id=lid).order_by(AcctAPPayment.id.desc()).limit(100).all()
            return jsonify({'payments': [{
                'id': p.id, 'payment_number': p.payment_number, 'vendor_id': p.vendor_id,
                'amount': p.amount, 'payment_date': p.payment_date.isoformat() if p.payment_date else None,
                'payment_method': p.payment_method,
            } for p in rows]})
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = create_ap_payment(
                db, models,
                vendor_id=body['vendor_id'],
                amount=body.get('amount'),
                applications=body.get('applications') or [],
                payment_method=body.get('payment_method') or 'Check',
                bank_account_id=body.get('bank_account_id'),
                user_id=current_user.id,
            )
            db.session.commit()
            p = out['payment']
            return jsonify({'ok': True, 'payment_id': p.id, 'journal_batch_id': out['journal_batch_id']})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/receipts', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_receipts():
        from financial_security import require_accounting_role
        from accounting_posting import create_ar_receipt
        AcctARReceipt = models['AcctARReceipt']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctARReceipt.query.filter_by(ledger_id=lid).order_by(AcctARReceipt.id.desc()).limit(100).all()
            return jsonify({'receipts': [{
                'id': r.id, 'receipt_number': r.receipt_number, 'customer_id': r.customer_id,
                'amount': r.amount, 'receipt_date': r.receipt_date.isoformat() if r.receipt_date else None,
            } for r in rows]})
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = create_ar_receipt(
                db, models,
                customer_id=body['customer_id'],
                amount=body.get('amount'),
                applications=body.get('applications') or [],
                payment_method=body.get('payment_method') or 'ACH',
                bank_account_id=body.get('bank_account_id'),
                user_id=current_user.id,
            )
            db.session.commit()
            r = out['receipt']
            return jsonify({'ok': True, 'receipt_id': r.id, 'journal_batch_id': out['journal_batch_id']})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/bank/transactions', methods=['GET'])
    @login_required
    def api_acct_bank_transactions():
        bank_id = request.args.get('bank_account_id', type=int)
        AcctBankTransaction = models['AcctBankTransaction']
        q = AcctBankTransaction.query
        if bank_id:
            q = q.filter_by(bank_account_id=bank_id)
        rows = q.order_by(AcctBankTransaction.id.desc()).limit(200).all()
        return jsonify({'transactions': [{
            'id': t.id, 'bank_account_id': t.bank_account_id,
            'transaction_date': t.transaction_date.isoformat() if t.transaction_date else None,
            'description': t.description, 'amount': t.amount,
            'reconciled': t.reconciled, 'reference': t.reference,
        } for t in rows]})

    @app.route('/api/accounting/bank/reconcile', methods=['POST'])
    @login_required
    def api_acct_bank_reconcile():
        from financial_security import require_accounting_role
        from accounting_posting import reconcile_bank_transactions
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = reconcile_bank_transactions(
                db, models,
                body['bank_account_id'],
                body.get('transaction_ids') or [],
                user_id=current_user.id,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payroll/runs', methods=['GET', 'POST'])
    @login_required
    def api_acct_payroll_runs():
        from datetime import date as date_cls
        AcctPayrollRun = models['AcctPayrollRun']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPayrollRun.query.filter_by(ledger_id=lid).order_by(AcctPayrollRun.id.desc()).limit(50).all()
            return jsonify({'runs': [{
                'id': r.id, 'run_number': r.run_number, 'status': r.status,
                'total_gross': r.total_gross, 'total_net': r.total_net,
                'total_taxes': getattr(r, 'total_taxes', 0),
            } for r in rows]})
        body = request.get_json(silent=True) or {}
        run = AcctPayrollRun(
            ledger_id=lid,
            run_number=(body.get('run_number') or f'PR-{date_cls.today().isoformat()}')[:30],
            pay_date=date_cls.today(),
            total_gross=float(body.get('total_gross') or 0),
            total_net=float(body.get('total_net') or 0),
            total_taxes=float(body.get('total_taxes') or 0),
            status='Open',
        )
        db.session.add(run)
        db.session.commit()
        return jsonify({'ok': True, 'run_id': run.id})

    @app.route('/api/accounting/payroll/runs/<int:run_id>/post', methods=['POST'])
    @login_required
    def api_acct_payroll_post(run_id):
        from financial_security import require_accounting_role
        from accounting_posting import run_payroll_post
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            out = run_payroll_post(db, models, run_id, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/assets/depreciate', methods=['POST'])
    @login_required
    def api_acct_depreciate():
        from financial_security import require_accounting_role
        from accounting_posting import run_depreciation
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            out = run_depreciation(db, models, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/settings', methods=['GET'])
    @login_required
    def api_acct_settings_get():
        from program_settings_persistence import load_accounting_defaults
        return jsonify(load_accounting_defaults())

    @app.route('/api/accounting/settings', methods=['POST'])
    @login_required
    def api_acct_settings_post():
        from program_settings_persistence import save_accounting_defaults
        try:
            from app import admin_required
        except ImportError:
            admin_required = lambda f: f
        # Enforced via financial_security or admin check
        if getattr(current_user, 'role', '') not in ('Admin', 'Developer'):
            return jsonify({'error': 'Admin required'}), 403
        body = request.get_json(silent=True) or {}
        saved = save_accounting_defaults(body)
        return jsonify({'ok': True, 'accounting': saved})

    @app.route('/api/accounting/reports/catalog', methods=['GET'])
    @login_required
    def api_acct_report_catalog():
        from accounting_reports import report_catalog
        return jsonify(report_catalog())

    @app.route('/api/accounting/reports/run', methods=['GET', 'POST'])
    @login_required
    def api_acct_report_run():
        from accounting_reports import report_to_csv, run_report
        from flask import Response
        body = request.get_json(silent=True) if request.method == 'POST' else {}
        report_type = (body or {}).get('report_type') or request.args.get('type') or request.args.get('report_type')
        if not report_type:
            return jsonify({'error': 'report_type required'}), 400
        filters = (body or {}).get('filters') or {}
        if request.args.get('project_id'):
            filters['project_id'] = request.args.get('project_id', type=int)
        if request.args.get('start_date'):
            filters['start_date'] = request.args.get('start_date')
        if request.args.get('end_date'):
            filters['end_date'] = request.args.get('end_date')
        lid = _ledger_id()
        try:
            data = run_report(db, models, lid, report_type, filters=filters, Project=Project)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        fmt = (request.args.get('format') or (body or {}).get('format') or '').lower()
        if fmt == 'csv':
            csv_text = report_to_csv(data)
            return Response(
                csv_text,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=casepm-{report_type}.csv'},
            )
        return jsonify(data)

    @app.route('/api/accounting/reports/custom', methods=['GET', 'POST'])
    @login_required
    def api_acct_custom_reports():
        from accounting_reports import serialize_report_definition
        AcctReportDefinition = models['AcctReportDefinition']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctReportDefinition.query.filter_by(ledger_id=lid).order_by(
                AcctReportDefinition.is_favorite.desc(),
                AcctReportDefinition.name.asc(),
            ).all()
            return jsonify({'reports': [serialize_report_definition(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        name = (body.get('name') or '').strip()
        rtype = (body.get('report_type') or '').strip()
        if not name or not rtype:
            return jsonify({'error': 'name and report_type required'}), 400
        import json as json_mod
        row = AcctReportDefinition(
            ledger_id=lid,
            name=name[:120],
            report_type=rtype,
            filters_json=json_mod.dumps(body.get('filters') or {}),
            columns_json=json_mod.dumps(body.get('columns') or {}),
            is_favorite=bool(body.get('is_favorite')),
            created_by_id=current_user.id,
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'report': serialize_report_definition(row)})

    @app.route('/api/accounting/reports/custom/<int:report_id>', methods=['DELETE'])
    @login_required
    def api_acct_custom_report_delete(report_id):
        AcctReportDefinition = models['AcctReportDefinition']
        row = AcctReportDefinition.query.get_or_404(report_id)
        db.session.delete(row)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/accounting/reports/custom/<int:report_id>/run', methods=['POST', 'GET'])
    @login_required
    def api_acct_custom_report_run(report_id):
        from accounting_reports import report_to_csv, run_report, serialize_report_definition
        from flask import Response
        import json as json_mod
        AcctReportDefinition = models['AcctReportDefinition']
        row = AcctReportDefinition.query.get_or_404(report_id)
        filters = json_mod.loads(row.filters_json) if row.filters_json else {}
        data = run_report(db, models, row.ledger_id, row.report_type, filters=filters, Project=Project)
        data['custom_report'] = serialize_report_definition(row)
        fmt = request.args.get('format', '').lower()
        if fmt == 'csv':
            return Response(
                report_to_csv(data),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=casepm-report-{report_id}.csv'},
            )
        return jsonify(data)
