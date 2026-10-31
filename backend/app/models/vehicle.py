from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base


class Vehicle(Base):
    """A collection vehicle.

    Under the approved MVP rules a scenario has two vehicles, each
    starting empty and making at most one trip.
    """

    __tablename__ = "vehicles"
    __table_args__ = (CheckConstraint("capacity_kg > 0", name="positive_capacity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True, default=None
    )
    vehicle_number: Mapped[str | None] = mapped_column(String(30), unique=True, default=None)
    name: Mapped[str] = mapped_column(String(100))
    vehicle_type: Mapped[str | None] = mapped_column(String(50), default=None)
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    depot_id: Mapped[int | None] = mapped_column(
        ForeignKey("depots.id", ondelete="RESTRICT"), index=True, default=None
    )
    status: Mapped[str] = mapped_column(String(30), default="available", nullable=False)
    start_latitude: Mapped[float] = mapped_column(Float)
    start_longitude: Mapped[float] = mapped_column(Float)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    scenario: Mapped["Scenario"] = relationship(back_populates="vehicles")  # noqa: F821
    depot: Mapped["Depot | None"] = relationship()  # noqa: F821
