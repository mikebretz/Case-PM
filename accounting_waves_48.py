"""
Wave 48 — Sage cutover hardening (email + playbook), construction integration pack hooks,
estimating SOV alignment, parity matrix prioritized gaps + auto-fix top actions.
"""
from __future__ import annotations

import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def sage_go_live_email_digest(db, models, ledger_id: int, *, min_alerts: int = 1) -> dict:
    """Email admin when go-live / cutover alerts are present (SMTP via program settings)."""
    from program_settings_persistence import load_program_settings
    from email_notifications import send_workflow_email
    from accounting_waves_46 import sage_go_live_alert_bundle
    from accounting_waves_47 import sage_cutover_checklist

    bundle = sage_go_live_alert_bundle(db, models, ledger_id)
    checklist = sage_cutover_checklist(db, models, ledger_id)
    alerts = bundle.get('alerts') or []
    critical = [a for a in alerts if a.get('severity') in ('critical', 'error')]
    if len(alerts) < min_alerts and checklist.get('ready'):
        return {'sent': False, 'reason': 'no_digest_needed', 'alert_count': len(alerts), 'ready': True}

    prog = load_program_settings()
    email = ((prog.get('email') or {}).get('admin_notification_email') or '').strip()
    if not email:
        return {'sent': False, 'reason': 'no_admin_email', 'alert_count': len(alerts)}

    lines = []
    for a in alerts[:25]:
        lines.append(f"- [{a.get('severity')}] {a.get('code')}: {str(a.get('detail', ''))[:180]}")
    cut_fail = [s for s in (checklist.get('steps') or []) if not s.get('ok')]
    for s in cut_fail[:12]:
        lines.append(f"- [cutover] {s.get('label')}")
    body = (
        f"Case PM Sage go-live digest (ledger {ledger_id})\n"
        f"Health: {bundle.get('health', {}).get('grade')} ({bundle.get('health', {}).get('score')})\n"
        f"Cutover ready: {checklist.get('ready')}\n"
        f"Alerts: {len(alerts)} ({len(critical)} critical/error)\n\n"
        + '\n'.join(lines or ['(no detail)'])
    )
    subject = 'Case PM — Sage go-live alert digest'
    if critical:
        subject = 'Case PM — URGENT Sage go-live alerts'
    sent = send_workflow_email(email, subject, f'<pre>{body}</pre>', body)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('sage_go_live_email_log') or []
    entry = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'sent': sent,
        'alert_count': len(alerts),
        'critical_count': len(critical),
        'cutover_ready': checklist.get('ready'),
    }
    log.append(entry)
    settings['sage_go_live_email_log'] = log[-30:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, action='sage_go_live_email_digest', details=entry)
    return {'sent': sent, **entry}


def cron_go_live_email_digest(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    runs = []
    for ledger in models['AcctLedger'].query.limit(10).all():
        runs.append({'ledger_id': ledger.id, **sage_go_live_email_digest(db, models, ledger.id)})
    return {'ledgers': runs}


def sage_cutover_conflict_playbook(
    db, models, ledger_id: int, body: dict | None = None, *, user_id=None, Project=None,
) -> dict:
    """
    Cutover playbook: auto-resolve vendor name conflicts (winner=sage), optional AP push + construction flush.
    """
    from accounting_waves_19 import resolve_sage_vendor_conflict, sage_vendor_conflict_review
    from accounting_waves_25 import sage_push_open_ap_idempotent
    from accounting_waves_27 import flush_construction_mirror_queue
    from accounting_waves_46 import sage_go_live_alert_bundle

    body = body or {}
    winner = (body.get('winner') or 'sage').lower()
    resolve_vendors = body.get('resolve_vendor_conflicts', True)
    push_ap = body.get('retry_ap_push', True)
    flush_queue = body.get('flush_construction_queue', True)
    project_id = body.get('project_id')

    resolved = []
    if resolve_vendors:
        review = sage_vendor_conflict_review(db, models, ledger_id, limit=100)
        for c in review.get('conflicts') or []:
            if c.get('type') != 'name_mismatch':
                continue
            if winner != 'sage':
                continue
            try:
                out = resolve_sage_vendor_conflict(
                    db, models, ledger_id,
                    {'code': c.get('code'), 'winner': 'sage', 'sage_name': c.get('sage_name')},
                    user_id=user_id,
                )
                resolved.append(out)
            except Exception as exc:
                resolved.append({'code': c.get('code'), 'error': str(exc)})

    ap_out = None
    if push_ap:
        ap_out = sage_push_open_ap_idempotent(db, models, ledger_id, user_id=user_id, limit=25)

    flush_out = None
    if flush_queue:
        flush_out = flush_construction_mirror_queue(db, models, ledger_id, user_id=user_id)

    sync_out = None
    if project_id and Project is not None:
        from accounting_waves_46 import sync_all_pending_construction
        import app as app_mod

        sync_out = sync_all_pending_construction(
            db, models, ledger_id, int(project_id), user_id=user_id,
            PayAppProjectState=app_mod.PayAppProjectState,
            Commitment=app_mod.Commitment,
            CommitmentAllocation=app_mod.CommitmentAllocation,
            Project=Project,
            ChangeOrder=app_mod.ChangeOrder,
        )

    alerts = sage_go_live_alert_bundle(db, models, ledger_id)
    report = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'vendor_resolved': len([r for r in resolved if r.get('code') and not r.get('error')]),
        'vendor_details': resolved[:20],
        'ap_push': ap_out,
        'construction_flush': flush_out,
        'project_sync': sync_out,
        'alerts_after': alerts.get('alert_count'),
    }
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_cutover_playbook_last'] = report
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_cutover_playbook', details={
        'vendor_resolved': report['vendor_resolved'],
        'project_id': project_id,
    })
    return report


