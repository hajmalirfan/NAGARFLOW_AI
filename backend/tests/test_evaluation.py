"""The S01 to S10 catalogue and loading it as ordinary records."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.evaluation import catalog_loader
from app.evaluation.catalog_loader import CATALOG_VERSION, load_catalog, read_catalog
from app.models import OptimizationRun, Scenario, StoragePoint, User
from app.services.optimization import run_provenance
from app.services.validation import RoadCheckResult, validate_scenario
from test_validation import FakeRoadNetwork, auth_headers  # noqa: F401

EVALUATION_URL = "/api/v1/evaluation/scenarios"
CODES = [f"S{number:02d}" for number in range(1, 11)]


def owner(db: Session, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def scenario_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Scenario))


def by_code(scenarios: list[Scenario]) -> dict[str, Scenario]:
    return {scenario.evaluation_code: scenario for scenario in scenarios}


def clean_roads() -> FakeRoadNetwork:
    return FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[]))


def test_manifest_contains_s01_through_s10() -> None:
    assert [case["code"] for case in read_catalog()] == CODES


def test_a_changed_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for path in catalog_loader.CATALOG_DIR.iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / "S01.json").write_text('{"changed": true}')
    monkeypatch.setattr(catalog_loader, "CATALOG_DIR", tmp_path)

    with pytest.raises(ValueError, match="S01"):
        read_catalog()


def test_every_case_has_two_vehicles_and_six_to_ten_points() -> None:
    for case in read_catalog():
        assert len(case["vehicle_capacities_kg"]) == 2
        assert 6 <= len(case["points"]) <= 10


def test_every_case_is_labelled_synthetic() -> None:
    for case in read_catalog():
        assert case["synthetic"] is True


def test_blocked_cases_fail_validation_with_expected_codes(
    client: TestClient, registered_user: dict[str, str], db_session: Session
) -> None:
    scenarios = by_code(load_catalog(db_session, owner(db_session, registered_user["email"])))

    for case in read_catalog():
        if case["expected"]["outcome"] != "blocked":
            continue
        report = validate_scenario(db_session, scenarios[case["code"]], clean_roads())
        assert report.can_optimize is False
        assert set(case["expected"]["error_codes"]) <= {e["code"] for e in report.errors}


def test_routes_cases_pass_validation(
    client: TestClient, registered_user: dict[str, str], db_session: Session
) -> None:
    scenarios = by_code(load_catalog(db_session, owner(db_session, registered_user["email"])))

    for case in read_catalog():
        if case["expected"]["outcome"] == "routes":
            report = validate_scenario(db_session, scenarios[case["code"]], clean_roads())
            assert report.can_optimize is True, (case["code"], report.errors)


def test_loading_twice_creates_nothing_new(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    first = client.post(EVALUATION_URL, headers=auth_headers)
    second = client.post(EVALUATION_URL, headers=auth_headers)

    assert first.status_code == second.status_code == 200
    assert [row["code"] for row in first.json()] == CODES
    assert first.json() == second.json()
    assert scenario_count(db_session) == 10


def test_a_failed_load_leaves_nothing(
    client: TestClient, registered_user: dict[str, str], db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = catalog_loader._create_case
    calls = []

    def fail_on_seventh(*args):
        calls.append(1)
        if len(calls) == 7:
            raise RuntimeError("stop")
        return real(*args)

    monkeypatch.setattr(catalog_loader, "_create_case", fail_on_seventh)
    with pytest.raises(RuntimeError):
        load_catalog(db_session, owner(db_session, registered_user["email"]))

    assert scenario_count(db_session) == 0
    assert db_session.scalar(select(func.count()).select_from(StoragePoint)) == 0


def test_a_deleted_case_is_restored_alone(
    client: TestClient, registered_user: dict[str, str], db_session: Session
) -> None:
    user = owner(db_session, registered_user["email"])
    scenarios = by_code(load_catalog(db_session, user))
    kept = scenarios["S02"].id
    db_session.delete(scenarios["S01"])
    db_session.commit()

    restored = by_code(load_catalog(db_session, user))

    assert scenario_count(db_session) == 10
    assert restored["S02"].id == kept
    assert len(restored["S01"].selected_storage_points) == 8


def test_two_coordinators_load_separately(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    other = {"name": "Second", "email": "second@example.com", "password": "another-password-123"}
    client.post("/api/v1/auth/register", json=other)
    token = client.post(
        "/api/v1/auth/login", json={"email": other["email"], "password": other["password"]}
    ).json()["access_token"]

    mine = client.post(EVALUATION_URL, headers=auth_headers)
    theirs = client.post(EVALUATION_URL, headers={"Authorization": f"Bearer {token}"})

    assert mine.status_code == theirs.status_code == 200
    assert not {r["scenario_id"] for r in mine.json()} & {r["scenario_id"] for r in theirs.json()}
    assert scenario_count(db_session) == 20


def test_loading_needs_authentication(client: TestClient) -> None:
    assert client.post(EVALUATION_URL).status_code == 401


def test_catalogue_runs_record_the_catalogue_version(
    client: TestClient, registered_user: dict[str, str], db_session: Session
) -> None:
    scenarios = load_catalog(db_session, owner(db_session, registered_user["email"]))

    assert run_provenance(scenarios[0])["catalog_version"] == CATALOG_VERSION


DEPOT = {"name": "Real depot", "code": "REAL-D", "latitude": 10.8, "longitude": 78.7}


def test_loading_leaves_real_depots_editable(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    depot = client.post("/api/v1/depots", json=DEPOT, headers=auth_headers).json()
    client.post(EVALUATION_URL, headers=auth_headers)

    response = client.put(
        f"/api/v1/depots/{depot['id']}", json={**DEPOT, "name": "Renamed"}, headers=auth_headers
    )

    assert response.status_code == 200


def test_a_real_depot_can_be_added_after_loading(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(EVALUATION_URL, headers=auth_headers)

    assert client.post("/api/v1/depots", json=DEPOT, headers=auth_headers).status_code == 201


def test_two_real_active_depots_are_still_refused(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(EVALUATION_URL, headers=auth_headers)
    client.post("/api/v1/depots", json=DEPOT, headers=auth_headers)

    response = client.post(
        "/api/v1/depots", json={**DEPOT, "code": "REAL-D2"}, headers=auth_headers
    )

    assert response.status_code == 409


def test_the_dashboard_ignores_catalogue_records(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    before = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    scenarios = load_catalog(db_session, owner(db_session, registered_user["email"]))
    db_session.add(OptimizationRun(
        scenario_id=scenarios[0].id, algorithm="greedy", status="feasible",
        total_distance_m=5, batch_id="b", routes=[],
    ))
    db_session.commit()

    after = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()

    assert after == before


@pytest.mark.parametrize(
    ("url", "body"),
    [
        ("/api/v1/depots", {**DEPOT, "code": "synth-u9-s01-d"}),
        ("/api/v1/facilities", {
            "name": "F", "facility_code": "SYNTH-U9-S01-F", "latitude": 10.8, "longitude": 78.7,
            "total_capacity_kg": "100", "address": "A", "status": "active",
        }),
        ("/api/v1/storage-points", {
            "name": "P", "point_code": "SYNTH-U9-S01-P01", "latitude": 10.8, "longitude": 78.7,
            "waste_quantity_kg": "10",
        }),
        ("/api/v1/vehicles", {
            "name": "V", "vehicle_number": "SYNTH-U9-S01-V1", "vehicle_type": "Truck",
            "capacity_kg": "100", "depot_id": 1,
        }),
    ],
)
def test_catalogue_codes_are_reserved(
    client: TestClient, auth_headers: dict[str, str], url: str, body: dict
) -> None:
    client.post("/api/v1/depots", json=DEPOT, headers=auth_headers)

    response = client.post(url, json=body, headers=auth_headers)

    assert response.status_code == 422
    assert "reserved" in response.text


def test_a_catalogue_record_keeps_its_code_when_edited(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    client.post(EVALUATION_URL, headers=auth_headers)
    point = db_session.scalar(select(StoragePoint).order_by(StoragePoint.id).limit(1))

    response = client.put(
        f"/api/v1/storage-points/{point.id}",
        json={
            "name": "Edited", "point_code": point.point_code, "latitude": 10.8,
            "longitude": 78.7, "waste_quantity_kg": "10",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200


def test_someone_elses_record_is_never_reused(
    client: TestClient, registered_user: dict[str, str], db_session: Session
) -> None:
    other = {"name": "Other", "email": "other@example.com", "password": "another-password-123"}
    client.post("/api/v1/auth/register", json=other)
    user = owner(db_session, registered_user["email"])
    stranger = owner(db_session, other["email"])
    db_session.add(StoragePoint(
        user_id=stranger.id, name="Planted", point_code=f"SYNTH-U{user.id}-S01-P01",
        latitude=10.8, longitude=78.7, waste_kg=1,
    ))
    db_session.commit()

    with pytest.raises(IntegrityError):
        load_catalog(db_session, user)

    assert scenario_count(db_session) == 0
