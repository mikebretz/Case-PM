"""Preconstruction estimating — persistence, RFP workflow, takeoff import, budget award."""
from __future__ import annotations

import json
from datetime import datetime

from budget_persistence import get_budget_state, normalize_cost_code, save_budget_state


ESTIMATE_STATUSES = ('Draft', 'In Progress', 'Out for Bid', 'Leveling', 'Awarded', 'Archived', 'Lost')
BID_PACKAGE_STATUSES = ('Draft', 'Open', 'Closed', 'Awarded')
INVITATION_STATUSES = ('Draft', 'Sent', 'Viewed', 'Quoted', 'Declined', 'Not Interested', 'Awarded')


def _parse_json(text, default=None):
    if default is None:
        default = []
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default


def _line_extended(qty, unit_cost):
    return round(float(qty or 0) * float(unit_cost or 0), 2)


def recalc_estimate_totals(Estimate, EstimateLine, estimate_id, EstimateAlternate=None):
    """Recompute direct cost and loaded total from worksheet lines + markups."""
    est = Estimate.query.get(estimate_id)
    if not est:
        return None
    from estimate_features import included_alternate_keys, line_counts_in_base
    included = included_alternate_keys(EstimateAlternate, estimate_id) if EstimateAlternate else set()
    lines = EstimateLine.query.filter_by(estimate_id=estimate_id).all()
    direct = sum(
        float(l.extended_cost or 0)
        for l in lines
        if line_counts_in_base(l, included)
    )
    est.direct_cost_total = direct
    cont = float(est.contingency_pct or 0) / 100.0
    oh = float(est.overhead_pct or 0) / 100.0
    profit = float(est.profit_pct or 0) / 100.0
    tax = float(est.tax_pct or 0) / 100.0
    subtotal = direct * (1 + cont + oh + profit)
    est.total_amount = round(subtotal * (1 + tax), 2)
    est.updated_at = datetime.utcnow()
    return est


def estimate_line_to_dict(line):
    return {
        'id': line.id,
        'estimate_id': line.estimate_id,
        'bid_package_id': line.bid_package_id,
        'sort_order': line.sort_order or 0,
        'cost_code': line.cost_code or '',
        'division': line.division or '',
        'spec_section': line.spec_section or '',
        'description': line.description or '',
        'cost_type': line.cost_type or 'Subcontract',
        'unit': line.unit or 'EA',
        'quantity': float(line.quantity or 0),
        'unit_cost': float(line.unit_cost or 0),
        'extended_cost': float(line.extended_cost or 0),
        'source': line.source or 'manual',
        'source_ref': line.source_ref or '',
        'notes': line.notes or '',
    }


def invitation_to_dict(inv, quote_lines=None):
    return {
        'id': inv.id,
        'bid_package_id': inv.bid_package_id,
        'company_id': inv.company_id or '',
        'company_name': inv.company_name or '',
        'contact_email': inv.contact_email or '',
        'contact_name': inv.contact_name or '',
        'status': inv.status or 'Draft',
        'sent_at': inv.sent_at.isoformat() if inv.sent_at else None,
        'responded_at': inv.responded_at.isoformat() if inv.responded_at else None,
        'quote_amount': float(inv.quote_amount or 0),
        'quote_notes': inv.quote_notes or '',
        'decline_reason': inv.decline_reason or '',
        'quote_lines': quote_lines or [],
    }


def bid_package_to_dict(pkg, invitations=None, lines=None):
    return {
        'id': pkg.id,
        'estimate_id': pkg.estimate_id,
        'project_id': pkg.project_id,
        'number': pkg.number or '',
        'title': pkg.title or '',
        'spec_section': pkg.spec_section or '',
        'division': pkg.division or '',
        'description': pkg.description or '',
        'scope_notes': pkg.scope_notes or '',
        'status': pkg.status or 'Draft',
        'due_date': pkg.due_date.isoformat() if pkg.due_date else None,
        'awarded_invitation_id': pkg.awarded_invitation_id,
        'drawing_refs': _parse_json(pkg.drawing_refs_json, []),
        'spec_refs': _parse_json(pkg.spec_refs_json, []),
        'invitations': invitations or [],
        'lines': lines or [],
    }


