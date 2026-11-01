"""Loads the S01 to S10 catalogue as ordinary records owned by a coordinator.

Records go in directly, not through the API, because S04, S05 and S09 are
meant to fail validation. Codes are unique across all users, so each one
carries its owner's id. Existing records are reused, which lets a deleted
case come back without clashing with what remains.
"""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation import CATALOG_CODE_PREFIX
from app.models.depot import Depot
from app.models.processing_facility import ProcessingFacility
from app.models.scenario import Scenario, scenario_depots, scenario_facilities
from app.models.storage_point import StoragePoint
from app.models.user import User
from app.models.vehicle import Vehicle

CATALOG_DIR = Path(__file__).parent / "catalog"
CATALOG_VERSION = json.loads((CATALOG_DIR / "manifest.json").read_text("utf-8"))["catalog_version"]


def read_catalog() -> list[dict]:
    """The ten cases in order. A file that does not match the manifest is refused."""
    manifest = json.loads((CATALOG_DIR / "manifest.json").read_text("utf-8"))
    cases = []
    for code, checksum in sorted(manifest["files"].items()):
        # Git may check text out with CRLF on Windows.
        content = (CATALOG_DIR / f"{code}.json").read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError(f"Catalogue file {code} does not match its checksum.")
        cases.append(json.loads(content))
    return cases


def _moment(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _reuse_or_add(
    db: Session, model: type, code_field: str, code: str, user_id: int, **values
) -> object:
    record = db.scalar(
        select(model).where(getattr(model, code_field) == code, model.user_id == user_id)
    )
    if record is None:
        record = model(**{code_field: code}, user_id=user_id, **values)
        db.add(record)
        db.flush()
    return record


def _create_case(db: Session, user: User, case: dict) -> Scenario:
    prefix = f"{CATALOG_CODE_PREFIX}{user.id}-{case['code']}"
    label = f"SYNTH-{case['code']}"
    shift = case["shift"] or {}
    scenario = Scenario(
        user_id=user.id,
        reference=f"SC-{uuid4().hex[:12].upper()}",
        name=f"{label} {case['name']}",
        description=f"Synthetic evaluation case. {case['purpose']}",
        status="draft",
        shift_start=_moment(shift.get("start")),
        shift_end=_moment(shift.get("end")),
        evaluation_code=case["code"],
    )
    db.add(scenario)
    db.flush()

    depot = _reuse_or_add(
        db, Depot, "code", f"{prefix}-D", user.id, name=f"{label} Depot",
        latitude=case["depot"]["latitude"], longitude=case["depot"]["longitude"],
    )
    facility = _reuse_or_add(
        db, ProcessingFacility, "facility_code", f"{prefix}-F", user.id,
        name=f"{label} Facility", latitude=case["facility"]["latitude"],
        longitude=case["facility"]["longitude"],
        capacity_kg=Decimal(str(case["facility"]["capacity_kg"])), status="active",
    )
    db.execute(scenario_depots.insert().values(scenario_id=scenario.id, depot_id=depot.id))
    db.execute(
        scenario_facilities.insert().values(scenario_id=scenario.id, facility_id=facility.id)
    )

    scenario.selected_vehicles = [
        _reuse_or_add(
            db, Vehicle, "vehicle_number", f"{prefix}-V{index}", user.id,
            name=f"{label} Vehicle {index}", vehicle_type="Truck",
            capacity_kg=Decimal(str(capacity)), depot_id=depot.id, status="available",
            is_available=True, start_latitude=depot.latitude, start_longitude=depot.longitude,
        )
        for index, capacity in enumerate(case["vehicle_capacities_kg"], 1)
    ]
    scenario.selected_storage_points = [
        _reuse_or_add(
            db, StoragePoint, "point_code", f"{prefix}-P{index:02d}", user.id,
            name=f"{label} Point {index}", latitude=point["latitude"],
            longitude=point["longitude"], waste_kg=Decimal(str(point["waste_kg"])),
            availability_status="available", available_from=_moment(point["available_from"]),
        )
        for index, point in enumerate(case["points"], 1)
    ]
    return scenario


def load_catalog(db: Session, user: User) -> list[Scenario]:
    """Create any case the coordinator lacks, all or nothing, and return all ten."""
    existing = {
        scenario.evaluation_code: scenario
        for scenario in db.scalars(
            select(Scenario).where(
                Scenario.user_id == user.id, Scenario.evaluation_code.is_not(None)
            )
        )
    }
    try:
        scenarios = [
            existing.get(case["code"]) or _create_case(db, user, case) for case in read_catalog()
        ]
        db.commit()
    except Exception:
        db.rollback()
        raise
    return scenarios
