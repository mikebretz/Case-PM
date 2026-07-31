# Case PM Accounting — scheduled reports (cron)

Nightly or weekly email of saved accounting reports uses SMTP from **Program Settings** (email mirror).

## Environment

Set on the server PC or cloud host:

```bash
CASEPM_CRON_SECRET=your-long-random-secret
```

## HTTP call

```http
POST /api/accounting/cron/run-scheduled-reports
X-CasePM-Cron-Secret: your-long-random-secret
Content-Type: application/json

{}
```

Response includes per-ledger schedule run status (`emailed`, `email_failed:…`, etc.). Failures are also stored under **Accounting → Reports → schedule alerts** (`/api/accounting/reports/schedule-alerts`).

## Windows Task Scheduler (example)

Program: `curl.exe`  
Arguments:

```text
-s -X POST -H "X-CasePM-Cron-Secret: YOUR_SECRET" http://127.0.0.1:5000/api/accounting/cron/run-scheduled-reports
```

Run daily at 6:00 AM on the machine where `RUN-AS-SERVER.bat` is active.

## Linux cron (example)

```cron
0 6 * * * curl -s -X POST -H "X-CasePM-Cron-Secret: YOUR_SECRET" http://127.0.0.1:5000/api/accounting/cron/run-scheduled-reports
```

## Startup guard

Before starting the server, run:

```bash
PYTHONPATH=. python3 scripts/accounting_startup_guard.py
```

`RUN-AS-SERVER.bat` and Case PM Desktop run this automatically when possible.

## Wave 10 maintenance (optional)

Same secret. Runs scheduled reports plus compliance reminder emails and admin notification for recent schedule failures:

```http
POST /api/accounting/cron/wave10
X-CasePM-Cron-Secret: your-long-random-secret
```

Set **admin notification email** under Program Settings → Email so failure and compliance digests have a recipient.

## Wave 11 maintenance (optional)

Runs wave 10 maintenance, Sage queue flush, Plaid auto-import (7 days), and scheduled reports:

```http
POST /api/accounting/cron/wave11
X-CasePM-Cron-Secret: your-long-random-secret
```

## Wave 12 maintenance (optional)

Wave 11 plus Sage ops admin email when conflicts/errors exist:

```http
POST /api/accounting/cron/wave12
X-CasePM-Cron-Secret: your-long-random-secret
```

Post-deploy check (authenticated API or script):

```bash
PYTHONPATH=. python3 scripts/deploy_accounting_check.py
```

## Wave 13 maintenance (optional)

Same secret as wave 12. Runs wave 12 maintenance (wave 11 → wave 10 chain); per-project retainage, closeout, and month-end cash workflows use the authenticated APIs:

```http
POST /api/accounting/cron/wave13
X-CasePM-Cron-Secret: your-long-random-secret
```

## Sage mirror maintenance (waves 14–19, optional)

Runs wave 13 cron chain plus Sage queue flush and mirror coverage check:

```http
POST /api/accounting/cron/sage-mirror
X-CasePM-Cron-Secret: your-long-random-secret
```

Use **Accounting → Integrations** mirror buttons for customer/AR/AP payment/G/L push, bank/tax pull, CRE job reconcile, and module coverage report (`/api/accounting/sage/mirror/coverage`).

## Sage mirror full maintenance (waves 20–24, optional)

Runs wave 14–19 mirror cron, portfolio job reconcile, and optional Sage paces when `SAGE_API_URL` is set:

```http
POST /api/accounting/cron/sage-mirror-full
X-CasePM-Cron-Secret: your-long-random-secret
```

## Sage mirror complete (waves 25–28, optional)

Pull AR/AP status, auto-retry inbox, optional paces (`CASEPM_RUN_SAGE_PACES=1`):

```http
POST /api/accounting/cron/sage-mirror-complete
X-CasePM-Cron-Secret: your-long-random-secret
```
