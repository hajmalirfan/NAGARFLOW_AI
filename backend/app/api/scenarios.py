from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.auth import get_current_user
from app.api.dependencies import get_db
from app.models import (
    Depot,
    OptimizationRun,
    ProcessingFacility,
    Scenario,
    ScenarioValidation,
    StoragePoint,
    User,
    Vehicle,
)
from app.schemas.scenario import ScenarioOptions, ScenarioResponse, ScenarioWrite
from app.models.optimization_run import ALGORITHM_GREEDY, ALGORITHM_OR_TOOLS
from app.schemas.optimization import MethodRun, OptimizationComparison
from app.schemas.validation import ValidationHistoryEntry, ValidationReportResponse
from app.services.optimization import optimize_scenario
from app.services.road_network import get_road_network
from app.services.validation import (
    NullRoadNetwork,
    ValidationReport,
    record_validation,
    validate_scenario,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])
ACTIVE_OPTIMIZATION_STATUSES = {"queued", "pending", "running", "in_progress"}


def _scenario_query() -> Select[tuple[Scenario]]:
    return select(Scenario).options(
        selectinload(Scenario.depot),
        selectinload(Scenario.processing_facility),
        selectinload(Scenario.selected_vehicles),
        selectinload(Scenario.selected_storage_points),
    )


def _get_owned_scenario(db: Session, scenario_id: int, user: User) -> Scenario:
    scenario = db.scalar(
        _scenario_query().where(Scenario.id == scenario_id, Scenario.user_id == user.id)
    )
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found.")
    return scenario


