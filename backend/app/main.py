import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.depots import router as depots_router
from app.api.evaluation import router as evaluation_router
from app.api.facilities import router as facilities_router
from app.api.history import router as history_router
from app.api.routes import router
from app.api.scenarios import router as scenarios_router
from app.api.storage_points import router as storage_points_router
from app.api.vehicles import router as vehicles_router
from app.core.config import settings
from app.db.base import Base
from app.db.migrations import (
    upgrade_legacy_depot_schema,
    upgrade_legacy_facility_schema,
    upgrade_legacy_evaluation_schema,
    upgrade_legacy_optimization_run_schema,
    upgrade_legacy_scenario_schema,
    upgrade_legacy_storage_point_schema,
    upgrade_legacy_user_schema,
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
    upgrade_legacy_user_schema(engine)
    upgrade_legacy_depot_schema(engine)
    upgrade_legacy_vehicle_schema(engine)
    upgrade_legacy_storage_point_schema(engine)
    upgrade_legacy_facility_schema(engine)
    upgrade_legacy_scenario_schema(engine)
    upgrade_legacy_optimization_run_schema(engine)
    upgrade_legacy_evaluation_schema(engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


# Registered before CORS so it runs inside it: a browser can only read a
# 500 that carries the CORS headers.
@app.middleware("http")
async def report_unexpected_errors(request: Request, call_next) -> Response:
    """Log an unexpected failure and give the caller a reference, not internals."""
    try:
        return await call_next(request)
    except Exception:
        reference = uuid4().hex[:8]
        logging.getLogger(__name__).exception("Unexpected error, reference %s.", reference)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on the server.", "reference": reference},
        )


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
app.include_router(evaluation_router, prefix=API_V1_PREFIX)
app.include_router(facilities_router, prefix=API_V1_PREFIX)
app.include_router(history_router, prefix=API_V1_PREFIX)
app.include_router(scenarios_router, prefix=API_V1_PREFIX)
app.include_router(storage_points_router, prefix=API_V1_PREFIX)
app.include_router(vehicles_router, prefix=API_V1_PREFIX)
# The original unversioned paths stay mounted so anything already
# pointing at /auth/* keeps working. They are hidden from the API docs,
# which document /api/v1 only.
app.include_router(auth_router, include_in_schema=False)
