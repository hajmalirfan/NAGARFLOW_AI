"""The S01 to S10 report: every case appears, and no failure shows a distance."""

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.evaluation.catalog_loader import load_catalog
from app.models import OptimizationRun, Scenario, ScenarioValidation, User
from app.services import optimization
from app.services.evaluation_report import build_report, report_csv
from app.services.optimization import optimize_scenario
from test_optimization import line_costs, straight_line
from test_validation import auth_headers  # noqa: F401

REPORT_URL = "/api/v1/evaluation/report"


def add_batch(
    db: Session, scenario: Scenario, batch: str, greedy: float | None = 1000.0,
    or_tools: float | None = 900.0,
) -> None:
    route = {"vehicle_name": "V1", "load_kg": 500.0, "capacity_kg": 6000.0}
    for algorithm, distance in (("greedy", greedy), ("or_tools", or_tools)):
        db.add(OptimizationRun(
            scenario_id=scenario.id, algorithm=algorithm,
            status="feasible" if distance is not None else "no_solution",
            total_distance_m=distance, batch_id=batch, message="" if distance else "No route.",
            routes=[route] if distance is not None else [], input_hash="abc",
            provenance={"catalog_version": "1", "ortools_version": "9", "road_dataset": "r.gpkg",
                        "time_limit_s": 10, "snap_limit_m": 200},
        ))
    db.commit()


def add_validation(db: Session, scenario: Scenario, passed: bool) -> None:
    errors = [] if passed else [{"code": "FACILITY_CAPACITY", "message": "Too much waste."}]
    db.add(ScenarioValidation(
        scenario_id=scenario.id, validation_status="valid" if passed else "invalid",
        can_optimize=passed, checks={}, errors=errors, warnings=[],
    ))
    db.commit()


@pytest.fixture
def user(client: TestClient, registered_user: dict[str, str], db_session: Session) -> User:
    return db_session.scalar(select(User).where(User.email == registered_user["email"]))


@pytest.fixture
def cases(db_session: Session, user: User) -> dict[str, Scenario]:
    return {s.evaluation_code: s for s in load_catalog(db_session, user)}


def row_for(report: dict, code: str) -> dict:
    return next(row for row in report["rows"] if row["code"] == code)


