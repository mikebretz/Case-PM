"""Tier-2 platform routes — mobile field, payments, OCR, push, 4D BIM, integrations."""
import io
import json

from flask import Response, redirect, send_file, url_for


def register_platform_tier2_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps.get('get_current_project_id')
    jsonify = deps['jsonify']
    request = deps['request']
    render_template = deps['render_template']
    get_active_project = deps.get('get_active_project')
    Notification = deps['Notification']
    ExtendedModuleRecord = deps['ExtendedModuleRecord']
    Project = deps['Project']
    Commitment = deps['Commitment']
    OperationsBimAsset = deps['OperationsBimAsset']
    OperationsBimScheduleLink = deps['OperationsBimScheduleLink']
    PushSubscription = deps['PushSubscription']
    ClientPortalSelection = deps['ClientPortalSelection']
    ClientPortalDrawRequest = deps['ClientPortalDrawRequest']
    ClientPortalPayment = deps['ClientPortalPayment']
    IntegrationSyncLog = deps.get('IntegrationSyncLog')
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')

    def models_dict():
        return {
            'Project': Project,
            'RFI': deps.get('RFI'),
            'ChangeOrder': deps.get('ChangeOrder'),
            'ExtendedModuleRecord': ExtendedModuleRecord,
            'ClientPortalApproval': deps.get('ClientPortalApproval'),
            'IntegrationSyncLog': IntegrationSyncLog,
            'Commitment': Commitment,
            'ClientPortalSelection': ClientPortalSelection,
            'ClientPortalDrawRequest': ClientPortalDrawRequest,
            'ClientPortalPayment': ClientPortalPayment,
        }

    @app.route('/api/notifications/stream')
    @login_required
    def api_notifications_stream():
        from platform_tier2_services import notification_sse_stream
        return Response(
            notification_sse_stream(current_user.id, Notification, db),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    @app.route('/api/push/subscribe', methods=['POST'])
    @login_required
    def api_push_subscribe():
        from platform_tier2_services import save_push_subscription
        body = request.get_json(silent=True) or {}
        save_push_subscription(db, PushSubscription, current_user.id, body)
        return jsonify({'ok': True})

    @app.route('/field')
    @login_required
    def field_mobile_page():
        """Legacy URL — daily logs live on the main Daily Log module."""
        return redirect(url_for('daily_log'))

    @app.route('/api/payments/charge', methods=['POST'])
    @login_required
    def api_payments_charge():
        from platform_tier2_services import process_contractor_payment
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        try:
            result = process_contractor_payment(
                body.get('amount'), body.get('payee') or 'Vendor',
                body.get('method') or 'ACH', project_id, current_user.id, body,
            )
            if ClientPortalPayment and project_id:
                pay = ClientPortalPayment(
                    project_id=int(project_id),
                    title=body.get('title') or 'Contractor payment',
                    amount=float(body.get('amount') or 0),
                    payment_method=body.get('method') or 'ACH',
                    status=result.get('status', 'Pending'),
                    external_ref=result.get('reference'),
                )
                db.session.add(pay)
                db.session.commit()
            return jsonify(result)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/operations/transmittals/<int:record_id>/package')
    @login_required
    def api_transmittal_package(record_id):
        from platform_tier2_services import build_transmittal_package
        row = ExtendedModuleRecord.query.filter_by(id=record_id, module_key='transmittals').first_or_404()
        pdf = build_transmittal_package(row, Project, upload_folder)
        return send_file(
            io.BytesIO(pdf),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'transmittal-package-{row.number or row.id}.pdf',
        )

    @app.route('/api/operations/vendor_invoices/ocr', methods=['POST'])
    @login_required
    def api_vendor_invoice_ocr():
        from platform_tier2_services import ocr_invoice_pdf, match_invoice_to_commitment
        f = request.files.get('file')
        if not f:
            return jsonify({'error': 'No file'}), 400
        import os
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f'ocr_{f.filename}')
        f.save(path)
        try:
            ocr = ocr_invoice_pdf(path)
            project_id = request.form.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
            matches = match_invoice_to_commitment(ocr, Commitment, project_id)
            return jsonify({'ocr': ocr, 'matches': matches})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    @app.route('/api/operations/bim/<int:asset_id>/4d')
    @login_required
    def api_bim_4d(asset_id):
        from platform_tier2_services import bim_4d_timeline
        project_id = request.args.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        return jsonify(bim_4d_timeline(db, OperationsBimScheduleLink, OperationsBimAsset, asset_id, project_id))

    @app.route('/api/client-portal/selections/<int:sel_id>/choose', methods=['POST'])
    @login_required
    def api_client_portal_selection(sel_id):
        row = ClientPortalSelection.query.get_or_404(sel_id)
        body = request.get_json(silent=True) or {}
        row.selected_option = body.get('option') or body.get('selected_option')
        row.status = 'Selected'
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/client-portal/draws/<int:draw_id>/respond', methods=['POST'])
    @login_required
    def api_client_portal_draw(draw_id):
        row = ClientPortalDrawRequest.query.get_or_404(draw_id)
        body = request.get_json(silent=True) or {}
        row.status = body.get('decision') or 'Approved'
        row.notes = body.get('notes') or row.notes
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/integrations/sync-full', methods=['POST'])
    @login_required
    def api_integrations_sync_full():
        from platform_tier2_services import sync_procore_bidirectional, sync_autodesk_bidirectional
        from platform_gaps_services import sync_integration
        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        logs = []
        if body.get('sage'):
            logs.extend(sync_integration(db, IntegrationSyncLog, 'sage', project_id, current_user.id, models_dict()).get('logs', []))
        if body.get('procore', True):
            logs.extend(sync_procore_bidirectional(db, IntegrationSyncLog, project_id, current_user.id, models_dict(), body.get('direction', 'both')))
        if body.get('autodesk'):
            logs.extend(sync_autodesk_bidirectional(db, IntegrationSyncLog, project_id, current_user.id, models_dict()))
        db.session.commit()
        return jsonify({'logs': logs, 'count': len(logs)})
