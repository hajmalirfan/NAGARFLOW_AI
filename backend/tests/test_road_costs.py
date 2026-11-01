"""Road cost tests, with distances worked out by hand on synthetic roads."""

from pathlib import Path

import pytest

from app.services.road_costs import build_cost_matrix, road_speed_kmh, route_geometry
from app.services.road_network import GeoPackageRoadNetwork, load_road_graph
from app.services.validation import RoadLocation
from road_fixtures import write_gpkg

SNAP_M = 200.0
METRES_PER_0_01_DEGREE = 1112
ONE_WAY = '"oneway"=>"yes"'
SOUTH = (78.70, 10.80)
NORTH = (78.70, 10.81)
EAST = (78.71, 10.81)


def network(path: Path, ways: list) -> GeoPackageRoadNetwork:
    return GeoPackageRoadNetwork(
        load_road_graph(write_gpkg(path / "roads.gpkg", ways), SNAP_M), SNAP_M
    )


def at(name: str, node: tuple[float, float]) -> RoadLocation:
    return RoadLocation(name, node[1], node[0])


def along(start: tuple[float, float], end: tuple[float, float], share: float) -> tuple[float, float]:
    return start[0] + (end[0] - start[0]) * share, start[1] + (end[1] - start[1]) * share


def test_length_of_a_known_segment(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH], "")])

    matrix = build_cost_matrix(roads, [at("A", SOUTH), at("B", NORTH)])

    assert matrix.distance_m[0][1] == pytest.approx(METRES_PER_0_01_DEGREE, abs=2)


@pytest.mark.parametrize("highway, speed", [
    ("motorway", 50), ("motorway_link", 50), ("trunk", 50), ("trunk_link", 50),
    ("primary", 40), ("primary_link", 40), ("secondary", 35), ("secondary_link", 35),
    ("tertiary", 30), ("tertiary_link", 30), ("unclassified", 25), ("road", 25),
    ("residential", 20), ("living_street", 20), ("service", 15),
])
def test_speed_by_road_type(highway: str, speed: int) -> None:
    assert road_speed_kmh(highway) == speed


def test_time_uses_the_road_type_speed(tmp_path: Path) -> None:
    roads = network(tmp_path, [("residential", [SOUTH, NORTH], "")])

    matrix = build_cost_matrix(roads, [at("A", SOUTH), at("B", NORTH)])

    assert matrix.time_s[0][1] == pytest.approx(200, abs=1)


def test_cost_counts_part_segments_from_each_snap(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH], "")])
    first, second = along(SOUTH, NORTH, 0.25), along(SOUTH, NORTH, 0.75)

    matrix = build_cost_matrix(roads, [at("A", first), at("B", second)])

    assert matrix.distance_m[0][1] == pytest.approx(556, abs=2)
    assert matrix.distance_m[1][0] == pytest.approx(556, abs=2)


def test_part_segments_join_a_longer_route(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH, EAST], "")])
    first, second = along(SOUTH, NORTH, 0.5), along(NORTH, EAST, 0.5)

    matrix = build_cost_matrix(roads, [at("A", first), at("B", second)])

    assert matrix.distance_m[0][1] == pytest.approx(556 + 546, abs=3)


def test_one_way_costs_differ_by_direction(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH, EAST, SOUTH], ONE_WAY)])

    matrix = build_cost_matrix(roads, [at("A", SOUTH), at("B", NORTH)])

    assert matrix.distance_m[0][1] == pytest.approx(1112, abs=2)
    assert matrix.distance_m[1][0] > 2000


def test_no_path_is_none(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH], ONE_WAY)])

    matrix = build_cost_matrix(roads, [at("A", NORTH), at("B", SOUTH)])

    assert matrix.distance_m[0][1] is None
    assert matrix.time_s[0][1] is None


def test_same_location_costs_zero_not_none(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH], ONE_WAY)])
    spot = along(SOUTH, NORTH, 0.5)

    matrix = build_cost_matrix(roads, [at("A", spot), at("B", spot)])

    assert matrix.distance_m[0][1] == 0
    assert matrix.time_s[0][1] == 0


def test_short_leg_never_rounds_to_zero(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH], "")])
    first = along(SOUTH, NORTH, 0.5)
    second = (first[0], first[1] + 0.000003)

    matrix = build_cost_matrix(roads, [at("A", first), at("B", second)])

    assert matrix.distance_m[0][1] == 1


def test_shortest_path_prefers_distance_over_time(tmp_path: Path) -> None:
    fast_detour = [SOUTH, EAST, NORTH]
    slow_direct = [SOUTH, NORTH]
    roads = network(tmp_path, [("trunk", fast_detour, ""), ("service", slow_direct, "")])

    matrix = build_cost_matrix(roads, [at("A", SOUTH), at("B", NORTH)])

    assert matrix.distance_m[0][1] == pytest.approx(1112, abs=2)
    assert matrix.time_s[0][1] == pytest.approx(267, abs=2)


def test_route_geometry_follows_the_road(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [SOUTH, NORTH, EAST], "")])
    first, second = along(SOUTH, NORTH, 0.5), along(NORTH, EAST, 0.5)

    line = route_geometry(roads, at("A", first), at("B", second))

    assert line[0] == pytest.approx(first)
    assert line[-1] == pytest.approx(second)
    assert NORTH in line
