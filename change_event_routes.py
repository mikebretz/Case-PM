"""Change Events, RFQ, COR, CPCO, and ERP accounting queue API routes."""


def register_change_event_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps['get_current_project_id']
    generate_next_number = deps['generate_next_number']
    ChangeEvent = deps['ChangeEvent']
    SubcontractorRFQ = deps['SubcontractorRFQ']
    RFQAllocation = deps['RFQAllocation']
    ChangeOrderRequest = deps['ChangeOrderRequest']
    CORAllocation = deps['CORAllocation']
    PotentialChangeOrder = deps['PotentialChangeOrder']
    PCOAllocation = deps['PCOAllocation']
    ChangeOrder = deps['ChangeOrder']
    ChangeOrderAllocation = deps['ChangeOrderAllocation']
    SageSyncEvent = deps['SageSyncEvent']
    Project = deps['Project']
    BudgetProjectState = deps['BudgetProjectState']
    ScheduleData = deps['ScheduleData']
    Commitment = deps['Commitment']
    PayAppProjectState = deps['PayAppProjectState']

    @app.route('/api/change-events', methods=['GET'])
    @login_required
    def api_list_change_events():
        from change_event_persistence import change_event_to_dict
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        events = ChangeEvent.query.filter_by(project_id=int(project_id)).order_by(ChangeEvent.created_at.desc()).all()
        return deps['jsonify']({'change_events': [change_event_to_dict(e) for e in events]})

    @app.route('/api/change-events/<int:event_id>', methods=['GET'])
    @login_required
    def api_get_change_event(event_id):
        from change_event_persistence import change_event_to_dict, rfq_to_dict, cor_to_dict
        from co_persistence import pco_to_dict, is_subcontract_co
        ce = ChangeEvent.query.get_or_404(event_id)
        rfqs = SubcontractorRFQ.query.filter_by(change_event_id=ce.id).all()
        rfq_payload = []
        for r in rfqs:
            allocs = RFQAllocation.query.filter_by(rfq_id=r.id).all()
            rfq_payload.append(rfq_to_dict(r, allocs))
        cors = ChangeOrderRequest.query.filter_by(change_event_id=ce.id).all()
        cor_payload = []
        for c in cors:
            allocs = CORAllocation.query.filter_by(cor_id=c.id).all()
            cor_payload.append(cor_to_dict(c, allocs))
        pcos = PotentialChangeOrder.query.filter_by(change_event_id=ce.id).all()
        pco_payload = []
        for p in pcos:
            ctype = getattr(p, 'contract_type', None) or 'Owner'
            if ctype == 'Subcontract':
                continue
            allocs = PCOAllocation.query.filter_by(pco_id=p.id).all()
            pco_payload.append(pco_to_dict(p, allocs))
        payload = change_event_to_dict(ce, rfqs=rfq_payload, pcos=pco_payload, cors=cor_payload)
        return deps['jsonify'](payload)

    @app.route('/api/change-events', methods=['POST'])
    @login_required
    def api_create_change_event():
        from change_event_persistence import apply_change_event_fields, change_event_to_dict
        from sage_service import create_and_process_sage_event
        body = deps['request'].get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        ce = ChangeEvent(
            project_id=int(project_id),
            number=generate_next_number('CE', ChangeEvent, doc_type='change_event', project_id=int(project_id)),
            title=body.get('title') or 'Change Event',
            status='Open',
            ball_in_court_role='Project Manager',
            created_by_id=current_user.id,
        )
        apply_change_event_fields(ce, body)
        db.session.add(ce)
        db.session.commit()
        create_and_process_sage_event(
            SageSyncEvent, Project, db, ce.project_id,
            'ChangeEventCreated',
            message=f'Change Event {ce.number} created',
            payload={'change_event_id': ce.id, 'rom_amount': ce.rom_amount},
            user_id=current_user.id,
            auto_process=True,
        )
        return deps['jsonify']({'ok': True, 'change_event': change_event_to_dict(ce)})

    @app.route('/api/change-events/<int:event_id>', methods=['PUT'])
    @login_required
    def api_update_change_event(event_id):
        from change_event_persistence import apply_change_event_fields, change_event_to_dict, apply_contingency_release, apply_partial_budget_line, link_change_event_schedule_impact
        ce = ChangeEvent.query.get_or_404(event_id)
        body = deps['request'].get_json(silent=True) or {}
        old_status = ce.status
        apply_change_event_fields(ce, body)
        if body.get('allocations'):
            for row in body['allocations']:
                apply_partial_budget_line(
                    BudgetProjectState, ce.project_id,
                    row.get('cost_code'), row.get('cost_type'), row.get('amount'),
                    row.get('description'), db,
                )
        if ce.status == 'Approved' and old_status != 'Approved':
            if float(getattr(ce, 'contingency_release_amount', 0) or 0):
                apply_contingency_release(BudgetProjectState, ce.project_id, ce.contingency_release_amount, db)
            link_change_event_schedule_impact(ScheduleData, Project, db, ce.project_id, ce)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'change_event': change_event_to_dict(ce)})

    @app.route('/api/change-events/<int:event_id>/workflow', methods=['POST'])
    @login_required
    def api_change_event_workflow(event_id):
        from change_event_persistence import (
            change_event_workflow_action, change_event_to_dict,
            apply_contingency_release, link_change_event_schedule_impact,
        )
        from sage_service import create_and_process_sage_event
        ce = ChangeEvent.query.get_or_404(event_id)
        body = deps['request'].get_json(silent=True) or {}
        action = body.get('action')
        old_status = ce.status
        try:
            new_status, final = change_event_workflow_action(ce, action, current_user)
        except ValueError as exc:
            return deps['jsonify']({'error': str(exc)}), 400
        if final and ce.status == 'Approved' and old_status != 'Approved':
            if float(getattr(ce, 'contingency_release_amount', 0) or 0):
                apply_contingency_release(BudgetProjectState, ce.project_id, ce.contingency_release_amount, db)
            link_change_event_schedule_impact(ScheduleData, Project, db, ce.project_id, ce)
            create_and_process_sage_event(
                SageSyncEvent, Project, db, ce.project_id,
                'ChangeEventCreated',
                message=f'Change Event {ce.number} approved',
                payload={'change_event_id': ce.id, 'rom_amount': ce.rom_amount, 'approved': True},
                user_id=current_user.id,
            )
        db.session.commit()
        return deps['jsonify']({'ok': True, 'new_status': new_status, 'final': final, 'change_event': change_event_to_dict(ce)})

    @app.route('/api/rfqs', methods=['GET'])
    @login_required
    def api_list_rfqs():
        from change_event_persistence import rfq_to_dict
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        rfqs = SubcontractorRFQ.query.filter_by(project_id=int(project_id)).order_by(SubcontractorRFQ.created_at.desc()).all()
        result = []
        for r in rfqs:
            allocs = RFQAllocation.query.filter_by(rfq_id=r.id).all()
            result.append(rfq_to_dict(r, allocs))
        return deps['jsonify']({'rfqs': result})

    @app.route('/api/rfqs', methods=['POST'])
    @login_required
    def api_create_rfq():
        from change_event_persistence import apply_rfq_fields, rfq_to_dict, save_generic_allocations
        body = deps['request'].get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        rfq = SubcontractorRFQ(
            project_id=int(project_id),
            number=generate_next_number('RFQ', SubcontractorRFQ, doc_type='rfq', project_id=int(project_id)),
            title=body.get('title') or 'Subcontractor RFQ',
            status='Draft',
            ball_in_court_role='Creator',
            created_by_id=current_user.id,
        )
        apply_rfq_fields(rfq, body)
        db.session.add(rfq)
        db.session.flush()
        if body.get('allocations'):
            save_generic_allocations(RFQAllocation, 'rfq_id', rfq.id, body['allocations'], db)
        db.session.commit()
        allocs = RFQAllocation.query.filter_by(rfq_id=rfq.id).all()
        return deps['jsonify']({'ok': True, 'rfq': rfq_to_dict(rfq, allocs)})

    @app.route('/api/rfqs/<int:rfq_id>', methods=['PUT'])
    @login_required
    def api_update_rfq(rfq_id):
        from change_event_persistence import apply_rfq_fields, rfq_to_dict, save_generic_allocations
        rfq = SubcontractorRFQ.query.get_or_404(rfq_id)
        body = deps['request'].get_json(silent=True) or {}
        apply_rfq_fields(rfq, body)
        if body.get('allocations') is not None:
            save_generic_allocations(RFQAllocation, 'rfq_id', rfq.id, body['allocations'], db)
        db.session.commit()
        allocs = RFQAllocation.query.filter_by(rfq_id=rfq.id).all()
        return deps['jsonify']({'ok': True, 'rfq': rfq_to_dict(rfq, allocs)})

    @app.route('/api/rfqs/<int:rfq_id>/workflow', methods=['POST'])
    @login_required
    def api_rfq_workflow(rfq_id):
        from change_event_persistence import rfq_workflow_action, rfq_to_dict, notify_rfq_subcontractor, promote_rfq_to_cpco
        from sage_service import create_and_process_sage_event
        rfq = SubcontractorRFQ.query.get_or_404(rfq_id)
        body = deps['request'].get_json(silent=True) or {}
        action = body.get('action')
        allocs = RFQAllocation.query.filter_by(rfq_id=rfq.id).all()
        alloc_payload = [{
            'cost_code': a.cost_code,
            'cost_type': a.cost_type,
            'amount': a.amount,
            'quoted_amount': getattr(a, 'quoted_amount', 0) or a.amount,
            'description': a.description,
            'sov_line_id': getattr(a, 'sov_line_id', None),
            'tax_group': getattr(a, 'tax_group', None),
        } for a in allocs]
        if action == 'quote' and body.get('allocations'):
            save_from = body['allocations']
            from change_event_persistence import save_generic_allocations
            save_generic_allocations(RFQAllocation, 'rfq_id', rfq.id, save_from, db)
            alloc_payload = save_from
        try:
            new_status, final = rfq_workflow_action(rfq, action, current_user, alloc_payload)
        except ValueError as exc:
            return deps['jsonify']({'error': str(exc)}), 400
        cpco = None
        if action == 'send':
            notify_rfq_subcontractor(rfq.project_id, rfq, deps['User'])
            create_and_process_sage_event(
                SageSyncEvent, Project, db, rfq.project_id,
                'RFQSubmitted', message=f'{rfq.number} sent to subcontractor',
                payload={'rfq_id': rfq.id, 'company_id': rfq.company_id},
                user_id=current_user.id,
            )
        if action == 'quote':
            create_and_process_sage_event(
                SageSyncEvent, Project, db, rfq.project_id,
                'RFQQuoted', message=f'{rfq.number} quoted',
                payload={'rfq_id': rfq.id, 'quoted_amount': rfq.quoted_amount},
                user_id=current_user.id,
            )
        if final and body.get('promote_cpco'):
            allocs = RFQAllocation.query.filter_by(rfq_id=rfq.id).all()
            cpco = promote_rfq_to_cpco(
                rfq, allocs, PotentialChangeOrder, PCOAllocation, db, generate_next_number, current_user.id,
            )
            create_and_process_sage_event(
                SageSyncEvent, Project, db, rfq.project_id,
                'CPCOSubmitted', message=f'CPCO {cpco.number} from RFQ {rfq.number}',
                payload={'pco_id': cpco.id, 'rfq_id': rfq.id, 'commitment_type': 'Subcontract'},
                user_id=current_user.id,
            )
        db.session.commit()
        allocs = RFQAllocation.query.filter_by(rfq_id=rfq.id).all()
        out = {'ok': True, 'new_status': new_status, 'rfq': rfq_to_dict(rfq, allocs)}
        if cpco:
            from co_persistence import pco_to_dict
            out['cpco'] = pco_to_dict(cpco, PCOAllocation.query.filter_by(pco_id=cpco.id).all())
        return deps['jsonify'](out)

    @app.route('/api/rfqs/<int:rfq_id>/portal-quote', methods=['POST'])
    @login_required
    def api_rfq_portal_quote(rfq_id):
        """Subcontractor portal — submit quote for an RFQ sent to their company."""
        from change_event_persistence import rfq_workflow_action, rfq_to_dict, save_generic_allocations
        from sage_service import create_and_process_sage_event
        rfq = SubcontractorRFQ.query.get_or_404(rfq_id)
        body = deps['request'].get_json(silent=True) or {}
        portal = deps.get('user_portal_type_fn')
        is_sub = portal(current_user) == 'sub' if portal else current_user.role in ('Company User', 'Subcontractor Accountant')
        if is_sub and rfq.company_id and str(getattr(current_user, 'company_id', '')) != str(rfq.company_id):
            if getattr(current_user, 'company', '') != (rfq.company_name or ''):
                return deps['jsonify']({'error': 'This RFQ is not assigned to your company.'}), 403
        if rfq.status not in ('Sent', 'Draft'):
            return deps['jsonify']({'error': 'RFQ is not open for quoting.'}), 400
        allocs = body.get('allocations') or []
        if not allocs:
            amt = float(body.get('quoted_amount') or body.get('amount') or 0)
            if amt <= 0:
                return deps['jsonify']({'error': 'Quote amount is required.'}), 400
            allocs = [{'cost_code': body.get('cost_code') or '01-0000', 'cost_type': 'Subcontract', 'amount': amt, 'quoted_amount': amt}]
        try:
            new_status, _final = rfq_workflow_action(rfq, 'quote', current_user, allocs)
        except ValueError as exc:
            return deps['jsonify']({'error': str(exc)}), 400
        save_generic_allocations(RFQAllocation, 'rfq_id', rfq.id, allocs, db)
        create_and_process_sage_event(
            SageSyncEvent, Project, db, rfq.project_id,
            'RFQQuoted', message=f'{rfq.number} quoted via portal',
            payload={'rfq_id': rfq.id, 'quoted_amount': rfq.quoted_amount, 'portal': True},
            user_id=current_user.id,
        )
        db.session.commit()
        saved = RFQAllocation.query.filter_by(rfq_id=rfq.id).all()
        return deps['jsonify']({'ok': True, 'new_status': new_status, 'rfq': rfq_to_dict(rfq, saved)})

    @app.route('/api/cors', methods=['GET'])
    @login_required
    def api_list_cors():
        from change_event_persistence import cor_to_dict
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        cors = ChangeOrderRequest.query.filter_by(project_id=int(project_id)).order_by(ChangeOrderRequest.created_at.desc()).all()
        result = []
        for c in cors:
            allocs = CORAllocation.query.filter_by(cor_id=c.id).all()
            result.append(cor_to_dict(c, allocs))
        return deps['jsonify']({'cors': result})

    @app.route('/api/cors', methods=['POST'])
    @login_required
    def api_create_cor():
        from change_event_persistence import apply_cor_fields, cor_to_dict, save_generic_allocations
        body = deps['request'].get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        cor = ChangeOrderRequest(
            project_id=int(project_id),
            number=generate_next_number('COR', ChangeOrderRequest, doc_type='cor', project_id=int(project_id)),
            title=body.get('title') or 'Change Order Request',
            status='Draft',
            ball_in_court_role='Creator',
            created_by_id=current_user.id,
        )
        apply_cor_fields(cor, body)
        db.session.add(cor)
        db.session.flush()
        if body.get('allocations'):
            save_generic_allocations(CORAllocation, 'cor_id', cor.id, body['allocations'], db)
            cor.amount = sum(float(a.get('amount') or 0) for a in body['allocations'])
        db.session.commit()
        allocs = CORAllocation.query.filter_by(cor_id=cor.id).all()
        return deps['jsonify']({'ok': True, 'cor': cor_to_dict(cor, allocs)})

    @app.route('/api/cors/<int:cor_id>/workflow', methods=['POST'])
    @login_required
    def api_cor_workflow(cor_id):
        from change_event_persistence import cor_workflow_action, cor_to_dict, promote_cor_to_pco, link_change_event_schedule_impact
        from sage_service import create_and_process_sage_event
        from financial_security import require_financial_project_access
        cor = ChangeOrderRequest.query.get_or_404(cor_id)
        try:
            require_financial_project_access(current_user, cor.project_id, Project)
        except (ValueError, PermissionError) as exc:
            return deps['jsonify']({'error': str(exc)}), 403
        body = deps['request'].get_json(silent=True) or {}
        action = body.get('action')
        try:
            new_status, final = cor_workflow_action(
                cor, action, current_user, body=body,
                ChangeOrderRequest=ChangeOrderRequest,
                CORAllocation=CORAllocation,
            )
        except ValueError as exc:
            return deps['jsonify']({'error': str(exc)}), 400
        pco = None
        if action == 'submit':
            create_and_process_sage_event(
                SageSyncEvent, Project, db, cor.project_id,
                'CORSubmitted', message=f'{cor.number} submitted',
                payload={'cor_id': cor.id, 'amount': cor.amount},
                user_id=current_user.id,
            )
        if final:
            create_and_process_sage_event(
                SageSyncEvent, Project, db, cor.project_id,
                'CORApproved', message=f'{cor.number} approved',
                payload={'cor_id': cor.id, 'amount': cor.amount},
                user_id=current_user.id,
            )
            if getattr(cor, 'change_event_id', None):
                ce = ChangeEvent.query.get(cor.change_event_id)
                if ce:
                    link_change_event_schedule_impact(ScheduleData, Project, db, cor.project_id, ce, cor.number)
            if body.get('promote_pco'):
                allocs = CORAllocation.query.filter_by(cor_id=cor.id).all()
                pco = promote_cor_to_pco(cor, allocs, PotentialChangeOrder, PCOAllocation, db, generate_next_number, current_user.id)
        db.session.commit()
        allocs = CORAllocation.query.filter_by(cor_id=cor.id).all()
        out = {'ok': True, 'new_status': new_status, 'cor': cor_to_dict(cor, allocs)}
        if pco:
            from co_persistence import pco_to_dict
            out['pco'] = pco_to_dict(pco, PCOAllocation.query.filter_by(pco_id=pco.id).all())
        return deps['jsonify'](out)

    @app.route('/api/pcos/<int:pco_id>/promote-cpco', methods=['POST'])
    @login_required
    def api_promote_cpco_route(pco_id):
        from change_event_persistence import promote_cpco_to_sco
        from co_persistence import co_to_dict, pco_to_dict
        from sage_service import create_and_process_sage_event
        pco = PotentialChangeOrder.query.get_or_404(pco_id)
        if (getattr(pco, 'contract_type', None) or 'Owner') != 'Subcontract':
            return deps['jsonify']({'error': 'Not a commitment PCO'}), 400
        allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
        try:
            sco = promote_cpco_to_sco(
                pco, allocs, ChangeOrder, ChangeOrderAllocation, db,
                generate_next_number, current_user.id, SubcontractorRFQ=SubcontractorRFQ,
            )
            create_and_process_sage_event(
                SageSyncEvent, Project, db, sco.project_id,
                'CPCOPromoted',
                message=f'CPCO {pco.number} promoted to {sco.number}',
                payload={'pco_id': pco.id, 'change_order_id': sco.id, 'commitment_type': 'Subcontract'},
                user_id=current_user.id,
            )
            db.session.commit()
            sco_allocs = ChangeOrderAllocation.query.filter_by(change_order_id=sco.id).all()
            return deps['jsonify']({
                'ok': True,
                'change_order': co_to_dict(sco, sco_allocs),
                'cpco': pco_to_dict(pco, allocs),
            })
        except ValueError as exc:
            db.session.rollback()
            return deps['jsonify']({'error': str(exc)}), 400

    @app.route('/api/sage/sync-events/<int:event_id>/accounting', methods=['POST'])
    @login_required
    def api_sage_accounting_review(event_id):
        from change_event_persistence import accept_sage_event_for_export, reject_sage_event, sage_event_to_dict
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return deps['jsonify']({'error': str(exc)}), 403
        event = SageSyncEvent.query.get_or_404(event_id)
        body = deps['request'].get_json(silent=True) or {}
        action = (body.get('action') or '').lower()
        if action == 'accept':
            accept_sage_event_for_export(event, current_user, db, Commitment=Commitment)
        elif action == 'reject':
            reject_sage_event(event, current_user, body.get('notes') or body.get('comments') or '')
        else:
            return deps['jsonify']({'error': 'action must be accept or reject'}), 400
        db.session.commit()
        return deps['jsonify']({'ok': True, 'event': sage_event_to_dict(event)})

    @app.route('/api/change-orders/billing-variance', methods=['GET'])
    @login_required
    def api_co_billing_variance():
        from change_event_persistence import compute_billing_variance_for_sub_cos
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        cos = ChangeOrder.query.filter_by(project_id=int(project_id)).all()
        rows = compute_billing_variance_for_sub_cos(cos, PayAppProjectState, int(project_id))
        return deps['jsonify']({'variances': rows})

    @app.route('/api/change-orders/sub-sov-lines', methods=['GET'])
    @login_required
    def api_sub_sov_lines_for_co():
        from pay_app_persistence import get_pay_app_state, normalize_sub_sov_keys
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        company_id = deps['request'].args.get('company_id')
        company_name = deps['request'].args.get('company_name')
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        _, state = get_pay_app_state(PayAppProjectState, int(project_id))
        sub_sov = normalize_sub_sov_keys(state.get('subcontractorSOV') or {})
        lines = []
        for key, rows in sub_sov.items():
            if company_id and str(key) != str(company_id) and (not company_name or key != company_name):
                continue
            for line in rows or []:
                lines.append({
                    'company_key': key,
                    'id': line.get('id'),
                    'cost_code': line.get('cost_code'),
                    'description': line.get('description'),
                    'scheduled_value': line.get('scheduled_value'),
                })
        return deps['jsonify']({'lines': lines})
