from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base

scenario_depots = Table(
    "scenario_depots",
    Base.metadata,
    Column("scenario_id", ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True),
    Column("depot_id", ForeignKey("depots.id", ondelete="CASCADE"), nullable=False),
)

scenario_facilities = Table(
    "scenario_facilities",
    Base.metadata,
    Column("scenario_id", ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "facility_id",
        ForeignKey("processing_facilities.id", ondelete="CASCADE"),
        nullable=False,
    ),
)

scenario_vehicles = Table(
    "scenario_vehicles",
    Base.metadata,
    Column("scenario_id", ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True),
    Column("vehicle_id", ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True),
)

scenario_storage_points = Table(
    "scenario_storage_points",
    Base.metadata,
    Column("scenario_id", ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "storage_point_id",
        ForeignKey("storage_points.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Scenario(Base):
    """One planning scenario belonging to a municipal coordinator.

    A scenario selects coordinator-owned depots, vehicles, storage points,
    and processing facilities for an optimization run.
    """

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Human-readable identifier shown in the UI, such as SC-0001.
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # Optional shift, in Indian Standard Time. No shift means no time limit,
    # so a vehicle may wait for waste as long as it needs.
    shift_start: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    shift_end: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    storage_points: Mapped[list["StoragePoint"]] = relationship(  # noqa: F821
        back_populates="scenario"
    )
    vehicles: Mapped[list["Vehicle"]] = relationship(  # noqa: F821
        back_populates="scenario", cascade="all, delete-orphan"
    )
    facilities: Mapped[list["ProcessingFacility"]] = relationship(  # noqa: F821
        back_populates="scenario", cascade="all, delete-orphan"
    )
    optimization_runs: Mapped[list["OptimizationRun"]] = relationship(  # noqa: F821
        back_populates="scenario", cascade="all, delete-orphan"
    )
    depot: Mapped["Depot | None"] = relationship(  # noqa: F821
        secondary=scenario_depots, uselist=False
    )
    processing_facility: Mapped["ProcessingFacility | None"] = relationship(  # noqa: F821
        secondary=scenario_facilities, uselist=False
    )
    selected_vehicles: Mapped[list["Vehicle"]] = relationship(  # noqa: F821
        secondary=scenario_vehicles
    )
    selected_storage_points: Mapped[list["StoragePoint"]] = relationship(  # noqa: F821
        secondary=scenario_storage_points
    )
