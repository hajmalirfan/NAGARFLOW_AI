from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


VehicleType = Literal["Truck", "Mini Truck"]
VehicleStatus = Literal["available", "maintenance", "inactive"]


class VehicleWrite(BaseModel):
    vehicle_number: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    vehicle_type: VehicleType
    capacity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    depot_id: int = Field(gt=0)
    status: VehicleStatus = "available"

    @field_validator("vehicle_number", "name")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value

    @field_validator("vehicle_number")
    @classmethod
    def normalize_vehicle_number(cls, value: str) -> str:
        return value.upper()


class VehicleDepot(BaseModel):
    id: int
    name: str
    code: str | None

    model_config = {"from_attributes": True}


class VehicleResponse(BaseModel):
    id: int
    vehicle_number: str | None
    name: str
    vehicle_type: str | None
    capacity_kg: float
    depot: VehicleDepot | None
    status: str
    is_available: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VehicleOption(BaseModel):
    id: int
    vehicle_number: str
    name: str
    vehicle_type: str
    capacity_kg: float
    depot_id: int
    status: VehicleStatus
    is_available: bool
