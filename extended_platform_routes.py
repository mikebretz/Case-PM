"""Operations Center — unified hub for extended platform modules."""
import os

from flask import send_file


def register_extended_platform_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps.get('get_current_project_id')
    generate_next_number = deps.get('generate_next_number')
    jsonify = deps['jsonify']
    request = deps['request']
    render_template = deps['render_template']
    get_active_project = deps['get_active_project']
    ExtendedModuleRecord = deps['ExtendedModuleRecord']
    OperationsAiMessage = deps['OperationsAiMessage']
    OperationsPaymentLine = deps['OperationsPaymentLine']
    OperationsReportRun = deps['OperationsReportRun']
    OperationsBimAsset = deps['OperationsBimAsset']
    Project = deps['Project']
    Commitment = deps['Commitment']
    CommitmentAllocation = deps['CommitmentAllocation']
    ChangeOrder = deps['ChangeOrder']
    BudgetProjectState = deps['BudgetProjectState']
    PayAppProjectState = deps['PayAppProjectState']
    SageSyncEvent = deps.get('SageSyncEvent')
    RFI = deps.get('RFI')
    ChangeEvent = deps.get('ChangeEvent')
    PunchItem = deps.get('PunchItem')
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')

    def models_dict():
        return {
            'Project': Project,
            'Commitment': Commitment,
            'RFI': RFI,
            'ChangeOrder': ChangeOrder,
            'ExtendedModuleRecord': ExtendedModuleRecord,
            'PunchItem': PunchItem,
            'PayAppProjectState': PayAppProjectState,
            'SageSyncEvent': SageSyncEvent,
            'OperationsAiMessage': OperationsAiMessage,
            'OperationsPaymentLine': OperationsPaymentLine,
        }

    @app.route('/operations')
    @login_required
    def operations_center_page():
        return render_template('operations_center.html', active_project=get_active_project())

    @app.route('/operations/bim-viewer')
    @login_required
    def operations_bim_viewer_page():
        from extended_platform_services import serialize_bim_asset
        asset_id = request.args.get('asset_id', type=int)
        asset = OperationsBimAsset.query.get_or_404(asset_id) if asset_id else None
        return render_template('operations_bim_viewer.html', asset=serialize_bim_asset(asset) if asset else None)

    @app.route('/api/operations/catalog')
    @login_required
    def api_operations_catalog():
        from extended_platform_services import report_catalog
        from extended_platform_persistence import catalog_for_ui
        return jsonify({
            'categories': catalog_for_ui(),
            'report_sources': report_catalog(),
        })

    @app.route('/api/operations/wip')
    @login_required
    def api_operations_wip():
        from extended_platform_persistence import build_wip_snapshot, build_portfolio_wip
        project_id = request.args.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        if project_id:
            snap = build_wip_snapshot(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState, project_id)
            return jsonify({'wip': snap})
        return jsonify(build_portfolio_wip(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState))

    @app.route('/api/operations/<module_key>', methods=['GET'])
    @login_required
    def api_operations_list(module_key):
        from extended_platform_persistence import MODULE_SCHEMAS, compute_stats, serialize_record
        if module_key not in MODULE_SCHEMAS:
            return jsonify({'error': 'Unknown module'}), 404
        project_id = request.args.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        schema = MODULE_SCHEMAS[module_key]
        q = ExtendedModuleRecord.query.filter_by(module_key=module_key)
        if schema.get('project_scoped', True) and project_id:
            q = q.filter_by(project_id=int(project_id))
        rows = q.order_by(ExtendedModuleRecord.updated_at.desc()).all()
        stats = compute_stats(ExtendedModuleRecord, module_key, project_id if schema.get('project_scoped') else None)
        payload = {
            'records': [serialize_record(r) for r in rows],
            'stats': stats,
            'schema': {
                'simple': schema.get('simple', []),
                'advanced': schema.get('advanced', []),
                'statuses': list(schema.get('statuses', ('Draft',))),
                'project_scoped': schema.get('project_scoped', True),
            },
        }
        if module_key == 'bim_models' and project_id:
            assets = OperationsBimAsset.query.filter_by(project_id=int(project_id)).order_by(
                OperationsBimAsset.created_at.desc()
            ).all()
            from extended_platform_services import serialize_bim_asset
            payload['bim_assets'] = [serialize_bim_asset(a) for a in assets]
        return jsonify(payload)

    @app.route('/api/operations/<module_key>', methods=['POST'])
    @login_required
    def api_operations_create(module_key):
        from extended_platform_persistence import MODULE_SCHEMAS, apply_payload, serialize_record
        if module_key not in MODULE_SCHEMAS:
            return jsonify({'error': 'Unknown module'}), 404
        body = request.get_json(silent=True) or {}
        schema = MODULE_SCHEMAS[module_key]
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        if schema.get('project_scoped', True) and not project_id:
            return jsonify({'error': 'Select a current project before creating this item.'}), 400
        row = ExtendedModuleRecord(
            module_key=module_key,
            project_id=int(project_id) if schema.get('project_scoped') and project_id else None,
            company_id=body.get('company_id'),
            title=(body.get('title') or 'New item').strip(),
            status=body.get('status') or list(schema.get('statuses', ('Draft',)))[0],
            created_by_id=current_user.id,
        )
        apply_payload(row, body, module_key)
        db.session.add(row)
        db.session.commit()
        return jsonify({'ok': True, 'record': serialize_record(row)})

    @app.route('/api/operations/<module_key>/<int:record_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def api_operations_record(module_key, record_id):
        from extended_platform_persistence import MODULE_SCHEMAS, apply_payload, serialize_record, validate_vendor_invoice
        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key=module_key).first_or_404()
        if request.method == 'GET':
            payload = {'record': serialize_record(row)}
            if module_key == 'vendor_invoices' and row.project_id:
                payload['validation'] = validate_vendor_invoice(row, Commitment, CommitmentAllocation, row.project_id)
            if module_key == 'payment_batches':
                lines = OperationsPaymentLine.query.filter_by(batch_record_id=row.id).all()
                payload['payment_lines'] = [
                    {'vendor_name': l.vendor_name, 'amount': l.amount, 'status': l.status, 'lien_waiver_ok': l.lien_waiver_ok}
                    for l in lines
                ]
            if module_key == 'report_definitions':
                runs = OperationsReportRun.query.filter_by(report_record_id=row.id).order_by(
                    OperationsReportRun.created_at.desc()
                ).limit(5).all()
                payload['recent_runs'] = [{'id': r.id, 'row_count': r.row_count, 'source': r.source, 'created_at': r.created_at.isoformat() if r.created_at else None} for r in runs]
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
            serialize_record, validate_vendor_invoice, apply_payload,
            promote_correspondence_to_rfi, promote_tm_to_change_event,
        )
        from extended_platform_services import process_payment_batch, run_report

        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key=module_key).first_or_404()
        body = request.get_json(silent=True) or {}
        action = (body.get('action') or '').lower()
        result = {'ok': True}

        if action == 'validate_invoice' and module_key == 'vendor_invoices':
            result['validation'] = validate_vendor_invoice(row, Commitment, CommitmentAllocation, row.project_id)
        elif action == 'promote_rfi' and module_key == 'correspondence' and RFI and generate_next_number:
            rfi = promote_correspondence_to_rfi(row, RFI, db, row.project_id, current_user.id, generate_next_number)
            db.session.commit()
            result['rfi_id'] = rfi.id
            result['rfi_number'] = rfi.number
        elif action == 'promote_change_event' and module_key == 'tm_tickets' and ChangeEvent:
            ce = promote_tm_to_change_event(row, ChangeEvent, db, row.project_id, current_user.id)
            db.session.commit()
            result['change_event_id'] = ce.id
            result['change_event_number'] = ce.number
        elif action == 'post_timesheet' and module_key == 'timesheets':
            row.status = 'Posted'
            db.session.commit()
            result['message'] = 'Timesheet posted to job cost queue.'
        elif action == 'process_payment' and module_key == 'payment_batches':
            pay_result = process_payment_batch(db, models_dict(), row, current_user.id)
            result.update(pay_result)
            result['message'] = f'Processed ${pay_result.get("total", 0):,.2f} across {pay_result.get("line_count", 0)} line(s).'
        elif action == 'run_report' and module_key == 'report_definitions':
            report_data = run_report(row, db, models_dict(), row.project_id or get_current_project_id())
            run_row = OperationsReportRun(
                report_record_id=row.id,
                project_id=row.project_id,
                source=report_data['source'],
                row_count=report_data['row_count'],
                result_json=jsonify(report_data['rows']).get_data(as_text=True) if hasattr(jsonify(report_data['rows']), 'get_data') else None,
                csv_text=report_data['csv'],
                created_by_id=current_user.id,
            )
            import json as _json
            run_row.result_json = _json.dumps(report_data['rows'][:200])
            db.session.add(run_row)
            row.status = 'Active'
            db.session.commit()
            result['report'] = report_data
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400

        result['record'] = serialize_record(row)
        return jsonify(result)

    @app.route('/api/operations/ai/chat', methods=['POST'])
    @login_required
    def api_operations_ai_chat():
        from extended_platform_services import ai_chat
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        result = ai_chat(
            db, models_dict(),
            int(project_id) if project_id else None,
            body.get('thread_id'),
            body.get('message') or body.get('question'),
            current_user.id,
        )
        return jsonify(result)

    @app.route('/api/operations/ai/thread/<thread_id>')
    @login_required
    def api_operations_ai_thread(thread_id):
        from extended_platform_services import get_ai_thread
        return jsonify({'messages': get_ai_thread(OperationsAiMessage, thread_id)})

    @app.route('/api/operations/reports/run', methods=['POST'])
    @login_required
    def api_operations_report_run_adhoc():
        from extended_platform_services import run_report
        import json as _json
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        definition = {
            'data_source': body.get('source') or 'operations',
            'columns_json': body.get('columns'),
            'filters_json': body.get('filters') or {},
        }
        report_data = run_report(definition, db, models_dict(), project_id)
        run_row = OperationsReportRun(
            project_id=int(project_id) if project_id else None,
            source=report_data['source'],
            row_count=report_data['row_count'],
            result_json=_json.dumps(report_data['rows'][:200]),
            csv_text=report_data['csv'],
            created_by_id=current_user.id,
        )
        db.session.add(run_row)
        db.session.commit()
        report_data['run_id'] = run_row.id
        return jsonify(report_data)

    @app.route('/api/operations/bim/upload', methods=['POST'])
    @login_required
    def api_operations_bim_upload():
        from extended_platform_services import save_bim_asset, serialize_bim_asset
        project_id = request.form.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        f = request.files.get('file')
        if not f:
            return jsonify({'error': 'No file uploaded'}), 400
        try:
            asset = save_bim_asset(
                db, OperationsBimAsset, project_id, f, upload_folder, current_user.id,
                meta={
                    'title': request.form.get('title'),
                    'revision': request.form.get('revision'),
                    'discipline': request.form.get('discipline'),
                },
            )
            return jsonify({'ok': True, 'asset': serialize_bim_asset(asset)})
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/operations/bim/<int:asset_id>/file')
    @login_required
    def api_operations_bim_file(asset_id):
        asset = OperationsBimAsset.query.get_or_404(asset_id)
        if not asset.stored_path or not os.path.isfile(asset.stored_path):
            return jsonify({'error': 'File not found'}), 404
        return send_file(asset.stored_path, as_attachment=False, download_name=asset.filename)

    @app.route('/api/operations/bim/assets')
    @login_required
    def api_operations_bim_assets():
        from extended_platform_services import serialize_bim_asset
        project_id = request.args.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        q = OperationsBimAsset.query
        if project_id:
            q = q.filter_by(project_id=int(project_id))
        assets = q.order_by(OperationsBimAsset.created_at.desc()).all()
        return jsonify({'assets': [serialize_bim_asset(a) for a in assets]})
