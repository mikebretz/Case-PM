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