def sage_parity_gap_prioritized_list(db, models, ledger_id: int) -> dict:
    from accounting_waves_47 import sage_parity_matrix

    matrix = sage_parity_matrix(db, models, ledger_id)
    rows = matrix.get('rows') or []
    gaps = []
    priority_rank = {'PJ': 1, 'JC': 2, 'CP': 3, 'AP': 4, 'AR': 5}
    for row in rows:
        mod = row.get('module') or ''
        events = row.get('casepm_events') or []
        has_write = bool(row.get('write'))
        if has_write and events:
            continue
        score = priority_rank.get(mod, 50)
        if mod in ('PJ', 'JC', 'CP'):
            score -= 5
        if not events:
            score += 3
        action = 'document_manual_sage_entry'
        playbook_step = None
        if mod in ('PJ', 'JC', 'CP'):
            action = 'flush_construction_mirror_queue'
            playbook_step = 'construction_sync_panel'
        elif mod == 'AP':
            action = 'sage_push_open_ap_idempotent'
            playbook_step = 'sage_cutover_playbook'
        gaps.append({
            'module': mod,
            'name': row.get('name'),
            'priority': score,
            'recommended_action': action,
            'playbook_step': playbook_step,
            'gap_notes': row.get('gap_notes') or ('No Case PM mirror events' if not events else 'Write path limited'),
            'casepm_events': events[:6],
        })
    gaps.sort(key=lambda g: (g['priority'], g['module']))
    for i, g in enumerate(gaps[:30], start=1):
        g['rank'] = i
    out = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'gap_count': len(gaps),
        'gaps': gaps[:30],
        'matrix_gap_count': matrix.get('gap_count'),
        'doc': 'docs/SAGE_CUTOVER_CHECKLIST.md',
    }
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_parity_gaps_prioritized'] = out
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, action='sage_parity_gaps_prioritized', details={'gap_count': len(gaps)})
    return out


def sage_parity_gap_auto_fix_top(db, models, ledger_id: int, *, user_id=None, limit: int = 3, Project=None) -> dict:
    """Run up to `limit` automated fixes suggested by the prioritized gap list."""
    gaps = sage_parity_gap_prioritized_list(db, models, ledger_id).get('gaps') or []
    fixes = []
    for g in gaps[:limit]:
        action = g.get('recommended_action')
        result = {'module': g.get('module'), 'action': action}
        try:
            if action == 'flush_construction_mirror_queue':
                from accounting_waves_27 import flush_construction_mirror_queue
                result['out'] = flush_construction_mirror_queue(db, models, ledger_id, user_id=user_id)
            elif action == 'sage_push_open_ap_idempotent':
                from accounting_waves_25 import sage_push_open_ap_idempotent
                result['out'] = sage_push_open_ap_idempotent(db, models, ledger_id, user_id=user_id)
            elif action == 'resolve_vendor_conflicts_sage':
                result['out'] = sage_cutover_conflict_playbook(
                    db, models, ledger_id, {'resolve_vendor_conflicts': True, 'retry_ap_push': False, 'flush_construction_queue': False},
                    user_id=user_id, Project=Project,
                )
            else:
                result['skipped'] = 'manual'
        except Exception as exc:
            result['error'] = str(exc)
        fixes.append(result)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_parity_auto_fix', details={'count': len(fixes)})
    return {'fixes': fixes, 'limit': limit}


