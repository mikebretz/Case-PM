# Case PM — deploy & operations (accounting + Sage)

## A — Ship and operate

1. Deploy `main` (includes waves 43–47).
2. Run smoke: `PYTHONPATH=. python3 scripts/test_accounting_smoke.py`.
3. Program Settings → Accounting:
   - Enable construction auto-post flags as needed
   - **Silent server auto-post** + equipment/delivery prompts if field should post without dialogs
4. Schedule crons (see `docs/ACCOUNTING_CRON.md`):
   - `run-scheduled-reports`
   - `pm-sage-depth`
   - `go-live-alerts`
   - `operations-bundle` (cutover snapshot + alerts)
5. Interactive cutover: open Accounting → **Construction sync** module → **Cutover checklist** / **Sage parity**.

## B — Construction loop

- **Pending construction** panel (Accounting → Construction sync)
- Delivery modal: **Accounting receipt $** field
- Full integration tests: `scripts/test_accounting_construction_full.py`

## C — PM pillars

- Estimating: **Roll to budget + accounting** button
- Sub portal: `/sub-compliance` — lien waiver + COI upload
- Mobile: `static/js/mobile-offline-outbox.js` + service worker flush
- Scheduling: `GET /api/pm/scheduling/leveling?project_id=`
- BIM: `/bim-viewer?project_id=&asset_id=`

## D — Sage parity

- `GET /api/accounting/sage/parity-matrix` — gaps highlighted for PJ/JC/CP modules
