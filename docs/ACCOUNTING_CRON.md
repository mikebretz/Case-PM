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
