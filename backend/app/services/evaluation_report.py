"""The S01 to S10 report, derived from saved runs and validations.

Every case always appears. A case whose newest validation failed is blocked
even if an older run exists, and a run older than a change to its records is
out of date and left out of the averages, because neither describes the case
as it stands. A method with no route carries no distance, here or in the CSV.
"""

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import workspace_owner_id
from app.evaluation.catalog_loader import CATALOG_VERSION, _moment, read_catalog
from app.models.optimization_run import (
    ALGORITHM_GREEDY,
    ALGORITHM_OR_TOOLS,
    OptimizationRun,
)
from app.models.scenario import Scenario
from app.models.scenario_validation import ScenarioValidation
from app.models.user import User
from app.services.optimization import comparison_difference
from app.services.validation import (
    _scenario_depot,
    _scenario_facility,
    _scenario_points,
    _scenario_vehicles,
)

CSV_COLUMNS = (
    "code", "name", "state", "edited", "matches_expected", "reasons",
    "greedy_status", "greedy_distance_m", "or_tools_status", "or_tools_distance_m",
    "difference_m", "difference_pct", "input_hash",
    "catalog_version", "ortools_version", "road_dataset", "time_limit_s",
)
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _newest_validation(db: Session, scenario: Scenario) -> ScenarioValidation | None:
    return db.scalar(
        select(ScenarioValidation)
        .where(ScenarioValidation.scenario_id == scenario.id)
        .order_by(ScenarioValidation.id.desc())
        .limit(1)
    )


def newest_batch(db: Session, scenario: Scenario) -> dict[str, OptimizationRun] | None:
    newest = db.scalar(
        select(OptimizationRun)
        .where(OptimizationRun.scenario_id == scenario.id, OptimizationRun.batch_id.is_not(None))
        .order_by(OptimizationRun.id.desc())
        .limit(1)
    )
    if newest is None:
        return None
    runs = db.scalars(select(OptimizationRun).where(OptimizationRun.batch_id == newest.batch_id))
    return {run.algorithm: run for run in runs}


def scenario_records(scenario: Scenario) -> list:
    return [
        scenario,
        _scenario_depot(scenario),
        _scenario_facility(scenario),
        *_scenario_vehicles(scenario),
        *_scenario_points(scenario),
    ]


def _inputs(depot, facility, vehicles, points, shift) -> tuple:
    return (
        (float(depot[0]), float(depot[1])),
        (float(facility[0]), float(facility[1]), float(facility[2])),
        sorted(float(capacity) for capacity in vehicles),
        sorted((float(p[0]), float(p[1]), float(p[2]), p[3]) for p in points),
        shift,
    )


def _is_edited(scenario: Scenario, case: dict) -> bool:
    """Whether the scenario's inputs still match its catalogue file."""
    depot = _scenario_depot(scenario)
    facility = _scenario_facility(scenario)
    shift = case["shift"] or {}
    loaded = _inputs(
        (depot.latitude, depot.longitude),
        (facility.latitude, facility.longitude, facility.capacity_kg),
        [vehicle.capacity_kg for vehicle in _scenario_vehicles(scenario)],
        [
            (p.latitude, p.longitude, p.waste_kg, p.available_from)
            for p in _scenario_points(scenario)
        ],
        (scenario.shift_start, scenario.shift_end),
    )
    return loaded != _inputs(
        (case["depot"]["latitude"], case["depot"]["longitude"]),
        (
            case["facility"]["latitude"], case["facility"]["longitude"],
            case["facility"]["capacity_kg"],
        ),
        case["vehicle_capacities_kg"],
        [
            (p["latitude"], p["longitude"], p["waste_kg"], _moment(p["available_from"]))
            for p in case["points"]
        ],
        (_moment(shift.get("start")), _moment(shift.get("end"))),
    )


def _matches_expected(row: dict, case: dict) -> bool | None:
    """Whether the outcome is the one the catalogue expects, once there is one."""
    expected = case["expected"]["outcome"]
    if row["state"] == "blocked":
        return expected == "blocked"
    if row["state"] in ("ran", "out_of_date"):
        return expected == "routes" and row["or_tools"]["distance_m"] is not None
    return None


def _method(run: OptimizationRun, facility_capacity_kg: float) -> dict:
    loads = [
        {key: route[key] for key in ("vehicle_name", "load_kg", "capacity_kg")}
        for route in run.routes or []
    ]
    return {
        "status": run.status,
        "message": run.message,
        "distance_m": run.total_distance_m,
        "vehicle_loads": loads,
        "facility_load_kg": sum(load["load_kg"] for load in loads),
        "facility_capacity_kg": facility_capacity_kg,
    }


