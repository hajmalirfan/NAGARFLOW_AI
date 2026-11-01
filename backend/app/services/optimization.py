"""Runs both algorithms on one scenario and saves what happened.

The two methods share one cost matrix and one ``RoutingProblem``, and the
hash of that problem is saved on both rows, so a comparison can show it
compared like with like. Every result passes through the independent
checker before it is saved.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.models.optimization_run import ALGORITHM_GREEDY, ALGORITHM_OR_TOOLS, OptimizationRun
from app.models.scenario import Scenario
from app.services.optimizer.greedy import solve_greedy
from app.services.optimizer.ortools_solver import solve_ortools
from app.services.optimizer.result_check import check_result
from app.services.optimizer.types import (
    HAS_ROUTES,
    INVALID_RESULT,
    NO_SOLUTION,
    MethodResult,
    RoutingProblem,
    VehicleRoute,
)
from app.services.road_costs import CostMatrix, build_cost_matrix, route_geometry
from app.services.validation import (
    RoadLocation,
    _scenario_depot,
    _scenario_facility,
    _scenario_points,
    _scenario_vehicles,
)

logger = logging.getLogger(__name__)

GRAMS_PER_KG = 1000


def kg_to_g(value: Decimal | float) -> int:
    """Whole grams, through ``Decimal`` so a load never depends on float rounding."""
    return int(Decimal(str(value)) * GRAMS_PER_KG)


def _sorted_points(scenario: Scenario) -> list:
    return sorted(_scenario_points(scenario), key=lambda point: point.point_code)


def _sorted_vehicles(scenario: Scenario) -> list:
    return sorted(_scenario_vehicles(scenario), key=lambda vehicle: vehicle.id)


def scenario_locations(scenario: Scenario) -> list[RoadLocation]:
    """Depot, then points by code, then facility."""
    depot = _scenario_depot(scenario)
    facility = _scenario_facility(scenario)
    return [
        RoadLocation(depot.code or depot.name, depot.latitude, depot.longitude),
        *(
            RoadLocation(point.point_code, point.latitude, point.longitude)
            for point in _sorted_points(scenario)
        ),
        RoadLocation(facility.facility_code, facility.latitude, facility.longitude),
    ]


def clock_zero(scenario: Scenario) -> datetime:
    """The moment vehicles leave the depot."""
    if scenario.shift_start is not None:
        return scenario.shift_start
    ready = [
        point.available_from for point in _scenario_points(scenario)
        if point.available_from is not None
    ]
    if ready:
        return min(ready)
    return utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def build_problem(scenario: Scenario, matrix: CostMatrix) -> RoutingProblem:
    zero = clock_zero(scenario)

    def seconds_after_zero(moment: datetime | None) -> int:
        if moment is None:
            return 0
        return max(0, round((moment - zero).total_seconds()))

    points = _sorted_points(scenario)
    vehicles = _sorted_vehicles(scenario)
    return RoutingProblem(
        names=matrix.names,
        demand_g=[0, *(kg_to_g(point.waste_kg) for point in points), 0],
        ready_s=[0, *(seconds_after_zero(point.available_from) for point in points), 0],
        vehicle_ids=[vehicle.id for vehicle in vehicles],
        capacity_g=[kg_to_g(vehicle.capacity_kg) for vehicle in vehicles],
        facility_capacity_g=kg_to_g(_scenario_facility(scenario).capacity_kg),
        distance_m=matrix.distance_m,
        time_s=matrix.time_s,
        shift_end_s=(
            None if scenario.shift_end is None else seconds_after_zero(scenario.shift_end)
        ),
    )


def problem_hash(problem: RoutingProblem) -> str:
    canonical = json.dumps(asdict(problem), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def run_method(
    solver: Callable[[RoutingProblem], MethodResult], problem: RoutingProblem
) -> MethodResult:
    """Run one algorithm. A crash or an unsound result never reaches the user as a route."""
    try:
        result = solver(problem)
    except Exception:
        logger.exception("Optimization algorithm failed.")
        return MethodResult(NO_SOLUTION, [], None, 0, "The algorithm failed unexpectedly.")

    issues = check_result(problem, result)
    if issues:
        logger.error("Result failed the independent check: %s", issues)
        return MethodResult(
            INVALID_RESULT, [], None, result.solve_ms,
            "The result failed the independent constraint check.",
        )
    return result


def _route_json(
    scenario: Scenario,
    route: VehicleRoute,
    locations: dict[str, RoadLocation],
    start: RoadLocation,
    end: RoadLocation,
    network: object,
) -> dict:
    vehicle = next(v for v in _scenario_vehicles(scenario) if v.id == route.vehicle_id)
    path = [start, *(locations[stop.code] for stop in route.stops), end]
    geometry: list[tuple[float, float]] = []
    for source, target in zip(path, path[1:]):
        geometry.extend(route_geometry(network, source, target))
    stops = []
    for stop in route.stops:
        location = locations[stop.code]
        stops.append({**asdict(stop), "latitude": location.latitude, "longitude": location.longitude})
    return {
        "vehicle_id": route.vehicle_id,
        "vehicle_name": vehicle.name,
        "capacity_kg": float(vehicle.capacity_kg),
        "load_kg": route.load_g / GRAMS_PER_KG,
        "distance_m": route.distance_m,
        "finish_s": route.finish_s,
        "stops": stops,
        "geometry": [list(point) for point in geometry],
    }


def optimize_scenario(
    db: Session, scenario: Scenario, network: object
) -> list[OptimizationRun]:
    """Run Greedy and OR-Tools on identical inputs and save both."""
    locations = scenario_locations(scenario)
    problem = build_problem(scenario, build_cost_matrix(network, locations))
    points_by_code = {location.name: location for location in locations[1:-1]}
    input_hash = problem_hash(problem)
    batch_id = uuid.uuid4().hex

    methods = (
        (ALGORITHM_GREEDY, solve_greedy),
        (
            ALGORITHM_OR_TOOLS,
            lambda p: solve_ortools(p, settings.optimizer_time_limit_s),
        ),
    )

    runs: list[OptimizationRun] = []
    for algorithm, solver in methods:
        result = run_method(solver, problem)
        routes = [
            _route_json(scenario, route, points_by_code, locations[0], locations[-1], network)
            for route in result.routes
        ]
        run = OptimizationRun(
            scenario_id=scenario.id,
            algorithm=algorithm,
            status=result.status,
            total_distance_m=result.total_distance_m if result.status in HAS_ROUTES else None,
            batch_id=batch_id,
            solve_ms=result.solve_ms,
            message=result.message,
            routes=routes,
            input_hash=input_hash,
        )
        db.add(run)
        runs.append(run)
    db.commit()
    return runs
