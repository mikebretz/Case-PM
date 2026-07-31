# Case PM Marketing Module (Pillars 1–9)

Construction marketing ties **project delivery** to **business development**: portfolio, pipeline, portal, reputation, campaigns, DAM, proposals, web capture, and ROI analytics.

## Status

| # | Pillar | Status |
|---|--------|--------|
| 1 | Portfolio & case studies | **Live** — gallery, before/after, videos JSON, exports (HTML/embed/LinkedIn/JSON), view counts |
| 2 | Lead pipeline & bids | **Live** — RFP/bid-package linkage, lead-from-bid-package, historical close rates + forecast |
| 3 | Client portal marketing | **Live** — portal tab, review links, published case studies per project |
| 4 | Reputation & referrals | **Live** — automation rules, public review forms, referral registry, testimonial widget, syndication webhook |
| 5 | Email & SMS campaigns | **Live** — templates, tracked opens/clicks/conversions (pixel + redirect), Twilio/webhook SMS |
| 6 | Visual DAM | **Live** — search, register external/video/document assets, phase/trade/use-case filters |
| 7 | Proposals & collateral | **Live** — content library, estimate-backed proposals, public view + e-sign capture |
| 8 | Web & lead capture | **Live** — landing pages (`/public/marketing/site/<slug>`), public leads, marketing settings (GBP URL, base URL) |
| 9 | Marketing ROI | **Live** — spend entries, CPL, campaign attribution, portfolio/landing/proposal view metrics |
| 10 | External integrations | **Planned** — Houzz/Dodge/ConstructConnect native connectors |

## Key routes

Staff hub: `/marketing`

Analytics: `GET /api/marketing/dashboard` (full ROI payload)

Automation: `POST /api/marketing/automation/run` `{ "project_id": 1 }`

Proposals: `POST /api/marketing/proposals` → `GET /public/marketing/proposal/<token>`

Public review: `/public/marketing/review/<token>`

Campaign tracking: `/api/marketing/track/open/<token>.gif`, `/api/marketing/track/click/<token>?u=...`

## Configuration

Program settings section `marketing` (via `PUT /api/marketing/settings`):

- `public_base_url` — used in emails and tracked links
- `google_business_profile_url`
- `review_syndication_enabled` + optional env `CASEPM_REVIEW_SYNDICATION_WEBHOOK`

SMS: `CASEPM_TWILIO_*` or `CASEPM_SMS_WEBHOOK_URL`

## Schema

New tables created via `define_marketing_models`; existing DBs upgraded with `ensure_marketing_schema()` on startup.

## Deploy check

```bash
python3 -c "from marketing_services import marketing_deploy_check; print(marketing_deploy_check())"
```
