"""Road network tests.

Every road here is synthetic and built per test, so these rules are proved
without the real dataset. Coordinates are ``(longitude, latitude)``.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import networkx as nx
import pytest

from app.core.config import settings
from app.services import road_network
from app.services.road_network import (
    GeoPackageRoadNetwork,
    RoadDataError,
    get_road_network,
    load_road_graph,
)
from app.services.validation import NullRoadNetwork, RoadCheckResult, RoadLocation
from road_fixtures import write_gpkg

SNAP_M = 200.0
A = (78.70, 10.80)
B = (78.71, 10.80)
C = (78.72, 10.80)


def load(path: Path, ways: list) -> nx.DiGraph:
    return load_road_graph(write_gpkg(path / "roads.gpkg", ways), SNAP_M).graph


# --- Which roads count -------------------------------------------------


@pytest.mark.parametrize("highway", [
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "service", "living_street", "road", "motorway_link",
    "trunk_link", "primary_link", "secondary_link", "tertiary_link",
])
def test_truck_roads_are_included(highway: str, tmp_path: Path) -> None:
    assert load(tmp_path, [(highway, [A, B], "")]).has_edge(A, B)


@pytest.mark.parametrize("highway", [
    "track", "path", "footway", "steps", "corridor", "cycleway",
    "pedestrian", "busway", "construction",
])
def test_other_road_types_are_excluded(highway: str, tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [B, C], ""), (highway, [A, B], "")])

    assert not graph.has_node(A)


@pytest.mark.parametrize("tags", [
    '"access"=>"private"', '"access"=>"no"',
    '"motor_vehicle"=>"private"', '"motor_vehicle"=>"no"',
])
def test_refused_access_is_excluded(tags: str, tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [B, C], ""), ("service", [A, B], tags)])

    assert not graph.has_node(A)


def test_other_access_values_stay_usable(tmp_path: Path) -> None:
    graph = load(tmp_path, [("service", [A, B], '"access"=>"customers"')])

    assert graph.has_edge(A, B)


# --- Direction ---------------------------------------------------------


def test_two_way_by_default(tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [A, B], "")])

    assert graph.has_edge(A, B) and graph.has_edge(B, A)


def test_oneway_follows_coordinate_order(tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [A, B], '"oneway"=>"yes"')])

    assert graph.has_edge(A, B) and not graph.has_edge(B, A)


def test_oneway_minus_one_reverses(tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [A, B], '"oneway"=>"-1"')])

    assert graph.has_edge(B, A) and not graph.has_edge(A, B)


def test_roundabout_is_one_way(tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [A, B], '"junction"=>"roundabout"')])

    assert graph.has_edge(A, B) and not graph.has_edge(B, A)


def test_oneway_no_overrides_roundabout(tmp_path: Path) -> None:
    tags = '"junction"=>"roundabout","oneway"=>"no"'

    graph = load(tmp_path, [("primary", [A, B], tags)])

    assert graph.has_edge(A, B) and graph.has_edge(B, A)


def test_unrecognised_oneway_value_stays_two_way(tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [A, B], '"oneway"=>"reversible"')])

    assert graph.has_edge(A, B) and graph.has_edge(B, A)


# --- Junctions ---------------------------------------------------------


def test_ways_crossing_without_a_shared_vertex_stay_separate(tmp_path: Path) -> None:
    west_east = [(78.70, 10.80), (78.72, 10.80)]
    south_north = [(78.71, 10.79), (78.71, 10.81)]

    graph = load(tmp_path, [("trunk", west_east, ""), ("residential", south_north, "")])

    assert not nx.has_path(graph, west_east[0], south_north[0])


def test_ways_sharing_a_vertex_connect(tmp_path: Path) -> None:
    graph = load(tmp_path, [("primary", [A, B], ""), ("primary", [B, C], "")])

    assert nx.has_path(graph, A, C)


def test_vertices_match_after_rounding_to_seven_places(tmp_path: Path) -> None:
    ways = [
        ("primary", [A, (78.71000001, 10.80)], ""),
        ("primary", [(78.71000004, 10.80), C], ""),
    ]

    assert nx.has_path(load(tmp_path, ways), A, C)


# --- Bad input ---------------------------------------------------------


def test_malformed_geometry_row_is_skipped(tmp_path: Path) -> None:
    ways = [("primary", [A, B], ""), ("primary", None, ""), ("primary", b"junk", "")]

    assert load(tmp_path, ways).has_edge(A, B)


def test_truncated_geometry_row_is_skipped(tmp_path: Path) -> None:
    from road_fixtures import encode_line

    ways = [("primary", [A, B], ""), ("primary", encode_line([A, C])[:-4], "")]

    assert not load(tmp_path, ways).has_node(C)


def test_path_with_spaces_loads(tmp_path: Path) -> None:
    graph = load(tmp_path / "folder with spaces", [("primary", [A, B], "")])

    assert graph.has_edge(A, B)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RoadDataError):
        load_road_graph(tmp_path / "absent.gpkg", SNAP_M)


def test_non_geopackage_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "notes.gpkg"
    path.write_text("not a database")

    with pytest.raises(RoadDataError):
        load_road_graph(path, SNAP_M)


def test_missing_lines_table_raises(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "empty.gpkg"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE other (id INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(RoadDataError):
        load_road_graph(path, SNAP_M)


def test_no_usable_roads_raises(tmp_path: Path) -> None:
    path = write_gpkg(tmp_path / "paths.gpkg", [("footway", [A, B], "")])

    with pytest.raises(RoadDataError):
        load_road_graph(path, SNAP_M)


# --- Segment index -----------------------------------------------------


def test_every_segment_is_indexed_in_each_cell_it_spans(tmp_path: Path) -> None:
    path = write_gpkg(tmp_path / "roads.gpkg", [("trunk", [A, C], "")])

    road_graph = load_road_graph(path, SNAP_M)

    def cell(node: tuple[float, float]) -> tuple[int, int]:
        return int(node[0] // road_graph.cell_deg), int(node[1] // road_graph.cell_deg)

    assert road_graph.cells[cell(A)] == [0]
    assert road_graph.cells[cell(C)] == [0]
    assert road_graph.cells[cell(B)] == [0]


# --- Snapping and reachability -----------------------------------------

METRES_PER_DEGREE = 111320
SPINE = [A, B, C]
ONE_WAY = '"oneway"=>"yes"'
# X lies off the spine: a stub from B to X is a dead end if one-way.
X = (78.71, 10.81)
Y = (78.71, 10.79)


def network(path: Path, ways: list) -> GeoPackageRoadNetwork:
    return GeoPackageRoadNetwork(
        load_road_graph(write_gpkg(path / "roads.gpkg", ways), SNAP_M), SNAP_M
    )


def at(name: str, node: tuple[float, float], north_m: float = 0) -> RoadLocation:
    return RoadLocation(name, node[1] + north_m / METRES_PER_DEGREE, node[0])


def along(start: tuple[float, float], end: tuple[float, float], share: float) -> tuple[float, float]:
    return start[0] + (end[0] - start[0]) * share, start[1] + (end[1] - start[1]) * share


def spine_check(path: Path, location: RoadLocation) -> RoadCheckResult:
    return network(path, [("primary", SPINE, "")]).check(
        at("DEP", A), [location, at("SP-2", B)], at("FAC", C)
    )


def test_all_locations_connected_passes(tmp_path: Path) -> None:
    assert spine_check(tmp_path, at("SP-1", along(A, B, 0.5))) == RoadCheckResult([], [])


def test_snaps_to_the_middle_of_a_long_segment(tmp_path: Path) -> None:
    far_vertex = (78.90, 10.80)
    roads = network(tmp_path, [("primary", [A, far_vertex], "")])

    result = roads.check(
        at("DEP", A), [at("SP-1", along(A, far_vertex, 0.5), north_m=50)], at("FAC", far_vertex)
    )

    assert result == RoadCheckResult([], [])


def test_location_just_inside_the_limit_attaches(tmp_path: Path) -> None:
    result = spine_check(tmp_path, at("SP-1", along(A, B, 0.5), north_m=190))

    assert result.too_far == []


def test_location_just_outside_the_limit_is_too_far(tmp_path: Path) -> None:
    result = spine_check(tmp_path, at("SP-1", along(A, B, 0.5), north_m=210))

    assert result.too_far == ["SP-1"]


def test_location_outside_the_extract_is_too_far(tmp_path: Path) -> None:
    result = spine_check(tmp_path, RoadLocation("SP-1", 10.89918, 79.54393))

    assert result.too_far == ["SP-1"]


def test_too_far_location_is_left_out_of_pair_checks(tmp_path: Path) -> None:
    result = spine_check(tmp_path, RoadLocation("SP-9", 10.89918, 79.54393))

    assert result.too_far == ["SP-9"]
    assert result.unreachable == []


def test_too_far_depot_and_facility_are_named(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, "")])
    far = RoadLocation("DEP", 12.0, 79.0)
    also_far = RoadLocation("FAC", 12.5, 79.5)

    result = roads.check(far, [at("SP-1", A), at("SP-2", C)], also_far)

    assert result == RoadCheckResult(["DEP", "FAC"], [])


def test_point_that_can_be_entered_but_not_left(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, ""), ("service", [B, X], ONE_WAY)])

    result = roads.check(
        at("DEP", A), [at("SP-1", along(B, X, 0.5)), at("SP-2", C)], at("FAC", C)
    )

    assert set(result.unreachable) == {"SP-1 → SP-2", "SP-1 → FAC"}


def test_location_in_a_separate_road_group(tmp_path: Path) -> None:
    island = [(78.80, 10.90), (78.81, 10.90)]
    roads = network(tmp_path, [("primary", SPINE, ""), ("primary", island, "")])

    result = roads.check(at("DEP", A), [at("SP-1", island[0]), at("SP-2", B)], at("FAC", C))

    assert result.too_far == []
    assert "DEP → SP-1" in result.unreachable
    assert "SP-2 → SP-1" in result.unreachable
    assert "SP-1 → FAC" in result.unreachable


def test_depot_that_cannot_reach_a_point(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, ""), ("service", [Y, B], ONE_WAY)])

    result = roads.check(
        at("DEP", A), [at("SP-1", along(Y, B, 0.5)), at("SP-2", C)], at("FAC", C)
    )

    assert set(result.unreachable) == {"DEP → SP-1", "SP-2 → SP-1"}


def test_point_that_cannot_reach_the_facility(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, ""), ("service", [Y, B], ONE_WAY)])

    result = roads.check(
        at("DEP", A), [at("SP-1", A), at("SP-2", C)], at("FAC", along(Y, B, 0.5))
    )

    assert set(result.unreachable) == {"SP-1 → FAC", "SP-2 → FAC"}


def test_facility_needs_no_route_back_to_the_depot(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, ""), ("service", [B, X], ONE_WAY)])

    result = roads.check(
        at("DEP", A), [at("SP-1", A), at("SP-2", C)], at("FAC", along(B, X, 0.5))
    )

    assert result == RoadCheckResult([], [])


def test_same_one_way_segment_connects_forward_only(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [A, B], ONE_WAY)])

    result = roads.check(
        at("DEP", along(A, B, 0.1)),
        [at("SP-1", along(A, B, 0.25)), at("SP-2", along(A, B, 0.75))],
        at("FAC", along(A, B, 0.9)),
    )

    assert result == RoadCheckResult([], ["SP-2 → SP-1"])


def test_same_one_way_segment_with_a_loop_connects_both_ways(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [A, B, X, A], ONE_WAY)])

    result = roads.check(
        at("DEP", along(A, B, 0.1)),
        [at("SP-1", along(A, B, 0.25)), at("SP-2", along(A, B, 0.75))],
        at("FAC", along(A, B, 0.9)),
    )

    assert result == RoadCheckResult([], [])


def test_identical_coordinates_connect(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", [A, B], ONE_WAY)])
    spot = along(A, B, 0.5)

    result = roads.check(
        at("DEP", along(A, B, 0.1)), [at("SP-1", spot), at("SP-2", spot)], at("FAC", B)
    )

    assert result == RoadCheckResult([], [])


# --- Loading once per process ------------------------------------------


def use_path(monkeypatch: pytest.MonkeyPatch, path: Path | str) -> None:
    monkeypatch.setattr(settings, "road_network_path", str(path))


def test_empty_path_gives_the_not_configured_network(monkeypatch: pytest.MonkeyPatch) -> None:
    use_path(monkeypatch, "")

    assert get_road_network().warning["code"] == "ROAD_NETWORK_NOT_CONFIGURED"


def test_missing_file_gives_the_unavailable_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_path(monkeypatch, tmp_path / "absent.gpkg")

    assert get_road_network().warning["code"] == "ROAD_NETWORK_UNAVAILABLE"


def test_failed_load_is_retried_once_the_file_is_fixed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "roads.gpkg"
    use_path(monkeypatch, path)
    assert isinstance(get_road_network(), NullRoadNetwork)

    write_gpkg(path, [("primary", [A, B], "")])

    assert isinstance(get_road_network(), GeoPackageRoadNetwork)


def test_concurrent_first_calls_build_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    use_path(monkeypatch, write_gpkg(tmp_path / "roads.gpkg", [("primary", [A, B], "")]))
    builds: list[int] = []
    real_load = road_network.load_road_graph

    def counting_load(path: Path, snap_max_m: float):
        builds.append(1)
        time.sleep(0.05)
        return real_load(path, snap_max_m)

    monkeypatch.setattr(road_network, "load_road_graph", counting_load)
    barrier = threading.Barrier(8)

    def first_call(_: int):
        barrier.wait()
        return get_road_network()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(first_call, range(8)))

    assert len(builds) == 1
    assert all(result is results[0] for result in results)


def test_relative_path_resolves_from_the_repository_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_gpkg(tmp_path / "data" / "roads.gpkg", [("primary", [A, B], "")])
    monkeypatch.setattr(road_network, "REPOSITORY_ROOT", tmp_path)
    use_path(monkeypatch, "data/roads.gpkg")

    assert isinstance(get_road_network(), GeoPackageRoadNetwork)


def test_routes_within_one_connected_group_need_no_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roads = network(tmp_path, [("primary", SPINE, "")])

    def refuse_search(*args: object) -> None:
        raise AssertionError("searched the whole graph")

    monkeypatch.setattr(road_network.nx, "descendants", refuse_search)

    result = roads.check(at("DEP", A), [at("SP-1", B), at("SP-2", B)], at("FAC", C))

    assert result == RoadCheckResult([], [])


# --- Found in review ---------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_coordinates_skip_the_row(bad: float, tmp_path: Path) -> None:
    ways = [("primary", [A, B], ""), ("primary", [(bad, 10.80), (78.73, 10.80)], "")]

    assert load(tmp_path, ways).has_edge(A, B)


def test_binary_tags_skip_the_row(tmp_path: Path) -> None:
    ways = [("primary", [A, B], ""), ("primary", [B, C], b" binary")]

    assert not load(tmp_path, ways).has_node(C)


def test_off_road_depot_sharing_a_point_code_is_still_too_far(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, "")])
    depot = RoadLocation("SHARED", 12.0, 70.0)

    result = roads.check(depot, [at("SHARED", A), at("SP-2", B)], at("FAC", C))

    assert result.too_far == ["SHARED"]


def test_off_road_point_sharing_the_facility_code_is_still_too_far(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, "")])
    point = RoadLocation("SHARED", 12.0, 70.0)

    result = roads.check(at("DEP", A), [point, at("SP-2", B)], at("SHARED", C))

    assert result.too_far == ["SHARED"]


def test_location_sharing_a_code_is_checked_at_its_own_place(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, ""), ("service", [Y, B], ONE_WAY)])
    point = at("SHARED", along(Y, B, 0.5))

    result = roads.check(at("DEP", A), [point, at("SP-2", C)], at("SHARED", C))

    assert "DEP → SHARED" in result.unreachable


def test_a_shared_code_is_named_once(tmp_path: Path) -> None:
    roads = network(tmp_path, [("primary", SPINE, "")])
    far = RoadLocation("SHARED", 12.0, 70.0)

    result = roads.check(far, [far, at("SP-2", B)], at("FAC", C))

    assert result.too_far == ["SHARED"]