def estimate_to_dict(est, lines=None, bid_packages=None, settings=None):
    payload = {
        'id': est.id,
        'project_id': est.project_id,
        'number': est.number or '',
        'title': est.title or '',
        'description': est.description or '',
        'status': est.status or 'Draft',
        'estimate_type': est.estimate_type or 'Hard Bid',
        'bid_date': est.bid_date.isoformat() if est.bid_date else None,
        'due_date': est.due_date.isoformat() if est.due_date else None,
        'contingency_pct': float(est.contingency_pct or 0),
        'overhead_pct': float(est.overhead_pct or 0),
        'profit_pct': float(est.profit_pct or 0),
        'tax_pct': float(est.tax_pct or 0),
        'direct_cost_total': float(est.direct_cost_total or 0),
        'total_amount': float(est.total_amount or 0),
        'awarded_at': est.awarded_at.isoformat() if est.awarded_at else None,
        'pushed_to_budget_at': est.pushed_to_budget_at.isoformat() if est.pushed_to_budget_at else None,
        'assumptions': _parse_json(est.assumptions_json, []),
        'attachments': _parse_json(est.attachments_json, []),
        'created_at': est.created_at.isoformat() if est.created_at else None,
        'updated_at': est.updated_at.isoformat() if est.updated_at else None,
        'lines': lines or [],
        'bid_packages': bid_packages or [],
    }
    if settings is not None:
        payload['settings'] = settings
    return payload


def apply_estimate_fields(est, data):
    for field in ('title', 'description', 'status', 'estimate_type'):
        if field in data and data[field] is not None:
            setattr(est, field, data[field])
    for field in ('contingency_pct', 'overhead_pct', 'profit_pct', 'tax_pct'):
        if field in data and data[field] is not None:
            setattr(est, field, float(data[field] or 0))
    for field in ('bid_date', 'due_date'):
        if field in data and data[field]:
            try:
                setattr(est, field, datetime.strptime(str(data[field])[:10], '%Y-%m-%d').date())
            except ValueError:
                pass
    if 'assumptions' in data:
        est.assumptions_json = json.dumps(data['assumptions'] or [])
    if 'attachments' in data:
        est.attachments_json = json.dumps(data['attachments'] or [])
    est.updated_at = datetime.utcnow()


def apply_estimate_line_fields(line, data):
    for field in ('cost_code', 'division', 'spec_section', 'description', 'cost_type', 'unit', 'source', 'source_ref', 'notes'):
        if field in data:
            setattr(line, field, data[field] or '')
    if 'bid_package_id' in data:
        line.bid_package_id = data['bid_package_id'] or None
    if 'sort_order' in data:
        line.sort_order = int(data['sort_order'] or 0)
    if 'quantity' in data:
        line.quantity = float(data['quantity'] or 0)
    if 'unit_cost' in data:
        line.unit_cost = float(data['unit_cost'] or 0)
    line.extended_cost = _line_extended(line.quantity, line.unit_cost)
    line.updated_at = datetime.utcnow()


def save_estimate_lines(EstimateLine, estimate_id, rows, db):
    """Replace all worksheet lines when rows list provided."""
    if rows is None:
        return
    EstimateLine.query.filter_by(estimate_id=estimate_id).delete()
    for i, row in enumerate(rows):
        line = EstimateLine(estimate_id=estimate_id, sort_order=i)
        apply_estimate_line_fields(line, row)
        db.session.add(line)


