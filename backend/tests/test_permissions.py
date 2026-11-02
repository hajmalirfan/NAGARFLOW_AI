"""Every route declares a permission, and each role gets exactly what it should."""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS
from app.main import app
from app.models import Depot, User
from test_roles import add_depot, headers_for, linked_user

PREFIX = "/api/v1"
PUBLIC_ACTIONS = ("register", "login", "forgot-password", "verify-reset-token", "reset-password")
PUBLIC = {"/health", f"{PREFIX}/health"}
PUBLIC |= {f"/auth/{action}" for action in PUBLIC_ACTIONS}
PUBLIC |= {f"{PREFIX}/auth/{action}" for action in PUBLIC_ACTIONS}

ALL_ROLES = ("planner", "reviewer", "management", "driver", "facility")
READERS = {"planner", "reviewer"}
SUMMARY_READERS = {"planner", "reviewer", "management"}
PLANNER = {"planner"}
RECORDS = ("depots", "vehicles", "storage-points", "facilities", "scenarios")


def record_rows() -> list[tuple[str, str, set[str]]]:
    rows: list[tuple[str, str, set[str]]] = []
    for record in RECORDS:
        rows += [
            ("GET", f"/{record}", READERS),
            ("POST", f"/{record}", PLANNER),
            ("GET", f"/{record}/1", READERS),
            ("PUT", f"/{record}/1", PLANNER),
            ("DELETE", f"/{record}/1", PLANNER),
        ]
    return rows


MATRIX = [
    ("GET", "/auth/me", set(ALL_ROLES)),
    ("GET", "/dashboard/summary", SUMMARY_READERS),
    *record_rows(),
    ("GET", "/facilities/1/capacity", READERS),
    ("GET", "/scenarios/options", READERS),
    ("GET", "/scenarios/1/validations", READERS),
    ("POST", "/scenarios/1/validate", PLANNER),
    ("POST", "/scenarios/1/optimize", PLANNER),
    ("GET", "/scenarios/1/optimization", READERS),
    ("GET", "/scenarios/1/optimization/abc", READERS),
    ("POST", "/evaluation/scenarios", PLANNER),
    ("GET", "/evaluation/report", SUMMARY_READERS),
    ("GET", "/evaluation/report.csv", SUMMARY_READERS),
    ("GET", "/optimization-history", SUMMARY_READERS),
]


def declared_permission(route: APIRoute) -> str | None:
    pending = list(route.dependant.dependencies)
    while pending:
        dependant = pending.pop()
        name = getattr(dependant.call, "permission", None)
        if name:
            return name
        pending += dependant.dependencies
    return None


def api_routes() -> list[APIRoute]:
    return [route for route in app.routes if isinstance(route, APIRoute)]


@pytest.fixture
def accounts(client: TestClient, registered_user: dict[str, str], db_session: Session) -> dict[str, User]:
    planner = db_session.scalar(select(User).where(User.email == registered_user["email"]))
    linked = {
        role: linked_user(db_session, planner, role, f"{role}@example.com")
        for role in ALL_ROLES[1:]
    }
    return {"planner": planner, **linked}


def test_every_route_declares_a_permission() -> None:
    for route in api_routes():
        if route.path not in PUBLIC:
            assert declared_permission(route) in PERMISSIONS, route.path


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("method,path,allowed", MATRIX)
def test_role_matrix(
    client: TestClient, accounts: dict[str, User], role: str, method: str, path: str,
    allowed: set[str],
) -> None:
    response = client.request(
        method, f"{PREFIX}{path}", headers=headers_for(accounts[role]), json={}
    )

    if role in allowed:
        assert response.status_code != 403, response.text
    else:
        assert response.status_code == 403, response.text
        assert isinstance(response.json()["detail"], str)


def test_matrix_covers_every_protected_route() -> None:
    def shape(path: str) -> str:
        parts = ["{}" if part == "1" or part == "abc" or "{" in part else part
                 for part in path.split("/")]
        return "/".join(parts)

    covered = {(method, shape(f"{PREFIX}{path}")) for method, path, _ in MATRIX}
    routes = {
        (method, shape(route.path))
        for route in api_routes()
        if route.path.startswith(PREFIX) and route.path not in PUBLIC
        for method in route.methods
    }

    assert routes - covered == set()


def test_a_refused_write_changes_nothing(
    client: TestClient, accounts: dict[str, User], db_session: Session
) -> None:
    response = client.post(
        f"{PREFIX}/depots",
        headers=headers_for(accounts["reviewer"]),
        json={"name": "New", "code": "NEW", "address": "Trichy", "latitude": 10.8, "longitude": 78.7},
    )

    assert response.status_code == 403
    assert db_session.scalar(select(func.count()).select_from(Depot)) == 0


def test_a_refused_delete_keeps_the_record(
    client: TestClient, accounts: dict[str, User], db_session: Session
) -> None:
    depot = add_depot(db_session, accounts["planner"], "KEEP")

    response = client.delete(
        f"{PREFIX}/depots/{depot.id}", headers=headers_for(accounts["management"])
    )

    assert response.status_code == 403
    assert db_session.get(Depot, depot.id) is not None


def test_a_role_change_applies_on_the_next_request(
    client: TestClient, accounts: dict[str, User], db_session: Session
) -> None:
    reviewer = accounts["reviewer"]
    headers = headers_for(reviewer)
    assert client.get(f"{PREFIX}/depots", headers=headers).status_code == 200

    reviewer.role = "driver"
    db_session.commit()

    assert client.get(f"{PREFIX}/depots", headers=headers).status_code == 403
