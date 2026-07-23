#!/usr/bin/env python3
"""Project directory + architect messaging tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from permissions_catalog import permissions_from_role  # noqa: E402
from case_workflow import user_has_module_access  # noqa: E402
from access_control import user_can_receive_workflow_email, user_email_internal_only  # noqa: E402
from project_workflow_users import build_project_directory, CONSULTANT_WORKFLOW_ROLES  # noqa: E402


class _User:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.is_authenticated = True


class _Row:
    def __init__(self, user_id, role='Viewer', company_id=None):
        self.user_id = user_id
        self.role = role
        self.company_id = company_id


class _MembershipQuery:
    def __init__(self, rows):
        self._rows = rows
        self._project_id = None

    def filter_by(self, **kwargs):
        self._project_id = kwargs.get('project_id')
        return self

    def all(self):
        return [r for r in self._rows if r.project_id == self._project_id]


class _PM:
    def __init__(self, rows):
        self._rows = rows

    @property
    def query(self):
        return _MembershipQuery(self._rows)


class _MembershipRow(_Row):
    def __init__(self, project_id, user_id, role='Viewer', company_id=None):
        super().__init__(user_id, role, company_id)
        self.project_id = project_id


class _Project:
    id = 7

    def get_details(self):
        return {
            'team_contacts': [
                {
                    'role': 'owner',
                    'name': 'Owner Contact',
                    'email': 'owner@example.com',
                    'phone': '555-0100',
                    'firm': 'Owner LLC',
                }
            ]
        }


class _UserQuery:
    def __init__(self, users):
        self._users = {u.id: u for u in users}

    def get(self, user_id):
        return self._users.get(int(user_id))


def test_architect_internal_only_not_email() -> None:
    perms = permissions_from_role('Architect')
    user = _User(role='Architect', permissions_json=json.dumps(perms))
    assert perms.get('global', {}).get('email_internal_only') is True
    assert user_has_module_access(user, 'internal_messages', 'view')
    assert not user_has_module_access(user, 'email', 'view')
    assert user_email_internal_only(user)
    assert not user_can_receive_workflow_email(user)


def test_staff_user_can_receive_workflow_email() -> None:
    perms = permissions_from_role('Project Manager')
    user = _User(role='Project Manager', permissions_json=json.dumps(perms), email='pm@case.com')
    assert user_can_receive_workflow_email(user)


def test_build_project_directory_merges_membership_and_contacts() -> None:
    users = [
        _User(id=1, first_name='Brett', last_name='Architect', email='arch@firm.com', phone='555-1111', role='Architect', company='Design Co', status='Active'),
        _User(id=2, first_name='Pat', last_name='Manager', email='pm@case.com', phone='555-2222', role='Project Manager', company='Case Contracting', status='Active'),
    ]
    pm = _PM([
        _MembershipRow(7, 1, 'Architect'),
        _MembershipRow(7, 2, 'Project Manager'),
    ])

    class UserModel:
        query = _UserQuery(users)

    class ProjectObj:
        id = 7
        project_manager = 'Pat Manager'
        client = 'Owner LLC'
        client_company_id = None

        def get_details(self):
            return {
                'team_contacts': [
                    {
                        'role': 'owner',
                        'name': 'Owner Contact',
                        'email': 'owner@example.com',
                        'phone': '555-0100',
                        'firm': 'Owner LLC',
                    }
                ]
            }

    directory = build_project_directory(ProjectObj(), UserModel, Company=None, ProjectMembership=pm)
    assert len(directory) >= 3
    names = {entry['name'] for entry in directory}
    assert 'Brett Architect' in names
    assert 'Pat Manager' in names
    assert 'Owner Contact' in names
    assert 'Pat Manager' in names or any('Pat' in n for n in names)
    arch = next(entry for entry in directory if entry['name'] == 'Brett Architect')
    assert arch['email'] == 'arch@firm.com'
    assert arch['role_label'] == 'Architect'


def test_consultant_roles_include_engineers() -> None:
    assert 'Structural Engineer' in CONSULTANT_WORKFLOW_ROLES
    assert 'Owner' in CONSULTANT_WORKFLOW_ROLES


def main() -> int:
    test_architect_internal_only_not_email()
    test_staff_user_can_receive_workflow_email()
    test_build_project_directory_merges_membership_and_contacts()
    test_consultant_roles_include_engineers()
    print('test_project_directory_and_workflow: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
