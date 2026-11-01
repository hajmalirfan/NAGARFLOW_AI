from typing import Literal

from pydantic import BaseModel


class LoadedCase(BaseModel):
    code: str
    scenario_id: int
    name: str


class VehicleLoad(BaseModel):
    vehicle_name: str
    load_kg: float
    capacity_kg: float


class MethodOutcome(BaseModel):
    status: str
    message: str | None
    distance_m: float | None
    vehicle_loads: list[VehicleLoad]
    facility_load_kg: float
    facility_capacity_kg: float


class ReportRow(BaseModel):
    code: str
    name: str
    purpose: str
    state: Literal["not_loaded", "not_run", "blocked", "ran"]
    scenario_id: int | None
    errors: list[dict]
    greedy: MethodOutcome | None
    or_tools: MethodOutcome | None
    difference_m: float | None
    difference_pct: float | None
    input_hash: str | None
    provenance: dict | None


class ReportSummary(BaseModel):
    not_loaded: int
    not_run: int
    blocked: int
    ran: int
    both_routes: int
    mean_difference_m: float | None
    mean_difference_pct: float | None


class EvaluationReport(BaseModel):
    rows: list[ReportRow]
    summary: ReportSummary
    catalog_version: str
    synthetic: bool
