"""Sage 300 Web API POST helper (best-effort; logs payload when live POST unavailable)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from sage300_web_client import build_resource_url, resolve_web_api_config, _auth_header


def post_resource(module: str, resource: str, payload: dict, *, company: str = '') -> dict:
    cfg = resolve_web_api_config()
    if not cfg.get('configured'):
        return {'ok': False, 'mode': 'unconfigured', 'error': 'Sage Web API not configured'}
    if not cfg.get('user') or not cfg.get('password'):
        return {
            'ok': False,
            'mode': 'queued_only',
            'error': 'No credentials — payload retained in Case PM queue only',
            'payload': payload,
        }
    url = build_resource_url(company, module, resource, top=0)
    url = url.split('?')[0]
    body = json.dumps(payload).encode('utf-8')
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': _auth_header(cfg['user'], cfg['password']),
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode('utf-8')
            data = json.loads(raw) if raw else {}
            return {'ok': True, 'mode': 'live', 'url': url, 'data': data}
    except urllib.error.HTTPError as exc:
        err_body = ''
        try:
            err_body = exc.read().decode('utf-8')[:500]
        except Exception:
            pass
        return {
            'ok': False,
            'mode': 'error',
            'url': url,
            'error': f'HTTP {exc.code}: {err_body or exc.reason}',
            'payload': payload,
        }
    except Exception as exc:
        return {'ok': False, 'mode': 'error', 'error': str(exc), 'payload': payload}
