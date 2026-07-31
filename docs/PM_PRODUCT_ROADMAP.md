# Case PM — product roadmap (PM pillars)

This document tracks major PM capabilities agreed with stakeholders. Built-in **Accounting** and optional **Sage 300** sync remain the financial system of record; these pillars deepen field and preconstruction workflows.

## 1. Scheduling & resource leveling

- **Today:** Master schedule, delivery/permit sync to schedule lines, calendar views.
- **Next:** Resource pools (crews, equipment), leveling across projects, baseline vs actual variance exports.

## 2. BIM coordination

- **Today:** Documents and RFIs; no native model viewer.
- **Next:** IFC upload, viewpoint/clash linking to punch and RFIs, optional ACC/Forge bridge.

## 3. Estimating → budget automation

- **Today:** Budget module, publish hook to accounting (`budget_publish_accounting_wizard`), commitment → budget sync on approve.
- **Next:** Estimate revision import, automatic cost-code mapping, SOV alignment checks.

## 4. Owner / subcontractor portal depth

- **Today:** Pay applications, commitments, lien waiver tracking on pay app state, DocuSign on commitments.
- **Next:** Company-scoped waiver library, COI expiry alerts at payment time, owner draw package portal.

## 5. Mobile offline

- **Today:** Responsive daily log and field modules (online).
- **Next:** IndexedDB outbox for daily logs, photos, and timesheets; conflict resolution on reconnect.

## API

- `GET /api/pm/roadmap/status` — JSON snapshot of pillar status and integration hooks.
