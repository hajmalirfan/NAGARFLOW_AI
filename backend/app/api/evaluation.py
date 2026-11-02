from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require
from app.evaluation.catalog_loader import load_catalog
from app.models.user import User
from app.schemas.evaluation import EvaluationReport, LoadedCase
from app.services.evaluation_report import build_report, report_csv

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/scenarios", response_model=list[LoadedCase])
def load_evaluation_scenarios(
    db: Session = Depends(get_db),
    user: User = Depends(require("records.write")),
) -> list[LoadedCase]:
    """Create the synthetic S01 to S10 cases this coordinator does not have yet."""
    return [
        LoadedCase(code=scenario.evaluation_code, scenario_id=scenario.id, name=scenario.name)
        for scenario in load_catalog(db, user)
    ]


@router.get("/report", response_model=EvaluationReport)
def read_evaluation_report(
    db: Session = Depends(get_db),
    user: User = Depends(require("reports.read")),
) -> dict:
    """Every S01 to S10 case and how it last went."""
    return build_report(db, user)


@router.get("/report.csv")
def download_evaluation_report(
    db: Session = Depends(get_db),
    user: User = Depends(require("reports.read")),
) -> Response:
    return Response(
        content=report_csv(build_report(db, user)),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="nagarflow-evaluation.csv"'},
    )
