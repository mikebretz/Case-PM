# CRE auto-post profile (construction accounting)

Case PM can post approved construction financials into the built-in ledger automatically. For new CRE deployments, apply the recommended profile once (admin).

## Apply profile

**API:** `POST /api/accounting/platform/apply-cre-autopost-profile` (authenticated)

**Program settings:** Accounting section flags (also editable in Program Settings → Accounting).

## Flags enabled

| Flag | Effect |
|------|--------|
| `auto_post_enabled` | Master switch for construction posting |
| `g702_post_on_approve` | Owner pay app (G702) → A/R + revenue G/L on approve |
| `sub_pay_app_post_on_approve` | Sub pay apps → A/P on approve |
| `commitment_post_on_approve` | Commitments → encumbrance / A/P hooks |
| `co_post_on_approve` | Owner change orders → contract value G/L |
| `timesheet_post_on_approve` | Timesheets → labor G/L (fail-loud if G/L cannot post) |
| `direct_cost_post_on_approve` | Direct costs → job expense G/L (fail-loud) |
| `auto_wip_on_billing_sync` | WIP adjustment when billing variance exceeds threshold |
| `retainage_accounting_enabled` | Retainage splits on sub pay apps |

## Timesheets and direct costs

Posting a timesheet or direct cost to job cost **requires** a successful G/L batch. If chart of accounts is missing required accounts (e.g. `5000`, `2300`, `5200`, `2000`), the post **raises an error** and does not complete — fix COA under Accounting → G/L.

Idempotency keys: `timesheet-{id}`, `direct-cost-{id}` (safe to retry).

## Integration health

Use **Accounting → Sage hybrid → Integration health** or `GET /api/accounting/integration/health` to see G702 pending sync, Sage push inbox errors, and G/L subledger tie-out in one view.

## Sage (optional)

Auto-post runs in Case PM first. Sage hybrid sync is separate; configure Web API URL and hybrid system-of-record under Program Settings → Sage 300.
