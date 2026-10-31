from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProcessingFacility(Base):
    """The facility where collected waste is delivered.

    ``capacity_kg`` is one shared limit across every vehicle delivery,
    not a per-vehicle allowance.
    """

    __tablename__ = "processing_facilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    capacity_kg: Mapped[float] = mapped_column(Float)

    scenario: Mapped["Scenario"] = relationship(back_populates="facilities")  # noqa: F821
