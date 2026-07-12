"""Developer program update tools — code snapshots, install, and rollback without touching user data."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

from backup_service import format_display_time, utc_now_iso
from version import CASEPM_VERSION

APP_ROOT = os.path.abspath(os.path.dirname(__file__) or '.')
CONFIG_PATH = os.path.join('instance', 'program_updates.json')
DEFAULT_SNAPSHOT_DIR = os.path.join('instance', 'code_snapshots')

SKIP_PREFIXES = (
    'instance' + os.sep,
    'uploads' + os.sep,
    'venv' + os.sep,
    '.venv' + os.sep,
    '.git' + os.sep,
    'node_modules' + os.sep,
    '__pycache__' + os.sep,
    '.pytest_cache' + os.sep,
)
SKIP_EXACT = {
    'instance', 'uploads', 'venv', '.venv', '.git', 'node_modules',
    '__pycache__', '.pytest_cache', '.env',
}
SNAPSHOT_NAME_RE = re.compile(r'^casepm_code_[0-9]{8}_[0-9]{6}_[a-f0-9]{6}\.zip$', re.I)


def _normalize_rel(path):
    return (path or '').replace('\\', '/').lstrip('./')


def should_skip_path(rel_path):
    """True when a path must never be included in code snapshots or overwrites."""
    rel = _normalize_rel(rel_path)
    if not rel:
        return True
    base = rel.split('/')[0]
    if base in SKIP_EXACT:
        return True
    for prefix in SKIP_PREFIXES:
        if rel.startswith(prefix.replace(os.sep, '/')):
            return True
    if rel.endswith('.pyc') or '/__pycache__/' in f'/{rel}/':
        return True
    return False


def _iter_app_files():
    """Yield relative paths for application code files under APP_ROOT."""
    for root, dirs, files in os.walk(APP_ROOT):
        rel_root = os.path.relpath(root, APP_ROOT)
        if rel_root == '.':
            rel_root = ''
        dirs[:] = [
            d for d in dirs
            if not should_skip_path(os.path.join(rel_root, d).replace('\\', '/'))
        ]
        for fn in files:
            rel = os.path.join(rel_root, fn).replace('\\', '/') if rel_root else fn
            if should_skip_path(rel):
                continue
            yield rel


def _load_config():
    if not os.path.isfile(CONFIG_PATH):
        return {'snapshot_folder': DEFAULT_SNAPSHOT_DIR, 'history': []}
    try:
        with open(CONFIG_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {'snapshot_folder': DEFAULT_SNAPSHOT_DIR, 'history': []}
        data.setdefault('snapshot_folder', DEFAULT_SNAPSHOT_DIR)
        data.setdefault('history', [])
        return data
    except (OSError, json.JSONDecodeError):
        return {'snapshot_folder': DEFAULT_SNAPSHOT_DIR, 'history': []}


def _save_config(data):
    os.makedirs('instance', exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)


def snapshot_dir(config=None):
    cfg = config or _load_config()
    folder = (cfg.get('snapshot_folder') or DEFAULT_SNAPSHOT_DIR).strip()
    return os.path.abspath(folder)


def save_snapshot_folder(folder):
    folder = (folder or '').strip() or DEFAULT_SNAPSHOT_DIR
    cfg = _load_config()
    cfg['snapshot_folder'] = folder
    _save_config(cfg)
    return folder


def _safe_snapshot_filename(filename):
    name = os.path.basename((filename or '').strip().replace('\\', '/'))
    if not name or not SNAPSHOT_NAME_RE.match(name):
        raise ValueError('Invalid snapshot filename')
    return name


def _resolve_snapshot_path(filename, dir_path=None):
    name = _safe_snapshot_filename(filename)
    root = os.path.abspath(dir_path or snapshot_dir())
    path = os.path.abspath(os.path.join(root, name))
    prefix = root if root.endswith(os.sep) else root + os.sep
    if path != root and not path.startswith(prefix):
        raise ValueError('Invalid snapshot path')
    if not os.path.isfile(path):
        raise ValueError(f'Snapshot not found: {name}')
    return path


def _git_run(args, timeout=90):
    try:
        proc = subprocess.run(
            ['git'] + list(args),
            cwd=APP_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or '').strip(), (proc.stderr or '').strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, '', str(exc)


def get_git_info():
    code, branch, _ = _git_run(['branch', '--show-current'])
    branch = branch if code == 0 else ''
    code, commit, _ = _git_run(['rev-parse', '--short', 'HEAD'])
    commit = commit if code == 0 else ''
    code, subject, _ = _git_run(['log', '-1', '--pretty=%s'])
    subject = subject if code == 0 else ''
    code, date, _ = _git_run(['log', '-1', '--pretty=%ci'])
    date = date if code == 0 else ''
    has_git = bool(commit)
    behind = ahead = 0
    if has_git:
        _git_run(['fetch', 'origin', '--quiet'], timeout=120)
        code, out, _ = _git_run(['rev-list', '--left-right', '--count', 'HEAD...origin/main'])
        if code == 0 and out:
            parts = out.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
    return {
        'available': has_git,
        'branch': branch,
        'commit': commit,
        'subject': subject,
        'commit_date': date,
        'ahead': ahead,
        'behind': behind,
        'remote_branch': 'origin/main',
    }


def get_status():
    cfg = _load_config()
    snaps = list_snapshots(cfg)
    git = get_git_info()
    return {
        'version': CASEPM_VERSION,
        'app_root': APP_ROOT,
        'snapshot_folder': snapshot_dir(cfg),
        'snapshot_count': len(snaps),
        'history_count': len(cfg.get('history') or []),
        'git': git,
        'user_data_protected': ['instance/', 'uploads/'],
    }


def list_snapshots(config=None):
    dir_path = snapshot_dir(config)
    if not os.path.isdir(dir_path):
        return []
    rows = []
    for name in sorted(os.listdir(dir_path), reverse=True):
        if not name.lower().endswith('.zip'):
            continue
        path = os.path.join(dir_path, name)
        try:
            stat = os.stat(path)
            manifest = _read_snapshot_manifest(path)
            created_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            created_iso = created_dt.isoformat().replace('+00:00', 'Z')
            rows.append({
                'filename': name,
                'path': path,
                'size_bytes': stat.st_size,
                'created_at': created_iso,
                'created_at_display': format_display_time(created_dt),
                'label': manifest.get('label') or '',
                'note': manifest.get('note') or '',
                'version': manifest.get('version') or '',
                'git_commit': manifest.get('git_commit') or '',
                'file_count': manifest.get('file_count') or 0,
            })
        except OSError:
            continue
    return rows


def _read_snapshot_manifest(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'snapshot_manifest.json' not in zf.namelist():
                return {}
            return json.loads(zf.read('snapshot_manifest.json').decode('utf-8'))
    except (OSError, json.JSONDecodeError, zipfile.BadZipFile):
        return {}


def get_history(limit=50):
    cfg = _load_config()
    history = list(cfg.get('history') or [])
    history.sort(key=lambda h: h.get('created_at') or '', reverse=True)
    return history[:limit]


def _append_history(entry):
    cfg = _load_config()
    history = cfg.get('history') or []
    history.insert(0, entry)
    cfg['history'] = history[:200]
    _save_config(cfg)


def create_snapshot(label='', note='', actor=''):
    """Save current application code to a zip in the configured snapshot folder."""
    dir_path = snapshot_dir()
    os.makedirs(dir_path, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
    filename = f'casepm_code_{stamp}.zip'
    dest = os.path.join(dir_path, filename)
    git = get_git_info()
    files = list(_iter_app_files())
    manifest = {
        'type': 'code_snapshot',
        'created_at': utc_now_iso(),
        'created_at_display': format_display_time(utc_now_iso()),
        'label': (label or '').strip() or 'Manual snapshot',
        'note': (note or '').strip(),
        'version': CASEPM_VERSION,
        'git_commit': git.get('commit') or '',
        'git_branch': git.get('branch') or '',
        'file_count': len(files),
        'actor': actor,
        'protected_paths': ['instance/', 'uploads/'],
    }
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            full = os.path.join(APP_ROOT, rel.replace('/', os.sep))
            if os.path.isfile(full):
                zf.write(full, rel.replace('\\', '/'))
        zf.writestr('snapshot_manifest.json', json.dumps(manifest, indent=2))

    entry = {
        'id': uuid.uuid4().hex[:12],
        'type': 'snapshot',
        'label': manifest['label'],
        'note': manifest['note'],
        'version_before': CASEPM_VERSION,
        'version_after': CASEPM_VERSION,
        'git_commit_before': git.get('commit') or '',
        'git_commit_after': git.get('commit') or '',
        'snapshot_file': filename,
        'created_at': manifest['created_at'],
        'created_at_display': manifest['created_at_display'],
        'actor': actor,
        'status': 'success',
    }
    _append_history(entry)
    return {
        'ok': True,
        'filename': filename,
        'path': dest,
        'size_bytes': os.path.getsize(dest),
        'file_count': len(files),
        'manifest': manifest,
        'history_entry': entry,
    }


def _apply_code_tree(source_root):
    """Copy application files from source_root into APP_ROOT, skipping user data paths."""
    applied = []
    for root, dirs, files in os.walk(source_root):
        rel_root = os.path.relpath(root, source_root)
        if rel_root == '.':
            rel_root = ''
        dirs[:] = [
            d for d in dirs
            if not should_skip_path(os.path.join(rel_root, d).replace('\\', '/') if rel_root else d)
        ]
        for fn in files:
            if fn == 'snapshot_manifest.json':
                continue
            rel = os.path.join(rel_root, fn).replace('\\', '/') if rel_root else fn
            if should_skip_path(rel):
                continue
            src = os.path.join(root, fn)
            dest = os.path.join(APP_ROOT, rel.replace('/', os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            applied.append(rel)
    return applied


def restore_snapshot(filename, actor='', auto_snapshot_note=''):
    """Roll back application code from a saved snapshot. User data is never touched."""
    zip_path = _resolve_snapshot_path(filename)
    git_before = get_git_info()
    safety = None
    if auto_snapshot_note is not False:
        safety = create_snapshot(
            label='Auto backup before rollback',
            note=auto_snapshot_note or f'Automatic safety copy before restoring {filename}',
            actor=actor,
        )

    with tempfile.TemporaryDirectory(prefix='casepm_code_restore_') as tmp_dir:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in zf.namelist():
                if should_skip_path(member):
                    continue
                zf.extract(member, tmp_dir)
        applied = _apply_code_tree(tmp_dir)

    manifest = _read_snapshot_manifest(zip_path)
    git_after = get_git_info()
    entry = {
        'id': uuid.uuid4().hex[:12],
        'type': 'rollback',
        'label': f'Restored {filename}',
        'note': manifest.get('label') or '',
        'version_before': CASEPM_VERSION,
        'version_after': CASEPM_VERSION,
        'git_commit_before': git_before.get('commit') or '',
        'git_commit_after': git_after.get('commit') or '',
        'snapshot_file': filename,
        'safety_snapshot': (safety or {}).get('filename'),
        'files_applied': len(applied),
        'created_at': utc_now_iso(),
        'created_at_display': format_display_time(utc_now_iso()),
        'actor': actor,
        'status': 'success',
    }
    _append_history(entry)
    return {
        'ok': True,
        'restored_from': _safe_snapshot_filename(filename),
        'files_applied': len(applied),
        'safety_snapshot': (safety or {}).get('filename'),
        'reload_required': True,
        'restart_required': True,
        'history_entry': entry,
    }


def apply_update_zip(file_storage, label='', note='', actor=''):
    """Install an application update zip after creating a safety snapshot."""
    if not file_storage or not getattr(file_storage, 'filename', None):
        raise ValueError('No update file uploaded')
    original = os.path.basename(file_storage.filename.replace('\\', '/'))
    if not original.lower().endswith('.zip'):
        raise ValueError('Update must be a .zip file')

    git_before = get_git_info()
    safety = create_snapshot(
        label='Auto backup before update',
        note=f'Automatic safety copy before installing {original}',
        actor=actor,
    )

    with tempfile.TemporaryDirectory(prefix='casepm_code_update_') as tmp_dir:
        upload_path = os.path.join(tmp_dir, 'upload.zip')
        file_storage.save(upload_path)
        with zipfile.ZipFile(upload_path, 'r') as zf:
            names = zf.namelist()
            if not names:
                raise ValueError('Update zip is empty')
            for member in names:
                if should_skip_path(member):
                    continue
                zf.extract(member, tmp_dir)
        entries = [e for e in os.listdir(tmp_dir) if e != 'upload.zip']
        source_root = tmp_dir
        if len(entries) == 1:
            only = os.path.join(tmp_dir, entries[0])
            if os.path.isdir(only):
                source_root = only
        applied = _apply_code_tree(source_root)

    git_after = get_git_info()
    entry = {
        'id': uuid.uuid4().hex[:12],
        'type': 'install',
        'label': (label or '').strip() or f'Installed {original}',
        'note': (note or '').strip(),
        'version_before': CASEPM_VERSION,
        'version_after': CASEPM_VERSION,
        'git_commit_before': git_before.get('commit') or '',
        'git_commit_after': git_after.get('commit') or '',
        'snapshot_file': safety.get('filename'),
        'upload_name': original,
        'files_applied': len(applied),
        'created_at': utc_now_iso(),
        'created_at_display': format_display_time(utc_now_iso()),
        'actor': actor,
        'status': 'success',
    }
    _append_history(entry)
    return {
        'ok': True,
        'upload_name': original,
        'files_applied': len(applied),
        'safety_snapshot': safety.get('filename'),
        'reload_required': True,
        'restart_required': True,
        'pip_may_be_required': os.path.isfile(os.path.join(APP_ROOT, 'requirements.txt')),
        'history_entry': entry,
    }


def git_pull_update(actor=''):
    """Pull latest code from origin/main after a safety snapshot."""
    git_before = get_git_info()
    if not git_before.get('available'):
        raise ValueError('Git is not available in this installation folder')

    safety = create_snapshot(
        label='Auto backup before git pull',
        note='Automatic safety copy before pulling updates from GitHub',
        actor=actor,
    )

    code, out, err = _git_run(['pull', 'origin', 'main'], timeout=180)
    if code != 0:
        entry = {
            'id': uuid.uuid4().hex[:12],
            'type': 'git_pull',
            'label': 'Git pull failed',
            'note': err or out or 'git pull failed',
            'version_before': CASEPM_VERSION,
            'version_after': CASEPM_VERSION,
            'git_commit_before': git_before.get('commit') or '',
            'git_commit_after': git_before.get('commit') or '',
            'snapshot_file': safety.get('filename'),
            'created_at': utc_now_iso(),
            'created_at_display': format_display_time(utc_now_iso()),
            'actor': actor,
            'status': 'failed',
        }
        _append_history(entry)
        raise ValueError(err or out or 'git pull failed')

    git_after = get_git_info()
    entry = {
        'id': uuid.uuid4().hex[:12],
        'type': 'git_pull',
        'label': 'Pulled from origin/main',
        'note': out.splitlines()[-1] if out else '',
        'version_before': CASEPM_VERSION,
        'version_after': CASEPM_VERSION,
        'git_commit_before': git_before.get('commit') or '',
        'git_commit_after': git_after.get('commit') or '',
        'snapshot_file': safety.get('filename'),
        'created_at': utc_now_iso(),
        'created_at_display': format_display_time(utc_now_iso()),
        'actor': actor,
        'status': 'success',
    }
    _append_history(entry)
    return {
        'ok': True,
        'output': out,
        'safety_snapshot': safety.get('filename'),
        'git_before': git_before,
        'git_after': git_after,
        'reload_required': True,
        'restart_required': True,
        'history_entry': entry,
    }
