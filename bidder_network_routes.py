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
    save_document_bytes = deps.get('save_document_bytes')
    get_active_project = deps.get('get_active_project')

    BidderNetworkRegistration = deps['BidderNetworkRegistration']
    BidderNetworkDocument = deps['BidderNetworkDocument']
    BidPackage = deps['BidPackage']
    Project = deps['Project']
    Estimate = deps['Estimate']
    Company = deps['Company']
    User = deps['User']
    Document = deps['Document']
    BidPackageAddendum = deps['BidPackageAddendum']
    PlanRoomClarification = deps['PlanRoomClarification']
    PlanRoomAddendumAck = deps['PlanRoomAddendumAck']
    PlanRoomExternalSyncLog = deps['PlanRoomExternalSyncLog']

    def models():
        return {
            'BidderNetworkRegistration': BidderNetworkRegistration,
            'BidderNetworkDocument': BidderNetworkDocument,
            'Company': Company,
            'User': User,
            'BidPackage': BidPackage,
            'Project': Project,
            'Estimate': Estimate,
            'Document': Document,
            'BidPackageAddendum': BidPackageAddendum,
            'PlanRoomClarification': PlanRoomClarification,
            'PlanRoomAddendumAck': PlanRoomAddendumAck,
            'PlanRoomExternalSyncLog': PlanRoomExternalSyncLog,
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

    def bidder_or_staff():
        from bidder_network_services import bidder_access_for_user
        if staff_estimating_ok():
            return {'approved': True, 'staff': True}
        return bidder_access_for_user(db, BidderNetworkRegistration, current_user)

    @app.route('/plan-room/projects')
    @login_required
    def plan_room_projects_page():
        from bidder_network_services import load_plan_room_settings, bidder_access_for_user
        access = bidder_access_for_user(db, BidderNetworkRegistration, current_user)
        if staff_estimating_ok():
            access = {'approved': True, 'staff': True}
        settings = load_plan_room_settings()
        return render_template(
            'bidder_plan_room_projects.html',
            settings=settings,
            access=access,
        )

    @app.route('/plan-room/projects/<int:project_id>/packages/<int:package_id>')
    @login_required
    def plan_room_package_detail_page(project_id, package_id):
        from bidder_network_services import load_plan_room_settings, bidder_access_for_user
        access = bidder_access_for_user(db, BidderNetworkRegistration, current_user)
        if staff_estimating_ok():
            access = {'approved': True, 'staff': True}
        settings = load_plan_room_settings()
        return render_template(
            'bidder_plan_room_package_detail.html',
            settings=settings,
            access=access,
            project_id=project_id,
            package_id=package_id,
        )

    @app.route('/plan-room/console')
    @login_required
    def plan_room_console_page():
        if not staff_estimating_ok():
            try:
                from portal_plan_room_access import is_plan_room_portal_user, plan_room_home_redirect
                if is_plan_room_portal_user(current_user):
                    return plan_room_home_redirect(current_user)
            except Exception:
                pass
            return redirect(url_for('estimating_page'))
        active_project = get_active_project() if get_active_project else None
        return render_template('plan_room_console.html', active_project=active_project)

    @app.route('/plan-room/projects/<int:project_id>')
    @login_required
    def plan_room_project_detail_page(project_id):
        from bidder_network_services import load_plan_room_settings, bidder_access_for_user
        access = bidder_access_for_user(db, BidderNetworkRegistration, current_user)
        if staff_estimating_ok():
            access = {'approved': True, 'staff': True}
        settings = load_plan_room_settings()
        return render_template(
            'bidder_plan_room_project_detail.html',
            settings=settings,
            access=access,
            project_id=project_id,
        )

    @app.route('/plan-room/opportunities')
    @login_required
    def plan_room_opportunities_redirect():
        return redirect('/plan-room/projects')

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

    @app.route('/api/public/bidder-network/projects')
    def api_public_plan_room_projects():
        from bidder_network_services import list_plan_room_projects
        return jsonify(list_plan_room_projects(db, BidPackage, Project, public_teaser=True))

    @app.route('/api/bidder-network/projects')
    @login_required
    def api_bidder_network_projects():
        from bidder_network_services import list_plan_room_projects
        access = bidder_or_staff()
        if not access.get('approved'):
            return jsonify({'error': 'Plan room access requires approval', 'access': access}), 403
        return jsonify(list_plan_room_projects(db, BidPackage, Project, public_teaser=False))

    @app.route('/api/bidder-network/projects/<int:project_id>')
    @login_required
    def api_bidder_network_project_detail(project_id):
        from bidder_network_services import plan_room_project_detail
        access = bidder_or_staff()
        if not access.get('approved'):
            return jsonify({'error': 'Plan room access requires approval', 'access': access}), 403
        try:
            staff = staff_estimating_ok()
            from plan_room_advanced_services import (
                enrich_addenda_with_acks,
                list_clarifications,
                user_addendum_ack_ids,
            )
            data = plan_room_project_detail(db, models(), project_id, staff_access=staff)
            add_ids = [a['id'] for a in data.get('addenda') or []]
            acked = user_addendum_ack_ids(db, PlanRoomAddendumAck, uid(), add_ids) if uid() else set()
            data['addenda'] = enrich_addenda_with_acks(data.get('addenda') or [], acked)
            data['clarifications'] = list_clarifications(db, PlanRoomClarification, project_id)['clarifications']
            data['documents_zip_url'] = f'/api/bidder-network/projects/{project_id}/documents.zip'
            data['pending_addendum_acks'] = sum(1 for a in data['addenda'] if not a.get('acknowledged'))
            return jsonify(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 404

    @app.route('/api/bidder-network/projects/<int:project_id>/packages/<int:package_id>')
    @login_required
    def api_bidder_network_package_detail(project_id, package_id):
        from bidder_network_services import plan_room_package_detail
        access = bidder_or_staff()
        if not access.get('approved'):
            return jsonify({'error': 'Plan room access requires approval', 'access': access}), 403
        try:
            staff = staff_estimating_ok()
            from plan_room_advanced_services import enrich_addenda_with_acks, user_addendum_ack_ids
            data = plan_room_package_detail(db, models(), project_id, package_id, staff_access=staff)
            add_ids = [a['id'] for a in data.get('addenda') or []]
            acked = user_addendum_ack_ids(db, PlanRoomAddendumAck, uid(), add_ids) if uid() else set()
            data['addenda'] = enrich_addenda_with_acks(data.get('addenda') or [], acked)
            data['documents_zip_url'] = f'/api/bidder-network/projects/{project_id}/packages/{package_id}/documents.zip'
            return jsonify(data)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 404

    @app.route('/api/bidder-network/admin/projects/<int:project_id>/console')
    @login_required
    def api_plan_room_admin_console(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import admin_plan_room_console
        try:
            return jsonify(admin_plan_room_console(db, models(), project_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 404

    @app.route('/api/bidder-network/admin/bid-packages/<int:package_id>/manifest', methods=['GET', 'PUT'])
    @login_required
    def api_plan_room_package_manifest(package_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import parse_package_manifest, update_bid_package_manifest
        pkg = BidPackage.query.get(int(package_id))
        if not pkg:
            return jsonify({'error': 'Bid package not found'}), 404
        if request.method == 'GET':
            return jsonify({
                'id': pkg.id,
                'project_id': pkg.project_id,
                'network_published': bool(pkg.network_published),
                'network_summary': pkg.network_summary,
                'manifest': parse_package_manifest(pkg),
            })
        body = request.get_json(silent=True) or {}
        try:
            out = update_bid_package_manifest(db, BidPackage, package_id, body)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/admin/projects/<int:project_id>/plan-documents', methods=['POST'])
    @login_required
    def api_plan_room_admin_upload_document(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        if not save_document_bytes:
            return jsonify({'error': 'Upload not configured'}), 500
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'error': 'file required'}), 400
        category = (request.form.get('category') or 'general').strip()
        name = (request.form.get('name') or f.filename).strip()
        doc_type_map = {
            'plans': 'Drawing',
            'specifications': 'Specification',
            'geotechnical': 'Report',
            'schedules': 'Other',
            'bid_forms': 'Other',
            'insurance': 'Other',
            'general': 'Other',
        }
        document_type = doc_type_map.get(category, 'Other')
        try:
            data = f.read()
            doc = save_document_bytes(
                int(project_id),
                data,
                name=name,
                original_filename=f.filename,
                mime_type=f.mimetype or 'application/octet-stream',
                document_type=document_type,
                uploaded_by_id=uid(),
            )
            return jsonify({'ok': True, 'document': doc, 'category': category})
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception:
            app.logger.exception('plan room document upload failed')
            return jsonify({'error': 'Upload failed'}), 500

    @app.route('/api/bidder-network/plan-documents/<int:doc_id>/download')
    @login_required
    def api_plan_room_document_download(doc_id):
        import os
        from flask import send_from_directory
        from bidder_network_services import user_may_access_plan_document
        if not staff_estimating_ok() and not user_may_access_plan_document(
            db, models(), current_user, doc_id, staff_access=staff_estimating_ok(),
        ):
            return jsonify({'error': 'Access denied'}), 403
        doc = Document.query.get_or_404(doc_id)
        directory = os.path.join(upload_folder, 'documents', str(doc.project_id))
        if not os.path.isfile(os.path.join(directory, doc.filename)):
            return jsonify({'error': 'File not found'}), 404
        return send_from_directory(
            directory, doc.filename, as_attachment=True,
            download_name=doc.original_filename or doc.filename,
        )

    @app.route('/api/bidder-network/plan-documents/<int:doc_id>/stream')
    @login_required
    def api_plan_room_document_stream(doc_id):
        import os
        from flask import send_from_directory
        from bidder_network_services import user_may_access_plan_document
        staff = staff_estimating_ok()
        if not staff and not user_may_access_plan_document(db, models(), current_user, doc_id, staff_access=staff):
            return jsonify({'error': 'Access denied'}), 403
        doc = Document.query.get_or_404(doc_id)
        directory = os.path.join(upload_folder, 'documents', str(doc.project_id))
        path = os.path.join(directory, doc.filename)
        if not os.path.isfile(path):
            return jsonify({'error': 'File not found'}), 404
        return send_from_directory(
            directory,
            doc.filename,
            as_attachment=False,
            mimetype=doc.mime_type or 'application/octet-stream',
            download_name=doc.original_filename or doc.filename,
        )

    @app.route('/plan-room/documents/<int:doc_id>/view')
    @login_required
    def plan_room_document_view_page(doc_id):
        from bidder_network_services import load_plan_room_settings, user_may_access_plan_document, bidder_access_for_user
        staff = staff_estimating_ok()
        access = bidder_access_for_user(db, BidderNetworkRegistration, current_user)
        if staff:
            access = {'approved': True, 'staff': True}
        if not access.get('approved'):
            return redirect(f'/login?next={request.path}')
        if not user_may_access_plan_document(db, models(), current_user, doc_id, staff_access=staff):
            return render_template(
                'bidder_plan_room_document_view.html',
                settings=load_plan_room_settings(),
                access=access,
                doc=None,
                error='You do not have access to this document.',
            ), 403
        doc = Document.query.get_or_404(doc_id)
        settings = load_plan_room_settings()
        from bidder_network_services import _document_dict, _doc_can_preview
        doc_payload = _document_dict(doc)
        if not _doc_can_preview(doc):
            return redirect(doc_payload['download_url'])
        return render_template(
            'bidder_plan_room_document_view.html',
            settings=settings,
            access=access,
            doc=doc_payload,
            project_id=doc.project_id,
            error=None,
        )

    @app.route('/api/bidder-network/admin/projects/<int:project_id>/estimating-summary')
    @login_required
    def api_plan_room_estimating_summary(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import estimating_plan_room_summary
        try:
            return jsonify(estimating_plan_room_summary(db, models(), project_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 404

    @app.route('/api/bidder-network/admin/bid-packages/<int:package_id>/sync-estimating', methods=['POST'])
    @login_required
    def api_plan_room_sync_estimating(package_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import sync_package_manifest_from_estimating
        try:
            out = sync_package_manifest_from_estimating(db, BidPackage, Document, package_id)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/projects/<int:project_id>/publish', methods=['POST', 'PUT'])
    @login_required
    def api_plan_room_publish_project(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from bidder_network_services import set_project_plan_room
        body = request.get_json(silent=True) or {}
        out = set_project_plan_room(db, Project, BidPackage, project_id, body)
        db.session.commit()
        return jsonify(out)

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
            manifest=body.get('manifest'),
        )
        db.session.commit()
        return jsonify(out)

    @app.route('/api/bidder-network/projects/<int:project_id>/clarifications', methods=['GET', 'POST'])
    @login_required
    def api_plan_room_clarifications(project_id):
        from plan_room_advanced_services import list_clarifications, submit_clarification
        if request.method == 'GET':
            access = bidder_or_staff()
            if not access.get('approved'):
                return jsonify({'error': 'Access denied'}), 403
            return jsonify(list_clarifications(db, PlanRoomClarification, project_id))
        if staff_estimating_ok():
            return jsonify({'error': 'Staff answer questions from the plan room console Q&A tab'}), 400
        access = bidder_or_staff()
        if not access.get('approved'):
            return jsonify({'error': 'Access denied'}), 403
        body = request.get_json(silent=True) or {}
        try:
            out = submit_clarification(db, models(), project_id, current_user, body)
            db.session.commit()
            return jsonify(out), 201
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/clarifications/<int:clarification_id>/answer', methods=['POST', 'PUT'])
    @login_required
    def api_plan_room_answer_clarification(clarification_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from plan_room_advanced_services import answer_clarification
        body = request.get_json(silent=True) or {}
        try:
            out = answer_clarification(db, PlanRoomClarification, clarification_id, uid(), body)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/addenda/<int:addendum_id>/acknowledge', methods=['POST'])
    @login_required
    def api_plan_room_ack_addendum(addendum_id):
        from plan_room_advanced_services import acknowledge_addendum
        if not uid():
            return jsonify({'error': 'Login required'}), 401
        try:
            out = acknowledge_addendum(db, PlanRoomAddendumAck, uid(), addendum_id)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/projects/<int:project_id>/documents.zip')
    @login_required
    def api_plan_room_project_zip(project_id):
        import io
        from flask import send_file
        from plan_room_advanced_services import zip_plan_documents
        access = bidder_or_staff()
        if not access.get('approved'):
            return jsonify({'error': 'Access denied'}), 403
        try:
            data, fname = zip_plan_documents(db, models(), project_id, package_id=None, upload_folder=upload_folder)
            return send_file(
                io.BytesIO(data),
                mimetype='application/zip',
                as_attachment=True,
                download_name=fname,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/projects/<int:project_id>/packages/<int:package_id>/documents.zip')
    @login_required
    def api_plan_room_package_zip(project_id, package_id):
        from flask import send_file
        import io
        from plan_room_advanced_services import zip_plan_documents
        access = bidder_or_staff()
        if not access.get('approved'):
            return jsonify({'error': 'Access denied'}), 403
        try:
            data, fname = zip_plan_documents(db, models(), project_id, package_id=package_id, upload_folder=upload_folder)
            return send_file(
                io.BytesIO(data),
                mimetype='application/zip',
                as_attachment=True,
                download_name=fname,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/admin/projects/<int:project_id>/broadcast-itb', methods=['POST'])
    @login_required
    def api_plan_room_broadcast_itb(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from plan_room_advanced_services import broadcast_plan_room_itb
        body = request.get_json(silent=True) or {}
        try:
            out = broadcast_plan_room_itb(
                db, models(), project_id,
                package_id=body.get('package_id'),
                notify_mode=body.get('notify_mode', 'both'),
            )
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/admin/projects/<int:project_id>/external-sync', methods=['POST'])
    @login_required
    def api_plan_room_external_sync(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from plan_room_advanced_services import export_external_network
        body = request.get_json(silent=True) or {}
        try:
            out = export_external_network(db, models(), project_id, body.get('provider', 'buildingconnected'), staff_user_id=uid())
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/bidder-network/admin/projects/<int:project_id>/external-sync/logs')
    @login_required
    def api_plan_room_external_sync_logs(project_id):
        if not staff_estimating_ok():
            return jsonify({'error': 'Estimating access required'}), 403
        from plan_room_advanced_services import list_external_sync_logs
        return jsonify(list_external_sync_logs(db, PlanRoomExternalSyncLog, project_id))

    @app.route('/estimating/plan-room-preview')
    @login_required
    def estimating_plan_room_preview():
        if not staff_estimating_ok():
            return redirect(url_for('estimating_page'))
        return redirect('/plan-room?preview=1')
