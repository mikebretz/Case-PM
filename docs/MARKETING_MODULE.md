# Case PM Marketing Module

See pillars 1–9 in the hub at `/marketing`. This document covers **gap closure** for the full research checklist.

## Pillar 10 — Integrations (live via webhooks)

| Integration | Inbound / outbound | Endpoint / config |
|-------------|-------------------|-------------------|
| Houzz | Inbound webhook | `POST /api/public/marketing/integrations/houzz` |
| Dodge | Inbound webhook | `POST /api/public/marketing/integrations/dodge` |
| ConstructConnect | Inbound webhook | `POST /api/public/marketing/integrations/constructconnect` |
| HubSpot / Salesforce | Outbound | `CASEPM_CRM_WEBHOOK_URL` + `crm_auto_push` in marketing settings |
| BIM → DAM | Internal | `POST /api/marketing/integrations/bim-sync` |
| Won jobs ↔ projects | Internal | `POST /api/marketing/integrations/accounting-sync` |

Optional header: `X-CasePM-Marketing-Key` = `CASEPM_MARKETING_WEBHOOK_SECRET`

## Brand & awards

- `GET/POST /api/marketing/brand-kit` — logo, colors, header/footer HTML applied to exports
- `GET /api/marketing/case-studies/<id>/award-package` — branded HTML + submission checklist

## Client portal marketing pack

- `GET/PUT /api/marketing/portal-pack/<project_id>` — progress photos, auto-detected warranty/manual documents, review links, Google/Houzz/Facebook review URLs

## Proposals

- `POST /api/marketing/proposals/<id>/pdf` — generates PDF (PyMuPDF)
- `POST /api/marketing/proposals/<id>/docusign` — DocuSign envelope when configured

## Referrals

- `POST /api/marketing/referrals/<id>/issue` — generates incentive code
- `POST /api/marketing/referrals/<id>/redeem` — redeem code

## SEO & local visibility

- `GET /api/marketing/seo/audit` — checklist score
- Marketing settings: `google_place_id`, `houzz_profile_url`, `facebook_page_url`, `company_nap_json`

## Scheduled jobs

```bash
python3 scripts/marketing_scheduled_jobs.py
```

Also runs on **project status change** (automation rules). Manual: `POST /api/marketing/jobs/run`

## ITB / RFP

- `POST /api/marketing/leads/itb` — invitation-to-bid intake (alias for RFP pipeline)

## ROI (profit-aware)

Dashboard includes `won_job_attribution`, `estimated_gross_margin`, and portfolio vs delivery metrics.

## Construction market profiles

Choose a primary market (residential, commercial, government, etc.) so templates and messaging match your work. See [MARKETING_CONSTRUCTION_MARKETS.md](MARKETING_CONSTRUCTION_MARKETS.md).

## Deploy check

```bash
python3 -c "from marketing_services import marketing_deploy_check; print(marketing_deploy_check())"
```
