"""The OpenStreetMap road network behind the road connectivity check.

This is the only module that knows the GeoPackage format. It reads the
``lines`` layer with the standard library and builds a directed graph plus
a grid index of road segments.

Two points are easy to get wrong and are handled explicitly:

* Roads connect only where they share an exact vertex. Two ways that merely
  cross on the map may be a flyover and a street, so a geometric crossing
  never makes a junction.
* A missing access tag counts as usable. OSM tags are sparse here, so
  requiring explicit permission would remove most of the network. Only an
  explicit refusal excludes a road.

Turn restrictions are not in this file, so a route that exists here is not
proof a truck may legally take it.
"""

import logging
import math
import re
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)

Node = tuple[float, float]  # (longitude, latitude), rounded

COORDINATE_PLACES = 7
# Half of 111,320 m per degree, which keeps a grid cell wider than the snap
# limit in longitude as well as latitude at any latitude below 60 degrees.
METRES_PER_CELL_DEGREE = 55660

TRUCK_ROADS = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "service", "living_street", "road", "motorway_link",
    "trunk_link", "primary_link", "secondary_link", "tertiary_link",
})
REFUSED_ACCESS = frozenset({"private", "no"})

# Bytes of envelope that follow the GeoPackage header, by envelope code.
ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
GEOMETRY_HEADER_BYTES = 8
WKB_LINESTRING = 2

TAG_PATTERN = re.compile(r'"([^"]+)"=>"([^"]*)"')


class RoadDataError(Exception):
    """The road dataset cannot be used."""


@dataclass(frozen=True)
class Segment:
    start: Node
    end: Node
    two_way: bool


@dataclass
class RoadGraph:
    graph: nx.DiGraph
    segments: list[Segment]
    cells: dict[tuple[int, int], list[int]]
    cell_deg: float


def _parse_line(blob: bytes) -> list[Node]:
    """Read a GeoPackage LineString, or raise if the row is malformed."""
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry")
    offset = GEOMETRY_HEADER_BYTES + ENVELOPE_BYTES[(blob[3] >> 1) & 7]
    order = "<" if blob[offset] == 1 else ">"
    kind, count = struct.unpack_from(f"{order}II", blob, offset + 1)
    if kind != WKB_LINESTRING:
        raise ValueError("not a LineString")
    values = struct.unpack_from(f"{order}{2 * count}d", blob, offset + 9)
    return [
        (round(values[i], COORDINATE_PLACES), round(values[i + 1], COORDINATE_PLACES))
        for i in range(0, len(values), 2)
    ]


def _is_refused(tags: dict[str, str]) -> bool:
    return (
        tags.get("access") in REFUSED_ACCESS
        or tags.get("motor_vehicle") in REFUSED_ACCESS
    )


def _direction(tags: dict[str, str]) -> str:
    """Whether a way runs ``both``, ``forward`` or ``reverse``."""
    oneway = tags.get("oneway")
    if oneway == "no":
        return "both"
    if oneway == "yes" or tags.get("junction") == "roundabout":
        return "forward"
    if oneway == "-1":
        return "reverse"
    return "both"


def _cell(longitude: float, latitude: float, cell_deg: float) -> tuple[int, int]:
    return math.floor(longitude / cell_deg), math.floor(latitude / cell_deg)


def _index_segment(
    cells: dict[tuple[int, int], list[int]], index: int, segment: Segment, cell_deg: float
) -> None:
    first = _cell(
        min(segment.start[0], segment.end[0]), min(segment.start[1], segment.end[1]), cell_deg
    )
    last = _cell(
        max(segment.start[0], segment.end[0]), max(segment.start[1], segment.end[1]), cell_deg
    )
    for x in range(first[0], last[0] + 1):
        for y in range(first[1], last[1] + 1):
            cells.setdefault((x, y), []).append(index)


def load_road_graph(path: Path, snap_max_m: float) -> RoadGraph:
    """Build the directed road graph, or raise ``RoadDataError``."""
    if not path.is_file():
        raise RoadDataError(f"Road network file not found: {path}")

    graph = nx.DiGraph()
    segments: list[Segment] = []
    cells: dict[tuple[int, int], list[int]] = {}
    cell_deg = snap_max_m / METRES_PER_CELL_DEGREE
    skipped = 0

    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
        try:
            rows = connection.execute(
                "SELECT highway, other_tags, geom FROM lines WHERE highway IS NOT NULL"
            )
            for highway, other_tags, geom in rows:
                if highway not in TRUCK_ROADS:
                    continue
                tags = dict(TAG_PATTERN.findall(other_tags or ""))
                if _is_refused(tags):
                    continue
                try:
                    nodes = _parse_line(geom)
                except (struct.error, KeyError, IndexError, TypeError, ValueError):
                    skipped += 1
                    continue

                direction = _direction(tags)
                if direction == "reverse":
                    nodes.reverse()
                two_way = direction == "both"
                for start, end in zip(nodes, nodes[1:]):
                    if start == end:
                        continue
                    graph.add_edge(start, end)
                    if two_way:
                        graph.add_edge(end, start)
                    segment = Segment(start, end, two_way)
                    segments.append(segment)
                    _index_segment(cells, len(segments) - 1, segment, cell_deg)
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise RoadDataError(f"Cannot read road network {path}: {error}") from error

    if skipped:
        logger.warning("Skipped %s malformed road rows in %s.", skipped, path)
    if not segments:
        raise RoadDataError(f"No usable roads found in {path}.")
    return RoadGraph(graph=graph, segments=segments, cells=cells, cell_deg=cell_deg)
