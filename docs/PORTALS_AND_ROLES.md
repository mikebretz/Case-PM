# Portals, roles, and navigation

Case PM separates **how** people sign in from **what** they can do. Permissions still come from User Management (`permissions_catalog.py`); the portal layer controls landing pages, banners, and which sidebar links are shown by default.

## Portal types

| Portal | Typical roles | Look & feel | Default home |
|--------|---------------|-------------|--------------|
| **Staff** | PM, Superintendent, Accounting, Admin | Full Construction OS sidebar | Dashboard |
| **Owner** | Owner | Emerald banner, **Approvals & updates** hub, broader read nav | Client Portal (`/client-portal`) |
| **Architect** | Architect | Sky banner, review-focused nav (no schedule / RFQ / bid tools) | Dashboard |
| **Subcontractor** | Sub, Company User | Amber banner, pay apps & RFIs | Pay Applications |
| **Sub vendor** | Subcontractor Accountant (pay-only) | Green banner | Pay Applications |
| **Plan room** | Plan Room Bidder | Public bid site | Plan room projects |

## Owner vs Architect (both use `consultant` portal in permissions)

- **Owner** — `client_view` on most project modules; can **approve/reject** change orders; sees schedule, daily log, weekly report, safety, photos, documents, and the **Client Portal** hub. Financial modules (budget, accounting, pay apps) stay off.
- **Architect** — Focused on **review**: RFIs, submittals, drawings, documents, change orders (with approval). No schedule, estimating, RFQ portal, or external email (internal messages only).

Access checks treat **`client_view` as satisfying read-only `view`** so owner navigation and GET APIs work without granting staff-level edit rights.

## Customizing access

Admins adjust modules and approval rights per user in **User Management**. Role templates (Owner, Architect, etc.) are starting points only.

## Related code

- `permissions_catalog.py` — role templates and access levels
- `case_workflow.py` — `user_has_module_access`, `is_owner_portal_user`, `is_architect_portal_user`
- `portal_sub_access.py` — consultant/sub module allow lists, `portal_home_endpoint_for_user`
- `templates/base.html` — `portal-owner` / `portal-architect` CSS and sidebar
