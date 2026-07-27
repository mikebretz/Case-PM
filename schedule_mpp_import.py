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
    from java_runtime import java_runtime_status

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

    java_status = java_runtime_status()
    if not java_status.get('jvm_path'):
        status['message'] = java_status.get('message') or 'Java is not available for MPP import.'
        status['setup_hint'] = java_status.get('setup_hint') or (
            'Run INSTALL-JAVA-FOR-MPP.bat on the server PC, then restart RUN-AS-SERVER.bat.'
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
            'Run INSTALL-JAVA-FOR-MPP.bat on the server PC, then restart RUN-AS-SERVER.bat.'
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

    from java_runtime import ensure_java_runtime
    ensure_java_runtime(auto_download=auto_install)

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
        from java_runtime import resolve_jvm_path

        if jpype.isJVMStarted():
            _jvm_started = True
            return
        jars = glob.glob(str(Path(jpype.__file__).parent / 'org.jpype.jar'))
        jars += glob.glob(str(Path(mpxj.__file__).parent / 'lib' / '*.jar'))
        if not jars:
            raise MppImportError('MPXJ libraries are not installed.')
        jvm_path = resolve_jvm_path()
        if not jvm_path:
            raise MppImportError('Java runtime not found for MPP import.')
        jpype.startJVM(jvm_path, classpath=jars, convertStrings=True)
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


def _rollup_summary_dates(data: list[dict[str, Any]]) -> None:
    """Set summary WBS start/finish from child activities (MSP summary rows can be stale)."""
    by_id = {int(row['id']): row for row in data}
    children: dict[int, list[int]] = {}
    for row in data:
        parent = int(row.get('parent') or 0)
        if parent:
            children.setdefault(parent, []).append(int(row['id']))

    def walk(parent_id: int) -> None:
        for child_id in children.get(parent_id, []):
            walk(child_id)
        row = by_id.get(parent_id)
        if not row or row.get('type') != 'project':
            return
        kid_rows = [by_id[cid] for cid in children.get(parent_id, []) if cid in by_id]
        if not kid_rows:
            return
        starts = [k['start_date'] for k in kid_rows if k.get('start_date')]
        ends = [k['end_date'] for k in kid_rows if k.get('end_date')]
        if starts:
            row['start_date'] = min(starts)
        if ends:
            row['end_date'] = max(ends)
        if row.get('start_date') and row.get('end_date') and row.get('type') == 'project':
            try:
                row['duration'] = _calendar_days_between(row['start_date'], row['end_date'])
            except ValueError:
                pass

    roots = [int(row['id']) for row in data if int(row.get('parent') or 0) == 0]
    for root_id in roots:
        walk(root_id)


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


def _calendar_days_between(start_str: str, end_str: str) -> int:
    """Calendar-day span for dhtmlx-gantt (work_time=false): end = start + duration."""
    start = datetime.strptime(start_str, '%Y-%m-%d').date()
    end = datetime.strptime(end_str, '%Y-%m-%d').date()
    if end < start:
        return 1
    return max(1, (end - start).days)


def _task_scheduled_dates(task) -> tuple[str | None, str | None]:
    """Read MSP scheduled start/finish (not actual/early/late CPM dates)."""
    start = None
    finish = None
    for start_attr in ('getScheduledStart', 'getStart'):
        if hasattr(task, start_attr):
            try:
                start = _format_date(getattr(task, start_attr)())
            except Exception:
                start = None
            if start:
                break
    for finish_attr in ('getScheduledFinish', 'getFinish'):
        if hasattr(task, finish_attr):
            try:
                finish = _format_date(getattr(task, finish_attr)())
            except Exception:
                finish = None
            if finish:
                break
    return start, finish


def _finalize_native_payload(data: list[dict[str, Any]], links: list[dict[str, Any]], import_meta: dict[str, Any]) -> dict[str, Any]:
    """Normalize imported tasks into Case PM native schedule shape."""
    for row in data:
        row.pop('_outline', None)
        if row.get('start_date'):
            row['start_date'] = str(row['start_date'])[:10]
        if row.get('end_date'):
            row['end_date'] = str(row['end_date'])[:10]
        if row.get('type') == 'milestone':
            row['duration'] = 0
            if row.get('start_date'):
                row['end_date'] = row['start_date']
        elif row.get('start_date') and row.get('end_date') and row.get('type') != 'project':
            try:
                row['duration'] = _calendar_days_between(row['start_date'], row['end_date'])
            except ValueError:
                pass
    _rollup_summary_dates(data)
    return {
        'data': data,
        'links': links,
        'source': 'Case PM schedule',
        'import_meta': import_meta,
        'settings': {'native_schedule': True},
    }


def _project_to_gantt(project) -> dict[str, Any]:
    defaults = project.getProjectProperties()
    tasks = project.getTasks()
    if tasks is None or tasks.isEmpty():
        raise MppImportError('No tasks found in MS Project file.')

    data: list[dict[str, Any]] = []
    uid_map: dict[int, int] = {}
    gid_is_summary: dict[int, bool] = {}
    pending_links: list[tuple[int, int, int, int]] = []
    links: list[dict[str, Any]] = []
    link_id = 1
    gantt_id = 1
    skipped_inactive = 0
    skipped_null = 0
    date_values: list[str] = []

    for idx in range(tasks.size()):
        task = tasks.get(idx)
        if task is None:
            continue
        uid = task.getUniqueID()
        if uid is None or int(uid) == 0:
            continue

        try:
            if task.getNull():
                skipped_null += 1
                continue
        except Exception:
            pass

        try:
            active = task.getActive()
            if active is not None and not bool(active):
                skipped_inactive += 1
                continue
        except Exception:
            pass

        name = (task.getName() or '').strip()
        if not name:
            name = f'Activity {uid}'

        gid = gantt_id
        gantt_id += 1
        uid_map[int(uid)] = gid

        summary = bool(task.getSummary())
        milestone = bool(task.getMilestone())
        gid_is_summary[gid] = summary
        outline = int(task.getOutlineLevel() or 1)
        start, finish = _task_scheduled_dates(task)
        duration = _duration_days(task.getDuration(), defaults)
        pct = task.getPercentageComplete()
        try:
            progress = float(pct) / 100.0 if pct is not None else 0.0
        except (TypeError, ValueError):
            progress = 0.0

        wbs_code = None
        try:
            wbs_raw = task.getWBS()
            if wbs_raw is not None:
                wbs_code = str(wbs_raw).strip() or None
        except Exception:
            wbs_code = None

        row: dict[str, Any] = {
            'id': gid,
            'text': name,
            'parent': 0,
            'type': 'project' if summary else ('milestone' if milestone else 'task'),
            'progress': progress,
            'open': True,
            '_outline': outline,
            'activity_id': str(uid),
        }
        if wbs_code:
            row['wbs'] = wbs_code
        if start:
            row['start_date'] = start
            date_values.append(start)
        if finish:
            row['end_date'] = finish
            date_values.append(finish)
        if milestone:
            row['duration'] = 0
            if start:
                row['end_date'] = start
        elif start and finish:
            row['duration'] = _calendar_days_between(start, finish)
        elif duration is not None:
            row['duration'] = max(1, duration)

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
                rel_type = rel.getType()
                type_val = int(rel_type.getValue()) if rel_type is not None else 1
                pending_links.append((
                    gid,
                    int(pred_uid),
                    type_val,
                    _lag_days(rel.getLag(), defaults),
                ))

    skipped_summary_links = 0
    for target_gid, pred_uid, type_val, lag in pending_links:
        source = uid_map.get(pred_uid)
        if not source:
            continue
        if gid_is_summary.get(source) or gid_is_summary.get(target_gid):
            skipped_summary_links += 1
            continue
        links.append({
            'id': link_id,
            'source': source,
            'target': target_gid,
            'type': _MS_LINK_TO_GANTT.get(type_val, '0'),
            'lag': lag,
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

    _rollup_summary_dates(data)

    import_meta: dict[str, Any] = {
        'task_count': len(data),
        'link_count': len(links),
        'skipped_inactive': skipped_inactive,
        'skipped_null': skipped_null,
        'skipped_summary_links': skipped_summary_links,
        'native_format': True,
        'imported_from': 'MS Project MPP',
    }
    if date_values:
        import_meta['date_start'] = min(date_values)
        import_meta['date_end'] = max(date_values)
        try:
            span_days = (
                datetime.strptime(import_meta['date_end'], '%Y-%m-%d')
                - datetime.strptime(import_meta['date_start'], '%Y-%m-%d')
            ).days
            import_meta['span_days'] = span_days
        except ValueError:
            pass

    return _finalize_native_payload(data, links, import_meta)


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
