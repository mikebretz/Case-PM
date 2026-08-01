"""Bidder plan room — public site, registration, staff approval, opportunities."""


def register_bidder_network_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    jsonify = deps['jsonify']
    request = deps['request']
    render_template = deps['render_template']
    redirect = deps['redirect']
    url_for = deps['url_for']
    save_uploaded_file = deps['save_uploaded_file']
    upload_folder = deps['upload_folder']

    BidderNetworkRegistration = deps['BidderNetworkRegistration']
    BidderNetworkDocument = deps['BidderNetworkDocument']
    BidPackage = deps['BidPackage']
    Project = deps['Project']
    Estimate = deps['Estimate']
    Company = deps['Company']
    User = deps['User']

    def models():
        return {
            'BidderNetworkRegistration': BidderNetworkRegistration,
            'BidderNetworkDocument': BidderNetworkDocument,
            'Company': Company,
            'User': User,
            'BidPackage': BidPackage,
            'Project': Project,
            'Estimate': Estimate,
        }

    def uid():
        return current_user.id if current_user and getattr(current_user, 'id', None) else None

    def staff_estimating_ok():
        if not current_user or not getattr(current_user, 'is_authenticated', False):
            return False
        role = (getattr(current_user, 'role', None) or '').strip()
        if role in ('Admin', 'Project Manager', 'Estimator', 'Preconstruction Manager'):
            return True
        try:
            from case_workflow import user_has_module_access
            return user_has_module_access(current_user, 'estimating', 'view')
        except Exception:
            return False

    @app.route('/plan-room')
    @app.route('/plan-room/register')
    def plan_room_public_page():
        from bidder_network_services import load_plan_room_settings, SPECIALTY_OPTIONS
        settings = load_plan_room_settings()
        embed = request.args.get('embed') == '1'
        preview = request.args.get('preview') == '1' and staff_estimating_ok()
        return render_template(
            'bidder_plan_room.html',
            settings=settings,
            specialties=SPECIALTY_OPTIONS,
            embed=embed,
            preview=preview,
        )

    @app.route('/plan-room/opportunities')
    @login_required
    def plan_room_opportunities_page():
        from bidder_network_services import load_plan_room_settings, bidder_access_for_user
        access = bidder_access_for_user(db, BidderNetworkRegistration, current_user)
        settings = load_plan_room_settings()
        return render_template(
            'bidder_plan_room_opportunities.html',
            settings=settings,
            access=access,
        )

    @app.route('/api/public/bidder-network/settings')
    def api_public_bidder_network_settings():
        from bidder_network_services import load_plan_room_settings, SPECIALTY_OPTIONS
        s = load_plan_room_settings()
        return jsonify({'settings': s, 'specialties': list(SPECIALTY_OPTIONS)})

    @app.route('/api/public/bidder-network/register', methods=['POST'])
    def api_public_bidder_register():
        from bidder_network_services import create_registration
        body = request.form.to_dict() if request.form else {}
        if request.is_json:
            body = request.get_json(silent=True) or body
        files = request.files.getlist('attachments') or request.files.getlist('files')
        try:
            out = create_registration(
                db, models(),
                body=body,
                files=files,
                save_file_fn=save_uploaded_file,
                upload_folder=upload_folder,
            )
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:
            db.session.rollback()
            app.logger.exception('bidder register failed')
            return jsonify({'error': 'Registration could not be saved'}), 500

    @app.route('/api/bidder-network/access')
    @login_required
    def api_bidder_network_access():
        from bidder_network_services import bidder_access_for_user
        return jsonify(bidder_access_for_user(db, BidderNetworkRegistration, current_user))

    @app.route('/api/bidder-network/opportunities')
    @login_required
    def api_bidder_network_opportunities():
        from bidder_network_services import bidder_access_for_user, list_network_opportunities
        access = bidder_access_for_user(db, BidderNetworkRegistration, current_user)
        if not access.get('approved') and not staff_estimating_ok():
            return jsonify({'error': 'Plan room access requires an approved bidder registration', 'access': access}), 403
        return jsonify(list_network_opportunities(db, BidPackage, Project, Estimate))

    @app.route('/api/bidder-network/registrations')
    @login_required
    def api_bidder_network_registrations_list():
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import list_registrations
        status = request.args.get('status')
        return jsonify(list_registrations(db, BidderNetworkRegistration, status=status))

    @app.route('/api/bidder-network/registrations/<int:reg_id>/approve', methods=['POST'])
    @login_required
    def api_bidder_network_approve(reg_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import approve_registration
        try:
            out = approve_registration(db, models(), reg_id, reviewer_id=uid())
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400
        except Exception:
            db.session.rollback()
            app.logger.exception('bidder approve failed')
            return jsonify({'error': 'Approval failed'}), 500

    @app.route('/api/bidder-network/registrations/<int:reg_id>/reject', methods=['POST'])
    @login_required
    def api_bidder_network_reject(reg_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import reject_registration
        body = request.get_json(silent=True) or {}
        try:
            out = reject_registration(
                db, BidderNetworkRegistration, reg_id,
                body.get('reason') or '',
                reviewer_id=uid(),
            )
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/registrations/<int:reg_id>/documents')
    @login_required
    def api_bidder_network_documents(reg_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        rows = BidderNetworkDocument.query.filter_by(registration_id=reg_id).all()
        return jsonify({
            'documents': [{
                'id': d.id,
                'filename': d.original_filename,
                'size_bytes': d.size_bytes,
                'download_url': f'/api/bidder-network/documents/{d.id}/download',
            } for d in rows],
        })

    @app.route('/api/bidder-network/documents/<int:doc_id>/download')
    @login_required
    def api_bidder_network_document_download(doc_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        import os
        from flask import send_from_directory
        doc = BidderNetworkDocument.query.get_or_404(doc_id)
        folder = os.path.join(upload_folder, 'bidder_network')
        return send_from_directory(folder, doc.stored_filename, as_attachment=True, download_name=doc.original_filename)

    @app.route('/api/estimates/bid-packages/<int:package_id>/network-publish', methods=['POST', 'PUT'])
    @login_required
    def api_bid_package_network_publish(package_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import set_package_network_publish
        body = request.get_json(silent=True) or {}
        published = body.get('published', body.get('network_published', True))
        out = set_package_network_publish(
            db, BidPackage, package_id,
            published=bool(published),
            summary=body.get('network_summary'),
        )
        db.session.commit()
        return jsonify(out)

    @app.route('/estimating/plan-room-preview')
    @login_required
    def estimating_plan_room_preview():
        if not staff_estimating_ok():
            return redirect(url_for('estimating_page'))
        return redirect('/plan-room?preview=1')
