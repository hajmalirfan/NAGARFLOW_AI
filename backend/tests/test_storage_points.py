from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.migrations import upgrade_legacy_storage_point_schema
from app.models import Scenario, StoragePoint, User, Vehicle
from app.models.scenario import scenario_storage_points, scenario_vehicles

STORAGE_POINTS = "/api/v1/storage-points"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def point_payload(**overrides: object) -> dict[str, object]:
    return {
        "name": "Central Market Collection Point",
        "point_code": "SP001",
        "address": "Central Market, Trichy",
        "latitude": 10.7905,
        "longitude": 78.7047,
        "waste_quantity_kg": 1200,
        "availability_status": "available",
        "description": "Verified market collection area.",
        **overrides,
    }


def test_storage_point_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(STORAGE_POINTS).status_code in (401, 403)
    assert client.post(STORAGE_POINTS, json=point_payload()).status_code in (401, 403)
    assert client.get(f"{STORAGE_POINTS}/1").status_code in (401, 403)


def test_create_list_view_update_and_delete_storage_point(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    created = client.post(
        STORAGE_POINTS, json=point_payload(), headers=auth_headers
    )
    assert created.status_code == 201, created.text
    point = created.json()
    assert point["name"] == "Central Market Collection Point"
    assert point["point_code"] == "SP001"
    assert point["waste_quantity_kg"] == 1200

    listed = client.get(STORAGE_POINTS, headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [point["id"]]
    viewed = client.get(f"{STORAGE_POINTS}/{point['id']}", headers=auth_headers)
    assert viewed.status_code == 200
    assert viewed.json() == point

    updated = client.put(
        f"{STORAGE_POINTS}/{point['id']}",
        json=point_payload(
            name="Updated market point",
            waste_quantity_kg="950.50",
            availability_status="unavailable",
        ),
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["waste_quantity_kg"] == 950.5
    assert updated.json()["availability_status"] == "unavailable"
    stored = db_session.get(StoragePoint, point["id"])
    assert stored is not None
    assert stored.waste_kg == Decimal("950.50")

    deleted = client.delete(f"{STORAGE_POINTS}/{point['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get(f"{STORAGE_POINTS}/{point['id']}", headers=auth_headers).status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": 90.01},
        {"longitude": -180.01},
        {"waste_quantity_kg": -1},
        {"name": "   "},
        {"point_code": " "},
        {"availability_status": "pending"},
    ],
)
def test_create_rejects_invalid_storage_point_data(
    client: TestClient,
    auth_headers: dict[str, str],
    overrides: dict[str, object],
) -> None:
    response = client.post(
        STORAGE_POINTS,
        json=point_payload(**overrides),
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_point_codes_are_unique_case_insensitively(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.post(STORAGE_POINTS, json=point_payload(), headers=auth_headers).status_code == 201
    duplicate = client.post(
        STORAGE_POINTS,
        json=point_payload(point_code="sp001"),
        headers=auth_headers,
    )
    assert duplicate.status_code == 409


def test_storage_points_are_scoped_to_the_signed_in_coordinator(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(STORAGE_POINTS, json=point_payload(), headers=auth_headers).json()
    second_account = {
        "name": "Other Coordinator",
        "email": "other@example.com",
        "password": "other-password-123",
    }
    assert client.post("/api/v1/auth/register", json=second_account).status_code == 201
    token = client.post(
        "/api/v1/auth/login",
        json={"email": second_account["email"], "password": second_account["password"]},
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}

    assert client.get(STORAGE_POINTS, headers=other_headers).json() == []
    assert client.get(f"{STORAGE_POINTS}/{created['id']}", headers=other_headers).status_code == 404
    assert client.delete(f"{STORAGE_POINTS}/{created['id']}", headers=other_headers).status_code == 404


def test_linked_point_cannot_be_deleted_or_increased_beyond_vehicle_capacity(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    created = client.post(
        STORAGE_POINTS, json=point_payload(waste_quantity_kg=100), headers=auth_headers
    ).json()
    user = db_session.scalar(select(User).where(User.email == registered_user["email"]))
    assert user is not None
    scenario = Scenario(
        user_id=user.id,
        reference="SC-STORAGE-1",
        name="Storage capacity scenario",
        description="",
    )
    vehicles = [
        Vehicle(
            user_id=user.id,
            name=f"Truck {index}",
            capacity_kg=Decimal("100"),
            start_latitude=10.7,
            start_longitude=78.6,
        )
        for index in (1, 2)
    ]
    point = db_session.get(StoragePoint, created["id"])
    assert point is not None
    db_session.add_all([scenario, *vehicles])
    db_session.flush()
    scenario.selected_vehicles = vehicles
    scenario.selected_storage_points = [point]
    db_session.commit()

    increase = client.put(
        f"{STORAGE_POINTS}/{point.id}",
        json=point_payload(waste_quantity_kg=250),
        headers=auth_headers,
    )
    assert increase.status_code == 409
    mark_unavailable = client.put(
        f"{STORAGE_POINTS}/{point.id}",
        json=point_payload(availability_status="unavailable"),
        headers=auth_headers,
    )
    assert mark_unavailable.status_code == 409
    assert client.delete(
        f"{STORAGE_POINTS}/{point.id}", headers=auth_headers
    ).status_code == 409
    assert db_session.execute(
        select(scenario_storage_points.c.storage_point_id).where(
            scenario_storage_points.c.scenario_id == scenario.id
        )
    ).scalar_one() == point.id
    assert len(
        db_session.execute(
            select(scenario_vehicles.c.vehicle_id).where(
                scenario_vehicles.c.scenario_id == scenario.id
            )
        ).all()
    ) == 2


def test_legacy_storage_point_migration_preserves_rows_and_relationship_tables() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        user = User(name="Legacy owner", email="legacy@example.com", hashed_password="hash")
        session.add(user)
        session.flush()
        scenario = Scenario(
            user_id=user.id,
            reference="SC-LEGACY-SP",
            name="Legacy storage scenario",
            description="",
        )
        session.add(scenario)
        session.commit()
        scenario_id = scenario.id

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("DROP TABLE storage_points")
        connection.exec_driver_sql(
            "CREATE TABLE storage_points ("
            "id INTEGER PRIMARY KEY, scenario_id INTEGER NOT NULL, name VARCHAR(150) NOT NULL, "
            "latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, waste_kg FLOAT NOT NULL, "
            "waste_type VARCHAR(50), available_from TIMESTAMP, "
            "FOREIGN KEY(scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE)"
        )
        connection.exec_driver_sql(
            "INSERT INTO storage_points "
            "(id, scenario_id, name, latitude, longitude, waste_kg, waste_type) "
            "VALUES (9, ?, 'Legacy point', 10.5, 78.5, 80.25, 'mixed')",
            (scenario_id,),
        )
        connection.exec_driver_sql(
            "INSERT INTO scenario_storage_points (scenario_id, storage_point_id) VALUES (?, 9)",
            (scenario_id,),
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    upgrade_legacy_storage_point_schema(engine)
    upgrade_legacy_storage_point_schema(engine)
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT id, user_id, scenario_id, point_code, waste_kg, availability_status "
            "FROM storage_points WHERE id = 9"
        ).one()
        assert row == (9, 1, scenario_id, "LEGACY-SP-9", 80.25, "available")
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql(
            "SELECT storage_point_id FROM scenario_storage_points WHERE scenario_id = ?",
            (scenario_id,),
        ).scalar_one() == 9
    engine.dispose()


def test_available_from_round_trips(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/storage-points",
        json=point_payload(available_from="2026-11-03T09:30:00"),
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    assert created.json()["available_from"] == "2026-11-03T09:30:00"
