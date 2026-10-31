"""Dashboard summary tests.

Every number the dashboard shows is read from the database. These tests
pin that down: an empty database must report zeros, a seeded database
must report the real totals, and one coordinator must never see another
coordinator's figures.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    OptimizationRun,
    ProcessingFacility,
    Scenario,
    StoragePoint,
    User,
    Vehicle,
)

SUMMARY = "/api/v1/dashboard/summary"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_scenario(
    db: Session,
    owner_email: str,
    *,
    name: str = "S01 normal feasible",
    storage_points: tuple[float, ...] = (),
    vehicles: tuple[tuple[float, bool], ...] = (),
    facility_capacity_kg: float | None = None,
    runs: tuple[tuple[str, str, float], ...] = (),
) -> Scenario:
    """Create one scenario with the data the dashboard aggregates."""
    owner = db.scalar(select(User).where(User.email == owner_email))
    assert owner is not None
    scenario = Scenario(user_id=owner.id, reference="SC-0001", name=name, description="")
    db.add(scenario)
    db.flush()

    for index, waste_kg in enumerate(storage_points):
        db.add(
            StoragePoint(
                scenario_id=scenario.id,
                name=f"Point {index + 1}",
                latitude=11.0 + index / 100,
                longitude=77.0 + index / 100,
                waste_kg=waste_kg,
            )
        )
    for index, (capacity_kg, is_available) in enumerate(vehicles):
        db.add(
            Vehicle(
                scenario_id=scenario.id,
                name=f"Vehicle {index + 1}",
                capacity_kg=capacity_kg,
                is_available=is_available,
                start_latitude=11.0,
                start_longitude=77.0,
            )
        )
    if facility_capacity_kg is not None:
        db.add(
            ProcessingFacility(
                scenario_id=scenario.id,
                name="Central facility",
                latitude=11.5,
                longitude=77.5,
                capacity_kg=facility_capacity_kg,
            )
        )
    for algorithm, status, distance_m in runs:
        db.add(
            OptimizationRun(
                scenario_id=scenario.id,
                algorithm=algorithm,
                status=status,
                total_distance_m=distance_m,
            )
        )
    db.commit()
    return scenario


# --- Access control ----------------------------------------------------


def test_summary_requires_authentication(client: TestClient) -> None:
    response = client.get(SUMMARY)
    assert response.status_code in (401, 403)


def test_summary_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.get(SUMMARY, headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


# --- Empty database ----------------------------------------------------


def test_empty_database_reports_zero_for_every_card(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(SUMMARY, headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json() | {
        "total_waste_kg": 0,
        "storage_points_count": 0,
        "available_vehicles_count": 0,
        "facility_remaining_capacity_kg": 0,
        "total_scenarios": 0,
        "optimized_routes_count": 0,
    } == response.json()


def test_empty_database_reports_the_facility_as_not_configured(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.get(SUMMARY, headers=auth_headers).json()

    assert body["facility_configured"] is False


def test_empty_database_returns_empty_sections(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.get(SUMMARY, headers=auth_headers).json()

    assert body["storage_points"] == []
    assert body["recent_scenarios"] == []
    assert body["vehicle_status"]["available"] == []
    assert body["vehicle_status"]["unavailable"] == []
    assert body["optimization_summary"]["total_runs"] == 0


# --- Seeded database ---------------------------------------------------


def test_cards_report_the_real_database_totals(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(
        db_session,
        registered_user["email"],
        storage_points=(1200.0, 800.0, 450.5),
        vehicles=((5000.0, True), (5000.0, False)),
        facility_capacity_kg=9000.0,
        runs=(("greedy", "success", 18400.0), ("or_tools", "success", 15200.0), ("greedy", "failed", 0.0)),
    )

    body = client.get(SUMMARY, headers=auth_headers).json()

    assert body["total_waste_kg"] == pytest.approx(2450.5)
    assert body["storage_points_count"] == 3
    assert body["available_vehicles_count"] == 1
    assert body["facility_remaining_capacity_kg"] == pytest.approx(9000.0)
    assert body["total_scenarios"] == 1
    assert body["optimized_routes_count"] == 2


def test_facility_is_reported_as_configured_when_one_exists(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(db_session, registered_user["email"], facility_capacity_kg=9000.0)

    body = client.get(SUMMARY, headers=auth_headers).json()

    assert body["facility_configured"] is True


def test_waste_overview_describes_the_storage_points(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(db_session, registered_user["email"], storage_points=(1200.0, 800.0, 400.0))

    overview = client.get(SUMMARY, headers=auth_headers).json()["waste_overview"]

    assert overview["total_waste_kg"] == pytest.approx(2400.0)
    assert overview["storage_points_count"] == 3
    assert overview["largest_point_kg"] == pytest.approx(1200.0)
    assert overview["average_point_kg"] == pytest.approx(800.0)


def test_vehicle_status_splits_available_from_unavailable(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(
        db_session,
        registered_user["email"],
        vehicles=((5000.0, True), (4000.0, False), (3000.0, True)),
    )

    status = client.get(SUMMARY, headers=auth_headers).json()["vehicle_status"]

    assert status["available_count"] == 2
    assert status["unavailable_count"] == 1
    assert len(status["available"]) == 2
    assert len(status["unavailable"]) == 1
    assert status["total_available_capacity_kg"] == pytest.approx(8000.0)


def test_storage_point_section_lists_each_point(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(db_session, registered_user["email"], storage_points=(1200.0, 800.0))

    points = client.get(SUMMARY, headers=auth_headers).json()["storage_points"]

    assert len(points) == 2
    assert points[0]["name"] == "Point 1"
    assert points[0]["waste_kg"] == pytest.approx(1200.0)
    assert "latitude" in points[0]
    assert "longitude" in points[0]


def test_recent_scenarios_section_lists_the_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(db_session, registered_user["email"], name="S07 distributed points")

    scenarios = client.get(SUMMARY, headers=auth_headers).json()["recent_scenarios"]

    assert len(scenarios) == 1
    assert scenarios[0]["name"] == "S07 distributed points"
    assert scenarios[0]["reference"] == "SC-0001"
    assert "status" in scenarios[0]
    assert "created_at" in scenarios[0]


def test_optimization_summary_counts_successes_and_failures(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    seed_scenario(
        db_session,
        registered_user["email"],
        runs=(
            ("greedy", "success", 18400.0),
            ("or_tools", "success", 15200.0),
            ("or_tools", "failed", 0.0),
        ),
    )

    summary = client.get(SUMMARY, headers=auth_headers).json()["optimization_summary"]

    assert summary["successful_runs"] == 2
    assert summary["failed_runs"] == 1
    assert summary["total_runs"] == 3
    assert summary["best_distance_km"] == pytest.approx(15.2)


# --- Isolation between coordinators ------------------------------------


def test_one_coordinator_never_sees_another_coordinators_figures(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    other = {"name": "Bala N", "email": "bala@example.com", "password": "bala-password-123"}
    assert client.post("/api/v1/auth/register", json=other).status_code == 201
    seed_scenario(
        db_session,
        other["email"],
        storage_points=(9999.0,),
        vehicles=((7000.0, True),),
        facility_capacity_kg=50000.0,
        runs=(("greedy", "success", 1000.0),),
    )

    body = client.get(SUMMARY, headers=auth_headers).json()

    assert body["total_waste_kg"] == 0
    assert body["storage_points_count"] == 0
    assert body["available_vehicles_count"] == 0
    assert body["facility_remaining_capacity_kg"] == 0
    assert body["total_scenarios"] == 0
    assert body["optimized_routes_count"] == 0
