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


def print_startup_banner(host: str, port: int, remote: bool) -> None:
    urls = access_urls(host, port)
    print('\n' + '=' * 75)
    print('CASE PM SERVER')
    print('=' * 75)
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
        print('    Run START-INTERNET-TUNNEL.bat in a second window for a shareable link.')
        print(f'    Or forward TCP port {port} on your router to this PC.')
    print()
    print('  Default login: admin@casepm.local / admin123')
    if remote:
        print('  SECURITY: change the admin password before sharing remote access.')
    print('=' * 75 + '\n')
