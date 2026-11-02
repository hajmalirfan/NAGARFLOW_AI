from pydantic import BaseModel


class ScenarioName(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class PreviewStop(BaseModel):
    code: str
    name: str
    quantity_kg: float | None
    # Seconds after the vehicle leaves the depot.
    arrival_s: int
    wait_s: int


class PreviewRoute(BaseModel):
    vehicle_name: str
    stops: list[PreviewStop]


class RoutePreview(BaseModel):
    scenario_name: str
    method: str
    out_of_date: bool
    routes: list[PreviewRoute]


class PreviewVehicleLoad(BaseModel):
    vehicle_name: str
    load_kg: float
    capacity_kg: float


class FacilityPreview(BaseModel):
    scenario_name: str
    method: str
    out_of_date: bool
    expected_total_kg: float
    facility_capacity_kg: float
    vehicles: list[PreviewVehicleLoad]
