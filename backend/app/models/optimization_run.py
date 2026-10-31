from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base

ALGORITHM_GREEDY = "greedy"
ALGORITHM_OR_TOOLS = "or_tools"

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


class OptimizationRun(Base):
    """The recorded outcome of one algorithm run on one scenario.

    Rows are written only by a real optimization run, so the dashboard's
    optimized-route count can never show a result that was not actually
    produced.
    """

    __tablename__ = "optimization_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    algorithm: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    total_distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    scenario: Mapped["Scenario"] = relationship(back_populates="optimization_runs")  # noqa: F821
