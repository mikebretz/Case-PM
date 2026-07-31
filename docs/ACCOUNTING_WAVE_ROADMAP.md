# Accounting Sage mirror — roadmap waves 1–96

Implementation is spread across `accounting_waves_17.py` … `accounting_waves_42.py` and `accounting_wave_registry.py`.

| Waves | Module file | Theme |
|-------|-------------|--------|
| 1–13 | 17–23 | Core accounting + construction |
| 14–19 | 24 | Sage mirror foundation |
| 20–24 | 25 | Mirror hardening |
| 25–28 | 26 | Production close + enterprise |
| 29–32 | 27 | SoR, drift, licensed modules |
| 33–36 | 28 | Packs, drift UX, month-close |
| 37–40 | 29 | Tax, distribution, FA, PR |
| 41–44 | 30 | CRE, consolidation, report packs |
| 45–48 | 31 | Bank/cash |
| 49, 61, 65, 69 | 34 | Cross-module GL/tax/FA/matrix |
| 50–52 | 35 | GL tie-out, FX, security |
| 53–56 | 32 | CRE bridge |
| 57–60 | 33 (+36 depth) | Distribution |
| 62–64 | 37 | Filing, PR, WH-347 |
| 62 (complete) | 39 | 941/1099 + amendment loop |
| 66–68 | 38 | JC/FA, retainage, WIP GL |
| 70–77 | 39 | IC, optional fields, BI, approvals, FX, segments |
| 78–85 | 40 | ISV, cert, scale, DR, SOC2, webhooks |
| 86–93 | 41 | Field maps, OData, errors, residency, fixtures |
| 94–96 | 42 | SLA, migrations, go-live sign-off |

Status API: `GET /api/accounting/roadmap/status`

Deploy check: `sage_mirror_deploy_check_v12()` in `accounting_waves_42.py`.
