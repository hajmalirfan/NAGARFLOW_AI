from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import build_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def read_dashboard_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require("dashboard.read")),
) -> DashboardSummary:
    """Every figure the dashboard shows, for the signed-in coordinator."""
    return build_dashboard_summary(db, user)
