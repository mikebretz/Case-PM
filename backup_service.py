"""Local and cloud backup helpers for Case PM program data."""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime

BACKUP_DIR = os.path.join('instance', 'backups')
DB_PATH = os.path.join('instance', 'case_pm.db')
SETTINGS_PATH = os.path.join('instance', 'program_settings.json')


def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    rows = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if not name.endswith('.zip'):
            continue
        path = os.path.join(BACKUP_DIR, name)
        try:
            stat = os.stat(path)
            rows.append({
                'filename': name,
                'path': path,
                'size_bytes': stat.st_size,
                'created_at': datetime.utcfromtimestamp(stat.st_mtime).isoformat() + 'Z',
                'location': 'local',
            })
        except OSError:
            continue
    return rows


def create_local_backup(note=''):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'casepm_backup_{stamp}.zip'
    dest = os.path.join(BACKUP_DIR, filename)
    manifest = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'note': note or '',
        'files': [],
    }
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        if os.path.isfile(DB_PATH):
            zf.write(DB_PATH, 'case_pm.db')
            manifest['files'].append('case_pm.db')
        if os.path.isfile(SETTINGS_PATH):
            zf.write(SETTINGS_PATH, 'program_settings.json')
            manifest['files'].append('program_settings.json')
        uploads = 'uploads'
        if os.path.isdir(uploads):
            for root, _, files in os.walk(uploads):
                for fn in files:
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, '.')
                    zf.write(full, arc)
                    manifest['files'].append(arc)
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
    return {
        'ok': True,
        'filename': filename,
        'path': dest,
        'size_bytes': os.path.getsize(dest),
        'created_at': manifest['created_at'],
        'location': 'local',
    }


def run_configured_backup(backup_config):
    """Run local backup and optionally copy to cloud folder."""
    cfg = backup_config or {}
    result = create_local_backup(note=cfg.get('last_run_note') or 'manual')
    cloud = cfg.get('cloud') or {}
    if cloud.get('enabled') and cloud.get('local_mirror_path'):
        mirror = cloud['local_mirror_path'].strip()
        if mirror:
            os.makedirs(mirror, exist_ok=True)
            shutil.copy2(result['path'], os.path.join(mirror, result['filename']))
            result['cloud_mirror'] = mirror
    result['cloud_configured'] = bool(cloud.get('enabled'))
    result['cloud_provider'] = cloud.get('provider') or 'none'
    return result
