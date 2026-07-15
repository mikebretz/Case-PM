"""Case PM — network helpers for local / LAN / remote access."""

from __future__ import annotations

import socket


def get_lan_ip_addresses() -> list[str]:
    """Return likely LAN IPv4 addresses for this machine."""
    ips: list[str] = []

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        primary = s.getsockname()[0]
        s.close()
        if primary and not primary.startswith('127.'):
            ips.append(primary)
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith('127.') or ip in ips:
                continue
            ips.append(ip)
    except OSError:
        pass

    return ips


def access_urls(host: str, port: int) -> dict[str, list[str]]:
    """Build human-readable URLs others can use to reach Case PM."""
    local = [f'http://127.0.0.1:{port}', f'http://localhost:{port}']
    lan: list[str] = []

    if host in ('0.0.0.0', '::'):
        lan = [f'http://{ip}:{port}' for ip in get_lan_ip_addresses()]
    elif host not in ('127.0.0.1', 'localhost'):
        lan = [f'http://{host}:{port}']

    return {'local': local, 'lan': lan}


def _startup_build() -> str:
    try:
        from flask import current_app
        return str(current_app.config.get('CASEPM_STARTUP_BUILD') or '?')
    except Exception:
        return '?'


def print_startup_banner(host: str, port: int, remote: bool) -> None:
    urls = access_urls(host, port)
    build = _startup_build()
    print('\n' + '=' * 75)
    print('CASE PM SERVER')
    print('=' * 75)
    print(f'  Build: {build}  (footer on every page must match after updates)')
    print(f'  Listening on: {host}:{port}')
    print()
    print('  On this computer:')
    for url in urls['local']:
        print(f'    {url}')
    if urls['lan']:
        print()
        print('  Other devices on your Wi-Fi / office network:')
        for url in urls['lan']:
            print(f'    {url}')
    elif remote:
        print()
        print('  LAN: no network address detected — check your connection.')
    if remote:
        print()
        print('  Internet (outside your building):')
        print('    1. Keep this window open (RUN-AS-SERVER.bat)')
        print('    2. Open a SECOND window → START-INTERNET-TUNNEL.bat')
        print('    3. Share the https://....trycloudflare.com link (not 192.168.x.x)')
        print('    4. If tunnel fails, try START-INTERNET-TUNNEL-HTTP2.bat')
        print(f'    Or forward TCP port {port} on your router to this PC.')
    print()
    print('  Default login: admin@casepm.local / admin123')
    if remote:
        print('  SECURITY: change the admin password before sharing remote access.')
    if remote:
        print()
        print('  TROUBLESHOOTING "connection refused" on other computers:')
        print('    1. Use RUN-AS-SERVER.bat (not run.bat)')
        print('    2. Run ALLOW-REMOTE-ACCESS.bat once (Windows Firewall)')
        print('    3. Share http://YOUR-LAN-IP:5000 — never use 127.0.0.1 from another PC')
        print('    4. Different network? Use START-INTERNET-TUNNEL.bat')
        print()
        print('  AFTER CODE UPDATES (remote users still see old screens):')
        print('    1. On THIS server PC: double-click PULL-AND-RESTART-SERVER.bat')
        print('    2. Or Developer → Program Updates → Pull, then close this window and re-run RUN-AS-SERVER.bat')
        print('    3. Remote PCs: hard-refresh (Ctrl+Shift+R); footer build id must change')
    print('=' * 75 + '\n')
