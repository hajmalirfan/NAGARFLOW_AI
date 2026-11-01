"""Scenario validation engine tests.

The engine is the gate in front of the optimization algorithms, so these
tests pin down every hard constraint from Step 10, including the one that
is easy to get wrong: combined capacity can pass while no assignment of
whole storage points to two vehicles exists.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Depot,
    ProcessingFacility,
    Scenario,
    ScenarioValidation,
    StoragePoint,
    User,
    Vehicle,
)
from app.services.validation import RoadCheckResult, RoadLocation, validate_scenario
from app.models.scenario import (
    scenario_depots,
    scenario_facilities,
    scenario_storage_points,
    scenario_vehicles,
)

SCENARIOS = "/api/v1/scenarios"


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict[str, str]) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def build_scenario(
    db: Session,
    owner_email: str,
    *,
    reference: str = "SC-VAL",
    waste: tuple[float, ...] = (1000, 1000, 1000, 1000, 1000, 1000),
    vehicle_capacities: tuple[float, ...] = (5000, 4000),
    vehicles_available: tuple[bool, ...] = (True, True),
    facility_capacity: float | None = 10000,
    facility_status: str = "active",
    with_depot: bool = True,
    depot_active: bool = True,
    coordinates: tuple[tuple[float, float], ...] | None = None,
) -> Scenario:
    """Assemble a scenario directly, so invalid states can be exercised.

    The create endpoint refuses most invalid combinations, but data drifts
    afterwards: a vehicle is taken out of service, a waste quantity is
    edited, a facility capacity is reduced. Validation runs against the
    scenario as it stands now.
    """
    owner = db.scalar(select(User).where(User.email == owner_email))
    assert owner is not None

    scenario = Scenario(
        user_id=owner.id, reference=reference, name=f"Scenario {reference}", description=""
    )
    db.add(scenario)
    db.flush()

    depot = None
    if with_depot:
        depot = Depot(
            user_id=owner.id, name="Depot", code=f"D-{reference}",
            latitude=10.79, longitude=78.70, is_active=depot_active,
        )
        db.add(depot)
        db.flush()
        db.execute(
            scenario_depots.insert().values(scenario_id=scenario.id, depot_id=depot.id)
        )

    if facility_capacity is not None:
        facility = ProcessingFacility(
            user_id=owner.id, name="Facility", facility_code=f"F-{reference}",
            latitude=10.81, longitude=78.68,
            capacity_kg=Decimal(str(facility_capacity)), status=facility_status,
        )
        db.add(facility)
        db.flush()
        db.execute(
            scenario_facilities.insert().values(
                scenario_id=scenario.id, facility_id=facility.id
            )
        )

    for index, capacity in enumerate(vehicle_capacities):
        available = vehicles_available[index] if index < len(vehicles_available) else True
        vehicle = Vehicle(
            user_id=owner.id, name=f"Vehicle {index + 1}",
            vehicle_number=f"{reference}-V{index + 1}", vehicle_type="Truck",
            capacity_kg=Decimal(str(capacity)),
            depot_id=depot.id if depot else None,
            status="available" if available else "maintenance",
            is_available=available,
            start_latitude=10.79, start_longitude=78.70,
        )
        db.add(vehicle)
        db.flush()
        db.execute(
            scenario_vehicles.insert().values(scenario_id=scenario.id, vehicle_id=vehicle.id)
        )

    for index, quantity in enumerate(waste):
        latitude, longitude = (
            coordinates[index] if coordinates and index < len(coordinates)
            else (10.79 + index / 100, 78.70 + index / 100)
        )
        point = StoragePoint(
            user_id=owner.id, name=f"Point {index + 1}",
            point_code=f"{reference}-P{index + 1}",
            latitude=latitude, longitude=longitude,
            waste_kg=Decimal(str(quantity)), availability_status="available",
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


class _Stub:
    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)


def stub_scenario(
    *,
    waste: tuple[float, ...] = (1000, 1000, 1000, 1000, 1000, 1000),
    bad_latitude: bool = False,
    null_longitude: bool = False,
) -> _Stub:
    """An in-memory scenario for states the database no longer allows."""
    points = [
        _Stub(
            id=index + 1,
            point_code=f"SP{index + 1:03d}",
            waste_kg=Decimal(str(quantity)),
            latitude=120.0 if (bad_latitude and index == 0) else 10.79 + index / 100,
            longitude=None if (null_longitude and index == 0) else 78.70 + index / 100,
        )
        for index, quantity in enumerate(waste)
    ]
    vehicles = [
        _Stub(
            id=index + 1, name=f"Vehicle {index + 1}", vehicle_number=f"V{index + 1}",
            capacity_kg=Decimal(str(capacity)), is_available=True, status="available",
        )
        for index, capacity in enumerate((5000, 4000))
    ]
    depot = _Stub(id=1, name="Depot", code="DEP-01", is_active=True,
                  latitude=10.79, longitude=78.70)
    facility = _Stub(id=1, facility_code="FAC001", status="active",
                     capacity_kg=Decimal("20000"), latitude=10.81, longitude=78.68)
    return _Stub(
        id=1, reference="SC-STUB", depot=depot, processing_facility=facility,
        facilities=[facility], selected_vehicles=vehicles, vehicles=[],
        selected_storage_points=points, storage_points=[],
    )


def validate(client: TestClient, headers: dict[str, str], scenario_id: int) -> dict:
    response = client.post(f"{SCENARIOS}/{scenario_id}/validate", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def error_codes(report: dict) -> set[str]:
    return {error["code"] for error in report["errors"]}


# --- Access control ----------------------------------------------------


def test_validate_requires_authentication(client: TestClient) -> None:
    assert client.post(f"{SCENARIOS}/1/validate").status_code in (401, 403)


def test_validating_another_coordinators_scenario_is_refused(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    other = {"name": "Bala N", "email": "bala@example.com", "password": "bala-password-123"}
    assert client.post("/api/v1/auth/register", json=other).status_code == 201
    scenario = build_scenario(db_session, other["email"], reference="SC-OTHER")

    response = client.post(f"{SCENARIOS}/{scenario.id}/validate", headers=auth_headers)

    assert response.status_code == 404


def test_validating_a_missing_scenario_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.post(f"{SCENARIOS}/9999/validate", headers=auth_headers).status_code == 404


# --- A scenario that satisfies every implementable constraint ----------


def test_a_sound_scenario_passes_every_check_it_can(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    report = validate(client, auth_headers, scenario.id)

    assert report["scenario_id"] == scenario.id
    assert report["errors"] == []
    for check in (
        "depot", "vehicles", "storage_points", "facility", "waste_quantity",
        "vehicle_capacity", "combined_capacity", "facility_capacity",
        "coordinates", "vehicle_assignment",
    ):
        assert report["checks"][check] == "passed", f"{check} should pass"


def test_road_connectivity_is_not_claimed_before_the_road_network_exists(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """A scenario is never called valid while connectivity is unverified."""
    scenario = build_scenario(db_session, registered_user["email"])

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["road_connectivity"] == "not_checked"
    assert report["validation_status"] == "incomplete"
    assert report["can_optimize"] is False
    assert "ROAD_NETWORK_NOT_CONFIGURED" in {w["code"] for w in report["warnings"]}


# --- Rule 1: depot -----------------------------------------------------


def test_a_scenario_without_a_depot_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"], with_depot=False)

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["depot"] == "failed"
    assert "DEPOT_MISSING" in error_codes(report)
    assert report["can_optimize"] is False


def test_an_inactive_depot_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"], depot_active=False)

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["depot"] == "failed"
    assert "DEPOT_INACTIVE" in error_codes(report)


# --- Rule 2: vehicles --------------------------------------------------


@pytest.mark.parametrize("capacities", [(5000,), (5000, 4000, 3000)])
def test_a_scenario_without_exactly_two_vehicles_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, capacities: tuple[float, ...],
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"], vehicle_capacities=capacities,
        vehicles_available=(True,) * len(capacities),
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["vehicles"] == "failed"
    assert "VEHICLE_COUNT" in error_codes(report)


def test_an_inactive_vehicle_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"], vehicles_available=(True, False)
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["vehicles"] == "failed"
    assert "VEHICLE_INACTIVE" in error_codes(report)


# --- Rule 3: storage point count --------------------------------------


def test_fewer_than_six_storage_points_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"], waste=(1000, 1000, 1000, 1000, 1000)
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["storage_points"] == "failed"
    assert "STORAGE_POINT_COUNT" in error_codes(report)


def test_more_than_ten_storage_points_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"], waste=tuple([500] * 11),
        vehicle_capacities=(5000, 4000),
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["storage_points"] == "failed"
    assert "STORAGE_POINT_COUNT" in error_codes(report)


# --- Rule 4: facility --------------------------------------------------


def test_a_scenario_without_a_facility_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"], facility_capacity=None)

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["facility"] == "failed"
    assert "FACILITY_MISSING" in error_codes(report)


def test_an_inactive_facility_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"], facility_status="inactive"
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["facility"] == "failed"
    assert "FACILITY_INACTIVE" in error_codes(report)


# --- Rule 5: waste quantity -------------------------------------------


def test_a_negative_waste_quantity_fails() -> None:
    """A CHECK constraint blocks this today, so the engine is tested directly.

    The check stays because rows created before the constraints existed
    can still hold a negative quantity, and the engine must refuse them
    rather than hand them to the optimizer.
    """
    report = validate_scenario(None, stub_scenario(waste=(-10, 1000, 1000, 1000, 1000, 1000)))

    assert report.checks["waste_quantity"] == "failed"
    assert "WASTE_QUANTITY_NEGATIVE" in {error["code"] for error in report.errors}


# --- Rule 6: a whole storage point must fit one vehicle ---------------


def test_a_storage_point_too_large_for_either_vehicle_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """No splitting: one point's whole quantity rides in one vehicle."""
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(6000, 200, 200, 200, 200, 200),
        vehicle_capacities=(5000, 4000),
        facility_capacity=20000,
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["vehicle_capacity"] == "failed"
    assert "STORAGE_POINT_CAPACITY" in error_codes(report)
    message = next(e["message"] for e in report["errors"] if e["code"] == "STORAGE_POINT_CAPACITY")
    assert "SC-VAL-P1" in message


