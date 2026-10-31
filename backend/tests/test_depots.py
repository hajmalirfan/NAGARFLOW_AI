"""Depot CRUD, validation, and scenario relationship tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.migrations import upgrade_legacy_depot_schema
from app.models import Depot, ProcessingFacility, Scenario, StoragePoint, User, Vehicle

DEPOTS = "/api/v1/depots"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def depot_payload(
    *,
    name: str = "Central Municipal Depot",
    code: str = "DEP001",
    latitude: float = 10.7905,
    longitude: float = 78.7047,
    is_active: bool = True,
) -> dict[str, object]:
    return {
        "name": name,
        "code": code,
        "address": "Municipal address entered by administrator",
        "latitude": latitude,
        "longitude": longitude,
        "is_active": is_active,
    }


@pytest.fixture
def scenario_resources(
    db_session: Session, registered_user: dict[str, str]
) -> dict[str, object]:
    user = db_session.query(User).filter_by(email=registered_user["email"]).one()
    source = Scenario(
        user_id=user.id,
        reference="SC-DEPOT-TEST",
        name="Configured resource records",
        description="",
    )
    db_session.add(source)
    db_session.flush()
    depot = Depot(
        user_id=user.id,
        name="North depot",
        code="DEP-TEST",
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
            vehicle_number=f"TN50CD{index:04d}",
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
    }


def test_depot_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(DEPOTS).status_code in (401, 403)
    assert client.post(DEPOTS, json={}).status_code in (401, 403)
    assert client.get(f"{DEPOTS}/1").status_code in (401, 403)
    assert client.put(f"{DEPOTS}/1", json={}).status_code in (401, 403)
    assert client.delete(f"{DEPOTS}/1").status_code in (401, 403)


def test_depot_crud_and_database_persistence(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    created = client.post(DEPOTS, json=depot_payload(), headers=auth_headers)
    assert created.status_code == 201, created.text
    depot = created.json()
    assert depot["name"] == "Central Municipal Depot"
    assert depot["code"] == "DEP001"
    assert depot["latitude"] == pytest.approx(10.7905)

    listed = client.get(DEPOTS, headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [depot["id"]]
    viewed = client.get(f"{DEPOTS}/{depot['id']}", headers=auth_headers)
    assert viewed.status_code == 200
    assert viewed.json()["address"] == "Municipal address entered by administrator"

    updated_payload = depot_payload(
        name="North Municipal Depot",
        code="dep002",
        latitude=11.2,
        longitude=77.3,
        is_active=False,
    )
    updated = client.put(
        f"{DEPOTS}/{depot['id']}", json=updated_payload, headers=auth_headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "North Municipal Depot"
    assert updated.json()["code"] == "DEP002"
    assert updated.json()["is_active"] is False

    persisted = db_session.get(Depot, depot["id"])
    assert persisted is not None
    assert persisted.latitude == pytest.approx(11.2)
    assert persisted.longitude == pytest.approx(77.3)

    deleted = client.delete(f"{DEPOTS}/{depot['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert db_session.get(Depot, depot["id"]) is None


def test_depot_code_is_unique_case_insensitively(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.post(DEPOTS, json=depot_payload(), headers=auth_headers).status_code == 201
    duplicate = client.post(
        DEPOTS,
        json=depot_payload(name="Other", code="dep001", is_active=False),
        headers=auth_headers,
    )
    assert duplicate.status_code == 409


def test_only_one_active_depot_is_allowed_per_user(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.post(DEPOTS, json=depot_payload(), headers=auth_headers).status_code == 201
    second = client.post(
        DEPOTS,
        json=depot_payload(name="Second", code="DEP002"),
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "Only one active depot" in second.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("code", " "),
        ("latitude", -90.01),
        ("latitude", 90.01),
        ("longitude", -180.01),
        ("longitude", 180.01),
    ],
)
def test_invalid_depot_data_is_rejected(
    client: TestClient,
    auth_headers: dict[str, str],
    field: str,
    value: object,
) -> None:
    invalid = depot_payload()
    invalid[field] = value
    assert client.post(DEPOTS, json=invalid, headers=auth_headers).status_code == 422


def test_depot_deletion_is_blocked_when_linked_to_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
) -> None:
    depot = scenario_resources["depot"]
    scenario_payload = {
        "name": "Linked scenario",
        "description": "",
        "depot_id": depot.id,
        "facility_id": scenario_resources["facility"].id,
        "vehicle_ids": [vehicle.id for vehicle in scenario_resources["vehicles"]],
        "storage_point_ids": [point.id for point in scenario_resources["points"]],
        "status": "draft",
    }
    created = client.post(
        "/api/v1/scenarios", json=scenario_payload, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    deletion = client.delete(f"{DEPOTS}/{depot.id}", headers=auth_headers)
    assert deletion.status_code == 409
    assert "linked to a scenario" in deletion.json()["detail"]


def test_inactive_depot_is_not_an_option_or_valid_for_a_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    scenario_resources: dict[str, object],
    db_session: Session,
) -> None:
    depot = scenario_resources["depot"]
    depot.is_active = False
    db_session.commit()

    options = client.get("/api/v1/scenarios/options", headers=auth_headers).json()
    assert all(item["id"] != depot.id for item in options["depots"])

    invalid = {
        "name": "Uses inactive depot",
        "description": "",
        "depot_id": depot.id,
        "facility_id": scenario_resources["facility"].id,
        "vehicle_ids": [vehicle.id for vehicle in scenario_resources["vehicles"]],
        "storage_point_ids": [point.id for point in scenario_resources["points"]],
        "status": "draft",
    }
    response = client.post("/api/v1/scenarios", json=invalid, headers=auth_headers)
    assert response.status_code == 422


def test_legacy_depot_table_is_upgraded_without_inventing_location_data() -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE depots (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "name VARCHAR(150) NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO depots (user_id, name) VALUES (1, 'Existing depot')")
        )

    upgrade_legacy_depot_schema(engine)
    upgrade_legacy_depot_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("depots")}
    assert {"code", "address", "latitude", "longitude", "is_active", "created_at", "updated_at"} <= columns
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT code, latitude, longitude, is_active FROM depots WHERE id = 1")
        ).one()
    assert row.code is None
    assert row.latitude is None
    assert row.longitude is None
    assert bool(row.is_active) is True
    engine.dispose()
