import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.depots import router as depots_router
from app.api.routes import router
from app.api.scenarios import router as scenarios_router
from app.api.storage_points import router as storage_points_router
from app.api.vehicles import router as vehicles_router
from app.core.config import settings
from app.db.base import Base
from app.db.migrations import (
    upgrade_legacy_depot_schema,
    upgrade_legacy_storage_point_schema,
    upgrade_legacy_vehicle_schema,
)
from app.db.session import engine

# Importing app.models before create_all runs registers every table on
# Base.metadata.
import app.models  # noqa: F401

API_V1_PREFIX = "/api/v1"

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    upgrade_legacy_depot_schema(engine)
    upgrade_legacy_vehicle_schema(engine)
    upgrade_legacy_storage_point_schema(engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(router, prefix=API_V1_PREFIX, include_in_schema=False)

app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(dashboard_router, prefix=API_V1_PREFIX)
app.include_router(depots_router, prefix=API_V1_PREFIX)
app.include_router(scenarios_router, prefix=API_V1_PREFIX)
app.include_router(storage_points_router, prefix=API_V1_PREFIX)
app.include_router(vehicles_router, prefix=API_V1_PREFIX)
# The original unversioned paths stay mounted so anything already
# pointing at /auth/* keeps working. They are hidden from the API docs,
# which document /api/v1 only.
app.include_router(auth_router, include_in_schema=False)