def apply_bid_package_fields(pkg, data):
    for field in ('title', 'description', 'scope_notes', 'status', 'spec_section', 'division'):
        if field in data:
            setattr(pkg, field, data[field] or '')
    if 'due_date' in data and data['due_date']:
        try:
            pkg.due_date = datetime.strptime(str(data['due_date'])[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    if 'drawing_refs' in data:
        pkg.drawing_refs_json = json.dumps(data['drawing_refs'] or [])
    if 'spec_refs' in data:
        pkg.spec_refs_json = json.dumps(data['spec_refs'] or [])
    pkg.updated_at = datetime.utcnow()


def apply_invitation_fields(inv, data):
    for field in ('company_id', 'company_name', 'contact_email', 'contact_name', 'status', 'quote_notes', 'decline_reason'):
        if field in data:
            setattr(inv, field, data[field] or '')
    if 'quote_amount' in data:
        inv.quote_amount = float(data['quote_amount'] or 0)
    inv.updated_at = datetime.utcnow()


def import_takeoff_to_estimate(EstimateLine, estimate_id, takeoff_items, db, bid_package_id=None, default_cost_code='01-000'):
    """Create estimate lines from drawing takeoff measurements."""
    imported = []
    existing_refs = {
        (l.source_ref or '')
        for l in EstimateLine.query.filter_by(estimate_id=estimate_id, source='takeoff').all()
    }
    sort_base = EstimateLine.query.filter_by(estimate_id=estimate_id).count()
    for i, item in enumerate(takeoff_items):
        ref = f"takeoff:{item.get('markup_id')}"
        if ref in existing_refs:
            continue
        qty = float(item.get('quantity') or 0)
        unit = item.get('unit') or 'ft'
        desc = item.get('description') or f"Takeoff from {item.get('sheet_number', 'sheet')}"
        line = EstimateLine(
            estimate_id=estimate_id,
            bid_package_id=bid_package_id,
            sort_order=sort_base + i,
            cost_code=default_cost_code,
            description=desc[:500],
            cost_type='Subcontract',
            unit=unit,
            quantity=qty,
            unit_cost=0,
            extended_cost=0,
            source='takeoff',
            source_ref=ref,
            notes=f"Sheet {item.get('sheet_number', '')} · {qty} {unit}",
        )
        db.session.add(line)
        imported.append(line)
    return imported


def aggregate_lines_by_cost_code(lines):
    """Roll up estimate lines for budget push."""
    buckets = {}
    for line in lines:
        code = (line.cost_code or '01-000').strip() or '01-000'
        key = (normalize_cost_code(code), (line.cost_type or 'Subcontract').strip())
        if key not in buckets:
            buckets[key] = {
                'cost_code': code,
                'cost_type': key[1],
                'description': line.description or f'Estimate — {code}',
                'amount': 0.0,
            }
        buckets[key]['amount'] += float(line.extended_cost or 0)
    return list(buckets.values())


def award_estimate_to_budget(
    Estimate,
    EstimateLine,
    BidPackage,
    BidInvitation,
    BudgetProjectState,
    db,
    estimate_id,
    user_id=None,
    use_bid_awards=False,
    EstimateBudgetMapping=None,
):
    """
    Push finalized estimate into project budget original_budget lines.
    When use_bid_awards=True, awarded bid package quotes override worksheet amounts per spec section.
    """
    est = Estimate.query.get_or_404(estimate_id)
    if est.status not in ('Awarded', 'Leveling', 'Out for Bid', 'In Progress'):
        est.status = 'Awarded'
    lines = EstimateLine.query.filter_by(estimate_id=estimate_id).order_by(EstimateLine.sort_order).all()
    rollups = aggregate_lines_by_cost_code(lines)

    if use_bid_awards:
        packages = BidPackage.query.filter_by(estimate_id=estimate_id, status='Awarded').all()
        for pkg in packages:
            inv_id = pkg.awarded_invitation_id
            if not inv_id:
                continue
            inv = BidInvitation.query.get(inv_id)
            if not inv or float(inv.quote_amount or 0) <= 0:
                continue
            code = pkg.spec_section or pkg.division or pkg.number or '01-000'
            rollups.append({
                'cost_code': code,
                'cost_type': 'Subcontract',
                'description': pkg.title or f'Awarded bid {pkg.number}',
                'amount': float(inv.quote_amount),
                'spec_section': pkg.spec_section or '',
            })

    if EstimateBudgetMapping:
        from estimate_features import apply_budget_mappings
        rollups = apply_budget_mappings(EstimateBudgetMapping, est.project_id, rollups)

    record, state = get_budget_state(BudgetProjectState, est.project_id)
    budget_lines = list(state.get('budgetLines') or [])
    audit = list(state.get('budgetAuditLog') or [])
    updated = 0
    created = 0

    for row in rollups:
        amt = float(row.get('amount') or 0)
        if amt <= 0:
            continue
        code = row.get('cost_code') or '01-000'
        ctype = row.get('cost_type') or 'Subcontract'
        target = normalize_cost_code(code)
        match = next(
            (l for l in budget_lines if normalize_cost_code(l.get('cost_code')) == target and (l.get('cost_type') or '') == ctype),
            None,
        )
        if match:
            match['original_budget'] = float(match.get('original_budget') or 0) + amt
            match['notes'] = (match.get('notes') or '') + f"\nEstimate {est.number} award +{amt:.2f}"
            updated += 1
        else:
            budget_lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000) + created,
                'cost_code': code,
                'description': row.get('description') or f'Estimate {est.number}',
                'cost_type': ctype,
                'original_budget': amt,
                'approved_changes': 0,
                'pending': 0,
                'notes': f'From estimate {est.number}',
                'actual': 0,
                'syncStatus': 'Not Synced',
                'percent_complete': 0,
                'source': 'estimate_award',
                'estimate_id': est.id,
            })
            created += 1

    audit.append({
        'timestamp': datetime.utcnow().isoformat(),
        'action': 'ESTIMATE_AWARDED_TO_BUDGET',
        'user_id': user_id,
        'details': {'estimate_id': est.id, 'estimate_number': est.number, 'updated': updated, 'created': created},
    })
    state['budgetLines'] = budget_lines
    state['budgetAuditLog'] = audit
    save_budget_state(BudgetProjectState, db, est.project_id, state, user_id)

    est.awarded_at = est.awarded_at or datetime.utcnow()
    est.pushed_to_budget_at = datetime.utcnow()
    est.pushed_to_budget_by_id = user_id
    est.status = 'Awarded'
    est.updated_at = datetime.utcnow()
    db.session.commit()
    return {'updated': updated, 'created': created, 'lines_pushed': updated + created}


