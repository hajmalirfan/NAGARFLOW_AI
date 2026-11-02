from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# A team account can never be a planner.
TeamRole = Literal["reviewer", "management", "driver", "facility"]


class TeamMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: TeamRole
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Please enter a name.")
        return value.strip()


class TeamMemberRole(BaseModel):
    role: TeamRole


class TeamMember(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str

    model_config = {"from_attributes": True}
