"""Google Gmail mail via OAuth 2.0 and Gmail API."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from email.utils import parsedate_to_datetime

from email_oauth_credentials import (
    google_client_id as client_id,
    google_client_secret as client_secret,
    google_configured as is_configured,
)

GMAIL_BASE = 'https://gmail.googleapis.com/gmail/v1'
USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
DEFAULT_SCOPES = [
    'openid',
    'email',
    'profile',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]


def integration_info() -> dict:
    return {
        'configured': is_configured(),
        'client_id_set': bool(client_id()),
        'client_secret_set': bool(client_secret()),
        'required_env': [
            'GOOGLE_CLIENT_ID (or GMAIL_CLIENT_ID)',
            'GOOGLE_CLIENT_SECRET (or GMAIL_CLIENT_SECRET)',
            'Or save the same values under Program Settings → Integrations → Email OAuth.',
        ],
        'redirect_note': 'Register redirect URI: {base_url}/api/email/oauth/google/callback',
        'scopes': DEFAULT_SCOPES,
    }


def _token_url() -> str:
    return 'https://oauth2.googleapis.com/token'


def _auth_url() -> str:
    return 'https://accounts.google.com/o/oauth2/v2/auth'


def authorization_url(*, redirect_uri: str, state: str) -> str:
    params = {
        'client_id': client_id(),
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': ' '.join(DEFAULT_SCOPES),
        'state': state,
        'access_type': 'offline',
        'prompt': 'consent select_account',
        'include_granted_scopes': 'true',
    }
    return f"{_auth_url()}?{urllib.parse.urlencode(params)}"


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(detail or exc.reason) from exc


def exchange_code(code: str, *, redirect_uri: str) -> dict:
    payload = {
        'client_id': client_id(),
        'client_secret': client_secret(),
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }
    data = _post_form(_token_url(), payload)
    if 'access_token' not in data:
        raise RuntimeError(data.get('error_description') or data.get('error') or 'Token exchange failed')
    expires_in = int(data.get('expires_in') or 3600)
    data['expires_at'] = (datetime.utcnow() + timedelta(seconds=max(60, expires_in - 60))).isoformat() + 'Z'
    return data


def refresh_access_token(refresh_token: str) -> dict:
    payload = {
        'client_id': client_id(),
        'client_secret': client_secret(),
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    data = _post_form(_token_url(), payload)
    if 'access_token' not in data:
        raise RuntimeError(data.get('error_description') or data.get('error') or 'Token refresh failed')
    expires_in = int(data.get('expires_in') or 3600)
    data['expires_at'] = (datetime.utcnow() + timedelta(seconds=max(60, expires_in - 60))).isoformat() + 'Z'
    if not data.get('refresh_token'):
        data['refresh_token'] = refresh_token
    return data


def _gmail_request(access_token: str, path: str, *, method: str = 'GET', body: dict | None = None) -> dict:
    url = f'{GMAIL_BASE}{path}'
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {access_token}')
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(detail or exc.reason) from exc


def _userinfo_request(access_token: str) -> dict:
    req = urllib.request.Request(USERINFO_URL)
    req.add_header('Authorization', f'Bearer {access_token}')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(detail or exc.reason) from exc


def get_user_profile(access_token: str) -> dict:
    profile = _userinfo_request(access_token)
    try:
        gmail_profile = _gmail_request(access_token, '/users/me/profile')
        if gmail_profile.get('emailAddress'):
            profile['emailAddress'] = gmail_profile['emailAddress']
    except Exception:
        pass
    return profile


def test_connection(access_token: str) -> dict:
    profile = get_user_profile(access_token)
    email = (profile.get('email') or profile.get('emailAddress') or '').strip()
    return {
        'ok': True,
        'display_name': profile.get('name') or '',
        'email_address': email,
        'provider': 'google',
    }


def ensure_fresh_tokens(user_id: int, *, db, UserEmailConnection) -> dict:
    from user_email_connection_persistence import load_tokens, save_tokens
    tokens = load_tokens(user_id, UserEmailConnection=UserEmailConnection)
    if not tokens.get('access_token'):
        raise RuntimeError('Mailbox is not connected to Google Gmail.')
    expires_at = tokens.get('expires_at')
    stale = True
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace('Z', ''))
            stale = datetime.utcnow() >= exp
        except ValueError:
            stale = True
    if stale:
        refresh = tokens.get('refresh_token')
        if not refresh:
            raise RuntimeError('Google session expired — reconnect Gmail.')
        tokens = refresh_access_token(refresh)
        save_tokens(user_id, tokens, db=db, UserEmailConnection=UserEmailConnection)
    return tokens


def _header_map(payload: dict) -> dict:
    headers = {}
    for h in (payload.get('headers') or []):
        if isinstance(h, dict) and h.get('name'):
            headers[h['name'].lower()] = h.get('value') or ''
    return headers


def _parse_from(from_hdr: str) -> tuple[str, str]:
    if not from_hdr:
        return 'Unknown', ''
    m = re.match(r'^(?:"?([^"]*)"?\s)?<?([^>]+@[^>]+)>?$', from_hdr.strip())
    if m:
        name = (m.group(1) or m.group(2) or '').strip()
        addr = (m.group(2) or '').strip()
        return name or addr, addr
    return from_hdr, ''


def gmail_message_to_casepm(msg: dict, *, user_email: str) -> dict:
    payload = msg.get('payload') or {}
    headers = _header_map(payload)
    from_name, from_email = _parse_from(headers.get('from', ''))
    internal_date = msg.get('internalDate')
    if internal_date:
        try:
            received = datetime.fromtimestamp(int(internal_date) / 1000, dt_timezone.utc).isoformat().replace('+00:00', 'Z')
        except (TypeError, ValueError):
            received = datetime.utcnow().isoformat() + 'Z'
    else:
        try:
            received = parsedate_to_datetime(headers.get('date', '')).isoformat()
        except Exception:
            received = datetime.utcnow().isoformat() + 'Z'
    snippet = (msg.get('snippet') or '')[:240]
    labels = msg.get('labelIds') or []
    unread = 'UNREAD' in labels
    starred = 'STARRED' in labels
    category = 'primary'
    if 'CATEGORY_PROMOTIONS' in labels:
        category = 'promotions'
    elif 'CATEGORY_SOCIAL' in labels:
        category = 'social'
    elif 'CATEGORY_UPDATES' in labels:
        category = 'updates'
    elif 'CATEGORY_FORUMS' in labels:
        category = 'forums'
    gid = msg.get('id') or ''
    return {
        'id': f'gmail_{gid}',
        'gmailId': gid,
        'folder': 'inbox',
        'category': category,
        'focused': category == 'primary',
        'from': from_name,
        'fromEmail': from_email,
        'to': [user_email] if user_email else [],
        'subject': headers.get('subject') or '(No subject)',
        'preview': snippet,
        'body': f'<p>{snippet.replace(chr(10), "<br>")}</p>',
        'date': received,
        'unread': unread,
        'starred': starred,
        'flagged': False,
        'hasAttachments': False,
        'attachments': [],
        'labels': labels,
        'threadId': msg.get('threadId') or gid,
        'importance': 'normal',
        'snoozedUntil': None,
        'scheduledFor': None,
        'source': 'google_gmail',
    }


def sync_inbox_messages(user_id: int, *, db, UserEmailConnection, UserEmailMailbox, UserEmailSecurity=None, limit: int = 40) -> dict:
    from email_mailbox_persistence import load_user_mailbox, save_user_mailbox
    from user_email_connection_persistence import connection_status, mark_synced
    from email_security import scan_messages_batch, apply_quarantine_actions
    from email_security_persistence import load_security_state

    tokens = ensure_fresh_tokens(user_id, db=db, UserEmailConnection=UserEmailConnection)
    conn = connection_status(user_id, UserEmailConnection=UserEmailConnection)
    user_email = conn.get('email_address') or ''
    list_path = f'/users/me/messages?labelIds=INBOX&maxResults={int(limit)}'
    listing = _gmail_request(tokens['access_token'], list_path)
    stubs = listing.get('messages') or []
    mapped = []
    for stub in stubs:
        mid = stub.get('id')
        if not mid:
            continue
        detail = _gmail_request(
            tokens['access_token'],
            f'/users/me/messages/{urllib.parse.quote(mid, safe="")}'
            '?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date',
        )
        mapped.append(gmail_message_to_casepm(detail, user_email=user_email))

    sec = load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    prefs = sec.get('preferences') or {}
    batch = scan_messages_batch(
        mapped,
        junk_level=prefs.get('junkLevel') or 'standard',
        blocked_senders=sec.get('blocked_senders') or [],
        safe_senders=sec.get('safe_senders') or [],
        user_email=user_email,
        false_positive_overrides=sec.get('false_positives') or [],
    )
    for msg in mapped:
        scan = batch['results'].get(str(msg.get('id')), {})
        msg['security'] = scan
    if prefs.get('autoQuarantine', True):
        mapped = apply_quarantine_actions(mapped, batch['results'])

    payload = load_user_mailbox(user_id, UserEmailMailbox=UserEmailMailbox)
    existing = payload.get('messages') or []
    non_gmail = [m for m in existing if isinstance(m, dict) and m.get('source') != 'google_gmail']
    by_id = {m.get('gmailId') or m.get('id'): m for m in mapped if m.get('gmailId') or m.get('id')}
    merged = non_gmail + list(by_id.values())
    merged.sort(key=lambda m: m.get('date') or '', reverse=True)
    meta = dict(payload.get('meta') or {})
    settings = dict(meta.get('settings') or {})
    settings.update({
        'provider': 'google',
        'googleConnected': True,
        'emailAddress': user_email,
        'displayName': conn.get('display_name') or settings.get('displayName', ''),
    })
    meta['settings'] = settings
    save_user_mailbox(user_id, merged, meta, db=db, UserEmailMailbox=UserEmailMailbox)
    mark_synced(user_id, db=db, UserEmailConnection=UserEmailConnection)
    return {'synced': len(mapped), 'total_messages': len(merged)}
