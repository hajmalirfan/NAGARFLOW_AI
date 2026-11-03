from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import commit_or_conflict, get_db, reject_reserved_code, require
from app.core.permissions import workspace_owner_id
from app.evaluation import CATALOG_CODE_PREFIX
from app.models import Depot, Scenario, User, Vehicle
from app.models.scenario import scenario_depots
from app.schemas.depot import DepotResponse, DepotWrite

router = APIRouter(prefix="/depots", tags=["depots"])
DUPLICATE_CODE = "A depot with this code already exists."


def _get_owned_depot(db: Session, depot_id: int, user: User) -> Depot:
    depot = db.scalar(
        select(Depot).where(Depot.id == depot_id, Depot.user_id == workspace_owner_id(user))
    )
    if depot is None:
        raise HTTPException(status_code=404, detail="Depot not found.")
    return depot


def _validate_depot(
    db: Session, payload: DepotWrite, user: User, depot_id: int | None = None
) -> None:
    duplicate_code = db.scalar(
        select(Depot.id).where(
            func.lower(Depot.code) == payload.code.lower(),
            Depot.id != depot_id if depot_id is not None else True,
        )
    )
    if duplicate_code is not None:
        raise HTTPException(status_code=409, detail=DUPLICATE_CODE)

    if payload.is_active:
        active_depot = db.scalar(
            select(Depot.id).where(
                Depot.user_id == workspace_owner_id(user),
                Depot.is_active.is_(True),
                Depot.code.not_like(f"{CATALOG_CODE_PREFIX}%"),
                Depot.id != depot_id if depot_id is not None else True,
            )
        )
        if active_depot is not None:
            raise HTTPException(
                status_code=409,
                detail="Only one active depot is allowed. Deactivate the current depot first.",
            )


@router.post("", response_model=DepotResponse, status_code=status.HTTP_201_CREATED)
def create_depot(
    payload: DepotWrite,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Depot:
    reject_reserved_code(payload.code)
    _validate_depot(db, payload, user)
    depot = Depot(user_id=workspace_owner_id(user), **payload.model_dump())
    db.add(depot)
    commit_or_conflict(db, DUPLICATE_CODE)
    db.refresh(depot)
    return depot


@router.get("", response_model=list[DepotResponse])
def list_depots(
    db: Session = Depends(get_db),
    user: User = Depends(require("records.read")),
) -> list[Depot]:
    return db.scalars(
        select(Depot).where(Depot.user_id == workspace_owner_id(user)).order_by(Depot.name, Depot.id)
    ).all()


@router.get("/{depot_id}", response_model=DepotResponse)
def get_depot(
    depot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.read")),
) -> Depot:
    return _get_owned_depot(db, depot_id, user)


@router.put("/{depot_id}", response_model=DepotResponse)
def update_depot(
    depot_id: int,
    payload: DepotWrite,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Depot:
    depot = _get_owned_depot(db, depot_id, user)
    reject_reserved_code(payload.code, depot.code)
    _validate_depot(db, payload, user, depot.id)
    for field, value in payload.model_dump().items():
        setattr(depot, field, value)
    if depot.latitude is not None and depot.longitude is not None:
        db.query(Vehicle).filter(Vehicle.depot_id == depot.id).update(
            {
                Vehicle.start_latitude: depot.latitude,
                Vehicle.start_longitude: depot.longitude,
            },
            synchronize_session="fetch",
        )
    commit_or_conflict(db, DUPLICATE_CODE)
    db.refresh(depot)
    return depot


@router.delete("/{depot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_depot(
    depot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> Response:
    depot = _get_owned_depot(db, depot_id, user)
    linked_scenario = db.scalar(
        select(Scenario.id)
        .join(scenario_depots, scenario_depots.c.scenario_id == Scenario.id)
        .where(
            scenario_depots.c.depot_id == depot.id,
            Scenario.user_id == workspace_owner_id(user),
        )
    )
    if linked_scenario is not None:
        raise HTTPException(
            status_code=409,
            detail="This depot is linked to a scenario. Update or remove that scenario first.",
        )
    linked_vehicle = db.scalar(
        select(Vehicle.id).where(Vehicle.depot_id == depot.id)
    )
    if linked_vehicle is not None:
        raise HTTPException(
            status_code=409,
            detail="This depot is assigned to a vehicle. Update or remove that vehicle first.",
        )
    db.delete(depot)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