def estimate_sov_alignment_report(db, project_id: int, *, BudgetProjectState=None, PayAppProjectState=None) -> dict:
    from budget_persistence import get_budget_state
    from pay_app_persistence import get_pay_app_state, normalize_cost_code

    pid = int(project_id)
    _, budget = get_budget_state(BudgetProjectState, pid) if BudgetProjectState else (None, {})
    _, pay = get_pay_app_state(PayAppProjectState, pid, db=db) if PayAppProjectState else (None, {})

    budget_totals = {}
    budget_display = {}
    for line in (budget or {}).get('budgetLines') or []:
        if not isinstance(line, dict):
            continue
        norm = normalize_cost_code(line.get('cost_code'))
        if not norm:
            continue
        amt = float(line.get('original_budget') or line.get('original') or 0)
        amt += float(line.get('approved_changes') or line.get('change_orders') or 0)
        budget_totals[norm] = budget_totals.get(norm, 0.0) + amt
        budget_display[norm] = line.get('cost_code') or norm

    sov_totals = {}
    sov_display = {}
    for line in (pay or {}).get('contractorSOV') or []:
        if not isinstance(line, dict):
            continue
        norm = normalize_cost_code(line.get('cost_code'))
        if not norm:
            continue
        amt = float(line.get('original') or 0)
        amt += float(line.get('co_amount') or line.get('change_orders') or 0)
        sov_totals[norm] = sov_totals.get(norm, 0.0) + amt
        sov_display[norm] = line.get('cost_code') or norm

    all_codes = sorted(set(budget_totals) | set(sov_totals))
    mismatches = []
    tolerance = 0.02
    for norm in all_codes:
        b = round(budget_totals.get(norm, 0.0), 2)
        s = round(sov_totals.get(norm, 0.0), 2)
        if abs(b - s) > tolerance:
            mismatches.append({
                'cost_code': budget_display.get(norm) or sov_display.get(norm) or norm,
                'budget_total': b,
                'sov_total': s,
                'variance': round(s - b, 2),
            })
    only_budget = [budget_display.get(c, c) for c in all_codes if c not in sov_totals and budget_totals.get(c, 0) > 0]
    only_sov = [sov_display.get(c, c) for c in all_codes if c not in budget_totals and sov_totals.get(c, 0) > 0]

    aligned = len(all_codes) - len(mismatches) - len(only_budget) - len(only_sov)
    return {
        'at': datetime.utcnow().isoformat() + 'Z',
        'project_id': pid,
        'budget_line_codes': len(budget_totals),
        'sov_line_codes': len(sov_totals),
        'aligned_codes': max(0, aligned),
        'mismatch_count': len(mismatches),
        'mismatches': mismatches[:50],
        'only_in_budget': only_budget[:20],
        'only_in_sov': only_sov[:20],
        'ok': not mismatches and not only_budget and not only_sov,
    }


def cron_operations_bundle_v48(db, models, secret: str) -> dict:
    """Alias for operations bundle (wave 48 adds go-live email digest via wave 47 bundle)."""
    from accounting_waves_47 import cron_operations_bundle

    return cron_operations_bundle(db, models, secret)


def sage_mirror_deploy_check_v17() -> dict:
    from accounting_waves_47 import sage_mirror_deploy_check_v16

    base = sage_mirror_deploy_check_v16()
    checks = {
        'go_live_email_digest': True,
        'cutover_playbook': True,
        'parity_gaps_prioritized': True,
        'sov_alignment': True,
        'construction_integration_pack': True,
    }
    try:
        assert callable(sage_go_live_email_digest)
        assert callable(sage_cutover_conflict_playbook)
        assert callable(sage_parity_gap_prioritized_list)
        assert callable(estimate_sov_alignment_report)
        import os as _os
        pack = _os.path.join(_os.path.dirname(__file__), 'scripts', 'test_accounting_construction_integration_pack.py')
        checks['construction_integration_pack'] = _os.path.isfile(pack)
    except Exception:
        checks = {k: False for k in checks}
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v16': base, 'wave_checks': checks}
