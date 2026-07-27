"""Convert MS Project .mpp files (via MPXJ) into Case PM gantt schedule payloads."""
from __future__ import annotations

import glob
import os
import tempfile
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

_jvm_lock = threading.Lock()
_jvm_started = False

# MS Project relation type value -> dhtmlx-gantt link type
_MS_LINK_TO_GANTT = {
    0: '2',  # FF
    1: '0',  # FS
    2: '3',  # SF
    3: '1',  # SS
}


class MppImportError(Exception):
    """Raised when an MPP/MS Project file cannot be parsed."""


def mpp_import_status() -> dict[str, Any]:
    """Return readiness details for native MPP import on this server."""
    import shutil

    status: dict[str, Any] = {
        'available': False,
        'packages_ok': False,
        'java_ok': False,
        'message': '',
        'setup_hint': '',
    }
    try:
        import jpype  # noqa: F401
        import mpxj  # noqa: F401
        status['packages_ok'] = True
    except ImportError:
        status['message'] = 'MPP import packages are not installed (mpxj, jpype1).'
        status['setup_hint'] = (
            'Close RUN-AS-SERVER.bat and start it again (it installs packages automatically), '
            'or run INSTALL-PACKAGES.bat on the server PC.'
        )
        return status

    if not shutil.which('java'):
        status['message'] = 'Java is not installed or not on PATH.'
        status['setup_hint'] = (
            'Install Java 17+ from https://adoptium.net/ (Temurin JRE), '
            'restart the Command Prompt, then restart RUN-AS-SERVER.bat.'
        )
        return status

    try:
        _ensure_jvm()
        status['java_ok'] = True
        status['available'] = True
        status['message'] = 'MPP import is ready.'
    except Exception as exc:
        status['message'] = f'MPP import could not start Java/MPXJ: {exc}'
        status['setup_hint'] = (
            'Install Java 17+ from https://adoptium.net/, verify "java -version" works, '
            'then restart RUN-AS-SERVER.bat.'
        )
    return status


_install_lock = threading.Lock()
_install_attempted = False


def ensure_mpp_import_dependencies(*, auto_install: bool = True) -> dict[str, Any]:
    """Install mpxj/jpype1 when missing, then return readiness status."""
    global _install_attempted
    status = mpp_import_status()
    if status['packages_ok'] or not auto_install:
        return status

    with _install_lock:
        status = mpp_import_status()
        if status['packages_ok']:
            return status
        if _install_attempted:
            return status
        _install_attempted = True

        import subprocess
        import sys

        print('MPP import: installing mpxj and jpype1 into', sys.executable)
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', 'mpxj>=14.0.0', 'jpype1>=1.5.0'],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or '').strip()
                print('MPP import: package install failed:', detail or f'exit {result.returncode}')
            else:
                print('MPP import: packages installed successfully.')
        except Exception as exc:
            print(f'MPP import: package install error: {exc}')

    return mpp_import_status()


def mpp_import_available() -> bool:
    """Return True when MPXJ + Java are available on this server."""
    return bool(mpp_import_status()['available'])


def _ensure_jvm() -> None:
    global _jvm_started
    with _jvm_lock:
        if _jvm_started:
            return
        import jpype
        import mpxj

        if jpype.isJVMStarted():
            _jvm_started = True
            return
        jars = glob.glob(str(Path(jpype.__file__).parent / 'org.jpype.jar'))
        jars += glob.glob(str(Path(mpxj.__file__).parent / 'lib' / '*.jar'))
        if not jars:
            raise MppImportError('MPXJ libraries are not installed.')
        jpype.startJVM(classpath=jars, convertStrings=True)
        _jvm_started = True


def _format_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, 'toLocalDate'):
        value = value.toLocalDate()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else None


def _duration_days(duration, defaults) -> int | None:
    if duration is None:
        return None
    from org.mpxj import TimeUnit

    try:
        days = duration.convertUnits(TimeUnit.DAYS, defaults)
        if days is None:
            return None
        return max(1, round(float(days.getDuration())))
    except Exception:
        return None


