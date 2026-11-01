"""Both algorithms on the Trichy dataset, which is local only and may be absent."""

import time
from pathlib import Path

import networkx as nx
import pytest

from app.services.optimizer.greedy import solve_greedy
from app.services.optimizer.ortools_solver import solve_ortools
from app.services.optimizer.result_check import check_result
from app.services.optimizer.types import RoutingProblem
from app.services.road_costs import build_cost_matrix
from app.services.road_network import GeoPackageRoadNetwork, load_road_graph
from app.services.validation import RoadLocation

DATASET = (
    Path(__file__).resolve().parents[2]
    / "docs/dataset/planet_78.163_11.047_55136793-geopackage"
    / "planet_78.163_11.047_55136793.gpkg"
)
CITY_WEST, CITY_SOUTH, CITY_EAST, CITY_NORTH = 78.6306621, 10.7273005, 78.7835251, 10.8805108
SNAP_M = 200.0
LOCATIONS = 12
TIME_LIMIT_S = 10
MATRIX_LIMIT_S = 10


@pytest.mark.skipif(not DATASET.is_file(), reason="Trichy dataset is not present")
def test_both_algorithms_on_city_roads() -> None:
    road_graph = load_road_graph(DATASET, SNAP_M)
    largest = max(nx.strongly_connected_components(road_graph.graph), key=len)
    city = sorted(
        node for node in largest
        if CITY_WEST <= node[0] <= CITY_EAST and CITY_SOUTH <= node[1] <= CITY_NORTH
    )
    chosen = city[:: len(city) // LOCATIONS][:LOCATIONS]
    locations = [RoadLocation(f"L{index:02d}", node[1], node[0]) for index, node in enumerate(chosen)]

    started = time.perf_counter()
    matrix = build_cost_matrix(GeoPackageRoadNetwork(road_graph, SNAP_M), locations)
    matrix_seconds = time.perf_counter() - started

    points = LOCATIONS - 2
    problem = RoutingProblem(
        names=matrix.names,
        demand_g=[0, *[1_000_000] * points, 0],
        ready_s=[0] * LOCATIONS,
        vehicle_ids=[1, 2],
        capacity_g=[6_000_000, 6_000_000],
        facility_capacity_g=20_000_000,
        distance_m=matrix.distance_m,
        time_s=matrix.time_s,
        shift_end_s=None,
    )
    greedy = solve_greedy(problem)
    or_tools = solve_ortools(problem, TIME_LIMIT_S)

    print(
        f"\nmatrix {matrix_seconds:.2f} s, greedy {greedy.total_distance_m} m in "
        f"{greedy.solve_ms} ms, or-tools {or_tools.total_distance_m} m in {or_tools.solve_ms} ms"
    )
    assert matrix_seconds < MATRIX_LIMIT_S
    assert check_result(problem, greedy) == []
    assert check_result(problem, or_tools) == []
    assert greedy.status == or_tools.status == "feasible"
    assert or_tools.total_distance_m <= greedy.total_distance_m
