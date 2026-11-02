"""Dashboard aggregation.

Every number here is computed with a real query against the signed-in
coordinator's own scenarios. Nothing is estimated, sampled, or filled in
with a placeholder figure: when there is no data the result is genuinely
zero, and the facility card reports that it is not configured.
"""

from sqlalchemy import ColumnElement, Select, and_, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import workspace_owner_id
from app.evaluation import CATALOG_CODE_PREFIX
from app.models.scenario import scenario_storage_points, scenario_vehicles
from app.models.optimization_run import (
    FAILED_STATUSES,
    SUCCESSFUL_STATUSES,
    OptimizationRun,
)
from app.models.processing_facility import ProcessingFacility
from app.models.scenario import Scenario
from app.models.storage_point import StoragePoint
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.dashboard import (
    DashboardSummary,
    OptimizationSummary,
    ScenarioSummary,
    StoragePointSummary,
    VehicleStatus,
    VehicleSummary,
    WasteOverview,
)

# How many rows the list sections show. The dashboard is an overview; the
# dedicated pages for each entity show everything.
RECENT_SCENARIO_LIMIT = 5
STORAGE_POINT_LIMIT = 10


def _owned_scenarios(user: User) -> Select[tuple[int]]:
    """Scenario ids belonging to this user, used to scope every total."""
    return select(Scenario.id).where(_real_scenarios(user))


def _real_scenarios(user: User) -> ColumnElement[bool]:
    """This user's scenarios, leaving out the synthetic evaluation cases."""
    return and_(Scenario.user_id == workspace_owner_id(user), Scenario.evaluation_code.is_(None))


