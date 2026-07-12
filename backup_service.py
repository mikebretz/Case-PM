"""Local and cloud backup helpers for Case PM program data."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_BACKUP_DIR = os.path.join('instance', 'backups')
DB_PATH = os.path.join('instance', 'case_pm.db')
SETTINGS_PATH = os.path.join('instance', 'program_settings.json')
UPLOADS_DIR = 'uploads'
DISPLAY_TZ = ZoneInfo('America/New_York')

_BACKUP_JOBS = {}
_BACKUP_JOBS_LOCK = threading.Lock()


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def format_display_time(dt_or_iso):
    """Format a UTC timestamp for display in US Eastern time (EST/EDT)."""
    if not dt_or_iso:
        return ''
    if isinstance(dt_or_iso, str):
        dt = datetime.fromisoformat(dt_or_iso.replace('Z', '+00:00'))
    else:
        dt = dt_or_iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(DISPLAY_TZ)
    tz_label = local.strftime('%Z')
    return local.strftime(f'%b %d, %Y %I:%M %p {tz_label}')


def _notify_progress(progress_cb, percent, message, current_file=''):
    if progress_cb:
        progress_cb(int(max(0, min(100, percent))), message, current_file)
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


def plan_backup_destinations(config=None):
    """Describe where the next backup will be written."""
    cfg = config or {}
    local = os.path.abspath(backup_dir(cfg))
    destinations = [{'label': 'Local backup folder', 'path': local}]
    cloud = cfg.get('cloud') or {}
    mirror_raw = (cloud.get('local_mirror_path') or '').strip()
    if mirror_raw:
        try:
            mirror = normalize_mirror_path(mirror_raw)
            destinations.append({'label': 'Off-site mirror (OneDrive/NAS)', 'path': mirror})
        except ValueError as exc:
            destinations.append({'label': 'Off-site mirror', 'path': mirror_raw, 'warning': str(exc)})
    return destinations


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
            created_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            created_iso = created_dt.isoformat().replace('+00:00', 'Z')
            rows.append({
                'filename': name,
                'path': path,
                'size_bytes': stat.st_size,
                'created_at': created_iso,
                'created_at_display': format_display_time(created_dt),
                'location': 'local',
            })
        except OSError:
            continue
    return rows


def create_local_backup(note='', config=None, progress_cb=None):
    dir_path = backup_dir(config)
    os.makedirs(dir_path, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
    filename = f'casepm_backup_{stamp}.zip'
    dest = os.path.join(dir_path, filename)
    created_iso = utc_now_iso()
    manifest = {
        'created_at': created_iso,
        'created_at_display': format_display_time(created_iso),
        'note': note or '',
        'files': [],
    }
    _notify_progress(progress_cb, 5, f'Creating backup in {dir_path}…')

    upload_files = []
    if os.path.isdir(UPLOADS_DIR):
        for root, _, files in os.walk(UPLOADS_DIR):
            for fn in files:
                upload_files.append(os.path.join(root, fn))

    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        if os.path.isfile(DB_PATH):
            _notify_progress(progress_cb, 12, 'Adding database (case_pm.db)…', 'case_pm.db')
            zf.write(DB_PATH, 'case_pm.db')
            manifest['files'].append('case_pm.db')
        if os.path.isfile(SETTINGS_PATH):
            _notify_progress(progress_cb, 22, 'Adding program settings…', 'program_settings.json')
            zf.write(SETTINGS_PATH, 'program_settings.json')
            manifest['files'].append('program_settings.json')
        total_uploads = len(upload_files)
        if total_uploads:
            _notify_progress(progress_cb, 28, f'Adding uploads (0/{total_uploads})…')
            for idx, full in enumerate(upload_files, start=1):
                arc = os.path.relpath(full, '.')
                zf.write(full, arc)
                manifest['files'].append(arc)
                pct = 28 + int((idx / total_uploads) * 52)
                _notify_progress(progress_cb, pct, f'Adding uploads ({idx}/{total_uploads})…', arc)
        else:
            _notify_progress(progress_cb, 55, 'No upload files to include')
        _notify_progress(progress_cb, 88, 'Writing manifest and finishing zip…', filename)
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))

    _notify_progress(progress_cb, 92, f'Local backup saved: {filename}', dest)
    return {
        'ok': True,
        'filename': filename,
        'path': dest,
        'size_bytes': os.path.getsize(dest),
        'created_at': created_iso,
        'created_at_display': format_display_time(created_iso),
        'location': 'local',
        'local_folder': os.path.abspath(dir_path),
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
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    if original.startswith('casepm_backup_'):
        filename = original
    else:
        filename = f'casepm_upload_{stamp}.zip'
    dest = os.path.join(dir_path, filename)
    file_storage.save(dest)
    _validate_backup_zip(dest)
    stat = os.stat(dest)
    created_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    created_iso = created_dt.isoformat().replace('+00:00', 'Z')
    return {
        'ok': True,
        'filename': filename,
        'path': dest,
        'size_bytes': stat.st_size,
        'created_at': created_iso,
        'created_at_display': format_display_time(created_dt),
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


def normalize_mirror_path(path):
    """Normalize a local mirror folder path (OneDrive sync folder, NAS, etc.)."""
    cleaned = (path or '').strip().strip('"').strip("'")
    if not cleaned:
        return ''
    if cleaned.lower().startswith(('http://', 'https://', 'onedrive://')):
        raise ValueError(
            'Use the local OneDrive folder on your PC (for example '
            'C:\\Users\\YourName\\OneDrive\\CasePM-Backups), not a web link.'
        )
    cleaned = os.path.expanduser(cleaned)
    cleaned = os.path.expandvars(cleaned)
    return os.path.normpath(cleaned)


def _mirror_backup_to_cloud(result, cloud, *, manual=False, progress_cb=None):
    """Copy the local backup zip to an off-site mirror folder when configured."""
    cloud = cloud or {}
    provider = (cloud.get('provider') or 'local_folder').strip().lower()
    mirror_raw = (cloud.get('local_mirror_path') or '').strip()
    enabled = bool(cloud.get('enabled'))

    if provider not in ('local_folder', 'folder', 'onedrive', 'nas', ''):
        return {
            'cloud_mirror_attempted': False,
            'cloud_mirror_skipped': f'Provider "{provider}" is not wired up yet — use Network / NAS folder for OneDrive.',
            'cloud_provider': provider,
        }

    if not mirror_raw:
        return {
            'cloud_mirror_attempted': False,
            'cloud_mirror_skipped': 'No mirror folder path configured.',
            'cloud_provider': provider or 'local_folder',
        }

    if not enabled and not manual:
        return {
            'cloud_mirror_attempted': False,
            'cloud_mirror_skipped': 'Cloud mirror is disabled.',
            'cloud_provider': provider or 'local_folder',
        }

    mirror = normalize_mirror_path(mirror_raw)
    dest_file = os.path.join(mirror, result['filename'])
    _notify_progress(progress_cb, 94, f'Copying to off-site folder…', mirror)
    try:
        os.makedirs(mirror, exist_ok=True)
        shutil.copy2(result['path'], dest_file)
    except OSError as exc:
        raise ValueError(
            f'Could not copy backup to mirror folder "{mirror}": {exc}'
        ) from exc

    if not os.path.isfile(dest_file):
        raise ValueError(f'Backup copy failed — file not found at "{dest_file}"')

    _notify_progress(progress_cb, 98, f'Off-site copy complete', dest_file)
    return {
        'cloud_mirror_attempted': True,
        'cloud_mirror': mirror,
        'cloud_mirror_file': dest_file,
        'cloud_mirror_status': 'success',
        'cloud_provider': provider or 'local_folder',
    }


def run_configured_backup(backup_config, *, manual=False, progress_cb=None):
    """Run local backup and optionally copy to a configured mirror folder."""
    cfg = backup_config or {}
    result = create_local_backup(
        note=cfg.get('last_run_note') or 'manual',
        config=cfg,
        progress_cb=progress_cb,
    )
    cloud = cfg.get('cloud') or {}
    mirror_info = _mirror_backup_to_cloud(result, cloud, manual=manual, progress_cb=progress_cb)
    result.update(mirror_info)
    result['cloud_configured'] = bool(cloud.get('enabled') or (cloud.get('local_mirror_path') or '').strip())
    result['destinations'] = plan_backup_destinations(cfg)
    _notify_progress(progress_cb, 100, 'Backup complete')
    return result


def get_backup_job(job_id):
    with _BACKUP_JOBS_LOCK:
        return dict(_BACKUP_JOBS.get(job_id) or {})


def mark_backup_job_finalized(job_id):
    with _BACKUP_JOBS_LOCK:
        if job_id in _BACKUP_JOBS:
            _BACKUP_JOBS[job_id]['finalized'] = True


def start_backup_job(app, backup_config, *, manual=True):
    """Run backup in a background thread and track progress for polling."""
    job_id = uuid.uuid4().hex
    destinations = plan_backup_destinations(backup_config)

    def _set(**fields):
        with _BACKUP_JOBS_LOCK:
            if job_id in _BACKUP_JOBS:
                _BACKUP_JOBS[job_id].update(fields)

    with _BACKUP_JOBS_LOCK:
        _BACKUP_JOBS[job_id] = {
            'status': 'running',
            'progress': 0,
            'step': 'Preparing backup…',
            'current_file': '',
            'destinations': destinations,
            'result': None,
            'error': None,
        }

    def _progress(percent, message, current_file=''):
        _set(progress=percent, step=message, current_file=current_file)

    def _worker():
        with app.app_context():
            try:
                result = run_configured_backup(backup_config, manual=manual, progress_cb=_progress)
                _set(status='done', progress=100, step='Backup complete', result=result, current_file='')
            except Exception as exc:
                _set(status='error', step='Backup failed', error=str(exc))

    threading.Thread(target=_worker, daemon=True).start()
    return job_id
