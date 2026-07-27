"""Locate or download a Java runtime for MS Project MPP import."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR_JAVA = ROOT / 'vendor' / 'java'
ADOPTIUM_WIN_JRE_URL = (
    'https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse'
)
_ensure_lock = threading.Lock()
_download_attempted = False


def _read_server_env_java_home() -> Path | None:
    env_file = ROOT / 'instance' / 'server.env'
    if not env_file.is_file():
        return None
    try:
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            if key.strip() != 'CASEPM_JAVA_HOME':
                continue
            raw = value.strip().strip('"').strip("'")
            if raw:
                path = Path(raw)
                if path.is_dir():
                    return path
    except OSError:
        pass
    return None


def _java_home_valid(home: Path | None) -> bool:
    if home is None or not home.is_dir():
        return False
    java_exe = home / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
    return java_exe.is_file()


def resolve_java_home() -> Path | None:
    """Return the Java home directory Case PM should use, if any."""
    candidates: list[Path] = []

    for raw in (os.environ.get('CASEPM_JAVA_HOME'), os.environ.get('JAVA_HOME')):
        if raw:
            candidates.append(Path(raw))

    env_home = _read_server_env_java_home()
    if env_home is not None:
        candidates.insert(0, env_home)

    if VENDOR_JAVA.is_dir():
        candidates.append(VENDOR_JAVA)

    which_java = shutil.which('java')
    if which_java:
        candidates.append(Path(which_java).resolve().parent.parent)

    seen: set[str] = set()
    for home in candidates:
        try:
            resolved = home.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if _java_home_valid(resolved):
            return resolved
    return None


def resolve_jvm_path() -> str | None:
    """Return the JVM shared library path for JPype."""
    home = resolve_java_home()
    if home is not None:
        if os.name == 'nt':
            candidates = [
                home / 'bin' / 'server' / 'jvm.dll',
                home / 'jre' / 'bin' / 'server' / 'jvm.dll',
            ]
        elif sys.platform == 'darwin':
            candidates = [
                home / 'lib' / 'server' / 'libjvm.dylib',
                home / 'jre' / 'lib' / 'server' / 'libjvm.dylib',
            ]
        else:
            candidates = [
                home / 'lib' / 'server' / 'libjvm.so',
                home / 'jre' / 'lib' / 'amd64' / 'server' / 'libjvm.so',
            ]
        for path in candidates:
            if path.is_file():
                return str(path)

    try:
        import jpype

        if not jpype.isJVMStarted():
            return jpype.getDefaultJVMPath()
    except Exception:
        pass
    return None


def _find_java_home_in_dir(base: Path) -> Path | None:
    if _java_home_valid(base):
        return base
    if not base.is_dir():
        return None
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if _java_home_valid(child):
            return child
        nested = _find_java_home_in_dir(child)
        if nested is not None:
            return nested
    return None


def _write_server_env_java_home(home: Path) -> None:
    env_file = ROOT / 'instance' / 'server.env'
    env_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if env_file.is_file():
        for existing in env_file.read_text(encoding='utf-8').splitlines():
            if existing.strip().startswith('CASEPM_JAVA_HOME='):
                continue
            lines.append(existing)
    lines.append(f'CASEPM_JAVA_HOME={home}')
    env_file.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')


def _download_windows_jre(target_home: Path) -> Path:
    print('Java runtime: downloading Temurin 17 JRE for Windows (~45 MB)...')
    target_home.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / 'temurin-jre.zip'
        req = urllib.request.Request(
            ADOPTIUM_WIN_JRE_URL,
            headers={'User-Agent': 'CasePM-java-runtime/1.0'},
        )
        with urllib.request.urlopen(req, timeout=600) as resp, open(zip_path, 'wb') as out:
            shutil.copyfileobj(resp, out)
        extract_dir = Path(tmp) / 'extract'
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        found = _find_java_home_in_dir(extract_dir)
        if found is None:
            raise RuntimeError('Downloaded Java archive did not contain a JRE.')
        if target_home.exists():
            shutil.rmtree(target_home)
        shutil.copytree(found, target_home)
    return target_home


def java_runtime_status() -> dict:
    home = resolve_java_home()
    jvm_path = resolve_jvm_path()
    ok = bool(jvm_path)
    if ok:
        message = 'Java runtime ready.'
        setup_hint = ''
    elif os.name == 'nt':
        message = 'Java is not installed for MPP import.'
        setup_hint = (
            'Restart RUN-AS-SERVER.bat to download Java automatically, '
            'or run INSTALL-JAVA-FOR-MPP.bat on the server PC.'
        )
    else:
        message = 'Java is not installed or not on PATH.'
        setup_hint = 'Install Java 17+ and restart the server.'
    return {
        'ok': ok,
        'java_home': str(home) if home else None,
        'jvm_path': jvm_path,
        'message': message,
        'setup_hint': setup_hint,
    }


def ensure_java_runtime(*, auto_download: bool = True) -> dict:
    """Ensure a Java runtime exists; on Windows download a bundled JRE when needed."""
    global _download_attempted

    status = java_runtime_status()
    if status['ok']:
        if status['java_home']:
            os.environ['CASEPM_JAVA_HOME'] = status['java_home']
        return status
    if not auto_download or os.name != 'nt':
        return status

    with _ensure_lock:
        status = java_runtime_status()
        if status['ok']:
            return status
        if _download_attempted:
            return status
        _download_attempted = True

        if _java_home_valid(VENDOR_JAVA):
            os.environ['CASEPM_JAVA_HOME'] = str(VENDOR_JAVA.resolve())
            _write_server_env_java_home(VENDOR_JAVA.resolve())
            return java_runtime_status()

        try:
            home = _download_windows_jre(VENDOR_JAVA)
            os.environ['CASEPM_JAVA_HOME'] = str(home)
            _write_server_env_java_home(home)
            print(f'Java runtime: installed to {home}')
            return java_runtime_status()
        except Exception as exc:
            return {
                'ok': False,
                'java_home': None,
                'jvm_path': None,
                'message': f'Could not download Java automatically: {exc}',
                'setup_hint': (
                    'Run INSTALL-JAVA-FOR-MPP.bat on the server PC or install Temurin 17 '
                    'from https://adoptium.net/'
                ),
            }
