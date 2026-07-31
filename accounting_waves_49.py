"""
Wave 49 — PM + accounting gap closure: scheduling pools/leveling, BIM status, portal waiver library,
mobile offline handlers, estimate revision import, SOV remediation, owner draw packages, AP preflight.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def _parse_task_dates(task: dict) -> tuple[date | None, date | None]:
    for start_k, end_k in (
        ('start', 'finish'),
        ('start_date', 'end_date'),
        ('startDate', 'endDate'),
    ):
        s, e = task.get(start_k), task.get(end_k)
        if s and e:
            try:
                return date.fromisoformat(str(s)[:10]), date.fromisoformat(str(e)[:10])
            except ValueError:
                continue
    return None, None


def scheduling_resource_pools(db, models, ledger_id: int, body: dict | None = None, *, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    pools = settings.get('scheduling_resource_pools') or []
    if body and body.get('pools') is not None:
        pools = body.get('pools') or []
        settings['scheduling_resource_pools'] = pools[-100:]
        _save_ledger_settings(ledger, settings)
        write_audit(db, models, ledger_id, user_id=user_id, action='scheduling_resource_pools', details={'count': len(pools)})
    return {'pools': pools, 'count': len(pools)}


def scheduling_resource_leveling_v2(db, ScheduleData, project_id: int, *, overload_threshold: int = 3) -> dict:
    """Date-overlap aware leveling on schedule payload tasks."""
    from accounting_waves_46 import scheduling_resource_summary

    base = scheduling_resource_summary(db, ScheduleData, int(project_id))
    pid = int(project_id)
    record = ScheduleData.query.filter_by(project_id=pid).first()
    tasks = []
    if record and record.payload:
        try:
            payload = json.loads(record.payload) if isinstance(record.payload, str) else (record.payload or {})
            tasks = payload.get('tasks') or payload.get('items') or []
        except Exception:
            tasks = []
    by_resource: dict[str, list[dict]] = {}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        res = (t.get('resource') or t.get('crew') or t.get('assigned_to') or 'Unassigned').strip()
        start, end = _parse_task_dates(t)
        by_resource.setdefault(res, []).append({'task': t, 'start': start, 'end': end})
    suggestions = []
    for res, rows in by_resource.items():
        dated = [r for r in rows if r['start'] and r['end']]
        overlaps = 0
        for i, a in enumerate(dated):
            for b in dated[i + 1:]:
                if a['start'] <= b['end'] and b['start'] <= a['end']:
                    overlaps += 1
        if len(rows) >= overload_threshold or overlaps > 0:
            suggestions.append({
                'resource': res,
                'task_count': len(rows),
                'overlap_pairs': overlaps,
                'action': 'stagger_or_split',
                'detail': (
                    f'{len(rows)} tasks on "{res}"'
                    + (f' with {overlaps} overlapping date pair(s)' if overlaps else ' (high assignment count)')
                ),
            })
    return {
        **base,
        'leveling_status': 'v2_calendar',
        'overload_threshold': overload_threshold,
        'leveling_suggestions': suggestions,
    }


def scheduling_cross_project_leveling(db, ScheduleData, Project, *, limit: int = 12) -> dict:
    """Portfolio snapshot: overloaded resources across active projects."""
    projects = []
    if Project:
        projects = Project.query.filter_by(status='Active').order_by(Project.id).limit(limit).all()
    portfolio = []
    totals: dict[str, int] = {}
    for p in projects:
        snap = scheduling_resource_leveling_v2(db, ScheduleData, p.id)
        hot = [s for s in (snap.get('leveling_suggestions') or []) if s.get('overlap_pairs') or (s.get('task_count') or 0) >= 5]
        if hot:
            portfolio.append({'project_id': p.id, 'name': getattr(p, 'name', ''), 'hotspots': hot[:5]})
        for b in snap.get('resource_buckets') or []:
            name = b.get('name') or 'Unassigned'
            totals[name] = totals.get(name, 0) + int(b.get('task_count') or 0)
    cross = sorted(
        [{'resource': k, 'task_count_across_projects': v} for k, v in totals.items()],
        key=lambda x: -x['task_count_across_projects'],
    )[:20]
    return {
        'at': datetime.utcnow().isoformat() + 'Z',
        'project_count': len(projects),
        'portfolio_hotspots': portfolio,
        'cross_project_resources': cross,
        'leveling_status': 'portfolio_v1',
    }


def company_waiver_library(db, PayAppProjectState, Project, Company, *, limit_projects: int = 50) -> dict:
    """Company-scoped lien waiver index across project pay app state."""
    from pay_app_persistence import get_pay_app_state

    by_company: dict[str, dict] = {}
    q = Project.query.order_by(Project.id.desc()).limit(limit_projects) if Project else []
    for proj in q:
        if not PayAppProjectState:
            break
        _, state = get_pay_app_state(PayAppProjectState, proj.id)
        waivers = (state or {}).get('subLienWaivers') or {}
        for company_key, periods in waivers.items():
            if not isinstance(periods, dict):
                continue
            bucket = by_company.setdefault(str(company_key), {'company_id': company_key, 'waivers': [], 'projects': set()})
            bucket['projects'].add(proj.id)
            for period_key, meta in periods.items():
                if not isinstance(meta, dict):
                    continue
                bucket['waivers'].append({
                    'project_id': proj.id,
                    'project_name': getattr(proj, 'name', ''),
                    'period': period_key,
                    'filename': meta.get('filename') or meta.get('file'),
                    'uploaded_at': meta.get('uploaded_at'),
                })
    companies = []
    if Company:
        for c in Company.query.order_by(Company.name).limit(500).all():
            entry = by_company.get(str(c.id)) or {'company_id': str(c.id), 'waivers': [], 'projects': set()}
            companies.append({
                'company_id': c.id,
                'name': c.name,
                'waiver_count': len(entry.get('waivers') or []),
                'project_count': len(entry.get('projects') or []),
                'waivers': (entry.get('waivers') or [])[:25],
            })
    else:
        for cid, entry in by_company.items():
            companies.append({
                'company_id': cid,
                'name': cid,
                'waiver_count': len(entry.get('waivers') or []),
                'project_count': len(entry.get('projects') or []),
                'waivers': entry.get('waivers')[:25],
            })
    return {'at': datetime.utcnow().isoformat() + 'Z', 'companies': companies, 'company_count': len(companies)}


def portal_compliance_library_enhanced(db, Company, COI, *, PayAppProjectState=None, Project=None) -> dict:
    from accounting_waves_46 import _portal_compliance_library_legacy

    base = _portal_compliance_library_legacy(db, Company, COI)
    today = date.today()
    soon = today + timedelta(days=30)
    for row in base.get('companies') or []:
        cid = row.get('company_id')
        expiring = []
        if COI and cid:
            for coi in COI.query.filter_by(company_id=cid).all():
                exp = getattr(coi, 'expiration_date', None) or getattr(coi, 'expiration', None)
                if not exp:
                    expiring.append({'coi_id': coi.id, 'status': 'missing_expiration'})
                elif exp < today:
                    row['coi_valid'] = False
                    expiring.append({'coi_id': coi.id, 'status': 'expired', 'expiration': exp.isoformat()})
                elif exp <= soon:
                    expiring.append({'coi_id': coi.id, 'status': 'expiring_soon', 'expiration': exp.isoformat()})
        row['coi_alerts'] = expiring[:5]
        row['payment_blocked_if_invalid'] = not row.get('coi_valid', False)
    waivers = company_waiver_library(db, PayAppProjectState, Project, Company) if PayAppProjectState else {'companies': []}
    waiver_by_id = {str(c['company_id']): c for c in waivers.get('companies') or []}
    for row in base.get('companies') or []:
        w = waiver_by_id.get(str(row.get('company_id'))) or {}
        row['waiver_count'] = w.get('waiver_count', 0)
        row['recent_waivers'] = w.get('waivers') or []
    base['waiver_library'] = True
    return base


def mobile_offline_process_item(
    db, models, ledger_id: int, item: dict, *, user_id=None, DailyLog=None, EquipmentEntry=None, Project=None,
) -> dict:
    from accounting_waves_46 import field_silent_auto_post_daily_log

    kind = item.get('kind')
    idem = (item.get('idempotency_key') or item.get('client_id') or '')[:80]
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    done = settings.get('mobile_offline_processed') or {}
    if idem and idem in done:
        return {'skipped': 'already_processed', 'idempotency_key': idem}

    if kind == 'daily_log' and item.get('daily_log_id'):
        out = field_silent_auto_post_daily_log(
            db, models, ledger_id, int(item['daily_log_id']), user_id=user_id,
            EquipmentEntry=EquipmentEntry, DailyLog=DailyLog, Project=Project,
        )
    elif kind == 'timesheet' and item.get('timesheet_id'):
        labor = round(float(item.get('labor_cost') or item.get('amount') or 0), 2)
        pid = int(item.get('project_id') or 0)
        if labor > 0 and pid:
            from accounting_waves_43 import post_timesheet_with_burden_gl

            out = post_timesheet_with_burden_gl(
                db, models, ledger_id, pid, labor,
                timesheet_ref=f"ts-{item['timesheet_id']}",
                user_id=user_id,
            )
        else:
            out = {'skipped': 'timesheet_missing_amount_or_project'}
    elif kind == 'photo':
        gallery = settings.get('mobile_offline_photos') or []
        gallery.append({
            'daily_log_id': item.get('daily_log_id'),
            'caption': (item.get('caption') or '')[:200],
            'stored_ref': (item.get('stored_ref') or item.get('filename') or '')[:200],
            'at': datetime.utcnow().isoformat() + 'Z',
        })
        settings['mobile_offline_photos'] = gallery[-200:]
        _save_ledger_settings(ledger, settings)
        out = {'stored': True, 'gallery_size': len(settings['mobile_offline_photos'])}
    else:
        return {'skipped': 'unsupported_kind', 'kind': kind}

    if idem:
        done[idem] = {'at': datetime.utcnow().isoformat() + 'Z', 'kind': kind}
        settings['mobile_offline_processed'] = {k: done[k] for k in list(done.keys())[-500:]}
        _save_ledger_settings(ledger, settings)
    return out


def mobile_offline_process_queue_v2(
    db, models, ledger_id: int, *, user_id=None, DailyLog=None, EquipmentEntry=None, Project=None,
) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = list(settings.get('mobile_offline_queue') or [])
    processed = []
    remaining = []
    for item in q:
        try:
            out = mobile_offline_process_item(
                db, models, ledger_id, item, user_id=user_id,
                DailyLog=DailyLog, EquipmentEntry=EquipmentEntry, Project=Project,
            )
            if out.get('skipped') == 'unsupported_kind':
                remaining.append(item)
            else:
                processed.append({'item': item, 'result': out})
        except Exception as exc:
            remaining.append(item)
            processed.append({'item': item, 'error': str(exc)[:300]})
    settings['mobile_offline_queue'] = remaining
    _save_ledger_settings(ledger, settings)
    return {'processed': len(processed), 'remaining': len(remaining), 'details': processed[:30]}


def sov_alignment_remediate_budget_to_sov(
    db, project_id: int, *, BudgetProjectState=None, PayAppProjectState=None, user_id=None,
) -> dict:
    """Add budget-only SOV lines from published budget (amounts only)."""
    from accounting_waves_48 import estimate_sov_alignment_report
    from budget_persistence import get_budget_state, normalize_cost_code
    from pay_app_persistence import get_pay_app_state, save_pay_app_state

    report = estimate_sov_alignment_report(db, int(project_id), BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState)
    if report.get('ok'):
        return {'project_id': int(project_id), 'added': 0, 'ok': True}
    _, budget = get_budget_state(BudgetProjectState, int(project_id)) if BudgetProjectState else (None, {})
    _, pay = get_pay_app_state(PayAppProjectState, int(project_id), db=db) if PayAppProjectState else (None, {})
    pay = pay or {}
    sov = list(pay.get('contractorSOV') or [])
    existing = {normalize_cost_code(l.get('cost_code')) for l in sov if isinstance(l, dict)}
    added = []
    for line in (budget or {}).get('budgetLines') or []:
        if not isinstance(line, dict):
            continue
        norm = normalize_cost_code(line.get('cost_code'))
        if not norm or norm in existing:
            continue
        amt = round(float(line.get('original_budget') or line.get('original') or 0), 2)
        amt += round(float(line.get('approved_changes') or line.get('change_orders') or 0), 2)
        if amt <= 0:
            continue
        sov.append({
            'cost_code': line.get('cost_code') or norm,
            'description': (line.get('description') or '')[:120],
            'original': amt,
            'co_amount': 0,
            'source': 'budget_align',
        })
        existing.add(norm)
        added.append(line.get('cost_code') or norm)
    if added and PayAppProjectState:
        pay['contractorSOV'] = sov
        save_pay_app_state(PayAppProjectState, db, int(project_id), pay, user_id=user_id)
    after = estimate_sov_alignment_report(db, int(project_id), BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState)
    return {'project_id': int(project_id), 'added': len(added), 'cost_codes': added[:40], 'after': after}


def import_estimate_revision_csv(
    Estimate, EstimateLine, estimate_id: int, csv_text: str, db, *, user_id=None, replace: bool = False,
) -> dict:
    """Import estimate revision lines from CSV (cost_code, description, quantity, unit_cost)."""
    from estimate_persistence import recalc_estimate_totals

    est = Estimate.query.get(int(estimate_id))
    if not est:
        raise ValueError('Estimate not found')
    reader = csv.DictReader(io.StringIO(csv_text))
    if replace:
        EstimateLine.query.filter_by(estimate_id=est.id).delete()
        db.session.flush()
    created = 0
    sort = EstimateLine.query.filter_by(estimate_id=est.id).count()
    for row in reader:
        cc = (row.get('cost_code') or row.get('Cost Code') or '').strip()
        if not cc:
            continue
        qty = float(row.get('quantity') or row.get('qty') or 0)
        unit = float(row.get('unit_cost') or row.get('unit') or 0)
        ext = round(qty * unit, 2)
        sort += 1
        line = EstimateLine(
            estimate_id=est.id,
            sort_order=sort,
            cost_code=cc[:40],
            description=(row.get('description') or row.get('Description') or '')[:300],
            quantity=qty,
            unit_cost=unit,
            extended_cost=ext,
            source='revision_import',
        )
        db.session.add(line)
        created += 1
    recalc_estimate_totals(Estimate, EstimateLine, est.id)
    meta = json.loads(est.settings_json or '{}') if est.settings_json else {}
    meta['last_revision_import_at'] = datetime.utcnow().isoformat() + 'Z'
    meta['last_revision_import_lines'] = created
    est.settings_json = json.dumps(meta)
    est.updated_at = datetime.utcnow()
    return {'estimate_id': est.id, 'lines_created': created, 'replace': replace}


def create_owner_draw_package_from_g702(
    db, models, ledger_id: int, project_id: int, period_number, *, user_id=None,
    PayAppProjectState=None, ClientPortalDrawRequest=None, Project=None,
) -> dict:
    from pay_app_persistence import get_pay_app_state

    if not ClientPortalDrawRequest or not PayAppProjectState:
        raise ValueError('Client portal or pay app module not available')
    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    periods = state.get('periods') or state.get('payAppPeriods') or []
    if isinstance(periods, dict):
        periods = list(periods.values())
    period = next(
        (p for p in periods if str(p.get('periodNumber') or p.get('period_number') or p.get('id')) == str(period_number)),
        None,
    )
    if not period:
        raise ValueError('Pay application period not found')
    amt = float(period.get('currentPaymentDue') or period.get('current_payment_due') or period.get('amountDue') or 0)
    title = f"Owner draw — period {period_number}"
    package = {
        'type': 'g702_draw_package',
        'project_id': int(project_id),
        'period_number': str(period_number),
        'amount': round(amt, 2),
        'status': period.get('status'),
        'documents': [
            {'label': 'G702 summary', 'path': f'/pay-applications?project_id={project_id}&period={period_number}'},
            {'label': 'Accounting AR', 'path': f'/accounting?project_id={project_id}'},
        ],
        'created_at': datetime.utcnow().isoformat() + 'Z',
    }
    row = ClientPortalDrawRequest(
        project_id=int(project_id),
        title=title[:300],
        amount=round(amt, 2),
        period=str(period_number)[:40],
        status='Pending',
        notes=json.dumps(package)[:4000],
    )
    db.session.add(row)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='owner_draw_package', details={'draw_id': row.id, **package})
    return {'draw_request_id': row.id, 'package': package}


def ap_payment_compliance_preflight(
    db, models, ledger_id: int, vendor_id: int, applications: list, *,
    PayAppProjectState=None, Project=None, Company=None, COI=None, company_id: int | None = None,
) -> dict:
    from accounting_waves_45 import ap_payment_compliance_hold

    hold = ap_payment_compliance_hold(
        db, models, ledger_id, int(vendor_id), applications or [],
        PayAppProjectState=PayAppProjectState, Project=Project, Company=Company, COI=COI, company_id=company_id,
    )
    return {
        'ok': not hold.get('held'),
        'held': hold.get('held'),
        'holds': hold.get('holds') or [],
        'vendor_id': int(vendor_id),
    }


def bim_coordination_status_live(db, models, ledger_id: int, *, OperationsBimAsset=None, project_id: int | None = None) -> dict:
    from accounting_waves_46 import _bim_coordination_status_legacy

    base = _bim_coordination_status_legacy(db, models, ledger_id)
    asset_count = 0
    if OperationsBimAsset:
        q = OperationsBimAsset.query
        if project_id:
            q = q.filter_by(project_id=int(project_id))
        asset_count = q.count()
    viewer = 'operations_glb_pdf' if asset_count else 'upload_required'
    base.update({
        'status': 'live' if asset_count else 'foundation',
        'viewer': viewer,
        'bim_asset_count': asset_count,
        'viewer_url_hint': '/bim-viewer',
    })
    return base


def pm_accounting_gap_closure_deploy_check() -> dict:
    checks = {}
    try:
        assert callable(scheduling_resource_leveling_v2)
        assert callable(company_waiver_library)
        assert callable(mobile_offline_process_queue_v2)
        assert callable(sov_alignment_remediate_budget_to_sov)
        assert callable(import_estimate_revision_csv)
        assert callable(create_owner_draw_package_from_g702)
        assert callable(ap_payment_compliance_preflight)
        checks['wave_49'] = True
    except Exception as exc:
        checks['wave_49'] = str(exc)[:120]
    from sage300_catalog import SAGE300_MODULES

    codes = {m.get('code') for m in SAGE300_MODULES}
    checks['sage_jc_cp_catalog'] = 'JC' in codes and 'CP' in codes
    return {'ok': all(v is True for v in checks.values()), 'checks': checks}