def build_dashboard_summary(db: Session, user: User) -> DashboardSummary:
    scenario_ids = _owned_scenarios(user)

    scenarios = db.scalars(
        select(Scenario)
        .where(_real_scenarios(user))
        .order_by(Scenario.created_at.desc(), Scenario.id.desc())
    ).all()

    storage_points = db.scalars(
        select(StoragePoint)
        .where(
            or_(
                StoragePoint.user_id == workspace_owner_id(user),
                and_(
                    StoragePoint.user_id.is_(None),
                    StoragePoint.scenario_id.in_(scenario_ids),
                ),
            ),
            StoragePoint.point_code.not_like(f"{CATALOG_CODE_PREFIX}%"),
        )
        .order_by(StoragePoint.id)
    ).all()

    selected_vehicle_ids = (
        select(scenario_vehicles.c.vehicle_id)
        .join(Scenario, Scenario.id == scenario_vehicles.c.scenario_id)
        .where(_real_scenarios(user))
    )
    vehicles = db.scalars(
        select(Vehicle)
        .where(
            or_(
                Vehicle.scenario_id.in_(scenario_ids),
                Vehicle.id.in_(selected_vehicle_ids),
            )
        )
        .order_by(Vehicle.id)
    ).all()

    facilities = db.scalars(
        select(ProcessingFacility).where(
            or_(
                ProcessingFacility.user_id == workspace_owner_id(user),
                and_(
                    ProcessingFacility.user_id.is_(None),
                    ProcessingFacility.scenario_id.in_(scenario_ids),
                ),
            ),
            ProcessingFacility.facility_code.not_like(f"{CATALOG_CODE_PREFIX}%"),
        )
    ).all()

    # Only these columns: saved route geometry is by far the largest thing stored.
    runs = db.execute(
        select(OptimizationRun.status, OptimizationRun.total_distance_m)
        .where(OptimizationRun.scenario_id.in_(scenario_ids))
    ).all()

    scenario_reference = {scenario.id: scenario.reference for scenario in scenarios}
    selected_vehicle_references = {
        vehicle_id: reference
        for reference, vehicle_id in db.execute(
            select(Scenario.reference, scenario_vehicles.c.vehicle_id)
            .join(Scenario, Scenario.id == scenario_vehicles.c.scenario_id)
            .where(Scenario.user_id == workspace_owner_id(user))
        ).all()
    }
    selected_storage_point_references = {
        point_id: reference
        for reference, point_id in db.execute(
            select(Scenario.reference, scenario_storage_points.c.storage_point_id)
            .join(Scenario, Scenario.id == scenario_storage_points.c.scenario_id)
            .where(Scenario.user_id == workspace_owner_id(user))
        ).all()
    }

    waste_quantities = [point.waste_kg for point in storage_points]
    total_waste_kg = sum(waste_quantities)

    available = [vehicle for vehicle in vehicles if vehicle.is_available]
    unavailable = [vehicle for vehicle in vehicles if not vehicle.is_available]

    # Nothing has been delivered until an optimization run records a
    # delivery, so the whole configured capacity is still available.
    facility_capacity_kg = sum(facility.capacity_kg for facility in facilities)

    successful_runs = [run for run in runs if run.status in SUCCESSFUL_STATUSES]
    failed_runs = [run for run in runs if run.status in FAILED_STATUSES]
    best_distance_m = min((run.total_distance_m for run in successful_runs), default=None)

    def to_vehicle_summary(vehicle: Vehicle) -> VehicleSummary:
        return VehicleSummary(
            id=vehicle.id,
            name=vehicle.name,
            capacity_kg=vehicle.capacity_kg,
            is_available=vehicle.is_available,
            scenario_reference=(
                selected_vehicle_references.get(vehicle.id)
                or scenario_reference.get(vehicle.scenario_id, "")
            ),
        )

    return DashboardSummary(
        total_waste_kg=total_waste_kg,
        storage_points_count=len(storage_points),
        available_vehicles_count=len(available),
        facility_remaining_capacity_kg=facility_capacity_kg,
        total_scenarios=len(scenarios),
        optimized_routes_count=len(successful_runs),
        facility_configured=bool(facilities),
        waste_overview=WasteOverview(
            total_waste_kg=total_waste_kg,
            storage_points_count=len(storage_points),
            largest_point_kg=max(waste_quantities, default=0.0),
            average_point_kg=(total_waste_kg / len(waste_quantities)) if waste_quantities else 0.0,
        ),
        vehicle_status=VehicleStatus(
            available=[to_vehicle_summary(vehicle) for vehicle in available],
            unavailable=[to_vehicle_summary(vehicle) for vehicle in unavailable],
            available_count=len(available),
            unavailable_count=len(unavailable),
            total_available_capacity_kg=sum(vehicle.capacity_kg for vehicle in available),
        ),
        storage_points=[
            StoragePointSummary(
                id=point.id,
                name=point.name,
                latitude=point.latitude,
                longitude=point.longitude,
                waste_kg=point.waste_kg,
                waste_type=point.waste_type,
                available_from=point.available_from,
                scenario_reference=(
                    selected_storage_point_references.get(point.id)
                    or scenario_reference.get(point.scenario_id, "")
                ),
            )
            for point in storage_points[:STORAGE_POINT_LIMIT]
        ],
        recent_scenarios=[
            ScenarioSummary(
                id=scenario.id,
                reference=scenario.reference,
                name=scenario.name,
                status=scenario.status,
                created_at=scenario.created_at,
                storage_points_count=(
                    len(scenario.selected_storage_points)
                    or sum(1 for point in storage_points if point.scenario_id == scenario.id)
                ),
                vehicles_count=(
                    len(scenario.selected_vehicles)
                    or sum(1 for vehicle in vehicles if vehicle.scenario_id == scenario.id)
                ),
            )
            for scenario in scenarios[:RECENT_SCENARIO_LIMIT]
        ],
        optimization_summary=OptimizationSummary(
            successful_runs=len(successful_runs),
            failed_runs=len(failed_runs),
            total_runs=len(runs),
            best_distance_km=(best_distance_m / 1000) if best_distance_m is not None else None,
        ),
    )