def _lag_days(lag, defaults) -> int:
    if lag is None:
        return 0
    from org.mpxj import TimeUnit

    try:
        days = lag.convertUnits(TimeUnit.DAYS, defaults)
        return round(float(days.getDuration()))
    except Exception:
        return 0


def _work_days_between(start_str: str, end_str: str) -> int:
    start = datetime.strptime(start_str, '%Y-%m-%d').date()
    end = datetime.strptime(end_str, '%Y-%m-%d').date()
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current = date.fromordinal(current.toordinal() + 1)
    return max(1, count)


def _project_to_gantt(project) -> dict[str, Any]:
    defaults = project.getProjectProperties()
    tasks = project.getTasks()
    if tasks is None or tasks.isEmpty():
        raise MppImportError('No tasks found in MS Project file.')

    data: list[dict[str, Any]] = []
    uid_map: dict[int, int] = {}
    links: list[dict[str, Any]] = []
    link_id = 1
    gantt_id = 1

    for idx in range(tasks.size()):
        task = tasks.get(idx)
        if task is None:
            continue
        uid = task.getUniqueID()
        if uid is None or int(uid) == 0:
            continue
        name = (task.getName() or '').strip()
        if not name:
            continue

        gid = gantt_id
        gantt_id += 1
        uid_map[int(uid)] = gid

        summary = bool(task.getSummary())
        milestone = bool(task.getMilestone())
        outline = int(task.getOutlineLevel() or 1)
        start = _format_date(task.getStart())
        finish = _format_date(task.getFinish())
        duration = _duration_days(task.getDuration(), defaults)
        pct = task.getPercentageComplete()
        try:
            progress = float(pct) / 100.0 if pct is not None else 0.0
        except (TypeError, ValueError):
            progress = 0.0

        row: dict[str, Any] = {
            'id': gid,
            'text': name,
            'parent': 0,
            'type': 'project' if summary else ('milestone' if milestone else 'task'),
            'progress': progress,
            'open': True,
            '_outline': outline,
        }
        if start:
            row['start_date'] = start
        if duration is not None:
            row['duration'] = 0 if milestone else max(1, duration)
        elif start and finish:
            row['duration'] = 0 if milestone else _work_days_between(start, finish)

        data.append(row)

        predecessors = task.getPredecessors()
        if predecessors:
            for rel in predecessors:
                pred_task = rel.getPredecessorTask()
                if pred_task is None:
                    continue
                pred_uid = pred_task.getUniqueID()
                if pred_uid is None:
                    continue
                source = uid_map.get(int(pred_uid))
                if not source:
                    continue
                rel_type = rel.getType()
                type_val = int(rel_type.getValue()) if rel_type is not None else 1
                links.append({
                    'id': link_id,
                    'source': source,
                    'target': gid,
                    'type': _MS_LINK_TO_GANTT.get(type_val, '0'),
                    'lag': _lag_days(rel.getLag(), defaults),
                })
                link_id += 1

    if not data:
        raise MppImportError('No tasks found in MS Project file.')

    stack: list[dict[str, int]] = [{'id': 0, 'level': 0}]
    for task in data:
        level = int(task.pop('_outline', 1))
        while len(stack) > 1 and stack[-1]['level'] >= level:
            stack.pop()
        task['parent'] = stack[-1]['id']
        if task.get('type') == 'project':
            stack.append({'id': task['id'], 'level': level})

    return {'data': data, 'links': links, 'source': 'MS Project MPP'}


def parse_mpp_bytes(content: bytes, *, filename: str = 'schedule.mpp') -> dict[str, Any]:
    """Read an MS Project file and return a gantt-compatible schedule payload."""
    if not content:
        raise MppImportError('Empty file.')
    _ensure_jvm()
    import jpype.imports  # noqa: F401
    from org.mpxj.reader import UniversalProjectReader

    ext = os.path.splitext(filename or '')[1].lower() or '.mpp'
    if ext not in {'.mpp', '.mpt', '.xml', '.mspdi'}:
        ext = '.mpp'

    reader = UniversalProjectReader()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        project = reader.read(tmp_path)
    except Exception as exc:
        raise MppImportError(f'Could not read MS Project file: {exc}') from exc
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return _project_to_gantt(project)
