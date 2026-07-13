"""Microsoft 365 / Outlook mail via OAuth 2.0 and Microsoft Graph."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
DEFAULT_SCOPES = [
    'openid', 'profile', 'email', 'offline_access',
    'User.Read', 'Mail.ReadWrite', 'Mail.Send',
]


def _env(name: str) -> str:
    return (os.environ.get(name) or '').strip()


def client_id() -> str:
    return _env('MICROSOFT_CLIENT_ID') or _env('AZURE_CLIENT_ID')


def client_secret() -> str:
    return _env('MICROSOFT_CLIENT_SECRET') or _env('AZURE_CLIENT_SECRET')


def tenant_id() -> str:
    return _env('MICROSOFT_TENANT_ID') or _env('AZURE_TENANT_ID') or 'common'


def is_configured() -> bool:
    return bool(client_id() and client_secret())


def integration_info() -> dict:
    return {
        'configured': is_configured(),
        'tenant_id': tenant_id() if is_configured() else None,
        'client_id_set': bool(client_id()),
        'client_secret_set': bool(client_secret()),
        'required_env': [
            'MICROSOFT_CLIENT_ID (or AZURE_CLIENT_ID)',
            'MICROSOFT_CLIENT_SECRET (or AZURE_CLIENT_SECRET)',
            'MICROSOFT_TENANT_ID (optional — default common/multi-tenant)',
        ],
        'redirect_note': 'Register redirect URI: {base_url}/api/email/oauth/microsoft/callback',
        'scopes': DEFAULT_SCOPES,
    }


def _token_url() -> str:
    return f'https://login.microsoftonline.com/{tenant_id()}/oauth2/v2.0/token'


def _auth_url() -> str:
    return f'https://login.microsoftonline.com/{tenant_id()}/oauth2/v2.0/authorize'


def authorization_url(*, redirect_uri: str, state: str) -> str:
    params = {
        'client_id': client_id(),
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'response_mode': 'query',
        'scope': ' '.join(DEFAULT_SCOPES),
        'state': state,
        'prompt': 'select_account',
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
        'scope': ' '.join(DEFAULT_SCOPES),
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
        'scope': ' '.join(DEFAULT_SCOPES),
    }
    data = _post_form(_token_url(), payload)
    if 'access_token' not in data:
        raise RuntimeError(data.get('error_description') or data.get('error') or 'Token refresh failed')
    expires_in = int(data.get('expires_in') or 3600)
    data['expires_at'] = (datetime.utcnow() + timedelta(seconds=max(60, expires_in - 60))).isoformat() + 'Z'
    if not data.get('refresh_token'):
        data['refresh_token'] = refresh_token
    return data


def _graph_request(access_token: str, path: str, *, method: str = 'GET', body: dict | None = None) -> dict:
    url = f'{GRAPH_BASE}{path}'
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


def get_user_profile(access_token: str) -> dict:
    return _graph_request(access_token, '/me?$select=displayName,mail,userPrincipalName,id')


def test_connection(access_token: str) -> dict:
    profile = get_user_profile(access_token)
    email = (profile.get('mail') or profile.get('userPrincipalName') or '').strip()
    return {
        'ok': True,
        'display_name': profile.get('displayName') or '',
        'email_address': email,
        'provider': 'microsoft',
    }


def ensure_fresh_tokens(user_id: int, *, db, UserEmailConnection) -> dict:
    from user_email_connection_persistence import load_tokens, save_tokens
    tokens = load_tokens(user_id, UserEmailConnection=UserEmailConnection)
    if not tokens.get('access_token'):
        raise RuntimeError('Mailbox is not connected to Microsoft 365.')
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
            raise RuntimeError('Microsoft session expired — reconnect Outlook.')
        tokens = refresh_access_token(refresh)
        save_tokens(user_id, tokens, db=db, UserEmailConnection=UserEmailConnection)
    return tokens


def graph_message_to_casepm(msg: dict, *, user_email: str) -> dict:
    sender = (msg.get('from') or {}).get('emailAddress') or {}
    received = msg.get('receivedDateTime') or msg.get('sentDateTime') or datetime.utcnow().isoformat() + 'Z'
    return {
        'id': f"graph_{msg.get('id', '')}",
        'graphId': msg.get('id'),
        'folder': 'inbox',
        'category': 'primary',
        'focused': True,
        'from': sender.get('name') or sender.get('address') or 'Unknown',
        'fromEmail': sender.get('address') or '',
        'to': [user_email] if user_email else [],
        'subject': msg.get('subject') or '(No subject)',
        'preview': (msg.get('bodyPreview') or '')[:240],
        'body': f"<p>{(msg.get('bodyPreview') or '').replace(chr(10), '<br>')}</p>",
        'date': received,
        'unread': not bool(msg.get('isRead')),
        'starred': bool(msg.get('flag', {}).get('flagStatus') == 'flagged') if isinstance(msg.get('flag'), dict) else False,
        'flagged': False,
        'hasAttachments': bool(msg.get('hasAttachments')),
        'attachments': [],
        'labels': [],
        'threadId': msg.get('conversationId') or msg.get('id'),
        'importance': (msg.get('importance') or 'normal').lower(),
        'snoozedUntil': None,
        'scheduledFor': None,
        'source': 'microsoft_graph',
    }


def sync_inbox_messages(user_id: int, *, db, UserEmailConnection, UserEmailMailbox, limit: int = 40) -> dict:
    from email_mailbox_persistence import load_user_mailbox, save_user_mailbox
    from user_email_connection_persistence import connection_status, mark_synced

    tokens = ensure_fresh_tokens(user_id, db=db, UserEmailConnection=UserEmailConnection)
    conn = connection_status(user_id, UserEmailConnection=UserEmailConnection)
    user_email = conn.get('email_address') or ''
    path = f"/me/mailFolders/inbox/messages?$top={int(limit)}&$orderby=receivedDateTime desc"
    path += '&$select=id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,conversationId,importance,flag'
    data = _graph_request(tokens['access_token'], path)
    items = data.get('value') or []
    mapped = [graph_message_to_casepm(m, user_email=user_email) for m in items]

    payload = load_user_mailbox(user_id, UserEmailMailbox=UserEmailMailbox)
    existing = payload.get('messages') or []
    non_graph = [m for m in existing if isinstance(m, dict) and m.get('source') != 'microsoft_graph']
    by_id = {m.get('graphId') or m.get('id'): m for m in mapped if m.get('graphId') or m.get('id')}
    merged = non_graph + list(by_id.values())
    merged.sort(key=lambda m: m.get('date') or '', reverse=True)
    meta = dict(payload.get('meta') or {})
    settings = dict(meta.get('settings') or {})
    settings.update({
        'provider': 'microsoft',
        'microsoftConnected': True,
        'emailAddress': user_email,
        'displayName': conn.get('display_name') or settings.get('displayName', ''),
    })
    meta['settings'] = settings
    save_user_mailbox(user_id, merged, meta, db=db, UserEmailMailbox=UserEmailMailbox)
    mark_synced(user_id, db=db, UserEmailConnection=UserEmailConnection)
    return {'synced': len(mapped), 'total_messages': len(merged)}
