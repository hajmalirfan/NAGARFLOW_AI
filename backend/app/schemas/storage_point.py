from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


AvailabilityStatus = Literal["available", "unavailable"]


class StoragePointWrite(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    point_code: str = Field(min_length=1, max_length=50)
    address: str = Field(default="", max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    waste_quantity_kg: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    availability_status: AvailabilityStatus = "available"
    available_from: datetime | None = None
    description: str = Field(default="", max_length=5000)

    @field_validator("name", "point_code")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value

    @field_validator("point_code")
    @classmethod
    def normalize_point_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("address", "description")
    @classmethod
    def trim_optional_text(cls, value: str) -> str:
        return value.strip()


class StoragePointResponse(BaseModel):
    id: int
    name: str
    point_code: str
    address: str | None
    latitude: float
    longitude: float
    waste_quantity_kg: float
    availability_status: AvailabilityStatus
    available_from: datetime | None
    description: str | None
    created_at: datetime
    updated_at: datetime
