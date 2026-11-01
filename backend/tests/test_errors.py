"""Failures reach people as plain messages, and internals stay in the log."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import dashboard, scenarios
from app.core.config import settings
from app.services.optimizer.types import RoutingProblem, no_route_message
from app.services.validation import NullRoadNetwork, validate_scenario
from test_validation import auth_headers, build_scenario, stub_scenario  # noqa: F401

ORIGIN = "http://localhost:5173"


def test_server_error_hides_internals(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args):
        raise RuntimeError("secret database password")

    monkeypatch.setattr(dashboard, "build_dashboard_summary", explode)

    response = client.get(
        "/api/v1/dashboard/summary", headers={**auth_headers, "Origin": ORIGIN}
    )

    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["detail"] == "Something went wrong on the server."
    assert len(response.json()["reference"]) == 8
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_http_errors_are_unchanged(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 401
    assert "reference" not in response.json()


def test_point_ready_at_shift_end_fails_validation() -> None:
    moment = datetime(2026, 11, 9, 16, 0)

    report = validate_scenario(
        None, stub_scenario(shift_end=moment, available_from=moment), NullRoadNetwork()
    )

    assert "AVAILABILITY_AFTER_SHIFT" in {error["code"] for error in report.errors}


def test_override_without_a_network_returns_409(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "require_road_connectivity", False)
    monkeypatch.setattr(scenarios, "get_road_network", NullRoadNetwork)
    scenario = build_scenario(db_session, registered_user["email"])

    response = client.post(f"/api/v1/scenarios/{scenario.id}/optimize", headers=auth_headers)

    assert response.status_code == 409
    assert "road network" in response.json()["detail"]["message"].lower()


def test_mixed_timezone_shift_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/scenarios",
        headers=auth_headers,
        json={
            "name": "Mixed", "vehicle_ids": [1, 2], "storage_point_ids": [1, 2, 3, 4, 5, 6],
            "depot_id": 1, "facility_id": 1,
            "shift_start": "2026-11-09T08:00", "shift_end": "2026-11-09T12:00Z",
        },
    )

    assert response.status_code == 422
    assert "same format" in response.text


def _problem(shift_end_s: int | None) -> RoutingProblem:
    return RoutingProblem(
        names=["D", "P", "F"], demand_g=[0, 1, 0], ready_s=[0, 0, 0], vehicle_ids=[1],
        capacity_g=[10], facility_capacity_g=10, distance_m=[[0] * 3] * 3,
        time_s=[[0] * 3] * 3, shift_end_s=shift_end_s,
    )


def test_no_route_message_points_at_the_shift() -> None:
    message = no_route_message(_problem(100), "The solver found no route.")

    assert message.startswith("The solver found no route.")
    assert "shift" in message and "availability" in message


def test_no_route_message_without_a_shift_is_unchanged() -> None:
    assert no_route_message(_problem(None), "No route.") == "No route."
