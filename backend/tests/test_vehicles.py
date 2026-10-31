"""Vehicle management, fleet constraints, and scenario integration tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.migrations import upgrade_legacy_vehicle_schema
from app.models import Depot, ProcessingFacility, Scenario, StoragePoint, User, Vehicle

VEHICLES = "/api/v1/vehicles"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def active_depot(
    client: TestClient, auth_headers: dict[str, str]
) -> dict[str, object]:
    response = client.post(
        "/api/v1/depots",
        headers=auth_headers,
        json={
            "name": "North depot",
            "code": "DEP-VEHICLE",
            "address": "Administrator-provided address",
            "latitude": 11.2,
            "longitude": 77.3,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def vehicle_payload(
    depot: dict[str, object],
    *,
    vehicle_number: str = "TN50AB1234",
    name: str = "Truck 01",
    vehicle_type: str = "Truck",
    capacity_kg: float = 5000,
    status: str = "available",
) -> dict[str, object]:
    return {
        "vehicle_number": vehicle_number,
        "name": name,
        "vehicle_type": vehicle_type,
        "capacity_kg": capacity_kg,
        "depot_id": depot["id"],
        "status": status,
    }


@pytest.fixture
def scenario_resources(
    db_session: Session, registered_user: dict[str, str]
) -> dict[str, object]:
    user = db_session.query(User).filter_by(email=registered_user["email"]).one()
    source = Scenario(
        user_id=user.id,
        reference="SC-VEH-RES",
        name="Existing planning resources",
        description="",
    )
    depot = Depot(
        user_id=user.id,
        name="North depot",
        code="DEP-VEH-RES",
        latitude=11.2,
        longitude=77.3,
        is_active=True,
    )
    db_session.add_all([source, depot])
    db_session.flush()
    vehicles = [
        Vehicle(
            user_id=user.id,
            scenario_id=source.id,
            vehicle_number=f"TN50VEH{index}",
            name=f"Truck {index}",
            vehicle_type="Truck",
            capacity_kg=5000,
            depot_id=depot.id,
            status="available",
            is_available=True,
            start_latitude=depot.latitude,
            start_longitude=depot.longitude,
        )
        for index in (1, 2)
    ]
    facility = ProcessingFacility(
        scenario_id=source.id,
        name="Central facility",
        facility_code="FAC-VEHICLES",
        latitude=11.5,
        longitude=77.5,
        capacity_kg=9000,
    )
    points = [
        StoragePoint(
            scenario_id=source.id,
            name=f"Point {index}",
            point_code=f"VEH-POINT-{index:02d}",
            latitude=11 + index / 100,
            longitude=77 + index / 100,
            waste_kg=100 * index,
        )
        for index in range(1, 7)
    ]
    db_session.add_all([*vehicles, facility, *points])
    db_session.commit()
    return {
        "source": source,
        "depot": depot,
        "vehicles": vehicles,
        "facility": facility,
        "points": points,
    }


def test_vehicle_api_requires_authentication(client: TestClient) -> None:
    assert client.get(VEHICLES).status_code in (401, 403)
    assert client.post(VEHICLES, json={}).status_code in (401, 403)
    assert client.get(f"{VEHICLES}/1").status_code in (401, 403)
    assert client.put(f"{VEHICLES}/1", json={}).status_code in (401, 403)
    assert client.delete(f"{VEHICLES}/1").status_code in (401, 403)


def test_create_two_vehicles_list_view_update_and_persist(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
    db_session: Session,
) -> None:
    first = client.post(
        VEHICLES, json=vehicle_payload(active_depot), headers=auth_headers
    )
    assert first.status_code == 201, first.text
    first_vehicle = first.json()
    assert first_vehicle["vehicle_number"] == "TN50AB1234"
    assert first_vehicle["depot"]["id"] == active_depot["id"]
    assert first_vehicle["status"] == "available"
    assert first_vehicle["is_available"] is True

    second = client.post(
        VEHICLES,
        json=vehicle_payload(active_depot, vehicle_number="TN50AB5678", name="Truck 02"),
        headers=auth_headers,
    )
    assert second.status_code == 201, second.text
    assert len(client.get(VEHICLES, headers=auth_headers).json()) == 2
    assert client.get(f"{VEHICLES}/{first_vehicle['id']}", headers=auth_headers).status_code == 200

    updated_payload = vehicle_payload(
        active_depot,
        capacity_kg=6200.5,
        vehicle_type="Mini Truck",
        status="maintenance",
    )
    updated = client.put(
        f"{VEHICLES}/{first_vehicle['id']}",
        json=updated_payload,
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["capacity_kg"] == pytest.approx(6200.5)
    assert updated.json()["status"] == "maintenance"
    assert updated.json()["is_available"] is False

    persisted = db_session.get(Vehicle, first_vehicle["id"])
    assert persisted is not None
    assert persisted.capacity_kg == pytest.approx(6200.5)
    assert persisted.start_latitude == pytest.approx(active_depot["latitude"])

    deleted = client.delete(f"{VEHICLES}/{second.json()['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert db_session.get(Vehicle, second.json()["id"]) is None


def test_registration_number_is_unique_case_insensitively(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
) -> None:
    assert client.post(
        VEHICLES, json=vehicle_payload(active_depot), headers=auth_headers
    ).status_code == 201
    duplicate = client.post(
        VEHICLES,
        json=vehicle_payload(active_depot, vehicle_number="tn50ab1234", status="inactive"),
        headers=auth_headers,
    )
    assert duplicate.status_code == 409


def test_fleet_can_register_additional_vehicles_for_scenario_selection(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
) -> None:
    for number in ("TN50AB1001", "TN50AB1002"):
        assert client.post(
            VEHICLES,
            json=vehicle_payload(active_depot, vehicle_number=number),
            headers=auth_headers,
        ).status_code == 201
    third = client.post(
        VEHICLES,
        json=vehicle_payload(active_depot, vehicle_number="TN50AB1003"),
        headers=auth_headers,
    )
    assert third.status_code == 201, third.text
    assert len(client.get(VEHICLES, headers=auth_headers).json()) == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vehicle_number", " "),
        ("name", " "),
        ("capacity_kg", 0),
        ("capacity_kg", -1),
        ("vehicle_type", "Bus"),
        ("status", "broken"),
    ],
)
def test_invalid_vehicle_data_is_rejected(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
    field: str,
    value: object,
) -> None:
    invalid = vehicle_payload(active_depot)
    invalid[field] = value
    assert client.post(VEHICLES, json=invalid, headers=auth_headers).status_code == 422


def test_vehicle_requires_an_active_owned_depot(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
) -> None:
    response = client.put(
        f"/api/v1/depots/{active_depot['id']}",
        headers=auth_headers,
        json={
            "name": active_depot["name"],
            "code": active_depot["code"],
            "address": active_depot["address"],
            "latitude": active_depot["latitude"],
            "longitude": active_depot["longitude"],
            "is_active": False,
        },
    )
    assert response.status_code == 200
    unavailable = client.post(
        VEHICLES, json=vehicle_payload(active_depot), headers=auth_headers
    )
    assert unavailable.status_code == 422


def test_vehicle_cannot_be_deleted_while_selected_by_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
    db_session: Session,
    registered_user: dict[str, str],
) -> None:
    vehicles = [
        client.post(
            VEHICLES,
            json=vehicle_payload(
                active_depot,
                vehicle_number=f"TN50AB{index}",
                name=f"Truck {index}",
            ),
            headers=auth_headers,
        ).json()
        for index in (1, 2)
    ]
    user = db_session.query(User).filter_by(email=registered_user["email"]).one()
    scenario = Scenario(
        user_id=user.id,
        reference="SC-VEHICLE-TEST",
        name="Vehicle-linked scenario",
        description="",
    )
    db_session.add(scenario)
    db_session.flush()
    scenario.selected_vehicles = [
        db_session.get(Vehicle, vehicle["id"]) for vehicle in vehicles
    ]
    db_session.commit()

    response = client.delete(f"{VEHICLES}/{vehicles[0]['id']}", headers=auth_headers)
    assert response.status_code == 409


def test_independently_managed_vehicles_can_be_selected_and_counted(
    client: TestClient,
    auth_headers: dict[str, str],
    active_depot: dict[str, object],
    db_session: Session,
    registered_user: dict[str, str],
) -> None:
    vehicles = [
        client.post(
            VEHICLES,
            json=vehicle_payload(
                active_depot,
                vehicle_number=f"TN50FLOW{index}",
                name=f"Fleet truck {index}",
            ),
            headers=auth_headers,
        ).json()
        for index in (1, 2)
    ]
    user = db_session.query(User).filter_by(email=registered_user["email"]).one()
    resource_scenario = Scenario(
        user_id=user.id,
        reference="SC-FLEET-RES",
        name="Existing facility and points",
        description="",
    )
    db_session.add(resource_scenario)
    db_session.flush()
    facility = ProcessingFacility(
        scenario_id=resource_scenario.id,
        name="Configured facility",
        facility_code="FAC-VEHICLES-2",
        latitude=11.4,
        longitude=77.4,
        capacity_kg=20000,
    )
    points = [
        StoragePoint(
            scenario_id=resource_scenario.id,
            name=f"Collection point {index}",
            point_code=f"RESOURCE-POINT-{index:02d}",
            latitude=11 + index / 100,
            longitude=77 + index / 100,
            waste_kg=100,
        )
        for index in range(6)
    ]
    db_session.add_all([facility, *points])
    db_session.commit()

    created = client.post(
        "/api/v1/scenarios",
        headers=auth_headers,
        json={
            "name": "Fleet-backed scenario",
            "description": "",
            "depot_id": active_depot["id"],
            "facility_id": facility.id,
            "vehicle_ids": [vehicle["id"] for vehicle in vehicles],
            "storage_point_ids": [point.id for point in points],
            "status": "ready",
        },
    )
    assert created.status_code == 201, created.text

    dashboard = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    assert dashboard["available_vehicles_count"] == 2
    summary = next(
        item
        for item in dashboard["recent_scenarios"]
        if item["id"] == created.json()["id"]
    )
    assert summary["vehicles_count"] == 2
    assert summary["storage_points_count"] == 6


def test_unavailable_vehicle_is_not_offered_or_assignable_to_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    db_session: Session,
) -> None:
    vehicles = scenario_resources["vehicles"]
    vehicles[0].status = "maintenance"
    vehicles[0].is_available = False
    db_session.commit()
    options = client.get("/api/v1/scenarios/options", headers=auth_headers).json()
    assert all(item["id"] != vehicles[0].id for item in options["vehicles"])

    payload = {
        "name": "Unavailable vehicle scenario",
        "description": "",
        "depot_id": scenario_resources["depot"].id,
        "facility_id": scenario_resources["facility"].id,
        "vehicle_ids": [vehicle.id for vehicle in vehicles],
        "storage_point_ids": [point.id for point in scenario_resources["points"]],
        "status": "draft",
    }
    response = client.post(
        "/api/v1/scenarios",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_scenario_rejects_waste_over_combined_vehicle_capacity(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    db_session: Session,
) -> None:
    resources = scenario_resources
    payload = {
        "name": "Over capacity",
        "description": "",
        "depot_id": resources["depot"].id,
        "facility_id": resources["facility"].id,
        "vehicle_ids": [vehicle.id for vehicle in resources["vehicles"]],
        "storage_point_ids": [point.id for point in resources["points"]],
        "status": "draft",
    }
    for vehicle in resources["vehicles"]:
        vehicle.capacity_kg = 500
    db_session.commit()
    response = client.post("/api/v1/scenarios", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert "exceeds the combined capacity" in response.json()["detail"]


def test_legacy_vehicle_table_migration_allows_independent_records() -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, hashed_password TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE scenarios (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "reference TEXT, name TEXT, description TEXT, status TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE depots (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, code TEXT, "
            "address TEXT, latitude FLOAT, longitude FLOAT, is_active BOOLEAN, created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE vehicles (id INTEGER PRIMARY KEY, scenario_id INTEGER NOT NULL, "
            "name VARCHAR(100), capacity_kg FLOAT, start_latitude FLOAT, start_longitude FLOAT, is_available BOOLEAN)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE scenario_vehicles (scenario_id INTEGER NOT NULL, vehicle_id INTEGER NOT NULL, "
            "PRIMARY KEY (scenario_id, vehicle_id), "
            "FOREIGN KEY (scenario_id) REFERENCES scenarios(id), "
            "FOREIGN KEY (vehicle_id) REFERENCES vehicles(id))"
        )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (1, 'Asha', 'asha@example.com', 'hash')"
        )
        connection.exec_driver_sql(
            "INSERT INTO scenarios VALUES (1, 1, 'SC-OLD', 'Old scenario', '', 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO vehicles VALUES (1, 1, 'Old truck', 5000, 11.0, 77.0, 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO scenario_vehicles VALUES (1, 1)"
        )

    upgrade_legacy_vehicle_schema(engine)
    upgrade_legacy_vehicle_schema(engine)
    columns = {column["name"]: column for column in inspect(engine).get_columns("vehicles")}
    assert columns["scenario_id"]["nullable"] is True
    assert {"user_id", "vehicle_number", "vehicle_type", "depot_id", "status"} <= set(columns)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT user_id, vehicle_number, status FROM vehicles WHERE id = 1")
        ).one()
    assert row.user_id == 1
    assert row.vehicle_number is None
    assert row.status == "available"
    with engine.connect() as connection:
        foreign_keys = connection.exec_driver_sql(
            "PRAGMA foreign_key_list(scenario_vehicles)"
        ).all()
        assert any(row[2] == "vehicles" for row in foreign_keys)
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
