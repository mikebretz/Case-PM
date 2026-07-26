"""Operations Center — unified hub for extended platform modules."""


def register_extended_platform_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps['get_current_project_id']
    generate_next_number = deps.get('generate_next_number')
    jsonify = deps['jsonify']
    request = deps['request']
    render_template = deps['render_template']
    get_active_project = deps['get_active_project']
    ExtendedModuleRecord = deps['ExtendedModuleRecord']
    Project = deps['Project']
    Commitment = deps['Commitment']
    CommitmentAllocation = deps['CommitmentAllocation']
    ChangeOrder = deps['ChangeOrder']
    BudgetProjectState = deps['BudgetProjectState']
    PayAppProjectState = deps['PayAppProjectState']
    RFI = deps.get('RFI')
    ChangeEvent = deps.get('ChangeEvent')

    @app.route('/operations')
    @login_required
    def operations_center_page():
        return render_template('operations_center.html', active_project=get_active_project())

    @app.route('/api/operations/catalog')
    @login_required
    def api_operations_catalog():
        from extended_platform_persistence import catalog_for_ui
        return jsonify({'categories': catalog_for_ui()})

    @app.route('/api/operations/wip')
    @login_required
    def api_operations_wip():
        from extended_platform_persistence import build_wip_snapshot, build_portfolio_wip
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        if project_id:
            snap = build_wip_snapshot(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState, project_id)
            return jsonify({'wip': snap})
        return jsonify(build_portfolio_wip(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState))

    @app.route('/api/operations/<module_key>', methods=['GET'])
    @login_required
    def api_operations_list(module_key):
        from extended_platform_persistence import (
            MODULE_SCHEMAS, compute_stats, serialize_record,
        )
        if module_key not in MODULE_SCHEMAS:
            return jsonify({'error': 'Unknown module'}), 404
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        schema = MODULE_SCHEMAS[module_key]
        q = ExtendedModuleRecord.query.filter_by(module_key=module_key)
        if schema.get('project_scoped', True) and project_id:
            q = q.filter_by(project_id=int(project_id))
        rows = q.order_by(ExtendedModuleRecord.updated_at.desc()).all()
        stats = compute_stats(ExtendedModuleRecord, module_key, project_id if schema.get('project_scoped') else None)
        return jsonify({
            'records': [serialize_record(r) for r in rows],
            'stats': stats,
            'schema': {
                'simple': schema.get('simple', []),
                'advanced': schema.get('advanced', []),
                'statuses': list(schema.get('statuses', ('Draft',))),
            },
        })

    @app.route('/api/operations/<module_key>', methods=['POST'])
    @login_required
    def api_operations_create(module_key):
        from extended_platform_persistence import MODULE_SCHEMAS, apply_payload, serialize_record
        if module_key not in MODULE_SCHEMAS:
            return jsonify({'error': 'Unknown module'}), 404
        body = request.get_json(silent=True) or {}
        schema = MODULE_SCHEMAS[module_key]
        project_id = body.get('project_id') or get_current_project_id()
        row = ExtendedModuleRecord(
            module_key=module_key,
            project_id=int(project_id) if schema.get('project_scoped') and project_id else None,
            company_id=body.get('company_id'),
            title=(body.get('title') or 'New item').strip(),
            status=body.get('status') or 'Draft',
            created_by_id=current_user.id,
        )
        apply_payload(row, body, module_key)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'record': serialize_record(row)})

    @app.route('/api/operations/<module_key>/<int:record_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def api_operations_record(module_key, record_id):
        from extended_platform_persistence import (
            MODULE_SCHEMAS, apply_payload, serialize_record,
            validate_vendor_invoice, generate_ai_insight,
            promote_correspondence_to_rfi, promote_tm_to_change_event,
        )
        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key=module_key).first_or_404()
        if request.method == 'GET':
            payload = {'record': serialize_record(row)}
            if module_key == 'vendor_invoices' and row.project_id:
                payload['validation'] = validate_vendor_invoice(
                    row, Commitment, CommitmentAllocation, row.project_id,
                )
            return jsonify(payload)
        if request.method == 'DELETE':
            db.session.delete(row)
            db.session.commit()
            return jsonify({'ok': True})
        body = request.get_json(silent=True) or {}
        apply_payload(row, body, module_key)
        db.session.commit()
        return jsonify({'ok': True, 'record': serialize_record(row)})

    @app.route('/api/operations/<module_key>/<int:record_id>/action', methods=['POST'])
    @login_required
    def api_operations_action(module_key, record_id):
        from extended_platform_persistence import (
            serialize_record, validate_vendor_invoice,
            generate_ai_insight, promote_correspondence_to_rfi, promote_tm_to_change_event,
        )
        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key=module_key).first_or_404()
        body = request.get_json(silent=True) or {}
        action = (body.get('action') or '').lower()
        result = {'ok': True}

        if action == 'validate_invoice' and module_key == 'vendor_invoices':
            result['validation'] = validate_vendor_invoice(
                row, Commitment, CommitmentAllocation, row.project_id,
            )
        elif action == 'promote_rfi' and module_key == 'correspondence' and RFI and generate_next_number:
            rfi = promote_correspondence_to_rfi(
                row, RFI, db, row.project_id, current_user.id, generate_next_number,
            )
            db.session.commit()
            result['rfi_id'] = rfi.id
            result['rfi_number'] = rfi.number
        elif action == 'promote_change_event' and module_key == 'tm_tickets' and ChangeEvent:
            ce = promote_tm_to_change_event(row, ChangeEvent, db, row.project_id, current_user.id)
            db.session.commit()
            result['change_event_id'] = ce.id
            result['change_event_number'] = ce.number
        elif action == 'ai_ask' and module_key == 'ai_insights':
            question = body.get('question') or row.title
            response = generate_ai_insight(
                row.project_id, module_key, question, Project, ExtendedModuleRecord, RFI, ChangeOrder,
            )
            from extended_platform_persistence import apply_payload as _apply
            _apply(row, {
                'advanced': {'prompt': question, 'response': response},
                'status': 'Answered',
            }, module_key)
            db.session.commit()
            result['response'] = response
        elif action == 'post_timesheet' and module_key == 'timesheets':
            row.status = 'Posted'
            db.session.commit()
            result['message'] = 'Timesheet marked posted — sync to job cost via Sage reconcile.'
        elif action == 'process_payment' and module_key == 'payment_batches':
            row.status = 'Processed'
            db.session.commit()
            result['message'] = 'Payment batch marked processed.'
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400

        result['record'] = serialize_record(row)
        return jsonify(result)
