"""Extended estimating API routes — features 1–29."""
import json
from datetime import datetime

from flask import send_file


def register_estimate_feature_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps['get_current_project_id']
    generate_next_number = deps['generate_next_number']
    Estimate = deps['Estimate']
    EstimateLine = deps['EstimateLine']
    BidPackage = deps['BidPackage']
    BidInvitation = deps['BidInvitation']
    BidQuoteLine = deps['BidQuoteLine']
    EstimateAssembly = deps['EstimateAssembly']
    EstimateSnapshot = deps['EstimateSnapshot']
    EstimateAlternate = deps['EstimateAlternate']
    EstimateCostHistory = deps['EstimateCostHistory']
    EstimateBudgetMapping = deps['EstimateBudgetMapping']
    BidPackageAddendum = deps['BidPackageAddendum']
    BidLevelingNote = deps['BidLevelingNote']
    BudgetProjectState = deps['BudgetProjectState']
    Commitment = deps['Commitment']
    CommitmentAllocation = deps['CommitmentAllocation']
    Company = deps['Company']
    COI = deps.get('COI')
    Project = deps['Project']
    DrawingMarkup = deps.get('DrawingMarkup')

    # --- Assemblies / library (#1, #8) ---
    @app.route('/api/estimates/assemblies', methods=['GET'])
    @login_required
    def api_list_assemblies():
        from estimate_features import assembly_to_dict, seed_default_assemblies
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        seed_default_assemblies(EstimateAssembly, db, project_id)
        seed_default_assemblies(EstimateAssembly, db, None)
        q = EstimateAssembly.query
        if project_id:
            rows = q.filter((EstimateAssembly.project_id == project_id) | (EstimateAssembly.project_id.is_(None))).all()
        else:
            rows = q.filter(EstimateAssembly.project_id.is_(None)).all()
        return deps['jsonify']({'assemblies': [assembly_to_dict(a) for a in rows]})

    @app.route('/api/estimates/assemblies', methods=['POST'])
    @login_required
    def api_create_assembly():
        from estimate_features import assembly_to_dict
        body = deps['request'].get_json(silent=True) or {}
        a = EstimateAssembly(
            project_id=body.get('project_id') or get_current_project_id(),
            name=body.get('name') or 'Assembly',
            description=body.get('description'),
            trade=body.get('trade'),
            spec_section=body.get('spec_section'),
            unit=body.get('unit') or 'EA',
            unit_cost=float(body.get('unit_cost') or 0),
            components_json=json.dumps(body.get('components') or []),
            source='user',
        )
        db.session.add(a)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'assembly': assembly_to_dict(a)})

    @app.route('/api/estimates/<int:estimate_id>/apply-assembly', methods=['POST'])
    @login_required
    def api_apply_assembly(estimate_id):
        from estimate_features import expand_assembly_to_lines, line_to_dict_extended, recalc_estimate_totals
        body = deps['request'].get_json(silent=True) or {}
        assembly_id = body.get('assembly_id')
        qty = float(body.get('quantity') or 1)
        if not assembly_id:
            return deps['jsonify']({'error': 'assembly_id required'}), 400
        sort_base = EstimateLine.query.filter_by(estimate_id=estimate_id).count()
        rows = expand_assembly_to_lines(EstimateAssembly, int(assembly_id), qty, sort_base)
        created = []
        for row in rows:
            line = EstimateLine(estimate_id=estimate_id)
            for k, v in row.items():
                if hasattr(line, k):
                    setattr(line, k, v)
            line.extended_cost = float(line.quantity or 0) * float(line.unit_cost or 0)
            db.session.add(line)
            created.append(line)
        recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'lines': [line_to_dict_extended(l) for l in created]})

    # --- Snapshots (#4) ---
    @app.route('/api/estimates/<int:estimate_id>/snapshots', methods=['GET'])
    @login_required
    def api_list_snapshots(estimate_id):
        from estimate_features import list_snapshots
        return deps['jsonify']({'snapshots': list_snapshots(EstimateSnapshot, estimate_id)})

    @app.route('/api/estimates/<int:estimate_id>/snapshots', methods=['POST'])
    @login_required
    def api_create_snapshot(estimate_id):
        from estimate_features import snapshot_estimate, list_snapshots
        body = deps['request'].get_json(silent=True) or {}
        snapshot_estimate(Estimate, EstimateLine, EstimateSnapshot, BidPackage, estimate_id, body.get('label'), current_user.id, db)
        return deps['jsonify']({'ok': True, 'snapshots': list_snapshots(EstimateSnapshot, estimate_id)})

    @app.route('/api/estimates/<int:estimate_id>/snapshots/<int:snap_id>', methods=['GET'])
    @login_required
    def api_get_snapshot(estimate_id, snap_id):
        snap = EstimateSnapshot.query.get_or_404(snap_id)
        if snap.estimate_id != estimate_id:
            return deps['jsonify']({'error': 'Not found'}), 404
        import json
        return deps['jsonify'](json.loads(snap.data_json or '{}'))

    # --- Alternates & allowances (#3) ---
    @app.route('/api/estimates/<int:estimate_id>/alternates', methods=['GET'])
    @login_required
    def api_list_alternates(estimate_id):
        from estimate_features import alternate_to_dict, recalc_alternate_amounts
        recalc_alternate_amounts(EstimateLine, EstimateAlternate, estimate_id)
        db.session.commit()
        rows = EstimateAlternate.query.filter_by(estimate_id=estimate_id).all()
        return deps['jsonify']({'alternates': [alternate_to_dict(a) for a in rows]})

    @app.route('/api/estimates/<int:estimate_id>/alternates', methods=['POST'])
    @login_required
    def api_save_alternates(estimate_id):
        from estimate_features import alternate_to_dict, recalc_alternate_amounts
        body = deps['request'].get_json(silent=True) or {}
        EstimateAlternate.query.filter_by(estimate_id=estimate_id).delete()
        for row in body.get('alternates') or []:
            alt = EstimateAlternate(
                estimate_id=estimate_id,
                alt_key=row.get('alt_key') or row.get('key'),
                label=row.get('label'),
                include_in_base=bool(row.get('include_in_base')),
                amount=float(row.get('amount') or 0),
                notes=row.get('notes'),
            )
            db.session.add(alt)
        recalc_alternate_amounts(EstimateLine, EstimateAlternate, estimate_id)
        db.session.commit()
        from estimate_persistence import recalc_estimate_totals
        recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
        db.session.commit()
        rows = EstimateAlternate.query.filter_by(estimate_id=estimate_id).all()
        return deps['jsonify']({'ok': True, 'alternates': [alternate_to_dict(a) for a in rows]})

    # --- Excel (#2, #16) ---
    @app.route('/api/estimates/<int:estimate_id>/export-excel', methods=['GET'])
    @login_required
    def api_export_excel(estimate_id):
        from estimate_features import export_worksheet_excel, compute_fee_breakdown, alternate_to_dict, line_to_dict_extended
        lines = [line_to_dict_extended(l) for l in EstimateLine.query.filter_by(estimate_id=estimate_id).all()]
        alts = [alternate_to_dict(a) for a in EstimateAlternate.query.filter_by(estimate_id=estimate_id).all()]
        est = Estimate.query.get_or_404(estimate_id)
        fee = compute_fee_breakdown(est, EstimateLine.query.filter_by(estimate_id=estimate_id).all(), EstimateAlternate)
        buf = export_worksheet_excel(lines, alts, fee)
        return send_file(buf, as_attachment=True, download_name=f'estimate-{est.number or estimate_id}.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/api/estimates/<int:estimate_id>/import-excel', methods=['POST'])
    @login_required
    def api_import_excel(estimate_id):
        from estimate_features import import_worksheet_excel
        from estimate_persistence import save_estimate_lines, recalc_estimate_totals
        f = deps['request'].files.get('file')
        if not f:
            return deps['jsonify']({'error': 'file required'}), 400
        rows = import_worksheet_excel(f)
        save_estimate_lines(EstimateLine, estimate_id, rows, db)
        recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'imported': len(rows)})

    @app.route('/api/estimates/<int:estimate_id>/export-leveling-excel', methods=['GET'])
    @login_required
    def api_export_leveling_excel(estimate_id):
        from estimate_persistence import bid_leveling_matrix
        from estimate_features import export_leveling_excel
        matrix = bid_leveling_matrix(BidPackage, BidInvitation, estimate_id)
        buf = export_leveling_excel(matrix)
        est = Estimate.query.get_or_404(estimate_id)
        return send_file(buf, as_attachment=True, download_name=f'leveling-{est.number or estimate_id}.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # --- Budget mappings (#18) ---
    @app.route('/api/estimates/budget-mappings', methods=['GET'])
    @login_required
    def api_list_budget_mappings():
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        rows = EstimateBudgetMapping.query.filter_by(project_id=int(project_id)).all()
        return deps['jsonify']({'mappings': [{
            'id': m.id, 'spec_section': m.spec_section, 'cost_code': m.cost_code, 'cost_type': m.cost_type,
        } for m in rows]})

    @app.route('/api/estimates/budget-mappings', methods=['POST'])
    @login_required
    def api_save_budget_mappings():
        body = deps['request'].get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        EstimateBudgetMapping.query.filter_by(project_id=int(project_id)).delete()
        for row in body.get('mappings') or []:
            db.session.add(EstimateBudgetMapping(
                project_id=int(project_id),
                spec_section=row.get('spec_section'),
                cost_code=row.get('cost_code'),
                cost_type=row.get('cost_type') or 'Subcontract',
            ))
        db.session.commit()
        return deps['jsonify']({'ok': True})

    # --- RFP attachments & addenda (#5, #14) ---
    @app.route('/api/estimates/bid-packages/<int:package_id>/attachments', methods=['PUT'])
    @login_required
    def api_package_attachments(package_id):
        pkg = BidPackage.query.get_or_404(package_id)
        body = deps['request'].get_json(silent=True) or {}
        import json
        pkg.attachments_json = json.dumps(body.get('document_ids') or body.get('attachments') or [])
        db.session.commit()
        return deps['jsonify']({'ok': True})

    @app.route('/api/estimates/bid-packages/<int:package_id>/addenda', methods=['GET', 'POST'])
    @login_required
    def api_package_addenda(package_id):
        import json
        if deps['request'].method == 'GET':
            rows = BidPackageAddendum.query.filter_by(bid_package_id=package_id).order_by(BidPackageAddendum.created_at).all()
            return deps['jsonify']({'addenda': [{
                'id': a.id, 'number': a.number, 'title': a.title, 'description': a.description,
                'require_rebid': a.require_rebid,
                'document_ids': json.loads(a.document_ids_json or '[]'),
            } for a in rows]})
        body = deps['request'].get_json(silent=True) or {}
        a = BidPackageAddendum(
            bid_package_id=package_id,
            number=body.get('number') or f'ADD-{BidPackageAddendum.query.filter_by(bid_package_id=package_id).count() + 1}',
            title=body.get('title') or 'Addendum',
            description=body.get('description'),
            require_rebid=bool(body.get('require_rebid')),
            document_ids_json=json.dumps(body.get('document_ids') or []),
        )
        db.session.add(a)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'id': a.id})

    # --- RFP email template (#10) ---
    @app.route('/api/estimates/rfp-template', methods=['GET', 'PUT'])
    @login_required
    def api_rfp_template():
        from estimate_features import DEFAULT_RFP_TEMPLATE, get_estimate_settings, save_estimate_settings
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        est = Estimate.query.filter_by(project_id=project_id).order_by(Estimate.updated_at.desc()).first()
        if deps['request'].method == 'GET':
            if est:
                return deps['jsonify'](get_estimate_settings(est).get('rfp_email_template', DEFAULT_RFP_TEMPLATE))
            return deps['jsonify'](DEFAULT_RFP_TEMPLATE)
        body = deps['request'].get_json(silent=True) or {}
        if not est:
            return deps['jsonify']({'error': 'Create an estimate first'}), 400
        save_estimate_settings(est, {'rfp_email_template': body})
        db.session.commit()
        return deps['jsonify']({'ok': True})

    # --- Vendor qualification (#11) ---
    @app.route('/api/estimates/bid-packages/<int:package_id>/qualify', methods=['POST'])
    @login_required
    def api_qualify_vendors(package_id):
        from estimate_features import check_vendor_qualification
        import json
        invitations = BidInvitation.query.filter_by(bid_package_id=package_id).all()
        results = []
        for inv in invitations:
            qual = check_vendor_qualification(Company, COI, inv.company_id, inv.company_name)
            inv.qualification_json = json.dumps(qual)
            results.append({'invitation_id': inv.id, 'company_name': inv.company_name, **qual})
        db.session.commit()
        return deps['jsonify']({'results': results})

    # --- Reminders (#12) ---
    @app.route('/api/estimates/run-reminders', methods=['POST'])
    @login_required
    def api_run_reminders():
        from estimate_features import send_bid_reminders
        body = deps['request'].get_json(silent=True) or {}
        sent = send_bid_reminders(BidPackage, BidInvitation, Project, deps['User'], db, hours_before=int(body.get('hours') or 48), Estimate=Estimate)
        return deps['jsonify']({'ok': True, 'reminders_sent': sent})

    # --- Leveling notes / scope gaps (#15) ---
    @app.route('/api/estimates/bid-packages/<int:package_id>/leveling-notes', methods=['GET', 'POST'])
    @login_required
    def api_leveling_notes(package_id):
        if deps['request'].method == 'GET':
            q = BidLevelingNote.query.filter_by(bid_package_id=package_id)
            inv_id = deps['request'].args.get('invitation_id', type=int)
            if inv_id:
                q = q.filter_by(invitation_id=inv_id)
            rows = q.order_by(BidLevelingNote.created_at.desc()).all()
            return deps['jsonify']({'notes': [{
                'id': n.id, 'invitation_id': n.invitation_id, 'note_type': n.note_type, 'text': n.text,
                'created_at': n.created_at.isoformat() if n.created_at else None,
            } for n in rows]})
        body = deps['request'].get_json(silent=True) or {}
        n = BidLevelingNote(
            bid_package_id=package_id,
            invitation_id=body.get('invitation_id'),
            note_type=body.get('note_type') or 'scope_gap',
            text=body.get('text') or '',
            created_by_id=current_user.id,
        )
        db.session.add(n)
        if body.get('invitation_id'):
            inv = BidInvitation.query.get(body['invitation_id'])
            if inv:
                import json
                gaps = json.loads(inv.scope_gaps_json or '[]')
                gaps.append({'type': n.note_type, 'text': n.text})
                inv.scope_gaps_json = json.dumps(gaps)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'id': n.id})

    # --- Award commitment (#17) ---
    @app.route('/api/estimates/bid-packages/<int:package_id>/award-commitment', methods=['POST'])
    @login_required
    def api_award_commitment(package_id):
        from estimate_features import award_to_commitment_draft
        from commitment_persistence import commitment_to_dict
        c = award_to_commitment_draft(
            BidPackage, BidInvitation, Commitment, CommitmentAllocation, db,
            package_id, generate_next_number, current_user.id,
        )
        allocs = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
        return deps['jsonify']({'ok': True, 'commitment': commitment_to_dict(c, allocs)})

    # --- Forecast sync (#19) ---
    @app.route('/api/estimates/<int:estimate_id>/sync-forecast', methods=['POST'])
    @login_required
    def api_sync_forecast(estimate_id):
        from estimate_features import sync_estimate_to_forecast
        rom = sync_estimate_to_forecast(Estimate, BudgetProjectState, db, estimate_id, current_user.id)
        return deps['jsonify']({'ok': True, 'estimate_rom': rom})

    # --- Contingency drawdown (#20) ---
    @app.route('/api/estimates/<int:estimate_id>/contingency-drawdown', methods=['POST'])
    @login_required
    def api_contingency_drawdown(estimate_id):
        from estimate_features import apply_contingency_drawdown
        est = Estimate.query.get_or_404(estimate_id)
        body = deps['request'].get_json(silent=True) or {}
        line = apply_contingency_drawdown(
            BudgetProjectState, db, est.project_id,
            body.get('amount'), current_user.id, body.get('note') or '',
        )
        return deps['jsonify']({'ok': True, 'contingency_line': line})

    # --- Fee breakdown (#21) ---
    @app.route('/api/estimates/<int:estimate_id>/fee-breakdown', methods=['GET'])
    @login_required
    def api_fee_breakdown(estimate_id):
        from estimate_features import compute_fee_breakdown
        est = Estimate.query.get_or_404(estimate_id)
        lines = EstimateLine.query.filter_by(estimate_id=estimate_id).all()
        return deps['jsonify'](compute_fee_breakdown(est, lines, EstimateAlternate))

    # --- Cost history (#27) ---
    @app.route('/api/estimates/cost-history', methods=['GET', 'POST'])
    @login_required
    def api_cost_history():
        from estimate_features import lookup_historical_cost
        if deps['request'].method == 'GET':
            rows = lookup_historical_cost(
                EstimateCostHistory,
                cost_code=deps['request'].args.get('cost_code'),
                trade=deps['request'].args.get('trade'),
                unit=deps['request'].args.get('unit'),
                project_id=deps['request'].args.get('project_id', type=int),
            )
            return deps['jsonify']({'history': rows})
        body = deps['request'].get_json(silent=True) or {}
        row = EstimateCostHistory(
            project_id=body.get('project_id') or get_current_project_id(),
            cost_code=body.get('cost_code'),
            trade=body.get('trade'),
            unit=body.get('unit'),
            unit_cost=float(body.get('unit_cost') or 0),
            description=body.get('description'),
            source_project_name=body.get('source_project_name'),
        )
        db.session.add(row)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'id': row.id})

    # --- Estimate settings ---
    @app.route('/api/estimates/<int:estimate_id>/settings', methods=['GET', 'PUT'])
    @login_required
    def api_estimate_settings(estimate_id):
        from estimate_features import get_estimate_settings, save_estimate_settings, RFP_NOTIFY_MODES
        est = Estimate.query.get_or_404(estimate_id)
        if deps['request'].method == 'GET':
            return deps['jsonify'](get_estimate_settings(est))
        body = deps['request'].get_json(silent=True) or {}
        patch = {}
        if 'award_auto_commitment' in body:
            patch['award_auto_commitment'] = bool(body['award_auto_commitment'])
        if 'rfp_notify_mode' in body:
            mode = str(body['rfp_notify_mode'] or 'both').lower()
            patch['rfp_notify_mode'] = mode if mode in RFP_NOTIFY_MODES else 'both'
        for key in ('fee_breakdown_visible', 'budget_mapping_auto', 'ai_scope_enabled', 'reminder_hours_before'):
            if key in body:
                patch[key] = body[key]
        if 'rfp_email_template' in body:
            patch['rfp_email_template'] = body['rfp_email_template']
        save_estimate_settings(est, patch)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'settings': get_estimate_settings(est)})

    # --- AI scope stub (#29) ---
    @app.route('/api/estimates/<int:estimate_id>/ai-scope', methods=['POST'])
    @login_required
    def api_ai_scope(estimate_id):
        from estimate_features import ai_extract_scope_from_spec, line_to_dict_extended
        import json
        body = deps['request'].get_json(silent=True) or {}
        suggestions = ai_extract_scope_from_spec(body.get('text') or '', body.get('spec_section'))
        if body.get('apply'):
            sort_base = EstimateLine.query.filter_by(estimate_id=estimate_id).count()
            created = []
            for i, row in enumerate(suggestions):
                line = EstimateLine(estimate_id=estimate_id, sort_order=sort_base + i)
                line.cost_code = row.get('cost_code', '01-000')
                line.spec_section = row.get('spec_section', '')
                line.description = row.get('description', '')
                line.quantity = row.get('quantity', 1)
                line.unit = row.get('unit', 'EA')
                line.source = 'ai_scope'
                line.meta_json = json.dumps({'confidence': row.get('confidence')})
                db.session.add(line)
                created.append(line)
            from estimate_persistence import recalc_estimate_totals
            recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
            db.session.commit()
            return deps['jsonify']({'ok': True, 'lines': [line_to_dict_extended(l) for l in created]})
        return deps['jsonify']({'suggestions': suggestions})

    # --- Takeoff link (#7) ---
    @app.route('/api/estimates/lines/<int:line_id>/takeoff-link', methods=['GET'])
    @login_required
    def api_takeoff_link(line_id):
        line = EstimateLine.query.get_or_404(line_id)
        markup = DrawingMarkup.query.get(line.markup_id) if DrawingMarkup and line.markup_id else None
        return deps['jsonify']({
            'line_id': line.id,
            'markup_id': line.markup_id,
            'drawing_id': markup.drawing_id if markup else None,
            'drawings_url': f'/drawings?project_id={Estimate.query.get(line.estimate_id).project_id}&markup_id={line.markup_id}' if line.markup_id else None,
        })

    # --- Dashboard tile (#25) ---
    @app.route('/api/estimates/dashboard-tile', methods=['GET'])
    @login_required
    def api_estimating_dashboard_tile():
        from estimate_features import build_dashboard_estimating_tile
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        return deps['jsonify'](build_dashboard_estimating_tile(Estimate, BidPackage, BidInvitation, project_id))

    # --- Filter/group lines (#9, #24) ---
    @app.route('/api/estimates/<int:estimate_id>/filter-lines', methods=['POST'])
    @login_required
    def api_filter_lines(estimate_id):
        from estimate_features import filter_group_lines, line_to_dict_extended
        body = deps['request'].get_json(silent=True) or {}
        lines = [line_to_dict_extended(l) for l in EstimateLine.query.filter_by(estimate_id=estimate_id).all()]
        return deps['jsonify'](filter_group_lines(lines, body.get('filters')))

    # --- Bulk edit (#23) ---
    @app.route('/api/estimates/<int:estimate_id>/bulk-edit', methods=['POST'])
    @login_required
    def api_bulk_edit(estimate_id):
        from estimate_features import apply_line_extended_fields
        body = deps['request'].get_json(silent=True) or {}
        ids = body.get('line_ids') or []
        patch = body.get('patch') or {}
        updated = 0
        for line_id in ids:
            line = EstimateLine.query.filter_by(id=int(line_id), estimate_id=estimate_id).first()
            if not line:
                continue
            apply_line_extended_fields(line, patch)
            updated += 1
        from estimate_persistence import recalc_estimate_totals
        recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'updated': updated})

    # --- Spec book sections for worksheet ---
    @app.route('/api/estimates/spec-book-sections', methods=['GET'])
    @login_required
    def api_spec_book_sections():
        import os
        from flask import current_app
        from csi_catalog import CSI_SPEC_SECTIONS, normalize_spec_code

        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        upload_root = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        folder = os.path.join(upload_root, 'spec_books', str(project_id))
        meta_path = os.path.join(folder, 'meta.json')
        pdf_path = os.path.join(folder, 'spec_book.pdf')
        if not os.path.isfile(meta_path) or not os.path.isfile(pdf_path):
            return deps['jsonify']({'has_spec_book': False, 'sections': [], 'filename': None})
        try:
            with open(meta_path, encoding='utf-8') as fh:
                meta = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return deps['jsonify']({'has_spec_book': False, 'sections': [], 'filename': None})
        section_map = meta.get('contentSectionPageMap') or meta.get('sectionPageMap') or {}
        csi_titles = {normalize_spec_code(s['code']): s['title'] for s in CSI_SPEC_SECTIONS}
        sections = []
        for code in sorted(section_map.keys(), key=lambda c: normalize_spec_code(c)):
            norm = normalize_spec_code(code)
            title = csi_titles.get(norm) or code
            sections.append({'code': code, 'title': title, 'label': f'{code} — {title}'})
        return deps['jsonify']({
            'has_spec_book': True,
            'filename': meta.get('filename'),
            'page_count': meta.get('pageCount', 0),
            'sections': sections,
        })

    # --- Takeoff finish templates & live expansion ---
    @app.route('/api/estimates/takeoff-finish-templates', methods=['GET'])
    @login_required
    def api_takeoff_finish_templates():
        from takeoff_templates import list_finish_templates
        trigger = deps['request'].args.get('trigger')
        return deps['jsonify']({'templates': list_finish_templates(trigger)})

    @app.route('/api/estimates/<int:estimate_id>/takeoff-expand', methods=['POST'])
    @login_required
    def api_takeoff_expand(estimate_id):
        from takeoff_templates import expand_takeoff_template
        from estimate_features import line_to_dict_extended
        import json
        Estimate.query.get_or_404(estimate_id)
        body = deps['request'].get_json(silent=True) or {}
        lines = expand_takeoff_template(
            body.get('template_id'),
            body.get('quantity'),
            unit=body.get('unit') or 'LF',
            markup_id=body.get('markup_id'),
            sheet_number=body.get('sheet_number') or '',
        )
        if body.get('apply'):
            sort_base = EstimateLine.query.filter_by(estimate_id=estimate_id).count()
            created = []
            for i, row in enumerate(lines):
                line = EstimateLine(estimate_id=estimate_id, sort_order=sort_base + i)
                line.cost_code = row.get('cost_code', '01-000')
                line.spec_section = row.get('spec_section', '')
                line.description = row.get('description', '')
                line.quantity = row.get('quantity', 0)
                line.unit = row.get('unit', 'EA')
                line.unit_cost = row.get('unit_cost', 0)
                line.extended_cost = round(float(line.quantity or 0) * float(line.unit_cost or 0), 2)
                line.source = row.get('source', 'takeoff')
                line.source_ref = row.get('source_ref', '')
                line.markup_id = row.get('markup_id')
                line.group_key = row.get('group_key', '')
                line.meta_json = json.dumps(row.get('meta') or {})
                db.session.add(line)
                created.append(line)
            from estimate_persistence import recalc_estimate_totals
            recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
            db.session.commit()
            return deps['jsonify']({'ok': True, 'lines': [line_to_dict_extended(l) for l in created]})
        return deps['jsonify']({'lines': lines})

    # --- Live takeoff data (#6) ---
    @app.route('/api/estimates/<int:estimate_id>/takeoff-live', methods=['GET'])
    @login_required
    def api_takeoff_live(estimate_id):
        from drawing_persistence import collect_takeoff_items
        est = Estimate.query.get_or_404(estimate_id)
        drawing_id = deps['request'].args.get('drawing_id', type=int)
        items = collect_takeoff_items(deps['DrawingMarkup'], deps['Drawing'], est.project_id, drawing_id)
        drawings = deps['Drawing'].query.filter_by(project_id=est.project_id).order_by(deps['Drawing'].sheet_number).all()
        return deps['jsonify']({
            'items': items,
            'drawings': [{
                'id': d.id,
                'sheet_number': d.sheet_number,
                'title': d.title,
                'file_url': f'/api/drawings/{d.id}/file',
            } for d in drawings],
            'project_id': est.project_id,
            'estimate_id': estimate_id,
        })
