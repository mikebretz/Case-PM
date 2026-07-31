# Case PM — product roadmap (PM pillars)

Built-in **Accounting** and optional **Sage 300** sync remain the financial system of record. PM pillars below are **live** as of wave 49 (gap-closure).

## 1. Scheduling & resource leveling

- **Live:** Master schedule, delivery/permit sync, `GET /api/pm/scheduling/leveling` (calendar overlap v2), `GET /api/pm/scheduling/cross-project-leveling`, resource pools `GET|POST /api/pm/scheduling/resource-pools`.

## 2. BIM coordination

- **Live:** `/bim-viewer` with GLB/GLTF/PDF preview, Operations BIM assets, viewpoint registry, 4D slider in Operations Center.
- **Note:** Native in-browser IFC without conversion is not included; upload GLB or download IFC.

## 3. Estimating → budget automation

- **Live:** Auto-pipeline, `POST /api/estimates/<id>/import-revision` (CSV), SOV alignment + `POST /api/accounting/estimating/sov-alignment/remediate`.

## 4. Owner / subcontractor portal depth

- **Live:** Sub compliance portal, enhanced compliance library (COI expiry alerts), `GET /api/portal/waiver-library`, AP `POST /api/accounting/ap/compliance-preflight`, owner draw packages `POST /api/accounting/construction/owner-draw-package`.

## 5. Mobile offline

- **Live:** IndexedDB outbox processes daily log, timesheet (G/L), and photo metadata with idempotency keys.

## API

- `GET /api/pm/roadmap/status` — JSON snapshot of pillar status and integration hooks.
- `GET /api/accounting/construction/pending-dashboard` — pending G702, sub AP, commitments, COs.
- `POST /api/accounting/construction/sync-all-pending` — one-click sync for active project.
- `GET /api/accounting/sage/go-live-alerts` — Sage go-live readiness snapshot.

## Operations (not product gaps)

Sage go-live still requires server configuration: credentials, cron (`docs/ACCOUNTING_CRON.md`), CRE auto-post profile, and smoke tests on the deploy host. Agency tax e-file remains an audit log in Case PM — confirm filings with your CPA or filing service.
