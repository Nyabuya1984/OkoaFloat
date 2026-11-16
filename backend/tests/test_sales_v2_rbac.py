from types import SimpleNamespace

from flask import Flask

import app.utils.rbac as rbac


def _protected(scope):
    @rbac.require_scope(scope)
    def view():
        return "ok"

    return view


def test_sales_role_can_use_mine_scope(monkeypatch):
    actor = SimpleNamespace(role="employee", is_superuser=False)
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: True)
    app = Flask(__name__)
    with app.test_request_context("/?scope=mine"):
        assert _protected("mine")() == "ok"


def test_sales_role_can_use_team_scope(monkeypatch):
    actor = SimpleNamespace(role="employee", is_superuser=False)
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: True)
    app = Flask(__name__)
    with app.test_request_context("/?scope=team"):
        response, status = _protected("team")()
        assert status == 403


def test_sales_role_can_use_org_scope(monkeypatch):
    actor = SimpleNamespace(role="employee", is_superuser=False)
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: True)
    app = Flask(__name__)
    with app.test_request_context("/?scope=org"):
        response, status = _protected("org")()
        assert status == 403


def test_superadmin_with_report_permission_can_use_org_scope(monkeypatch):
    actor = SimpleNamespace(role="super_admin", is_superuser=False)
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: True)
    app = Flask(__name__)
    with app.test_request_context("/?scope=org"):
        assert _protected("org")() == "ok"


def test_superadmin_can_use_org_scope_without_sales_role_permission(monkeypatch):
    actor = SimpleNamespace(role="super_admin", is_superuser=False)
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: False)
    app = Flask(__name__)
    with app.test_request_context("/?scope=org"):
        assert _protected("org")() == "ok"


def test_conflicting_scope_is_rejected(monkeypatch):
    actor = SimpleNamespace(role="employee", is_superuser=False)
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: True)
    app = Flask(__name__)
    with app.test_request_context("/?scope=org"):
        response, status = _protected("team")()
        assert status == 403
        assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_multiple_allowed_scopes_are_accepted(monkeypatch):
    import app.utils.organization as organization

    actor = SimpleNamespace(id=19, role="team_leader", is_superuser=False)
    assignment = SimpleNamespace(
        organizational_role="team_leader",
        department_name="Sales & Marketing",
    )
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: True)
    monkeypatch.setattr(organization, "get_active_assignment", lambda _user_id: assignment)
    app = Flask(__name__)

    @rbac.require_scope({"mine", "team"})
    def view():
        return "ok"

    with app.test_request_context("/?scope=team"):
        assert view() == "ok"

    with app.test_request_context("/?scope=mine"):
        assert view() == "ok"


def test_sales_management_assignment_authorizes_only_hierarchy_scopes(monkeypatch):
    import app.utils.organization as organization

    actor = SimpleNamespace(id=17, role="manager", is_superuser=False)
    assignment = SimpleNamespace(
        organizational_role="team_leader",
        department_name="Sales & Marketing",
    )
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: False)
    monkeypatch.setattr(
        organization,
        "get_active_assignment",
        lambda user_id: assignment if user_id == actor.id else None,
    )
    app = Flask(__name__)
    with app.test_request_context("/?scope=team"):
        assert _protected("team")() == "ok"
    with app.test_request_context("/?scope=org"):
        response, status = _protected("org")()
        assert status == 403


def test_non_sales_manager_cannot_use_team_scope_without_report_permission(monkeypatch):
    import app.utils.organization as organization

    actor = SimpleNamespace(id=18, role="manager", is_superuser=False)
    assignment = SimpleNamespace(
        organizational_role="department_manager",
        department_name="Finance",
    )
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: actor)
    monkeypatch.setattr(rbac, "can", lambda user, permission: False)
    monkeypatch.setattr(organization, "get_active_assignment", lambda _user_id: assignment)
    app = Flask(__name__)
    with app.test_request_context("/?scope=team"):
        response, status = _protected("team")()
        assert status == 403
