"""Accounting module API routes — Sage 300 catalog, ERP queue, Web API inquiries."""
from __future__ import annotations


def register_accounting_routes(app, deps):
    db = deps['db']
    request = deps['request']
    jsonify = deps['jsonify']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps['get_current_project_id']
    Project = deps['Project']
    SageSyncEvent = deps['SageSyncEvent']

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

    @app.route('/api/accounting/connection', methods=['GET'])
    @login_required
    def api_accounting_connection():
        from accounting_module_service import connection_status
        return jsonify(connection_status())

    @app.route('/api/accounting/dashboard', methods=['GET'])
    @login_required
    def api_accounting_dashboard():
        from accounting_module_service import build_dashboard
        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        return jsonify(build_dashboard(Project, SageSyncEvent, int(project_id)))

    @app.route('/api/accounting/erp-queue', methods=['GET'])
    @login_required
    def api_accounting_erp_queue():
        from accounting_module_service import serialize_erp_events
        from sage_service import sage_event_to_dict

        project_id = request.args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        limit = min(request.args.get('limit', 100, type=int), 300)
        accounting_status = (request.args.get('accounting_status') or '').strip()
        status = (request.args.get('status') or '').strip()
        q = SageSyncEvent.query.filter_by(project_id=int(project_id))
        if accounting_status:
            q = q.filter(SageSyncEvent.accounting_status == accounting_status)
        if status:
            q = q.filter(SageSyncEvent.status == status)
        events = q.order_by(SageSyncEvent.created_at.desc()).limit(limit).all()
        return jsonify({'events': serialize_erp_events(events, sage_event_to_dict)})

    @app.route('/api/accounting/web-api/probe', methods=['POST'])
    @login_required
    def api_accounting_web_probe():
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        from sage300_web_client import probe_connection
        return jsonify(probe_connection())

    @app.route('/api/accounting/web-api/resource', methods=['GET'])
    @login_required
    def api_accounting_web_resource():
        from financial_security import require_accounting_role
        try:
            require_accounting_role(current_user)
        except PermissionError as exc:
            return jsonify({'error': str(exc)}), 403
        from sage300_web_client import get_resource

        module = request.args.get('module', '')
        resource = request.args.get('resource', '')
        if not module or not resource:
            return jsonify({'error': 'module and resource required'}), 400
        company = request.args.get('company', '')
        top = request.args.get('top', 25, type=int)
        skip = request.args.get('skip', 0, type=int)
        filters = request.args.get('$filter', '') or request.args.get('filter', '')
        result = get_resource(module, resource, company=company, top=top, skip=skip, filters=filters)
        return jsonify(result)
