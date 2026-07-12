"""Local and cloud backup helpers for Case PM program data."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime

DEFAULT_BACKUP_DIR = os.path.join('instance', 'backups')
DB_PATH = os.path.join('instance', 'case_pm.db')
SETTINGS_PATH = os.path.join('instance', 'program_settings.json')
UPLOADS_DIR = 'uploads'


def backup_dir(config=None):
    """Resolve configured local backup folder."""
    if config and (config.get('local_path') or '').strip():
        return config['local_path'].strip()
    return DEFAULT_BACKUP_DIR


def _safe_backup_filename(filename):
    name = os.path.basename((filename or '').strip().replace('\\', '/'))
    if not name or not name.lower().endswith('.zip'):
        raise ValueError('Backup must be a .zip file')
    if name in ('.', '..') or '..' in name or '/' in name or '\\' in name:
        raise ValueError('Invalid backup filename')
    return name


def _resolve_backup_path(filename, dir_path=None):
    name = _safe_backup_filename(filename)
    root = os.path.abspath(dir_path or DEFAULT_BACKUP_DIR)
    path = os.path.abspath(os.path.join(root, name))
    prefix = root if root.endswith(os.sep) else root + os.sep
    if path != root and not path.startswith(prefix):
        raise ValueError('Invalid backup path')
    if not os.path.isfile(path):
        raise ValueError(f'Backup not found: {name}')
    return path


def _validate_backup_zip(zip_path):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        if 'case_pm.db' not in zf.namelist():
            raise ValueError('Backup zip must contain case_pm.db')
    return True


def dispose_db_engine(db):
    """Release SQLite handles before replacing the database file."""
    if not db:
        return
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass
    try:
        db.engine.dispose()
    except Exception:
        pass


def list_backups(config=None):
    dir_path = backup_dir(config)
    if not os.path.isdir(dir_path):
        return []
    rows = []
    for name in sorted(os.listdir(dir_path), reverse=True):
        if not name.endswith('.zip'):
            continue
        path = os.path.join(dir_path, name)
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


def create_local_backup(note='', config=None):
    dir_path = backup_dir(config)
    os.makedirs(dir_path, exist_ok=True)
    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
    filename = f'casepm_backup_{stamp}.zip'
    dest = os.path.join(dir_path, filename)
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
        if os.path.isdir(UPLOADS_DIR):
            for root, _, files in os.walk(UPLOADS_DIR):
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


def _extract_backup_contents(zip_path, tmp_dir):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(tmp_dir)


def _apply_extracted_backup(tmp_dir):
    """Copy extracted backup payload into the live program folders."""
    restored = []

    db_src = os.path.join(tmp_dir, 'case_pm.db')
    if os.path.isfile(db_src):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        shutil.copy2(db_src, DB_PATH)
        restored.append('case_pm.db')

    settings_src = os.path.join(tmp_dir, 'program_settings.json')
    if os.path.isfile(settings_src):
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        shutil.copy2(settings_src, SETTINGS_PATH)
        restored.append('program_settings.json')

    uploads_src = os.path.join(tmp_dir, UPLOADS_DIR)
    if os.path.isdir(uploads_src):
        if os.path.isdir(UPLOADS_DIR):
            shutil.rmtree(UPLOADS_DIR)
        shutil.copytree(uploads_src, UPLOADS_DIR)
        restored.append('uploads/')

    return restored


def restore_from_backup(filename, backup_config=None, db=None):
    """Install program data from a backup zip. Creates a safety backup first."""
    dir_path = backup_dir(backup_config)
    zip_path = _resolve_backup_path(filename, dir_path)
    _validate_backup_zip(zip_path)

    safety = create_local_backup(note='auto-before-restore', config=backup_config)
    dispose_db_engine(db)

    with tempfile.TemporaryDirectory(prefix='casepm_restore_') as tmp_dir:
        _extract_backup_contents(zip_path, tmp_dir)
        restored = _apply_extracted_backup(tmp_dir)

    return {
        'ok': True,
        'restored_from': _safe_backup_filename(filename),
        'restored_files': restored,
        'safety_backup': safety.get('filename'),
        'reload_required': True,
    }


def save_uploaded_backup(file_storage, backup_config=None):
    """Save an uploaded .zip into the backup folder after validation."""
    if not file_storage or not file_storage.filename:
        raise ValueError('Backup file is required')
    original = _safe_backup_filename(file_storage.filename)
    dir_path = backup_dir(backup_config)
    os.makedirs(dir_path, exist_ok=True)
    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    if original.startswith('casepm_backup_'):
        filename = original
    else:
        filename = f'casepm_upload_{stamp}.zip'
    dest = os.path.join(dir_path, filename)
    file_storage.save(dest)
    _validate_backup_zip(dest)
    stat = os.stat(dest)
    return {
        'ok': True,
        'filename': filename,
        'path': dest,
        'size_bytes': stat.st_size,
        'created_at': datetime.utcfromtimestamp(stat.st_mtime).isoformat() + 'Z',
        'location': 'uploaded',
    }


def clear_all_program_data(backup_config=None, db=None):
    """Wipe database, uploads, and settings after creating a safety backup."""
    safety = create_local_backup(note='auto-before-clear-all', config=backup_config)
    dispose_db_engine(db)

    if os.path.isfile(DB_PATH):
        os.remove(DB_PATH)
    if os.path.isfile(SETTINGS_PATH):
        os.remove(SETTINGS_PATH)
    if os.path.isdir(UPLOADS_DIR):
        shutil.rmtree(UPLOADS_DIR)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    for sub in ('photos', 'coi', 'documents', 'attachments', 'profile_images', 'signatures'):
        os.makedirs(os.path.join(UPLOADS_DIR, sub), exist_ok=True)

    return {
        'ok': True,
        'safety_backup': safety.get('filename'),
        'reload_required': True,
    }


def run_configured_backup(backup_config):
    """Run local backup and optionally copy to cloud folder."""
    cfg = backup_config or {}
    result = create_local_backup(note=cfg.get('last_run_note') or 'manual', config=cfg)
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
