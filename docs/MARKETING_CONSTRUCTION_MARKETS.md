# Construction market profiles (marketing)

Case PM marketing is **segmented by construction market** so messaging, lead sources, templates, and landing content match how your firm actually builds.

## Supported markets (top segments)

| ID | Label | Typical focus |
|----|--------|----------------|
| `residential` | Residential | Remodel, custom homes, Houzz/referrals |
| `multifamily` | Multifamily residential | Developers, schedule, repeat work |
| `commercial` | Commercial | Office, retail, RFP/portfolio |
| `government` | Government / public | Procurement, compliance, public refs |
| `industrial` | Industrial | Plants, DCs, technical delivery |
| `healthcare` | Healthcare | Occupied facilities, ICRA |
| `education` | Education | K-12, campus, bond programs |
| `infrastructure` | Infrastructure / heavy civil | DOT, utilities, public works |
| `specialty_trade` | Specialty trade / subcontractor | GC partners, trade expertise |

## Configure

1. Open **Marketing** → **Construction market profile** (top of page).
2. Choose your **primary** market.
3. Click **Apply marketing scheme** — seeds market-specific campaign templates, content blocks, and updates the default landing page hero/SEO.

Settings stored in `program_settings.json` → `marketing`:

- `primary_construction_market`
- `secondary_construction_markets` (optional list for mixed firms)

## APIs

- `GET /api/marketing/construction-markets` — catalog
- `GET /api/marketing/market-scheme` — active profile + recommendations
- `POST /api/marketing/market-scheme/apply` — apply templates for a market
- `PUT /api/marketing/settings` — save market ids; pass `"apply_market_scheme": true` to apply in one step

## Leads

New leads default `construction_market` and recommended **source** from the active primary market (override per lead in API/UI).

## Extending

Add markets in `marketing_construction_markets.py` (`CONSTRUCTION_MARKETS`). Each profile defines lead sources, campaign themes, content pillars, SEO focus, and portal tone so future marketing waves stay consistent.
