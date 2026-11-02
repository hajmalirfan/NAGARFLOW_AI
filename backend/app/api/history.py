from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require
from app.api.scenarios import build_comparison
from app.core.permissions import workspace_owner_id
from app.models.optimization_run import OptimizationRun
from app.models.scenario import Scenario
from app.models.user import User
from app.schemas.optimization import HistoryPage, HistoryRow

router = APIRouter(prefix="/optimization-history", tags=["optimization-history"])


@router.get("", response_model=HistoryPage)
def read_history(
    scenario_id: int | None = None,
    status: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require("history.read")),
) -> HistoryPage:
    """One row per paired run, newest first, for this coordinator's scenarios."""
    batches = (
        select(OptimizationRun.batch_id, func.max(OptimizationRun.id).label("newest"))
        .join(Scenario, OptimizationRun.scenario_id == Scenario.id)
        .where(Scenario.user_id == workspace_owner_id(user), OptimizationRun.batch_id.is_not(None))
        .group_by(OptimizationRun.batch_id)
    )
    if scenario_id is not None:
        batches = batches.where(OptimizationRun.scenario_id == scenario_id)
    if status is not None:
        matching = select(OptimizationRun.batch_id).where(OptimizationRun.status == status)
        batches = batches.where(OptimizationRun.batch_id.in_(matching))

    total = db.scalar(select(func.count()).select_from(batches.subquery()))
    page = db.execute(
        batches.order_by(func.max(OptimizationRun.id).desc()).limit(limit).offset(offset)
    ).all()

    items = []
    for batch_id, _ in page:
        runs = list(db.scalars(
            select(OptimizationRun).where(OptimizationRun.batch_id == batch_id)
        ))
        comparison = build_comparison(runs)
        items.append(HistoryRow(
            scenario_id=comparison.scenario_id,
            scenario_name=db.get(Scenario, comparison.scenario_id).name,
            batch_id=batch_id,
            created_at=comparison.created_at,
            greedy_status=comparison.greedy.status,
            greedy_distance_m=comparison.greedy.total_distance_m,
            or_tools_status=comparison.or_tools.status,
            or_tools_distance_m=comparison.or_tools.total_distance_m,
            difference_m=comparison.difference_m,
        ))
    return HistoryPage(items=items, total=total)
