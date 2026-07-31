"""Construction marketing — portfolio, pipeline, campaigns, reputation, DAM."""


def register_marketing_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps.get('get_current_project_id')
    jsonify = deps['jsonify']
    request = deps['request']
    render_template = deps['render_template']
    get_active_project = deps['get_active_project']
    MarketingLead = deps['MarketingLead']
    MarketingCaseStudy = deps['MarketingCaseStudy']
    MarketingCampaign = deps['MarketingCampaign']
    MarketingReviewRequest = deps['MarketingReviewRequest']
    MarketingAsset = deps['MarketingAsset']
    MarketingCollateralTemplate = deps['MarketingCollateralTemplate']
    Project = deps['Project']
    Photo = deps['Photo']
    Estimate = deps['Estimate']
    BudgetProjectState = deps.get('BudgetProjectState')
    PayAppProjectState = deps.get('PayAppProjectState')

    def uid():
        return current_user.id if current_user and getattr(current_user, 'id', None) else None

    @app.route('/marketing')
    @login_required
    def marketing_page():
        return render_template('marketing.html', active_project=get_active_project())

    @app.route('/api/marketing/catalog')
    @login_required
    def api_marketing_catalog():
        from marketing_services import marketing_module_catalog, seed_collateral_templates

        seed_collateral_templates(db, MarketingCollateralTemplate)
        db.session.commit()
        return jsonify(marketing_module_catalog())

    @app.route('/api/marketing/deploy-check')
    @login_required
    def api_marketing_deploy_check():
        from marketing_services import marketing_deploy_check

        return jsonify(marketing_deploy_check())

    @app.route('/api/marketing/dashboard')
    @login_required
    def api_marketing_dashboard():
        from marketing_services import marketing_roi_dashboard

        return jsonify(marketing_roi_dashboard(db, MarketingLead, MarketingCampaign, Project))

    @app.route('/api/marketing/leads')
    @login_required
    def api_marketing_leads_list():
        from marketing_services import list_leads

        stage = request.args.get('stage')
        return jsonify(list_leads(db, MarketingLead, stage=stage))

    @app.route('/api/marketing/leads', methods=['POST'])
    @login_required
    def api_marketing_leads_create():
        from marketing_services import upsert_lead

        body = request.get_json(silent=True) or {}
        try:
            out = upsert_lead(db, MarketingLead, body, user_id=uid())
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/leads/<int:lead_id>', methods=['PATCH', 'PUT'])
    @login_required
    def api_marketing_leads_update(lead_id):
        from marketing_services import upsert_lead

        body = request.get_json(silent=True) or {}
        try:
            out = upsert_lead(db, MarketingLead, body, user_id=uid(), lead_id=lead_id)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/leads/<int:lead_id>/stage', methods=['POST'])
    @login_required
    def api_marketing_leads_stage(lead_id):
        from marketing_services import move_lead_stage

        body = request.get_json(silent=True) or {}
        stage = body.get('stage') or request.args.get('stage')
        if not stage:
            return jsonify({'error': 'stage required'}), 400
        try:
            out = move_lead_stage(db, MarketingLead, lead_id, stage, user_id=uid())
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/leads/<int:lead_id>/convert-estimate', methods=['POST'])
    @login_required
    def api_marketing_leads_convert(lead_id):
        from marketing_services import convert_lead_to_estimate

        try:
            out = convert_lead_to_estimate(
                db, MarketingLead, Estimate, Project, lead_id, user_id=uid(),
            )
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/pipeline')
    @login_required
    def api_marketing_pipeline():
        from marketing_services import pipeline_analytics

        return jsonify(pipeline_analytics(db, MarketingLead))

    @app.route('/api/marketing/case-studies')
    @login_required
    def api_marketing_case_studies():
        from marketing_services import list_case_studies

        status = request.args.get('status')
        return jsonify(list_case_studies(db, MarketingCaseStudy, status=status))

    @app.route('/api/marketing/case-studies/from-project', methods=['POST'])
    @login_required
    def api_marketing_case_study_build():
        from marketing_services import build_case_study_from_project

        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        try:
            out = build_case_study_from_project(
                db, MarketingCaseStudy, Project, Photo, BudgetProjectState, PayAppProjectState,
                int(project_id), user_id=uid(), title=body.get('title'),
            )
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/case-studies/<int:case_study_id>/publish', methods=['POST'])
    @login_required
    def api_marketing_case_study_publish(case_study_id):
        from marketing_services import publish_case_study

        try:
            out = publish_case_study(db, MarketingCaseStudy, case_study_id)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/assets')
    @login_required
    def api_marketing_assets():
        from marketing_services import list_marketing_assets

        project_id = request.args.get('project_id', type=int) or (
            get_current_project_id() if get_current_project_id else None
        )
        tag = request.args.get('tag')
        return jsonify(list_marketing_assets(db, MarketingAsset, Photo, project_id=project_id, tag=tag))

    @app.route('/api/marketing/assets/sync', methods=['POST'])
    @login_required
    def api_marketing_assets_sync():
        from marketing_services import sync_dam_from_project_photos

        body = request.get_json(silent=True) or {}
        project_id = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        if not project_id:
            return jsonify({'error': 'project_id required'}), 400
        out = sync_dam_from_project_photos(db, MarketingAsset, Photo, int(project_id), user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/reviews')
    @login_required
    def api_marketing_reviews():
        from marketing_services import list_reviews

        public_only = request.args.get('public_only', '').lower() in ('1', 'true', 'yes')
        return jsonify(list_reviews(db, MarketingReviewRequest, public_only=public_only))

    @app.route('/api/marketing/reviews', methods=['POST'])
    @login_required
    def api_marketing_reviews_create():
        from marketing_services import create_review_request

        body = request.get_json(silent=True) or {}
        if not body.get('project_id'):
            return jsonify({'error': 'project_id required'}), 400
        out = create_review_request(db, MarketingReviewRequest, body, user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/reviews/<int:review_id>/send', methods=['POST'])
    @login_required
    def api_marketing_reviews_send(review_id):
        from marketing_services import send_review_request_email

        body = request.get_json(silent=True) or {}
        email = body.get('email')
        try:
            out = send_review_request_email(db, MarketingReviewRequest, review_id, email)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/reviews/<int:review_id>/complete', methods=['POST'])
    @login_required
    def api_marketing_reviews_complete(review_id):
        from marketing_services import complete_review

        body = request.get_json(silent=True) or {}
        try:
            out = complete_review(db, MarketingReviewRequest, review_id, body)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/campaigns')
    @login_required
    def api_marketing_campaigns_list():
        rows = MarketingCampaign.query.order_by(MarketingCampaign.id.desc()).limit(100).all()
        from marketing_services import campaign_to_dict

        return jsonify({'campaigns': [campaign_to_dict(r) for r in rows]})

    @app.route('/api/marketing/campaigns', methods=['POST'])
    @login_required
    def api_marketing_campaigns_upsert():
        from marketing_services import upsert_campaign

        body = request.get_json(silent=True) or {}
        cid = body.get('id')
        try:
            out = upsert_campaign(db, MarketingCampaign, body, user_id=uid(), campaign_id=cid)
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/campaigns/<int:campaign_id>/send', methods=['POST'])
    @login_required
    def api_marketing_campaigns_send(campaign_id):
        from marketing_services import send_campaign

        body = request.get_json(silent=True) or {}
        try:
            out = send_campaign(
                db, MarketingCampaign, MarketingLead, campaign_id,
                test_email=body.get('test_email'),
            )
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/collateral')
    @login_required
    def api_marketing_collateral():
        from marketing_services import seed_collateral_templates

        seed_collateral_templates(db, MarketingCollateralTemplate)
        db.session.commit()
        rows = MarketingCollateralTemplate.query.order_by(MarketingCollateralTemplate.key).all()
        return jsonify({
            'templates': [
                {'id': r.id, 'key': r.key, 'name': r.name, 'body_html': r.body_html}
                for r in rows
            ],
        })

    # Public — lead capture & portfolio embed (no login)
    @app.route('/api/public/marketing/leads', methods=['POST'])
    def api_public_marketing_lead():
        from marketing_services import capture_public_lead

        body = request.get_json(silent=True) or {}
        if not (body.get('email') or body.get('phone') or body.get('contact_name') or body.get('name')):
            return jsonify({'error': 'Contact information required'}), 400
        out = capture_public_lead(db, MarketingLead, body)
        db.session.commit()
        return jsonify({'ok': True, 'lead_id': out.get('id')})

    @app.route('/public/marketing/case-study/<slug>')
    def public_marketing_case_study(slug):
        from marketing_services import published_case_study_by_slug

        data = published_case_study_by_slug(db, MarketingCaseStudy, Photo, slug)
        if not data:
            return render_template('marketing_embed.html', case_study=None, slug=slug), 404
        return render_template('marketing_embed.html', case_study=data, slug=slug)

    @app.route('/api/public/marketing/case-study/<slug>')
    def api_public_marketing_case_study(slug):
        from marketing_services import published_case_study_by_slug

        data = published_case_study_by_slug(db, MarketingCaseStudy, Photo, slug)
        if not data:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(data)
