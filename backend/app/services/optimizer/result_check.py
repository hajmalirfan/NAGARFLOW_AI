"""The independent check every algorithm's result must pass.

It recomputes each route from the cost matrix and trusts nothing a solver
reports, so neither algorithm marks its own work and both are held to
exactly the same hard constraints.
"""

from collections import Counter

from app.services.optimizer.types import HAS_ROUTES, MethodResult, RoutingProblem, VehicleRoute


def _check_route(problem: RoutingProblem, route: VehicleRoute, issues: list[str]) -> int:
    """Check one route, adding any problems. Returns its true distance."""
    label = f"Vehicle {route.vehicle_id}"
    index_of = {name: index for index, name in enumerate(problem.names)}

    if route.vehicle_id not in problem.vehicle_ids:
        issues.append(f"{label} is not in this scenario.")
        return 0
    capacity = problem.capacity_g[problem.vehicle_ids.index(route.vehicle_id)]

    position = 0
    clock = 0
    distance = 0
    load = 0
    for stop in route.stops:
        target = index_of.get(stop.code)
        if target is None or target not in problem.points:
            issues.append(f"{label} visits unknown stop {stop.code}.")
            continue
        leg = problem.distance_m[position][target]
        time = problem.time_s[position][target]
        if leg is None or time is None:
            issues.append(f"{label} has no road from {problem.names[position]} to {stop.code}.")
            return distance
        distance += leg
        arrival = clock + time
        service = max(arrival, problem.ready_s[target])
        if (stop.arrival_s, stop.service_s) != (arrival, service):
            issues.append(f"{label} reports the wrong times at {stop.code}.")
        if stop.service_s < problem.ready_s[target]:
            issues.append(f"{label} collects at {stop.code} before its waste is available.")
        load += problem.demand_g[target]
        position, clock = target, service

    leg = problem.distance_m[position][problem.facility]
    time = problem.time_s[position][problem.facility]
    if leg is None or time is None:
        issues.append(f"{label} has no road to the facility.")
        return distance
    distance += leg
    finish = clock + time

    if load > capacity:
        issues.append(f"{label} carries {load} g over its {capacity} g capacity.")
    if load != route.load_g:
        issues.append(f"{label} reports the wrong load.")
    if distance != route.distance_m:
        issues.append(f"{label} reports the wrong distance.")
    if finish != route.finish_s:
        issues.append(f"{label} reports the wrong finish time.")
    if problem.shift_end_s is not None and finish > problem.shift_end_s:
        issues.append(f"{label} finishes after the shift ends.")
    return distance


def check_result(problem: RoutingProblem, result: MethodResult) -> list[str]:
    """Every way this result breaks a hard constraint. Empty means it is sound."""
    if result.status not in HAS_ROUTES:
        return []

    issues: list[str] = []
    total = sum(_check_route(problem, route, issues) for route in result.routes)

    visits = Counter(stop.code for route in result.routes for stop in route.stops)
    for index in problem.points:
        count = visits[problem.names[index]]
        if count != 1:
            issues.append(f"{problem.names[index]} is visited {count} times, not once.")

    vehicles = Counter(route.vehicle_id for route in result.routes)
    issues.extend(f"Vehicle {vid} makes more than one trip." for vid, n in vehicles.items() if n > 1)

    delivered = sum(problem.demand_g[index] for index in problem.points)
    if delivered > problem.facility_capacity_g:
        issues.append("The combined delivery exceeds the shared facility capacity.")
    if total != result.total_distance_m:
        issues.append("The reported total distance does not match the routes.")
    return issues
