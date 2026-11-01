"""The S01 to S10 catalogue and loading it as ordinary records."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evaluation import catalog_loader
from app.evaluation.catalog_loader import CATALOG_VERSION, load_catalog, read_catalog
from app.models import Scenario, StoragePoint, User
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
