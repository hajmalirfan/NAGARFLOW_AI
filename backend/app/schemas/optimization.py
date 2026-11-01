from datetime import datetime

from pydantic import BaseModel


class MethodRun(BaseModel):
    status: str
    total_distance_m: float | None
    solve_ms: int | None
    message: str | None
    routes: list[dict]


class OptimizationComparison(BaseModel):
    scenario_id: int
    batch_id: str
    created_at: datetime
    input_hash: str | None
    provenance: dict | None = None
    greedy: MethodRun
    or_tools: MethodRun
    # Greedy minus OR-Tools, so a positive figure means OR-Tools was shorter.
    # Null unless both methods produced a checked route.
    difference_m: float | None
    difference_pct: float | None


class HistoryRow(BaseModel):
    scenario_id: int
    scenario_name: str
    batch_id: str
    created_at: datetime
    greedy_status: str
    greedy_distance_m: float | None
    or_tools_status: str
    or_tools_distance_m: float | None
    difference_m: float | None


class HistoryPage(BaseModel):
    items: list[HistoryRow]
    total: int
