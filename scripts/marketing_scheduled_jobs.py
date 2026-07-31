#!/usr/bin/env python3
"""Run marketing automation (closeout reviews, milestones). Schedule via cron or Task Scheduler."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    import app as app_mod
    from marketing_gaps import run_scheduled_marketing_jobs

    with app_mod.app.app_context():
        models = {
            'MarketingLead': app_mod.MarketingLead,
            'MarketingCaseStudy': app_mod.MarketingCaseStudy,
            'MarketingCampaign': app_mod.MarketingCampaign,
            'MarketingReviewRequest': app_mod.MarketingReviewRequest,
            'MarketingAsset': app_mod.MarketingAsset,
            'MarketingCollateralTemplate': app_mod.MarketingCollateralTemplate,
            'MarketingCampaignRecipient': app_mod.MarketingCampaignRecipient,
            'MarketingAutomationRule': app_mod.MarketingAutomationRule,
            'MarketingReferral': app_mod.MarketingReferral,
            'MarketingProposal': app_mod.MarketingProposal,
            'MarketingContentBlock': app_mod.MarketingContentBlock,
            'MarketingLandingPage': app_mod.MarketingLandingPage,
            'MarketingSpend': app_mod.MarketingSpend,
            'MarketingCampaignTemplate': app_mod.MarketingCampaignTemplate,
            'MarketingBrandKit': app_mod.MarketingBrandKit,
            'MarketingPortalPack': app_mod.MarketingPortalPack,
            'Estimate': app_mod.Estimate,
            'EstimateLine': app_mod.EstimateLine,
            'Project': app_mod.Project,
        }
        out = run_scheduled_marketing_jobs(app_mod.db, models, app_mod.Project)
        app_mod.db.session.commit()
        print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
