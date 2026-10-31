from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base


class ScenarioValidation(Base):
    """One recorded run of the validation engine.

    Every validation is kept, pass or fail, so the decision that let a
    scenario reach the optimizer (or stopped it) can be reviewed later
    alongside the data it was based on.
    """

    __tablename__ = "scenario_validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    validation_status: Mapped[str] = mapped_column(String(20))
    can_optimize: Mapped[bool] = mapped_column(Boolean, default=False)
    checks: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    total_waste_kg: Mapped[float] = mapped_column(default=0.0)
    storage_point_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    scenario: Mapped["Scenario"] = relationship()  # noqa: F821
