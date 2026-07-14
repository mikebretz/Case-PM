#!/usr/bin/env python3
"""Clear all subcontractor SOV and pay-app data across projects (void sub commitments)."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description='Clear all subcontractor SOV data')
    parser.add_argument('--project-id', type=int, help='Limit to one project id')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-void', action='store_true', help='Do not void subcontract commitments')
    args = parser.parse_args()

    import app as app_module
    from app import db, Project, Commitment, PayAppProjectState
    from pay_app_persistence import (
        get_pay_app_state,
        save_pay_app_state,
        clear_all_subcontractor_pay_data,
        void_all_subcontractor_commitments,
        prune_orphan_subcontractor_sov,
    )

    with app_module.app.app_context():
        if args.project_id:
            projects = Project.query.filter_by(id=args.project_id).all()
        else:
            projects = Project.query.all()

        if not projects:
            print('No projects found.')
            return 1

        for project in projects:
            _, state = get_pay_app_state(PayAppProjectState, project.id)
            state = state or {}
            sub_sov = state.get('subcontractorSOV') or {}
            sub_count = len(sub_sov)
            commitments = Commitment.query.filter_by(project_id=project.id).all()
            sub_commitments = [
                c for c in commitments
                if c.commitment_type == 'Subcontract' and c.status != 'Void'
            ]
            print(f'Project {project.id}: {project.name} — SOV vendors={sub_count}, sub commitments={len(sub_commitments)}')

            if args.dry_run:
                continue

            voided = []
            if not args.no_void:
                voided = void_all_subcontractor_commitments(
                    project.id, Commitment=Commitment, db=db, user_id=None,
                )
            cleared = clear_all_subcontractor_pay_data(state)
            prune = prune_orphan_subcontractor_sov(state, [])
            save_pay_app_state(PayAppProjectState, db, project.id, state, user_id=None)
            print(f'  voided={len(voided)} cleared={cleared.get("cleared")} prune={prune}')

        if args.dry_run:
            print('Dry run — no changes made.')
        else:
            print('Done.')
        return 0


if __name__ == '__main__':
    sys.exit(main())
