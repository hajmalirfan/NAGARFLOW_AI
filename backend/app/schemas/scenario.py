from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ScenarioStatus = Literal["draft", "ready"]


class DepotOption(BaseModel):
    id: int
    name: str


class FacilityOption(BaseModel):
    id: int
    name: str
    capacity_kg: float


class VehicleOption(BaseModel):
    id: int
    name: str
    capacity_kg: float
    is_available: bool
    depot_id: int | None = None


class StoragePointOption(BaseModel):
    id: int
    name: str
    waste_kg: float
    waste_type: str


class ScenarioWrite(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=5000)
    depot_id: int = Field(gt=0)
    facility_id: int = Field(gt=0)
    vehicle_ids: list[int] = Field(min_length=2, max_length=2)
    storage_point_ids: list[int] = Field(min_length=6, max_length=10)
    status: ScenarioStatus = "draft"

    @model_validator(mode="after")
    def selected_ids_must_be_unique(self) -> "ScenarioWrite":
        if len(set(self.vehicle_ids)) != len(self.vehicle_ids):
            raise ValueError("Select two different vehicles.")
        if len(set(self.storage_point_ids)) != len(self.storage_point_ids):
            raise ValueError("A storage point cannot be assigned more than once.")
        return self


class ScenarioOptions(BaseModel):
    depots: list[DepotOption]
    facilities: list[FacilityOption]
    vehicles: list[VehicleOption]
    storage_points: list[StoragePointOption]


class ScenarioResponse(BaseModel):
    id: int
    reference: str
    name: str
    description: str
    status: str
    depot: DepotOption | None
    processing_facility: FacilityOption | None
    vehicles: list[VehicleOption]
    storage_points: list[StoragePointOption]
    created_at: datetime
    updated_at: datetime


class ScenarioListResponse(BaseModel):
    items: list[ScenarioResponse]
