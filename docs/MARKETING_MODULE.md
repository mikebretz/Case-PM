# Case PM Marketing Module

Construction-focused marketing ties **project delivery data** to business development: portfolio, pipeline, reputation, campaigns, and visual assets—without maintaining a separate generic CRM.

## Pillars (research alignment)

| Pillar | Status | Implementation |
|--------|--------|----------------|
| Project portfolio & case studies | Live | `build_case_study_from_project`, publish + public embed |
| Lead & opportunity pipeline | Live | Stages inquiry → won/lost, analytics, convert to estimate/project |
| Client portal + marketing | Live | Complements Client Portal; review requests post-close |
| Reputation & referrals | Live | `MarketingReviewRequest`, email trigger, public testimonials flag |
| Email campaigns | Live | Segmented sends via `send_workflow_email` |
| Visual DAM | Live | Sync from `Photo`, tags and use-cases |
| Proposal & collateral | Partial | `MarketingCollateralTemplate` seed templates |
| Website & lead capture | Partial | `POST /api/public/marketing/leads`, public case study URLs |
| Marketing ROI dashboards | Live | `/api/marketing/dashboard` |
| Houzz / Dodge / CRM integrations | Planned | Catalog only |

## Routes

### Staff (login required)

- `GET /marketing` — UI hub
- `GET /api/marketing/catalog` — pillar catalog + seed collateral
- `GET /api/marketing/dashboard` — ROI + pipeline summary
- `GET|POST /api/marketing/leads` — CRUD pipeline
- `POST /api/marketing/leads/<id>/stage` — move stage
- `POST /api/marketing/leads/<id>/convert-estimate` — won path into PM/estimating
- `GET /api/marketing/case-studies` — list
- `POST /api/marketing/case-studies/from-project` — auto-build from project + photos
- `POST /api/marketing/case-studies/<id>/publish`
- `GET /api/marketing/assets`, `POST /api/marketing/assets/sync`
- Reviews & campaigns under `/api/marketing/reviews` and `/api/marketing/campaigns`

### Public (CSRF exempt)

- `POST /api/public/marketing/leads` — website form intake
- `GET /public/marketing/case-study/<slug>` — embeddable HTML
- `GET /api/public/marketing/case-study/<slug>` — JSON for integrations

## Permissions

Module key: `marketing` with sub-keys `marketing_pipeline`, `marketing_portfolio`, `marketing_campaigns`, `marketing_reputation`, `marketing_assets` (see `permissions_catalog.py`).

## Data model

Defined in `marketing_models.py` via `define_marketing_models(db)`:

- `MarketingLead`, `MarketingCaseStudy`, `MarketingCampaign`, `MarketingReviewRequest`, `MarketingAsset`, `MarketingCollateralTemplate`

Tables are created with `db.create_all()` on startup.

## Deploy check

```python
from marketing_services import marketing_deploy_check
marketing_deploy_check()  # {'ok': True}
```
