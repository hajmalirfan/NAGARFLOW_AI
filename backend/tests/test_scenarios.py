"""Scenario management tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Depot,
    OptimizationRun,
    ProcessingFacility,
    Scenario,
    StoragePoint,
    User,
    Vehicle,
)
from app.models.scenario import scenario_storage_points, scenario_vehicles

SCENARIOS = "/api/v1/scenarios"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scenario_resources(
    db_session: Session, registered_user: dict[str, str]
) -> dict[str, object]:
    user = db_session.scalar(select(User).where(User.email == registered_user["email"]))
    assert user is not None
    source = Scenario(
        user_id=user.id,
        reference="SC-RESOURCE",
        name="Configured resource records",
        description="Existing records used as real form choices.",
    )
    db_session.add(source)
    db_session.flush()

    depot = Depot(
        user_id=user.id,
        name="North depot",
        code="DEP-RESOURCE",
        latitude=11.2,
        longitude=77.2,
        is_active=True,
    )
    db_session.add(depot)
    db_session.flush()
    facility = ProcessingFacility(
        scenario_id=source.id,
        name="Central facility",
        latitude=11.5,
        longitude=77.5,
        capacity_kg=9000,
    )
    vehicles = [
        Vehicle(
            user_id=user.id,
            scenario_id=source.id,
            vehicle_number=f"TN50AB{index:04d}",
            name=f"Truck {index}",
            vehicle_type="Truck",
            capacity_kg=5000,
            depot_id=depot.id,
            start_latitude=11,
            start_longitude=77,
            is_available=True,
        )
        for index in (1, 2)
    ]
    points = [
        StoragePoint(
            scenario_id=source.id,
            name=f"Point {index}",
            point_code=f"SC-POINT-{index:02d}",
            latitude=11 + index / 100,
            longitude=77 + index / 100,
            waste_kg=100 * index,
        )
        for index in range(1, 7)
    ]
    db_session.add_all([depot, facility, *vehicles, *points])
    db_session.commit()
    return {
        "depot": depot,
        "facility": facility,
        "vehicles": vehicles,
        "points": points,
        "source": source,
    }


def payload(resources: dict[str, object], *, name: str = "Weekly collection") -> dict[str, object]:
    return {
        "name": name,
        "description": "Routine municipal collection.",
        "depot_id": resources["depot"].id,
        "facility_id": resources["facility"].id,
        "vehicle_ids": [vehicle.id for vehicle in resources["vehicles"]],
        "storage_point_ids": [point.id for point in resources["points"]],
        "status": "ready",
    }


def test_scenario_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(SCENARIOS).status_code in (401, 403)
    assert client.get(f"{SCENARIOS}/options").status_code in (401, 403)
    assert client.post(SCENARIOS, json={}).status_code in (401, 403)


def test_options_contain_only_database_records_for_the_user(
    client: TestClient, auth_headers: dict[str, str], scenario_resources: dict[str, object]
) -> None:
    response = client.get(f"{SCENARIOS}/options", headers=auth_headers)

    assert response.status_code == 200
    options = response.json()
    assert [item["name"] for item in options["depots"]] == ["North depot"]
    assert {item["id"] for item in options["facilities"]} == {scenario_resources["facility"].id}
    assert len(options["vehicles"]) == 2
    assert len(options["storage_points"]) == 6


def test_create_list_and_view_scenario_preserves_relationships(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    db_session: Session,
) -> None:
    created = client.post(SCENARIOS, json=payload(scenario_resources), headers=auth_headers)

    assert created.status_code == 201, created.text
    scenario = created.json()
    assert scenario["name"] == "Weekly collection"
    assert scenario["status"] == "ready"
    assert scenario["depot"]["name"] == "North depot"
    assert scenario["processing_facility"]["name"] == "Central facility"
    assert len(scenario["vehicles"]) == 2
    assert len(scenario["storage_points"]) == 6

    listed = client.get(SCENARIOS, headers=auth_headers).json()
    assert any(item["id"] == scenario["id"] for item in listed)
    viewed = client.get(f"{SCENARIOS}/{scenario['id']}", headers=auth_headers)
    assert viewed.status_code == 200
    assert viewed.json()["storage_points"] == scenario["storage_points"]

    assert len(db_session.execute(
        select(scenario_storage_points.c.storage_point_id).where(
            scenario_storage_points.c.scenario_id == scenario["id"]
        )
    ).all()) == 6
    assert len(db_session.execute(
        select(scenario_vehicles.c.vehicle_id).where(
            scenario_vehicles.c.scenario_id == scenario["id"]
        )
    ).all()) == 2
    dashboard = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    current_scenario = next(
        item for item in dashboard["recent_scenarios"] if item["id"] == scenario["id"]
    )
    assert current_scenario["storage_points_count"] == 6
    assert current_scenario["vehicles_count"] == 2


def test_update_and_delete_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
) -> None:
    created = client.post(SCENARIOS, json=payload(scenario_resources), headers=auth_headers).json()
    updated_payload = payload(scenario_resources, name="Updated collection")
    updated_payload["status"] = "draft"

    updated = client.put(
        f"{SCENARIOS}/{created['id']}", json=updated_payload, headers=auth_headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated collection"
    assert updated.json()["status"] == "draft"

    deleted = client.delete(f"{SCENARIOS}/{created['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get(f"{SCENARIOS}/{created['id']}", headers=auth_headers).status_code == 404


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("vehicle_ids", [1]),
        ("vehicle_ids", [1, 1]),
        ("storage_point_ids", [1, 2, 3, 4, 5]),
        ("storage_point_ids", [1, 2, 3, 4, 5, 6, 1]),
        ("status", "optimizing"),
    ],
)
def test_invalid_scenario_data_is_rejected(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    field: str,
    value: object,
) -> None:
    invalid = payload(scenario_resources)
    invalid[field] = value
    response = client.post(SCENARIOS, json=invalid, headers=auth_headers)

    assert response.status_code == 422


def test_unknown_or_other_users_records_are_rejected(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
) -> None:
    invalid = payload(scenario_resources)
    invalid["facility_id"] = 99999

    assert client.post(SCENARIOS, json=invalid, headers=auth_headers).status_code == 422


def test_unavailable_storage_points_are_not_offered_or_assignable(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    db_session: Session,
) -> None:
    point = scenario_resources["points"][0]
    point.availability_status = "unavailable"
    db_session.commit()

    options = client.get(f"{SCENARIOS}/options", headers=auth_headers).json()
    assert point.id not in {item["id"] for item in options["storage_points"]}
    response = client.post(
        SCENARIOS,
        json=payload(scenario_resources),
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "Unavailable storage points" in response.json()["detail"]


def test_name_must_be_unique_per_user(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
) -> None:
    assert client.post(SCENARIOS, json=payload(scenario_resources), headers=auth_headers).status_code == 201
    duplicate = client.post(SCENARIOS, json=payload(scenario_resources), headers=auth_headers)
    assert duplicate.status_code == 409


def test_scenario_cannot_be_deleted_during_optimization(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    db_session: Session,
) -> None:
    created = client.post(SCENARIOS, json=payload(scenario_resources), headers=auth_headers).json()
    db_session.add(
        OptimizationRun(
            scenario_id=created["id"],
            algorithm="greedy",
            status="running",
            total_distance_m=0,
        )
    )
    db_session.commit()

    response = client.delete(f"{SCENARIOS}/{created['id']}", headers=auth_headers)
    assert response.status_code == 409
