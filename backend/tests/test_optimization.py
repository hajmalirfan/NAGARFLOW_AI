"""Paired optimization runs, from scenario records to saved results.

Road costs are replaced at the boundary, so these tests need no road data.
Everything from the scenario records to the saved rows runs for real.
"""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.migrations import upgrade_legacy_optimization_run_schema
from app.models import OptimizationRun
from app.services import optimization
from app.services.optimization import (
    build_problem,
    clock_zero,
    optimize_scenario,
    problem_hash,
    scenario_locations,
)
from app.services.road_costs import CostMatrix
from app.services.validation import RoadCheckResult
from test_validation import (  # noqa: F401
    FakeRoadNetwork,
    auth_headers,
    build_scenario,
    stub_scenario,
)


def line_costs(network: object, locations: list) -> CostMatrix:
    size = len(locations)
    matrix = [[abs(a - b) * 100 for b in range(size)] for a in range(size)]
    return CostMatrix([loc.name for loc in locations], matrix, [list(row) for row in matrix])


def straight_line(network: object, source, target) -> list[tuple[float, float]]:
    return [(source.longitude, source.latitude), (target.longitude, target.latitude)]


@pytest.fixture
def fake_roads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(optimization, "build_cost_matrix", line_costs)
    monkeypatch.setattr(optimization, "route_geometry", straight_line)
    monkeypatch.setattr(settings, "optimizer_time_limit_s", 1)


def problem_for(scenario) -> object:
    return build_problem(scenario, line_costs(None, scenario_locations(scenario)))


def saved(db: Session) -> list[OptimizationRun]:
    return list(db.scalars(select(OptimizationRun).order_by(OptimizationRun.id)))


def test_problem_scales_kg_to_grams_exactly() -> None:
    problem = problem_for(stub_scenario(waste=(1234.56, 1000, 1000, 1000, 1000, 1000)))

    assert problem.demand_g[1] == 1234560
    assert problem.demand_g[0] == 0
    assert problem.demand_g[-1] == 0


def test_points_run_in_ascending_code_order() -> None:
    names = [loc.name for loc in scenario_locations(stub_scenario())]

    assert names == ["DEP-01", "SP001", "SP002", "SP003", "SP004", "SP005", "SP006", "FAC001"]


def test_ready_times_count_from_shift_start() -> None:
    scenario = stub_scenario(available_from=datetime(2026, 11, 3, 7))
    scenario.shift_start = datetime(2026, 11, 3, 6)
    scenario.shift_end = datetime(2026, 11, 3, 14)

    problem = problem_for(scenario)

    assert problem.ready_s[1] == 3600
    assert problem.shift_end_s == 8 * 3600


def test_ready_time_before_shift_start_is_zero() -> None:
    scenario = stub_scenario(available_from=datetime(2026, 11, 3, 1))
    scenario.shift_start = datetime(2026, 11, 3, 6)
    scenario.shift_end = datetime(2026, 11, 3, 14)

    assert problem_for(scenario).ready_s[1] == 0


def test_clock_without_a_shift_starts_at_earliest_availability() -> None:
    scenario = stub_scenario(available_from=datetime(2026, 11, 3, 7))

    assert clock_zero(scenario) == datetime(2026, 11, 3, 7)
    assert problem_for(scenario).shift_end_s is None


def test_hash_is_stable_and_changes_with_input() -> None:
    problem = problem_for(stub_scenario())

    assert problem_hash(problem) == problem_hash(problem_for(stub_scenario()))
    assert problem_hash(problem) != problem_hash(replace(problem, shift_end_s=5))


def test_both_runs_share_batch_and_hash(
    client: TestClient, registered_user: dict[str, str], db_session: Session, fake_roads: None
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    optimize_scenario(db_session, scenario, object())

    greedy, or_tools = saved(db_session)
    assert (greedy.algorithm, or_tools.algorithm) == ("greedy", "or_tools")
    assert greedy.batch_id == or_tools.batch_id
    assert greedy.input_hash == or_tools.input_hash
    assert greedy.status == or_tools.status == "feasible"
    assert greedy.total_distance_m > 0
    assert greedy.routes[0]["geometry"]
    assert greedy.routes[0]["load_kg"] > 0


def test_a_crashing_solver_saves_no_solution_and_the_other_still_runs(
    client: TestClient, registered_user: dict[str, str], db_session: Session,
    fake_roads: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def crash(problem: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(optimization, "solve_greedy", crash)
    scenario = build_scenario(db_session, registered_user["email"])

    optimize_scenario(db_session, scenario, object())

    greedy, or_tools = saved(db_session)
    assert greedy.status == "no_solution"
    assert greedy.total_distance_m is None
    assert or_tools.status == "feasible"


def test_a_result_failing_the_checker_becomes_invalid_result(
    client: TestClient, registered_user: dict[str, str], db_session: Session,
    fake_roads: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = optimization.solve_greedy
    monkeypatch.setattr(
        optimization, "solve_greedy", lambda p: replace(real(p), total_distance_m=1)
    )
    scenario = build_scenario(db_session, registered_user["email"])

    optimize_scenario(db_session, scenario, object())

    greedy = saved(db_session)[0]
    assert greedy.status == "invalid_result"
    assert greedy.total_distance_m is None
    assert greedy.routes == []


def test_failed_runs_store_no_distance(
    client: TestClient, registered_user: dict[str, str], db_session: Session, fake_roads: None
) -> None:
    scenario = build_scenario(
        db_session, registered_user["email"], waste=(3000, 3000, 3000, 0, 0, 0),
        vehicle_capacities=(5000, 4000),
    )

    optimize_scenario(db_session, scenario, object())

    for run in saved(db_session):
        assert run.status != "feasible"
        assert run.total_distance_m is None


def test_upgrade_makes_distance_nullable() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE optimization_runs (id INTEGER PRIMARY KEY, scenario_id INTEGER, "
            "algorithm VARCHAR(20), status VARCHAR(20), total_distance_m FLOAT NOT NULL, "
            "created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO optimization_runs (scenario_id, algorithm, status, total_distance_m, created_at) "
            "VALUES (1, 'greedy', 'success', 12.5, '2026-11-01 10:00:00')"
        ))

    upgrade_legacy_optimization_run_schema(engine)

    columns = {column["name"]: column for column in inspect(engine).get_columns("optimization_runs")}
    assert columns["total_distance_m"]["nullable"] is True
    assert {"batch_id", "solve_ms", "message", "routes", "input_hash"} <= set(columns)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, total_distance_m FROM optimization_runs")
        ).one()
    assert tuple(row) == ("success", 12.5)


def test_grams_use_decimal_not_float() -> None:
    assert optimization.kg_to_g(Decimal("0.29")) == 290
    assert optimization.kg_to_g(1234.56) == 1234560


# --- API ---------------------------------------------------------------

SCENARIOS = "/api/v1/scenarios"


@pytest.fixture
def clean_roads(monkeypatch: pytest.MonkeyPatch, fake_roads: None) -> None:
    network = FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[]))
    monkeypatch.setattr("app.api.scenarios.get_road_network", lambda: network)