def test_report_always_has_ten_rows(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = client.get(REPORT_URL, headers=auth_headers).json()

    assert [row["code"] for row in body["rows"]] == [f"S{n:02d}" for n in range(1, 11)]
    assert body["synthetic"] is True


def test_state_not_loaded(db_session: Session, user: User) -> None:
    report = build_report(db_session, user)

    assert {row["state"] for row in report["rows"]} == {"not_loaded"}
    assert report["summary"]["not_loaded"] == 10


def test_state_not_run(db_session: Session, user: User, cases: dict) -> None:
    assert row_for(build_report(db_session, user), "S01")["state"] == "not_run"


def test_state_blocked_shows_errors_and_no_distance(
    db_session: Session, user: User, cases: dict
) -> None:
    add_validation(db_session, cases["S05"], passed=False)

    row = row_for(build_report(db_session, user), "S05")

    assert row["state"] == "blocked"
    assert row["errors"] == [{"code": "FACILITY_CAPACITY", "message": "Too much waste."}]
    assert row["greedy"] is None
    assert row["or_tools"] is None
    assert row["difference_m"] is None


def test_blocked_hides_an_older_batch(db_session: Session, user: User, cases: dict) -> None:
    add_validation(db_session, cases["S01"], passed=True)
    add_batch(db_session, cases["S01"], "old")
    add_validation(db_session, cases["S01"], passed=False)

    row = row_for(build_report(db_session, user), "S01")

    assert row["state"] == "blocked"
    assert row["greedy"] is None


def test_state_ran(db_session: Session, user: User, cases: dict) -> None:
    add_validation(db_session, cases["S01"], passed=True)
    add_batch(db_session, cases["S01"], "first")
    add_batch(db_session, cases["S01"], "second", or_tools=800.0)

    row = row_for(build_report(db_session, user), "S01")

    assert row["state"] == "ran"
    assert row["greedy"]["distance_m"] == 1000
    assert row["or_tools"]["distance_m"] == 800
    assert row["difference_m"] == 200
    assert row["difference_pct"] == 20
    assert row["greedy"]["vehicle_loads"] == [
        {"vehicle_name": "V1", "load_kg": 500.0, "capacity_kg": 6000.0}
    ]
    assert row["greedy"]["facility_load_kg"] == 500
    assert row["greedy"]["facility_capacity_kg"] == 20000
    assert row["input_hash"] == "abc"
    assert row["provenance"]["road_dataset"] == "r.gpkg"


def test_infeasible_results_have_no_distance(db_session: Session, user: User, cases: dict) -> None:
    add_batch(db_session, cases["S01"], "failed", greedy=None)

    row = row_for(build_report(db_session, user), "S01")

    assert row["greedy"]["status"] == "no_solution"
    assert row["greedy"]["distance_m"] is None
    assert row["greedy"]["message"] == "No route."
    assert row["difference_m"] is None


def test_summary_means_only_cases_where_both_found_routes(
    db_session: Session, user: User, cases: dict
) -> None:
    add_batch(db_session, cases["S01"], "a", greedy=1000.0, or_tools=900.0)
    add_batch(db_session, cases["S02"], "b", greedy=1000.0, or_tools=700.0)
    add_batch(db_session, cases["S03"], "c", greedy=None, or_tools=500.0)
    add_validation(db_session, cases["S05"], passed=False)

    summary = build_report(db_session, user)["summary"]

    assert summary["ran"] == 3
    assert summary["blocked"] == 1
    assert summary["not_run"] == 6
    assert summary["both_routes"] == 2
    assert summary["mean_difference_m"] == 200
    assert summary["mean_difference_pct"] == 20


def test_summary_mean_is_null_with_no_comparable_cases(db_session: Session, user: User) -> None:
    summary = build_report(db_session, user)["summary"]

    assert summary["mean_difference_m"] is None
    assert summary["mean_difference_pct"] is None


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_leaves_no_route_blank(db_session: Session, user: User, cases: dict) -> None:
    add_batch(db_session, cases["S01"], "failed", greedy=None)
    add_validation(db_session, cases["S05"], passed=False)

    rows = rows_of(report_csv(build_report(db_session, user)))

    assert rows[0]["greedy_distance_m"] == ""
    assert rows[0]["or_tools_distance_m"] == "900.0"
    assert rows[0]["difference_m"] == ""
    assert rows[4]["greedy_distance_m"] == ""
    assert rows[4]["reasons"] == "FACILITY_CAPACITY: Too much waste."


def test_csv_neutralises_formulas(db_session: Session, user: User, cases: dict) -> None:
    for start, code in (("=", "S01"), ("+", "S02"), ("-", "S03"), ("@", "S04")):
        cases[code].name = f'{start}HYPERLINK("http://x")'
    db_session.commit()

    rows = rows_of(report_csv(build_report(db_session, user)))

    assert [row["name"][:2] for row in rows[:4]] == ["'=", "'+", "'-", "'@"]


def test_csv_keeps_a_negative_difference_a_number(
    db_session: Session, user: User, cases: dict
) -> None:
    add_batch(db_session, cases["S01"], "a", greedy=900.0, or_tools=1000.0)

    assert rows_of(report_csv(build_report(db_session, user)))[0]["difference_m"] == "-100.0"


def test_csv_matches_report(
    client: TestClient, auth_headers: dict[str, str], db_session: Session, user: User, cases: dict
) -> None:
    add_batch(db_session, cases["S01"], "a")

    response = client.get(f"{REPORT_URL}.csv", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = rows_of(response.text)
    assert len(rows) == 10
    assert rows[0]["state"] == "ran"
    assert rows[0]["greedy_status"] == "feasible"


def test_report_shows_only_your_own_runs(
    client: TestClient, db_session: Session, user: User, cases: dict
) -> None:
    add_batch(db_session, cases["S01"], "a")
    other = {"name": "Other", "email": "other@example.com", "password": "another-password-123"}
    client.post("/api/v1/auth/register", json=other)
    stranger = db_session.scalar(select(User).where(User.email == other["email"]))

    assert row_for(build_report(db_session, stranger), "S01")["state"] == "not_loaded"


def test_report_needs_authentication(client: TestClient) -> None:
    assert client.get(REPORT_URL).status_code == 401
    assert client.get(f"{REPORT_URL}.csv").status_code == 401


def test_a_changed_record_marks_the_run_out_of_date(
    db_session: Session, user: User, cases: dict
) -> None:
    add_batch(db_session, cases["S01"], "a")
    add_batch(db_session, cases["S02"], "b", greedy=1000.0, or_tools=500.0)
    cases["S01"].selected_storage_points[0].waste_kg = 1
    db_session.commit()

    report = build_report(db_session, user)

    assert row_for(report, "S01")["state"] == "out_of_date"
    assert report["summary"]["out_of_date"] == 1
    assert report["summary"]["both_routes"] == 1
    assert report["summary"]["mean_difference_m"] == 500


def test_a_new_run_clears_out_of_date(db_session: Session, user: User, cases: dict) -> None:
    add_batch(db_session, cases["S01"], "a")
    cases["S01"].selected_storage_points[0].waste_kg = 1
    db_session.commit()
    add_batch(db_session, cases["S01"], "b")

    assert row_for(build_report(db_session, user), "S01")["state"] == "ran"


def test_an_edited_case_is_flagged(db_session: Session, user: User, cases: dict) -> None:
    cases["S02"].selected_storage_points[0].latitude = 11.3
    db_session.commit()

    report = build_report(db_session, user)

    assert row_for(report, "S02")["edited"] is True
    assert row_for(report, "S01")["edited"] is False


def test_outcome_is_compared_with_the_catalogue(
    db_session: Session, user: User, cases: dict
) -> None:
    add_batch(db_session, cases["S01"], "a")
    add_batch(db_session, cases["S02"], "b", or_tools=None)
    add_batch(db_session, cases["S04"], "c")
    add_validation(db_session, cases["S03"], passed=False)
    add_validation(db_session, cases["S05"], passed=False)

    report = build_report(db_session, user)

    assert row_for(report, "S01")["matches_expected"] is True
    assert row_for(report, "S02")["matches_expected"] is False
    assert row_for(report, "S03")["matches_expected"] is False
    assert row_for(report, "S04")["matches_expected"] is False
    assert row_for(report, "S05")["matches_expected"] is True
    assert row_for(report, "S06")["matches_expected"] is None


def test_csv_shows_edited_and_expected(db_session: Session, user: User, cases: dict) -> None:
    cases["S01"].selected_storage_points[0].latitude = 11.3
    db_session.commit()
    add_batch(db_session, cases["S01"], "a")

    row = rows_of(report_csv(build_report(db_session, user)))[0]

    assert row["edited"] == "True"
    assert row["matches_expected"] == "True"


def test_a_real_run_is_current_and_unedited(
    db_session: Session, user: User, cases: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(optimization, "build_cost_matrix", line_costs)
    monkeypatch.setattr(optimization, "route_geometry", straight_line)
    monkeypatch.setattr(settings, "optimizer_time_limit_s", 1)

    optimize_scenario(db_session, cases["S01"], object())

    row = row_for(build_report(db_session, user), "S01")
    assert row["state"] == "ran"
    assert row["edited"] is False
    assert row["matches_expected"] is True
