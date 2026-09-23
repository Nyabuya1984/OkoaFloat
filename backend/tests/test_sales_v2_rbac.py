from types import SimpleNamespace

from flask import Flask

import app.utils.rbac as rbac


def _protected(scope):
    @rbac.require_scope(scope)
    def view():
        return "ok"

    return view


def test_employee_can_use_mine_scope(monkeypatch):
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: SimpleNamespace(role="employee", is_superuser=False))
    app = Flask(__name__)
    with app.test_request_context("/?scope=mine"):
        assert _protected("mine")() == "ok"


def test_employee_cannot_use_team_scope(monkeypatch):
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: SimpleNamespace(role="employee", is_superuser=False))
    app = Flask(__name__)
    with app.test_request_context("/?scope=team"):
        response, status = _protected("team")()
        assert status == 403
        assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_manager_can_use_team_scope(monkeypatch):
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: SimpleNamespace(role="manager", is_superuser=False))
    app = Flask(__name__)
    with app.test_request_context("/?scope=team"):
        assert _protected("team")() == "ok"


def test_conflicting_scope_is_rejected(monkeypatch):
    monkeypatch.setattr(rbac, "_authenticated_user", lambda: SimpleNamespace(role="manager", is_superuser=False))
    app = Flask(__name__)
    with app.test_request_context("/?scope=org"):
        response, status = _protected("team")()
        assert status == 403
        assert response.get_json()["error"]["code"] == "FORBIDDEN"
