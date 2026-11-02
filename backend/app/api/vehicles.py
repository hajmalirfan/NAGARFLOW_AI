from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_db, reject_reserved_code, require
from app.core.permissions import workspace_owner_id
from app.models import Depot, Scenario, User, Vehicle
from app.models.scenario import scenario_vehicles
from app.schemas.vehicle import VehicleResponse, VehicleWrite

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _owned_scenario_ids(user: User) -> Select[tuple[int]]:
    return select(Scenario.id).where(Scenario.user_id == workspace_owner_id(user))


def _owned_vehicle_condition(user: User) -> ColumnElement[bool]:
    return or_(
        Vehicle.user_id == workspace_owner_id(user),
        Vehicle.scenario_id.in_(_owned_scenario_ids(user)),
    )


def _vehicle_query() -> Select[tuple[Vehicle]]:
    return select(Vehicle).options(selectinload(Vehicle.depot))


def _get_owned_vehicle(db: Session, vehicle_id: int, user: User) -> Vehicle:
    vehicle = db.scalar(
        _vehicle_query().where(
            Vehicle.id == vehicle_id,
            _owned_vehicle_condition(user),
        )
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return vehicle


def _get_owned_depot(db: Session, depot_id: int, user: User) -> Depot:
    depot = db.scalar(
        select(Depot).where(
            Depot.id == depot_id,
            Depot.user_id == workspace_owner_id(user),
            Depot.is_active.is_(True),
            Depot.latitude.is_not(None),
            Depot.longitude.is_not(None),
        )
    )
    if depot is None:
        raise HTTPException(status_code=422, detail="Select an active configured depot.")
    return depot


def _validate_write(
    db: Session, payload: VehicleWrite, user: User, vehicle_id: int | None = None
) -> Depot:
    duplicate_number = db.scalar(
        select(Vehicle.id).where(
            func.lower(Vehicle.vehicle_number) == payload.vehicle_number.lower(),
            Vehicle.id != vehicle_id if vehicle_id is not None else True,
        )
    )
    if duplicate_number is not None:
        raise HTTPException(status_code=409, detail="A vehicle with this registration number already exists.")

    return _get_owned_depot(db, payload.depot_id, user)


def _linked_scenarios(db: Session, vehicle: Vehicle) -> list[Scenario]:
    return db.scalars(
        select(Scenario)
        .join(scenario_vehicles, scenario_vehicles.c.scenario_id == Scenario.id)
        .where(scenario_vehicles.c.vehicle_id == vehicle.id)
        .options(selectinload(Scenario.selected_vehicles), selectinload(Scenario.selected_storage_points))
    ).all()


def _validate_linked_scenario_capacity(
    scenario: Scenario, vehicle: Vehicle, capacity_kg: Decimal
) -> None:
    selected_capacity = sum(
        (
            capacity_kg
            if selected.id == vehicle.id
            else selected.capacity_kg
            for selected in scenario.selected_vehicles
        ),
        Decimal("0"),
    )
    total_waste = sum(
        (Decimal(str(point.waste_kg)) for point in scenario.selected_storage_points),
        Decimal("0"),
    )
    if total_waste > selected_capacity:
        raise HTTPException(
            status_code=409,
            detail="This capacity change would leave a linked scenario with more waste than its vehicles can carry.",
        )


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleWrite,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Vehicle:
    reject_reserved_code(payload.vehicle_number)
    depot = _validate_write(db, payload, user)
    vehicle = Vehicle(
        user_id=workspace_owner_id(user),
        scenario_id=None,
        vehicle_number=payload.vehicle_number,
        name=payload.name,
        vehicle_type=payload.vehicle_type,
        capacity_kg=payload.capacity_kg,
        depot_id=depot.id,
        status=payload.status,
        is_available=payload.status == "available",
        start_latitude=depot.latitude,
        start_longitude=depot.longitude,
    )
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A vehicle with this registration number already exists.") from None
    db.refresh(vehicle)
    return db.scalar(_vehicle_query().where(Vehicle.id == vehicle.id))


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(
    db: Session = Depends(get_db),
    user: User = Depends(require("records.read")),
) -> list[Vehicle]:
    return db.scalars(
        _vehicle_query()
        .where(_owned_vehicle_condition(user))
        .order_by(Vehicle.name, Vehicle.id)
    ).all()


@router.get("/{vehicle_id}", response_model=VehicleResponse)
def get_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.read")),
) -> Vehicle:
    return _get_owned_vehicle(db, vehicle_id, user)


@router.put("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleWrite,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Vehicle:
    vehicle = _get_owned_vehicle(db, vehicle_id, user)
    reject_reserved_code(payload.vehicle_number, vehicle.vehicle_number)
    depot = _validate_write(db, payload, user, vehicle.id)
    linked_scenarios = _linked_scenarios(db, vehicle)
    if linked_scenarios and (
        payload.depot_id != vehicle.depot_id or payload.status != "available"
    ):
        raise HTTPException(
            status_code=409,
            detail="Update linked scenarios before changing this vehicle's depot or making it unavailable.",
        )
    for scenario in linked_scenarios:
        _validate_linked_scenario_capacity(scenario, vehicle, payload.capacity_kg)

    vehicle.vehicle_number = payload.vehicle_number
    vehicle.name = payload.name
    vehicle.vehicle_type = payload.vehicle_type
    vehicle.capacity_kg = payload.capacity_kg
    vehicle.depot_id = depot.id
    vehicle.status = payload.status
    vehicle.is_available = payload.status == "available"
    vehicle.start_latitude = depot.latitude
    vehicle.start_longitude = depot.longitude
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A vehicle with this registration number already exists.") from None
    db.refresh(vehicle)
    return db.scalar(_vehicle_query().where(Vehicle.id == vehicle.id))


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Response:
    vehicle = _get_owned_vehicle(db, vehicle_id, user)
    linked_vehicle = db.scalar(
        select(scenario_vehicles.c.scenario_id).where(
            scenario_vehicles.c.vehicle_id == vehicle.id
        )
    )
    if linked_vehicle is not None:
        raise HTTPException(
            status_code=409,
            detail="This vehicle is linked to a scenario. Update or remove that scenario first.",
        )
    if vehicle.scenario_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This legacy vehicle is still linked to its original scenario.",
        )
    db.delete(vehicle)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
