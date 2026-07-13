"""Outbound workflow email + in-app notifications (SMTP when configured)."""
from __future__ import annotations

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import case_workflow as cw


def _load_smtp_settings():
    try:
        from program_settings_persistence import load_email_settings_mirror
        return load_email_settings_mirror() or {}
    except Exception:
        return {}


def _base_url():
    try:
        from flask import request
        if request:
            return request.host_url.rstrip('/')
    except Exception:
        pass
    return ''


def send_workflow_email(to_email, subject, html_body, text_body=None):
    """Send email via SMTP if program settings are configured. Returns True if sent."""
    if not to_email or '@' not in str(to_email):
        return False
    settings = _load_smtp_settings()
    host = (settings.get('smtpHost') or settings.get('smtp_host') or '').strip()
    if not host:
        return False
    port = int(settings.get('smtpPort') or settings.get('smtp_port') or 587)
    user = (settings.get('smtpUser') or settings.get('smtp_user') or '').strip()
    password = settings.get('smtpPassword') or settings.get('smtp_password') or ''
    use_tls = settings.get('smtpTls', settings.get('smtp_tls', True))
    from_addr = (settings.get('emailAddress') or settings.get('from_email') or user or 'noreply@casepm.local').strip()

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_email
    plain = text_body or _html_to_plain(html_body)
    msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls()
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception:
        return False


def _html_to_plain(html):
    import re
    text = re.sub(r'<br\s*/?>', '\n', html or '', flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _module_notify_key(module: str) -> str:
    mapping = {
        'RFIs': 'rfis',
        'RFI': 'rfis',
        'Submittals': 'submittals',
        'Change Orders': 'change_orders',
        'Pay Applications': 'pay_applications',
        'Commitments': 'commitments',
        'Estimating': 'estimating_rfp',
        'Safety': 'safety',
        'Schedule': 'schedule',
        'Documents': 'documents',
        'Inspections': 'inspections',
        'Daily Log': 'daily_log',
        'Punch List': 'punch_list',
        'Email': 'email',
    }
    return mapping.get(module or '', 'change_orders')


def notify_user_workflow(
    user,
    *,
    title,
    description,
    action_url,
    project_id=None,
    module='Change Orders',
    requires_action=True,
    priority='high',
    send_email=True,
):
    """In-app message + optional outbound email to the user's address."""
    if not user:
        return
    uid = getattr(user, 'id', None)
    if not uid:
        return
    module_key = _module_notify_key(module)
    try:
        from user_extended_prefs import user_should_receive_notification
        allow_in_app = user_should_receive_notification(user, module_key, 'in_app')
        allow_email = send_email and user_should_receive_notification(user, module_key, 'email')
    except Exception:
        allow_in_app = True
        allow_email = bool(send_email)
    if not allow_in_app and not allow_email:
        return
    body = f'<p>{description}</p>'
    if action_url:
        full_url = action_url if action_url.startswith('http') else f'{_base_url()}{action_url}'
        body += f'<p><a href="{full_url}">Open in Case PM</a></p>'
    if allow_in_app:
        cw.notify_user(uid, title, description, action_url)
        cw.create_internal_message(
            uid,
            folder='action-required' if requires_action else 'team',
            msg_type='alert',
            subject=title,
            preview=(description or '')[:500],
            body=body,
            project_id=project_id,
            from_label=module,
            module=module,
            action_url=action_url,
            action_label='Review',
            priority=priority,
            requires_action=requires_action,
        )
    if allow_email and getattr(user, 'email', None):
        send_workflow_email(
            user.email,
            title,
            f'<div style="font-family:sans-serif"><h2>{title}</h2>{body}</div>',
            description,
        )


def notify_role_workflow(
    User,
    role,
    *,
    title,
    description,
    action_url,
    project_id=None,
    module='Change Orders',
    can_act_fn=None,
):
    """Notify all active users matching a ball-in-court role."""
    if not User:
        return
    users = User.query.filter_by(status='Active').all()
    for u in users:
        if can_act_fn and not can_act_fn(u, role):
            continue
        if not can_act_fn and getattr(u, 'role', None) != role and getattr(u, 'role', None) != 'Admin':
            continue
        notify_user_workflow(
            u,
            title=title,
            description=description,
            action_url=action_url,
            project_id=project_id,
            module=module,
        )
