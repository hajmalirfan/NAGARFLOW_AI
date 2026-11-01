"""Google OR-Tools route optimization.

Guided local search stops at its time limit without proving the answer is
the best possible, so a found route is ``feasible`` ("best found"), never
``optimal``. No solution within the limit is ``timeout``, which is a
different claim from ``infeasible``.

Every point is mandatory, so no point is given a penalty to be dropped.
Waiting is the time dimension's slack (DEC-003).
"""

import time as clock_time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.services.optimizer.types import (
    FEASIBLE,
    INFEASIBLE,
    NO_SOLUTION,
    no_route_message,
    TIMEOUT,
    MethodResult,
    RoutingProblem,
    Stop,
    VehicleRoute,
)

STATUS_TIMEOUT = routing_enums_pb2.RoutingSearchStatus.ROUTING_FAIL_TIMEOUT
STATUS_INFEASIBLE = routing_enums_pb2.RoutingSearchStatus.ROUTING_INFEASIBLE


def _search(routing: pywrapcp.RoutingModel, parameters) -> tuple[object | None, int]:
    solution = routing.SolveWithParameters(parameters)
    return solution, routing.status()


def _horizon(problem: RoutingProblem) -> int:
    """The latest time a trip may end."""
    if problem.shift_end_s is not None:
        return problem.shift_end_s
    longest_leg = max(
        (time for row in problem.time_s for time in row if time is not None), default=0
    )
    return max(problem.ready_s) + longest_leg * len(problem.names)


def _route(problem: RoutingProblem, vehicle_id: int, visits: list[int]) -> VehicleRoute:
    """Lay out a visit order at its earliest times."""
    position, clock, distance, load = 0, 0, 0, 0
    stops: list[Stop] = []
    for point in visits:
        arrival = clock + problem.time_s[position][point]
        service = max(arrival, problem.ready_s[point])
        stops.append(Stop(problem.names[point], arrival, service, service - arrival))
        distance += problem.distance_m[position][point]
        load += problem.demand_g[point]
        position, clock = point, service
    return VehicleRoute(
        vehicle_id=vehicle_id,
        stops=stops,
        load_g=load,
        distance_m=distance + problem.distance_m[position][problem.facility],
        finish_s=clock + problem.time_s[position][problem.facility],
    )


def solve_ortools(problem: RoutingProblem, time_limit_s: int) -> MethodResult:
    started = clock_time.perf_counter()

    def elapsed_ms() -> int:
        return round((clock_time.perf_counter() - started) * 1000)

    if sum(problem.demand_g) > problem.facility_capacity_g:
        return MethodResult(
            INFEASIBLE, [], None, elapsed_ms(), "Total waste exceeds the shared facility capacity."
        )

    horizon = _horizon(problem)
    if max(problem.ready_s) > horizon:
        return MethodResult(
            INFEASIBLE, [], None, elapsed_ms(), "Some waste is not available before the shift ends."
        )

    size = len(problem.names)
    vehicles = len(problem.vehicle_ids)
    manager = pywrapcp.RoutingIndexManager(size, vehicles, [0] * vehicles, [size - 1] * vehicles)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        cost = problem.distance_m[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
        return 0 if cost is None else cost

    def time_callback(from_index: int, to_index: int) -> int:
        cost = problem.time_s[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
        return 0 if cost is None else cost

    def demand_callback(from_index: int) -> int:
        return problem.demand_g[manager.IndexToNode(from_index)]

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance_callback))
    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(demand_callback),
        0,
        problem.capacity_g,
        True,
        "load",
    )
    routing.AddDimension(
        routing.RegisterTransitCallback(time_callback), horizon, horizon, True, "time"
    )
    time_dimension = routing.GetDimensionOrDie("time")
    for point in problem.points:
        time_dimension.CumulVar(manager.NodeToIndex(point)).SetMin(problem.ready_s[point])

    # A pair with no road is removed outright, because a cost could only
    # discourage it. The depot-to-facility pair stays: it means an unused vehicle.
    for from_index in range(routing.Size()):
        for to_index in range(routing.Size() + vehicles):
            first = manager.IndexToNode(from_index)
            second = manager.IndexToNode(to_index)
            if first != second and problem.distance_m[first][second] is None:
                routing.NextVar(from_index).RemoveValue(to_index)

    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    parameters.time_limit.FromSeconds(time_limit_s)

    solution, status = _search(routing, parameters)

    if solution is None:
        if status == STATUS_TIMEOUT:
            return MethodResult(
                TIMEOUT, [], None, elapsed_ms(),
                f"No route was found within {time_limit_s} seconds.",
            )
        if status == STATUS_INFEASIBLE:
            return MethodResult(
                INFEASIBLE, [], None, elapsed_ms(), "No route can satisfy every constraint."
            )
        return MethodResult(
            NO_SOLUTION, [], None, elapsed_ms(),
            no_route_message(problem, "The solver found no route."),
        )

    routes: list[VehicleRoute] = []
    for vehicle, vehicle_id in enumerate(problem.vehicle_ids):
        visits: list[int] = []
        index = solution.Value(routing.NextVar(routing.Start(vehicle)))
        while not routing.IsEnd(index):
            visits.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        if visits:
            routes.append(_route(problem, vehicle_id, visits))

    total = sum(route.distance_m for route in routes)
    return MethodResult(FEASIBLE, routes, total, elapsed_ms(), "")
