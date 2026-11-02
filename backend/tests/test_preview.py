"""Scoped previews for driver and facility accounts. No failed run shows a route."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.catalog_loader import load_catalog
from app.models import OptimizationRun, Scenario, User
from test_roles import headers_for, linked_user

NAMES = "/api/v1/scenarios/names"


def good_route(code: str, name: str = "V1", load_kg: float = 500.0) -> dict:
    return {
        "vehicle_id": 1, "vehicle_name": name, "capacity_kg": 6000.0, "load_kg": load_kg,
        "distance_m": 1000, "finish_s": 900, "geometry": [[78.7, 10.8], [78.71, 10.81]],
        "stops": [{"code": code, "arrival_s": 300, "service_s": 60, "wait_s": 0,
                   "latitude": 10.8, "longitude": 78.7}],
    }


def add_run(
    db: Session, scenario: Scenario, batch: str, algorithm: str, status: str, routes: list[dict]
) -> None:
    db.add(OptimizationRun(
        scenario_id=scenario.id, algorithm=algorithm, status=status, batch_id=batch,
        total_distance_m=1000.0 if routes else None, message="", routes=routes,
        input_hash="abc", provenance={},
    ))
    db.commit()


def add_good_batch(db: Session, scenario: Scenario, batch: str = "good") -> None:
    code = scenario.selected_storage_points[0].point_code
    add_run(db, scenario, batch, "greedy", "feasible", [good_route(code, "Greedy V")])
    add_run(db, scenario, batch, "or_tools", "feasible", [good_route(code, "OR V", 400.0)])


@pytest.fixture
def planner(client: TestClient, registered_user: dict[str, str], db_session: Session) -> User:
    return db_session.scalar(select(User).where(User.email == registered_user["email"]))


@pytest.fixture
def scenario(db_session: Session, planner: User) -> Scenario:
    return load_catalog(db_session, planner)[0]


@pytest.fixture
def driver(db_session: Session, planner: User) -> dict[str, str]:
    return headers_for(linked_user(db_session, planner, "driver", "d@example.com"))


@pytest.fixture
def facility(db_session: Session, planner: User) -> dict[str, str]:
    return headers_for(linked_user(db_session, planner, "facility", "f@example.com"))


def routes_url(scenario: Scenario) -> str:
    return f"/api/v1/scenarios/{scenario.id}/preview/routes"


def facility_url(scenario: Scenario) -> str:
    return f"/api/v1/scenarios/{scenario.id}/preview/facility"


def test_names_return_only_id_and_name(
    client: TestClient, scenario: Scenario, driver: dict[str, str]
) -> None:
    body = client.get(NAMES, headers=driver).json()

    assert len(body) == 10
    assert set(body[0]) == {"id", "name"}


def test_names_are_workspace_scoped(
    client: TestClient, scenario: Scenario, db_session: Session
) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "another-password-123"},
    )
    other = db_session.scalar(select(User).where(User.email == "other@example.com"))

    assert client.get(NAMES, headers=headers_for(other)).json() == []


def test_routes_prefer_or_tools(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    add_good_batch(db_session, scenario)

    body = client.get(routes_url(scenario), headers=driver).json()

    point = scenario.selected_storage_points[0]
    assert body["method"] == "or_tools"
    assert body["routes"][0]["vehicle_name"] == "OR V"
    stop = body["routes"][0]["stops"][0]
    assert stop["code"] == point.point_code
    assert stop["name"] == point.name
    assert stop["quantity_kg"] == float(point.waste_kg)
    assert stop["arrival_s"] == 300


def test_routes_fall_back_to_greedy(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    code = scenario.selected_storage_points[0].point_code
    add_run(db_session, scenario, "b", "greedy", "feasible", [good_route(code, "Greedy V")])
    add_run(db_session, scenario, "b", "or_tools", "no_solution", [])

    body = client.get(routes_url(scenario), headers=driver).json()

    assert body["method"] == "greedy"
    assert body["routes"][0]["vehicle_name"] == "Greedy V"


def test_routes_404_when_no_run_exists(
    client: TestClient, scenario: Scenario, driver: dict[str, str]
) -> None:
    response = client.get(routes_url(scenario), headers=driver)

    assert response.status_code == 404
    assert response.json()["detail"] == "No saved route exists for this scenario."


def test_routes_404_when_both_methods_failed(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    add_run(db_session, scenario, "b", "greedy", "no_solution", [])
    add_run(db_session, scenario, "b", "or_tools", "invalid_result", [])

    assert client.get(routes_url(scenario), headers=driver).status_code == 404


def test_a_failed_newest_batch_hides_an_older_route(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str],
    facility: dict[str, str],
) -> None:
    add_good_batch(db_session, scenario, "old")
    add_run(db_session, scenario, "new", "greedy", "timeout", [])
    add_run(db_session, scenario, "new", "or_tools", "timeout", [])

    assert client.get(routes_url(scenario), headers=driver).status_code == 404
    assert client.get(facility_url(scenario), headers=facility).status_code == 404


def test_routes_leave_out_geometry(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    add_good_batch(db_session, scenario)

    response = client.get(routes_url(scenario), headers=driver)

    assert "geometry" not in response.text
    assert "latitude" not in response.text


def test_facility_totals_match_vehicle_loads(
    client: TestClient, db_session: Session, scenario: Scenario, facility: dict[str, str]
) -> None:
    code = scenario.selected_storage_points[0].point_code
    routes = [good_route(code, "A", 400.0), good_route(code, "B", 250.5)]
    add_run(db_session, scenario, "b", "greedy", "feasible", routes)
    add_run(db_session, scenario, "b", "or_tools", "feasible", routes)

    body = client.get(facility_url(scenario), headers=facility).json()

    assert body["expected_total_kg"] == 650.5
    assert body["facility_capacity_kg"] == float(scenario.processing_facility.capacity_kg)
    assert body["vehicles"][0] == {"vehicle_name": "A", "load_kg": 400.0, "capacity_kg": 6000.0}
    assert "stops" not in body


def test_facility_uses_the_same_method_as_routes(
    client: TestClient, db_session: Session, scenario: Scenario, facility: dict[str, str],
    driver: dict[str, str],
) -> None:
    code = scenario.selected_storage_points[0].point_code
    add_run(db_session, scenario, "b", "greedy", "feasible", [good_route(code)])
    add_run(db_session, scenario, "b", "or_tools", "timeout", [])

    assert client.get(facility_url(scenario), headers=facility).json()["method"] == "greedy"
    assert client.get(routes_url(scenario), headers=driver).json()["method"] == "greedy"


def test_a_changed_scenario_is_out_of_date(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    add_good_batch(db_session, scenario)
    scenario.selected_storage_points[0].waste_kg = 1
    db_session.commit()

    assert client.get(routes_url(scenario), headers=driver).json()["out_of_date"] is True


def test_a_fresh_run_is_not_out_of_date(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    add_good_batch(db_session, scenario)

    assert client.get(routes_url(scenario), headers=driver).json()["out_of_date"] is False


def test_a_stop_removed_since_the_run_has_no_quantity(
    client: TestClient, db_session: Session, scenario: Scenario, driver: dict[str, str]
) -> None:
    add_run(db_session, scenario, "b", "or_tools", "feasible", [good_route("GONE")])

    stop = client.get(routes_url(scenario), headers=driver).json()["routes"][0]["stops"][0]

    assert stop["name"] == "GONE"
    assert stop["quantity_kg"] is None


def test_another_workspace_gets_404(
    client: TestClient, db_session: Session, scenario: Scenario
) -> None:
    add_good_batch(db_session, scenario)
    client.post(
        "/api/v1/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "another-password-123"},
    )
    other = db_session.scalar(select(User).where(User.email == "other@example.com"))

    assert client.get(routes_url(scenario), headers=headers_for(other)).status_code == 404
    assert client.get(facility_url(scenario), headers=headers_for(other)).status_code == 404
