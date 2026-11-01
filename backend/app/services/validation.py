"""The scenario validation engine.

This is the gate in front of the optimization algorithms. Both Greedy and
OR-Tools must honour exactly the hard constraints checked here, so the
rules live in one place rather than being restated per algorithm.

Two points are easy to get wrong and are handled explicitly:

* A storage point is never split. Its whole quantity rides in one
  vehicle, so the largest point must fit a single vehicle.
* Passing the combined-capacity check does not mean a valid assignment
  exists. Three 3,000 kg points fit two vehicles of 5,000 and 4,000 by
  total, yet no split of whole points works. ``_find_assignment`` decides
  this exactly rather than assuming.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.depot import Depot
from app.models.processing_facility import ProcessingFacility
from app.models.scenario import Scenario
from app.models.scenario_validation import ScenarioValidation
from app.models.storage_point import StoragePoint
from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

PASSED = "passed"
FAILED = "failed"
NOT_CHECKED = "not_checked"

STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
# Every implementable hard constraint passed, but at least one required
# check could not run yet, so the scenario must not be called valid.
STATUS_INCOMPLETE = "incomplete"

CHECK_ORDER = (
    "depot",
    "vehicles",
    "storage_points",
    "facility",
    "waste_quantity",
    "vehicle_capacity",
    "combined_capacity",
    "facility_capacity",
    "coordinates",
    "availability",
    "vehicle_assignment",
    "road_connectivity",
)

MIN_STORAGE_POINTS = 6
MAX_STORAGE_POINTS = 10
REQUIRED_VEHICLES = 2


MAX_LISTED_ROUTES = 5

ROAD_NETWORK_NOT_CONFIGURED_WARNING = {
    "code": "ROAD_NETWORK_NOT_CONFIGURED",
    "message": (
        "Road connectivity has not been checked because no road network is "
        "configured. A scenario is not marked valid until connectivity is "
        "verified."
    ),
}


@dataclass(frozen=True)
class RoadLocation:
    name: str
    latitude: float
    longitude: float


@dataclass
class RoadCheckResult:
    """Why a scenario's trip cannot be driven, if it cannot.

    ``too_far`` names locations beyond the snap limit from any road, and
    ``unreachable`` lists failed required routes as ``"A → B"``.
    """

    too_far: list[str]
    unreachable: list[str]


class RoadNetwork(Protocol):
    """Supplies road reachability between the scenario's locations.

    ``check`` returns ``None`` when no road network is available to answer
    the question.
    """

    def check(
        self, depot: RoadLocation, points: list[RoadLocation], facility: RoadLocation
    ) -> RoadCheckResult | None: ...


class NullRoadNetwork:
    """Stands in whenever no usable road network is available.

    It answers ``None``: not "everything is reachable", but "this cannot
    be determined". The engine then refuses to call the scenario valid,
    instead of assuming connectivity it has not verified. ``warning`` says
    why the check could not run.
    """

    def __init__(self, warning: dict[str, str] = ROAD_NETWORK_NOT_CONFIGURED_WARNING) -> None:
        self.warning = warning

    def check(
        self, depot: RoadLocation, points: list[RoadLocation], facility: RoadLocation
    ) -> RoadCheckResult | None:
        return None


@dataclass
class VehicleLoad:
    vehicle_id: int
    name: str
    capacity_kg: Decimal
    assigned_point_codes: list[str]
    assigned_kg: Decimal


@dataclass
class ValidationReport:
    scenario_id: int
    validation_status: str
    can_optimize: bool
    checks: dict[str, str]
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    total_waste_kg: Decimal = Decimal("0")
    storage_point_count: int = 0
    feasible_assignment: list[VehicleLoad] | None = None


def _is_valid_latitude(value: float | None) -> bool:
    return value is not None and -90 <= value <= 90


def _is_valid_longitude(value: float | None) -> bool:
    return value is not None and -180 <= value <= 180


def _scenario_vehicles(scenario: Scenario) -> list[Vehicle]:
    return list({v.id: v for v in (*scenario.selected_vehicles, *scenario.vehicles)}.values())


def _scenario_points(scenario: Scenario) -> list[StoragePoint]:
    points = {
        p.id: p for p in (*scenario.selected_storage_points, *scenario.storage_points)
    }.values()
    return sorted(points, key=lambda point: point.id)


def _scenario_facility(scenario: Scenario) -> ProcessingFacility | None:
    if scenario.processing_facility is not None:
        return scenario.processing_facility
    return scenario.facilities[0] if scenario.facilities else None


def _scenario_depot(scenario: Scenario) -> Depot | None:
    return scenario.depot


def _find_assignment(
    points: list[StoragePoint], vehicles: list[Vehicle]
) -> list[VehicleLoad] | None:
    """Split whole storage points between two vehicles, or report that no split works.

    With at most ten points there are fewer than 1,024 subsets, so every
    candidate is examined. The answer is exact: a ``None`` result means no
    assignment exists, not that the search gave up.
    """
    if len(vehicles) != REQUIRED_VEHICLES:
        return None

    first, second = vehicles
    first_capacity = Decimal(str(first.capacity_kg))
    second_capacity = Decimal(str(second.capacity_kg))
    quantities = [Decimal(str(point.waste_kg)) for point in points]
    indices = range(len(points))

    # Every subset size from empty to the full set, so no candidate split
    # is missed.
    for size in range(len(points) + 1):
        for subset in combinations(indices, size):
            chosen = set(subset)
            first_load = sum((quantities[i] for i in chosen), Decimal("0"))
            if first_load > first_capacity:
                continue
            remaining = [i for i in indices if i not in chosen]
            second_load = sum((quantities[i] for i in remaining), Decimal("0"))
            if second_load > second_capacity:
                continue
            return [
                VehicleLoad(
                    vehicle_id=first.id,
                    name=first.name,
                    capacity_kg=first_capacity,
                    assigned_point_codes=[points[i].point_code for i in sorted(chosen)],
                    assigned_kg=first_load,
                ),
                VehicleLoad(
                    vehicle_id=second.id,
                    name=second.name,
                    capacity_kg=second_capacity,
                    assigned_point_codes=[points[i].point_code for i in remaining],
                    assigned_kg=second_load,
                ),
            ]
    return None


def validate_scenario(
    db: Session, scenario: Scenario, road_network: RoadNetwork | None = None
) -> ValidationReport:
    """Run every hard constraint, in the documented order."""
    network = road_network or NullRoadNetwork()
    checks: dict[str, str] = {name: NOT_CHECKED for name in CHECK_ORDER}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def fail(check: str, code: str, message: str) -> None:
        checks[check] = FAILED
        errors.append({"code": code, "message": message})

    depot = _scenario_depot(scenario)
    vehicles = _scenario_vehicles(scenario)
    points = _scenario_points(scenario)
    facility = _scenario_facility(scenario)

    total_waste = sum((Decimal(str(point.waste_kg)) for point in points), Decimal("0"))

    # Rule 1 - exactly one valid depot.
    if depot is None:
        fail("depot", "DEPOT_MISSING", "The scenario has no depot configured.")
    elif not depot.is_active:
        fail(
            "depot",
            "DEPOT_INACTIVE",
            f"Depot {depot.code or depot.name} is inactive and cannot be used.",
        )
    elif not _is_valid_latitude(depot.latitude) or not _is_valid_longitude(depot.longitude):
        fail(
            "depot",
            "DEPOT_COORDINATES",
            f"Depot {depot.code or depot.name} does not have valid coordinates.",
        )
    else:
        checks["depot"] = PASSED

    # Rule 2 - exactly two active vehicles.
    if len(vehicles) != REQUIRED_VEHICLES:
        fail(
            "vehicles",
            "VEHICLE_COUNT",
            f"The scenario needs exactly {REQUIRED_VEHICLES} vehicles but has {len(vehicles)}.",
        )
    else:
        inactive = [
            vehicle for vehicle in vehicles
            if not vehicle.is_available or vehicle.status != "available"
        ]
        if inactive:
            names = ", ".join(v.vehicle_number or v.name for v in inactive)
            fail("vehicles", "VEHICLE_INACTIVE", f"These vehicles are not active: {names}.")
        else:
            checks["vehicles"] = PASSED

    # Rule 3 - between six and ten storage points.
    if not MIN_STORAGE_POINTS <= len(points) <= MAX_STORAGE_POINTS:
        fail(
            "storage_points",
            "STORAGE_POINT_COUNT",
            f"The scenario needs between {MIN_STORAGE_POINTS} and {MAX_STORAGE_POINTS} "
            f"storage points but has {len(points)}.",
        )
    else:
        checks["storage_points"] = PASSED

    # Rule 4 - exactly one active facility.
    if facility is None:
        fail("facility", "FACILITY_MISSING", "The scenario has no processing facility.")
    elif facility.status != "active":
        fail(
            "facility",
            "FACILITY_INACTIVE",
            f"Processing facility {facility.facility_code} is inactive.",
        )
    else:
        checks["facility"] = PASSED

    # Rule 5 - no negative waste quantity.
    negative = [point for point in points if Decimal(str(point.waste_kg)) < 0]
    if negative:
        codes = ", ".join(point.point_code for point in negative)
        fail(
            "waste_quantity",
            "WASTE_QUANTITY_NEGATIVE",
            f"These storage points have a negative waste quantity: {codes}.",
        )
    else:
        checks["waste_quantity"] = PASSED

    # Rule 6 - every whole storage point must fit one vehicle.
    if vehicles and checks["waste_quantity"] == PASSED:
        largest_vehicle = max(Decimal(str(v.capacity_kg)) for v in vehicles)
        oversized = [
            point for point in points
            if Decimal(str(point.waste_kg)) > largest_vehicle
        ]
        if oversized:
            for point in oversized:
                errors.append({
                    "code": "STORAGE_POINT_CAPACITY",
                    "message": (
                        f"Storage point {point.point_code} holds {point.waste_kg} kg and "
                        f"cannot fit into either vehicle. Waste is never split between "
                        f"vehicles."
                    ),
                })
            checks["vehicle_capacity"] = FAILED
        else:
            checks["vehicle_capacity"] = PASSED

    # Rule 7 - combined vehicle capacity.
    if len(vehicles) == REQUIRED_VEHICLES and checks["waste_quantity"] == PASSED:
        combined = sum((Decimal(str(v.capacity_kg)) for v in vehicles), Decimal("0"))
        if total_waste > combined:
            fail(
                "combined_capacity",
                "COMBINED_CAPACITY",
                f"Total waste of {total_waste} kg exceeds the combined vehicle "
                f"capacity of {combined} kg.",
            )
        else:
            checks["combined_capacity"] = PASSED

    # Rule 8 - shared facility capacity.
    if facility is not None and checks["waste_quantity"] == PASSED:
        facility_capacity = Decimal(str(facility.capacity_kg))
        if total_waste > facility_capacity:
            fail(
                "facility_capacity",
                "FACILITY_CAPACITY",
                f"Total waste of {total_waste} kg exceeds the shared facility "
                f"capacity of {facility_capacity} kg.",
            )
        else:
            checks["facility_capacity"] = PASSED

    # Rule 9 - valid coordinates everywhere.
    bad_coordinates = [
        point.point_code for point in points
        if not _is_valid_latitude(point.latitude) or not _is_valid_longitude(point.longitude)
    ]
    if facility is not None and (
        not _is_valid_latitude(facility.latitude)
        or not _is_valid_longitude(facility.longitude)
    ):
        bad_coordinates.append(facility.facility_code)
    if depot is not None and (
        not _is_valid_latitude(depot.latitude) or not _is_valid_longitude(depot.longitude)
    ):
        bad_coordinates.append(depot.code or depot.name)
    if bad_coordinates:
        fail(
            "coordinates",
            "INVALID_COORDINATES",
            f"These locations do not have valid coordinates: {', '.join(bad_coordinates)}.",
        )
    else:
        checks["coordinates"] = PASSED

    # DEC-003: a vehicle waits for waste, so only a shift can make waste too
    # late. A point ready before the shift starts is simply ready at once.
    shift_end = scenario.shift_end
    too_late = [
        point.point_code for point in points
        if shift_end is not None
        and point.available_from is not None
        and point.available_from > shift_end
    ]
    if too_late:
        fail(
            "availability",
            "AVAILABILITY_AFTER_SHIFT",
            f"Waste at these points is not available until after the shift ends: "
            f"{', '.join(too_late)}.",
        )
    else:
        checks["availability"] = PASSED

    # A valid assignment of whole points to the two vehicles must exist.
    assignment: list[VehicleLoad] | None = None
    if (
        checks["vehicles"] == PASSED
        and checks["storage_points"] == PASSED
        and checks["vehicle_capacity"] == PASSED
        and checks["combined_capacity"] == PASSED
    ):
        assignment = _find_assignment(points, vehicles)
        if assignment is None:
            fail(
                "vehicle_assignment",
                "NO_FEASIBLE_ASSIGNMENT",
                "No way to divide these storage points between the two vehicles "
                "without splitting a point's waste. Adjust the quantities, the "
                "vehicle capacities, or the selected points.",
            )
        else:
            checks["vehicle_assignment"] = PASSED

    # Rule 10 - road connectivity.
    # Skipped when a location is missing or unusable: an earlier check has
    # already failed the scenario, so there is nothing to ask of the roads.
    if depot is not None and facility is not None and checks["coordinates"] == PASSED:
        result = network.check(
            RoadLocation(depot.code or depot.name, depot.latitude, depot.longitude),
            [RoadLocation(p.point_code, p.latitude, p.longitude) for p in points],
            RoadLocation(facility.facility_code, facility.latitude, facility.longitude),
        )
        if result is None:
            warnings.append(getattr(network, "warning", ROAD_NETWORK_NOT_CONFIGURED_WARNING))
        else:
            if result.too_far:
                limit = f"{settings.road_snap_max_m:g}"
                fail(
                    "road_connectivity",
                    "ROAD_TOO_FAR",
                    f"These locations are more than {limit} m from a usable road: "
                    f"{', '.join(result.too_far)}.",
                )
            if result.unreachable:
                listed = ", ".join(result.unreachable[:MAX_LISTED_ROUTES])
                others = len(result.unreachable) - MAX_LISTED_ROUTES
                suffix = f", and {others} more" if others > 0 else ""
                fail(
                    "road_connectivity",
                    "ROAD_UNREACHABLE",
                    f"These required routes do not exist by road: {listed}{suffix}.",
                )
            if not result.too_far and not result.unreachable:
                checks["road_connectivity"] = PASSED

    required_checks = [name for name in CHECK_ORDER]
    if not settings.require_road_connectivity:
        # Explicit operator override for development when no road network
        # is available. Logged every time so it cannot pass unnoticed.
        required_checks.remove("road_connectivity")
        if checks["road_connectivity"] == NOT_CHECKED:
            logger.warning(
                "Scenario %s validated with require_road_connectivity disabled; "
                "connectivity was not verified.",
                scenario.reference,
            )

    has_failure = any(checks[name] == FAILED for name in CHECK_ORDER)
    unchecked = [name for name in required_checks if checks[name] == NOT_CHECKED]

    if has_failure:
        status = STATUS_INVALID
    elif unchecked:
        status = STATUS_INCOMPLETE
    else:
        status = STATUS_VALID

    return ValidationReport(
        scenario_id=scenario.id,
        validation_status=status,
        can_optimize=status == STATUS_VALID,
        checks=checks,
        errors=errors,
        warnings=warnings,
        total_waste_kg=total_waste,
        storage_point_count=len(points),
        feasible_assignment=assignment,
    )


def record_validation(db: Session, report: ValidationReport) -> ScenarioValidation:
    """Save the report so the decision can be reviewed later."""
    record = ScenarioValidation(
        scenario_id=report.scenario_id,
        validation_status=report.validation_status,
        can_optimize=report.can_optimize,
        checks=report.checks,
        errors=report.errors,
        warnings=report.warnings,
        total_waste_kg=float(report.total_waste_kg),
        storage_point_count=report.storage_point_count,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
