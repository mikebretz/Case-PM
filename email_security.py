"""Email security scanner — phishing, spam, and intrusion heuristics."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

JUNK_THRESHOLDS = {
    'low': {'warn': 60, 'quarantine': 80},
    'standard': {'warn': 45, 'quarantine': 70},
    'high': {'warn': 35, 'quarantine': 55},
    'strict': {'warn': 25, 'quarantine': 40},
}

PHISHING_PHRASES = [
    r'verify your (account|identity|password|credentials)',
    r'confirm your (account|identity|password|billing)',
    r'account (suspended|locked|compromised|disabled)',
    r'unusual (sign[- ]?in|login) activity',
    r'password (expir|reset|change) (required|immediately|now)',
    r'wire transfer',
    r'urgent.{0,20}(payment|invoice|transfer)',
    r'click (here|below|this link) (to|and)',
    r'update your (payment|billing|bank)',
    r'gift card',
    r'payroll.{0,20}(change|update|direct deposit)',
    r'ceo.{0,20}(request|urgent|wire)',
    r'action required.{0,30}(immediately|within 24)',
    r'your mailbox.{0,20}(full|quota|storage)',
    r'mfa.{0,20}(required|verify|setup)',
]

SPAM_PHRASES = [
    r'unsubscribe',
    r'limited time offer',
    r'act now',
    r'free (trial|gift|money|bitcoin)',
    r'winner|congratulations.{0,20}won',
    r'no obligation',
    r'100% free',
    r'earn \$\d+',
    r'work from home',
    r'crypto.{0,20}(profit|investment)',
    r'viagra|cialis|pharmacy',
    r'lottery',
    r'inheritance',
    r'nigerian prince',
]

INTRUSION_PATTERNS = [
    (r'<script[\s>]', 'Embedded script tag detected'),
    (r'javascript\s*:', 'JavaScript URL scheme'),
    (r'on(error|load|click|mouseover)\s*=', 'Inline event handler'),
    (r'data:text/html', 'Data URI HTML payload'),
    (r'<iframe[\s>]', 'Embedded iframe'),
    (r'eval\s*\(', 'JavaScript eval() call'),
    (r'document\.cookie', 'Cookie access attempt'),
    (r'\.exe\b|\.scr\b|\.bat\b|\.cmd\b|\.vbs\b|\.js\b|\.wsf\b', 'Dangerous attachment extension'),
    (r'powershell\s+-', 'PowerShell invocation'),
    (r'cmd\.exe', 'Command shell reference'),
]

SUSPICIOUS_TLDS = {
    'xyz', 'top', 'click', 'loan', 'work', 'gq', 'ml', 'cf', 'tk', 'buzz', 'rest', 'cam',
    'zip', 'mov', 'monster', 'sbs', 'cfd',
}

URL_SHORTENERS = {
    'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'ow.ly', 'is.gd', 'buff.ly', 'rb.gy',
    'cutt.ly', 'shorturl.at',
}

TRUSTED_INTERNAL_DOMAINS = {
    'casepm.com', 'casepm.local', 'caseconstruction.com',
}

DISPLAY_NAME_BRANDS = [
  'microsoft', 'google', 'apple', 'paypal', 'amazon', 'docusign', 'adobe',
  'case pm', 'case construction', 'outlook', 'office 365',
]


@dataclass
class SecurityFinding:
    code: str
    severity: str
    message: str
    score: int = 0


@dataclass
class ScanResult:
    risk_score: int = 0
    risk_level: str = 'safe'
    action: str = 'allow'
    category: str = 'clean'
    findings: list[SecurityFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocked_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'action': self.action,
            'category': self.category,
            'findings': [
                {'code': f.code, 'severity': f.severity, 'message': f.message, 'score': f.score}
                for f in self.findings
            ],
            'warnings': self.warnings,
            'blocked_reason': self.blocked_reason,
        }


def _normalize_email(addr: str) -> str:
    return (addr or '').strip().lower()


def _extract_domain(email: str) -> str:
    email = _normalize_email(email)
    if '@' not in email:
        return ''
    return email.rsplit('@', 1)[-1]


def _text_blob(message: dict) -> str:
    parts = [
        message.get('subject') or '',
        message.get('preview') or '',
        message.get('body') or '',
        message.get('from') or '',
        message.get('fromEmail') or '',
    ]
    return ' '.join(str(p) for p in parts)


def _extract_urls(text: str) -> list[str]:
    return re.findall(r'https?://[^\s<>"\']+', text, flags=re.IGNORECASE)


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if '@' in host:
            host = host.rsplit('@', 1)[-1]
        if ':' in host:
            host = host.split(':', 1)[0]
        return host.removeprefix('www.')
    except Exception:
        return ''


def _looks_like_ip(host: str) -> bool:
    return bool(re.match(r'^\d{1,3}(\.\d{1,3}){3}$', host or ''))


def _punycode_suspicious(host: str) -> bool:
    return 'xn--' in (host or '').lower()


def _display_name_spoof(display_name: str, from_email: str) -> SecurityFinding | None:
    name = (display_name or '').lower()
    domain = _extract_domain(from_email)
    if not name or not domain:
        return None
    for brand in DISPLAY_NAME_BRANDS:
        if brand in name and brand.replace(' ', '') not in domain.replace('.', '').replace('-', ''):
            if domain not in TRUSTED_INTERNAL_DOMAINS:
                return SecurityFinding(
                    'display_name_spoof',
                    'high',
                    f'Display name references "{brand.title()}" but sender domain is {domain}',
                    28,
                )
    return None


def _auth_header_findings(headers: dict | None) -> list[SecurityFinding]:
    if not headers:
        return []
    findings = []
    lowered = {str(k).lower(): str(v).lower() for k, v in headers.items()}
    spf = lowered.get('received-spf') or lowered.get('authentication-results', '')
    dkim = lowered.get('authentication-results', '')
    dmarc = lowered.get('authentication-results', '')

    if spf and 'fail' in spf:
        findings.append(SecurityFinding('spf_fail', 'high', 'SPF authentication failed', 22))
    elif spf and 'softfail' in spf:
        findings.append(SecurityFinding('spf_softfail', 'medium', 'SPF soft-fail — sender may be spoofed', 12))

    if dkim and 'dkim=fail' in dkim:
        findings.append(SecurityFinding('dkim_fail', 'high', 'DKIM signature verification failed', 20))
    if dmarc and 'dmarc=fail' in dmarc:
        findings.append(SecurityFinding('dmarc_fail', 'high', 'DMARC policy check failed', 24))
    return findings


def _attachment_findings(message: dict) -> list[SecurityFinding]:
    findings = []
    dangerous_ext = {'.exe', '.scr', '.bat', '.cmd', '.vbs', '.js', '.wsf', '.ps1', '.hta', '.dll', '.iso'}
    double_ext_re = re.compile(r'\.(pdf|docx?|xlsx?|png|jpg)\.(exe|scr|js|vbs|bat)$', re.I)
    for att in message.get('attachments') or []:
        name = str(att.get('name') or '')
        lower = name.lower()
        ext = '.' + lower.rsplit('.', 1)[-1] if '.' in lower else ''
        if ext in dangerous_ext:
            findings.append(SecurityFinding('dangerous_attachment', 'critical', f'Dangerous attachment: {name}', 35))
        if double_ext_re.search(lower):
            findings.append(SecurityFinding('double_extension', 'critical', f'Double extension trick: {name}', 32))
        if lower.endswith('.zip') and any(x in lower for x in ('invoice', 'payment', 'urgent', 'scan')):
            findings.append(SecurityFinding('suspicious_zip', 'high', f'Suspicious compressed attachment: {name}', 18))
    return findings


def _url_findings(text: str) -> list[SecurityFinding]:
    findings = []
    for url in _extract_urls(text):
        host = _domain_from_url(url)
        if not host:
            continue
        if _looks_like_ip(host):
            findings.append(SecurityFinding('ip_link', 'high', f'Link uses raw IP address: {host}', 20))
        if host in URL_SHORTENERS:
            findings.append(SecurityFinding('url_shortener', 'medium', f'URL shortener used: {host}', 10))
        tld = host.rsplit('.', 1)[-1] if '.' in host else ''
        if tld in SUSPICIOUS_TLDS:
            findings.append(SecurityFinding('suspicious_tld', 'medium', f'Suspicious top-level domain: .{tld}', 12))
        if _punycode_suspicious(host):
            findings.append(SecurityFinding('punycode_domain', 'high', f'Internationalized (punycode) domain: {host}', 22))
        if any(token in url.lower() for token in ('login', 'signin', 'verify', 'password', 'account', 'secure', 'update-billing')):
            if host not in TRUSTED_INTERNAL_DOMAINS:
                findings.append(SecurityFinding('credential_url', 'high', f'Link may harvest credentials: {host}', 18))
    return findings


def _phrase_findings(text: str, patterns: list[str], code_prefix: str, severity: str, score: int, max_matches: int = 3) -> list[SecurityFinding]:
    findings = []
    lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, lower, flags=re.IGNORECASE):
            findings.append(SecurityFinding(
                f'{code_prefix}_{len(findings) + 1}',
                severity,
                f'Matched suspicious phrase pattern ({pattern[:48]}…)',
                score,
            ))
            if len(findings) >= max_matches:
                break
    return findings


def _caps_spam_score(text: str) -> int:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12:
        return 0
    upper = sum(1 for c in letters if c.isupper())
    ratio = upper / len(letters)
    if ratio > 0.6:
        return 12
    if ratio > 0.45:
        return 6
    return 0


def _risk_level(score: int) -> str:
    if score >= 80:
        return 'critical'
    if score >= 60:
        return 'high'
    if score >= 40:
        return 'medium'
    if score >= 20:
        return 'low'
    return 'safe'


def _category_from_findings(findings: list[SecurityFinding], score: int) -> str:
    codes = {f.code.split('_')[0] for f in findings}
    if any(c in codes for c in ('dangerous', 'double', 'intrusion', 'embedded')):
        return 'malware'
    if 'display' in ''.join(f.code for f in findings) or any('credential' in f.code for f in findings):
        return 'phishing'
    if any(c in codes for c in ('spf', 'dkim', 'dmarc', 'punycode')):
        return 'spoofing'
    if score >= 40 and any('spam' in f.code or 'caps' in f.code for f in findings):
        return 'spam'
    if score >= 45:
        return 'phishing'
    if score >= 30:
        return 'spam'
    return 'clean'


def scan_email_message(
    message: dict,
    *,
    junk_level: str = 'standard',
    blocked_senders: list[str] | None = None,
    safe_senders: list[str] | None = None,
    user_email: str = '',
    false_positive_overrides: list[str] | None = None,
) -> ScanResult:
    """Scan a single mailbox message and return structured risk assessment."""
    blocked_senders = [_normalize_email(x) for x in (blocked_senders or [])]
    safe_senders = [_normalize_email(x) for x in (safe_senders or [])]
    false_positive_overrides = [str(x) for x in (false_positive_overrides or [])]

    msg_id = str(message.get('id') or '')
    from_email = _normalize_email(message.get('fromEmail') or '')
    from_display = message.get('from') or ''
    text = _text_blob(message)
    findings: list[SecurityFinding] = []

    if msg_id and msg_id in false_positive_overrides:
        return ScanResult(
            risk_score=0,
            risk_level='safe',
            action='allow',
            category='clean',
            warnings=['Previously marked as not spam / safe by you'],
        )

    if from_email and from_email in safe_senders:
        return ScanResult(
            risk_score=0,
            risk_level='safe',
            action='allow',
            category='clean',
            warnings=['Sender is on your safe list'],
        )

    if from_email and from_email in blocked_senders:
        return ScanResult(
            risk_score=100,
            risk_level='critical',
            action='block',
            category='blocked',
            findings=[SecurityFinding('blocked_sender', 'critical', 'Sender is on your blocked list', 100)],
            warnings=['Sender is blocked'],
            blocked_reason='blocked_sender',
        )

    spoof = _display_name_spoof(from_display, from_email)
    if spoof:
        findings.append(spoof)

    findings.extend(_auth_header_findings(message.get('headers')))
    findings.extend(_attachment_findings(message))
    findings.extend(_url_findings(text))
    findings.extend(_phrase_findings(text, PHISHING_PHRASES, 'phishing', 'high', 16, max_matches=2))
    findings.extend(_phrase_findings(text, SPAM_PHRASES, 'spam', 'medium', 12, max_matches=3))

    sender_domain = _extract_domain(from_email)
    if sender_domain:
        tld = sender_domain.rsplit('.', 1)[-1] if '.' in sender_domain else ''
        if tld in SUSPICIOUS_TLDS:
            findings.append(SecurityFinding('sender_suspicious_tld', 'medium', f'Sender uses suspicious domain .{tld}', 14))

    for pattern, desc in INTRUSION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(SecurityFinding('intrusion_pattern', 'critical', desc, 30))
            break

    caps_score = _caps_spam_score(message.get('subject') or '')
    if caps_score:
        findings.append(SecurityFinding('caps_spam', 'low', 'Subject uses excessive capital letters', caps_score))

    if from_email and user_email:
        user_domain = _extract_domain(user_email)
        sender_domain = _extract_domain(from_email)
        if user_domain and sender_domain == user_domain and from_email != _normalize_email(user_email):
            local_part = from_email.split('@', 1)[0]
            if any(x in local_part for x in ('admin', 'it-support', 'helpdesk', 'security', 'billing')):
                findings.append(SecurityFinding(
                    'internal_impersonation',
                    'high',
                    'Sender appears to impersonate an internal role',
                    20,
                ))

    if message.get('folder') == 'sent':
        return ScanResult(risk_score=0, risk_level='safe', action='allow', category='clean')

    # Deduplicate by code keeping highest score
    deduped: dict[str, SecurityFinding] = {}
    for f in findings:
        prev = deduped.get(f.code)
        if not prev or f.score > prev.score:
            deduped[f.code] = f
    findings = list(deduped.values())
    score = min(100, sum(f.score for f in findings))

    thresholds = JUNK_THRESHOLDS.get(junk_level, JUNK_THRESHOLDS['standard'])
    level = _risk_level(score)
    category = _category_from_findings(findings, score)

    if score >= thresholds['quarantine']:
        action = 'quarantine'
    elif score >= thresholds['warn']:
        action = 'warn'
    else:
        action = 'allow'

    warnings = [f.message for f in sorted(findings, key=lambda x: -x.score)[:6]]
    return ScanResult(
        risk_score=score,
        risk_level=level,
        action=action,
        category=category,
        findings=findings,
        warnings=warnings,
    )


def scan_messages_batch(
    messages: list[dict],
    *,
    junk_level: str = 'standard',
    blocked_senders: list[str] | None = None,
    safe_senders: list[str] | None = None,
    user_email: str = '',
    false_positive_overrides: list[str] | None = None,
) -> dict[str, Any]:
    results = {}
    summary = {'total': 0, 'warn': 0, 'quarantine': 0, 'block': 0, 'safe': 0}
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        msg_id = str(msg.get('id') or '')
        if not msg_id:
            continue
        scan = scan_email_message(
            msg,
            junk_level=junk_level,
            blocked_senders=blocked_senders,
            safe_senders=safe_senders,
            user_email=user_email,
            false_positive_overrides=false_positive_overrides,
        )
        results[msg_id] = scan.to_dict()
        summary['total'] += 1
        if scan.action == 'block':
            summary['block'] += 1
        elif scan.action == 'quarantine':
            summary['quarantine'] += 1
        elif scan.action == 'warn':
            summary['warn'] += 1
        else:
            summary['safe'] += 1
    return {'results': results, 'summary': summary}


def apply_quarantine_actions(messages: list[dict], scan_results: dict[str, dict]) -> list[dict]:
    """Move quarantined messages to spam unless user already filed them elsewhere."""
    updated = []
    for msg in messages:
        m = dict(msg)
        msg_id = str(m.get('id') or '')
        scan = scan_results.get(msg_id) or {}
        action = scan.get('action')
        m['security'] = scan
        if action in ('quarantine', 'block') and m.get('folder') in (None, '', 'inbox', 'focused', 'other'):
            m['folder'] = 'spam'
            m['securityQuarantined'] = True
        updated.append(m)
    return updated


def generate_simulation_corpus(count: int = 1000) -> list[dict]:
    """Generate a mixed corpus for security regression testing."""
    import random
    import string
    from datetime import datetime, timedelta

    random.seed(42)
    corpus: list[dict] = []

    def _msg(idx: int, **kwargs) -> dict:
        base = {
            'id': f'sim_{idx}',
            'folder': 'inbox',
            'from': kwargs.pop('from_name', 'Sender'),
            'fromEmail': kwargs.pop('from_email', f'sender{idx}@example.com'),
            'to': ['user@casepm.com'],
            'subject': kwargs.pop('subject', 'Routine update'),
            'preview': kwargs.pop('preview', 'Please review the attached document.'),
            'body': kwargs.pop('body', '<p>Please review the attached document.</p>'),
            'date': (datetime.utcnow() - timedelta(hours=idx % 72)).isoformat() + 'Z',
            'unread': True,
            'hasAttachments': bool(kwargs.get('attachments')),
            'attachments': kwargs.pop('attachments', []),
            'headers': kwargs.pop('headers', {}),
            'simCategory': kwargs.pop('sim_category', 'legitimate'),
        }
        base.update(kwargs)
        return base

    templates = [
        ('legitimate', lambda i: _msg(i, from_name='Sarah Chen', from_email='sarah.chen@aldistores.com', subject='Submittal log review', body='<p>Please review the submittal package.</p>', sim_category='legitimate')),
        ('legitimate', lambda i: _msg(i, from_name='Mike Johnson', from_email='mike.j@structureeng.com', subject='RFI #142 clarification', body='<p>See attached sketch.</p>', sim_category='legitimate')),
        ('spam', lambda i: _msg(i, from_email=f'promo{i}@deal-offers.top', subject='ACT NOW — LIMITED TIME OFFER!!!', body='<p>Free money! Unsubscribe anytime.</p>', sim_category='spam')),
        ('spam', lambda i: _msg(i, from_email=f'crypto{i}@coin-profit.xyz', subject='Earn $5000 weekly from home', body='<p>100% free crypto investment. No obligation.</p>', sim_category='spam')),
        ('phishing', lambda i: _msg(i, from_name='Microsoft Account Team', from_email=f'secure{i}@micros0ft-login.xyz', subject='Urgent: verify your account immediately', body='<p>Your account was suspended. <a href="https://micros0ft-login.xyz/verify">Click here to verify your password</a></p>', sim_category='phishing')),
        ('phishing', lambda i: _msg(i, from_name='PayPal', from_email=f'billing{i}@paypa1-secure.click', subject='Action required: update your payment method', body='<p>Confirm your billing within 24 hours: https://paypa1-secure.click/login</p>', sim_category='phishing')),
        ('phishing', lambda i: _msg(i, from_name='CEO', from_email=f'ceo{i}@external-mail.net', subject='Wire transfer needed today', body='<p>I need you to process an urgent wire transfer. Gift card details attached.</p>', sim_category='phishing')),
        ('intrusion', lambda i: _msg(i, from_email=f'payload{i}@bad-host.tk', subject='Invoice attached', body='<script>document.cookie</script><p>See attachment</p>', attachments=[{'name': 'invoice.pdf.exe', 'size': '2 MB'}], sim_category='intrusion')),
        ('intrusion', lambda i: _msg(i, from_email=f'malware{i}@185.220.101.42', subject='Scan from printer', body='<p>Download: http://185.220.101.42/payload</p><iframe src="javascript:alert(1)"></iframe>', sim_category='intrusion')),
        ('false_positive', lambda i: _msg(i, from_name='DocuSign', from_email='noreply@docusign.net', subject='Please DocuSign: Subcontract', body='<p>Please review and sign the attached subcontract via DocuSign.</p>', sim_category='false_positive')),
        ('false_positive', lambda i: _msg(i, from_name='Case PM System', from_email='notifications@casepm.com', subject='Daily digest — 3 items need your attention', body='<p>Your daily project digest is ready.</p>', sim_category='false_positive')),
        ('spoofing', lambda i: _msg(i, from_name='IT Support', from_email=f'helpdesk{i}@casepm.com.evil.ru', subject='Password reset required', body='<p>Verify your credentials now.</p>', headers={'authentication-results': 'spf=fail dkim=fail dmarc=fail'}, sim_category='spoofing')),
    ]

    for i in range(count):
        category, builder = templates[i % len(templates)]
        corpus.append(builder(i))

    return corpus


def run_simulation(count: int = 1000, junk_level: str = 'standard') -> dict[str, Any]:
    corpus = generate_simulation_corpus(count)
    safe_senders = ['notifications@casepm.com']
    batch = scan_messages_batch(
        corpus,
        junk_level=junk_level,
        safe_senders=safe_senders,
        user_email='user@casepm.com',
    )
    by_sim: dict[str, dict[str, int]] = {}
    mismatches: list[dict] = []
    for msg in corpus:
        cat = msg.get('simCategory') or 'unknown'
        scan = batch['results'].get(msg['id'], {})
        action = scan.get('action', 'allow')
        by_sim.setdefault(cat, {'total': 0, 'warn': 0, 'quarantine': 0, 'block': 0, 'allow': 0})
        by_sim[cat]['total'] += 1
        if action == 'block':
            by_sim[cat]['block'] += 1
        elif action == 'quarantine':
            by_sim[cat]['quarantine'] += 1
        elif action == 'warn':
            by_sim[cat]['warn'] += 1
        else:
            by_sim[cat]['allow'] += 1

        expected_action = {
            'legitimate': 'allow',
            'false_positive': 'allow',
            'spam': 'quarantine',
            'phishing': 'quarantine',
            'intrusion': 'quarantine',
            'spoofing': 'quarantine',
        }.get(cat, 'warn')
        actual = action
        if cat in ('spam', 'phishing', 'intrusion', 'spoofing'):
            ok = actual in ('quarantine', 'block', 'warn')
        elif cat in ('legitimate', 'false_positive'):
            ok = actual == 'allow' or (cat == 'false_positive' and actual == 'warn')
        else:
            ok = True
        if not ok:
            mismatches.append({
                'id': msg['id'],
                'sim_category': cat,
                'expected': expected_action,
                'actual': actual,
                'score': scan.get('risk_score'),
                'warnings': scan.get('warnings', [])[:2],
            })

    caught_threats = sum(
        by_sim.get(c, {}).get('quarantine', 0)
        + by_sim.get(c, {}).get('block', 0)
        + by_sim.get(c, {}).get('warn', 0)
        for c in ('spam', 'phishing', 'intrusion', 'spoofing')
    )
    threat_total = sum(by_sim.get(c, {}).get('total', 0) for c in ('spam', 'phishing', 'intrusion', 'spoofing'))
    legit_allowed = by_sim.get('legitimate', {}).get('allow', 0)
    legit_total = by_sim.get('legitimate', {}).get('total', 0)

    return {
        'count': count,
        'junk_level': junk_level,
        'summary': batch['summary'],
        'by_category': by_sim,
        'threat_detection_rate': round(caught_threats / threat_total, 4) if threat_total else 1.0,
        'legitimate_pass_rate': round(legit_allowed / legit_total, 4) if legit_total else 1.0,
        'mismatch_count': len(mismatches),
        'mismatches_sample': mismatches[:15],
    }
