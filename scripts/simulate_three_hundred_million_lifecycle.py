#!/usr/bin/env python3
"""
$300M mega lifecycle — 5× paperwork vs $100M baseline, marketing hub → plan room →
estimating → 36-month PM/pay apps → accounting closeout → PM complete.

  PYTHONPATH=/workspace python3 scripts/simulate_three_hundred_million_lifecycle.py
  PYTHONPATH=/workspace python3 scripts/simulate_three_hundred_million_lifecycle.py --report /tmp/300m_sim.json
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime

sys.path.insert(0, '/workspace')

from scripts.simulate_hundred_million_lifecycle import (  # noqa: E402
    CONFIG_300M_5X,
    _issue_dict,
    run_lifecycle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='$300M full lifecycle (5× paperwork)')
    parser.add_argument('--report', default='', help='Write JSON report path')
    parser.add_argument('--seed', type=int, default=300)
    args = parser.parse_args()

    print('=' * 72)
    print('$300M FULL LIFECYCLE (marketing → plan room → accounting closeout)')
    print('=' * 72)
    try:
        rt = run_lifecycle(CONFIG_300M_5X, seed=args.seed)
    except Exception:
        traceback.print_exc()
        return 2

    issues = rt.result.issues
    crit = [i for i in issues if i.severity == 'critical']
    warn = [i for i in issues if i.severity == 'warning']
    info = [i for i in issues if i.severity == 'info']

    print(f'\nProject ID: {rt.project.id}')
    print(json.dumps(rt.result.metrics, indent=2))
    print(f'\nIssues: {len(crit)} critical, {len(warn)} warning, {len(info)} info')
    for i in issues:
        print(f'  [{i.severity.upper():8}] {i.category}: {i.message}')

    payload = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'project_id': rt.project.id,
        'scenario': rt.scenario.name,
        'contract_value': rt.scenario.contract_value,
        'metrics': rt.result.metrics,
        'issues': [_issue_dict(i) for i in issues],
        'summary': {
            'critical': len(crit),
            'warning': len(warn),
            'info': len(info),
        },
    }
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f'\nReport written: {args.report}')

    return 1 if crit else 0


if __name__ == '__main__':
    raise SystemExit(main())
