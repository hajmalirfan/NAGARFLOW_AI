"""All ten catalogue cases on the Trichy dataset, which is local only and may be absent."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.evaluation.catalog_loader import load_catalog, read_catalog
from app.models import User
from app.services.optimization import optimize_scenario
from app.services.road_network import GeoPackageRoadNetwork, load_road_graph
from app.services.validation import validate_scenario

DATASET = (
    Path(__file__).resolve().parents[2]
    / "docs/dataset/planet_78.163_11.047_55136793-geopackage"
    / "planet_78.163_11.047_55136793.gpkg"
)
SNAP_M = 200.0
TIME_LIMIT_S = 10


@pytest.mark.skipif(not DATASET.is_file(), reason="Trichy dataset is not present")
def test_every_case_matches_its_expected_outcome(
    client: TestClient, registered_user: dict[str, str], db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "optimizer_time_limit_s", TIME_LIMIT_S)
    network = GeoPackageRoadNetwork(load_road_graph(DATASET, SNAP_M), SNAP_M)
    user = db_session.scalar(select(User).where(User.email == registered_user["email"]))
    scenarios = {s.evaluation_code: s for s in load_catalog(db_session, user)}

    print()
    for case in read_catalog():
        report = validate_scenario(db_session, scenarios[case["code"]], network)
        codes = {error["code"] for error in report.errors}
        if case["expected"]["outcome"] == "blocked":
            print(case["code"], "blocked", sorted(codes))
            assert report.can_optimize is False
            assert set(case["expected"]["error_codes"]) <= codes
            continue

        assert report.can_optimize is True, (case["code"], report.errors)
        greedy, or_tools = optimize_scenario(db_session, scenarios[case["code"]], network)
        waits = sum(stop["wait_s"] for route in or_tools.routes for stop in route["stops"])
        print(
            case["code"], greedy.status, greedy.total_distance_m, greedy.message, "|",
            or_tools.status, or_tools.total_distance_m, or_tools.message, "| waits", waits,
        )
        # Greedy may fail a tight case; OR-Tools must find what the case expects.
        assert or_tools.status == "feasible", case["code"]
        if greedy.total_distance_m is not None:
            assert or_tools.total_distance_m <= greedy.total_distance_m, case["code"]
        if case["code"] == "S06":
            assert waits > 0