# --- Rule 7: combined capacity ----------------------------------------


def test_waste_over_the_combined_vehicle_capacity_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(2000, 2000, 2000, 2000, 2000, 2000),
        vehicle_capacities=(5000, 4000),
        facility_capacity=50000,
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["combined_capacity"] == "failed"
    assert "COMBINED_CAPACITY" in error_codes(report)


# --- The partition check: capacity passes but no assignment exists ----


def test_no_feasible_assignment_is_detected_even_when_capacity_checks_pass(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """Three 3,000 kg points, vehicles of 5,000 and 4,000.

    Total 9,000 fits the combined 9,000, and each point fits a vehicle on
    its own, but no split of whole points into the two vehicles works: any
    two points make 6,000, over either vehicle.
    """
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(3000, 3000, 3000, 0, 0, 0),
        vehicle_capacities=(5000, 4000),
        facility_capacity=20000,
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["vehicle_capacity"] == "passed"
    assert report["checks"]["combined_capacity"] == "passed"
    assert report["checks"]["vehicle_assignment"] == "failed"
    assert "NO_FEASIBLE_ASSIGNMENT" in error_codes(report)
    assert report["can_optimize"] is False


def test_a_feasible_partition_is_accepted(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """The worked example: 3,000 + 2,500 + 1,500 + 1,000 into 5,000 / 4,000.

    Vehicle 1 takes 3,000 + 1,500 and vehicle 2 takes 2,500 + 1,000.
    """
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(3000, 2500, 1500, 1000, 0, 0),
        vehicle_capacities=(5000, 4000),
        facility_capacity=10000,
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["vehicle_assignment"] == "passed"
    assert "NO_FEASIBLE_ASSIGNMENT" not in error_codes(report)


def test_the_report_names_a_workable_assignment_when_one_exists(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(3000, 2500, 1500, 1000, 0, 0),
        vehicle_capacities=(5000, 4000),
        facility_capacity=10000,
    )

    report = validate(client, auth_headers, scenario.id)

    assignment = report["feasible_assignment"]
    assert assignment is not None
    assert len(assignment) == 2
    for load in assignment:
        assert load["assigned_kg"] <= load["capacity_kg"]
    assert sum(load["assigned_kg"] for load in assignment) == pytest.approx(8000)


# --- Rule 8: facility capacity ----------------------------------------


def test_waste_over_the_shared_facility_capacity_fails(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(1000, 1000, 1000, 1000, 1000, 1000),
        vehicle_capacities=(5000, 4000),
        facility_capacity=5000,
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["checks"]["facility_capacity"] == "failed"
    assert "FACILITY_CAPACITY" in error_codes(report)


# --- Rule 9: coordinates ----------------------------------------------


def test_an_out_of_range_coordinate_fails() -> None:
    """Also blocked by a CHECK constraint today, so tested at the engine."""
    report = validate_scenario(None, stub_scenario(bad_latitude=True))

    assert report.checks["coordinates"] == "failed"
    assert "INVALID_COORDINATES" in {error["code"] for error in report.errors}


def test_a_missing_coordinate_fails() -> None:
    report = validate_scenario(None, stub_scenario(null_longitude=True))

    assert report.checks["coordinates"] == "failed"
    assert "INVALID_COORDINATES" in {error["code"] for error in report.errors}


# --- Nothing is silently dropped --------------------------------------


def test_every_storage_point_is_accounted_for_in_the_report(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    """Invalid points are reported, never quietly excluded."""
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(6000, 200, 200, 200, 200, 200),
        vehicle_capacities=(5000, 4000), facility_capacity=20000,
    )

    report = validate(client, auth_headers, scenario.id)

    assert report["storage_point_count"] == 6
    assert report["total_waste_kg"] == pytest.approx(7000)


# --- Validation history -----------------------------------------------


def test_each_validation_is_saved_with_the_scenario_and_a_timestamp(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    validate(client, auth_headers, scenario.id)
    validate(client, auth_headers, scenario.id)

    saved = db_session.scalars(
        select(ScenarioValidation)
        .where(ScenarioValidation.scenario_id == scenario.id)
        .order_by(ScenarioValidation.id)
    ).all()
    assert len(saved) == 2
    for record in saved:
        assert record.created_at is not None
        assert record.validation_status in {"valid", "invalid", "incomplete"}
        assert "depot" in record.checks


def test_the_history_endpoint_returns_past_validations_newest_first(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])
    validate(client, auth_headers, scenario.id)
    validate(client, auth_headers, scenario.id)

    response = client.get(f"{SCENARIOS}/{scenario.id}/validations", headers=auth_headers)

    assert response.status_code == 200, response.text
    history = response.json()
    assert len(history) == 2
    assert history[0]["id"] > history[1]["id"]


def test_history_records_the_failure_so_it_can_be_reviewed_later(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"], with_depot=False)

    validate(client, auth_headers, scenario.id)

    record = db_session.scalars(
        select(ScenarioValidation).where(ScenarioValidation.scenario_id == scenario.id)
    ).one()
    assert record.validation_status == "invalid"
    assert record.can_optimize is False
    assert "DEPOT_MISSING" in {error["code"] for error in record.errors}


# --- Several failures at once -----------------------------------------


def test_all_failing_checks_are_reported_not_only_the_first(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"],
        waste=(1000, 1000, 1000),
        vehicle_capacities=(5000,), vehicles_available=(True,),
        facility_capacity=None, with_depot=False,
    )

    report = validate(client, auth_headers, scenario.id)

    codes = error_codes(report)
    assert {"DEPOT_MISSING", "VEHICLE_COUNT", "STORAGE_POINT_COUNT", "FACILITY_MISSING"} <= codes
    assert report["validation_status"] == "invalid"


# --- Rule 10: road connectivity ----------------------------------------


class FakeRoadNetwork:
    """Answers a fixed result, so engine tests need no road data."""

    def __init__(
        self, result: RoadCheckResult | None, warning: dict[str, str] | None = None
    ) -> None:
        self.result = result
        self.calls: list[tuple] = []
        if warning is not None:
            self.warning = warning

    def check(self, depot, points, facility) -> RoadCheckResult | None:
        self.calls.append((depot, points, facility))
        return self.result


def run_road_check(result: RoadCheckResult | None):
    return validate_scenario(None, stub_scenario(), FakeRoadNetwork(result))


def test_clean_road_check_makes_the_scenario_valid() -> None:
    report = run_road_check(RoadCheckResult(too_far=[], unreachable=[]))

    assert report.checks["road_connectivity"] == "passed"
    assert report.validation_status == "valid"
    assert report.can_optimize is True


def test_road_network_receives_each_location_by_its_code() -> None:
    fake = FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[]))

    validate_scenario(None, stub_scenario(), fake)

    depot, points, facility = fake.calls[0]
    assert depot == RoadLocation("DEP-01", 10.79, 78.70)
    assert [point.name for point in points][:2] == ["SP001", "SP002"]
    assert facility == RoadLocation("FAC001", 10.81, 78.68)


def test_location_too_far_from_a_road_is_named() -> None:
    report = run_road_check(RoadCheckResult(too_far=["SP-1"], unreachable=[]))

    assert report.checks["road_connectivity"] == "failed"
    assert report.validation_status == "invalid"
    error = next(e for e in report.errors if e["code"] == "ROAD_TOO_FAR")
    assert "SP-1" in error["message"]
    assert "200" in error["message"]


def test_unreachable_message_lists_five_pairs_and_counts_the_rest() -> None:
    pairs = [f"A{i} → B{i}" for i in range(7)]

    report = run_road_check(RoadCheckResult(too_far=[], unreachable=pairs))

    assert report.validation_status == "invalid"
    message = next(e for e in report.errors if e["code"] == "ROAD_UNREACHABLE")["message"]
    assert "A4 → B4" in message
    assert "A5 → B5" not in message
    assert "2 more" in message


def test_both_road_errors_appear_together() -> None:
    report = run_road_check(RoadCheckResult(too_far=["SP-1"], unreachable=["SP-2 → SP-3"]))

    assert {"ROAD_TOO_FAR", "ROAD_UNREACHABLE"} <= {e["code"] for e in report.errors}


def test_network_warning_is_reported_when_the_network_cannot_answer() -> None:
    fake = FakeRoadNetwork(
        None, warning={"code": "ROAD_NETWORK_UNAVAILABLE", "message": "File is unreadable."}
    )

    report = validate_scenario(None, stub_scenario(), fake)

    assert report.checks["road_connectivity"] == "not_checked"
    assert report.validation_status == "incomplete"
    assert "ROAD_NETWORK_UNAVAILABLE" in {w["code"] for w in report.warnings}


def test_road_check_is_skipped_when_coordinates_failed() -> None:
    fake = FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[]))

    report = validate_scenario(None, stub_scenario(bad_latitude=True), fake)

    assert fake.calls == []
    assert report.checks["road_connectivity"] == "not_checked"
    assert report.validation_status == "invalid"


def test_road_check_is_skipped_without_a_depot() -> None:
    scenario = stub_scenario()
    scenario.depot = None
    fake = FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[]))

    report = validate_scenario(None, scenario, fake)

    assert fake.calls == []
    assert report.validation_status == "invalid"


def test_road_check_is_skipped_without_a_facility() -> None:
    scenario = stub_scenario()
    scenario.processing_facility = None
    scenario.facilities = []
    fake = FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[]))

    report = validate_scenario(None, scenario, fake)

    assert fake.calls == []
    assert report.validation_status == "invalid"
