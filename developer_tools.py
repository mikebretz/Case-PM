"""Developer-only overrides — unlock locked records, edit immutable fields."""
from __future__ import annotations

import os


def developer_emails():
    raw = os.environ.get('CASEPM_DEVELOPER_EMAILS', 'michael.bretz@casepm.com,admin@casepm.local')
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def is_developer(user):
    if not user:
        return False
    if getattr(user, 'role', None) == 'Developer':
        return True
    email = (getattr(user, 'email', None) or '').lower()
    return email in developer_emails()


def is_admin_or_developer(user):
    if not user:
        return False
    return getattr(user, 'role', None) == 'Admin' or is_developer(user)


def unlock_change_order(co):
    if hasattr(co, 'executed_locked'):
        co.executed_locked = False
    return co


def override_project_number(project, new_number, normalize_fn):
    project.number = normalize_fn(new_number)
    return project
