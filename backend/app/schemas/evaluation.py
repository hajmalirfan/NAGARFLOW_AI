from pydantic import BaseModel


class LoadedCase(BaseModel):
    code: str
    scenario_id: int
    name: str
