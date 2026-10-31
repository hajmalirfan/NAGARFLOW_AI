"""Processing facility tests.

These cover the Step 9 testing checklist and the business rules that the
optimization engine will depend on, above all that facility capacity is
one shared limit across both vehicle deliveries rather than a per-vehicle
allowance.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Depot, ProcessingFacility, Scenario, StoragePoint, User, Vehicle
from app.models.scenario import (
    scenario_facilities,
    scenario_storage_points,
    scenario_vehicles,
)

FACILITIES = "/api/v1/facilities"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def facility_payload(**overrides: object) -> dict[str, object]:
    return {
        "name": "Central Waste Processing Plant",
        "facility_code": "FAC001",
        "address": "Trichy Industrial Area",
        "latitude": 10.8150,
        "longitude": 78.6850,
        "total_capacity_kg": 10000,
        "status": "active",
        "description": "Primary municipal processing plant.",
        **overrides,
    }


def create_facility(client: TestClient, headers: dict[str, str], **overrides: object) -> dict:
    response = client.post(FACILITIES, json=facility_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- Access control ----------------------------------------------------


def test_facility_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(FACILITIES).status_code in (401, 403)
    assert client.post(FACILITIES, json=facility_payload()).status_code in (401, 403)
    assert client.get(f"{FACILITIES}/1").status_code in (401, 403)
    assert client.get(f"{FACILITIES}/1/capacity").status_code in (401, 403)
    assert client.put(f"{FACILITIES}/1", json=facility_payload()).status_code in (401, 403)
    assert client.delete(f"{FACILITIES}/1").status_code in (401, 403)


def test_one_coordinator_cannot_see_another_coordinators_facility(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    mine = create_facility(client, auth_headers)

    other = {"name": "Bala N", "email": "bala@example.com", "password": "bala-password-123"}
    assert client.post("/api/v1/auth/register", json=other).status_code == 201
    token = client.post(
        "/api/v1/auth/login", json={"email": other["email"], "password": other["password"]}
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}

    assert client.get(FACILITIES, headers=other_headers).json() == []
    assert client.get(f"{FACILITIES}/{mine['id']}", headers=other_headers).status_code == 404
    assert client.get(f"{FACILITIES}/{mine['id']}/capacity", headers=other_headers).status_code == 404


# --- CRUD --------------------------------------------------------------


def test_create_list_view_update_and_delete_facility(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    facility = create_facility(client, auth_headers)
    assert facility["name"] == "Central Waste Processing Plant"
    assert facility["facility_code"] == "FAC001"
    assert facility["total_capacity_kg"] == 10000
    assert facility["status"] == "active"
    assert facility["address"] == "Trichy Industrial Area"

    listed = client.get(FACILITIES, headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [facility["id"]]

    fetched = client.get(f"{FACILITIES}/{facility['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["facility_code"] == "FAC001"

    updated = client.put(
        f"{FACILITIES}/{facility['id']}",
        json=facility_payload(name="Renamed Plant", total_capacity_kg=12500.50),
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed Plant"
    assert updated.json()["total_capacity_kg"] == pytest.approx(12500.50)

    deleted = client.delete(f"{FACILITIES}/{facility['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    assert client.get(FACILITIES, headers=auth_headers).json() == []


def test_facility_code_is_normalized_to_upper_case(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    facility = create_facility(client, auth_headers, facility_code="fac-042")
    assert facility["facility_code"] == "FAC-042"


def test_missing_facility_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get(f"{FACILITIES}/9999", headers=auth_headers).status_code == 404
    assert client.get(f"{FACILITIES}/9999/capacity", headers=auth_headers).status_code == 404


# --- Validation --------------------------------------------------------


def test_duplicate_facility_code_is_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    create_facility(client, auth_headers, facility_code="FAC001")

    duplicate = client.post(
        FACILITIES,
        json=facility_payload(name="Second Plant", facility_code="fac001"),
        headers=auth_headers,
    )

    assert duplicate.status_code == 409


def test_zero_capacity_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        FACILITIES, json=facility_payload(total_capacity_kg=0), headers=auth_headers
    )
    assert response.status_code == 422


def test_negative_capacity_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        FACILITIES, json=facility_payload(total_capacity_kg=-500), headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 91),
        ("latitude", -91),
        ("longitude", 181),
        ("longitude", -181),
    ],
)
def test_coordinates_outside_valid_range_are_rejected(
    client: TestClient, auth_headers: dict[str, str], field: str, value: float
) -> None:
    response = client.post(FACILITIES, json=facility_payload(**{field: value}), headers=auth_headers)
    assert response.status_code == 422


def test_blank_name_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(FACILITIES, json=facility_payload(name="   "), headers=auth_headers)
    assert response.status_code == 422


def test_unknown_status_is_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        FACILITIES, json=facility_payload(status="paused"), headers=auth_headers
    )
    assert response.status_code == 422


# --- Active / inactive -------------------------------------------------


def test_facility_can_be_deactivated_and_reactivated(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    facility = create_facility(client, auth_headers)

    deactivated = client.put(
        f"{FACILITIES}/{facility['id']}",
        json=facility_payload(status="inactive"),
        headers=auth_headers,
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "inactive"

    reactivated = client.put(
        f"{FACILITIES}/{facility['id']}",
        json=facility_payload(status="active"),
        headers=auth_headers,
    )
    assert reactivated.json()["status"] == "active"


# --- Shared capacity ---------------------------------------------------


def seed_scenario_using_facility(
    db: Session,
    owner_email: str,
    facility_id: int,
    *,
    reference: str = "SC-9001",
    waste_quantities: tuple[float, ...] = (4000.0, 5000.0),
    vehicle_capacities: tuple[float, ...] = (6000.0, 6000.0),
) -> Scenario:
    """Attach a scenario to a facility with known waste and vehicles."""
    owner = db.scalar(select(User).where(User.email == owner_email))
    assert owner is not None
    depot = Depot(
        user_id=owner.id, name="Central Depot", code=f"D-{reference}",
        latitude=10.79, longitude=78.70, is_active=True,
    )
    db.add(depot)
    db.flush()

    scenario = Scenario(
        user_id=owner.id, reference=reference, name=f"Scenario {reference}", description=""
    )
    db.add(scenario)
    db.flush()

    db.execute(
        scenario_facilities.insert().values(scenario_id=scenario.id, facility_id=facility_id)
    )
    for index, capacity in enumerate(vehicle_capacities):
        vehicle = Vehicle(
            user_id=owner.id, name=f"Vehicle {index + 1}",
            vehicle_number=f"{reference}-V{index + 1}", vehicle_type="Truck",
            capacity_kg=Decimal(str(capacity)), depot_id=depot.id, status="available",
            is_available=True, start_latitude=10.79, start_longitude=78.70,
        )
        db.add(vehicle)
        db.flush()
        db.execute(
            scenario_vehicles.insert().values(scenario_id=scenario.id, vehicle_id=vehicle.id)
        )
    for index, waste in enumerate(waste_quantities):
        point = StoragePoint(
            user_id=owner.id, name=f"Point {index + 1}",
            point_code=f"{reference}-P{index + 1}", latitude=10.79 + index / 100,
            longitude=78.70 + index / 100, waste_kg=Decimal(str(waste)),
            availability_status="available",
        )
        db.add(point)
        db.flush()
        db.execute(
            scenario_storage_points.insert().values(
                scenario_id=scenario.id, storage_point_id=point.id
            )
        )
    db.commit()
    return scenario


def test_capacity_endpoint_reports_the_whole_capacity_when_nothing_is_allocated(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    facility = create_facility(client, auth_headers, total_capacity_kg=10000)

    response = client.get(f"{FACILITIES}/{facility['id']}/capacity", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_capacity_kg"] == pytest.approx(10000)
    assert body["allocated_kg"] == pytest.approx(0)
    assert body["remaining_capacity_kg"] == pytest.approx(10000)
    assert body["scenarios"] == []


def test_capacity_is_shared_across_both_vehicle_deliveries(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """Rule 1: 10,000 kg capacity, 4,000 + 5,000 delivered, 1,000 remaining.

    The capacity is one shared pool. It is NOT 10,000 kg per vehicle.
    """
    facility = create_facility(client, auth_headers, total_capacity_kg=10000)
    seed_scenario_using_facility(
        db_session,
        registered_user["email"],
        facility["id"],
        waste_quantities=(4000.0, 5000.0),
    )

    body = client.get(f"{FACILITIES}/{facility['id']}/capacity", headers=auth_headers).json()

    assert body["total_capacity_kg"] == pytest.approx(10000)
    assert body["allocated_kg"] == pytest.approx(9000)
    assert body["remaining_capacity_kg"] == pytest.approx(1000)
    assert body["is_within_capacity"] is True


def test_capacity_endpoint_breaks_allocation_down_per_scenario(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    facility = create_facility(client, auth_headers, total_capacity_kg=10000)
    seed_scenario_using_facility(
        db_session, registered_user["email"], facility["id"],
        reference="SC-9001", waste_quantities=(4000.0, 5000.0),
    )

    body = client.get(f"{FACILITIES}/{facility['id']}/capacity", headers=auth_headers).json()

    assert len(body["scenarios"]) == 1
    assert body["scenarios"][0]["reference"] == "SC-9001"
    assert body["scenarios"][0]["allocated_kg"] == pytest.approx(9000)


def test_capacity_endpoint_flags_an_over_committed_facility(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    facility = create_facility(client, auth_headers, total_capacity_kg=8000)
    seed_scenario_using_facility(
        db_session, registered_user["email"], facility["id"],
        waste_quantities=(4000.0, 5000.0), vehicle_capacities=(6000.0, 6000.0),
    )

    body = client.get(f"{FACILITIES}/{facility['id']}/capacity", headers=auth_headers).json()

    assert body["allocated_kg"] == pytest.approx(9000)
    assert body["remaining_capacity_kg"] == pytest.approx(-1000)
    assert body["is_within_capacity"] is False


def test_capacity_cannot_be_reduced_below_what_a_scenario_already_commits(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """Rule 2: W1 + W2 <= F must keep holding after an edit."""
    facility = create_facility(client, auth_headers, total_capacity_kg=10000)
    seed_scenario_using_facility(
        db_session, registered_user["email"], facility["id"],
        waste_quantities=(4000.0, 5000.0),
    )

    response = client.put(
        f"{FACILITIES}/{facility['id']}",
        json=facility_payload(total_capacity_kg=8000),
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "capacity" in response.json()["detail"].lower()


def test_capacity_can_be_increased_while_a_scenario_is_linked(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    facility = create_facility(client, auth_headers, total_capacity_kg=10000)
    seed_scenario_using_facility(
        db_session, registered_user["email"], facility["id"],
        waste_quantities=(4000.0, 5000.0),
    )

    response = client.put(
        f"{FACILITIES}/{facility['id']}",
        json=facility_payload(total_capacity_kg=15000),
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["total_capacity_kg"] == pytest.approx(15000)


# --- Scenario relationship --------------------------------------------


def test_a_facility_linked_to_a_scenario_cannot_be_deleted(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    facility = create_facility(client, auth_headers)
    seed_scenario_using_facility(db_session, registered_user["email"], facility["id"])

    response = client.delete(f"{FACILITIES}/{facility['id']}", headers=auth_headers)

    assert response.status_code == 409
    assert "scenario" in response.json()["detail"].lower()
    assert db_session.scalar(select(ProcessingFacility).where(
        ProcessingFacility.id == facility["id"]
    )) is not None


def test_a_facility_linked_to_a_scenario_cannot_be_deactivated(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    facility = create_facility(client, auth_headers)
    seed_scenario_using_facility(db_session, registered_user["email"], facility["id"])

    response = client.put(
        f"{FACILITIES}/{facility['id']}",
        json=facility_payload(status="inactive"),
        headers=auth_headers,
    )

    assert response.status_code == 409


def test_scenario_options_exclude_an_inactive_facility(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Rule 4: inactive facilities cannot be selected in new scenarios."""
    active = create_facility(client, auth_headers, facility_code="FAC-ON")
    inactive = create_facility(client, auth_headers, facility_code="FAC-OFF", status="inactive")

    options = client.get("/api/v1/scenarios/options", headers=auth_headers).json()

    offered = {item["id"] for item in options["facilities"]}
    assert active["id"] in offered
    assert inactive["id"] not in offered


def test_scenario_options_offer_a_facility_created_through_the_api(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    facility = create_facility(client, auth_headers)

    options = client.get("/api/v1/scenarios/options", headers=auth_headers).json()

    offered = {item["id"]: item for item in options["facilities"]}
    assert facility["id"] in offered
    assert offered[facility["id"]]["capacity_kg"] == pytest.approx(10000)


# --- Database persistence ---------------------------------------------


def test_facility_is_persisted_with_its_owner_and_timestamps(
    client: TestClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, str],
    db_session: Session,
) -> None:
    created = create_facility(client, auth_headers)

    stored = db_session.scalar(
        select(ProcessingFacility).where(ProcessingFacility.id == created["id"])
    )
    owner = db_session.scalar(select(User).where(User.email == registered_user["email"]))

    assert stored is not None
    assert stored.user_id == owner.id
    assert stored.facility_code == "FAC001"
    assert Decimal(str(stored.capacity_kg)) == Decimal("10000.00")
    assert stored.created_at is not None
    assert stored.updated_at is not None
