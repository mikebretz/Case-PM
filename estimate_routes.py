"""Preconstruction estimating API routes — estimates, RFPs, takeoff, award."""
from datetime import datetime


def register_estimate_routes(app, deps):
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
    BudgetProjectState = deps['BudgetProjectState']
    EstimateBudgetMapping = deps.get('EstimateBudgetMapping')
    EstimateAlternate = deps.get('EstimateAlternate')
    Commitment = deps.get('Commitment')
    Company = deps['Company']
    Drawing = deps['Drawing']
    DrawingMarkup = deps['DrawingMarkup']
    User = deps['User']
    Project = deps['Project']

    def _load_estimate_detail(est):
        from estimate_persistence import (
            estimate_to_dict, estimate_line_to_dict, bid_package_to_dict,
            invitation_to_dict, recalc_estimate_totals,
        )
        from estimate_features import get_estimate_settings
        lines = EstimateLine.query.filter_by(estimate_id=est.id).order_by(EstimateLine.sort_order, EstimateLine.id).all()
        packages = BidPackage.query.filter_by(estimate_id=est.id).order_by(BidPackage.number).all()
        pkg_payload = []
        for pkg in packages:
            invs = BidInvitation.query.filter_by(bid_package_id=pkg.id).all()
            inv_payload = []
            for inv in invs:
                qlines = BidQuoteLine.query.filter_by(invitation_id=inv.id).all()
                inv_payload.append(invitation_to_dict(inv, [
                    {'cost_code': q.cost_code, 'description': q.description, 'amount': q.amount,
                     'quantity': q.quantity, 'unit': q.unit, 'unit_cost': q.unit_cost}
                    for q in qlines
                ]))
            pkg_lines = [estimate_line_to_dict(l) for l in lines if l.bid_package_id == pkg.id]
            pkg_payload.append(bid_package_to_dict(pkg, inv_payload, pkg_lines))
        recalc_estimate_totals(Estimate, EstimateLine, est.id, EstimateAlternate)
        db.session.flush()
        return estimate_to_dict(
            est,
            [estimate_line_to_dict(l) for l in lines],
            pkg_payload,
            settings=get_estimate_settings(est),
        )

    @app.route('/api/estimates', methods=['GET'])
    @login_required
    def api_list_estimates():
        from estimate_persistence import estimate_to_dict
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        rows = Estimate.query.filter_by(project_id=int(project_id)).order_by(Estimate.updated_at.desc()).all()
        return deps['jsonify']({'estimates': [estimate_to_dict(e) for e in rows]})

    @app.route('/api/estimates/<int:estimate_id>', methods=['GET'])
    @login_required
    def api_get_estimate(estimate_id):
        est = Estimate.query.get_or_404(estimate_id)
        return deps['jsonify'](_load_estimate_detail(est))

    @app.route('/api/estimates', methods=['POST'])
    @login_required
    def api_create_estimate():
        from estimate_persistence import apply_estimate_fields, estimate_to_dict, save_estimate_lines, recalc_estimate_totals
        body = deps['request'].get_json(silent=True) or {}
        project_id = body.get('project_id') or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        est = Estimate(
            project_id=int(project_id),
            number=generate_next_number('EST', Estimate, doc_type='estimate', project_id=int(project_id)),
            title=body.get('title') or 'Project Estimate',
            status='Draft',
            created_by_id=current_user.id,
        )
        apply_estimate_fields(est, body)
        db.session.add(est)
        db.session.flush()
        if body.get('lines'):
            save_estimate_lines(EstimateLine, est.id, body['lines'], db)
        recalc_estimate_totals(Estimate, EstimateLine, est.id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'estimate': _load_estimate_detail(est)})

    @app.route('/api/estimates/<int:estimate_id>', methods=['PUT'])
    @login_required
    def api_update_estimate(estimate_id):
        from estimate_persistence import apply_estimate_fields, save_estimate_lines, recalc_estimate_totals
        est = Estimate.query.get_or_404(estimate_id)
        body = deps['request'].get_json(silent=True) or {}
        apply_estimate_fields(est, body)
        if 'lines' in body:
            save_estimate_lines(EstimateLine, est.id, body['lines'], db)
        recalc_estimate_totals(Estimate, EstimateLine, est.id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'estimate': _load_estimate_detail(est)})

    @app.route('/api/estimates/<int:estimate_id>/lines', methods=['POST'])
    @login_required
    def api_add_estimate_line(estimate_id):
        from estimate_persistence import apply_estimate_line_fields, estimate_line_to_dict, recalc_estimate_totals
        Estimate.query.get_or_404(estimate_id)
        body = deps['request'].get_json(silent=True) or {}
        sort = EstimateLine.query.filter_by(estimate_id=estimate_id).count()
        line = EstimateLine(estimate_id=estimate_id, sort_order=sort)
        apply_estimate_line_fields(line, body)
        db.session.add(line)
        recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'line': estimate_line_to_dict(line)})

    @app.route('/api/estimates/<int:estimate_id>/import-takeoff', methods=['POST'])
    @login_required
    def api_import_takeoff(estimate_id):
        from drawing_persistence import collect_takeoff_items
        from estimate_persistence import import_takeoff_to_estimate, recalc_estimate_totals, estimate_line_to_dict
        est = Estimate.query.get_or_404(estimate_id)
        body = deps['request'].get_json(silent=True) or {}
        drawing_id = body.get('drawing_id')
        items = collect_takeoff_items(DrawingMarkup, Drawing, est.project_id, drawing_id)
        if not items:
            return deps['jsonify']({'error': 'No takeoff measurements found'}), 400
        imported = import_takeoff_to_estimate(
            EstimateLine, est.id, items, db,
            bid_package_id=body.get('bid_package_id'),
            default_cost_code=body.get('cost_code') or '01-000',
        )
        recalc_estimate_totals(Estimate, EstimateLine, est.id, EstimateAlternate)
        db.session.commit()
        return deps['jsonify']({
            'ok': True,
            'imported': len(imported),
            'lines': [estimate_line_to_dict(l) for l in imported],
            'estimate': _load_estimate_detail(est),
        })

    @app.route('/api/estimates/<int:estimate_id>/takeoff-preview', methods=['GET'])
    @login_required
    def api_takeoff_preview(estimate_id):
        from drawing_persistence import collect_takeoff_items
        est = Estimate.query.get_or_404(estimate_id)
        drawing_id = deps['request'].args.get('drawing_id', type=int)
        items = collect_takeoff_items(DrawingMarkup, Drawing, est.project_id, drawing_id)
        q = (deps['request'].args.get('q') or '').strip().lower()
        if q:
            items = [i for i in items if q in (i.get('description') or '').lower() or q in (i.get('sheet_number') or '').lower()]
        return deps['jsonify']({'items': items, 'count': len(items)})

    @app.route('/api/estimates/<int:estimate_id>/bid-packages', methods=['POST'])
    @login_required
    def api_create_bid_package(estimate_id):
        from estimate_persistence import apply_bid_package_fields, bid_package_to_dict
        est = Estimate.query.get_or_404(estimate_id)
        body = deps['request'].get_json(silent=True) or {}
        pkg = BidPackage(
            estimate_id=est.id,
            project_id=est.project_id,
            number=generate_next_number('RFP', BidPackage, doc_type='bid_package', project_id=est.project_id),
            title=body.get('title') or 'Bid Package',
            status='Draft',
        )
        apply_bid_package_fields(pkg, body)
        db.session.add(pkg)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'bid_package': bid_package_to_dict(pkg)})

    @app.route('/api/estimates/bid-packages/<int:package_id>', methods=['PUT'])
    @login_required
    def api_update_bid_package(package_id):
        from estimate_persistence import apply_bid_package_fields, bid_package_to_dict, invitation_to_dict
        pkg = BidPackage.query.get_or_404(package_id)
        body = deps['request'].get_json(silent=True) or {}
        apply_bid_package_fields(pkg, body)
        db.session.commit()
        invs = BidInvitation.query.filter_by(bid_package_id=pkg.id).all()
        return deps['jsonify']({'ok': True, 'bid_package': bid_package_to_dict(pkg, [invitation_to_dict(i) for i in invs])})

    @app.route('/api/estimates/bid-packages/<int:package_id>/invitations', methods=['POST'])
    @login_required
    def api_add_invitations(package_id):
        from estimate_persistence import invitation_to_dict
        pkg = BidPackage.query.get_or_404(package_id)
        body = deps['request'].get_json(silent=True) or {}
        vendors = body.get('vendors') or []
        created = []
        for v in vendors:
            inv = BidInvitation(
                bid_package_id=pkg.id,
                company_id=str(v.get('company_id') or v.get('id') or ''),
                company_name=v.get('company_name') or v.get('name') or '',
                contact_email=v.get('contact_email') or v.get('email') or '',
                contact_name=v.get('contact_name') or '',
                status='Draft',
            )
            db.session.add(inv)
            created.append(inv)
        db.session.commit()
        return deps['jsonify']({'ok': True, 'invitations': [invitation_to_dict(i) for i in created]})

    @app.route('/api/estimates/bid-packages/<int:package_id>/mass-invite', methods=['POST'])
    @login_required
    def api_mass_invite(package_id):
        from estimate_persistence import companies_for_spec_trade, notify_bid_invitations, invitation_to_dict
        pkg = BidPackage.query.get_or_404(package_id)
        body = deps['request'].get_json(silent=True) or {}
        if body.get('auto_match'):
            companies = companies_for_spec_trade(Company, spec_section=pkg.spec_section, trade=body.get('trade'))
            for c in companies:
                existing = BidInvitation.query.filter_by(bid_package_id=pkg.id, company_name=c.name).first()
                if existing:
                    continue
                inv = BidInvitation(
                    bid_package_id=pkg.id,
                    company_id=str(c.id),
                    company_name=c.name,
                    contact_email=c.email or '',
                    status='Draft',
                )
                db.session.add(inv)
            db.session.flush()
        invitations = BidInvitation.query.filter_by(bid_package_id=pkg.id).all()
        now = datetime.utcnow()
        sent = []
        for inv in invitations:
            if inv.status in ('Draft', 'Sent'):
                inv.status = 'Sent'
                inv.sent_at = now
                sent.append(inv)
        if body.get('send_notifications', True):
            est = Estimate.query.get(pkg.estimate_id)
            from estimate_features import get_estimate_settings
            notify_mode = body.get('notify_mode') or (get_estimate_settings(est).get('rfp_notify_mode') if est else 'both')
            notify_bid_invitations(
                pkg.project_id, sent, pkg, User,
                notify_mode=notify_mode,
                estimate=est,
                Project=Project,
            )
        pkg.status = 'Open'
        db.session.commit()
        return deps['jsonify']({'ok': True, 'sent': len(sent), 'invitations': [invitation_to_dict(i) for i in invitations]})

    @app.route('/api/estimates/bid-packages/<int:package_id>/award', methods=['POST'])
    @login_required
    def api_award_bid_package(package_id):
        from estimate_persistence import bid_package_to_dict, invitation_to_dict
        pkg = BidPackage.query.get_or_404(package_id)
        body = deps['request'].get_json(silent=True) or {}
        inv_id = body.get('invitation_id')
        if not inv_id:
            return deps['jsonify']({'error': 'invitation_id required'}), 400
        inv = BidInvitation.query.get_or_404(int(inv_id))
        if inv.bid_package_id != pkg.id:
            return deps['jsonify']({'error': 'Invitation does not belong to this package'}), 400
        for other in BidInvitation.query.filter_by(bid_package_id=pkg.id).all():
            other.status = 'Awarded' if other.id == inv.id else (
                'Quoted' if other.status == 'Awarded' else other.status
            )
        inv.status = 'Awarded'
        pkg.awarded_invitation_id = inv.id
        pkg.status = 'Awarded'
        db.session.commit()
        commitment_id = None
        est = Estimate.query.get(pkg.estimate_id)
        if est:
            from estimate_features import get_estimate_settings, award_to_commitment_draft
            if get_estimate_settings(est).get('award_auto_commitment') and Commitment:
                try:
                    c = award_to_commitment_draft(
                        BidPackage, BidInvitation, Commitment,
                        deps.get('CommitmentAllocation'),
                        db, pkg.id, generate_next_number, current_user.id,
                    )
                    commitment_id = c.id
                except Exception:
                    db.session.rollback()
        invs = BidInvitation.query.filter_by(bid_package_id=pkg.id).all()
        payload = {'ok': True, 'bid_package': bid_package_to_dict(pkg, [invitation_to_dict(i) for i in invs])}
        if commitment_id:
            payload['commitment_id'] = commitment_id
        return deps['jsonify'](payload)

    @app.route('/api/estimates/<int:estimate_id>/leveling', methods=['GET'])
    @login_required
    def api_bid_leveling(estimate_id):
        from estimate_persistence import bid_leveling_matrix
        Estimate.query.get_or_404(estimate_id)
        return deps['jsonify']({'matrix': bid_leveling_matrix(BidPackage, BidInvitation, estimate_id)})

    @app.route('/api/estimates/<int:estimate_id>/award-to-budget', methods=['POST'])
    @login_required
    def api_award_to_budget(estimate_id):
        from estimate_persistence import award_estimate_to_budget
        body = deps['request'].get_json(silent=True) or {}
        try:
            result = award_estimate_to_budget(
                Estimate, EstimateLine, BidPackage, BidInvitation,
                BudgetProjectState, db, estimate_id,
                user_id=current_user.id,
                use_bid_awards=bool(body.get('use_bid_awards')),
                EstimateBudgetMapping=EstimateBudgetMapping,
            )
        except Exception as exc:
            db.session.rollback()
            return deps['jsonify']({'error': str(exc)}), 400
        est = Estimate.query.get(estimate_id)
        return deps['jsonify']({'ok': True, 'result': result, 'estimate': _load_estimate_detail(est)})

    @app.route('/api/estimates/vendors', methods=['GET'])
    @login_required
    def api_estimate_vendors():
        from estimate_persistence import companies_for_spec_trade
        spec = deps['request'].args.get('spec_section')
        trade = deps['request'].args.get('trade')
        companies = companies_for_spec_trade(Company, spec_section=spec, trade=trade)
        return deps['jsonify']({'vendors': [
            {'id': c.id, 'name': c.name, 'email': c.email, 'trade': c.trade, 'type': c.type}
            for c in companies
        ]})

    @app.route('/api/estimates/portal', methods=['GET'])
    @login_required
    def api_estimate_portal_list():
        from estimate_persistence import bid_package_to_dict, invitation_to_dict
        project_id = deps['request'].args.get('project_id', type=int) or get_current_project_id()
        if not project_id:
            return deps['jsonify']({'error': 'project_id required'}), 400
        cid = str(getattr(current_user, 'company_id', '') or '')
        cname = (getattr(current_user, 'company', '') or '').strip()
        email = (getattr(current_user, 'email', '') or '').strip()
        is_staff = current_user.role in ('Admin', 'Project Manager', 'Estimator', 'Preconstruction Manager')
        invitations = BidInvitation.query.join(BidPackage).filter(
            BidPackage.project_id == int(project_id),
            BidInvitation.status.in_(('Sent', 'Viewed', 'Quoted', 'Declined', 'Not Interested', 'Awarded')),
        ).all()
        results = []
        for inv in invitations:
            if not is_staff:
                match = (
                    (cid and str(inv.company_id or '') == cid)
                    or (cname and (inv.company_name or '').strip() == cname)
                    or (email and (inv.contact_email or '').strip() == email)
                )
                if not match:
                    continue
            pkg = BidPackage.query.get(inv.bid_package_id)
            if not pkg:
                continue
            est = Estimate.query.get(pkg.estimate_id)
            results.append({
                'invitation': invitation_to_dict(inv),
                'bid_package': bid_package_to_dict(pkg),
                'estimate_number': est.number if est else '',
                'estimate_title': est.title if est else '',
            })
        return deps['jsonify']({'invitations': results})

    @app.route('/api/estimates/portal/<int:invitation_id>/respond', methods=['POST'])
    @login_required
    def api_estimate_portal_respond(invitation_id):
        inv = BidInvitation.query.get_or_404(invitation_id)
        body = deps['request'].get_json(silent=True) or {}
        action = (body.get('action') or 'quote').lower()
        now = datetime.utcnow()
        if action in ('decline', 'not_interested', 'not interested'):
            inv.status = 'Not Interested' if 'not' in action else 'Declined'
            inv.decline_reason = body.get('reason') or body.get('decline_reason') or ''
            inv.responded_at = now
        elif action == 'quote':
            inv.status = 'Quoted'
            inv.quote_amount = float(body.get('quote_amount') or body.get('amount') or 0)
            inv.quote_notes = body.get('quote_notes') or body.get('notes') or ''
            inv.responded_at = now
            BidQuoteLine.query.filter_by(invitation_id=inv.id).delete()
            for row in body.get('quote_lines') or []:
                ql = BidQuoteLine(
                    invitation_id=inv.id,
                    cost_code=row.get('cost_code') or '',
                    description=row.get('description') or '',
                    amount=float(row.get('amount') or 0),
                    quantity=float(row.get('quantity') or 0),
                    unit=row.get('unit') or '',
                    unit_cost=float(row.get('unit_cost') or 0),
                    notes=row.get('notes') or '',
                )
                db.session.add(ql)
            if not inv.quote_amount and body.get('quote_lines'):
                inv.quote_amount = sum(float(r.get('amount') or 0) for r in body['quote_lines'])
        else:
            return deps['jsonify']({'error': f'Unknown action: {action}'}), 400
        db.session.commit()
        from estimate_persistence import invitation_to_dict
        return deps['jsonify']({'ok': True, 'invitation': invitation_to_dict(inv)})
