from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base

ALGORITHM_GREEDY = "greedy"
ALGORITHM_OR_TOOLS = "or_tools"

SUCCESSFUL_STATUSES = ("feasible", "optimal")
FAILED_STATUSES = ("no_solution", "infeasible", "timeout", "invalid_result")


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
    # Null unless a checked route exists: no result is ever shown as 0 m.
    total_distance_m: Mapped[float | None] = mapped_column(Float, default=None)
    # Greedy and OR-Tools from one request share a batch.
    batch_id: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    solve_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    routes: Mapped[list | None] = mapped_column(JSON, default=None)
    input_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    # What produced this result: catalogue, road data, solver and limits.
    provenance: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    scenario: Mapped["Scenario"] = relationship(back_populates="optimization_runs")  # noqa: F821
