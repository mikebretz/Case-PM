# Sage 300 cutover checklist (Case PM built-in accounting + optional sync)

Use this before pointing production traffic at Sage sync or declaring go-live.

## Prerequisites

- `CASEPM_CRON_SECRET` set on the server
- SMTP configured if using scheduled accounting reports
- Program Settings → Accounting: review auto-post flags (or run **Apply CRE auto-post** in Accounting)

## Steps

1. **Test connection** — Program Settings → Sage → Test Connection; Accounting → **Sage setup** health.
2. **Pull fiscal calendar** — `POST /api/accounting/sage/fiscal/pull` or cron `pm-sage-depth`.
3. **Vendor / job maps** — Companies → Sage lookup; resolve conflicts (Accounting → Sage conflicts).
4. **Flush construction queue** — Accounting → Sage ops / `POST /api/accounting/sage/construction/flush-queue` in a test project.
5. **PJ reconcile** — Pull PJ + portfolio/cost-code reconcile for a pilot job.
6. **Integration health** — Grade ≥ 75; resolve G702 pending and AP push errors.
7. **Go-live alerts** — `GET /api/accounting/sage/go-live-alerts` or cron `go-live-alerts`.
8. **Smoke** — `PYTHONPATH=. python3 scripts/test_accounting_smoke.py` on the deploy host.
9. **Cutover API** — `GET /api/accounting/sage/cutover-checklist` (all steps green).

## API

- `GET /api/accounting/sage/cutover-checklist` — persisted snapshot on ledger
- `GET /api/accounting/sage/parity-matrix` — module read/write/conflict matrix (wave 47)
- `POST /api/accounting/cron/operations-bundle` — refresh cutover + alerts (cron)

See also `docs/DEPLOY_OPERATIONS.md` and `docs/ACCOUNTING_CRON.md`.
