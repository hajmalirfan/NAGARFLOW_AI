from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CheckResult = Literal["passed", "failed", "not_checked"]
ValidationStatus = Literal["valid", "invalid", "incomplete"]


class ValidationMessage(BaseModel):
    code: str
    message: str


class VehicleLoadResponse(BaseModel):
    vehicle_id: int
    name: str
    capacity_kg: float
    assigned_point_codes: list[str]
    assigned_kg: float


class ValidationReportResponse(BaseModel):
    """The outcome of one validation run.

    ``can_optimize`` is true only when every required check passed.
    ``incomplete`` means nothing failed but a required check could not
    run, so the scenario must not reach the optimizer yet.
    """

    scenario_id: int
    validation_status: ValidationStatus
    can_optimize: bool
    checks: dict[str, CheckResult]
    errors: list[ValidationMessage]
    warnings: list[ValidationMessage]
    total_waste_kg: float
    storage_point_count: int
    feasible_assignment: list[VehicleLoadResponse] | None = None


class ValidationHistoryEntry(BaseModel):
    id: int
    scenario_id: int
    validation_status: ValidationStatus
    can_optimize: bool
    checks: dict[str, CheckResult]
    errors: list[ValidationMessage]
    warnings: list[ValidationMessage]
    total_waste_kg: float
    storage_point_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
