from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DepotWrite(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=50)
    address: str | None = Field(default=None, max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_active: bool = True

    @field_validator("name", "code")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("address")
    @classmethod
    def trim_address(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class DepotResponse(BaseModel):
    id: int
    name: str
    code: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
