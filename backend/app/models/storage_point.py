from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StoragePoint(Base):
    """A waste collection point that a vehicle must visit.

    The whole quantity at a point is collected by exactly one vehicle:
    the approved MVP rule forbids splitting a point across vehicles.
    """

    __tablename__ = "storage_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    waste_kg: Mapped[float] = mapped_column(Float)
    waste_type: Mapped[str | None] = mapped_column(String(50), default=None)
    # When the waste becomes collectable. Null means it is available now.
    available_from: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    scenario: Mapped["Scenario"] = relationship(back_populates="storage_points")  # noqa: F821
