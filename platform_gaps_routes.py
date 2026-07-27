"""Routes for platform gap features — client portal, integrations, transmittals, AI assist."""
import io

from flask import Response, send_file


def register_platform_gaps_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps.get('get_current_project_id')
    jsonify = deps['jsonify']
    request = deps['request']
    render_template = deps['render_template']
    get_active_project = deps['get_active_project']
    ExtendedModuleRecord = deps['ExtendedModuleRecord']
    OperationsTransmittalRecipient = deps['OperationsTransmittalRecipient']
    ClientPortalApproval = deps['ClientPortalApproval']
    IntegrationSyncLog = deps['IntegrationSyncLog']
    BudgetProjectState = deps['BudgetProjectState']
    SageSyncEvent = deps.get('SageSyncEvent')
    Project = deps['Project']
    RFI = deps.get('RFI')
    ChangeOrder = deps['ChangeOrder']
    User = deps['User']

    def models_dict():
        return {
            'Project': Project,
            'RFI': RFI,
            'ChangeOrder': ChangeOrder,
            'ExtendedModuleRecord': ExtendedModuleRecord,
            'ClientPortalApproval': ClientPortalApproval,
            'IntegrationSyncLog': IntegrationSyncLog,
            'SageSyncEvent': SageSyncEvent,
            'BudgetProjectState': BudgetProjectState,
            'Commitment': deps.get('Commitment'),
            'PayAppProjectState': deps.get('PayAppProjectState'),
        }

    @app.route('/client-portal')
    @login_required
    def client_portal_page():
        return render_template('client_portal.html', active_project=get_active_project())

    @app.route('/api/client-portal/feed')
    @login_required
    def api_client_portal_feed():
        from platform_gaps_services import build_client_portal_feed
        project_id = request.args.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        return jsonify(build_client_portal_feed(db, models_dict(), current_user, project_id))

    @app.route('/api/client-portal/approvals/<int:approval_id>/respond', methods=['POST'])
    @login_required
    def api_client_portal_respond(approval_id):
        from platform_gaps_services import respond_client_portal
        body = request.get_json(silent=True) or {}
        try:
            result = respond_client_portal(
                db, ClientPortalApproval, approval_id, current_user,
                body.get('response') or '', body.get('decision') or 'Approved',
            )
            return jsonify(result)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/client-portal/share', methods=['POST'])
    @login_required
    def api_client_portal_share():
        from platform_gaps_services import create_client_portal_approval
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        row = create_client_portal_approval(
            db, ClientPortalApproval, int(project_id),
            body.get('item_type') or 'document',
            int(body.get('item_id') or 0),
            body.get('title') or 'Shared item',
            body.get('description') or '',
            body.get('action_url') or f'/documents?project_id={project_id}',
            current_user.id,
            body.get('assign_user_id'),
        )
        db.session.commit()
        return jsonify({'ok': True, 'approval_id': row.id})

    @app.route('/api/integrations/sync', methods=['POST'])
    @login_required
    def api_integrations_sync():
        from platform_gaps_services import sync_integration
        body = request.get_json(silent=True) or {}
        integration = body.get('integration') or 'sage'
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        try:
            result = sync_integration(db, IntegrationSyncLog, integration, project_id, current_user.id, models_dict())
            return jsonify(result)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/integrations/logs')
    @login_required
    def api_integrations_logs():
        q = IntegrationSyncLog.query.order_by(IntegrationSyncLog.created_at.desc()).limit(50)
        project_id = request.args.get('project_id', type=int)
        if project_id:
            q = q.filter_by(project_id=project_id)
        rows = q.all()
        return jsonify({'logs': [{
            'id': r.id, 'integration': r.integration, 'direction': r.direction,
            'entity_type': r.entity_type, 'status': r.status, 'message': r.message,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in rows]})

    @app.route('/api/operations/transmittals/<int:record_id>/pdf')
    @login_required
    def api_transmittal_pdf(record_id):
        from platform_gaps_services import build_transmittal_pdf_for_record
        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key='transmittals').first_or_404()
        pdf = build_transmittal_pdf_for_record(row, Project, OperationsTransmittalRecipient)
        return send_file(
            io.BytesIO(pdf),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'transmittal-{row.number or row.id}.pdf',
        )

    @app.route('/api/operations/transmittals/ack/<token>', methods=['GET', 'POST'])
    def api_transmittal_ack(token):
        from platform_gaps_services import acknowledge_transmittal
        try:
            result = acknowledge_transmittal(db, OperationsTransmittalRecipient, ExtendedModuleRecord, token)
            if request.method == 'GET':
                return render_template('transmittal_ack.html', ok=True, transmittal_id=result.get('transmittal_id'))
            return jsonify(result)
        except ValueError as exc:
            if request.method == 'GET':
                return render_template('transmittal_ack.html', ok=False, error=str(exc)), 400
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/operations/certified_payroll/<int:record_id>/wh347')
    @login_required
    def api_wh347_pdf(record_id):
        from platform_gaps_services import generate_certified_payroll
        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key='certified_payroll').first_or_404()
        pdf, violations = generate_certified_payroll(db, row, Project)
        resp = send_file(
            io.BytesIO(pdf),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'wh347-{row.number or row.id}.pdf',
        )
        resp.headers['X-Prevailing-Violations'] = str(len(violations))
        return resp

    @app.route('/api/operations/ai/assist', methods=['POST'])
    @login_required
    def api_operations_ai_assist():
        from platform_gaps_services import ai_assist
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        result = ai_assist(
            db, models_dict(),
            body.get('task') or 'general',
            int(project_id) if project_id else None,
            body.get('record_id'),
            current_user.id,
            body.get('context'),
        )
        return jsonify(result)

    @app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
    @login_required
    def api_notification_mark_read(notification_id):
        from app import Notification
        n = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
        n.is_read = True
        db.session.commit()
        return jsonify({'ok': True})
