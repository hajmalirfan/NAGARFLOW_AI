"""Database models.

Importing every model here means that importing ``app.models`` (or any
single model through it) registers all tables on ``Base.metadata``.
Without this, a module that imports only one model would fail on flush,
because its foreign keys could not find the tables they point at.
"""

from app.models.depot import Depot
from app.models.optimization_run import OptimizationRun
from app.models.password_reset_token import PasswordResetToken
from app.models.processing_facility import ProcessingFacility
from app.models.scenario import Scenario
from app.models.storage_point import StoragePoint
from app.models.user import User
from app.models.vehicle import Vehicle

__all__ = [
    "Depot",
    "OptimizationRun",
    "PasswordResetToken",
    "ProcessingFacility",
    "Scenario",
    "StoragePoint",
    "User",
    "Vehicle",
]
