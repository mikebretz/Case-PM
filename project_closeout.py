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
