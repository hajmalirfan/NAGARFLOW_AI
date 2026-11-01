"""The availability-aware nearest-feasible baseline.

Each round takes the shortest feasible move across both vehicles. It never
looks ahead, so it can strand a point that some other assignment would have
served. That outcome is reported as ``no_solution``: construction failed,
which does not prove that no solution exists.
"""

import time as clock_time
from dataclasses import dataclass, field

from app.services.optimizer.types import (
    FEASIBLE,
    NO_SOLUTION,
    no_route_message,
    MethodResult,
    RoutingProblem,
    Stop,
    VehicleRoute,
)


@dataclass
class _Vehicle:
    vehicle_id: int
    capacity_g: int
    position: int = 0
    clock: int = 0
    load_g: int = 0
    distance_m: int = 0
    stops: list[Stop] = field(default_factory=list)


def _service_time(problem: RoutingProblem, vehicle: _Vehicle, point: int) -> int | None:
    """When this vehicle could serve this point, or ``None`` if it cannot."""
    if vehicle.load_g + problem.demand_g[point] > vehicle.capacity_g:
        return None
    travel = problem.time_s[vehicle.position][point]
    onward = problem.time_s[point][problem.facility]
    if travel is None or onward is None:
        return None
    service = max(vehicle.clock + travel, problem.ready_s[point])
    if problem.shift_end_s is not None and service + onward > problem.shift_end_s:
        return None
    return service


def _no_solution(started: float, message: str) -> MethodResult:
    return MethodResult(NO_SOLUTION, [], None, _elapsed_ms(started), message)


def _elapsed_ms(started: float) -> int:
    return round((clock_time.perf_counter() - started) * 1000)


def solve_greedy(problem: RoutingProblem) -> MethodResult:
    started = clock_time.perf_counter()
    if sum(problem.demand_g) > problem.facility_capacity_g:
        return _no_solution(started, "Total waste exceeds the shared facility capacity.")

    vehicles = [
        _Vehicle(vehicle_id, capacity)
        for vehicle_id, capacity in zip(problem.vehicle_ids, problem.capacity_g)
    ]
    remaining = list(problem.points)

    while remaining:
        best: tuple[int, str, int] | None = None
        move: tuple[_Vehicle, int, int] | None = None
        for vehicle in vehicles:
            for point in remaining:
                service = _service_time(problem, vehicle, point)
                if service is None:
                    continue
                key = (
                    problem.distance_m[vehicle.position][point],
                    problem.names[point],
                    vehicle.vehicle_id,
                )
                if best is None or key < best:
                    best, move = key, (vehicle, point, service)

        if move is None:
            stranded = ", ".join(problem.names[point] for point in remaining)
            return _no_solution(
                started, no_route_message(problem, f"No vehicle could take: {stranded}.")
            )

        vehicle, point, service = move
        arrival = vehicle.clock + problem.time_s[vehicle.position][point]
        vehicle.distance_m += problem.distance_m[vehicle.position][point]
        vehicle.load_g += problem.demand_g[point]
        vehicle.stops.append(Stop(problem.names[point], arrival, service, service - arrival))
        vehicle.position, vehicle.clock = point, service
        remaining.remove(point)

    routes = [
        VehicleRoute(
            vehicle_id=vehicle.vehicle_id,
            stops=vehicle.stops,
            load_g=vehicle.load_g,
            distance_m=vehicle.distance_m + problem.distance_m[vehicle.position][problem.facility],
            finish_s=vehicle.clock + problem.time_s[vehicle.position][problem.facility],
        )
        for vehicle in vehicles
        if vehicle.stops
    ]
    total = sum(route.distance_m for route in routes)
    return MethodResult(FEASIBLE, routes, total, _elapsed_ms(started), "")
