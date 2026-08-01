"""
Third-party plugin and external integration security for Case PM.

Validates outbound HTTP (SSRF protection), documents approved CDN vendors,
and builds Content-Security-Policy for browser-side plugin isolation.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Approved server-side API hosts (outbound fetch allowlist).
ALLOWED_EXTERNAL_HOSTS = frozenset({
    'nominatim.openstreetmap.org',
    'geocoding-api.open-meteo.com',
    'api.open-meteo.com',
    'router.project-osrm.org',
    'graph.microsoft.com',
    'login.microsoftonline.com',
    'api.openai.com',
    'api.anthropic.com',
    'account-d.docusign.com',
    'account.docusign.com',
    'demo.docusign.net',
    'www.osha.gov',
    'www.java.com',
})

# CDN / font hosts referenced in templates (supply-chain inventory).
APPROVED_CDN_HOSTS = frozenset({
    'cdn.tailwindcss.com',
    'cdnjs.cloudflare.com',
    'cdn.jsdelivr.net',
    'unpkg.com',
    'cdn.dhtmlx.com',
    'ajax.googleapis.com',
    'fonts.googleapis.com',
    'fonts.gstatic.com',
    'sheetjs.com',
})

# Browser plugins loaded from CDNs — pinned versions in templates.
PLUGIN_INVENTORY = [
    {'id': 'tailwind', 'host': 'cdn.tailwindcss.com', 'purpose': 'UI styling (JIT)', 'pages': 'base layout'},
    {'id': 'fontawesome', 'host': 'cdnjs.cloudflare.com', 'version': '6.5.1', 'purpose': 'Icons', 'pages': 'global'},
    {'id': 'leaflet', 'host': 'unpkg.com', 'version': '1.9.4', 'purpose': 'Company job map', 'pages': 'company_map'},
    {'id': 'tinymce', 'host': 'cdn.jsdelivr.net', 'version': '6.8.2', 'purpose': 'Word editor', 'pages': 'word_editor'},
    {'id': 'mammoth', 'host': 'cdn.jsdelivr.net', 'version': '1.6.0', 'purpose': 'DOCX import', 'pages': 'word_editor'},
    {'id': 'html-docx-js', 'host': 'cdn.jsdelivr.net', 'version': '0.3.1', 'purpose': 'DOCX export', 'pages': 'word_editor'},
    {'id': 'luckysheet', 'host': 'cdn.jsdelivr.net', 'version': '2.1.13', 'purpose': 'Excel editor', 'pages': 'sheet_editor'},
    {'id': 'luckyexcel', 'host': 'cdn.jsdelivr.net', 'version': '1.0.1', 'purpose': 'XLSX import', 'pages': 'sheet_editor'},
    {'id': 'sheetjs', 'host': 'cdn.jsdelivr.net', 'version': '0.20.3', 'purpose': 'Spreadsheet I/O', 'pages': 'sheet_editor, financials, submittals'},
    {'id': 'chartjs', 'host': 'cdn.jsdelivr.net', 'version': '4.4.1', 'purpose': 'Dashboard charts', 'pages': 'dashboard'},
    {'id': 'pdfjs', 'host': 'cdnjs.cloudflare.com', 'version': '3.11.174', 'purpose': 'PDF viewer', 'pages': 'submittals, drawings, estimating'},
    {'id': 'dhtmlx-gantt', 'host': 'cdn.dhtmlx.com', 'purpose': 'Schedule Gantt (JS); CSS self-hosted without bundled Inter fonts', 'pages': 'schedule'},
    {'id': 'model-viewer', 'host': 'ajax.googleapis.com', 'version': '3.4.0', 'purpose': 'BIM 3D viewer', 'pages': 'operations_center'},
]

PRIVATE_IP_NETWORKS = (
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('100.64.0.0/10'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
)

_COORD_RE = re.compile(r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?$')  # reserved for future path validation


def _hostname_blocked(hostname: str) -> bool:
    host = (hostname or '').strip().lower().rstrip('.')
    if not host:
        return True
    if host in ('localhost', 'metadata.google.internal', 'metadata.goog'):
        return True
    if host.endswith('.local') or host.endswith('.internal'):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in PRIVATE_IP_NETWORKS)
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
                if any(addr in net for net in PRIVATE_IP_NETWORKS):
                    return True
            except ValueError:
                continue
    except OSError:
        return True
    return False


def validate_external_url(url: str, *, extra_hosts: frozenset[str] | None = None) -> str:
    """Return normalized https URL or raise ValueError (SSRF / allowlist)."""
    raw = (url or '').strip()
    if not raw:
        raise ValueError('URL required')
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ('https', 'http'):
        raise ValueError('Only http(s) URLs are allowed')
    host = (parsed.hostname or '').lower()
    allowed = set(ALLOWED_EXTERNAL_HOSTS)
    if extra_hosts:
        allowed |= set(extra_hosts)
    if host not in allowed:
        raise ValueError(f'Host not in external allowlist: {host}')
    if _hostname_blocked(host):
        raise ValueError('Blocked host')
    if parsed.username or parsed.password:
        raise ValueError('URL credentials not allowed')
    return parsed.geturl()


def safe_http_json(
    url: str,
    *,
    timeout: int = 15,
    headers: dict | None = None,
    extra_hosts: frozenset[str] | None = None,
) -> dict | list:
    """Fetch JSON only from allowlisted external hosts."""
    safe_url = validate_external_url(url, extra_hosts=extra_hosts)
    req = urllib.request.Request(safe_url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get('Content-Type') or '').lower()
            if 'json' not in ctype and 'javascript' not in ctype:
                # Some APIs omit content-type; cap size to reduce abuse.
                body = resp.read(2_000_000)
            else:
                body = resp.read(2_000_000)
            import json
            return json.loads(body.decode('utf-8'))
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc


def validate_coordinates(lat: float, lng: float) -> tuple[float, float]:
    """Reject out-of-range or non-finite coordinates (routing/geocode abuse)."""
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid coordinates') from exc
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
        raise ValueError('Coordinates out of range')
    return lat_f, lng_f


def build_osrm_url(origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float) -> str:
    o_lat, o_lng = validate_coordinates(origin_lat, origin_lng)
    d_lat, d_lng = validate_coordinates(dest_lat, dest_lng)
    base = 'https://router.project-osrm.org/route/v1/driving'
    return f'{base}/{o_lng:.6f},{o_lat:.6f};{d_lng:.6f},{d_lat:.6f}'


def escape_html_text(value: Any) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def build_content_security_policy() -> str:
    """CSP restricting script/style loads to self + approved CDNs."""
    cdn_scripts = ' '.join(f'https://{h}' for h in sorted(APPROVED_CDN_HOSTS))
    return (
        "default-src 'self'; "
        f"script-src 'self' {cdn_scripts} 'unsafe-inline' 'unsafe-eval'; "
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {cdn_scripts}; "
        f"font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com {cdn_scripts}; "
        "img-src 'self' data: blob: https:; "
        f"connect-src 'self' {cdn_scripts} https://router.project-osrm.org https://nominatim.openstreetmap.org "
        "https://geocoding-api.open-meteo.com https://api.open-meteo.com https://graph.microsoft.com; "
        "frame-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'"
    )


def plugin_inventory_payload() -> dict[str, Any]:
    return {
        'plugins': PLUGIN_INVENTORY,
        'cdn_hosts': sorted(APPROVED_CDN_HOSTS),
        'external_api_hosts': sorted(ALLOWED_EXTERNAL_HOSTS),
        'recommendations': [
            'CDN scripts are version-pinned in templates; do not load unpinned /latest URLs.',
            'Self-host critical vendors under /static/vendor/ for stricter CSP (future).',
            'Office editors (TinyMCE, Luckysheet) sanitize pasted HTML client-side; do not paste untrusted macros.',
            'Map/geocode APIs are server-side only — clients cannot redirect fetches to arbitrary hosts.',
        ],
    }


def safe_notification_url(url: str, *, origin: str) -> str:
    """Validate service-worker push notification target (open redirect protection)."""
    raw = (url or '/').strip() or '/'
    try:
        parsed = urllib.parse.urlparse(raw if '://' in raw else urllib.parse.urljoin(origin, raw))
        base = urllib.parse.urlparse(origin)
        if parsed.scheme not in ('http', 'https') or parsed.netloc != base.netloc:
            return '/'
        path = parsed.path or '/'
        if '..' in path.split('/'):
            return '/'
        return path + (('?' + parsed.query) if parsed.query else '')
    except Exception:
        return '/'
