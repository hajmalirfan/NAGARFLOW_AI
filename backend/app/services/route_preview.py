"""Read-only previews of a saved run, for driver and facility accounts.

Only the newest batch counts. An older route is never shown in place of a
failed run, because it would describe a plan that was since replaced.
"""

from sqlalchemy.orm import Session

from app.models.optimization_run import (
    ALGORITHM_GREEDY,
    ALGORITHM_OR_TOOLS,
    OptimizationRun,
)
from app.models.scenario import Scenario
from app.schemas.preview import FacilityPreview, RoutePreview
from app.services.evaluation_report import newest_batch, scenario_records
from app.services.validation import _scenario_facility, _scenario_points

ROUTE_STATUSES = {"feasible", "optimal"}


def preview_run(db: Session, scenario: Scenario) -> OptimizationRun | None:
    """The newest batch's OR-Tools run, or Greedy's when OR-Tools has no route."""
    batch = newest_batch(db, scenario) or {}
    for algorithm in (ALGORITHM_OR_TOOLS, ALGORITHM_GREEDY):
        run = batch.get(algorithm)
        if run is not None and run.status in ROUTE_STATUSES and run.routes:
            return run
    return None


def _out_of_date(scenario: Scenario, run: OptimizationRun) -> bool:
    return max(record.updated_at for record in scenario_records(scenario)) > run.created_at


def route_preview(scenario: Scenario, run: OptimizationRun) -> RoutePreview:
    points = {point.point_code: point for point in _scenario_points(scenario)}

    def stop(saved: dict) -> dict:
        point = points.get(saved["code"])
        return {
            "code": saved["code"],
            "name": point.name if point else saved["code"],
            "quantity_kg": float(point.waste_kg) if point else None,
            "arrival_s": saved["arrival_s"],
            "wait_s": saved["wait_s"],
        }

    return RoutePreview(
        scenario_name=scenario.name,
        method=run.algorithm,
        out_of_date=_out_of_date(scenario, run),
        routes=[
            {"vehicle_name": route["vehicle_name"], "stops": [stop(s) for s in route["stops"]]}
            for route in run.routes
        ],
    )


def facility_preview(scenario: Scenario, run: OptimizationRun) -> FacilityPreview:
    return FacilityPreview(
        scenario_name=scenario.name,
        method=run.algorithm,
        out_of_date=_out_of_date(scenario, run),
        expected_total_kg=sum(route["load_kg"] for route in run.routes),
        facility_capacity_kg=float(_scenario_facility(scenario).capacity_kg),
        vehicles=run.routes,
    )
