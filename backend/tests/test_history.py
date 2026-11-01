"""Looking back over saved runs."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OptimizationRun, User
from test_validation import auth_headers, build_scenario  # noqa: F401

HISTORY_URL = "/api/v1/optimization-history"


def add_batch(
    db: Session, scenario_id: int, batch: str,
    greedy: tuple[str, float | None] = ("feasible", 1000.0),
    or_tools: tuple[str, float | None] = ("feasible", 900.0),
) -> None:
    for algorithm, (status, distance) in (("greedy", greedy), ("or_tools", or_tools)):
        db.add(OptimizationRun(
            scenario_id=scenario_id, algorithm=algorithm, status=status,
            total_distance_m=distance, batch_id=batch, routes=[],
        ))
    db.commit()


def other_scenario(client: TestClient, db: Session):
    other = {"name": "Other", "email": "other@example.com", "password": "another-password-123"}
    client.post("/api/v1/auth/register", json=other)
    return build_scenario(db, other["email"], reference="OTHER")


@pytest.fixture
def scenario(client: TestClient, registered_user: dict[str, str], db_session: Session):
    return build_scenario(db_session, registered_user["email"])


def test_history_is_newest_first(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    add_batch(db_session, scenario.id, "old")
    add_batch(db_session, scenario.id, "new")

    body = client.get(HISTORY_URL, headers=auth_headers).json()

    assert body["total"] == 2
    assert [row["batch_id"] for row in body["items"]] == ["new", "old"]
    assert body["items"][0]["scenario_name"] == scenario.name
    assert body["items"][0]["greedy_distance_m"] == 1000
    assert body["items"][0]["or_tools_distance_m"] == 900
    assert body["items"][0]["difference_m"] == 100


def test_history_pages(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    for name in ("a", "b", "c"):
        add_batch(db_session, scenario.id, name)

    body = client.get(HISTORY_URL, params={"limit": 1, "offset": 1}, headers=auth_headers).json()

    assert [row["batch_id"] for row in body["items"]] == ["b"]
    assert body["total"] == 3


def test_limit_above_100_is_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(HISTORY_URL, params={"limit": 101}, headers=auth_headers)

    assert response.status_code == 422


def test_filters_by_scenario(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, scenario,
) -> None:
    second = build_scenario(db_session, registered_user["email"], reference="SECOND")
    add_batch(db_session, scenario.id, "first")
    add_batch(db_session, second.id, "second")

    body = client.get(
        HISTORY_URL, params={"scenario_id": second.id}, headers=auth_headers
    ).json()

    assert [row["batch_id"] for row in body["items"]] == ["second"]


def test_status_matches_either_method(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    add_batch(db_session, scenario.id, "fine")
    add_batch(db_session, scenario.id, "greedy-failed", greedy=("no_solution", None))
    add_batch(db_session, scenario.id, "solver-failed", or_tools=("no_solution", None))

    body = client.get(
        HISTORY_URL, params={"status": "no_solution"}, headers=auth_headers
    ).json()

    assert {row["batch_id"] for row in body["items"]} == {"greedy-failed", "solver-failed"}
    assert body["total"] == 2


def test_a_failed_method_has_no_distance_or_difference(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    add_batch(db_session, scenario.id, "failed", greedy=("no_solution", None))

    row = client.get(HISTORY_URL, headers=auth_headers).json()["items"][0]

    assert row["greedy_distance_m"] is None
    assert row["difference_m"] is None


def test_history_hides_other_coordinators(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    add_batch(db_session, other_scenario(client, db_session).id, "theirs")

    assert client.get(HISTORY_URL, headers=auth_headers).json() == {"items": [], "total": 0}


def test_rows_without_a_batch_are_left_out(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    db_session.add(OptimizationRun(
        scenario_id=scenario.id, algorithm="greedy", status="success", total_distance_m=5,
    ))
    db_session.commit()

    assert client.get(HISTORY_URL, headers=auth_headers).json()["total"] == 0


def test_saved_comparison_opens(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    add_batch(db_session, scenario.id, "first", greedy=("feasible", 2000.0))
    add_batch(db_session, scenario.id, "second")

    response = client.get(
        f"/api/v1/scenarios/{scenario.id}/optimization/first", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["greedy"]["total_distance_m"] == 2000


def test_unknown_batch_is_404(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, scenario
) -> None:
    response = client.get(
        f"/api/v1/scenarios/{scenario.id}/optimization/none", headers=auth_headers
    )

    assert response.status_code == 404


def test_another_coordinators_batch_is_404(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    theirs = other_scenario(client, db_session)
    add_batch(db_session, theirs.id, "theirs")

    response = client.get(
        f"/api/v1/scenarios/{theirs.id}/optimization/theirs", headers=auth_headers
    )

    assert response.status_code == 404


def test_a_batch_from_another_scenario_is_404(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, scenario,
) -> None:
    second = build_scenario(db_session, registered_user["email"], reference="SECOND")
    add_batch(db_session, second.id, "second")

    response = client.get(
        f"/api/v1/scenarios/{scenario.id}/optimization/second", headers=auth_headers
    )

    assert response.status_code == 404
