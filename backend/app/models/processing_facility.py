from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base


class ProcessingFacility(Base):
    """The facility where collected waste is delivered.

    ``capacity_kg`` is one shared limit across every vehicle delivery, not
    a per-vehicle allowance: if the facility holds 10,000 kg and vehicle 1
    brings 4,000 kg, then vehicle 2 can bring at most 6,000 kg.

    The column keeps its original name while the API exposes it as
    ``total_capacity_kg``, matching how storage points keep ``waste_kg``
    behind ``waste_quantity_kg``.
    """

    __tablename__ = "processing_facilities"
    __table_args__ = (
        CheckConstraint("capacity_kg > 0", name="positive_capacity"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="valid_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="valid_longitude"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )
    # Nullable for records from the original scenario-owned schema.
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), index=True, default=None
    )
    name: Mapped[str] = mapped_column(String(150))
    facility_code: Mapped[str] = mapped_column(String(50), unique=True)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    scenario: Mapped["Scenario | None"] = relationship(back_populates="facilities")  # noqa: F821

    @property
    def is_active(self) -> bool:
        return self.status == "active"
