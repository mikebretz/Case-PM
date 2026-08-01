"""Project closeout readiness — block completion until critical PM items are resolved."""
from __future__ import annotations

OPEN_RFI_STATUSES = ('Draft', 'Open', 'Under Review', 'Awaiting Response', 'Answered')
PENDING_CO_STATUSES = (
    'Submitted', 'Under Review', 'Pending Architect', 'Pending Owner',
    'Pending Accounting', 'Pending Review', 'Pricing',
)
OPEN_SUBMITTAL_STATUSES = (
    'Draft', 'Open', 'Sent to Subcontractor', 'Submitted', 'Under Review',
    'Revise & Resubmit', 'Reviewed as Noted', 'No Exceptions Taken',
)
COMPLETE_PROJECT_STATUSES = frozenset({'Complete', 'Completed'})


def closeout_readiness(
    project_id,
    *,
    RFI,
    ChangeOrder,
    Submittal=None,
    PotentialChangeOrder=None,
) -> dict:
    """Return blocking issues and warnings before marking a project complete."""
    pid = int(project_id)
    blocking = []
    warnings = []

    open_rfis = RFI.query.filter(
        RFI.project_id == pid,
        RFI.status.in_(OPEN_RFI_STATUSES),
    ).count()
    if open_rfis:
        blocking.append(f'{open_rfis} RFI(s) still open — close or void before completing the project.')

    pending_cos = ChangeOrder.query.filter(
        ChangeOrder.project_id == pid,
        ChangeOrder.status.in_(PENDING_CO_STATUSES),
    ).count()
    if pending_cos:
        blocking.append(f'{pending_cos} change order(s) still in approval workflow.')

    draft_cos = ChangeOrder.query.filter_by(project_id=pid, status='Draft').count()
    if draft_cos:
        warnings.append(f'{draft_cos} change order(s) still in Draft.')

    open_submittals = 0
    if Submittal is not None:
        open_submittals = Submittal.query.filter(
            Submittal.project_id == pid,
            Submittal.status.notin_(('Closed', 'Void')),
        ).count()
        if open_submittals > 0:
            warnings.append(f'{open_submittals} submittal(s) not closed.')

    open_pcos = 0
    if PotentialChangeOrder is not None:
        open_pcos = PotentialChangeOrder.query.filter(
            PotentialChangeOrder.project_id == pid,
            PotentialChangeOrder.status.notin_(('Promoted', 'Void', 'Rejected')),
        ).count()
        if open_pcos:
            warnings.append(f'{open_pcos} PCO(s) not promoted or voided.')

    return {
        'ok': len(blocking) == 0,
        'blocking': blocking,
        'warnings': warnings,
        'counts': {
            'open_rfis': open_rfis,
            'pending_change_orders': pending_cos,
            'draft_change_orders': draft_cos,
            'open_submittals': open_submittals,
            'open_pcos': open_pcos,
        },
    }


def assert_project_may_complete(project_id, *, force: bool = False, **models) -> dict:
    report = closeout_readiness(project_id, **models)
    if report['ok'] or force:
        return report
    msg = ' '.join(report['blocking'])
    raise ValueError(f'Closeout checklist failed: {msg}')


def sweep_project_closeout_blockers(
    project_id,
    *,
    db,
    RFI,
    ChangeOrder,
    User,
    users: dict,
    approve_co_fn=None,
    Submittal=None,
    PotentialChangeOrder=None,
    void_stuck_cos: bool = True,
) -> dict:
    """
    Simulation / admin helper: close open RFIs, clear in-flight owner COs, close submittals.
    Returns counts of actions taken.
    """
    from rfi_persistence import add_response, workflow_rfi
    from workflow_responder import execute_rfi_action

    pid = int(project_id)
    stats = {'rfis_closed': 0, 'cos_resolved': 0, 'submittals_closed': 0, 'pcos_voided': 0}

    pm = users.get('pm')
    arch = users.get('arch')
    if not pm:
        return stats

    for rfi in RFI.query.filter(RFI.project_id == pid, RFI.status.in_(OPEN_RFI_STATUSES)).all():
        try:
            if (rfi.status or '') == 'Draft':
                execute_rfi_action(rfi, 'submit', pm, User, {})
            if arch and (rfi.status or '') not in ('Closed', 'Void'):
                add_response(rfi, {'body': 'Closeout sweep — official response.', 'is_official': True}, arch.id, 'Sim Architect')
            if (rfi.status or '') not in ('Closed', 'Void'):
                workflow_rfi(rfi, 'close', 'Closeout sweep')
            stats['rfis_closed'] += 1
        except Exception:
            rfi.status = 'Closed'
            stats['rfis_closed'] += 1
    db.session.commit()

    pending = ChangeOrder.query.filter(
        ChangeOrder.project_id == pid,
        ChangeOrder.status.in_(PENDING_CO_STATUSES),
    ).all()
    for co in pending:
        if approve_co_fn:
            try:
                st = approve_co_fn(co)
                if st == 'Approved':
                    stats['cos_resolved'] += 1
                    continue
            except Exception:
                pass
        if void_stuck_cos:
            co.status = 'Void'
            stats['cos_resolved'] += 1
    for co in ChangeOrder.query.filter_by(project_id=pid, status='Draft').all():
        co.status = 'Void'
        stats['cos_resolved'] += 1
    db.session.commit()

    if Submittal is not None:
        from submittal_persistence import submittal_workflow_action
        for sub in Submittal.query.filter(
            Submittal.project_id == pid,
            Submittal.status.notin_(('Closed', 'Void')),
        ).all():
            try:
                submittal_workflow_action(sub, 'close', pm)
                stats['submittals_closed'] += 1
            except Exception:
                sub.status = 'Closed'
                stats['submittals_closed'] += 1
        db.session.commit()

    if PotentialChangeOrder is not None:
        for pco in PotentialChangeOrder.query.filter(
            PotentialChangeOrder.project_id == pid,
            PotentialChangeOrder.status.notin_(('Promoted', 'Void', 'Rejected')),
        ).all():
            pco.status = 'Void'
            stats['pcos_voided'] += 1
        db.session.commit()

    return stats
