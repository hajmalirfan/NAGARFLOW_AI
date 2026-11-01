"""The problem and result shapes shared by both algorithms.

Nothing here knows about the database or the road file, so each solver can
be tested on its own and neither can see anything the other cannot.
"""

from dataclasses import dataclass

FEASIBLE = "feasible"
OPTIMAL = "optimal"
NO_SOLUTION = "no_solution"
INFEASIBLE = "infeasible"
TIMEOUT = "timeout"
INVALID_RESULT = "invalid_result"

HAS_ROUTES = (FEASIBLE, OPTIMAL)


@dataclass
class RoutingProblem:
    """One scenario, as both algorithms see it.

    Index 0 of every location list is the depot, the last index is the
    facility, and storage points lie between in ascending code order.
    Demand and capacity are whole grams, so no load depends on float
    rounding. Times count seconds from the trip clock's zero.
    """

    names: list[str]
    demand_g: list[int]
    ready_s: list[int]
    vehicle_ids: list[int]
    capacity_g: list[int]
    facility_capacity_g: int
    distance_m: list[list[int | None]]
    time_s: list[list[int | None]]
    shift_end_s: int | None

    @property
    def facility(self) -> int:
        return len(self.names) - 1

    @property
    def points(self) -> range:
        return range(1, self.facility)


@dataclass
class Stop:
    code: str
    arrival_s: int
    service_s: int
    wait_s: int


@dataclass
class VehicleRoute:
    vehicle_id: int
    stops: list[Stop]
    load_g: int
    distance_m: int
    finish_s: int


def no_route_message(problem: RoutingProblem, base: str) -> str:
    """``base``, plus the likeliest cause when a shift limits the routes."""
    if problem.shift_end_s is None:
        return base
    return f"{base} Check the shift length and the waste availability times."


@dataclass
class MethodResult:
    status: str
    routes: list[VehicleRoute]
    total_distance_m: int | None
    solve_ms: int
    message: str
