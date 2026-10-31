from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.auth import get_current_user
from app.api.dependencies import get_db
from app.models import ProcessingFacility, Scenario, User
from app.models.scenario import scenario_facilities
from app.schemas.facility import (
    FacilityCapacityResponse,
    FacilityResponse,
    FacilityScenarioAllocation,
    FacilityWrite,
)

router = APIRouter(prefix="/facilities", tags=["processing facilities"])


def _owned_facility_query(user: User) -> Select[tuple[ProcessingFacility]]:
    """Facilities this coordinator manages.

    Covers both the current user-owned records and legacy rows that were
    created under the earlier scenario-owned schema.
    """
    owned_scenario_ids = select(Scenario.id).where(Scenario.user_id == user.id)
    return select(ProcessingFacility).where(
        or_(
            ProcessingFacility.user_id == user.id,
            and_(
                ProcessingFacility.user_id.is_(None),
                ProcessingFacility.scenario_id.in_(owned_scenario_ids),
            ),
        )
    )


def _get_owned_facility(db: Session, facility_id: int, user: User) -> ProcessingFacility:
    facility = db.scalar(
        _owned_facility_query(user).where(ProcessingFacility.id == facility_id)
    )
    if facility is None:
        raise HTTPException(status_code=404, detail="Processing facility not found.")
    return facility


def _validate_facility_code(
    db: Session, facility_code: str, facility_id: int | None = None
) -> None:
    duplicate = db.scalar(
        select(ProcessingFacility.id).where(
            func.lower(ProcessingFacility.facility_code) == facility_code.lower(),
            ProcessingFacility.id != facility_id if facility_id is not None else True,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409, detail="A processing facility with this code already exists."
        )


def _linked_scenarios(db: Session, facility: ProcessingFacility) -> list[Scenario]:
    """Scenarios that deliver to this facility, old and new linkage alike."""
    conditions = [scenario_facilities.c.facility_id == facility.id]
    if facility.scenario_id is not None:
        conditions.append(Scenario.id == facility.scenario_id)
    return (
        db.scalars(
            select(Scenario)
            .outerjoin(
                scenario_facilities,
                scenario_facilities.c.scenario_id == Scenario.id,
            )
            .where(or_(*conditions))
            .options(
                selectinload(Scenario.selected_storage_points),
                selectinload(Scenario.storage_points),
            )
        )
        .unique()
        .all()
    )


def _allocated_kg(scenario: Scenario) -> Decimal:
    """Waste this scenario commits to its facility.

    Every configured storage point is mandatory and its whole quantity is
    delivered, so the commitment is the sum across the scenario's points.
    """
    points = {
        point.id: point
        for point in (*scenario.selected_storage_points, *scenario.storage_points)
    }.values()
    return sum((Decimal(str(point.waste_kg)) for point in points), Decimal("0"))


def _serialize(facility: ProcessingFacility) -> FacilityResponse:
    return FacilityResponse(
        id=facility.id,
        name=facility.name,
        facility_code=facility.facility_code,
        address=facility.address,
        latitude=facility.latitude,
        longitude=facility.longitude,
        total_capacity_kg=facility.capacity_kg,
        status=facility.status,
        description=facility.description,
        created_at=facility.created_at,
        updated_at=facility.updated_at,
    )


@router.post("", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
def create_facility(
    payload: FacilityWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FacilityResponse:
    _validate_facility_code(db, payload.facility_code)
    values = payload.model_dump()
    facility = ProcessingFacility(
        user_id=user.id,
        name=values["name"],
        facility_code=values["facility_code"],
        address=values["address"] or None,
        latitude=values["latitude"],
        longitude=values["longitude"],
        capacity_kg=values["total_capacity_kg"],
        status=values["status"],
        description=values["description"] or None,
    )
    db.add(facility)
    db.commit()
    db.refresh(facility)
    return _serialize(facility)


@router.get("", response_model=list[FacilityResponse])
def list_facilities(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FacilityResponse]:
    facilities = db.scalars(
        _owned_facility_query(user).order_by(
            ProcessingFacility.name, ProcessingFacility.id
        )
    ).all()
    return [_serialize(facility) for facility in facilities]


@router.get("/{facility_id}", response_model=FacilityResponse)
def get_facility(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FacilityResponse:
    return _serialize(_get_owned_facility(db, facility_id, user))


@router.get("/{facility_id}/capacity", response_model=FacilityCapacityResponse)
def get_facility_capacity(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FacilityCapacityResponse:
    """Report the shared capacity pool for this facility."""
    facility = _get_owned_facility(db, facility_id, user)
    scenarios = _linked_scenarios(db, facility)

    allocations = [
        FacilityScenarioAllocation(
            id=scenario.id,
            reference=scenario.reference,
            name=scenario.name,
            allocated_kg=_allocated_kg(scenario),
        )
        for scenario in scenarios
    ]
    allocated = sum((_allocated_kg(scenario) for scenario in scenarios), Decimal("0"))
    total = Decimal(str(facility.capacity_kg))

    return FacilityCapacityResponse(
        id=facility.id,
        name=facility.name,
        facility_code=facility.facility_code,
        total_capacity_kg=total,
        allocated_kg=allocated,
        remaining_capacity_kg=total - allocated,
        is_within_capacity=allocated <= total,
        status=facility.status,
        scenarios=sorted(allocations, key=lambda item: item.reference),
    )


@router.put("/{facility_id}", response_model=FacilityResponse)
def update_facility(
    facility_id: int,
    payload: FacilityWrite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FacilityResponse:
    facility = _get_owned_facility(db, facility_id, user)
    _validate_facility_code(db, payload.facility_code, facility.id)

    scenarios = _linked_scenarios(db, facility)
    if scenarios:
        if payload.status == "inactive":
            raise HTTPException(
                status_code=409,
                detail=(
                    "This facility is linked to a scenario. Update or remove that "
                    "scenario before deactivating the facility."
                ),
            )
        # Rule 2: W1 + W2 <= F has to keep holding after the edit.
        for scenario in scenarios:
            allocated = _allocated_kg(scenario)
            if allocated > payload.total_capacity_kg:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Scenario {scenario.reference} already commits "
                        f"{allocated} kg to this facility, so the shared capacity "
                        f"cannot be reduced to {payload.total_capacity_kg} kg."
                    ),
                )

    values = payload.model_dump()
    facility.name = values["name"]
    facility.facility_code = values["facility_code"]
    facility.address = values["address"] or None
    facility.latitude = values["latitude"]
    facility.longitude = values["longitude"]
    facility.capacity_kg = values["total_capacity_kg"]
    facility.status = values["status"]
    facility.description = values["description"] or None
    db.commit()
    db.refresh(facility)
    return _serialize(facility)


@router.delete("/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(
    facility_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    facility = _get_owned_facility(db, facility_id, user)
    if _linked_scenarios(db, facility):
        raise HTTPException(
            status_code=409,
            detail=(
                "This facility is linked to a scenario. Update or remove that "
                "scenario first."
            ),
        )
    db.delete(facility)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
