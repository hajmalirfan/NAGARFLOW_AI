"""Road network tests.

Every road here is synthetic and built per test, so these rules are proved
without the real dataset. Coordinates are ``(longitude, latitude)``.
"""

from pathlib import Path

import networkx as nx
import pytest

from app.services.road_network import RoadDataError, load_road_graph
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
