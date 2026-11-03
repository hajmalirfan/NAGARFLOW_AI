from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import commit_or_conflict, get_db, reject_reserved_code, require
from app.core.permissions import workspace_owner_id
from app.models import Scenario, StoragePoint, User
from app.models.scenario import scenario_storage_points
from app.schemas.storage_point import StoragePointResponse, StoragePointWrite

router = APIRouter(prefix="/storage-points", tags=["storage points"])
DUPLICATE_CODE = "A storage point with this code already exists."


def _owned_point_query(user: User) -> Select[tuple[StoragePoint]]:
    owned_scenario_ids = select(Scenario.id).where(Scenario.user_id == workspace_owner_id(user))
    return select(StoragePoint).where(
        or_(
            StoragePoint.user_id == workspace_owner_id(user),
            and_(
                StoragePoint.user_id.is_(None),
                StoragePoint.scenario_id.in_(owned_scenario_ids),
            ),
        )
    )


def _get_owned_point(db: Session, point_id: int, user: User) -> StoragePoint:
    point = db.scalar(_owned_point_query(user).where(StoragePoint.id == point_id))
    if point is None:
        raise HTTPException(status_code=404, detail="Storage point not found.")
    return point


def _validate_point_code(
    db: Session, point_code: str, point_id: int | None = None
) -> None:
    duplicate = db.scalar(
        select(StoragePoint.id).where(
            func.lower(StoragePoint.point_code) == point_code.lower(),
            StoragePoint.id != point_id if point_id is not None else True,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail=DUPLICATE_CODE
        )


def _validate_linked_scenario_capacity(
    db: Session,
    point: StoragePoint,
    new_waste_kg: Decimal,
    availability_status: str,
) -> None:
    linked_conditions = [
        scenario_storage_points.c.storage_point_id == point.id,
    ]
    if point.scenario_id is not None:
        linked_conditions.append(Scenario.id == point.scenario_id)
    linked_scenarios = db.scalars(
        select(Scenario)
        .outerjoin(
            scenario_storage_points,
            scenario_storage_points.c.scenario_id == Scenario.id,
        )
        .where(or_(*linked_conditions))
        .options(
            selectinload(Scenario.selected_vehicles),
            selectinload(Scenario.selected_storage_points),
            selectinload(Scenario.vehicles),
            selectinload(Scenario.storage_points),
        )
    ).unique().all()
    if availability_status == "unavailable" and linked_scenarios:
        raise HTTPException(
            status_code=409,
            detail=(
                "This storage point is linked to a scenario. Update or remove "
                "that scenario before marking the point unavailable."
            ),
        )
    for scenario in linked_scenarios:
        scenario_points = {
            selected.id: selected
            for selected in (*scenario.selected_storage_points, *scenario.storage_points)
        }.values()
        scenario_vehicles = {
            vehicle.id: vehicle
            for vehicle in (*scenario.selected_vehicles, *scenario.vehicles)
        }.values()
        total_waste = sum(
            (
                new_waste_kg if selected.id == point.id else Decimal(str(selected.waste_kg))
                for selected in scenario_points
            ),
            Decimal("0"),
        )
        capacity = sum(
            (vehicle.capacity_kg for vehicle in scenario_vehicles),
            Decimal("0"),
        )
        if total_waste > capacity:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Changing this quantity would exceed the vehicle capacity "
                    f"for scenario {scenario.reference}."
                ),
            )


def _serialize(point: StoragePoint) -> StoragePointResponse:
    return StoragePointResponse(
        id=point.id,
        name=point.name,
        point_code=point.point_code,
        address=point.address,
        latitude=point.latitude,
        longitude=point.longitude,
        waste_quantity_kg=point.waste_kg,
        availability_status=point.availability_status,
        available_from=point.available_from,
        description=point.description,
        created_at=point.created_at,
        updated_at=point.updated_at,
    )


@router.post("", response_model=StoragePointResponse, status_code=status.HTTP_201_CREATED)
def create_storage_point(
    payload: StoragePointWrite,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> StoragePointResponse:
    reject_reserved_code(payload.point_code)
    _validate_point_code(db, payload.point_code)
    values = payload.model_dump()
    point = StoragePoint(
        user_id=workspace_owner_id(user),
        name=values["name"],
        point_code=values["point_code"],
        address=values["address"] or None,
        latitude=values["latitude"],
        longitude=values["longitude"],
        waste_kg=values["waste_quantity_kg"],
        availability_status=values["availability_status"],
        available_from=values["available_from"],
        description=values["description"] or None,
    )
    db.add(point)
    commit_or_conflict(db, DUPLICATE_CODE)
    db.refresh(point)
    return _serialize(point)


@router.get("", response_model=list[StoragePointResponse])
def list_storage_points(
    db: Session = Depends(get_db),
    user: User = Depends(require("records.read")),
) -> list[StoragePointResponse]:
    points = db.scalars(
        _owned_point_query(user).order_by(StoragePoint.name, StoragePoint.id)
    ).all()
    return [_serialize(point) for point in points]


@router.get("/{point_id}", response_model=StoragePointResponse)
def get_storage_point(
    point_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.read")),
) -> StoragePointResponse:
    return _serialize(_get_owned_point(db, point_id, user))


@router.put("/{point_id}", response_model=StoragePointResponse)
def update_storage_point(
    point_id: int,
    payload: StoragePointWrite,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> StoragePointResponse:
    point = _get_owned_point(db, point_id, user)
    reject_reserved_code(payload.point_code, point.point_code)
    _validate_point_code(db, payload.point_code, point.id)
    _validate_linked_scenario_capacity(
        db, point, payload.waste_quantity_kg, payload.availability_status
    )
    values = payload.model_dump()
    point.name = values["name"]
    point.point_code = values["point_code"]
    point.address = values["address"] or None
    point.latitude = values["latitude"]
    point.longitude = values["longitude"]
    point.waste_kg = values["waste_quantity_kg"]
    point.availability_status = values["availability_status"]
    point.available_from = values["available_from"]
    point.description = values["description"] or None
    commit_or_conflict(db, DUPLICATE_CODE)
    db.refresh(point)
    return _serialize(point)


@router.delete("/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_storage_point(
    point_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Response:
    point = _get_owned_point(db, point_id, user)
    linked_scenario = db.scalar(
        select(scenario_storage_points.c.scenario_id)
        .join(Scenario, Scenario.id == scenario_storage_points.c.scenario_id)
        .where(
            scenario_storage_points.c.storage_point_id == point.id,
            Scenario.user_id == workspace_owner_id(user),
        )
    )
    legacy_scenario = (
        point.scenario_id
        if point.scenario_id is not None
        and db.scalar(
            select(Scenario.id).where(
                Scenario.id == point.scenario_id, Scenario.user_id == workspace_owner_id(user)
            )
        )
        is not None
        else None
    )
    if linked_scenario is not None or legacy_scenario is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This storage point is linked to a scenario. Update or remove "
                "that scenario first."
            ),
        )
    db.delete(point)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
