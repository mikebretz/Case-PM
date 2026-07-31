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
    PayAppProjectState = deps.get('PayAppProjectState')

    models = {k: deps[k] for k in deps if k.startswith('Acct')}
    from datetime import date

    def _ensure_schema():
        from accounting_persistence import ensure_accounting_schema
        try:
            ensure_accounting_schema(db, models)
        except Exception:
            db.session.rollback()

    def _ledger_id():
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
        _ensure_schema()
        ledger = get_or_create_default_ledger(db, models['AcctLedger'])
        seed_chart_of_accounts(db, models['AcctLedger'], models['AcctGLAccount'], ledger)
        return ledger.id

    @app.before_request
    def _accounting_screen_guard():
        path = request.path or ''
        if not path.startswith('/api/accounting/'):
            return None
        if request.method == 'OPTIONS':
            return None
        exempt = (
            '/catalog', '/dashboard', '/platform/i18n', '/platform/screen-permissions',
            '/payments/pay-now/',
        )
        if any(x in path for x in exempt):
            return None
        try:
            from accounting_enforcement import screen_access_for_request
            lid = _ledger_id()
            ledger = models['AcctLedger'].query.get(lid)
            screen_access_for_request(ledger, path, request.method)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        except Exception:
            return None
        return None

    @app.route('/accounting')
    @login_required
    def accounting_page():
        from flask import render_template
        _ensure_schema()
        active = deps.get('get_active_project')()
        return render_template('accounting.html', active_project=active, page_module='accounting')

    @app.route('/api/accounting/catalog', methods=['GET'])
    @login_required
    def api_accounting_catalog():
        from accounting_module_service import get_catalog
        return jsonify(get_catalog(db, models))

    @app.route('/api/accounting/dashboard', methods=['GET'])
    @login_required
    def api_accounting_dashboard():
        from accounting_module_service import build_company_dashboard
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        return jsonify(build_company_dashboard(
            db, models, project_id=project_id, Project=Project, SageSyncEvent=SageSyncEvent,
        ))

    @app.route('/api/accounting/dashboard/kpi-config', methods=['GET', 'PATCH'])
    @login_required
    def api_accounting_dashboard_kpi_config():
        from accounting_platform_depth import dashboard_kpi_config, update_dashboard_kpi_config
        ledger = models['AcctLedger'].query.get(_ledger_id())
        if request.method == 'GET':
            return jsonify(dashboard_kpi_config(ledger))
        cfg = update_dashboard_kpi_config(ledger, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'ok': True, **cfg})

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
        from accounting_gl_extended import validate_account_number_segments
        from accounting_gl_service import ledger_gl_options
        ledger = models['AcctLedger'].query.get(lid)
        opts = ledger_gl_options(ledger)
        try:
            segs = validate_account_number_segments(acct.account_number, opts['segment_count'])
            import json as json_mod
            acct.segments_json = json_mod.dumps(segs)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
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
            ledger = models['AcctLedger'].query.get(batch.ledger_id)
            from accounting_enforcement import posting_context
            post_journal_batch(
                db, batch, models['AcctJournalLine'], ledger=ledger,
                models=models, **posting_context(current_user),
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, 'batch': serialize_batch(batch)})

    @app.route('/api/accounting/gl/accounts/<int:account_id>', methods=['PATCH'])
    @login_required
    def api_acct_gl_account_patch(account_id):
        from accounting_persistence import serialize_account
        from accounting_gl_service import patch_gl_account
        AcctGLAccount = models['AcctGLAccount']
        lid = _ledger_id()
        acct = AcctGLAccount.query.filter_by(id=account_id, ledger_id=lid).first_or_404()
        body = request.get_json(silent=True) or {}
        patch_gl_account(acct, body)
        db.session.commit()
        return jsonify({'ok': True, 'account': serialize_account(acct)})

    @app.route('/api/accounting/gl/accounts/<int:account_id>/register', methods=['GET'])
    @login_required
    def api_acct_gl_account_register(account_id):
        from accounting_gl_service import account_register
        lid = _ledger_id()
        try:
            data = account_register(db, models, lid, account_id)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        return jsonify(data)

    @app.route('/api/accounting/gl/batches/<int:batch_id>', methods=['GET', 'PATCH', 'DELETE'])
    @login_required
    def api_acct_gl_batch_detail(batch_id):
        from accounting_persistence import serialize_batch
        from accounting_gl_service import batch_lines_payload, update_open_batch
        AcctJournalBatch = models['AcctJournalBatch']
        AcctJournalLine = models['AcctJournalLine']
        AcctGLAccount = models['AcctGLAccount']
        AcctLedger = models['AcctLedger']
        lid = _ledger_id()
        batch = AcctJournalBatch.query.filter_by(id=batch_id, ledger_id=lid).first_or_404()
        if request.method == 'GET':
            lines = batch_lines_payload(AcctJournalLine, AcctGLAccount, batch.id)
            return jsonify({'batch': serialize_batch(batch, lines)})
        if request.method == 'DELETE':
            if batch.status != 'Open':
                return jsonify({'error': 'Only open batches can be deleted'}), 400
            AcctJournalLine.query.filter_by(batch_id=batch.id).delete()
            db.session.delete(batch)
            db.session.commit()
            return jsonify({'ok': True})
        body = request.get_json(silent=True) or {}
        try:
            update_open_batch(db, models, batch, body, AcctLedger)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        lines = batch_lines_payload(AcctJournalLine, AcctGLAccount, batch.id)
        return jsonify({'ok': True, 'batch': serialize_batch(batch, lines)})

    @app.route('/api/accounting/gl/options', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_gl_options():
        from accounting_gl_service import ledger_gl_options, update_ledger_gl_options
        AcctLedger = models['AcctLedger']
        lid = _ledger_id()
        ledger = AcctLedger.query.get(lid)
        if request.method == 'GET':
            return jsonify(ledger_gl_options(ledger))
        body = request.get_json(silent=True) or {}
        data = update_ledger_gl_options(ledger, body)
        db.session.commit()
        return jsonify({'ok': True, 'options': data})

    @app.route('/api/accounting/gl/segments/validate', methods=['POST'])
    @login_required
    def api_acct_gl_segments_validate():
        from accounting_gl_extended import segments_payload, validate_account_number_segments
        from accounting_gl_service import ledger_gl_options
        body = request.get_json(silent=True) or {}
        ledger = models['AcctLedger'].query.get(_ledger_id())
        opts = ledger_gl_options(ledger)
        segs = validate_account_number_segments(body.get('account_number', ''), opts['segment_count'])
        return jsonify({'ok': True, **segments_payload(body.get('account_number', ''), opts['segment_count'])})

    @app.route('/api/accounting/gl/budgets', methods=['GET', 'POST'])
    @login_required
    def api_acct_gl_budgets():
        from accounting_gl_extended import create_budget, serialize_budget
        AcctGLBudget = models['AcctGLBudget']
        AcctGLBudgetLine = models['AcctGLBudgetLine']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctGLBudget.query.filter_by(ledger_id=lid).order_by(AcctGLBudget.id.desc()).all()
            return jsonify({'budgets': [serialize_budget(b) for b in rows]})
        body = request.get_json(silent=True) or {}
        b = create_budget(db, models, lid, body)
        db.session.commit()
        return jsonify({'budget': serialize_budget(b)}), 201

    @app.route('/api/accounting/gl/budgets/<int:budget_id>/vs-actual', methods=['GET'])
    @login_required
    def api_acct_gl_budget_vs_actual(budget_id):
        from accounting_gl_extended import budget_vs_actual
        period = request.args.get('period_key')
        try:
            data = budget_vs_actual(db, models, _ledger_id(), budget_id, period_key=period)
            return jsonify(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/recurring-journals', methods=['GET', 'POST'])
    @login_required
    def api_acct_gl_recurring():
        from accounting_gl_extended import create_recurring_journal, run_recurring_journal, serialize_recurring
        AcctGLRecurringJournal = models['AcctGLRecurringJournal']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctGLRecurringJournal.query.filter_by(ledger_id=lid).order_by(AcctGLRecurringJournal.id.desc()).all()
            return jsonify({'recurring': [serialize_recurring(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        try:
            r = create_recurring_journal(db, models, lid, body)
            db.session.commit()
            return jsonify({'recurring': serialize_recurring(r)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/recurring-journals/<int:rec_id>/run', methods=['POST'])
    @login_required
    def api_acct_gl_recurring_run(rec_id):
        from accounting_gl_extended import run_recurring_journal
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        r = models['AcctGLRecurringJournal'].query.filter_by(id=rec_id, ledger_id=_ledger_id()).first_or_404()
        try:
            out = run_recurring_journal(db, models, r, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/allocations', methods=['GET', 'POST'])
    @login_required
    def api_acct_gl_allocations():
        from accounting_gl_extended import create_allocation_template, run_allocation, serialize_allocation
        AcctGLAllocationTemplate = models['AcctGLAllocationTemplate']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctGLAllocationTemplate.query.filter_by(ledger_id=lid).all()
            return jsonify({'templates': [serialize_allocation(t) for t in rows]})
        body = request.get_json(silent=True) or {}
        try:
            t = create_allocation_template(db, models, lid, body)
            db.session.commit()
            return jsonify({'template': serialize_allocation(t)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/allocations/<int:template_id>/run', methods=['POST'])
    @login_required
    def api_acct_gl_allocation_run(template_id):
        from accounting_gl_extended import run_allocation
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        t = models['AcctGLAllocationTemplate'].query.filter_by(id=template_id, ledger_id=_ledger_id()).first_or_404()
        body = request.get_json(silent=True) or {}
        try:
            out = run_allocation(db, models, t, body.get('amount'), batch_date=body.get('batch_date'), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/intercompany', methods=['GET', 'POST'])
    @login_required
    def api_acct_gl_intercompany():
        from accounting_gl_extended import create_intercompany_entry, post_intercompany_entry, serialize_intercompany
        AcctIntercompanyEntry = models['AcctIntercompanyEntry']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctIntercompanyEntry.query.filter_by(ledger_id=lid).order_by(AcctIntercompanyEntry.id.desc()).limit(50).all()
            return jsonify({'entries': [serialize_intercompany(e) for e in rows]})
        body = request.get_json(silent=True) or {}
        try:
            e = create_intercompany_entry(db, models, lid, body)
            db.session.commit()
            return jsonify({'entry': serialize_intercompany(e)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/intercompany/<int:entry_id>/post', methods=['POST'])
    @login_required
    def api_acct_gl_intercompany_post(entry_id):
        from accounting_gl_extended import post_intercompany_entry, serialize_intercompany
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        e = models['AcctIntercompanyEntry'].query.filter_by(id=entry_id, ledger_id=_ledger_id()).first_or_404()
        try:
            out = post_intercompany_entry(db, models, e, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out, 'entry': serialize_intercompany(e)})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/subledger-reconcile', methods=['GET'])
    @login_required
    def api_acct_gl_subledger_reconcile():
        from accounting_gl_extended import subledger_control_reconcile
        return jsonify(subledger_control_reconcile(db, models, _ledger_id()))

    @app.route('/api/accounting/gl/budgets/<int:budget_id>/grid', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_gl_budget_grid(budget_id):
        from accounting_gl_extended import budget_grid, update_budget_grid
        lid = _ledger_id()
        if request.method == 'GET':
            try:
                return jsonify(budget_grid(db, models, lid, budget_id))
            except ValueError as exc:
                return jsonify({'error': str(exc)}), 400
        try:
            data = update_budget_grid(db, models, lid, budget_id, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify(data)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/currency-rates', methods=['GET', 'POST'])
    @login_required
    def api_acct_currency_rates():
        from accounting_multicurrency import serialize_rate, upsert_currency_rate
        AcctCurrencyRate = models['AcctCurrencyRate']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctCurrencyRate.query.filter_by(ledger_id=lid).order_by(AcctCurrencyRate.rate_date.desc()).limit(120).all()
            return jsonify({'rates': [serialize_rate(r) for r in rows]})
        try:
            r = upsert_currency_rate(db, models, lid, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'rate': serialize_rate(r)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/revaluation', methods=['POST'])
    @login_required
    def api_acct_revaluation():
        from accounting_multicurrency import run_revaluation
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            out = run_revaluation(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/invoices/<int:invoice_id>/post-gl', methods=['POST'])
    @login_required
    def api_acct_ap_invoice_post_gl(invoice_id):
        from accounting_posting import post_ap_invoice_to_gl
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = post_ap_invoice_to_gl(
                db, models, invoice_id,
                expense_account_id=body.get('expense_account_id'),
                user_id=getattr(current_user, 'id', None),
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/ar/invoices/<int:invoice_id>/post-gl', methods=['POST'])
    @login_required
    def api_acct_ar_invoice_post_gl(invoice_id):
        from accounting_posting import post_ar_invoice_to_gl
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = post_ar_invoice_to_gl(
                db, models, invoice_id,
                revenue_account_id=body.get('revenue_account_id'),
                user_id=getattr(current_user, 'id', None),
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/ap/vendors/<int:vendor_id>', methods=['PATCH'])
    @login_required
    def api_acct_ap_vendor_patch(vendor_id):
        from accounting_core_gaps import log_field_changes
        from accounting_persistence import serialize_vendor
        AcctVendor = models['AcctVendor']
        lid = _ledger_id()
        v = AcctVendor.query.filter_by(id=vendor_id, ledger_id=lid).first_or_404()
        body = request.get_json(silent=True) or {}
        before = {f: getattr(v, f, None) for f in ('name', 'terms', 'tax_group', 'email', 'phone', 'status')}
        for field in ('name', 'terms', 'tax_group', 'email', 'phone', 'status'):
            if field in body:
                setattr(v, field, str(body[field])[:200] if body[field] is not None else '')
        log_field_changes(
            db, models, lid, user_id=current_user.id,
            entity_type='vendor', entity_id=v.id, before=before,
            after={f: getattr(v, f, None) for f in before},
        )
        db.session.commit()
        return jsonify({'ok': True, 'vendor': serialize_vendor(v)})

    @app.route('/api/accounting/ar/customers/<int:customer_id>', methods=['PATCH'])
    @login_required
    def api_acct_ar_customer_patch(customer_id):
        from accounting_core_gaps import log_field_changes
        from accounting_persistence import serialize_customer
        AcctCustomer = models['AcctCustomer']
        lid = _ledger_id()
        c = AcctCustomer.query.filter_by(id=customer_id, ledger_id=lid).first_or_404()
        body = request.get_json(silent=True) or {}
        before = {f: getattr(c, f, None) for f in ('name', 'terms', 'email', 'status', 'credit_limit')}
        for field in ('name', 'terms', 'email', 'status'):
            if field in body:
                setattr(c, field, str(body[field])[:200] if body[field] is not None else '')
        if 'credit_limit' in body:
            c.credit_limit = float(body['credit_limit'] or 0)
        after = {f: getattr(c, f, None) for f in before}
        log_field_changes(
            db, models, lid, user_id=current_user.id,
            entity_type='customer', entity_id=c.id, before=before, after=after,
        )
        db.session.commit()
        return jsonify({'ok': True, 'customer': serialize_customer(c)})

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
        from accounting_ap_extended import compute_ap_invoice_amounts
        AcctVendor = models['AcctVendor']
        vendor = AcctVendor.query.get(int(body['vendor_id']))
        withhold_pct = body.get('withhold_percent')
        if withhold_pct is None and vendor:
            withhold_pct = vendor.default_withhold_percent
        amounts = compute_ap_invoice_amounts(
            body.get('gross_amount') or body.get('amount') or 0,
            retainage_percent=body.get('retainage_percent', 0),
            withhold_percent=withhold_pct or 0,
        )
        doc = AcctAPDocument(
            ledger_id=lid,
            vendor_id=int(body['vendor_id']),
            document_number=(body.get('document_number') or '').strip(),
            document_date=date_cls.fromisoformat(body['document_date']) if body.get('document_date') else date_cls.today(),
            due_date=date_cls.fromisoformat(body['due_date']) if body.get('due_date') else None,
            amount=amounts['amount'],
            gross_amount=amounts['gross_amount'],
            retainage_amount=amounts['retainage_amount'],
            withhold_amount=amounts['withhold_amount'],
            purchase_order_id=body.get('purchase_order_id'),
            po_reference=(body.get('po_reference') or '')[:40] or None,
            project_id=body.get('project_id'),
            status='Open',
        )
        if not doc.document_number:
            return jsonify({'error': 'document_number required'}), 400
        db.session.add(doc)
        db.session.flush()
        if body.get('post_to_gl'):
            from accounting_posting import post_ap_invoice_to_gl
            from financial_security import require_accounting_role
            try:
                require_accounting_role(current_user)
                post_ap_invoice_to_gl(
                    db, models, doc.id,
                    expense_account_id=body.get('expense_account_id'),
                    user_id=getattr(current_user, 'id', None),
                )
            except (PermissionError, ValueError) as exc:
                db.session.rollback()
                return jsonify({'error': str(exc)}), 400
        db.session.commit()
        return jsonify({'ok': True, 'invoice': serialize_ap_doc(doc)})

    @app.route('/api/accounting/ap/vendor-groups', methods=['GET', 'POST'])
    @login_required
    def api_acct_ap_vendor_groups():
        from accounting_ap_extended import serialize_vendor_group
        AcctVendorGroup = models['AcctVendorGroup']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctVendorGroup.query.filter_by(ledger_id=lid).all()
            return jsonify({'groups': [serialize_vendor_group(g) for g in rows]})
        body = request.get_json(silent=True) or {}
        g = AcctVendorGroup(
            ledger_id=lid,
            code=(body.get('code') or '')[:20],
            name=(body.get('name') or '')[:120],
            terms=body.get('terms'),
        )
        if not g.code or not g.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(g)
        db.session.commit()
        return jsonify({'group': serialize_vendor_group(g)}), 201

    @app.route('/api/accounting/ap/vendors/<int:vendor_id>/tax-profile', methods=['PATCH'])
    @login_required
    def api_acct_ap_vendor_tax(vendor_id):
        from accounting_ap_extended import patch_vendor_extended, serialize_vendor_extended
        from accounting_enforcement import merge_optional_fields, optional_fields_from_entity
        v = models['AcctVendor'].query.filter_by(id=vendor_id, ledger_id=_ledger_id()).first_or_404()
        body = request.get_json(silent=True) or {}
        patch_vendor_extended(v, body)
        if 'optional_fields' in body:
            v.details_json = merge_optional_fields(v.details_json, 'vendor', body['optional_fields'], models, _ledger_id())
        db.session.commit()
        out = serialize_vendor_extended(v)
        out['optional_fields'] = optional_fields_from_entity(v)
        return jsonify({'vendor': out})

    @app.route('/api/accounting/ap/recurring-payables', methods=['GET', 'POST'])
    @login_required
    def api_acct_ap_recurring():
        from accounting_ap_extended import generate_recurring_ap_invoice, serialize_recurring_ap
        AcctAPRecurringPayable = models['AcctAPRecurringPayable']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctAPRecurringPayable.query.filter_by(ledger_id=lid).all()
            return jsonify({'recurring': [serialize_recurring_ap(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        from datetime import date as date_cls
        r = AcctAPRecurringPayable(
            ledger_id=lid,
            vendor_id=int(body['vendor_id']),
            description=body.get('description'),
            amount=float(body.get('amount') or 0),
            frequency=(body.get('frequency') or 'monthly')[:20],
            next_run_date=date_cls.fromisoformat(body['next_run_date']) if body.get('next_run_date') else date_cls.today(),
            is_active=True,
        )
        db.session.add(r)
        db.session.commit()
        return jsonify({'recurring': serialize_recurring_ap(r)}), 201

    @app.route('/api/accounting/ap/recurring-payables/<int:rec_id>/generate', methods=['POST'])
    @login_required
    def api_acct_ap_recurring_generate(rec_id):
        from accounting_ap_extended import generate_recurring_ap_invoice
        from accounting_persistence import serialize_ap_doc
        r = models['AcctAPRecurringPayable'].query.filter_by(id=rec_id, ledger_id=_ledger_id()).first_or_404()
        try:
            doc = generate_recurring_ap_invoice(db, models, r)
            db.session.commit()
            return jsonify({'invoice': serialize_ap_doc(doc)})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/invoices/<int:invoice_id>/three-way-match', methods=['GET'])
    @login_required
    def api_acct_ap_three_way(invoice_id):
        from accounting_ap_extended import three_way_match
        return jsonify(three_way_match(db, models, _ledger_id(), invoice_id))

    @app.route('/api/accounting/ap/reports/1099', methods=['GET'])
    @login_required
    def api_acct_ap_1099():
        from accounting_ap_extended import report_1099
        from datetime import date
        year = request.args.get('year', type=int) or date.today().year
        return jsonify(report_1099(db, models, _ledger_id(), year))

    @app.route('/api/accounting/ap/payments/<int:payment_id>/void', methods=['POST'])
    @login_required
    def api_acct_ap_void_payment(payment_id):
        from accounting_ap_extended import void_ap_payment
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        p = models['AcctAPPayment'].query.filter_by(id=payment_id, ledger_id=_ledger_id()).first_or_404()
        body = request.get_json(silent=True) or {}
        try:
            out = void_ap_payment(db, models, p, reason=body.get('reason', ''), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/payments/nacha', methods=['POST'])
    @login_required
    def api_acct_ap_nacha():
        from accounting_ap_extended import nacha_ach_file
        from flask import Response
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            content = nacha_ach_file(
                db, models, _ledger_id(),
                body.get('payment_ids') or [],
                company_name=body.get('company_name', 'CASE PM'),
                company_id=body.get('company_id', '1234567890'),
                dest_routing=body.get('dest_routing', '021000021'),
                dest_account=body.get('dest_account', '123456789'),
            )
            return Response(
                content,
                mimetype='text/plain',
                headers={'Content-Disposition': 'attachment; filename=ap-disbursement.ach'},
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/reports/vendor-activity', methods=['GET'])
    @login_required
    def api_acct_ap_vendor_activity():
        from accounting_reports import vendor_activity_report
        return jsonify(vendor_activity_report(db, models, _ledger_id()))

    @app.route('/api/accounting/ap/vendors/<int:vendor_id>/activity', methods=['GET'])
    @login_required
    def api_acct_ap_vendor_activity_detail(vendor_id):
        from accounting_ap_extended import vendor_activity_detail
        try:
            return jsonify(vendor_activity_detail(db, models, _ledger_id(), vendor_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

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
            email=body.get('email') or '',
        )
        if not c.code or not c.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(c)
        db.session.commit()
        return jsonify({'ok': True, 'customer': serialize_customer(c)})

    @app.route('/api/accounting/import/companies', methods=['GET'])
    @login_required
    def api_acct_import_companies():
        from accounting_master_data import list_importable_companies
        Company = deps.get('Company')
        if not Company:
            return jsonify({'error': 'Company directory not available'}), 503
        role = (request.args.get('role') or 'vendor').strip().lower()
        if role not in ('vendor', 'customer'):
            role = 'vendor'
        lid = _ledger_id()
        companies = list_importable_companies(
            db, Company, models['AcctVendor'], models['AcctCustomer'], lid, role=role,
        )
        return jsonify({'companies': companies})

    @app.route('/api/accounting/ap/vendors/from-company', methods=['POST'])
    @login_required
    def api_acct_vendor_from_company():
        from accounting_master_data import import_vendor_from_company
        from accounting_persistence import serialize_vendor
        if not deps.get('Company'):
            return jsonify({'error': 'Company directory not available'}), 503
        body = request.get_json(silent=True) or {}
        if not body.get('company_id'):
            return jsonify({'error': 'company_id required'}), 400
        try:
            v, created = import_vendor_from_company(db, {**models, 'Company': deps['Company']}, _ledger_id(), body['company_id'])
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, 'created': created, 'vendor': serialize_vendor(v)})

    @app.route('/api/accounting/ar/customers/from-company', methods=['POST'])
    @login_required
    def api_acct_customer_from_company():
        from accounting_master_data import import_customer_from_company
        from accounting_persistence import serialize_customer
        if not deps.get('Company'):
            return jsonify({'error': 'Company directory not available'}), 503
        body = request.get_json(silent=True) or {}
        if not body.get('company_id'):
            return jsonify({'error': 'company_id required'}), 400
        try:
            c, created = import_customer_from_company(db, {**models, 'Company': deps['Company']}, _ledger_id(), body['company_id'])
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, 'created': created, 'customer': serialize_customer(c)})

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
        from accounting_ar_extended import assert_customer_can_invoice
        customer = models['AcctCustomer'].query.filter_by(id=int(body['customer_id']), ledger_id=lid).first()
        if not customer:
            return jsonify({'error': 'customer not found'}), 400
        try:
            assert_customer_can_invoice(customer)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        doc = AcctARDocument(
            ledger_id=lid,
            customer_id=int(body['customer_id']),
            document_number=(body.get('document_number') or '').strip(),
            document_type=(body.get('document_type') or 'Invoice')[:20],
            document_date=date_cls.fromisoformat(body['document_date']) if body.get('document_date') else date_cls.today(),
            due_date=date_cls.fromisoformat(body['due_date']) if body.get('due_date') else None,
            amount=float(body.get('amount') or 0),
            project_id=body.get('project_id'),
            ship_to_id=body.get('ship_to_id'),
            status='Open',
        )
        if not doc.document_number:
            return jsonify({'error': 'document_number required'}), 400
        db.session.add(doc)
        db.session.flush()
        if body.get('post_to_gl'):
            from accounting_posting import post_ar_invoice_to_gl
            from financial_security import require_accounting_role
            try:
                require_accounting_role(current_user)
                post_ar_invoice_to_gl(
                    db, models, doc.id,
                    revenue_account_id=body.get('revenue_account_id'),
                    user_id=getattr(current_user, 'id', None),
                )
            except (PermissionError, ValueError) as exc:
                db.session.rollback()
                return jsonify({'error': str(exc)}), 400
        db.session.commit()
        return jsonify({'ok': True, 'invoice': serialize_ar_doc(doc)})

    @app.route('/api/accounting/ar/customer-groups', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_customer_groups():
        from accounting_ar_extended import serialize_customer_group
        AcctCustomerGroup = models['AcctCustomerGroup']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctCustomerGroup.query.filter_by(ledger_id=lid).all()
            return jsonify({'groups': [serialize_customer_group(g) for g in rows]})
        body = request.get_json(silent=True) or {}
        g = AcctCustomerGroup(
            ledger_id=lid,
            code=(body.get('code') or '')[:20],
            name=(body.get('name') or '')[:120],
            credit_limit=float(body.get('credit_limit') or 0),
        )
        if not g.code or not g.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(g)
        db.session.commit()
        return jsonify({'group': serialize_customer_group(g)}), 201

    @app.route('/api/accounting/ar/customers/<int:customer_id>/profile', methods=['PATCH'])
    @login_required
    def api_acct_ar_customer_profile(customer_id):
        from accounting_ar_extended import serialize_customer_extended
        from accounting_enforcement import merge_optional_fields, optional_fields_from_entity
        c = models['AcctCustomer'].query.filter_by(id=customer_id, ledger_id=_ledger_id()).first_or_404()
        body = request.get_json(silent=True) or {}
        if 'customer_group_id' in body:
            c.customer_group_id = int(body['customer_group_id']) if body['customer_group_id'] else None
        if 'credit_hold' in body:
            c.credit_hold = bool(body['credit_hold'])
        if 'national_account_code' in body:
            c.national_account_code = str(body['national_account_code'])[:40]
        if 'optional_fields' in body:
            c.details_json = merge_optional_fields(c.details_json, 'customer', body['optional_fields'], models, _ledger_id())
        db.session.commit()
        out = serialize_customer_extended(c)
        out['optional_fields'] = optional_fields_from_entity(c)
        return jsonify({'customer': out})

    @app.route('/api/accounting/ar/customers/<int:customer_id>/ship-tos', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_ship_tos(customer_id):
        import json as json_mod
        from accounting_ar_extended import serialize_ship_to
        AcctCustomerShipTo = models['AcctCustomerShipTo']
        c = models['AcctCustomer'].query.filter_by(id=customer_id, ledger_id=_ledger_id()).first_or_404()
        if request.method == 'GET':
            rows = AcctCustomerShipTo.query.filter_by(customer_id=c.id).all()
            return jsonify({'ship_tos': [serialize_ship_to(s) for s in rows]})
        body = request.get_json(silent=True) or {}
        s = AcctCustomerShipTo(
            customer_id=c.id,
            code=(body.get('code') or 'MAIN')[:20],
            name=(body.get('name') or c.name)[:120],
            address_json=json_mod.dumps(body.get('address') or {}),
            is_default=bool(body.get('is_default')),
        )
        db.session.add(s)
        db.session.commit()
        return jsonify({'ship_to': serialize_ship_to(s)}), 201

    @app.route('/api/accounting/ar/memos', methods=['POST'])
    @login_required
    def api_acct_ar_memos():
        from accounting_ar_extended import create_ar_memo
        from accounting_persistence import serialize_ar_doc
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            doc = create_ar_memo(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'invoice': serialize_ar_doc(doc)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/recurring-invoices', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_recurring():
        from accounting_ar_extended import serialize_recurring_ar
        from datetime import date as date_cls
        AcctARRecurringInvoice = models['AcctARRecurringInvoice']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctARRecurringInvoice.query.filter_by(ledger_id=lid).all()
            return jsonify({'recurring': [serialize_recurring_ar(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        r = AcctARRecurringInvoice(
            ledger_id=lid,
            customer_id=int(body['customer_id']),
            description=body.get('description'),
            amount=float(body.get('amount') or 0),
            frequency=(body.get('frequency') or 'monthly')[:20],
            next_run_date=date_cls.fromisoformat(body['next_run_date']) if body.get('next_run_date') else date_cls.today(),
            is_active=True,
        )
        db.session.add(r)
        db.session.commit()
        return jsonify({'recurring': serialize_recurring_ar(r)}), 201

    @app.route('/api/accounting/ar/recurring-invoices/<int:rec_id>/generate', methods=['POST'])
    @login_required
    def api_acct_ar_recurring_generate(rec_id):
        from accounting_ar_extended import generate_recurring_ar_invoice
        from accounting_persistence import serialize_ar_doc
        r = models['AcctARRecurringInvoice'].query.filter_by(id=rec_id, ledger_id=_ledger_id()).first_or_404()
        try:
            doc = generate_recurring_ar_invoice(db, models, r)
            db.session.commit()
            return jsonify({'invoice': serialize_ar_doc(doc)})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/dunning/overdue', methods=['GET'])
    @login_required
    def api_acct_ar_dunning_overdue():
        from accounting_ar_extended import overdue_customers
        rows = overdue_customers(models['AcctARDocument'], models['AcctCustomer'], _ledger_id())
        return jsonify({'customers': rows})

    @app.route('/api/accounting/ar/dunning/send', methods=['POST'])
    @login_required
    def api_acct_ar_dunning_send():
        from accounting_ar_extended import dunning_email_package
        body = request.get_json(silent=True) or {}
        try:
            out = dunning_email_package(
                db, models, _ledger_id(),
                body['customer_id'],
                body.get('level', 1),
                body.get('message', ''),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (KeyError, ValueError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/customers/<int:customer_id>/statement/print', methods=['GET'])
    @login_required
    def api_acct_ar_statement_print(customer_id):
        from accounting_ar_extended import customer_statement, statement_printable_html
        from flask import Response
        AcctLedger = models['AcctLedger']
        try:
            data = customer_statement(db, models, _ledger_id(), customer_id)
            ledger = AcctLedger.query.get(_ledger_id())
            html = statement_printable_html(data, company_name=ledger.name if ledger else 'Case PM')
            return Response(html, mimetype='text/html')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/customers/<int:customer_id>/statement', methods=['GET'])
    @login_required
    def api_acct_ar_statement(customer_id):
        from accounting_ar_extended import customer_statement
        try:
            return jsonify(customer_statement(db, models, _ledger_id(), customer_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/receipt-batches', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_receipt_batches():
        from accounting_ar_extended import create_receipt_batch, post_receipt_batch, next_receipt_batch_number
        AcctARReceiptBatch = models['AcctARReceiptBatch']
        AcctARReceiptBatchLine = models['AcctARReceiptBatchLine']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctARReceiptBatch.query.filter_by(ledger_id=lid).order_by(AcctARReceiptBatch.id.desc()).limit(30).all()
            return jsonify({'batches': [{
                'id': b.id, 'batch_number': b.batch_number,
                'batch_date': b.batch_date.isoformat() if b.batch_date else None,
                'status': b.status,
            } for b in rows]})
        body = request.get_json(silent=True) or {}
        batch = create_receipt_batch(db, models, lid, body, user_id=current_user.id)
        db.session.commit()
        return jsonify({'batch': {'id': batch.id, 'batch_number': batch.batch_number, 'status': batch.status}}), 201

    @app.route('/api/accounting/ar/receipt-batches/<int:batch_id>/post', methods=['POST'])
    @login_required
    def api_acct_ar_receipt_batch_post(batch_id):
        from accounting_ar_extended import post_receipt_batch
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        batch = models['AcctARReceiptBatch'].query.filter_by(id=batch_id, ledger_id=_ledger_id()).first_or_404()
        try:
            out = post_receipt_batch(db, models, batch, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/bank/accounts', methods=['GET', 'POST'])
    @login_required
    def api_acct_bank_accounts():
        from accounting_bank_service import bank_ledger_summary, serialize_bank_account, patch_bank_account
        AcctBankAccount = models['AcctBankAccount']
        AcctGLAccount = models['AcctGLAccount']
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify({'accounts': bank_ledger_summary(db, models, lid)})
        body = request.get_json(silent=True) or {}
        a = AcctBankAccount(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            name=(body.get('name') or '').strip(),
            currency=body.get('currency') or 'USD',
            gl_account_id=body.get('gl_account_id'),
        )
        if not a.code or not a.name:
            return jsonify({'error': 'code and name required'}), 400
        db.session.add(a)
        db.session.commit()
        return jsonify({'ok': True, 'account': serialize_bank_account(a, balance=0, unreconciled=0)})

    @app.route('/api/accounting/bank/accounts/<int:account_id>', methods=['PATCH'])
    @login_required
    def api_acct_bank_account_patch(account_id):
        from accounting_bank_service import patch_bank_account, serialize_bank_account, bank_ledger_summary
        AcctBankAccount = models['AcctBankAccount']
        AcctGLAccount = models['AcctGLAccount']
        lid = _ledger_id()
        a = AcctBankAccount.query.filter_by(id=account_id, ledger_id=lid).first_or_404()
        body = request.get_json(silent=True) or {}
        try:
            patch_bank_account(a, body, AcctGLAccount, lid)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        summary = {x['id']: x for x in bank_ledger_summary(db, models, lid)}
        return jsonify({'ok': True, 'account': summary.get(a.id, serialize_bank_account(a))})

    @app.route('/api/accounting/bank/transactions', methods=['GET', 'POST'])
    @login_required
    def api_acct_bank_transactions_mut():
        from accounting_bank_service import record_manual_bank_transaction
        from financial_security import require_accounting_role
        from datetime import date as date_cls
        AcctBankTransaction = models['AcctBankTransaction']
        if request.method == 'GET':
            bank_id = request.args.get('bank_account_id', type=int)
            q = AcctBankTransaction.query
            if bank_id:
                q = q.filter_by(bank_account_id=bank_id)
            rows = q.order_by(AcctBankTransaction.id.desc()).limit(200).all()
            return jsonify({'transactions': [{
                'id': t.id, 'bank_account_id': t.bank_account_id,
                'transaction_date': t.transaction_date.isoformat() if t.transaction_date else None,
                'description': t.description, 'amount': t.amount,
                'transaction_type': t.transaction_type,
                'reconciled': t.reconciled, 'reference': t.reference,
            } for t in rows]})
        body = request.get_json(silent=True) or {}
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            td = body.get('transaction_date')
            out = record_manual_bank_transaction(
                db, models,
                ledger_id=_ledger_id(),
                bank_account_id=body['bank_account_id'],
                amount=body.get('amount'),
                description=body.get('description') or '',
                transaction_type=body.get('transaction_type') or 'Manual',
                reference=body.get('reference') or '',
                transaction_date=date_cls.fromisoformat(td) if td else None,
                post_gl=bool(body.get('post_to_gl')),
                offset_account_id=body.get('offset_account_id'),
                user_id=getattr(current_user, 'id', None),
            )
            db.session.commit()
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/tax/groups', methods=['GET', 'POST'])
    @login_required
    def api_acct_tax_groups():
        from accounting_operations import serialize_tax_group
        AcctTaxGroup = models['AcctTaxGroup']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctTaxGroup.query.filter_by(ledger_id=lid).order_by(AcctTaxGroup.code).all()
            return jsonify({'groups': [serialize_tax_group(g) for g in rows]})
        body = request.get_json(silent=True) or {}
        g = AcctTaxGroup(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            description=body.get('description') or '',
            rate_percent=float(body.get('rate_percent') or 0),
            authority=body.get('authority') or '',
            tax_type=(body.get('tax_type') or 'sales')[:20],
            applies_to=(body.get('applies_to') or 'both')[:10],
            is_active=body.get('is_active', True) is not False,
        )
        if not g.code:
            return jsonify({'error': 'code required'}), 400
        db.session.add(g)
        db.session.commit()
        return jsonify({'ok': True, 'group': serialize_tax_group(g)})

    @app.route('/api/accounting/tax/groups/<int:group_id>', methods=['PATCH', 'DELETE'])
    @login_required
    def api_acct_tax_group_detail(group_id):
        from accounting_operations import serialize_tax_group
        AcctTaxGroup = models['AcctTaxGroup']
        g = AcctTaxGroup.query.get_or_404(group_id)
        if g.ledger_id != _ledger_id():
            return jsonify({'error': 'Not found'}), 404
        if request.method == 'DELETE':
            db.session.delete(g)
            db.session.commit()
            return jsonify({'ok': True})
        body = request.get_json(silent=True) or {}
        for field in ('description', 'authority', 'tax_type', 'applies_to'):
            if field in body:
                setattr(g, field, str(body[field])[:80])
        if 'rate_percent' in body:
            g.rate_percent = float(body['rate_percent'] or 0)
        if 'is_active' in body:
            g.is_active = bool(body['is_active'])
        db.session.commit()
        return jsonify({'ok': True, 'group': serialize_tax_group(g)})

    @app.route('/api/accounting/tax/calculate', methods=['POST'])
    @login_required
    def api_acct_tax_calculate():
        from accounting_operations import calculate_tax
        body = request.get_json(silent=True) or {}
        try:
            out = calculate_tax(
                db, models, _ledger_id(),
                amount=body.get('amount', 0),
                tax_group_code=body.get('tax_group_code'),
                tax_group_id=body.get('tax_group_id'),
            )
            return jsonify(out)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/tax/summary', methods=['GET'])
    @login_required
    def api_acct_tax_summary():
        from accounting_operations import tax_liability_summary
        return jsonify(tax_liability_summary(db, models, _ledger_id()))

    @app.route('/api/accounting/inventory/items', methods=['GET', 'POST'])
    @login_required
    def api_acct_inventory():
        from accounting_operations import serialize_inventory_item
        AcctInventoryItem = models['AcctInventoryItem']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctInventoryItem.query.filter_by(ledger_id=lid).limit(500).all()
            return jsonify({'items': [serialize_inventory_item(i) for i in rows]})
        body = request.get_json(silent=True) or {}
        i = AcctInventoryItem(
            ledger_id=lid,
            item_number=(body.get('item_number') or '').strip(),
            description=body.get('description') or '',
            qty_on_hand=float(body.get('qty_on_hand') or 0),
            unit_cost=float(body.get('unit_cost') or 0),
            uom=(body.get('uom') or 'EA')[:10],
        )
        if not i.item_number:
            return jsonify({'error': 'item_number required'}), 400
        db.session.add(i)
        db.session.commit()
        return jsonify({'ok': True, 'item': serialize_inventory_item(i)})

    @app.route('/api/accounting/inventory/transactions', methods=['GET'])
    @login_required
    def api_acct_inventory_txns():
        AcctInventoryTransaction = models['AcctInventoryTransaction']
        AcctInventoryItem = models['AcctInventoryItem']
        lid = _ledger_id()
        item_id = request.args.get('item_id', type=int)
        q = AcctInventoryTransaction.query.filter_by(ledger_id=lid)
        if item_id:
            q = q.filter_by(item_id=item_id)
        rows = q.order_by(AcctInventoryTransaction.id.desc()).limit(200).all()
        items = {i.id: i.item_number for i in AcctInventoryItem.query.filter_by(ledger_id=lid).all()}
        return jsonify({'transactions': [{
            'id': t.id,
            'item_id': t.item_id,
            'item_number': items.get(t.item_id, ''),
            'txn_type': t.txn_type,
            'qty_delta': t.qty_delta,
            'unit_cost': t.unit_cost,
            'reference': t.reference,
            'created_at': t.created_at.isoformat() if t.created_at else None,
        } for t in rows]})

    @app.route('/api/accounting/inventory/items/<int:item_id>/adjust', methods=['POST'])
    @login_required
    def api_acct_inventory_adjust(item_id):
        """Receive (+) or issue (-) quantity on hand."""
        from accounting_operations import record_inventory_movement
        body = request.get_json(silent=True) or {}
        delta = float(body.get('qty_delta') or 0)
        if delta == 0:
            return jsonify({'error': 'qty_delta required'}), 400
        try:
            out = record_inventory_movement(
                db, models, _ledger_id(), item_id,
                qty_delta=delta,
                txn_type=body.get('txn_type') or 'adjust',
                unit_cost=body.get('unit_cost'),
                reference=body.get('reference') or '',
                project_id=body.get('project_id'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 404

    @app.route('/api/accounting/po/orders', methods=['GET', 'POST'])
    @login_required
    def api_acct_po():
        import json as json_mod
        from datetime import date as date_cls
        from accounting_operations import po_recompute_total, serialize_po
        AcctPurchaseOrder = models['AcctPurchaseOrder']
        AcctVendor = models['AcctVendor']
        lid = _ledger_id()
        vendors = {v.id: v.name for v in AcctVendor.query.filter_by(ledger_id=lid).all()}
        if request.method == 'GET':
            rows = AcctPurchaseOrder.query.filter_by(ledger_id=lid).order_by(AcctPurchaseOrder.id.desc()).limit(200).all()
            return jsonify({'orders': [serialize_po(o, vendors) for o in rows]})
        body = request.get_json(silent=True) or {}
        lines = body.get('lines') or []
        total = float(body.get('total_amount') or 0)
        if lines:
            total = po_recompute_total(lines)
        o = AcctPurchaseOrder(
            ledger_id=lid,
            vendor_id=body.get('vendor_id'),
            po_number=(body.get('po_number') or '').strip(),
            order_date=date_cls.today(),
            total_amount=total,
            project_id=body.get('project_id'),
            status='Open',
            lines_json=json_mod.dumps(lines) if lines else None,
        )
        if not o.po_number:
            return jsonify({'error': 'po_number required'}), 400
        db.session.add(o)
        db.session.commit()
        return jsonify({'ok': True, 'order': serialize_po(o, vendors)})

    @app.route('/api/accounting/po/orders/<int:po_id>', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_po_detail(po_id):
        import json as json_mod
        from accounting_operations import po_recompute_total, serialize_po
        AcctPurchaseOrder = models['AcctPurchaseOrder']
        AcctVendor = models['AcctVendor']
        lid = _ledger_id()
        vendors = {v.id: v.name for v in AcctVendor.query.filter_by(ledger_id=lid).all()}
        o = AcctPurchaseOrder.query.get_or_404(po_id)
        if o.ledger_id != lid:
            return jsonify({'error': 'Not found'}), 404
        if request.method == 'GET':
            return jsonify({'order': serialize_po(o, vendors)})
        body = request.get_json(silent=True) or {}
        if 'status' in body:
            o.status = str(body['status'])[:20]
        if 'vendor_id' in body:
            o.vendor_id = body['vendor_id']
        if 'lines' in body:
            lines = body['lines'] or []
            o.lines_json = json_mod.dumps(lines)
            o.total_amount = po_recompute_total(lines)
        db.session.commit()
        return jsonify({'ok': True, 'order': serialize_po(o, vendors)})

    @app.route('/api/accounting/po/orders/<int:po_id>/receive', methods=['POST'])
    @login_required
    def api_acct_po_receive(po_id):
        from accounting_operations import receive_purchase_order
        body = request.get_json(silent=True) or {}
        try:
            out = receive_purchase_order(db, models, _ledger_id(), po_id, lines_received=body.get('lines'))
            db.session.commit()
            return jsonify({'ok': True, 'order': out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/orders', methods=['GET', 'POST'])
    @login_required
    def api_acct_oe():
        import json as json_mod
        from datetime import date as date_cls
        from accounting_operations import po_recompute_total, serialize_oe
        AcctSalesOrder = models['AcctSalesOrder']
        AcctCustomer = models['AcctCustomer']
        lid = _ledger_id()
        customers = {c.id: c.name for c in AcctCustomer.query.filter_by(ledger_id=lid).all()}
        if request.method == 'GET':
            rows = AcctSalesOrder.query.filter_by(ledger_id=lid).order_by(AcctSalesOrder.id.desc()).limit(200).all()
            return jsonify({'orders': [serialize_oe(o, customers) for o in rows]})
        body = request.get_json(silent=True) or {}
        lines = body.get('lines') or []
        total = float(body.get('total_amount') or 0)
        if lines:
            total = po_recompute_total(lines)
        o = AcctSalesOrder(
            ledger_id=lid,
            customer_id=body.get('customer_id'),
            order_number=(body.get('order_number') or '').strip(),
            order_date=date_cls.today(),
            total_amount=total,
            project_id=body.get('project_id'),
            status='Open',
            lines_json=json_mod.dumps(lines) if lines else None,
        )
        if not o.order_number:
            return jsonify({'error': 'order_number required'}), 400
        db.session.add(o)
        db.session.commit()
        return jsonify({'ok': True, 'order': serialize_oe(o, customers)})

    @app.route('/api/accounting/oe/orders/<int:order_id>', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_oe_detail(order_id):
        import json as json_mod
        from accounting_operations import po_recompute_total, serialize_oe
        AcctSalesOrder = models['AcctSalesOrder']
        AcctCustomer = models['AcctCustomer']
        lid = _ledger_id()
        customers = {c.id: c.name for c in AcctCustomer.query.filter_by(ledger_id=lid).all()}
        o = AcctSalesOrder.query.get_or_404(order_id)
        if o.ledger_id != lid:
            return jsonify({'error': 'Not found'}), 404
        if request.method == 'GET':
            return jsonify({'order': serialize_oe(o, customers)})
        body = request.get_json(silent=True) or {}
        if 'status' in body:
            o.status = str(body['status'])[:20]
        if 'customer_id' in body:
            o.customer_id = body['customer_id']
        if 'lines' in body:
            lines = body['lines'] or []
            o.lines_json = json_mod.dumps(lines)
            o.total_amount = po_recompute_total(lines)
        db.session.commit()
        return jsonify({'ok': True, 'order': serialize_oe(o, customers)})

    @app.route('/api/accounting/oe/orders/<int:order_id>/ship', methods=['POST'])
    @login_required
    def api_acct_oe_ship(order_id):
        from accounting_operations import ship_sales_order
        body = request.get_json(silent=True) or {}
        try:
            out = ship_sales_order(db, models, _ledger_id(), order_id, lines_shipped=body.get('lines'))
            db.session.commit()
            return jsonify({'ok': True, 'order': out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/orders/<int:order_id>/invoice', methods=['POST'])
    @login_required
    def api_acct_oe_invoice(order_id):
        from accounting_operations import invoice_sales_order
        try:
            out = invoice_sales_order(db, models, _ledger_id(), order_id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/assets', methods=['GET', 'POST'])
    @login_required
    def api_acct_assets():
        from datetime import date as date_cls
        from accounting_operations import serialize_asset
        AcctFixedAsset = models['AcctFixedAsset']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctFixedAsset.query.filter_by(ledger_id=lid).order_by(AcctFixedAsset.asset_number).all()
            return jsonify({'assets': [serialize_asset(a) for a in rows]})
        body = request.get_json(silent=True) or {}
        a = AcctFixedAsset(
            ledger_id=lid,
            asset_number=(body.get('asset_number') or '').strip(),
            description=body.get('description') or '',
            acquisition_date=date_cls.today(),
            acquisition_cost=float(body.get('acquisition_cost') or 0),
            useful_life_months=int(body.get('useful_life_months') or 60),
            depreciation_method=(body.get('depreciation_method') or 'straight_line')[:30],
            location=(body.get('location') or '')[:120],
            serial_number=(body.get('serial_number') or '')[:80],
            salvage_value=float(body.get('salvage_value') or 0),
        )
        if not a.asset_number:
            return jsonify({'error': 'asset_number required'}), 400
        db.session.add(a)
        db.session.commit()
        return jsonify({'ok': True, 'asset': serialize_asset(a)})

    @app.route('/api/accounting/assets/<int:asset_id>', methods=['PATCH'])
    @login_required
    def api_acct_asset_patch(asset_id):
        from accounting_operations import serialize_asset
        AcctFixedAsset = models['AcctFixedAsset']
        a = AcctFixedAsset.query.get_or_404(asset_id)
        if a.ledger_id != _ledger_id():
            return jsonify({'error': 'Not found'}), 404
        body = request.get_json(silent=True) or {}
        for field in ('description', 'location', 'serial_number', 'depreciation_method', 'book', 'status'):
            if field in body:
                setattr(a, field, str(body[field])[:120])
        for field in ('acquisition_cost', 'salvage_value', 'accumulated_depreciation'):
            if field in body:
                setattr(a, field, float(body[field] or 0))
        if 'useful_life_months' in body:
            a.useful_life_months = int(body['useful_life_months'] or 60)
        db.session.commit()
        return jsonify({'ok': True, 'asset': serialize_asset(a)})

    @app.route('/api/accounting/assets/<int:asset_id>/dispose', methods=['POST'])
    @login_required
    def api_acct_asset_dispose(asset_id):
        from financial_security import require_accounting_role
        from accounting_operations import dispose_fixed_asset
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = dispose_fixed_asset(db, models, _ledger_id(), asset_id, proceeds=body.get('proceeds', 0))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/assets/depreciation-runs', methods=['GET'])
    @login_required
    def api_acct_depreciation_runs():
        AcctDepreciationRun = models['AcctDepreciationRun']
        lid = _ledger_id()
        rows = AcctDepreciationRun.query.filter_by(ledger_id=lid).order_by(AcctDepreciationRun.id.desc()).limit(24).all()
        return jsonify({'runs': [{
            'id': r.id,
            'run_number': r.run_number,
            'period_date': r.period_date.isoformat() if r.period_date else None,
            'total_amount': r.total_amount,
            'journal_batch_id': r.journal_batch_id,
            'status': r.status,
        } for r in rows]})

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
                'payment_method': p.payment_method, 'status': p.status,
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
                discount_amount=body.get('discount_amount'),
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

    @app.route('/api/accounting/payroll/import/users', methods=['GET'])
    @login_required
    def api_acct_payroll_import_users():
        from accounting_master_data import list_importable_users
        User = deps.get('User')
        if not User:
            return jsonify({'error': 'User directory not available'}), 503
        users = list_importable_users(db, User, models['AcctPayrollEmployee'], _ledger_id())
        return jsonify({'users': users})

    @app.route('/api/accounting/payroll/employees/from-user', methods=['POST'])
    @login_required
    def api_acct_payroll_employee_from_user():
        from accounting_master_data import import_employee_from_user
        from accounting_payroll import serialize_employee
        User = deps.get('User')
        if not User:
            return jsonify({'error': 'User directory not available'}), 503
        body = request.get_json(silent=True) or {}
        if not body.get('user_id'):
            return jsonify({'error': 'user_id required'}), 400
        try:
            e, created = import_employee_from_user(db, {**models, 'User': User}, _ledger_id(), body['user_id'])
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        return jsonify({'ok': True, 'created': created, 'employee': serialize_employee(e)})

    @app.route('/api/accounting/payroll/employees', methods=['GET', 'POST'])
    @login_required
    def api_acct_payroll_employees():
        from accounting_payroll import serialize_employee
        AcctPayrollEmployee = models['AcctPayrollEmployee']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPayrollEmployee.query.filter_by(ledger_id=lid).order_by(AcctPayrollEmployee.last_name).all()
            return jsonify({'employees': [serialize_employee(e) for e in rows]})
        body = request.get_json(silent=True) or {}
        e = AcctPayrollEmployee(
            ledger_id=lid,
            employee_number=(body.get('employee_number') or '').strip(),
            first_name=(body.get('first_name') or '').strip(),
            last_name=(body.get('last_name') or '').strip(),
            pay_type=(body.get('pay_type') or 'hourly')[:20],
            hourly_rate=float(body.get('hourly_rate') or 0),
            annual_salary=float(body.get('annual_salary') or 0),
            default_project_id=body.get('default_project_id'),
            department=(body.get('department') or '')[:80],
            federal_wh_percent=float(body.get('federal_wh_percent', 22)),
            state_wh_percent=float(body.get('state_wh_percent', 5)),
            payment_method=(body.get('payment_method') or 'direct_deposit')[:20],
            bank_account_last4=(body.get('bank_account_last4') or '')[:4],
            user_id=body.get('user_id'),
        )
        if not e.employee_number or not e.first_name or not e.last_name:
            return jsonify({'error': 'employee_number, first_name, last_name required'}), 400
        db.session.add(e)
        db.session.commit()
        return jsonify({'ok': True, 'employee': serialize_employee(e)})

    @app.route('/api/accounting/payroll/employees/<int:emp_id>', methods=['PATCH'])
    @login_required
    def api_acct_payroll_employee_patch(emp_id):
        from accounting_payroll import serialize_employee
        AcctPayrollEmployee = models['AcctPayrollEmployee']
        e = AcctPayrollEmployee.query.get_or_404(emp_id)
        if e.ledger_id != _ledger_id():
            return jsonify({'error': 'Not found'}), 404
        body = request.get_json(silent=True) or {}
        for field in ('first_name', 'last_name', 'department', 'pay_type', 'payment_method', 'status'):
            if field in body:
                setattr(e, field, str(body[field])[:80])
        for field in ('hourly_rate', 'annual_salary', 'federal_wh_percent', 'state_wh_percent'):
            if field in body:
                setattr(e, field, float(body[field] or 0))
        if 'default_project_id' in body:
            e.default_project_id = body['default_project_id']
        db.session.commit()
        return jsonify({'ok': True, 'employee': serialize_employee(e)})

    @app.route('/api/accounting/payroll/deductions', methods=['GET', 'POST'])
    @login_required
    def api_acct_payroll_deductions():
        from accounting_payroll import serialize_deduction
        AcctPayrollDeduction = models['AcctPayrollDeduction']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPayrollDeduction.query.filter_by(ledger_id=lid).order_by(AcctPayrollDeduction.code).all()
            return jsonify({'deductions': [serialize_deduction(d) for d in rows]})
        body = request.get_json(silent=True) or {}
        d = AcctPayrollDeduction(
            ledger_id=lid,
            code=(body.get('code') or '').strip(),
            description=body.get('description') or '',
            deduction_type=(body.get('deduction_type') or 'posttax')[:20],
            calc_method=(body.get('calc_method') or 'fixed')[:10],
            amount=float(body.get('amount') or 0),
            percent=float(body.get('percent') or 0),
        )
        if not d.code:
            return jsonify({'error': 'code required'}), 400
        db.session.add(d)
        db.session.commit()
        return jsonify({'ok': True, 'deduction': serialize_deduction(d)})

    @app.route('/api/accounting/payroll/deductions/enroll', methods=['POST'])
    @login_required
    def api_acct_payroll_deduction_enroll():
        AcctPayrollEmployeeDeduction = models['AcctPayrollEmployeeDeduction']
        body = request.get_json(silent=True) or {}
        emp_id = body.get('employee_id')
        ded_id = body.get('deduction_id')
        if not emp_id or not ded_id:
            return jsonify({'error': 'employee_id and deduction_id required'}), 400
        existing = AcctPayrollEmployeeDeduction.query.filter_by(
            employee_id=int(emp_id), deduction_id=int(ded_id)
        ).first()
        if existing:
            return jsonify({'ok': True, 'id': existing.id})
        row = AcctPayrollEmployeeDeduction(
            employee_id=int(emp_id),
            deduction_id=int(ded_id),
            override_amount=body.get('override_amount'),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'id': row.id})

    @app.route('/api/accounting/payroll/register', methods=['GET'])
    @login_required
    def api_acct_payroll_register():
        from accounting_payroll import payroll_register
        return jsonify(payroll_register(db, models, _ledger_id()))

    @app.route('/api/accounting/payroll/runs', methods=['GET', 'POST'])
    @login_required
    def api_acct_payroll_runs():
        from datetime import date as date_cls
        from accounting_payroll import serialize_run
        AcctPayrollRun = models['AcctPayrollRun']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPayrollRun.query.filter_by(ledger_id=lid).order_by(AcctPayrollRun.id.desc()).limit(50).all()
            return jsonify({'runs': [serialize_run(r) for r in rows]})
        body = request.get_json(silent=True) or {}

        def _d(v):
            if not v:
                return None
            if hasattr(v, 'isoformat'):
                return v
            return date_cls.fromisoformat(str(v)[:10])

        run = AcctPayrollRun(
            ledger_id=lid,
            run_number=(body.get('run_number') or f'PR-{date_cls.today().isoformat()}')[:30],
            pay_date=_d(body.get('pay_date')) or date_cls.today(),
            period_start=_d(body.get('period_start')),
            period_end=_d(body.get('period_end')),
            pay_frequency=(body.get('pay_frequency') or 'biweekly')[:20],
            total_gross=float(body.get('total_gross') or 0),
            total_net=float(body.get('total_net') or 0),
            total_taxes=float(body.get('total_taxes') or 0),
            status='Open',
            notes=body.get('notes') or '',
        )
        db.session.add(run)
        db.session.commit()
        return jsonify({'ok': True, 'run': serialize_run(run)})

    @app.route('/api/accounting/payroll/runs/<int:run_id>', methods=['GET'])
    @login_required
    def api_acct_payroll_run_detail(run_id):
        from accounting_payroll import serialize_run, serialize_run_line
        AcctPayrollRun = models['AcctPayrollRun']
        AcctPayrollRunLine = models['AcctPayrollRunLine']
        AcctPayrollEmployee = models['AcctPayrollEmployee']
        run = AcctPayrollRun.query.get_or_404(run_id)
        if run.ledger_id != _ledger_id():
            return jsonify({'error': 'Not found'}), 404
        lines = AcctPayrollRunLine.query.filter_by(run_id=run.id).all()
        return jsonify({
            'run': serialize_run(run, [
                serialize_run_line(ln, AcctPayrollEmployee.query.get(ln.employee_id)) for ln in lines
            ]),
        })

    @app.route('/api/accounting/payroll/runs/<int:run_id>/build', methods=['POST'])
    @login_required
    def api_acct_payroll_run_build(run_id):
        from accounting_payroll import build_run_from_employees
        body = request.get_json(silent=True) or {}
        try:
            out = build_run_from_employees(
                db, models, _ledger_id(), run_id,
                default_hours=float(body.get('default_hours') or 40),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payroll/runs/<int:run_id>/calculate', methods=['POST'])
    @login_required
    def api_acct_payroll_run_calculate(run_id):
        from accounting_payroll import recalculate_run
        try:
            run = recalculate_run(db, models, run_id)
            db.session.commit()
            return jsonify({'ok': True, 'run': run})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payroll/runs/<int:run_id>/lines', methods=['POST'])
    @login_required
    def api_acct_payroll_run_line(run_id):
        from accounting_payroll import recalculate_run, serialize_run_line
        AcctPayrollRun = models['AcctPayrollRun']
        AcctPayrollRunLine = models['AcctPayrollRunLine']
        AcctPayrollEmployee = models['AcctPayrollEmployee']
        run = AcctPayrollRun.query.get_or_404(run_id)
        if run.ledger_id != _ledger_id() or run.status != 'Open':
            return jsonify({'error': 'Run not editable'}), 400
        body = request.get_json(silent=True) or {}
        ln = AcctPayrollRunLine(
            run_id=run.id,
            employee_id=int(body['employee_id']),
            hours_regular=float(body.get('hours_regular') or 0),
            hours_overtime=float(body.get('hours_overtime') or 0),
            project_id=body.get('project_id'),
        )
        db.session.add(ln)
        db.session.flush()
        run_data = recalculate_run(db, models, run.id)
        db.session.commit()
        return jsonify({'ok': True, 'run': run_data})

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

    # —— Payment Processing ——
    @app.route('/api/accounting/payments/settings', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_payment_settings():
        from financial_security import require_accounting_role
        from accounting_payment_processing import payment_processor_settings, update_payment_processor_settings
        AcctLedger = models['AcctLedger']
        lid = _ledger_id()
        ledger = AcctLedger.query.get(lid)
        if request.method == 'GET':
            return jsonify(payment_processor_settings(ledger))
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        out = update_payment_processor_settings(ledger, body)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/accounting/payments/batches', methods=['GET', 'POST'])
    @login_required
    def api_acct_payment_batches():
        from financial_security import require_accounting_role
        from accounting_payment_processing import (
            batch_lines,
            create_payment_batch,
            serialize_payment_batch,
        )
        AcctPaymentBatch = models['AcctPaymentBatch']
        AcctPaymentBatchLine = models['AcctPaymentBatchLine']
        AcctVendor = models['AcctVendor']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPaymentBatch.query.filter_by(ledger_id=lid).order_by(AcctPaymentBatch.id.desc()).limit(50).all()
            out = []
            for b in rows:
                lines = batch_lines(AcctPaymentBatchLine, b.id)
                out.append(serialize_payment_batch(b, lines=[{
                    'id': ln.id,
                    'vendor_id': ln.vendor_id,
                    'vendor_name': (AcctVendor.query.get(ln.vendor_id).name if AcctVendor.query.get(ln.vendor_id) else ''),
                    'ap_document_id': ln.ap_document_id,
                    'amount': ln.amount,
                    'check_number': ln.check_number,
                    'reference': ln.reference,
                } for ln in lines]))
            return jsonify({'batches': out})
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            batch = create_payment_batch(db, models, lid, body, user_id=current_user.id)
            db.session.commit()
            lines = batch_lines(AcctPaymentBatchLine, batch.id)
            return jsonify({'batch': serialize_payment_batch(batch, lines=[{
                'id': ln.id, 'vendor_id': ln.vendor_id, 'ap_document_id': ln.ap_document_id,
                'amount': ln.amount, 'reference': ln.reference,
            } for ln in lines])}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payments/batches/<int:batch_id>/post', methods=['POST'])
    @login_required
    def api_acct_payment_batch_post(batch_id):
        from financial_security import require_accounting_role
        from accounting_payment_processing import post_payment_batch, serialize_payment_batch, batch_lines
        AcctPaymentBatch = models['AcctPaymentBatch']
        AcctPaymentBatchLine = models['AcctPaymentBatchLine']
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        lid = _ledger_id()
        batch = AcctPaymentBatch.query.filter_by(id=batch_id, ledger_id=lid).first_or_404()
        try:
            out = post_payment_batch(db, models, batch, user_id=current_user.id)
            db.session.commit()
            lines = batch_lines(AcctPaymentBatchLine, batch.id)
            return jsonify({'ok': True, **out, 'batch': serialize_payment_batch(batch, lines=[{
                'id': ln.id, 'vendor_id': ln.vendor_id, 'amount': ln.amount,
            } for ln in lines])})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payments/batches/<int:batch_id>/micr', methods=['GET'])
    @login_required
    def api_acct_payment_batch_micr(batch_id):
        from accounting_payment_processing import micr_export_rows
        from flask import Response
        import csv
        import io
        lid = _ledger_id()
        try:
            rows = micr_export_rows(db, models, batch_id, lid)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        fmt = (request.args.get('format') or 'json').lower()
        if fmt == 'csv':
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=[
                'check_number', 'payment_number', 'vendor_name', 'amount',
                'payment_date', 'micr_routing', 'micr_account', 'company_name',
            ])
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, '') for k in w.fieldnames})
            return Response(
                buf.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=micr-batch-{batch_id}.csv'},
            )
        return jsonify({'rows': rows})

    @app.route('/api/accounting/payments/pay-now-links', methods=['GET', 'POST'])
    @login_required
    def api_acct_pay_now_links():
        from financial_security import require_accounting_role
        from accounting_payment_processing import create_pay_now_link, serialize_pay_now_link
        AcctPayNowLink = models['AcctPayNowLink']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctPayNowLink.query.filter_by(ledger_id=lid).order_by(AcctPayNowLink.id.desc()).limit(40).all()
            return jsonify({'links': [serialize_pay_now_link(x) for x in rows]})
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            link = create_pay_now_link(
                db, models, lid,
                body['ar_document_id'],
                days_valid=body.get('days_valid', 30),
                payment_method=body.get('payment_method', 'card'),
            )
            db.session.commit()
            return jsonify({'link': serialize_pay_now_link(link)}), 201
        except (KeyError, ValueError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payments/pay-now/<token>/complete', methods=['POST'])
    @login_required
    def api_acct_pay_now_complete(token):
        from accounting_payment_processing import complete_pay_now_link, serialize_pay_now_link
        body = request.get_json(silent=True) or {}
        try:
            out = complete_pay_now_link(
                db, models, token,
                bank_account_id=body.get('bank_account_id'),
                user_id=current_user.id,
            )
            db.session.commit()
            return jsonify({
                'ok': True,
                'link': serialize_pay_now_link(out['link']),
                'receipt_id': out['receipt_id'],
                'journal_batch_id': out.get('journal_batch_id'),
            })
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    # —— G/L Consolidation ——
    @app.route('/api/accounting/consolidation/ledgers', methods=['GET', 'POST'])
    @login_required
    def api_acct_consolidation_ledgers():
        from financial_security import require_accounting_role
        from accounting_consolidation import create_subsidiary_ledger, ledger_tree, serialize_ledger
        AcctLedger = models['AcctLedger']
        _ensure_schema()
        if request.method == 'GET':
            return jsonify(ledger_tree(AcctLedger))
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        parent_id = body.get('parent_ledger_id') or _ledger_id()
        try:
            child = create_subsidiary_ledger(db, models, parent_id, body)
            db.session.commit()
            return jsonify({'ledger': serialize_ledger(child)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/trial-balance', methods=['GET'])
    @login_required
    def api_acct_consolidation_trial_balance():
        from accounting_consolidation import consolidated_trial_balance
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        child_raw = request.args.get('child_ledger_ids', '')
        child_ids = [int(x) for x in child_raw.split(',') if x.strip()] if child_raw else None
        include_parent = request.args.get('include_parent', '1') != '0'
        try:
            data = consolidated_trial_balance(
                db, models, parent_id,
                include_parent=include_parent,
                child_ids=child_ids,
            )
            return jsonify(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/runs', methods=['GET', 'POST'])
    @login_required
    def api_acct_consolidation_runs():
        from financial_security import require_accounting_role
        from accounting_consolidation import create_consolidation_run, serialize_consolidation_run
        AcctConsolidationRun = models['AcctConsolidationRun']
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        if request.method == 'GET':
            rows = AcctConsolidationRun.query.filter_by(parent_ledger_id=parent_id).order_by(
                AcctConsolidationRun.id.desc(),
            ).limit(30).all()
            return jsonify({'runs': [serialize_consolidation_run(r) for r in rows]})
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        body.setdefault('parent_ledger_id', parent_id)
        try:
            run = create_consolidation_run(db, models, parent_id, body)
            db.session.commit()
            return jsonify({'run': serialize_consolidation_run(run)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/runs/<int:run_id>/post-eliminations', methods=['POST'])
    @login_required
    def api_acct_consolidation_post_eliminations(run_id):
        from financial_security import require_accounting_role
        from accounting_consolidation import post_consolidation_eliminations, serialize_consolidation_run
        AcctConsolidationRun = models['AcctConsolidationRun']
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        run = AcctConsolidationRun.query.get_or_404(run_id)
        body = request.get_json(silent=True) or {}
        try:
            out = post_consolidation_eliminations(db, models, run, body, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out, 'run': serialize_consolidation_run(run)})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/fiscal-periods', methods=['GET', 'POST'])
    @login_required
    def api_acct_platform_fiscal():
        from datetime import date as date_cls
        from accounting_platform import generate_fiscal_periods, list_fiscal_periods, set_fiscal_period_status, write_audit
        lid = _ledger_id()
        if request.method == 'GET':
            fy = request.args.get('fiscal_year', type=int)
            return jsonify(list_fiscal_periods(models, lid, fiscal_year=fy))
        body = request.get_json(silent=True) or {}
        if body.get('action') in ('close', 'open'):
            try:
                p = set_fiscal_period_status(db, models, lid, int(body['period_id']), 'Closed' if body['action'] == 'close' else 'Open')
                write_audit(db, models, lid, user_id=current_user.id, action=f"fiscal_{body['action']}", entity_type='fiscal_period', entity_id=p.id)
                db.session.commit()
                return jsonify({'ok': True, 'period': {'id': p.id, 'status': p.status}})
            except ValueError as exc:
                db.session.rollback()
                return jsonify({'error': str(exc)}), 400
        fy = body.get('fiscal_year') or date_cls.today().year
        data = generate_fiscal_periods(db, models, lid, fy)
        write_audit(db, models, lid, user_id=current_user.id, action='fiscal_generate', details={'fiscal_year': fy})
        db.session.commit()
        return jsonify(data), 201

    @app.route('/api/accounting/platform/locations', methods=['GET', 'POST'])
    @login_required
    def api_acct_platform_locations():
        from accounting_platform import serialize_location, upsert_location
        AcctLocation = models['AcctLocation']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctLocation.query.filter_by(ledger_id=lid).order_by(AcctLocation.code).all()
            return jsonify({'locations': [serialize_location(r) for r in rows]})
        try:
            loc = upsert_location(db, models, lid, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'location': serialize_location(loc)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/gl-security', methods=['GET', 'POST'])
    @login_required
    def api_acct_platform_gl_security():
        from accounting_platform import serialize_gl_security, upsert_gl_account_security
        AcctGLAccountSecurity = models['AcctGLAccountSecurity']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctGLAccountSecurity.query.filter_by(ledger_id=lid).limit(200).all()
            return jsonify({'rules': [serialize_gl_security(r) for r in rows]})
        try:
            r = upsert_gl_account_security(db, models, lid, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'rule': serialize_gl_security(r)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/optional-fields', methods=['GET', 'POST'])
    @login_required
    def api_acct_platform_optional_fields():
        from accounting_platform import serialize_optional_field, upsert_optional_field
        AcctOptionalFieldDef = models['AcctOptionalFieldDef']
        lid = _ledger_id()
        entity = request.args.get('entity_type')
        if request.method == 'GET':
            q = AcctOptionalFieldDef.query.filter_by(ledger_id=lid)
            if entity:
                q = q.filter_by(entity_type=entity)
            rows = q.order_by(AcctOptionalFieldDef.sort_order).all()
            return jsonify({'fields': [serialize_optional_field(f) for f in rows]})
        try:
            f = upsert_optional_field(db, models, lid, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'field': serialize_optional_field(f)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/audit-log', methods=['GET'])
    @login_required
    def api_acct_platform_audit():
        from accounting_platform import serialize_audit
        AcctAuditLog = models['AcctAuditLog']
        lid = _ledger_id()
        rows = AcctAuditLog.query.filter_by(ledger_id=lid).order_by(AcctAuditLog.id.desc()).limit(100).all()
        return jsonify({'entries': [serialize_audit(r) for r in rows]})

    @app.route('/api/accounting/platform/locale', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_platform_locale():
        from accounting_platform import ledger_locale_settings, update_ledger_locale
        ledger = models['AcctLedger'].query.get(_ledger_id())
        if request.method == 'GET':
            return jsonify(ledger_locale_settings(ledger))
        data = update_ledger_locale(ledger, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'ok': True, 'locale': data})

    @app.route('/api/accounting/platform/export/chart', methods=['GET'])
    @login_required
    def api_acct_platform_export_chart():
        from accounting_platform import export_chart_csv
        from flask import Response
        csv_text = export_chart_csv(models, _ledger_id())
        return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=chart_of_accounts.csv'})

    @app.route('/api/accounting/platform/import/chart', methods=['POST'])
    @login_required
    def api_acct_platform_import_chart():
        from accounting_platform import import_chart_csv, write_audit
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        csv_text = body.get('csv') or ''
        try:
            out = import_chart_csv(db, models, _ledger_id(), csv_text)
            write_audit(db, models, _ledger_id(), user_id=current_user.id, action='import_coa', details=out)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/integrity', methods=['GET'])
    @login_required
    def api_acct_platform_integrity():
        from accounting_platform import data_integrity_check
        return jsonify(data_integrity_check(db, models, _ledger_id()))

    @app.route('/api/accounting/platform/financial-reporter', methods=['GET'])
    @login_required
    def api_acct_platform_financial_reporter():
        from accounting_platform import financial_reporter_layout
        rtype = request.args.get('report_type') or 'trial_balance'
        return jsonify(financial_reporter_layout(models, _ledger_id(), rtype))

    @app.route('/api/accounting/gl/budgets/<int:budget_id>/clone', methods=['POST'])
    @login_required
    def api_acct_gl_budget_clone(budget_id):
        from accounting_gl_extended import clone_budget, serialize_budget
        try:
            b = clone_budget(db, models, _ledger_id(), budget_id, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'budget': serialize_budget(b)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/recurring-journals/run-due', methods=['POST'])
    @login_required
    def api_acct_gl_recurring_run_due():
        from accounting_gl_extended import run_due_recurring_schedules
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            out = run_due_recurring_schedules(db, models, _ledger_id(), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/match-tolerance', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_ap_match_tolerance():
        from accounting_ap_extended import get_match_tolerance, set_match_tolerance
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify(get_match_tolerance(models, lid))
        t = set_match_tolerance(db, models, lid, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'amount_tolerance': t.amount_tolerance, 'percent_tolerance': t.percent_tolerance})

    @app.route('/api/accounting/ap/invoices/<int:invoice_id>/release-retainage', methods=['POST'])
    @login_required
    def api_acct_ap_release_retainage(invoice_id):
        from accounting_ap_extended import release_retainage
        body = request.get_json(silent=True) or {}
        try:
            out = release_retainage(db, models, _ledger_id(), invoice_id, body.get('amount'), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/recurring-payables/run-due', methods=['POST'])
    @login_required
    def api_acct_ap_recurring_run_due():
        from accounting_gl_ap_ar_complete import run_due_recurring_payables
        try:
            out = run_due_recurring_payables(db, models, _ledger_id(), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/recurring-invoices/run-due', methods=['POST'])
    @login_required
    def api_acct_ar_recurring_run_due():
        from accounting_gl_ap_ar_complete import run_due_recurring_ar_invoices
        try:
            out = run_due_recurring_ar_invoices(db, models, _ledger_id(), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/1099/fire/file', methods=['GET'])
    @login_required
    def api_acct_ap_1099_fire_file():
        from datetime import date as date_cls
        from accounting_gl_ap_ar_complete import export_1099_fire_transmission
        from flask import Response
        yr = request.args.get('tax_year', type=int) or (date_cls.today().year - 1)
        content = export_1099_fire_transmission(db, models, _ledger_id(), yr)
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename=1099-fire-{yr}.txt'},
        )

    @app.route('/api/accounting/gl/subledger-reconcile/suggestion', methods=['GET'])
    @login_required
    def api_acct_gl_subledger_suggestion():
        from accounting_gl_ap_ar_complete import subledger_reconcile_suggestion
        return jsonify(subledger_reconcile_suggestion(db, models, _ledger_id()))

    @app.route('/api/accounting/gl/subledger-reconcile/post', methods=['POST'])
    @login_required
    def api_acct_gl_subledger_post():
        from financial_security import require_accounting_role
        from accounting_gl_ap_ar_complete import post_subledger_adjustment
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            out = post_subledger_adjustment(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/1099/efile', methods=['GET'])
    @login_required
    def api_acct_ap_1099_efile():
        from accounting_ap_extended import export_1099_efile
        from datetime import date as date_cls
        year = request.args.get('tax_year', type=int) or (date_cls.today().year - 1)
        return jsonify(export_1099_efile(db, models, _ledger_id(), year))

    @app.route('/api/accounting/ar/dunning/rules', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_dunning_rules():
        from accounting_ar_extended import serialize_dunning_rule, upsert_dunning_rule
        AcctDunningRule = models['AcctDunningRule']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctDunningRule.query.filter_by(ledger_id=lid).order_by(AcctDunningRule.days_past_due).all()
            return jsonify({'rules': [serialize_dunning_rule(r) for r in rows]})
        r = upsert_dunning_rule(db, models, lid, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'rule': serialize_dunning_rule(r)}), 201

    @app.route('/api/accounting/ar/dunning/candidates', methods=['GET'])
    @login_required
    def api_acct_ar_dunning_candidates():
        from accounting_ar_extended import dunning_candidates
        return jsonify(dunning_candidates(db, models, _ledger_id()))

    @app.route('/api/accounting/ar/cash-application/<int:customer_id>', methods=['GET'])
    @login_required
    def api_acct_ar_cash_application(customer_id):
        from accounting_ar_extended import cash_application_workbench
        return jsonify(cash_application_workbench(db, models, _ledger_id(), customer_id))

    @app.route('/api/accounting/ar/cash-application/apply', methods=['POST'])
    @login_required
    def api_acct_ar_cash_application_apply():
        from accounting_ar_extended import apply_cash_workbench
        try:
            out = apply_cash_workbench(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/ownership', methods=['GET', 'POST'])
    @login_required
    def api_acct_consolidation_ownership():
        from accounting_consolidation import list_ownership, upsert_ownership, serialize_ownership
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        if request.method == 'GET':
            return jsonify(list_ownership(models, parent_id))
        try:
            row = upsert_ownership(db, models, parent_id, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'ownership': serialize_ownership(row)}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/financials', methods=['GET'])
    @login_required
    def api_acct_consolidation_financials():
        from accounting_consolidation import consolidated_financial_statement
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        stmt = request.args.get('statement') or 'balance_sheet'
        as_of = request.args.get('as_of')
        return jsonify(consolidated_financial_statement(db, models, parent_id, statement=stmt, as_of=as_of))

    @app.route('/api/accounting/consolidation/fx-translate', methods=['GET'])
    @login_required
    def api_acct_consolidation_fx():
        from accounting_consolidation import fx_translate_consolidated_tb
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        return jsonify(fx_translate_consolidated_tb(db, models, parent_id, rate_date=request.args.get('rate_date')))

    @app.route('/api/accounting/consolidation/runs/<int:run_id>/suggest-eliminations', methods=['GET'])
    @login_required
    def api_acct_consolidation_suggest_elim(run_id):
        from accounting_consolidation import suggest_auto_eliminations
        run = models['AcctConsolidationRun'].query.get_or_404(run_id)
        return jsonify(suggest_auto_eliminations(db, models, run.parent_ledger_id, run))

    @app.route('/api/accounting/consolidation/runs/<int:run_id>/rollup', methods=['POST'])
    @login_required
    def api_acct_consolidation_rollup(run_id):
        from financial_security import require_accounting_role
        from accounting_consolidation import post_rollup_journal, serialize_consolidation_run
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        run = models['AcctConsolidationRun'].query.get_or_404(run_id)
        try:
            out = post_rollup_journal(db, models, run, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out, 'run': serialize_consolidation_run(run)})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/lock-period', methods=['POST'])
    @login_required
    def api_acct_consolidation_lock_period():
        from financial_security import require_accounting_role
        from accounting_consolidation import lock_entity_periods
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        period_key = body.get('period_key')
        if not period_key:
            return jsonify({'error': 'period_key required (YYYY-MM)'}), 400
        parent_id = body.get('parent_ledger_id') or _ledger_id()
        try:
            out = lock_entity_periods(db, models, parent_id, period_key, lock_children=bool(body.get('lock_children', True)))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/i18n', methods=['GET'])
    @login_required
    def api_acct_platform_i18n():
        from accounting_i18n import pack_for_lang
        from accounting_platform import ledger_locale_settings
        ledger = models['AcctLedger'].query.get(_ledger_id())
        loc = ledger_locale_settings(ledger)
        return jsonify({'lang': loc.get('ui_language', 'en'), 'strings': pack_for_lang(loc.get('ui_language'))})

    @app.route('/api/accounting/platform/year-end-close', methods=['POST'])
    @login_required
    def api_acct_platform_year_end():
        from financial_security import require_accounting_role
        from accounting_platform import year_end_close
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = year_end_close(db, models, _ledger_id(), body.get('fiscal_year'), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/platform/security-matrix', methods=['GET'])
    @login_required
    def api_acct_platform_security_matrix():
        from accounting_platform import security_matrix
        return jsonify(security_matrix(models, _ledger_id()))

    @app.route('/api/accounting/platform/financial-reporter/run', methods=['GET'])
    @login_required
    def api_acct_platform_financial_reporter_run():
        from accounting_platform import run_financial_reporter
        rtype = request.args.get('report_type') or 'trial_balance'
        return jsonify(run_financial_reporter(
            db, models, _ledger_id(), rtype,
            location_id=request.args.get('location_id', type=int),
            as_of=request.args.get('as_of'),
        ))

    @app.route('/api/accounting/platform/export/vendors', methods=['GET'])
    @login_required
    def api_acct_export_vendors():
        from accounting_platform import export_vendors_csv
        from flask import Response
        return Response(export_vendors_csv(models, _ledger_id()), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=vendors.csv'})

    @app.route('/api/accounting/platform/export/customers', methods=['GET'])
    @login_required
    def api_acct_export_customers():
        from accounting_platform import export_customers_csv
        from flask import Response
        return Response(export_customers_csv(models, _ledger_id()), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=customers.csv'})

    @app.route('/api/accounting/platform/import/vendors', methods=['POST'])
    @login_required
    def api_acct_import_vendors():
        from accounting_platform import import_vendors_csv, write_audit
        body = request.get_json(silent=True) or {}
        out = import_vendors_csv(db, models, _ledger_id(), body.get('csv') or '')
        write_audit(db, models, _ledger_id(), user_id=current_user.id, action='import_vendors', details=out)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/import/customers', methods=['POST'])
    @login_required
    def api_acct_import_customers():
        from accounting_platform import import_customers_csv, write_audit
        body = request.get_json(silent=True) or {}
        out = import_customers_csv(db, models, _ledger_id(), body.get('csv') or '')
        write_audit(db, models, _ledger_id(), user_id=current_user.id, action='import_customers', details=out)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/gl/budgets/compare', methods=['GET'])
    @login_required
    def api_acct_gl_budget_compare():
        from accounting_gl_extended import compare_budget_scenarios
        ids = request.args.get('ids', '')
        budget_ids = [int(x) for x in ids.split(',') if x.strip().isdigit()]
        return jsonify(compare_budget_scenarios(db, models, _ledger_id(), budget_ids))

    @app.route('/api/accounting/consolidation/cash-flow', methods=['GET'])
    @login_required
    def api_acct_consolidation_cf():
        from accounting_consolidation import indirect_cash_flow_statement
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        return jsonify(indirect_cash_flow_statement(db, models, parent_id, as_of=request.args.get('as_of')))

    @app.route('/api/accounting/consolidation/nci', methods=['GET'])
    @login_required
    def api_acct_consolidation_nci():
        from accounting_consolidation import non_controlling_interest_summary
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        return jsonify(non_controlling_interest_summary(db, models, parent_id))

    @app.route('/api/accounting/consolidation/fx-post', methods=['POST'])
    @login_required
    def api_acct_consolidation_fx_post():
        from accounting_consolidation import post_fx_translation_adjustment
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        try:
            out = post_fx_translation_adjustment(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/ic-rules', methods=['GET', 'POST'])
    @login_required
    def api_acct_consolidation_ic_rules():
        from accounting_consolidation import list_ic_rules, upsert_ic_rule, serialize_ic_rule
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        if request.method == 'GET':
            return jsonify(list_ic_rules(models, parent_id))
        r = upsert_ic_rule(db, models, parent_id, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'rule': serialize_ic_rule(r)}), 201

    @app.route('/api/accounting/consolidation/ic-reconciliation', methods=['GET'])
    @login_required
    def api_acct_consolidation_ic_recon():
        from accounting_consolidation import intercompany_reconciliation
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        return jsonify(intercompany_reconciliation(db, models, parent_id))

    @app.route('/api/accounting/ap/withholding-rules', methods=['GET', 'POST'])
    @login_required
    def api_acct_ap_withholding():
        from accounting_ap_extended import serialize_withholding_rule, upsert_withholding_rule
        AcctWithholdingRule = models['AcctWithholdingRule']
        lid = _ledger_id()
        if request.method == 'GET':
            rows = AcctWithholdingRule.query.filter_by(ledger_id=lid).all()
            return jsonify({'rules': [serialize_withholding_rule(r) for r in rows]})
        r = upsert_withholding_rule(db, models, lid, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'rule': serialize_withholding_rule(r)}), 201

    @app.route('/api/accounting/ap/match-workbench', methods=['GET'])
    @login_required
    def api_acct_ap_match_workbench():
        from accounting_ap_extended import ap_match_workbench
        return jsonify(ap_match_workbench(db, models, _ledger_id()))

    @app.route('/api/accounting/ap/reports/1099/print', methods=['GET'])
    @login_required
    def api_acct_ap_1099_print():
        from accounting_ap_extended import report_1099_printable_html
        from flask import Response
        from datetime import date as date_cls
        year = request.args.get('tax_year', type=int) or (date_cls.today().year - 1)
        html = report_1099_printable_html(db, models, _ledger_id(), year)
        return Response(html, mimetype='text/html')

    @app.route('/api/accounting/ap/withholding/calculate', methods=['POST'])
    @login_required
    def api_acct_ap_withhold_calc():
        from accounting_ap_extended import compute_withholding_for_invoice
        body = request.get_json(silent=True) or {}
        return jsonify(compute_withholding_for_invoice(db, models, _ledger_id(), body.get('vendor_id'), body.get('gross')))

    @app.route('/api/accounting/ar/dunning/smtp', methods=['POST'])
    @login_required
    def api_acct_ar_dunning_smtp():
        from accounting_ar_extended import send_dunning_smtp
        body = request.get_json(silent=True) or {}
        try:
            out = send_dunning_smtp(db, models, _ledger_id(), body['customer_id'], int(body.get('level') or 1), body.get('message'))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/dunning/run-auto', methods=['POST'])
    @login_required
    def api_acct_ar_dunning_auto():
        from accounting_ar_extended import run_automated_dunning
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        out = run_automated_dunning(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/import/journals', methods=['POST'])
    @login_required
    def api_acct_import_journals():
        from accounting_core_gaps import import_journal_csv
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        out = import_journal_csv(db, models, _ledger_id(), body.get('csv') or '', user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/import/open-ap', methods=['POST'])
    @login_required
    def api_acct_import_open_ap():
        from accounting_core_gaps import import_open_ap_csv
        body = request.get_json(silent=True) or {}
        out = import_open_ap_csv(db, models, _ledger_id(), body.get('csv') or '')
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/import/open-ar', methods=['POST'])
    @login_required
    def api_acct_import_open_ar():
        from accounting_core_gaps import import_open_ar_csv
        body = request.get_json(silent=True) or {}
        out = import_open_ar_csv(db, models, _ledger_id(), body.get('csv') or '')
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/year-end-reopen', methods=['POST'])
    @login_required
    def api_acct_year_end_reopen():
        from accounting_core_gaps import year_end_reopen
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        body = request.get_json(silent=True) or {}
        out = year_end_reopen(db, models, _ledger_id(), body.get('fiscal_year'), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/integrity/remediate', methods=['POST'])
    @login_required
    def api_acct_integrity_remediate():
        from accounting_core_gaps import integrity_remediate
        out = integrity_remediate(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/platform/posting-schedule', methods=['GET'])
    @login_required
    def api_acct_posting_schedule():
        from accounting_platform_depth import posting_schedule_full
        return jsonify(posting_schedule_full(db, models, _ledger_id()))

    @app.route('/api/accounting/platform/fiscal-archives', methods=['GET'])
    @login_required
    def api_acct_platform_fiscal_archives():
        from accounting_platform_depth import list_fiscal_archive_index
        return jsonify(list_fiscal_archive_index(models, _ledger_id()))

    @app.route('/api/accounting/platform/revaluation-runs', methods=['GET'])
    @login_required
    def api_acct_platform_revaluation_runs():
        from accounting_platform_depth import list_revaluation_runs
        return jsonify(list_revaluation_runs(models, _ledger_id()))

    @app.route('/api/accounting/platform/report-layouts', methods=['GET', 'POST'])
    @login_required
    def api_acct_report_layouts():
        from accounting_core_gaps import list_report_layouts, save_report_layout
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify(list_report_layouts(models, lid))
        row = save_report_layout(db, models, lid, request.get_json(silent=True) or {}, user_id=current_user.id)
        db.session.commit()
        return jsonify({'layout': {'id': row.id, 'name': row.name, 'report_type': row.report_type}}), 201

    @app.route('/api/accounting/platform/screen-permissions', methods=['GET', 'PATCH'])
    @login_required
    def api_acct_screen_permissions():
        from accounting_core_gaps import screen_permissions, update_screen_permissions
        ledger = models['AcctLedger'].query.get(_ledger_id())
        if request.method == 'GET':
            return jsonify(screen_permissions(ledger))
        perms = update_screen_permissions(ledger, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'ok': True, 'permissions': perms})

    @app.route('/api/accounting/gl/budgets/<int:budget_id>/lock', methods=['POST'])
    @login_required
    def api_acct_gl_budget_lock(budget_id):
        from accounting_core_gaps import lock_budget
        body = request.get_json(silent=True) or {}
        b = lock_budget(db, models, _ledger_id(), budget_id, locked=bool(body.get('locked', True)))
        db.session.commit()
        return jsonify({'budget_id': b.id, 'status': b.status})

    @app.route('/api/accounting/ar/dunning/letter/<int:customer_id>', methods=['GET'])
    @login_required
    def api_acct_ar_dunning_letter(customer_id):
        from accounting_core_gaps import dunning_letter_html
        from flask import Response
        level = request.args.get('level', type=int) or 1
        html = dunning_letter_html(db, models, _ledger_id(), customer_id, level=level)
        return Response(html, mimetype='text/html')

    @app.route('/api/accounting/ar/cash-application/advanced', methods=['POST'])
    @login_required
    def api_acct_ar_cash_advanced():
        from accounting_ar_extended import apply_cash_workbench_advanced
        try:
            out = apply_cash_workbench_advanced(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/consolidation/cash-flow-ui', methods=['GET'])
    @login_required
    def api_acct_consolidation_cf_ui():
        from accounting_consolidation import indirect_cash_flow_statement
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        return jsonify(indirect_cash_flow_statement(db, models, parent_id, as_of=request.args.get('as_of')))

    # --- Parity wave 2 (broad module gap closure) ---

    @app.route('/api/accounting/bi/kpi-dashboard', methods=['GET'])
    @login_required
    def api_acct_bi_kpi():
        from accounting_parity_wave2 import kpi_dashboard
        return jsonify(kpi_dashboard(db, models, _ledger_id()))

    @app.route('/api/accounting/bank/distribution-codes', methods=['GET', 'POST'])
    @login_required
    def api_acct_bank_dist_codes():
        from accounting_parity_wave2 import list_distribution_codes, save_distribution_code
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify({'codes': list_distribution_codes(models, lid)})
        body = request.get_json(silent=True) or {}
        try:
            cid = save_distribution_code(db, models, lid, body, code_id=body.get('id'))
            db.session.commit()
            return jsonify({'ok': True, 'id': cid}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/bank/distribution-apply', methods=['POST'])
    @login_required
    def api_acct_bank_dist_apply():
        from accounting_parity_wave2 import apply_distribution_to_deposit
        body = request.get_json(silent=True) or {}
        try:
            out = apply_distribution_to_deposit(
                db, models, _ledger_id(), body['bank_account_id'], body['amount'], body['distribution_code'],
                user_id=current_user.id,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/bank/ofx-import', methods=['POST'])
    @login_required
    def api_acct_bank_ofx():
        from accounting_parity_wave2 import import_bank_ofx
        body = request.get_json(silent=True) or {}
        try:
            out = import_bank_ofx(
                db, models, _ledger_id(), body['bank_account_id'], body.get('ofx_text') or '',
                user_id=current_user.id,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/bank/nsf', methods=['POST'])
    @login_required
    def api_acct_bank_nsf():
        from accounting_parity_wave2 import record_nsf
        try:
            out = record_nsf(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/tax/groups/<int:group_id>/components', methods=['GET', 'PUT'])
    @login_required
    def api_acct_tax_components(group_id):
        from accounting_parity_wave2 import save_tax_components, tax_group_with_components
        AcctTaxGroup = models['AcctTaxGroup']
        tg = AcctTaxGroup.query.filter_by(id=group_id, ledger_id=_ledger_id()).first_or_404()
        if request.method == 'GET':
            return jsonify(tax_group_with_components(tg))
        body = request.get_json(silent=True) or {}
        try:
            out = save_tax_components(db, models, _ledger_id(), group_id, body.get('components') or [])
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/tax/filing-prep', methods=['GET'])
    @login_required
    def api_acct_tax_filing():
        from accounting_parity_wave2 import tax_filing_prep
        return jsonify(tax_filing_prep(db, models, _ledger_id(), request.args.get('period_key')))

    @app.route('/api/accounting/tax/apply-document', methods=['POST'])
    @login_required
    def api_acct_tax_apply_doc():
        from accounting_parity_wave2 import apply_tax_to_document
        body = request.get_json(silent=True) or {}
        try:
            out = apply_tax_to_document(db, models, _ledger_id(), body['doc_type'], body['doc_id'], body['tax_group_code'])
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/inventory/lots', methods=['GET', 'POST'])
    @login_required
    def api_acct_inventory_lots():
        from accounting_parity_wave2 import list_lots, receive_lot
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify({'lots': list_lots(models, lid, request.args.get('item_id', type=int))})
        body = request.get_json(silent=True) or {}
        try:
            out = receive_lot(db, models, lid, body['item_id'], body['qty'], body.get('lot_number'), body.get('serial_number'), body.get('unit_cost', 0))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/po/blanket', methods=['POST'])
    @login_required
    def api_acct_po_blanket():
        from accounting_parity_wave2 import create_blanket_po
        body = request.get_json(silent=True) or {}
        try:
            po = create_blanket_po(db, models, _ledger_id(), body)
            db.session.commit()
            return jsonify({'ok': True, 'po_id': po.id, 'po_number': po.po_number}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/po/<int:po_id>/blanket-release', methods=['POST'])
    @login_required
    def api_acct_po_blanket_release(po_id):
        from accounting_parity_wave2 import release_blanket_po
        body = request.get_json(silent=True) or {}
        try:
            out = release_blanket_po(db, models, _ledger_id(), po_id, body.get('amount'), body.get('lines'))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/quotes', methods=['POST'])
    @login_required
    def api_acct_oe_quotes():
        from accounting_parity_wave2 import create_quote
        try:
            so = create_quote(db, models, _ledger_id(), request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'ok': True, 'quote_id': so.id, 'order_number': so.order_number}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/quotes/<int:quote_id>/convert', methods=['POST'])
    @login_required
    def api_acct_oe_quote_convert(quote_id):
        from accounting_parity_wave2 import convert_quote_to_order
        try:
            so = convert_quote_to_order(db, models, _ledger_id(), quote_id)
            db.session.commit()
            return jsonify({'ok': True, 'order_id': so.id, 'order_number': so.order_number})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/returns', methods=['POST'])
    @login_required
    def api_acct_oe_returns():
        from accounting_parity_wave2 import create_sales_return
        try:
            so = create_sales_return(db, models, _ledger_id(), request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify({'ok': True, 'return_id': so.id}), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/summary-billing', methods=['POST'])
    @login_required
    def api_acct_ar_summary_billing():
        from accounting_parity_wave2 import summary_billing_invoice
        body = request.get_json(silent=True) or {}
        try:
            out = summary_billing_invoice(db, models, _ledger_id(), body['parent_customer_id'], body.get('child_customer_ids'), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/credit-reviews', methods=['GET', 'POST'])
    @login_required
    def api_acct_ar_credit_reviews():
        from accounting_parity_wave2 import credit_review_queue, submit_credit_review, resolve_credit_review
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify({'reviews': credit_review_queue(db, models, lid)})
        body = request.get_json(silent=True) or {}
        if body.get('resolve_review_id'):
            try:
                out = resolve_credit_review(db, models, lid, int(body['resolve_review_id']), body, user_id=current_user.id)
                db.session.commit()
                return jsonify({'ok': True, **out})
            except ValueError as exc:
                db.session.rollback()
                return jsonify({'error': str(exc)}), 400
        try:
            out = submit_credit_review(db, models, lid, body, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out}), 201
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ar/cash-workbench/<int:customer_id>', methods=['GET'])
    @login_required
    def api_acct_ar_cash_workbench(customer_id):
        from accounting_parity_wave2 import cash_workbench
        return jsonify(cash_workbench(db, models, _ledger_id(), customer_id))

    @app.route('/api/accounting/ap/match-grid/<int:invoice_id>', methods=['GET'])
    @login_required
    def api_acct_ap_match_grid(invoice_id):
        from accounting_gl_ap_ar_complete import build_match_line_grid
        try:
            return jsonify(build_match_line_grid(db, models, _ledger_id(), invoice_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/ap/t5018', methods=['GET'])
    @login_required
    def api_acct_ap_t5018():
        from datetime import date as date_cls
        from accounting_parity_wave2 import export_t5018
        from flask import Response
        yr = request.args.get('tax_year', type=int) or date_cls.today().year
        return Response(export_t5018(db, models, _ledger_id(), yr), mimetype='text/plain')

    @app.route('/api/accounting/ap/1099/fire', methods=['GET'])
    @login_required
    def api_acct_ap_1099_fire():
        from datetime import date as date_cls
        from accounting_parity_wave2 import export_1099_fire
        yr = request.args.get('tax_year', type=int) or date_cls.today().year
        return jsonify(export_1099_fire(db, models, _ledger_id(), yr))

    @app.route('/api/accounting/gl/budgets/<int:budget_id>/submit-approval', methods=['POST'])
    @login_required
    def api_acct_gl_budget_submit(budget_id):
        from accounting_parity_wave2 import budget_approval_submit
        try:
            b = budget_approval_submit(db, models, _ledger_id(), budget_id, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, 'budget_id': b.id, 'status': b.status})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/budgets/<int:budget_id>/approve', methods=['POST'])
    @login_required
    def api_acct_gl_budget_approve(budget_id):
        from accounting_parity_wave2 import budget_approval_decide
        body = request.get_json(silent=True) or {}
        try:
            b = budget_approval_decide(db, models, _ledger_id(), budget_id, bool(body.get('approved', True)), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, 'budget_id': b.id, 'status': b.status})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/fiscal-archive/<int:fiscal_year>', methods=['GET'])
    @login_required
    def api_acct_gl_fiscal_archive(fiscal_year):
        from accounting_parity_wave2 import fiscal_archive_snapshot
        return jsonify(fiscal_archive_snapshot(db, models, _ledger_id(), fiscal_year))

    @app.route('/api/accounting/consolidation/runs/<int:run_id>/auto-eliminations', methods=['POST'])
    @login_required
    def api_acct_con_auto_elim(run_id):
        from accounting_parity_wave2 import auto_suggest_and_post_eliminations
        parent_id = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        try:
            out = auto_suggest_and_post_eliminations(db, models, parent_id, run_id, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payroll/runs/<int:run_id>/eft-file', methods=['GET'])
    @login_required
    def api_acct_payroll_eft(run_id):
        from accounting_parity_wave2 import payroll_eft_file
        from flask import Response
        try:
            content = payroll_eft_file(db, models, _ledger_id(), run_id)
            return Response(content, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=payroll-eft-{run_id}.csv'})
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payments/stripe-intent', methods=['POST'])
    @login_required
    def api_acct_stripe_intent():
        from accounting_tier14_wave import create_stripe_payment_intent
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(create_stripe_payment_intent(body.get('amount', 0), body.get('currency', 'usd'), body.get('metadata')))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/reports/designer', methods=['GET', 'POST'])
    @login_required
    def api_acct_report_designer():
        from accounting_parity_wave2 import report_designer_list, report_designer_save
        lid = _ledger_id()
        if request.method == 'GET':
            return jsonify({'reports': report_designer_list(models, lid)})
        body = request.get_json(silent=True) or {}
        rid = report_designer_save(db, models, lid, body, user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, 'id': rid}), 201

    @app.route('/api/accounting/reports/schedule', methods=['POST'])
    @login_required
    def api_acct_report_schedule():
        from accounting_parity_wave2 import schedule_report
        try:
            out = schedule_report(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, 'schedule': out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/jobcost/<int:project_id>/revenue-recognition', methods=['GET'])
    @login_required
    def api_acct_jc_revenue(project_id):
        from accounting_parity_wave2 import revenue_recognition_schedule
        return jsonify(revenue_recognition_schedule(db, models, _ledger_id(), project_id))

    @app.route('/api/accounting/assets/depreciate-book', methods=['POST'])
    @login_required
    def api_acct_depreciate_book():
        from accounting_parity_wave2 import run_depreciation_book
        body = request.get_json(silent=True) or {}
        try:
            out = run_depreciation_book(db, models, _ledger_id(), body.get('book', 'GAAP'), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    # --- Parity wave 3 ---

    @app.route('/api/accounting/payroll/form-941', methods=['GET'])
    @login_required
    def api_acct_payroll_941():
        from accounting_parity_wave3 import export_form_941_summary, export_form_941_csv
        from flask import Response
        lid = _ledger_id()
        q = request.args.get('quarter', type=int) or 1
        y = request.args.get('year', type=int) or date.today().year
        if request.args.get('format') == 'csv':
            return Response(export_form_941_csv(db, models, lid, q, y), mimetype='text/csv')
        return jsonify(export_form_941_summary(db, models, lid, q, y))

    @app.route('/api/accounting/payroll/w2-summary', methods=['GET'])
    @login_required
    def api_acct_payroll_w2():
        from accounting_parity_wave3 import export_w2_summary
        y = request.args.get('tax_year', type=int) or date.today().year
        return jsonify(export_w2_summary(db, models, _ledger_id(), y))

    @app.route('/api/accounting/payroll/certified/<int:project_id>', methods=['GET'])
    @login_required
    def api_acct_payroll_certified(project_id):
        from accounting_parity_wave3 import certified_payroll_wh347
        from flask import Response
        we = request.args.get('week_ending') or date.today().isoformat()
        return Response(
            certified_payroll_wh347(db, models, _ledger_id(), project_id, we),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=wh347-p{project_id}.csv'},
        )

    @app.route('/api/accounting/ap/1099/print/<int:vendor_id>', methods=['GET'])
    @login_required
    def api_acct_1099_official(vendor_id):
        from accounting_parity_wave3 import form_1099_official_html
        from flask import Response
        yr = request.args.get('tax_year', type=int) or date.today().year
        html = form_1099_official_html(db, models, _ledger_id(), yr, vendor_id)
        return Response(html, mimetype='text/html')

    @app.route('/api/accounting/payments/stripe-webhook', methods=['POST'])
    def api_acct_stripe_webhook():
        import json
        from accounting_tier14_wave import handle_stripe_webhook
        raw = request.get_data() or b''
        payload = request.get_json(silent=True) or {}
        if not payload and raw:
            try:
                payload = json.loads(raw.decode('utf-8'))
            except Exception:
                payload = {}
        out = handle_stripe_webhook(
            payload,
            request.headers.get('Stripe-Signature', ''),
            raw_body=raw,
            db=db,
            models=models,
        )
        try:
            from accounting_waves_21 import log_stripe_webhook_event

            AcctLedger = models['AcctLedger']
            ledger = AcctLedger.query.order_by(AcctLedger.id).first()
            if ledger:
                log_stripe_webhook_event(ledger, payload, out)
                db.session.commit()
        except Exception:
            db.session.rollback()
        if out.get('pay_now'):
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        elif out.get('received'):
            pass
        status = 400 if out.get('error') else 200
        return jsonify(out), status

    @app.route('/api/accounting/payments/stripe-capture', methods=['POST'])
    @login_required
    def api_acct_stripe_capture():
        from accounting_parity_wave3 import capture_pay_now_stripe
        body = request.get_json(silent=True) or {}
        try:
            out = capture_pay_now_stripe(db, models, body['token'], body.get('payment_intent_id', ''), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, 'receipt_id': out.get('receipt_id'), 'journal_batch_id': out.get('journal_batch_id')})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/reports/comparative', methods=['GET'])
    @login_required
    def api_acct_report_comparative():
        from accounting_parity_wave3 import comparative_income_statement
        pa = request.args.get('period_a') or date.today().strftime('%Y-%m')
        pb = request.args.get('period_b') or date.today().strftime('%Y-%m')
        return jsonify(comparative_income_statement(db, models, _ledger_id(), pa, pb))

    @app.route('/api/accounting/inventory/fifo-issue', methods=['POST'])
    @login_required
    def api_acct_inventory_fifo():
        from accounting_parity_wave3 import inventory_fifo_issue
        body = request.get_json(silent=True) or {}
        try:
            out = inventory_fifo_issue(db, models, _ledger_id(), body['item_id'], body['qty'], body.get('reference'))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/bank/plaid-import', methods=['POST'])
    @login_required
    def api_acct_bank_plaid():
        from accounting_parity_wave3 import import_plaid_transactions
        from accounting_tier14_wave import plaid_sandbox_or_live_transactions
        from accounting_waves_17 import plaid_access_token_for_ledger
        body = request.get_json(silent=True) or {}
        try:
            ledger = models['AcctLedger'].query.get(_ledger_id())
            if ledger and not body.get('access_token'):
                tok = plaid_access_token_for_ledger(ledger)
                if tok:
                    body = {**body, 'access_token': tok}
            txns = plaid_sandbox_or_live_transactions(body)
            out = import_plaid_transactions(
                db, models, _ledger_id(), body['bank_account_id'], txns, user_id=current_user.id,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/gl/batches/<int:batch_id>/validate-segments', methods=['GET'])
    @login_required
    def api_acct_gl_validate_segments(batch_id):
        from accounting_parity_wave3 import validate_journal_batch_segments
        return jsonify(validate_journal_batch_segments(db, models, _ledger_id(), batch_id))

    @app.route('/api/accounting/consolidation/auditor-package', methods=['GET'])
    @login_required
    def api_acct_con_auditor():
        from accounting_parity_wave3 import auditor_package
        parent = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        return jsonify(auditor_package(db, models, parent, as_of=request.args.get('as_of')))

    @app.route('/api/accounting/reports/run-scheduled', methods=['POST'])
    @login_required
    def api_acct_reports_run_scheduled():
        from accounting_tier14_wave import run_scheduled_reports_with_email
        out = run_scheduled_reports_with_email(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/ap/match-grid/<int:invoice_id>/lines', methods=['GET'])
    @login_required
    def api_acct_ap_match_lines(invoice_id):
        from accounting_parity_wave3 import ap_match_line_grid_enriched
        try:
            return jsonify(ap_match_line_grid_enriched(db, models, _ledger_id(), invoice_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    # --- All priority chunks (core 5 + bank + distribution + payroll + construction) ---

    @app.route('/api/accounting/consolidation/auditor-package/download', methods=['GET'])
    @login_required
    def api_acct_auditor_download():
        from accounting_all_chunks import download_auditor_package_bytes
        from flask import Response
        parent = request.args.get('parent_ledger_id', type=int) or _ledger_id()
        data = download_auditor_package_bytes(db, models, parent, as_of=request.args.get('as_of'))
        return Response(data, mimetype='application/zip', headers={
            'Content-Disposition': 'attachment; filename=auditor-package.zip',
        })

    @app.route('/api/accounting/payments/stripe-config', methods=['GET'])
    @login_required
    def api_acct_stripe_config():
        from accounting_all_chunks import stripe_runtime_config
        ledger = models['AcctLedger'].query.get(_ledger_id())
        return jsonify(stripe_runtime_config(ledger))

    @app.route('/api/accounting/bank/auto-match', methods=['GET'])
    @login_required
    def api_acct_bank_auto_match():
        from accounting_all_chunks import bank_auto_match_suggestions
        bid = request.args.get('bank_account_id', type=int)
        if not bid:
            return jsonify({'error': 'bank_account_id required'}), 400
        return jsonify(bank_auto_match_suggestions(db, models, _ledger_id(), bid))

    @app.route('/api/accounting/payments/batches/<int:batch_id>/positive-pay', methods=['GET'])
    @login_required
    def api_acct_positive_pay(batch_id):
        from accounting_all_chunks import positive_pay_export
        from flask import Response
        return Response(positive_pay_export(db, models, _ledger_id(), batch_id), mimetype='text/plain')

    @app.route('/api/accounting/inventory/items/<int:item_id>/costing', methods=['PATCH'])
    @login_required
    def api_acct_item_costing(item_id):
        from accounting_all_chunks import set_item_costing
        body = request.get_json(silent=True) or {}
        try:
            out = set_item_costing(db, models, _ledger_id(), item_id, body.get('costing_method'))
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/po/orders/<int:po_id>/create-ap-invoice', methods=['POST'])
    @login_required
    def api_acct_po_ap_invoice(po_id):
        from accounting_all_chunks import po_receive_create_ap_invoice
        try:
            out = po_receive_create_ap_invoice(db, models, _ledger_id(), po_id, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/orders/<int:order_id>/ship-cogs', methods=['POST'])
    @login_required
    def api_acct_oe_ship_cogs(order_id):
        from accounting_all_chunks import oe_ship_post_cogs
        try:
            out = oe_ship_post_cogs(db, models, _ledger_id(), order_id, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payroll/tax-package/<int:tax_year>', methods=['GET'])
    @login_required
    def api_acct_payroll_tax_pkg(tax_year):
        from accounting_all_chunks import payroll_tax_package
        return jsonify(payroll_tax_package(db, models, _ledger_id(), tax_year))

    @app.route('/api/accounting/payroll/garnishment', methods=['POST'])
    @login_required
    def api_acct_payroll_garnishment():
        from accounting_waves_19 import create_garnishment_order
        body = request.get_json(silent=True) or {}
        try:
            out = create_garnishment_order(db, models, _ledger_id(), body, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/jobcost/<int:project_id>/panel', methods=['GET'])
    @login_required
    def api_acct_jobcost_panel(project_id):
        from accounting_waves_17 import jobcost_with_pay_apps
        from accounting_waves_20 import jobcost_variance_breakdown
        base = jobcost_with_pay_apps(db, models, _ledger_id(), project_id)
        if PayAppProjectState:
            base['variance_detail'] = jobcost_variance_breakdown(
                db, models, _ledger_id(), project_id, PayAppProjectState=PayAppProjectState,
            )
        return jsonify(base)

    @app.route('/api/accounting/ar/progress-billing', methods=['POST'])
    @login_required
    def api_acct_ar_progress():
        from accounting_all_chunks import apply_progress_billing_to_ar
        body = request.get_json(silent=True) or {}
        try:
            out = apply_progress_billing_to_ar(
                db, models, _ledger_id(), body['customer_id'], body['amount'],
                body.get('project_id'), body.get('document_number'), user_id=current_user.id,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/integrations/status', methods=['GET'])
    @login_required
    def api_acct_integrations_status():
        import os
        from accounting_all_chunks import stripe_runtime_config
        from accounting_tier14_wave import sage_integration_status
        from accounting_waves_17 import plaid_credentials_ok, sage_hybrid_dashboard
        ledger = models['AcctLedger'].query.get(_ledger_id())
        settings = {}
        try:
            from accounting_gl_service import _parse_settings
            settings = _parse_settings(ledger)
        except Exception:
            pass
        plaid_linked = bool((settings.get('plaid') or {}).get('access_token'))
        return jsonify({
            'stripe': {
                **stripe_runtime_config(ledger),
                'webhook_secret_set': bool(os.environ.get('STRIPE_WEBHOOK_SECRET')),
            },
            'plaid': {
                'configured': plaid_credentials_ok(),
                'linked': plaid_linked,
                'link_ui': True,
                'env': os.environ.get('PLAID_ENV', 'sandbox'),
            },
            'sage': sage_integration_status(),
            'sage_hybrid': sage_hybrid_dashboard(db, models, _ledger_id()),
        })

    @app.route('/api/accounting/compliance/w2-efile/<int:tax_year>', methods=['GET'])
    @login_required
    def api_acct_w2_efile(tax_year):
        from accounting_tier14_wave import export_w2_efile_package
        from flask import Response
        return Response(
            export_w2_efile_package(db, models, _ledger_id(), tax_year),
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename=w2-efile-{tax_year}.txt'},
        )

    @app.route('/api/accounting/compliance/941-efile', methods=['GET'])
    @login_required
    def api_acct_941_efile():
        from accounting_tier14_wave import export_941_efile_package
        from flask import Response
        q = request.args.get('quarter', type=int) or 1
        y = request.args.get('year', type=int) or date.today().year
        return Response(
            export_941_efile_package(db, models, _ledger_id(), q, y),
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename=941-{y}-Q{q}.txt'},
        )

    @app.route('/api/accounting/compliance/1099/transmit-log', methods=['POST'])
    @login_required
    def api_acct_1099_transmit_log():
        from accounting_tier14_wave import log_1099_transmit
        body = request.get_json(silent=True) or {}
        yr = body.get('tax_year') or (date.today().year - 1)
        out = log_1099_transmit(db, models, _ledger_id(), int(yr), user_id=current_user.id)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/accounting/po/orders/<int:po_id>/line-grid', methods=['GET'])
    @login_required
    def api_acct_po_line_grid(po_id):
        from accounting_tier14_wave import po_line_receipt_grid
        return jsonify(po_line_receipt_grid(db, models, _ledger_id(), po_id))

    @app.route('/api/accounting/po/orders/<int:po_id>/blanket-release', methods=['POST'])
    @login_required
    def api_acct_po_orders_blanket_release(po_id):
        from accounting_tier14_wave import blanket_po_release
        try:
            out = blanket_po_release(db, models, _ledger_id(), po_id, request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/orders/<int:order_id>/fulfillment-grid', methods=['GET'])
    @login_required
    def api_acct_oe_fulfillment_grid(order_id):
        from accounting_tier14_wave import oe_fulfillment_grid
        return jsonify(oe_fulfillment_grid(db, models, _ledger_id(), order_id))

    @app.route('/api/accounting/inventory/transfer', methods=['POST'])
    @login_required
    def api_acct_ic_transfer():
        from accounting_tier14_wave import inventory_location_transfer
        try:
            out = inventory_location_transfer(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/sage/sync/vendors', methods=['POST'])
    @login_required
    def api_acct_sage_pull_vendors():
        from accounting_tier14_wave import sage_pull_vendors
        out = sage_pull_vendors(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/sage/sync/gl-accounts', methods=['POST'])
    @login_required
    def api_acct_sage_pull_gl():
        from accounting_tier14_wave import sage_pull_gl_accounts
        out = sage_pull_gl_accounts(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/sage/sync/queue-batches', methods=['POST'])
    @login_required
    def api_acct_sage_queue_batches():
        from accounting_tier14_wave import sage_queue_open_batches
        out = sage_queue_open_batches(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    # --- Waves 1–7 depth ---

    @app.route('/api/accounting/integrations/plaid/link-token', methods=['POST'])
    @login_required
    def api_acct_plaid_link_token():
        from accounting_waves_17 import create_plaid_link_token
        try:
            return jsonify(create_plaid_link_token(db, models, _ledger_id(), user_id=current_user.id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/integrations/plaid/exchange', methods=['POST'])
    @login_required
    def api_acct_plaid_exchange():
        from accounting_waves_17 import exchange_plaid_public_token
        body = request.get_json(silent=True) or {}
        try:
            out = exchange_plaid_public_token(db, models, _ledger_id(), body['public_token'], user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/sage/hybrid', methods=['GET', 'POST'])
    @login_required
    def api_acct_sage_hybrid():
        from accounting_waves_17 import sage_hybrid_dashboard, save_sage_hybrid_policy
        if request.method == 'POST':
            out = save_sage_hybrid_policy(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        return jsonify(sage_hybrid_dashboard(db, models, _ledger_id()))

    @app.route('/api/accounting/sage/sync/push-vendors', methods=['POST'])
    @login_required
    def api_acct_sage_push_vendors():
        from accounting_waves_17 import sage_push_vendors
        out = sage_push_vendors(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/sage/sync/push-open-ap', methods=['POST'])
    @login_required
    def api_acct_sage_push_open_ap():
        from accounting_waves_17 import sage_push_open_ap
        out = sage_push_open_ap(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/compliance/calendar', methods=['GET'])
    @login_required
    def api_acct_compliance_calendar():
        from accounting_waves_17 import compliance_filing_calendar
        yr = request.args.get('tax_year', type=int)
        return jsonify(compliance_filing_calendar(_ledger_id(), yr))

    @app.route('/api/accounting/compliance/amendment/<form>', methods=['POST'])
    @login_required
    def api_acct_compliance_amendment(form):
        from accounting_waves_17 import compliance_amendment_package
        from flask import Response
        body = request.get_json(silent=True) or {}
        yr = body.get('tax_year') or request.args.get('tax_year', type=int) or (date.today().year - 1)
        text = compliance_amendment_package(db, models, _ledger_id(), form, int(yr), body)
        return Response(text, mimetype='text/plain', headers={
            'Content-Disposition': f'attachment; filename=amend-{form}-{yr}.txt',
        })

    @app.route('/api/accounting/inventory/lot-serial-grid', methods=['GET'])
    @login_required
    def api_acct_ic_lot_serial():
        from accounting_waves_17 import inventory_lot_serial_grid
        iid = request.args.get('item_id', type=int)
        return jsonify(inventory_lot_serial_grid(db, models, _ledger_id(), iid))

    @app.route('/api/accounting/oe/commissions', methods=['GET'])
    @login_required
    def api_acct_oe_commissions():
        from accounting_waves_17 import oe_commission_summary
        oid = request.args.get('order_id', type=int)
        return jsonify(oe_commission_summary(db, models, _ledger_id(), oid))

    @app.route('/api/accounting/oe/orders/<int:order_id>/commissions', methods=['POST'])
    @login_required
    def api_acct_oe_commissions_set(order_id):
        from accounting_waves_17 import apply_oe_line_commissions
        try:
            out = apply_oe_line_commissions(db, models, _ledger_id(), order_id, request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/reports/designer/layouts', methods=['GET', 'POST'])
    @login_required
    def api_acct_report_designer_layouts():
        from accounting_waves_17 import list_enhanced_report_layouts, save_enhanced_report_layout
        if request.method == 'POST':
            out = save_enhanced_report_layout(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, 'layout': out})
        return jsonify(list_enhanced_report_layouts(db, models, _ledger_id()))

    @app.route('/api/accounting/reports/designer/run/<layout_id>', methods=['POST'])
    @login_required
    def api_acct_report_designer_run(layout_id):
        from accounting_waves_17 import run_enhanced_layout_report
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(run_enhanced_layout_report(db, models, _ledger_id(), layout_id, body))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/assets/tax-depreciate', methods=['POST'])
    @login_required
    def api_acct_fa_tax_depreciate():
        from accounting_waves_17 import run_tax_book_depreciation
        body = request.get_json(silent=True) or {}
        try:
            out = run_tax_book_depreciation(db, models, _ledger_id(), body.get('book') or 'TAX', user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/assets/<int:asset_id>/transfer', methods=['POST'])
    @login_required
    def api_acct_fa_transfer(asset_id):
        from accounting_waves_17 import transfer_fixed_asset
        try:
            out = transfer_fixed_asset(db, models, _ledger_id(), asset_id, request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/assets/mass-dispose', methods=['POST'])
    @login_required
    def api_acct_fa_mass_dispose():
        from accounting_waves_17 import mass_dispose_assets
        try:
            out = mass_dispose_assets(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    # --- Wave 8: production bridges ---

    @app.route('/pay-now/<token>')
    def pay_now_page(token):
        from flask import render_template
        return render_template('pay_now.html', token=token)

    @app.route('/api/accounting/payments/pay-now/<token>/checkout', methods=['GET'])
    def api_acct_pay_now_checkout(token):
        from accounting_waves_18 import pay_now_public_checkout
        try:
            return jsonify(pay_now_public_checkout(db, models, token))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payments/pay-now/<token>/complete', methods=['POST'])
    def api_acct_pay_now_complete_public(token):
        from accounting_waves_18 import pay_now_complete_card
        body = request.get_json(silent=True) or {}
        try:
            out = pay_now_complete_card(db, models, token, body.get('payment_intent_id', ''))
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/sage/sync/flush', methods=['POST'])
    @login_required
    def api_acct_sage_flush():
        from accounting_waves_18 import sage_flush_sync_queues
        out = sage_flush_sync_queues(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/payroll/wh347/<int:project_id>.pdf', methods=['GET'])
    @login_required
    def api_acct_wh347_pdf(project_id):
        from accounting_waves_18 import payroll_wh347_pdf_bytes
        from flask import Response
        we = request.args.get('week_ending') or date.today().isoformat()
        try:
            data = payroll_wh347_pdf_bytes(db, models, _ledger_id(), project_id, we)
            return Response(data, mimetype='application/pdf', headers={
                'Content-Disposition': f'attachment; filename=wh347-project-{project_id}.pdf',
            })
        except Exception as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/inventory/lot-receive', methods=['POST'])
    @login_required
    def api_acct_ic_lot_receive():
        from accounting_waves_18 import inventory_receive_with_lot
        try:
            out = inventory_receive_with_lot(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/oe/commissions/accrue', methods=['POST'])
    @login_required
    def api_acct_oe_commission_accrue():
        from accounting_waves_18 import post_oe_commission_accrual
        body = request.get_json(silent=True) or {}
        try:
            out = post_oe_commission_accrual(
                db, models, _ledger_id(), user_id=current_user.id,
                order_id=body.get('order_id'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/cron/run-scheduled-reports', methods=['POST'])
    def api_acct_cron_scheduled():
        from accounting_waves_18 import cron_run_scheduled_reports
        secret = request.headers.get('X-CasePM-Cron-Secret') or (request.get_json(silent=True) or {}).get('secret', '')
        try:
            out = cron_run_scheduled_reports(db, models, secret)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403

    # --- Wave 9: tiers A–D ---

    @app.route('/api/accounting/jobcost/<int:project_id>/g702-pending', methods=['GET'])
    @login_required
    def api_acct_g702_pending(project_id):
        from accounting_waves_19 import g702_pending_ar_sync
        if not PayAppProjectState:
            return jsonify({'error': 'Pay app module not available'}), 503
        return jsonify(g702_pending_ar_sync(db, models, _ledger_id(), project_id, PayAppProjectState))

    @app.route('/api/accounting/jobcost/<int:project_id>/g702-sync', methods=['POST'])
    @login_required
    def api_acct_g702_sync(project_id):
        from accounting_waves_19 import sync_g702_period_to_ar
        body = request.get_json(silent=True) or {}
        if not PayAppProjectState:
            return jsonify({'error': 'Pay app module not available'}), 503
        try:
            out = sync_g702_period_to_ar(
                db, models, _ledger_id(), project_id, body.get('period') or body.get('period_number'),
                user_id=current_user.id, PayAppProjectState=PayAppProjectState, Project=Project,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/sage/sync/push-open-ap-live', methods=['POST'])
    @login_required
    def api_acct_sage_push_ap_live():
        from accounting_waves_20 import sage_push_open_ap_with_error_log
        out = sage_push_open_ap_with_error_log(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/sage/conflicts/vendors', methods=['GET'])
    @login_required
    def api_acct_sage_conflicts():
        from accounting_waves_19 import sage_vendor_conflict_review
        return jsonify(sage_vendor_conflict_review(db, models, _ledger_id()))

    @app.route('/api/accounting/sage/conflicts/resolve', methods=['POST'])
    @login_required
    def api_acct_sage_conflict_resolve():
        from accounting_waves_19 import resolve_sage_vendor_conflict
        try:
            out = resolve_sage_vendor_conflict(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/integrations/stripe-banner', methods=['GET'])
    @login_required
    def api_acct_stripe_banner():
        from accounting_waves_19 import stripe_readiness_banner
        ledger = models['AcctLedger'].query.get(_ledger_id())
        return jsonify(stripe_readiness_banner(ledger))

    @app.route('/api/accounting/compliance/efile/transmit', methods=['POST'])
    @login_required
    def api_acct_efile_transmit():
        from accounting_waves_19 import efile_transmit
        out = efile_transmit(db, models, _ledger_id(), request.get_json(silent=True) or {}, user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/compliance/efile/log', methods=['GET'])
    @login_required
    def api_acct_efile_log():
        from accounting_waves_19 import efile_transmit_log
        return jsonify(efile_transmit_log(db, models, _ledger_id()))

    @app.route('/api/accounting/compliance/efile/retry/<entry_id>', methods=['POST'])
    @login_required
    def api_acct_efile_retry(entry_id):
        from accounting_waves_19 import efile_retry
        out = efile_retry(db, models, _ledger_id(), entry_id, user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/compliance/mark-filed', methods=['POST'])
    @login_required
    def api_acct_compliance_mark_filed():
        from accounting_waves_19 import compliance_mark_filed
        body = request.get_json(silent=True) or {}
        try:
            out = compliance_mark_filed(db, models, _ledger_id(), body['deadline_id'], user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except KeyError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/compliance/reminders', methods=['POST'])
    @login_required
    def api_acct_compliance_reminders():
        from accounting_waves_19 import compliance_send_reminders
        body = request.get_json(silent=True) or {}
        try:
            out = compliance_send_reminders(db, models, _ledger_id(), body.get('email', ''), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payroll/certified/<int:project_id>/prevailing', methods=['GET'])
    @login_required
    def api_acct_certified_prevailing(project_id):
        from accounting_waves_19 import certified_payroll_with_prevailing
        we = request.args.get('week_ending') or date.today().isoformat()
        return jsonify(certified_payroll_with_prevailing(db, models, _ledger_id(), project_id, we, Project=Project))

    @app.route('/api/accounting/ar/write-off', methods=['POST'])
    @login_required
    def api_acct_ar_write_off():
        from accounting_waves_19 import post_ar_write_off, WRITE_OFF_REASONS
        body = request.get_json(silent=True) or {}
        try:
            out = post_ar_write_off(db, models, _ledger_id(), body, user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, 'reasons': list(WRITE_OFF_REASONS), **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/reports/designer/columns', methods=['GET'])
    @login_required
    def api_acct_report_columns():
        from accounting_waves_20 import report_designer_column_catalog
        return jsonify(report_designer_column_catalog())

    @app.route('/api/accounting/reports/schedule-alerts', methods=['GET'])
    @login_required
    def api_acct_schedule_alerts():
        ledger = models['AcctLedger'].query.get(_ledger_id())
        from accounting_gl_service import _parse_settings
        return jsonify({'alerts': (_parse_settings(ledger).get('report_schedule_alerts') or [])})

    # --- Wave 10 ---

    @app.route('/api/accounting/jobcost/<int:project_id>/g702-sync-all', methods=['POST'])
    @login_required
    def api_acct_g702_sync_all(project_id):
        from accounting_waves_20 import sync_all_g702_pending_to_ar
        if not PayAppProjectState:
            return jsonify({'error': 'Pay app module not available'}), 503
        try:
            out = sync_all_g702_pending_to_ar(
                db, models, _ledger_id(), project_id,
                user_id=current_user.id, PayAppProjectState=PayAppProjectState, Project=Project,
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except Exception as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/jobcost/<int:project_id>/variance', methods=['GET'])
    @login_required
    def api_acct_jobcost_variance(project_id):
        from accounting_waves_20 import jobcost_variance_breakdown
        if not PayAppProjectState:
            return jsonify({'error': 'Pay app module not available'}), 503
        return jsonify(jobcost_variance_breakdown(db, models, _ledger_id(), project_id, PayAppProjectState))

    @app.route('/api/accounting/sage/conflicts/gl', methods=['GET'])
    @login_required
    def api_acct_sage_gl_conflicts():
        from accounting_waves_20 import sage_gl_account_conflict_review
        return jsonify(sage_gl_account_conflict_review(db, models, _ledger_id()))

    @app.route('/api/accounting/program-settings/sor-summary', methods=['GET'])
    @login_required
    def api_acct_sor_summary():
        from accounting_waves_20 import program_settings_sor_summary
        return jsonify(program_settings_sor_summary(db, models, _ledger_id()))

    @app.route('/api/accounting/compliance/efile/dashboard', methods=['GET'])
    @login_required
    def api_acct_efile_dashboard():
        from accounting_waves_20 import efile_status_dashboard
        return jsonify(efile_status_dashboard(db, models, _ledger_id()))

    @app.route('/api/accounting/payroll/certified/<int:project_id>/prevailing-daily', methods=['GET'])
    @login_required
    def api_acct_certified_prevailing_daily(project_id):
        from accounting_waves_20 import certified_payroll_prevailing_daily_log
        we = request.args.get('week_ending') or date.today().isoformat()
        return jsonify(certified_payroll_prevailing_daily_log(db, models, _ledger_id(), project_id, we, Project=Project))

    @app.route('/api/accounting/cron/wave10', methods=['POST'])
    def api_acct_cron_wave10():
        from accounting_waves_20 import cron_wave10_maintenance
        secret = request.headers.get('X-CasePM-Cron-Secret') or (request.get_json(silent=True) or {}).get('secret', '')
        try:
            out = cron_wave10_maintenance(db, models, secret)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403

    # --- Wave 11 ---

    def _commitment_models():
        import app as app_mod
        return app_mod.Commitment, app_mod.CommitmentAllocation

    @app.route('/api/accounting/jobcost/<int:project_id>/sub-ap-pending', methods=['GET'])
    @login_required
    def api_acct_sub_ap_pending(project_id):
        from accounting_waves_21 import sub_pay_app_pending_ap_sync
        if not PayAppProjectState:
            return jsonify({'error': 'Pay app module not available'}), 503
        return jsonify(sub_pay_app_pending_ap_sync(db, models, _ledger_id(), project_id, PayAppProjectState))

    @app.route('/api/accounting/jobcost/<int:project_id>/sub-ap-sync-all', methods=['POST'])
    @login_required
    def api_acct_sub_ap_sync_all(project_id):
        from accounting_waves_21 import sync_all_sub_pay_apps_pending_to_ap
        Commitment, _ = _commitment_models()
        if not PayAppProjectState:
            return jsonify({'error': 'Pay app module not available'}), 503
        try:
            out = sync_all_sub_pay_apps_pending_to_ap(
                db, models, _ledger_id(), project_id, user_id=current_user.id,
                PayAppProjectState=PayAppProjectState, Commitment=Commitment,
                Project=Project, Company=deps.get('Company'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except Exception as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/jobcost/<int:project_id>/commitments-pending', methods=['GET'])
    @login_required
    def api_acct_commitments_pending(project_id):
        from accounting_waves_21 import commitment_pending_accounting
        Commitment, _ = _commitment_models()
        return jsonify(commitment_pending_accounting(db, models, _ledger_id(), project_id, Commitment))

    @app.route('/api/accounting/jobcost/<int:project_id>/commitments-sync-all', methods=['POST'])
    @login_required
    def api_acct_commitments_sync_all(project_id):
        from accounting_waves_21 import sync_all_commitments_pending
        Commitment, CommitmentAllocation = _commitment_models()
        try:
            out = sync_all_commitments_pending(
                db, models, _ledger_id(), project_id, user_id=current_user.id,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                Project=Project, Company=deps.get('Company'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except Exception as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/commitments/<int:commitment_id>/accounting-sync', methods=['POST'])
    @login_required
    def api_acct_commitment_sync(commitment_id):
        from accounting_waves_21 import sync_commitment_to_accounting
        Commitment, CommitmentAllocation = _commitment_models()
        try:
            out = sync_commitment_to_accounting(
                db, models, _ledger_id(), commitment_id, user_id=current_user.id,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                Project=Project, Company=deps.get('Company'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/commitments/change-order/post', methods=['POST'])
    @login_required
    def api_acct_cco_post():
        from accounting_waves_21 import post_commitment_change_order
        Commitment, _ = _commitment_models()
        try:
            out = post_commitment_change_order(
                db, models, _ledger_id(), request.get_json(silent=True) or {},
                user_id=current_user.id, Commitment=Commitment, Project=Project, Company=deps.get('Company'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/jobcost/<int:project_id>/wip', methods=['GET'])
    @login_required
    def api_acct_jobcost_wip(project_id):
        from accounting_waves_21 import jobcost_wip_analysis
        return jsonify(jobcost_wip_analysis(db, models, _ledger_id(), project_id, PayAppProjectState))

    @app.route('/api/accounting/jobcost/<int:project_id>/wip-adjust', methods=['POST'])
    @login_required
    def api_acct_jobcost_wip_adjust(project_id):
        from accounting_waves_21 import post_wip_billing_adjustment
        body = request.get_json(silent=True) or {}
        try:
            out = post_wip_billing_adjustment(
                db, models, _ledger_id(), project_id, user_id=current_user.id,
                amount=body.get('amount'),
            )
            db.session.commit()
            return jsonify({'ok': True, **out})
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/payments/exceptions', methods=['GET'])
    @login_required
    def api_acct_payment_exceptions():
        from accounting_waves_21 import payment_exception_inbox
        return jsonify(payment_exception_inbox(db, models, _ledger_id()))

    @app.route('/api/accounting/payments/exceptions/reconcile', methods=['POST'])
    @login_required
    def api_acct_payment_exceptions_reconcile():
        from accounting_waves_21 import reconcile_pay_now_exceptions
        out = reconcile_pay_now_exceptions(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/bank/plaid-auto-import', methods=['POST'])
    @login_required
    def api_acct_plaid_auto_import():
        from accounting_waves_21 import plaid_auto_import_for_ledger
        try:
            out = plaid_auto_import_for_ledger(db, models, _ledger_id(), user_id=current_user.id)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except (ValueError, KeyError) as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/accounting/sage/sync/pull-open-ap', methods=['POST'])
    @login_required
    def api_acct_sage_pull_open_ap():
        from accounting_waves_21 import sage_pull_open_ap
        out = sage_pull_open_ap(db, models, _ledger_id(), user_id=current_user.id)
        db.session.commit()
        return jsonify({'ok': True, **out})

    @app.route('/api/accounting/sage/exceptions', methods=['GET'])
    @login_required
    def api_acct_sage_exceptions():
        from accounting_waves_21 import sage_hybrid_exception_inbox
        return jsonify(sage_hybrid_exception_inbox(db, models, _ledger_id()))

    @app.route('/api/accounting/cron/wave11', methods=['POST'])
    def api_acct_cron_wave11():
        from accounting_waves_21 import cron_wave11_maintenance
        secret = request.headers.get('X-CasePM-Cron-Secret') or (request.get_json(silent=True) or {}).get('secret', '')
        try:
            out = cron_wave11_maintenance(db, models, secret)
            db.session.commit()
            return jsonify({'ok': True, **out})
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