def optimize(client: TestClient, headers: dict[str, str], scenario_id: int):
    return client.post(f"{SCENARIOS}/{scenario_id}/optimize", headers=headers)


def test_optimize_requires_authentication(client: TestClient) -> None:
    assert client.post(f"{SCENARIOS}/1/optimize").status_code in (401, 403)


def test_optimize_refuses_an_invalid_scenario(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, clean_roads: None,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"], facility_capacity=100)

    response = optimize(client, auth_headers, scenario.id)

    assert response.status_code == 409
    report = response.json()["detail"]["report"]
    assert "FACILITY_CAPACITY" in {error["code"] for error in report["errors"]}
    assert saved(db_session) == []


def test_optimize_refuses_when_the_road_network_is_unavailable(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, fake_roads: None,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    response = optimize(client, auth_headers, scenario.id)

    assert response.status_code == 409
    assert response.json()["detail"]["report"]["validation_status"] == "incomplete"


def test_optimize_returns_both_methods(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, clean_roads: None,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    response = optimize(client, auth_headers, scenario.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["greedy"]["status"] == "feasible"
    assert body["or_tools"]["status"] == "feasible"
    assert body["or_tools"]["routes"][0]["geometry"]
    assert len(saved(db_session)) == 2


def test_difference_is_greedy_minus_or_tools(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, clean_roads: None,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    body = optimize(client, auth_headers, scenario.id).json()

    expected = body["greedy"]["total_distance_m"] - body["or_tools"]["total_distance_m"]
    assert body["difference_m"] == expected
    assert body["difference_pct"] == pytest.approx(
        expected / body["greedy"]["total_distance_m"] * 100, abs=0.01
    )


def test_difference_needs_both_feasible(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, clean_roads: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def crash(problem: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(optimization, "solve_greedy", crash)
    scenario = build_scenario(db_session, registered_user["email"])

    body = optimize(client, auth_headers, scenario.id).json()

    assert body["greedy"]["total_distance_m"] is None
    assert body["difference_m"] is None
    assert body["difference_pct"] is None


def test_another_coordinators_scenario_is_404(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, clean_roads: None,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])
    other = {"name": "Other", "email": "other@example.com", "password": "other-password-123"}
    client.post("/api/v1/auth/register", json=other)
    token = client.post(
        "/api/v1/auth/login", json={"email": other["email"], "password": other["password"]}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert optimize(client, headers, scenario.id).status_code == 404
    assert client.get(f"{SCENARIOS}/{scenario.id}/optimization", headers=headers).status_code == 404


def test_latest_optimization_returns_the_newest_batch(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session, clean_roads: None,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])
    optimize(client, auth_headers, scenario.id)
    newest = optimize(client, auth_headers, scenario.id).json()["batch_id"]

    response = client.get(f"{SCENARIOS}/{scenario.id}/optimization", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["batch_id"] == newest


def test_no_optimization_yet_is_404(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])

    response = client.get(f"{SCENARIOS}/{scenario.id}/optimization", headers=auth_headers)

    assert response.status_code == 404


def test_rows_without_a_batch_are_ignored(
    client: TestClient, auth_headers: dict[str, str], registered_user: dict[str, str],
    db_session: Session,
) -> None:
    scenario = build_scenario(db_session, registered_user["email"])
    db_session.add(OptimizationRun(
        scenario_id=scenario.id, algorithm="greedy", status="success", total_distance_m=5
    ))
    db_session.commit()

    response = client.get(f"{SCENARIOS}/{scenario.id}/optimization", headers=auth_headers)

    assert response.status_code == 404