def _row(db: Session, case: dict, scenario: Scenario | None) -> dict:
    row = {
        "code": case["code"], "name": case["name"], "purpose": case["purpose"],
        "state": "not_loaded", "scenario_id": None, "errors": [],
        "greedy": None, "or_tools": None, "difference_m": None, "difference_pct": None,
        "input_hash": None, "provenance": None, "edited": False, "matches_expected": None,
    }
    if scenario is None:
        return row

    row.update(
        name=scenario.name, scenario_id=scenario.id, state="not_run",
        edited=_is_edited(scenario, case),
    )
    validation = _newest_validation(db, scenario)
    if validation is not None and not validation.can_optimize:
        row.update(state="blocked", errors=[*validation.errors, *validation.warnings])
        row["matches_expected"] = _matches_expected(row, case)
        return row

    batch = newest_batch(db, scenario)
    if batch is None:
        return row

    capacity = float(_scenario_facility(scenario).capacity_kg)
    greedy, or_tools = batch[ALGORITHM_GREEDY], batch[ALGORITHM_OR_TOOLS]
    difference_m, difference_pct = comparison_difference(
        greedy.total_distance_m, or_tools.total_distance_m
    )
    changed = max(record.updated_at for record in scenario_records(scenario))
    row.update(
        state="out_of_date" if changed > greedy.created_at else "ran",
        greedy=_method(greedy, capacity),
        or_tools=_method(or_tools, capacity),
        difference_m=difference_m,
        difference_pct=difference_pct,
        input_hash=greedy.input_hash,
        provenance=greedy.provenance,
    )
    row["matches_expected"] = _matches_expected(row, case)
    return row


def _summary(rows: list[dict]) -> dict:
    compared = [
        row for row in rows if row["state"] == "ran" and row["difference_m"] is not None
    ]

    def mean(field: str) -> float | None:
        if not compared:
            return None
        return round(sum(row[field] for row in compared) / len(compared), 2)

    summary = {
        state: sum(row["state"] == state for row in rows)
        for state in ("not_loaded", "not_run", "blocked", "ran", "out_of_date")
    }
    return {
        **summary,
        "both_routes": len(compared),
        "mean_difference_m": mean("difference_m"),
        "mean_difference_pct": mean("difference_pct"),
    }


def build_report(db: Session, user: User) -> dict:
    scenarios = {
        scenario.evaluation_code: scenario
        for scenario in db.scalars(
            select(Scenario).where(
                Scenario.user_id == workspace_owner_id(user), Scenario.evaluation_code.is_not(None)
            )
        )
    }
    rows = [_row(db, case, scenarios.get(case["code"])) for case in read_catalog()]
    return {
        "rows": rows,
        "summary": _summary(rows),
        "catalog_version": CATALOG_VERSION,
        "synthetic": True,
    }


def _safe_cell(value: object) -> object:
    """Stop a spreadsheet reading text as a formula. Numbers stay numbers."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return f"'{value}"
    return value


def report_csv(report: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in report["rows"]:
        greedy = row["greedy"] or {}
        or_tools = row["or_tools"] or {}
        provenance = row["provenance"] or {}
        reasons = [f"{error['code']}: {error['message']}" for error in row["errors"]]
        for method in (greedy, or_tools):
            if method.get("message"):
                reasons.append(method["message"])
        cells = {
            "code": row["code"], "name": row["name"], "state": row["state"],
            "edited": row["edited"], "matches_expected": row["matches_expected"],
            "reasons": "; ".join(reasons),
            "greedy_status": greedy.get("status"),
            "greedy_distance_m": greedy.get("distance_m"),
            "or_tools_status": or_tools.get("status"),
            "or_tools_distance_m": or_tools.get("distance_m"),
            "difference_m": row["difference_m"],
            "difference_pct": row["difference_pct"],
            "input_hash": row["input_hash"],
            "catalog_version": provenance.get("catalog_version"),
            "ortools_version": provenance.get("ortools_version"),
            "road_dataset": provenance.get("road_dataset"),
            "time_limit_s": provenance.get("time_limit_s"),
        }
        writer.writerow({key: _safe_cell(value) for key, value in cells.items()})
    return output.getvalue()
