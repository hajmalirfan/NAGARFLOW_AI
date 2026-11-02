"""Attacks on access, tokens and input. Each case failed safely or became a fix."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.evaluation.catalog_loader import load_catalog
from app.main import app
from app.models import Depot, User
from test_depots import depot_payload
from test_facilities import facility_payload
from test_preview import add_good_batch
from test_roles import headers_for, linked_user
from test_storage_points import point_payload
from test_vehicles import vehicle_payload

PREFIX = "/api/v1"
ME = f"{PREFIX}/auth/me"
BIG_TEXT = "x" * 100_000
SQL_TEXT = "'; DROP TABLE users; --"


def scenario_payload() -> dict[str, object]:
    return {
        "name": "Stolen", "description": "", "depot_id": 1, "facility_id": 1,
        "vehicle_ids": [1, 2], "storage_point_ids": [1, 2, 3, 4, 5, 6],
    }


def id_routes(records: dict[str, int], batch: str, member: int) -> list[tuple[str, str, dict | None]]:
    scenario = records["scenario"]
    depot = records["depot"]
    vehicle = records["vehicle"]
    point = records["point"]
    facility = records["facility"]
    return [
        ("GET", f"/depots/{depot}", None),
        ("PUT", f"/depots/{depot}", depot_payload()),
        ("DELETE", f"/depots/{depot}", None),
        ("GET", f"/vehicles/{vehicle}", None),
        ("PUT", f"/vehicles/{vehicle}", vehicle_payload({"id": 1})),
        ("DELETE", f"/vehicles/{vehicle}", None),
        ("GET", f"/storage-points/{point}", None),
        ("PUT", f"/storage-points/{point}", point_payload()),
        ("DELETE", f"/storage-points/{point}", None),
        ("GET", f"/facilities/{facility}", None),
        ("GET", f"/facilities/{facility}/capacity", None),
        ("PUT", f"/facilities/{facility}", facility_payload()),
        ("DELETE", f"/facilities/{facility}", None),
        ("GET", f"/scenarios/{scenario}", None),
        ("PUT", f"/scenarios/{scenario}", scenario_payload()),
        ("DELETE", f"/scenarios/{scenario}", None),
        ("POST", f"/scenarios/{scenario}/validate", None),
        ("POST", f"/scenarios/{scenario}/optimize", None),
        ("GET", f"/scenarios/{scenario}/optimization", None),
        ("GET", f"/scenarios/{scenario}/optimization/{batch}", None),
        ("GET", f"/scenarios/{scenario}/validations", None),
        ("GET", f"/scenarios/{scenario}/preview/routes", None),
        ("GET", f"/scenarios/{scenario}/preview/facility", None),
        ("PUT", f"/team/{member}", {"role": "driver"}),
        ("DELETE", f"/team/{member}", None),
    ]


@pytest.fixture
def workspaces(client: TestClient, db_session: Session) -> dict:
    """Two planners, with records and a team account belonging to the second."""
    for name in ("mine", "theirs"):
        client.post(
            f"{PREFIX}/auth/register",
            json={"name": name, "email": f"{name}@example.com", "password": "a-long-password-1"},
        )
    mine = db_session.scalar(select(User).where(User.email == "mine@example.com"))
    theirs = db_session.scalar(select(User).where(User.email == "theirs@example.com"))
    scenario = load_catalog(db_session, theirs)[0]
    add_good_batch(db_session, scenario, "theirbatch")
    member = linked_user(db_session, theirs, "reviewer", "member@example.com")
    records = {
        "scenario": scenario.id,
        "depot": scenario.depot.id,
        "vehicle": scenario.selected_vehicles[0].id,
        "point": scenario.selected_storage_points[0].id,
        "facility": scenario.processing_facility.id,
    }
    return {
        "mine": mine, "theirs": theirs, "member": member, "scenario": scenario,
        "routes": id_routes(records, "theirbatch", member.id),
    }


def path_shape(path: str) -> str:
    return "/".join("{}" if "{" in part or part.isdigit() or part == "theirbatch" else part
                    for part in path.split("/"))


def test_id_route_list_is_complete(workspaces: dict) -> None:
    covered = {(method, path_shape(f"{PREFIX}{path}")) for method, path, _ in workspaces["routes"]}
    routes = {
        (method, path_shape(route.path))
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(PREFIX) and "{" in route.path
        for method in route.methods
    }

    assert routes - covered == set()


def test_another_workspace_gets_404(client: TestClient, workspaces: dict) -> None:
    headers = headers_for(workspaces["mine"])

    for method, path, body in workspaces["routes"]:
        response = client.request(method, f"{PREFIX}{path}", headers=headers, json=body)
        assert response.status_code == 404, f"{method} {path}: {response.text}"


def test_every_write_refuses_a_linked_account(client: TestClient, workspaces: dict) -> None:
    headers = headers_for(workspaces["member"])

    for method, path, body in workspaces["routes"]:
        if method != "GET":
            response = client.request(method, f"{PREFIX}{path}", headers=headers, json=body)
            assert response.status_code == 403, f"{method} {path}: {response.text}"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def valid_token(client: TestClient, registered_user: dict[str, str]) -> str:
    return client.post(
        f"{PREFIX}/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]


def test_a_tampered_token_is_refused(client: TestClient, registered_user: dict[str, str]) -> None:
    token = valid_token(client, registered_user)
    head, body, signature = token.split(".")
    swapped = ("A" if signature[0] != "A" else "B") + signature[1:]

    assert client.get(ME, headers=bearer(f"{head}.{body}.{swapped}")).status_code == 401


def test_an_expired_token_is_refused(client: TestClient, registered_user: dict[str, str]) -> None:
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_a_wrong_secret_token_is_refused(client: TestClient, registered_user: dict[str, str]) -> None:
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "y" * 40, algorithm="HS256",
    )

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_an_alg_none_token_is_refused(client: TestClient, registered_user: dict[str, str]) -> None:
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        None, algorithm="none",
    )

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_a_token_for_a_deleted_account_is_refused(client: TestClient, db_session: Session) -> None:
    assert client.get(ME, headers=bearer(create_access_token(9999))).status_code == 401


@pytest.mark.parametrize("subject", [{}, {"sub": "not-a-number"}])
def test_a_token_without_a_usable_subject_is_refused(
    client: TestClient, registered_user: dict[str, str], subject: dict
) -> None:
    token = jwt.encode(
        {**subject, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )

    assert client.get(ME, headers=bearer(token)).status_code == 401


OVERSIZED = [
    ("/depots", depot_payload, ("name", "code", "address")),
    ("/storage-points", point_payload, ("name", "point_code", "address", "description")),
    ("/facilities", facility_payload, ("name", "facility_code", "address", "description")),
]


@pytest.mark.parametrize("path,payload,fields", OVERSIZED)
def test_oversized_text_is_refused(
    client: TestClient, workspaces: dict, path: str, payload, fields: tuple[str, ...]
) -> None:
    headers = headers_for(workspaces["mine"])

    for field in fields:
        response = client.post(
            f"{PREFIX}{path}", headers=headers, json={**payload(), field: BIG_TEXT}
        )
        assert response.status_code == 422, field


@pytest.mark.parametrize("field", ("vehicle_number", "name", "vehicle_type"))
def test_oversized_vehicle_text_is_refused(client: TestClient, workspaces: dict, field: str) -> None:
    response = client.post(
        f"{PREFIX}/vehicles", headers=headers_for(workspaces["mine"]),
        json={**vehicle_payload({"id": 1}), field: BIG_TEXT},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("field", ("name", "description"))
def test_oversized_scenario_text_is_refused(client: TestClient, workspaces: dict, field: str) -> None:
    response = client.post(
        f"{PREFIX}/scenarios", headers=headers_for(workspaces["mine"]),
        json={**scenario_payload(), field: BIG_TEXT},
    )

    assert response.status_code == 422


def test_oversized_credentials_are_refused(client: TestClient) -> None:
    response = client.post(
        f"{PREFIX}/auth/login", json={"email": "a@example.com", "password": BIG_TEXT}
    )

    assert response.status_code == 422


def test_sql_shaped_text_is_stored_as_text(
    client: TestClient, workspaces: dict, db_session: Session
) -> None:
    response = client.post(
        f"{PREFIX}/depots", headers=headers_for(workspaces["mine"]),
        json=depot_payload(name=SQL_TEXT, code="SAFE-1"),
    )

    assert response.status_code == 201
    assert response.json()["name"] == SQL_TEXT
    assert db_session.scalar(select(func.count()).select_from(User)) >= 2
    assert db_session.scalar(select(Depot).where(Depot.name == SQL_TEXT)) is not None


def test_sql_shaped_history_filter_returns_no_rows(client: TestClient, workspaces: dict) -> None:
    response = client.get(
        f"{PREFIX}/optimization-history", headers=headers_for(workspaces["mine"]),
        params={"status": SQL_TEXT},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_sql_shaped_login_is_only_a_failed_login(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        f"{PREFIX}/auth/login", json={"email": registered_user["email"], "password": SQL_TEXT}
    )

    assert response.status_code == 401
