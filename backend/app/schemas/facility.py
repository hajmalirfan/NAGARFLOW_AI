from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FacilityStatus = Literal["active", "inactive"]


class FacilityWrite(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    facility_code: str = Field(min_length=1, max_length=50)
    address: str = Field(default="", max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Must be greater than zero: a facility with no capacity cannot receive
    # a delivery, so it could never satisfy W1 + W2 <= F.
    total_capacity_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    status: FacilityStatus = "active"
    description: str = Field(default="", max_length=5000)

    @field_validator("name", "facility_code")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value

    @field_validator("facility_code")
    @classmethod
    def normalize_facility_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("address", "description")
    @classmethod
    def trim_optional_text(cls, value: str) -> str:
        return value.strip()


class FacilityResponse(BaseModel):
    id: int
    name: str
    facility_code: str
    address: str | None
    latitude: float
    longitude: float
    total_capacity_kg: float
    status: FacilityStatus
    description: str | None
    created_at: datetime
    updated_at: datetime


class FacilityScenarioAllocation(BaseModel):
    id: int
    reference: str
    name: str
    allocated_kg: float


class FacilityCapacityResponse(BaseModel):
    """Shared capacity across every delivery made to this facility.

    ``allocated_kg`` is the waste that linked scenarios commit to this
    facility. Once the optimization engine records real deliveries it
    becomes the delivered total; until then it is what the configured
    scenarios would deliver.
    """

    id: int
    name: str
    facility_code: str
    total_capacity_kg: float
    allocated_kg: float
    remaining_capacity_kg: float
    is_within_capacity: bool
    status: FacilityStatus
    scenarios: list[FacilityScenarioAllocation]
