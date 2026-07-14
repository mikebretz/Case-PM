#!/usr/bin/env python3
"""Remove a stuck subcontractor from a project (void commitments + purge SOV)."""
from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description='Remove subcontractor from project pay apps')
    parser.add_argument('--project', required=True, help='Project name (partial match)')
    parser.add_argument('--company', required=True, help='Subcontractor company name (partial match)')
    parser.add_argument('--force', action='store_true', help='Void approved commitments')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    import app as app_module
    from app import db, Project, Commitment, PayAppProjectState
    from pay_app_persistence import (
        get_pay_app_state,
        purge_subcontractor_from_pay_state,
        void_subcontractor_commitments,
        commitment_matches_vendor,
        save_pay_app_state,
    )

    with app_module.app.app_context():
        projects = Project.query.filter(Project.name.ilike(f'%{args.project}%')).all()
        if not projects:
            print(f'No project matching "{args.project}"')
            return 1
        if len(projects) > 1:
            print('Multiple projects matched:')
            for p in projects:
                print(f'  {p.id}: {p.name}')
            return 1
        project = projects[0]
        print(f'Project: {project.name} (id={project.id})')

        commitments = Commitment.query.filter_by(project_id=project.id).all()
        matches = [
            c for c in commitments
            if commitment_matches_vendor(c, None, args.company)
            or (args.company.lower() in (c.company_name or '').lower())
        ]
        if not matches:
            print(f'No commitments matching "{args.company}"')
        else:
            for c in matches:
                print(f'  Commitment {c.number}: {c.company_name} ({c.status})')

        _, state = get_pay_app_state(PayAppProjectState, project.id)
        sub_sov = state.get('subcontractorSOV') or {}
        sov_keys = [k for k in sub_sov if args.company.lower() in str(k).lower()]
        for k, lines in sub_sov.items():
            if args.company.lower() in str(k).lower() or any(
                args.company.lower() in (line.get('description') or '').lower() for line in (lines or [])
            ):
                sov_keys.append(k)
        sov_keys = list(dict.fromkeys(sov_keys))
        print(f'SOV keys to purge: {sov_keys or "(none found by name — will match by company name)"}')

        if args.dry_run:
            print('Dry run — no changes made.')
            return 0

        company_name = args.company
        company_id = None
        if matches:
            company_id = matches[0].company_id
            company_name = matches[0].company_name or company_name

        voided = void_subcontractor_commitments(
            project.id, company_id, company_name,
            Commitment=Commitment, db=db, allow_approved=args.force or True,
        )
        purge = purge_subcontractor_from_pay_state(state, company_id, company_name)
        save_pay_app_state(PayAppProjectState, db, project.id, state, user_id=None)

        from accounting_reconcile import reconcile_project_accounting
        from app import (
            ChangeOrder, ChangeOrderAllocation, CommitmentAllocation,
            BudgetProjectState,
        )
        reconcile_project_accounting(
            project.id, None,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=PayAppProjectState,
            db=db,
        )

        print(f'Voided {len(voided)} commitment(s). Purge: {purge}')
        print('Done.')
        return 0


if __name__ == '__main__':
    sys.exit(main())
