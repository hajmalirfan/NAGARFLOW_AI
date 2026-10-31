from datetime import datetime

from pydantic import BaseModel


class WasteOverview(BaseModel):
    total_waste_kg: float
    storage_points_count: int
    largest_point_kg: float
    average_point_kg: float


class VehicleSummary(BaseModel):
    id: int
    name: str
    capacity_kg: float
    is_available: bool
    scenario_reference: str


class VehicleStatus(BaseModel):
    available: list[VehicleSummary]
    unavailable: list[VehicleSummary]
    available_count: int
    unavailable_count: int
    total_available_capacity_kg: float


class StoragePointSummary(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    waste_kg: float
    waste_type: str | None
    available_from: datetime | None
    scenario_reference: str


class ScenarioSummary(BaseModel):
    id: int
    reference: str
    name: str
    status: str
    created_at: datetime
    storage_points_count: int
    vehicles_count: int


class OptimizationSummary(BaseModel):
    successful_runs: int
    failed_runs: int
    total_runs: int
    best_distance_km: float | None


class DashboardSummary(BaseModel):
    """Everything the dashboard shows, in one response.

    The six top-level numbers are the summary cards. Every one is read
    from the database for the signed-in coordinator only.
    """

    total_waste_kg: float
    storage_points_count: int
    available_vehicles_count: int
    facility_remaining_capacity_kg: float
    total_scenarios: int
    optimized_routes_count: int

    # False when no processing facility has been set up yet, so the UI can
    # show "Not configured" rather than implying a real capacity of zero.
    facility_configured: bool

    waste_overview: WasteOverview
    vehicle_status: VehicleStatus
    storage_points: list[StoragePointSummary]
    recent_scenarios: list[ScenarioSummary]
    optimization_summary: OptimizationSummary
