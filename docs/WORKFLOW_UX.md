# Workflow UX (high impact)

## My work queue

- **Page:** `/my-work`
- **API:** `GET /api/my-work?project_id=&limit=`
- Aggregates RFIs, submittals, change orders, PCOs, pay app periods, approvals, and internal messages where the signed-in user can act (ball-in-court, assignee, or approval rights).
- Dashboard tiles **Assigned to Me** and **My Work Queue** use the same API.

## Simple view

- Toggle in the header on **Budget**, **Pay Applications**, **Change Orders**, and **Submittals**.
- Hides elements marked `data-casepm-advanced="1"`; preference stored per user in `localStorage`.

## Project guard

- `casepm-project-guard.js` syncs localStorage project id with the header and blocks mismatched API writes.
- Budget server save uses the guard before `PUT /api/budget/state`.

## Onboarding

- First-time staff users with no active project see a short welcome dialog (dismiss stored in `localStorage`).

## Email

- **Microsoft Outlook** — OAuth via Program Settings / Email.
- **Gmail** — not available via OAuth yet; use IMAP/SMTP or Outlook until a future release.
