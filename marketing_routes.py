"""Construction marketing — portfolio, pipeline, campaigns, reputation, DAM."""

from flask import render_template


def register_marketing_routes(app, deps):
    db = deps['db']
    login_required = deps['login_required']
    current_user = deps['current_user']
    get_current_project_id = deps.get('get_current_project_id')
    jsonify = deps['jsonify']
    request = deps['request']
    get_active_project = deps['get_active_project']
    MarketingLead = deps['MarketingLead']
    MarketingCaseStudy = deps['MarketingCaseStudy']
    MarketingCampaign = deps['MarketingCampaign']
    MarketingReviewRequest = deps['MarketingReviewRequest']
    MarketingAsset = deps['MarketingAsset']
    MarketingCollateralTemplate = deps['MarketingCollateralTemplate']
    MarketingCampaignRecipient = deps['MarketingCampaignRecipient']
    MarketingAutomationRule = deps['MarketingAutomationRule']
    MarketingReferral = deps['MarketingReferral']
    MarketingProposal = deps['MarketingProposal']
    MarketingContentBlock = deps['MarketingContentBlock']
    MarketingLandingPage = deps['MarketingLandingPage']
    MarketingSpend = deps['MarketingSpend']
    MarketingCampaignTemplate = deps['MarketingCampaignTemplate']
    MarketingBrandKit = deps['MarketingBrandKit']
    MarketingPortalPack = deps['MarketingPortalPack']
    Project = deps['Project']
    Photo = deps['Photo']
    Document = deps.get('Document')
    OperationsBimAsset = deps.get('OperationsBimAsset')
    Estimate = deps['Estimate']
    EstimateLine = deps.get('EstimateLine')
    BidPackage = deps.get('BidPackage')
    BudgetProjectState = deps.get('BudgetProjectState')
    PayAppProjectState = deps.get('PayAppProjectState')

    def models():
        return {
            'MarketingLead': MarketingLead,
            'MarketingCaseStudy': MarketingCaseStudy,
            'MarketingCampaign': MarketingCampaign,
            'MarketingReviewRequest': MarketingReviewRequest,
            'MarketingAsset': MarketingAsset,
            'MarketingCollateralTemplate': MarketingCollateralTemplate,
            'MarketingCampaignRecipient': MarketingCampaignRecipient,
            'MarketingAutomationRule': MarketingAutomationRule,
            'MarketingReferral': MarketingReferral,
            'MarketingProposal': MarketingProposal,
            'MarketingContentBlock': MarketingContentBlock,
            'MarketingLandingPage': MarketingLandingPage,
            'MarketingSpend': MarketingSpend,
            'MarketingCampaignTemplate': MarketingCampaignTemplate,
            'MarketingBrandKit': MarketingBrandKit,
            'MarketingPortalPack': MarketingPortalPack,
            'Estimate': Estimate,
            'EstimateLine': EstimateLine,
            'Project': Project,
            'Photo': Photo,
            'Document': Document,
            'OperationsBimAsset': OperationsBimAsset,
            'BudgetProjectState': BudgetProjectState,
        }

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
        from marketing_pillars import seed_marketing_defaults

        seed_collateral_templates(db, MarketingCollateralTemplate)
        seed_marketing_defaults(db, models())
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
        from marketing_pillars import marketing_analytics_full

        return jsonify(marketing_analytics_full(db, models()))

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
        from marketing_pillars import send_campaign_tracked

        body = request.get_json(silent=True) or {}
        try:
            out = send_campaign_tracked(db, models(), campaign_id, test_email=body.get('test_email'))
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

    @app.route('/api/marketing/client-portal')
    @login_required
    def api_marketing_client_portal_bundle():
        from marketing_pillars import enrich_client_portal_feed
        pid = request.args.get('project_id', type=int) or (get_current_project_id() if get_current_project_id else None)
        base = {}
        enrich_client_portal_feed(db, models(), base, pid)
        return jsonify(base.get('marketing') or {})

    @app.route('/api/marketing/pipeline/forecast')
    @login_required
    def api_marketing_pipeline_forecast():
        from marketing_pillars import pipeline_forecast_advanced
        return jsonify(pipeline_forecast_advanced(db, MarketingLead))

    @app.route('/api/marketing/leads/<int:lead_id>/link-bid-package', methods=['POST'])
    @login_required
    def api_marketing_link_bid(lead_id):
        from marketing_pillars import link_lead_to_bid_package
        body = request.get_json(silent=True) or {}
        if not body.get('bid_package_id') or not BidPackage:
            return jsonify({'error': 'bid_package_id required'}), 400
        try:
            out = link_lead_to_bid_package(db, MarketingLead, BidPackage, Estimate, lead_id, int(body['bid_package_id']))
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/leads/from-bid-package', methods=['POST'])
    @login_required
    def api_marketing_lead_from_bid():
        from marketing_pillars import create_lead_from_bid_package
        body = request.get_json(silent=True) or {}
        if not body.get('bid_package_id'):
            return jsonify({'error': 'bid_package_id required'}), 400
        out = create_lead_from_bid_package(db, MarketingLead, BidPackage, Estimate, int(body['bid_package_id']), user_id=uid(), contact=body)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/case-studies/<int:case_study_id>', methods=['PATCH'])
    @login_required
    def api_marketing_case_study_update(case_study_id):
        from marketing_pillars import enrich_case_study_from_project, export_case_study_bundle
        body = request.get_json(silent=True) or {}
        row = MarketingCaseStudy.query.get(int(case_study_id))
        if not row:
            return jsonify({'error': 'Not found'}), 404
        out = enrich_case_study_from_project(db, MarketingCaseStudy, row, Project, Photo, body=body)
        photos = Photo.query.filter_by(project_id=row.project_id).limit(12).all() if Photo else []
        out['exports'] = export_case_study_bundle(row, photos)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/case-studies/<int:case_study_id>/exports')
    @login_required
    def api_marketing_case_study_exports(case_study_id):
        from marketing_pillars import export_case_study_bundle
        row = MarketingCaseStudy.query.get(int(case_study_id))
        if not row:
            return jsonify({'error': 'Not found'}), 404
        photos = Photo.query.filter_by(project_id=row.project_id).limit(12).all() if Photo else []
        return jsonify(export_case_study_bundle(row, photos))

    @app.route('/api/marketing/automation/run', methods=['POST'])
    @login_required
    def api_marketing_automation_run():
        from marketing_pillars import run_project_automation
        body = request.get_json(silent=True) or {}
        pid = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        if not pid:
            return jsonify({'error': 'project_id required'}), 400
        out = run_project_automation(db, models(), Project, project_id=int(pid), user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/referrals', methods=['GET', 'POST'])
    @login_required
    def api_marketing_referrals():
        from marketing_pillars import list_referrals, register_referral
        if request.method == 'GET':
            return jsonify(list_referrals(db, MarketingReferral))
        body = request.get_json(silent=True) or {}
        out = register_referral(db, MarketingReferral, MarketingLead, body, user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/assets/search')
    @login_required
    def api_marketing_assets_search():
        from marketing_pillars import search_assets
        return jsonify(search_assets(
            db, MarketingAsset, Photo,
            q=request.args.get('q') or '',
            project_id=request.args.get('project_id', type=int),
            trade=request.args.get('trade'),
            phase=request.args.get('phase'),
            use_case=request.args.get('use_case'),
        ))

    @app.route('/api/marketing/assets/register', methods=['POST'])
    @login_required
    def api_marketing_assets_register():
        from marketing_pillars import register_asset
        out = register_asset(db, MarketingAsset, request.get_json(silent=True) or {}, user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/content-blocks')
    @login_required
    def api_marketing_content_blocks():
        rows = MarketingContentBlock.query.order_by(MarketingContentBlock.sort_order, MarketingContentBlock.id).all()
        return jsonify({'blocks': [{
            'id': r.id, 'category': r.category, 'title': r.title, 'body_html': r.body_html,
        } for r in rows]})

    @app.route('/api/marketing/proposals', methods=['GET', 'POST'])
    @login_required
    def api_marketing_proposals():
        from marketing_pillars import build_proposal_from_estimate, proposal_to_dict
        if request.method == 'GET':
            rows = MarketingProposal.query.order_by(MarketingProposal.id.desc()).limit(50).all()
            return jsonify({'proposals': [proposal_to_dict(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        if not body.get('estimate_id'):
            return jsonify({'error': 'estimate_id required'}), 400
        out = build_proposal_from_estimate(db, models(), int(body['estimate_id']), lead_id=body.get('lead_id'), user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/proposals/<int:proposal_id>/send', methods=['POST'])
    @login_required
    def api_marketing_proposals_send(proposal_id):
        from marketing_pillars import send_proposal_email
        body = request.get_json(silent=True) or {}
        if not body.get('email'):
            return jsonify({'error': 'email required'}), 400
        out = send_proposal_email(db, MarketingProposal, proposal_id, body['email'])
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/landing-pages', methods=['GET', 'POST'])
    @login_required
    def api_marketing_landing_pages():
        from marketing_pillars import upsert_landing_page, landing_page_to_dict, default_landing_page
        if request.method == 'GET':
            default_landing_page(db, MarketingLandingPage, MarketingCaseStudy)
            db.session.commit()
            rows = MarketingLandingPage.query.order_by(MarketingLandingPage.id.desc()).limit(50).all()
            return jsonify({'pages': [landing_page_to_dict(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        out = upsert_landing_page(db, MarketingLandingPage, body, page_id=body.get('id'))
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/spend', methods=['GET', 'POST'])
    @login_required
    def api_marketing_spend():
        from marketing_pillars import record_spend
        if request.method == 'GET':
            rows = MarketingSpend.query.order_by(MarketingSpend.id.desc()).limit(100).all()
            return jsonify({'entries': [{'id': r.id, 'channel': r.channel, 'label': r.label, 'amount': r.amount, 'campaign_id': r.campaign_id} for r in rows]})
        out = record_spend(db, MarketingSpend, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/construction-markets')
    @login_required
    def api_marketing_construction_markets():
        from marketing_construction_markets import construction_markets_catalog
        return jsonify(construction_markets_catalog())

    @app.route('/api/marketing/market-scheme')
    @login_required
    def api_marketing_market_scheme():
        from marketing_construction_markets import marketing_scheme_payload
        from marketing_pillars import load_marketing_settings
        return jsonify(marketing_scheme_payload(load_marketing_settings()))

    @app.route('/api/marketing/market-scheme/apply', methods=['POST'])
    @login_required
    def api_marketing_market_scheme_apply():
        from marketing_construction_markets import apply_construction_market_scheme
        from marketing_pillars import load_marketing_settings, save_marketing_settings
        body = request.get_json(silent=True) or {}
        primary = body.get('primary_construction_market') or load_marketing_settings().get('primary_construction_market')
        secondary = body.get('secondary_construction_markets') or []
        save_marketing_settings({
            'primary_construction_market': primary,
            'secondary_construction_markets': secondary,
        })
        out = apply_construction_market_scheme(db, models(), primary, secondary=secondary)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/settings', methods=['GET', 'PUT'])
    @login_required
    def api_marketing_settings():
        from marketing_pillars import load_marketing_settings, save_marketing_settings
        if request.method == 'GET':
            from marketing_construction_markets import marketing_scheme_payload
            settings = load_marketing_settings()
            return jsonify({'settings': settings, 'scheme': marketing_scheme_payload(settings)})
        body = request.get_json(silent=True) or {}
        saved = save_marketing_settings(body)
        if body.get('apply_market_scheme'):
            from marketing_construction_markets import apply_construction_market_scheme
            apply_construction_market_scheme(
                db, models(),
                saved.get('primary_construction_market') or 'commercial',
                secondary=saved.get('secondary_construction_markets') or [],
            )
            db.session.commit()
        return jsonify({'settings': saved})

    @app.route('/api/marketing/testimonials/widget')
    @login_required
    def api_marketing_testimonials():
        from marketing_pillars import testimonial_widget
        return jsonify(testimonial_widget(db, MarketingReviewRequest))

    @app.route('/api/marketing/reviews/syndicate', methods=['POST'])
    @login_required
    def api_marketing_syndicate():
        from marketing_pillars import syndicate_reviews
        return jsonify(syndicate_reviews(db, MarketingReviewRequest))

    @app.route('/api/marketing/campaign-templates')
    @login_required
    def api_marketing_campaign_templates():
        rows = MarketingCampaignTemplate.query.order_by(MarketingCampaignTemplate.key).all()
        return jsonify({'templates': [{'key': r.key, 'name': r.name, 'subject': r.subject, 'channel': r.channel} for r in rows]})

    @app.route('/api/marketing/brand-kit', methods=['GET', 'POST', 'PUT'])
    @login_required
    def api_marketing_brand_kit():
        from marketing_gaps import default_brand_kit, upsert_brand_kit
        if request.method == 'GET':
            default_brand_kit(db, MarketingBrandKit)
            db.session.commit()
            rows = MarketingBrandKit.query.all()
            from marketing_gaps import brand_kit_to_dict
            return jsonify({'kits': [brand_kit_to_dict(r) for r in rows]})
        body = request.get_json(silent=True) or {}
        out = upsert_brand_kit(db, MarketingBrandKit, body, kit_id=body.get('id'))
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/portal-pack/<int:project_id>', methods=['GET', 'PUT'])
    @login_required
    def api_marketing_portal_pack(project_id):
        from marketing_gaps import build_portal_marketing_pack, upsert_portal_pack
        if request.method == 'GET':
            return jsonify(build_portal_marketing_pack(db, models(), project_id))
        upsert_portal_pack(db, MarketingPortalPack, project_id, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify(build_portal_marketing_pack(db, models(), project_id))

    @app.route('/api/marketing/case-studies/<int:case_study_id>/award-package')
    @login_required
    def api_marketing_award_package(case_study_id):
        from marketing_gaps import case_study_award_package
        return jsonify(case_study_award_package(db, MarketingCaseStudy, MarketingBrandKit, case_study_id, Photo))

    @app.route('/api/marketing/proposals/<int:proposal_id>/pdf', methods=['POST'])
    @login_required
    def api_marketing_proposal_pdf(proposal_id):
        from marketing_gaps import build_proposal_pdf, save_proposal_pdf
        row = MarketingProposal.query.get_or_404(proposal_id)
        path = save_proposal_pdf(row, build_proposal_pdf(row))
        db.session.commit()
        return jsonify({'pdf_path': path})

    @app.route('/api/marketing/proposals/<int:proposal_id>/docusign', methods=['POST'])
    @login_required
    def api_marketing_proposal_docusign(proposal_id):
        from marketing_gaps import send_proposal_docusign
        body = request.get_json(silent=True) or {}
        if not body.get('email'):
            return jsonify({'error': 'email required'}), 400
        out = send_proposal_docusign(db, MarketingProposal, proposal_id, body['email'], body.get('name') or '')
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/referrals/<int:referral_id>/issue', methods=['POST'])
    @login_required
    def api_marketing_referral_issue(referral_id):
        from marketing_gaps import issue_referral_incentive
        out = issue_referral_incentive(db, MarketingReferral, request.get_json(silent=True) or {}, referral_id=referral_id)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/referrals/<int:referral_id>/redeem', methods=['POST'])
    @login_required
    def api_marketing_referral_redeem(referral_id):
        from marketing_gaps import redeem_referral_incentive
        body = request.get_json(silent=True) or {}
        try:
            out = redeem_referral_incentive(db, MarketingReferral, referral_id, body.get('code') or '')
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/api/marketing/seo/audit')
    @login_required
    def api_marketing_seo_audit():
        from marketing_gaps import local_seo_audit
        return jsonify(local_seo_audit(db, MarketingLandingPage, MarketingCaseStudy))

    @app.route('/api/marketing/integrations/catalog')
    @login_required
    def api_marketing_integrations_catalog():
        from marketing_integrations import integration_catalog
        return jsonify(integration_catalog())

    @app.route('/api/marketing/integrations/bim-sync', methods=['POST'])
    @login_required
    def api_marketing_bim_sync():
        from marketing_integrations import sync_bim_assets_to_dam
        body = request.get_json(silent=True) or {}
        pid = body.get('project_id') or (get_current_project_id() if get_current_project_id else None)
        if not pid:
            return jsonify({'error': 'project_id required'}), 400
        out = sync_bim_assets_to_dam(db, models(), int(pid), user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/integrations/accounting-sync', methods=['POST'])
    @login_required
    def api_marketing_accounting_sync():
        from marketing_integrations import sync_accounting_won_signal
        out = sync_accounting_won_signal(db, MarketingLead, Project)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/leads/itb', methods=['POST'])
    @login_required
    def api_marketing_itb_lead():
        from marketing_gaps import create_itb_lead
        out = create_itb_lead(db, MarketingLead, request.get_json(silent=True) or {}, user_id=uid())
        db.session.commit()
        return jsonify(out)

    @app.route('/api/marketing/jobs/run', methods=['POST'])
    @login_required
    def api_marketing_jobs_run():
        from marketing_gaps import run_scheduled_marketing_jobs
        out = run_scheduled_marketing_jobs(db, models(), Project)
        db.session.commit()
        return jsonify(out)

    @app.route('/api/public/marketing/integrations/<source>', methods=['POST'])
    def api_public_marketing_integration(source):
        from marketing_integrations import ingest_integration_lead, _verify_webhook_secret
        if source not in ('houzz', 'dodge', 'constructconnect'):
            return jsonify({'error': 'Unknown integration'}), 404
        if not _verify_webhook_secret(request.headers):
            return jsonify({'error': 'Unauthorized'}), 401
        out = ingest_integration_lead(db, MarketingLead, request.get_json(silent=True) or {}, source)
        db.session.commit()
        return jsonify({'ok': True, 'lead': out})

    @app.route('/api/marketing/track/open/<token>.gif')
    def api_marketing_track_open(token):
        from marketing_pillars import track_campaign_open
        from flask import Response
        track_campaign_open(db, MarketingCampaignRecipient, token)
        db.session.commit()
        pixel = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        return Response(pixel, mimetype='image/gif')

    @app.route('/api/marketing/track/click/<token>')
    def api_marketing_track_click(token):
        from marketing_pillars import track_campaign_click
        from flask import redirect
        url = request.args.get('u') or '/'
        track_campaign_click(db, MarketingCampaignRecipient, MarketingLead, token)
        db.session.commit()
        return redirect(url)

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
        from marketing_pillars import record_case_study_view

        record_case_study_view(db, MarketingCaseStudy, slug)
        db.session.commit()
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

    @app.route('/public/marketing/site/<slug>')
    def public_marketing_site(slug):
        from marketing_pillars import record_landing_view, landing_page_to_dict
        data = record_landing_view(db, MarketingLandingPage, slug)
        if not data:
            return render_template('marketing_site.html', page=None), 404
        db.session.commit()
        return render_template('marketing_site.html', page=data)

    @app.route('/public/marketing/review/<token>')
    def public_marketing_review(token):
        from marketing_pillars import public_review_form
        data = public_review_form(db, MarketingReviewRequest, token)
        return render_template('marketing_review.html', review=data, token=token)

    @app.route('/api/public/marketing/review/<token>', methods=['GET', 'POST'])
    def api_public_marketing_review(token):
        from marketing_pillars import public_review_form, complete_public_review
        if request.method == 'GET':
            data = public_review_form(db, MarketingReviewRequest, token)
            if not data:
                return jsonify({'error': 'Not found'}), 404
            return jsonify(data)
        try:
            out = complete_public_review(db, MarketingReviewRequest, token, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    @app.route('/public/marketing/proposal/<token>')
    def public_marketing_proposal(token):
        from marketing_pillars import record_proposal_view
        data = record_proposal_view(db, MarketingProposal, token)
        if not data:
            return render_template('marketing_proposal.html', proposal=None), 404
        db.session.commit()
        return render_template('marketing_proposal.html', proposal=data, token=token)

    @app.route('/api/public/marketing/proposal/<token>/sign', methods=['POST'])
    def api_public_proposal_sign(token):
        from marketing_pillars import sign_proposal_token
        try:
            out = sign_proposal_token(db, MarketingProposal, token, request.get_json(silent=True) or {})
            db.session.commit()
            return jsonify(out)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
