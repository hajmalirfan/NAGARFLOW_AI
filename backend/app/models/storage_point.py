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


class StoragePoint(Base):
    """A coordinator-managed collection location available to scenarios."""

    __tablename__ = "storage_points"
    __table_args__ = (
        CheckConstraint("waste_kg >= 0", name="valid_waste_quantity"),
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
    point_code: Mapped[str] = mapped_column(String(50), unique=True)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    waste_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    availability_status: Mapped[str] = mapped_column(
        String(30), default="available", nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    # These fields remain for compatibility with the earlier planning schema.
    waste_type: Mapped[str | None] = mapped_column(String(50), default=None)
    available_from: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    scenario: Mapped["Scenario | None"] = relationship(back_populates="storage_points")  # noqa: F821