def bid_leveling_matrix(BidPackage, BidInvitation, estimate_id):
    """Build comparison grid: packages × invited vendors."""
    packages = BidPackage.query.filter_by(estimate_id=estimate_id).order_by(BidPackage.number).all()
    matrix = []
    for pkg in packages:
        invitations = BidInvitation.query.filter_by(bid_package_id=pkg.id).all()
        row = {
            'package': bid_package_to_dict(pkg),
            'bids': [
                {
                    'invitation_id': inv.id,
                    'company_name': inv.company_name,
                    'status': inv.status,
                    'quote_amount': float(inv.quote_amount or 0),
                    'is_low': False,
                    'is_awarded': inv.id == pkg.awarded_invitation_id,
                }
                for inv in invitations
                if inv.status in ('Quoted', 'Awarded')
            ],
        }
        quoted = [b for b in row['bids'] if b['quote_amount'] > 0]
        if quoted:
            low = min(quoted, key=lambda b: b['quote_amount'])
            low['is_low'] = True
        matrix.append(row)
    return matrix


def notify_bid_invitations(
    project_id,
    invitations,
    bid_package,
    User,
    title=None,
    notify_mode='both',
    estimate=None,
    Project=None,
):
    """Mass-notify vendors/subs for an RFP bid package (in-app, email, both, or none)."""
    mode = (notify_mode or 'both').lower()
    if mode not in ('both', 'in_app', 'email', 'none'):
        mode = 'both'
    if mode == 'none' or not invitations:
        return
    try:
        from email_notifications import notify_user_workflow, send_workflow_email
        from estimate_features import get_estimate_settings, render_rfp_email

        action_url = f'/estimate-portal?project_id={project_id}&package_id={bid_package.id}'
        title = title or f'{bid_package.number} — RFP invitation: {bid_package.title}'
        description = bid_package.description or bid_package.scope_notes or 'Please review and submit your bid.'
        send_in_app = mode in ('both', 'in_app')
        send_email = mode in ('both', 'email')
        users = User.query.filter_by(status='Active').all()
        project = Project.query.get(project_id) if Project and project_id else None
        template = get_estimate_settings(estimate).get('rfp_email_template') if estimate else None
        portal_url = action_url if action_url.startswith('http') else None
        if portal_url is None:
            try:
                from email_notifications import _base_url
                portal_url = f'{_base_url()}{action_url}'
            except Exception:
                portal_url = action_url
        if template and project:
            email_subj, email_body = render_rfp_email(template, project, bid_package, portal_url)
        else:
            email_subj, email_body = title, description

        emailed = set()
        for inv in invitations:
            cid = str(getattr(inv, 'company_id', '') or '').strip()
            cname = (getattr(inv, 'company_name', '') or '').strip()
            email = (getattr(inv, 'contact_email', '') or '').strip().lower()
            targets = []
            for u in users:
                if cid and str(getattr(u, 'company_id', '') or '') == cid:
                    targets.append(u)
                elif cname and (getattr(u, 'company', '') or '').strip() == cname:
                    targets.append(u)
                elif email and (getattr(u, 'email', '') or '').strip().lower() == email:
                    targets.append(u)
            if send_in_app:
                seen = set()
                for u in targets:
                    if u.id in seen:
                        continue
                    seen.add(u.id)
                    notify_user_workflow(
                        u,
                        title=title,
                        description=description,
                        action_url=action_url,
                        project_id=project_id,
                        module='Estimating',
                        send_email=False,
                    )
            if send_email and email and email not in emailed:
                emailed.add(email)
                send_workflow_email(
                    email,
                    email_subj,
                    f'<div style="font-family:sans-serif"><p>{email_body.replace(chr(10), "<br>")}</p>'
                    f'<p><a href="{portal_url}">Open bid portal</a></p></div>',
                    email_body,
                )
    except Exception:
        pass


def companies_for_spec_trade(Company, spec_section=None, trade=None):
    """Find vendor companies matching spec section or trade."""
    q = Company.query
    companies = q.order_by(Company.name).all()
    spec = (spec_section or '').replace(' ', '').upper()
    trade_q = (trade or '').strip().lower()
    results = []
    for c in companies:
        ctrade = (c.trade or '').strip().lower()
        details = _parse_json(c.details_json, {})
        trades = [t.lower() for t in (details.get('trades') or [])]
        spec_sections = [s.replace(' ', '').upper() for s in (details.get('spec_sections') or [])]
        if spec and spec in spec_sections:
            results.append(c)
        elif trade_q and (trade_q in ctrade or trade_q in trades):
            results.append(c)
        elif not spec and not trade_q:
            results.append(c)
    return results