def _serialize(scenario: Scenario) -> ScenarioResponse:
    return ScenarioResponse(
        id=scenario.id,
        reference=scenario.reference,
        name=scenario.name,
        description=scenario.description,
        status=scenario.status,
        shift_start=scenario.shift_start,
        shift_end=scenario.shift_end,
        depot={"id": scenario.depot.id, "name": scenario.depot.name} if scenario.depot else None,
        processing_facility=(
            {
                "id": scenario.processing_facility.id,
                "name": scenario.processing_facility.name,
                "capacity_kg": scenario.processing_facility.capacity_kg,
            }
            if scenario.processing_facility
            else None
        ),
        vehicles=[
            {
                "id": vehicle.id,
                "name": vehicle.name,
                "capacity_kg": vehicle.capacity_kg,
                "is_available": vehicle.is_available,
            }
            for vehicle in scenario.selected_vehicles
        ],
        storage_points=[
            {
                "id": point.id,
                "name": point.name,
                "point_code": point.point_code,
                "waste_kg": point.waste_kg,
                "waste_type": point.waste_type or "",
                "availability_status": point.availability_status,
            }
            for point in scenario.selected_storage_points
        ],
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def _validated_resources(
    db: Session, payload: ScenarioWrite, user: User
) -> tuple[Depot, ProcessingFacility, list[Vehicle], list[StoragePoint]]:
    owned_scenario_ids = select(Scenario.id).where(Scenario.user_id == user.id)
    depot = db.get(Depot, payload.depot_id)
    if depot is None or depot.user_id != user.id or not depot.is_active:
        raise HTTPException(status_code=422, detail="Select an active depot from your configured records.")

    facility = db.scalar(
        select(ProcessingFacility).where(
            ProcessingFacility.id == payload.facility_id,
            or_(
                ProcessingFacility.user_id == user.id,
                and_(
                    ProcessingFacility.user_id.is_(None),
                    ProcessingFacility.scenario_id.in_(owned_scenario_ids),
                ),
            ),
        )
    )
    if facility is None:
        raise HTTPException(status_code=422, detail="Select a processing facility from your records.")
    # Rule 4: an inactive facility cannot be chosen for a new scenario.
    if facility.status != "active":
        raise HTTPException(
            status_code=422,
            detail="Inactive processing facilities cannot be selected for a scenario.",
        )

    vehicles = db.scalars(
        select(Vehicle).where(
            Vehicle.id.in_(payload.vehicle_ids),
            or_(
                Vehicle.user_id == user.id,
                Vehicle.scenario_id.in_(owned_scenario_ids),
            ),
            Vehicle.depot_id == depot.id,
            Vehicle.status == "available",
            Vehicle.is_available.is_(True),
        )
    ).all()
    if len(vehicles) != 2:
        raise HTTPException(
            status_code=422,
            detail="Select two available vehicles assigned to the selected depot.",
        )

    points = db.scalars(
        select(StoragePoint).where(
            StoragePoint.id.in_(payload.storage_point_ids),
            or_(
                StoragePoint.user_id == user.id,
                and_(
                    StoragePoint.user_id.is_(None),
                    StoragePoint.scenario_id.in_(owned_scenario_ids),
                ),
            ),
        )
    ).all()
    if len(points) != len(payload.storage_point_ids):
        raise HTTPException(status_code=422, detail="Select storage points from your configured records.")
    if any(point.availability_status != "available" for point in points):
        raise HTTPException(
            status_code=422,
            detail="Unavailable storage points cannot be selected for a scenario.",
        )
    total_waste = sum(
        (Decimal(str(point.waste_kg)) for point in points),
        Decimal("0"),
    )
    vehicle_capacity = sum(
        (vehicle.capacity_kg for vehicle in vehicles),
        Decimal("0"),
    )
    if total_waste > vehicle_capacity:
        raise HTTPException(
            status_code=422,
            detail="Selected waste exceeds the combined capacity of the two vehicles.",
        )
    # Rule 2: W1 + W2 <= F. The facility capacity is one shared pool across
    # both vehicle deliveries, not a per-vehicle allowance.
    facility_capacity = Decimal(str(facility.capacity_kg))
    if total_waste > facility_capacity:
        raise HTTPException(
            status_code=422,
            detail=(
                "Selected waste exceeds the shared capacity of the processing "
                "facility."
            ),
        )
    return depot, facility, vehicles, points


def _apply_payload(db: Session, scenario: Scenario, payload: ScenarioWrite, user: User) -> None:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Scenario name is required.")
    duplicate = db.scalar(
        select(Scenario.id).where(
            Scenario.user_id == user.id,
            func.lower(Scenario.name) == name.lower(),
            Scenario.id != scenario.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A scenario with this name already exists.")

    depot, facility, vehicles, points = _validated_resources(db, payload, user)
    scenario.name = name
    scenario.description = payload.description.strip()
    scenario.status = payload.status
    scenario.shift_start = payload.shift_start
    scenario.shift_end = payload.shift_end
    scenario.depot = depot
    scenario.processing_facility = facility
    scenario.selected_vehicles = vehicles
    scenario.selected_storage_points = points


@router.get("/options", response_model=ScenarioOptions)
def scenario_options(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ScenarioOptions:
    owned_scenario_ids = select(Scenario.id).where(Scenario.user_id == user.id)
    depots = db.scalars(
        select(Depot)
        .where(
            Depot.user_id == user.id,
            Depot.is_active.is_(True),
            Depot.code.is_not(None),
            Depot.latitude.is_not(None),
            Depot.longitude.is_not(None),
        )
        .order_by(Depot.name)
    ).all()
    facilities = db.scalars(
        select(ProcessingFacility)
        .where(
            or_(
                ProcessingFacility.user_id == user.id,
                and_(
                    ProcessingFacility.user_id.is_(None),
                    ProcessingFacility.scenario_id.in_(owned_scenario_ids),
                ),
            ),
            # Rule 4: only an active facility can be offered for selection.
            ProcessingFacility.status == "active",
        )
        .order_by(ProcessingFacility.name)
    ).all()
    vehicles = db.scalars(
        select(Vehicle)
        .where(
            or_(
                Vehicle.user_id == user.id,
                Vehicle.scenario_id.in_(owned_scenario_ids),
            ),
            Vehicle.status == "available",
            Vehicle.is_available.is_(True),
            Vehicle.vehicle_number.is_not(None),
            Vehicle.vehicle_type.is_not(None),
            Vehicle.depot_id.is_not(None),
        )
        .order_by(Vehicle.name)
    ).all()
    points = db.scalars(
        select(StoragePoint)
        .where(
            or_(
                StoragePoint.user_id == user.id,
                and_(
                    StoragePoint.user_id.is_(None),
                    StoragePoint.scenario_id.in_(owned_scenario_ids),
                ),
            ),
            StoragePoint.availability_status == "available",
        )
        .order_by(StoragePoint.name)
    ).all()
    return ScenarioOptions(
        depots=[{"id": item.id, "name": item.name} for item in depots],
        facilities=[
            {"id": item.id, "name": item.name, "capacity_kg": item.capacity_kg}
            for item in facilities
        ],
        vehicles=[
            {
                "id": item.id,
                "name": item.name,
                "capacity_kg": item.capacity_kg,
                "is_available": item.is_available,
                "depot_id": item.depot_id,
            }
            for item in vehicles
        ],
        storage_points=[
            {
                "id": item.id,
                "name": item.name,
                "point_code": item.point_code,
                "waste_kg": item.waste_kg,
                "waste_type": item.waste_type or "",
                "availability_status": item.availability_status,
            }
            for item in points
        ],
    )


@router.get("", response_model=list[ScenarioResponse])
def list_scenarios(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ScenarioResponse]:
    scenarios = db.scalars(
        _scenario_query()
        .where(Scenario.user_id == user.id)
        .order_by(Scenario.updated_at.desc(), Scenario.id.desc())
    ).all()
    return [_serialize(scenario) for scenario in scenarios]


@router.post("", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: ScenarioWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScenarioResponse:
    scenario = Scenario(
        user_id=user.id,
        reference=f"SC-{uuid4().hex[:12].upper()}",
        name=payload.name.strip(),
        description=payload.description.strip(),
        status=payload.status,
        shift_start=payload.shift_start,
        shift_end=payload.shift_end,
    )
    _apply_payload(db, scenario, payload, user)
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return _serialize(db.scalar(_scenario_query().where(Scenario.id == scenario.id)))


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScenarioResponse:
    return _serialize(_get_owned_scenario(db, scenario_id, user))


@router.put("/{scenario_id}", response_model=ScenarioResponse)
def update_scenario(
    scenario_id: int,
    payload: ScenarioWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScenarioResponse:
    scenario = _get_owned_scenario(db, scenario_id, user)
    _apply_payload(db, scenario, payload, user)
    db.commit()
    db.refresh(scenario)
    return _serialize(db.scalar(_scenario_query().where(Scenario.id == scenario.id)))


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    scenario = _get_owned_scenario(db, scenario_id, user)
    active_run = db.scalar(
        select(OptimizationRun.id).where(
            OptimizationRun.scenario_id == scenario.id,
            func.lower(OptimizationRun.status).in_(ACTIVE_OPTIMIZATION_STATUSES),
        )
    )
    if active_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This scenario cannot be deleted while optimization is in progress.",
        )
    db.delete(scenario)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _report_response(report: ValidationReport) -> ValidationReportResponse:
    return ValidationReportResponse(
        scenario_id=report.scenario_id,
        validation_status=report.validation_status,
        can_optimize=report.can_optimize,
        checks=report.checks,
        errors=report.errors,
        warnings=report.warnings,
        total_waste_kg=float(report.total_waste_kg),
        storage_point_count=report.storage_point_count,
        feasible_assignment=(
            [
                {
                    "vehicle_id": load.vehicle_id,
                    "name": load.name,
                    "capacity_kg": float(load.capacity_kg),
                    "assigned_point_codes": load.assigned_point_codes,
                    "assigned_kg": float(load.assigned_kg),
                }
                for load in report.feasible_assignment
            ]
            if report.feasible_assignment is not None
            else None
        ),
    )


def _method_run(run: OptimizationRun) -> MethodRun:
    return MethodRun(
        status=run.status,
        total_distance_m=run.total_distance_m,
        solve_ms=run.solve_ms,
        message=run.message,
        routes=run.routes or [],
    )


def build_comparison(runs: list[OptimizationRun]) -> OptimizationComparison:
    by_algorithm = {run.algorithm: run for run in runs}
    greedy = by_algorithm[ALGORITHM_GREEDY]
    or_tools = by_algorithm[ALGORITHM_OR_TOOLS]

    difference_m = difference_pct = None
    if greedy.total_distance_m is not None and or_tools.total_distance_m is not None:
        difference_m = greedy.total_distance_m - or_tools.total_distance_m
        difference_pct = (
            round(difference_m / greedy.total_distance_m * 100, 2)
            if greedy.total_distance_m else 0.0
        )

    return OptimizationComparison(
        scenario_id=greedy.scenario_id,
        batch_id=greedy.batch_id,
        created_at=greedy.created_at,
        input_hash=greedy.input_hash,
        provenance=greedy.provenance,
        greedy=_method_run(greedy),
        or_tools=_method_run(or_tools),
        difference_m=difference_m,
        difference_pct=difference_pct,
    )


@router.post("/{scenario_id}/validate", response_model=ValidationReportResponse)
def validate_scenario_endpoint(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ValidationReportResponse:
    """Check every hard constraint before the optimizer may run.

    The result is recorded so the decision can be reviewed later, and the
    scenario is re-checked on every call rather than cached, because the
    underlying vehicles, points and facility can change at any time.
    """
    scenario = _get_owned_scenario(db, scenario_id, user)
    report = validate_scenario(db, scenario, get_road_network())
    record_validation(db, report)
    return _report_response(report)


@router.post("/{scenario_id}/optimize", response_model=OptimizationComparison)
def optimize_scenario_endpoint(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OptimizationComparison:
    """Run Greedy and OR-Tools on identical inputs and compare them.

    The scenario is validated afresh, because it may have changed since it
    was last checked. Nothing runs unless every hard constraint passes.
    """
    scenario = _get_owned_scenario(db, scenario_id, user)
    network = get_road_network()
    report = validate_scenario(db, scenario, network)
    record_validation(db, report)
    if not report.can_optimize:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This scenario cannot be optimized until it passes validation.",
                "report": _report_response(report).model_dump(),
            },
        )
    if isinstance(network, NullRoadNetwork):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Routes need a road network, and none is available.",
                "report": _report_response(report).model_dump(),
            },
        )
    return build_comparison(optimize_scenario(db, scenario, network))


@router.get("/{scenario_id}/optimization", response_model=OptimizationComparison)
def latest_optimization(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OptimizationComparison:
    """The most recent comparison for this scenario."""
    _get_owned_scenario(db, scenario_id, user)
    newest = db.scalar(
        select(OptimizationRun)
        .where(OptimizationRun.scenario_id == scenario_id, OptimizationRun.batch_id.is_not(None))
        .order_by(OptimizationRun.id.desc())
        .limit(1)
    )
    if newest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This scenario has not been optimized yet.",
        )
    runs = db.scalars(select(OptimizationRun).where(OptimizationRun.batch_id == newest.batch_id))
    return build_comparison(list(runs))


@router.get("/{scenario_id}/optimization/{batch_id}", response_model=OptimizationComparison)
def saved_optimization(
    scenario_id: int,
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OptimizationComparison:
    """One saved comparison, reopened from the history."""
    _get_owned_scenario(db, scenario_id, user)
    runs = list(db.scalars(
        select(OptimizationRun).where(
            OptimizationRun.scenario_id == scenario_id, OptimizationRun.batch_id == batch_id
        )
    ))
    if not runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This saved run does not exist."
        )
    return build_comparison(runs)


@router.get("/{scenario_id}/validations", response_model=list[ValidationHistoryEntry])
def list_scenario_validations(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ScenarioValidation]:
    """Past validation runs for this scenario, newest first."""
    _get_owned_scenario(db, scenario_id, user)
    return list(
        db.scalars(
            select(ScenarioValidation)
            .where(ScenarioValidation.scenario_id == scenario_id)
            .order_by(ScenarioValidation.id.desc())
        ).all()
    )
