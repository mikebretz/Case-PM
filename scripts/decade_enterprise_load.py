"""500-user enterprise pool + 100+ concurrent in-app load testing for decade stress."""
from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from scripts.simulate_concurrent_portfolio import ROLE_POOL

ENTERPRISE_PASSWORD = 'SimTest!12345'
DEFAULT_TOTAL_USERS = 500
RAMP_USERS_PER_YEAR = 50
INITIAL_ENTERPRISE_USERS = 50


def enterprise_users_at_month(all_users: list, global_month: int) -> list:
    """Simulate org growth: 50 users at month 0, +50 each year, cap 500."""
    if not all_users:
        return []
    years_elapsed = max(0, global_month // 12)
    target = min(len(all_users), INITIAL_ENTERPRISE_USERS + years_elapsed * RAMP_USERS_PER_YEAR)
    return all_users[:target]


def provision_enterprise_users(db, User, *, total: int = DEFAULT_TOTAL_USERS) -> list:
    """Create `total` persistent enterprise users (idempotent by email)."""
    users: list = []
    for i in range(total):
        email = f'enterprise.u{i:04d}@casepm.test'
        role = ROLE_POOL[i % len(ROLE_POOL)]
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(
                first_name='Enterprise',
                last_name=f'U{i:04d}',
                email=email,
                role=role,
                status='Active',
            )
            u.set_password(ENTERPRISE_PASSWORD)
            db.session.add(u)
        else:
            u.role = role
            u.status = 'Active'
        users.append(u)
    db.session.commit()
    return users


def assign_project_memberships(
    db,
    users: list,
    project_id: int,
    ProjectMembership,
    *,
    max_per_project: int = 35,
    project_index: int = 0,
) -> list:
    """Round-robin slice of enterprise users onto a project."""
    from project_access import save_memberships_for_user

    if not users or not ProjectMembership:
        return []
    n = min(max_per_project, len(users))
    start = (project_index * 17) % max(1, len(users))
    assigned = []
    for j in range(n):
        u = users[(start + j) % len(users)]
        assigned.append(u)
    for u in assigned:
        try:
            save_memberships_for_user(
                u.id, [project_id], db,
                ProjectMembership=ProjectMembership,
                default_role=u.role,
            )
        except Exception:
            continue
    db.session.commit()
    return assigned


def _login_worker_client(app, user):
    from scripts.simulate_security_harness import _login_client

    client = app.test_client()
    token = _login_client(client, user, app)
    return client, token


def _pick_requests(project_id: int) -> list[tuple[str, str]]:
    pid = int(project_id)
    return [
        ('GET', f'/api/projects/{pid}'),
        ('GET', f'/api/budget/state?project_id={pid}'),
        ('GET', f'/api/rfis?project_id={pid}'),
        ('GET', f'/api/rfis/dashboard?project_id={pid}'),
        ('GET', '/api/projects/financial-summary'),
        ('GET', f'/api/projects/{pid}/closeout-readiness'),
    ]


def _run_user_session(
    app,
    user,
    project_ids: list[int],
    *,
    ops: int,
) -> dict[str, Any]:
    """One simulated user session: mixed read APIs across assigned projects."""
    import random

    errors: list[str] = []
    latencies_ms: list[float] = []
    try:
        with app.app_context():
            client, _token = _login_worker_client(app, user)
            for _ in range(ops):
                pid = random.choice(project_ids)
                method, path = random.choice(_pick_requests(pid))
                t0 = time.perf_counter()
                if method == 'GET':
                    rv = client.get(path)
                else:
                    rv = client.open(path, method=method)
                elapsed = (time.perf_counter() - t0) * 1000
                latencies_ms.append(elapsed)
                if rv.status_code >= 500:
                    errors.append(f'{path} -> {rv.status_code}')
            try:
                from app import db
                db.session.remove()
            except Exception:
                pass
    except Exception as exc:
        errors.append(str(exc))
    return {'latencies_ms': latencies_ms, 'errors': errors}


def run_concurrent_load_test(
    app,
    users: list,
    project_ids: list[int],
    *,
    concurrency: int = 128,
    ops_per_user: int = 6,
    parallel_wave: int = 24,
    p95_warn_ms: float = 8000.0,
    p95_fail_ms: float = 20000.0,
    max_error_rate: float = 0.08,
    label: str = 'peak',
) -> dict[str, Any]:
    """
    Simulate `concurrency` user sessions (100+ for decade stress).
    Runs in waves of `parallel_wave` to limit SQLite lock contention in dev/test DBs.
    """
    if not users or not project_ids:
        return {'skipped': True, 'reason': 'no users or projects', 'label': label}

    active_users = users[: min(len(users), concurrency)]
    try:
        uri = str(app.config.get('SQLALCHEMY_DATABASE_URI', '')).lower()
    except Exception:
        uri = ''
    if 'sqlite' in uri:
        wave = 1
    else:
        wave = max(1, min(parallel_wave, len(active_users)))
    all_latencies: list[float] = []
    all_errors: list[str] = []
    t0 = time.perf_counter()

    for offset in range(0, len(active_users), wave):
        batch = active_users[offset: offset + wave]
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = [
                pool.submit(_run_user_session, app, u, project_ids, ops=ops_per_user)
                for u in batch
            ]
            for fut in as_completed(futures, timeout=180):
                try:
                    out = fut.result(timeout=1)
                    all_latencies.extend(out.get('latencies_ms') or [])
                    all_errors.extend(out.get('errors') or [])
                except Exception as exc:
                    all_errors.append(str(exc))

    wall_s = time.perf_counter() - t0
    total_ops = len(all_latencies)
    error_rate = len(all_errors) / max(1, total_ops + len(all_errors))

    stats: dict[str, Any] = {
        'label': label,
        'concurrency': len(active_users),
        'parallel_wave': wave,
        'sqlite_sequential_sessions': wave == 1 and 'sqlite' in uri,
        'ops_per_user': ops_per_user,
        'total_requests': total_ops,
        'wall_seconds': round(wall_s, 2),
        'requests_per_second': round(total_ops / wall_s, 2) if wall_s > 0 else 0,
        'errors': len(all_errors),
        'error_rate': round(error_rate, 4),
        'error_samples': all_errors[:15],
    }

    if all_latencies:
        all_latencies.sort()
        stats['latency_ms'] = {
            'min': round(all_latencies[0], 2),
            'p50': round(statistics.median(all_latencies), 2),
            'p95': round(all_latencies[int(len(all_latencies) * 0.95) - 1], 2),
            'max': round(all_latencies[-1], 2),
            'mean': round(statistics.mean(all_latencies), 2),
        }
        p95 = stats['latency_ms']['p95']
        stats['degraded'] = p95 > p95_warn_ms or error_rate > max_error_rate
        stats['failed'] = p95 > p95_fail_ms or error_rate > 0.2
    else:
        stats['failed'] = True
        stats['degraded'] = True

    return stats


def run_portfolio_with_periodic_load(
    models: dict,
    scenarios: list,
    app,
    enterprise_users: list,
    *,
    load_at_months: tuple[int, ...] = (24, 60, 96, 119),
    load_concurrency: int = 128,
    verbose: bool = False,
    on_month: Callable[[int, list], None] | None = None,
) -> tuple[list, list[dict]]:
    """Interleaved portfolio ticks + enterprise load bursts at calendar milestones."""
    import random

    import scripts.simulate_concurrent_portfolio as portfolio_mod
    from scripts.simulate_concurrent_portfolio import ProjectRuntime, _run_month_tick
    from scripts.simulate_financial_project import SimResult

    horizons = max(s.end_month for s in scenarios) + 1
    runtimes = [
        ProjectRuntime(scenario=s, result=SimResult(name=s.name, project_id=0))
        for s in scenarios
    ]
    load_reports: list[dict] = []

    for global_month in range(horizons):
        active = [rt for rt in runtimes if rt.scenario.start_month <= global_month <= rt.scenario.end_month]
        if not active:
            continue
        random.shuffle(active)
        if verbose:
            print(f'\n--- Global month {global_month} ({len(active)} active) ---')
        elif global_month % 12 == 0 or global_month == horizons - 1:
            print(f'  decade month {global_month}/{horizons - 1}: {len(active)} active jobs', flush=True)

        for rt in active:
            portfolio_mod._decade_global_month = global_month
            _run_month_tick(rt, models, global_month)
            models['db'].session.commit()

        if on_month:
            on_month(global_month, runtimes)

        if global_month in load_at_months:
            active_users = enterprise_users_at_month(enterprise_users, global_month)
            pids = [rt.result.project_id for rt in runtimes if rt.result.project_id]
            conc = min(load_concurrency, max(100, len(active_users) // 2))
            print(f'\n  ⟳ Load test @ month {global_month}: {conc} concurrent users, '
                  f'{len(active_users)} enterprise users provisioned…', flush=True)
            report = run_concurrent_load_test(
                app,
                active_users,
                pids,
                concurrency=conc,
                ops_per_user=8,
                parallel_wave=min(32, conc),
                label=f'month-{global_month}',
            )
            load_reports.append(report)
            lat = report.get('latency_ms') or {}
            print(f'     rps={report.get("requests_per_second")} p95={lat.get("p95")}ms '
                  f'errors={report.get("errors")} degraded={report.get("degraded")}', flush=True)

    return runtimes, load_reports
