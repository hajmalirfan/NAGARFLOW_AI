"""Solver and result checker tests.

Roads here are a straight line: a location's position is its distance in
metres from zero, and each metre takes one second, so every expected figure
can be checked by eye.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.services.optimizer import ortools_solver
from app.services.optimizer.greedy import solve_greedy
from app.services.optimizer.ortools_solver import solve_ortools
from app.services.optimizer.result_check import check_result
from app.services.optimizer.types import MethodResult, RoutingProblem, Stop, VehicleRoute


def problem_from(
    positions: list[int],
    demands: list[int],
    capacities: tuple[int, ...] = (100, 100),
    *,
    ready: list[int] | None = None,
    shift_end_s: int | None = None,
    facility_capacity_g: int = 10_000,
    blocked: tuple[tuple[int, int], ...] = (),
) -> RoutingProblem:
    """``positions`` run depot, points, facility; the rest are per point."""
    size = len(positions)
    matrix: list[list[int | None]] = [
        [abs(a - b) for b in positions] for a in positions
    ]
    for first, second in blocked:
        matrix[first][second] = None
    names = ["DEP", *[f"P{i}" for i in range(1, size - 1)], "FAC"]
    return RoutingProblem(
        names=names,
        demand_g=[0, *demands, 0],
        ready_s=[0, *(ready or [0] * len(demands)), 0],
        vehicle_ids=[index + 1 for index in range(len(capacities))],
        capacity_g=list(capacities),
        facility_capacity_g=facility_capacity_g,
        distance_m=matrix,
        time_s=[list(row) for row in matrix],
        shift_end_s=shift_end_s,
    )


def correct_result() -> tuple[RoutingProblem, MethodResult]:
    problem = problem_from([0, 10, 20, 30], [5, 5])
    route = VehicleRoute(
        vehicle_id=1,
        stops=[Stop("P1", 10, 10, 0), Stop("P2", 20, 20, 0)],
        load_g=10,
        distance_m=30,
        finish_s=30,
    )
    return problem, MethodResult("feasible", [route], 30, 1, "")


def codes(result: MethodResult) -> list[list[str]]:
    return [[stop.code for stop in route.stops] for route in result.routes]


# --- Checker -----------------------------------------------------------


def test_checker_accepts_a_correct_result() -> None:
    problem, result = correct_result()

    assert check_result(problem, result) == []


def test_checker_rejects_a_missing_point() -> None:
    problem, result = correct_result()
    route = replace(result.routes[0], stops=result.routes[0].stops[:1], load_g=5)

    assert check_result(problem, replace(result, routes=[route]))


def test_checker_rejects_a_duplicate_point() -> None:
    problem, result = correct_result()
    stops = [*result.routes[0].stops, Stop("P2", 20, 20, 0)]
    route = replace(result.routes[0], stops=stops)

    assert check_result(problem, replace(result, routes=[route]))


def test_checker_rejects_an_overloaded_vehicle() -> None:
    problem, result = correct_result()

    assert check_result(replace(problem, capacity_g=[9, 9]), result)


def test_checker_rejects_a_combined_load_over_facility_capacity() -> None:
    problem, result = correct_result()

    assert check_result(replace(problem, facility_capacity_g=9), result)


def test_checker_rejects_service_before_ready() -> None:
    problem, result = correct_result()

    assert check_result(replace(problem, ready_s=[0, 15, 0, 0]), result)


def test_checker_rejects_a_wrong_distance() -> None:
    problem, result = correct_result()

    assert check_result(problem, replace(result, total_distance_m=29))


def test_checker_rejects_a_finish_after_shift() -> None:
    problem, result = correct_result()

    assert check_result(replace(problem, shift_end_s=29), result)


def test_checker_rejects_a_leg_with_no_path() -> None:
    problem, result = correct_result()
    distance = [list(row) for row in problem.distance_m]
    distance[1][2] = None

    assert check_result(replace(problem, distance_m=distance), result)


def test_checker_ignores_a_result_with_no_routes_to_check() -> None:
    problem, _ = correct_result()

    assert check_result(problem, MethodResult("no_solution", [], None, 1, "stuck")) == []


# --- Greedy ------------------------------------------------------------


def test_greedy_serves_every_point_once() -> None:
    problem = problem_from([0, 10, 20, 30, 40], [5, 5, 5])

    result = solve_greedy(problem)

    assert result.status == "feasible"
    assert sorted(code for route in codes(result) for code in route) == ["P1", "P2", "P3"]
    assert check_result(problem, result) == []


def test_greedy_takes_the_nearest_feasible_pair() -> None:
    problem = problem_from([0, 30, 10, 40], [5, 5])

    result = solve_greedy(problem)

    assert codes(result) == [["P2", "P1"]]


def test_greedy_ties_go_to_lower_code_then_vehicle() -> None:
    problem = problem_from([10, 0, 20, 30], [5, 5])

    result = solve_greedy(problem)

    assert codes(result)[0][0] == "P1"
    assert result.routes[0].vehicle_id == 1


def test_greedy_waits_without_adding_distance() -> None:
    problem = problem_from([0, 10, 20], [5], ready=[100])

    result = solve_greedy(problem)

    assert result.total_distance_m == 20
    stop = result.routes[0].stops[0]
    assert (stop.arrival_s, stop.service_s, stop.wait_s) == (10, 100, 90)
    assert result.routes[0].finish_s == 110


def test_greedy_stops_at_shift_end() -> None:
    problem = problem_from([0, 10, 20], [5], ready=[100], shift_end_s=50)

    result = solve_greedy(problem)

    assert result.status == "no_solution"
    assert result.total_distance_m is None
    assert result.routes == []


def test_greedy_strands_a_point_after_a_bad_choice() -> None:
    problem = problem_from([0, 1, 2, 50, 60], [2, 2, 5], capacities=(6, 4))

    result = solve_greedy(problem)

    assert result.status == "no_solution"
    assert result.total_distance_m is None
    assert "P3" in result.message


def test_greedy_visits_a_zero_waste_point() -> None:
    problem = problem_from([0, 10, 20], [0])

    assert codes(solve_greedy(problem)) == [["P1"]]


def test_greedy_handles_a_zero_metre_leg() -> None:
    problem = problem_from([0, 10, 10, 20], [5, 5])

    result = solve_greedy(problem)

    assert result.status == "feasible"
    assert result.total_distance_m == 20


def test_greedy_refuses_a_total_over_facility_capacity() -> None:
    problem = problem_from([0, 10, 20], [50], facility_capacity_g=40)

    assert solve_greedy(problem).status == "no_solution"


def test_greedy_avoids_a_leg_with_no_path() -> None:
    problem = problem_from([0, 10, 20, 30], [5, 5], blocked=((1, 2),))

    result = solve_greedy(problem)

    assert result.status == "feasible"
    assert check_result(problem, result) == []


# --- OR-Tools ----------------------------------------------------------

LIMIT_S = 1


def short_sighted() -> RoutingProblem:
    """Depot at 10 and facility at 0. Greedy splits the work: 40 m against 30 m."""
    return problem_from([10, 9, 20, 0], [5, 5])


def test_greedy_is_short_sighted_on_the_fixture() -> None:
    assert solve_greedy(short_sighted()).total_distance_m == 40


def test_ortools_beats_greedy_where_greedy_is_short_sighted() -> None:
    assert solve_ortools(short_sighted(), LIMIT_S).total_distance_m == 30


def test_ortools_says_feasible_not_optimal() -> None:
    assert solve_ortools(short_sighted(), LIMIT_S).status == "feasible"


def test_ortools_serves_every_point() -> None:
    result = solve_ortools(problem_from([0, 10, 20, 30, 40], [5, 5, 5]), LIMIT_S)

    assert sorted(code for route in codes(result) for code in route) == ["P1", "P2", "P3"]


def test_ortools_respects_capacity() -> None:
    result = solve_ortools(problem_from([0, 10, 20, 30], [6, 6], capacities=(10, 10)), LIMIT_S)

    assert len(result.routes) == 2
    assert all(route.load_g <= 10 for route in result.routes)


def test_ortools_fits_a_load_exactly_at_capacity() -> None:
    grams = int(Decimal("1234.56") * 1000)
    problem = problem_from([0, 10, 20], [grams], capacities=(grams, 1), facility_capacity_g=grams)

    assert solve_ortools(problem, LIMIT_S).status == "feasible"


def test_ortools_leaves_a_vehicle_unused_when_shorter() -> None:
    assert len(solve_ortools(short_sighted(), LIMIT_S).routes) == 1


def test_ortools_waits_for_late_waste() -> None:
    result = solve_ortools(problem_from([0, 10, 20], [5], ready=[100]), LIMIT_S)

    assert result.total_distance_m == 20
    stop = result.routes[0].stops[0]
    assert (stop.arrival_s, stop.service_s, stop.wait_s) == (10, 100, 90)


def test_ortools_enforces_shift_end() -> None:
    problem = problem_from([0, 10, 20], [5], ready=[100], shift_end_s=50)

    result = solve_ortools(problem, LIMIT_S)

    assert result.status in ("infeasible", "no_solution")
    assert result.total_distance_m is None
    assert result.routes == []


def test_ortools_reports_impossible_capacity_as_not_feasible() -> None:
    problem = problem_from([0, 10, 20], [50], capacities=(10, 10))

    result = solve_ortools(problem, LIMIT_S)

    assert result.status in ("infeasible", "no_solution")
    assert result.total_distance_m is None


def test_ortools_refuses_a_total_over_facility_capacity() -> None:
    problem = problem_from([0, 10, 20], [50], facility_capacity_g=40)

    assert solve_ortools(problem, LIMIT_S).status == "infeasible"


def test_ortools_avoids_a_leg_with_no_path() -> None:
    problem = problem_from([0, 10, 20, 30], [5, 5], capacities=(10, 10), blocked=((1, 2),))

    result = solve_ortools(problem, LIMIT_S)

    assert result.status == "feasible"
    assert check_result(problem, result) == []


def test_ortools_timeout_has_no_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ortools_solver, "_search",
        lambda routing, parameters: (None, ortools_solver.STATUS_TIMEOUT),
    )

    result = solve_ortools(short_sighted(), LIMIT_S)

    assert result.status == "timeout"
    assert result.total_distance_m is None
    assert result.routes == []


def test_ortools_visits_a_zero_waste_point() -> None:
    assert codes(solve_ortools(problem_from([0, 10, 20], [0]), LIMIT_S)) == [["P1"]]


def test_every_ortools_result_passes_the_checker() -> None:
    problem = problem_from(
        [0, 40, 10, 30, 20, 50], [5, 5, 5, 5], capacities=(10, 10), ready=[0, 60, 0, 0]
    )

    assert check_result(problem, solve_ortools(problem, LIMIT_S)) == []
