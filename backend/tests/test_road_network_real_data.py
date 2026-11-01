"""The Trichy dataset itself, which is local only and may be absent."""

import time
from pathlib import Path

import networkx as nx
import pytest

from app.services.road_network import GeoPackageRoadNetwork, load_road_graph
from app.services.validation import RoadCheckResult, RoadLocation

DATASET = (
    Path(__file__).resolve().parents[2]
    / "docs/dataset/planet_78.163_11.047_55136793-geopackage"
    / "planet_78.163_11.047_55136793.gpkg"
)
CITY_WEST, CITY_SOUTH, CITY_EAST, CITY_NORTH = 78.6306621, 10.7273005, 78.7835251, 10.8805108
SNAP_M = 200.0


@pytest.mark.skipif(not DATASET.is_file(), reason="Trichy dataset is not present")
def test_city_roads_connect_in_the_real_dataset() -> None:
    started = time.perf_counter()
    road_graph = load_road_graph(DATASET, SNAP_M)
    load_seconds = time.perf_counter() - started

    largest = max(nx.strongly_connected_components(road_graph.graph), key=len)
    share = len(largest) / road_graph.graph.number_of_nodes()
    city_nodes = sorted(
        node for node in largest
        if CITY_WEST <= node[0] <= CITY_EAST and CITY_SOUTH <= node[1] <= CITY_NORTH
    )
    chosen = city_nodes[:: len(city_nodes) // 8][:8]
    locations = [
        RoadLocation(f"L{index}", node[1], node[0]) for index, node in enumerate(chosen)
    ]

    roads = GeoPackageRoadNetwork(road_graph, SNAP_M)
    started = time.perf_counter()
    result = roads.check(locations[0], locations[1:7], locations[7])
    check_seconds = time.perf_counter() - started

    print(
        f"\nload {load_seconds:.1f} s, check {check_seconds:.2f} s, "
        f"{road_graph.graph.number_of_nodes()} nodes, largest directed group {share:.2%}, "
        f"{len(city_nodes)} of its nodes in the city box"
    )
    assert result == RoadCheckResult(too_far=[], unreachable=[])
