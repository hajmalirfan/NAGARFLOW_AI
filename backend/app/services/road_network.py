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
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from app.core.config import settings
from app.services.validation import (
    NullRoadNetwork,
    RoadCheckResult,
    RoadLocation,
    RoadNetwork,
)

logger = logging.getLogger(__name__)

Node = tuple[float, float]  # (longitude, latitude), rounded

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

COORDINATE_PLACES = 7
METRES_PER_DEGREE = 111320
# Half a degree of latitude's length, which keeps a grid cell wider than the
# snap limit in longitude as well as latitude at any latitude below 60 degrees.
METRES_PER_CELL_DEGREE = METRES_PER_DEGREE / 2

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
    groups: dict[Node, int]  # nodes sharing a number reach each other


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
    groups = {
        node: number
        for number, members in enumerate(nx.strongly_connected_components(graph))
        for node in members
    }
    return RoadGraph(
        graph=graph, segments=segments, cells=cells, cell_deg=cell_deg, groups=groups
    )


@dataclass(frozen=True)
class _Snap:
    """Where a location attaches to the road network."""

    segment_index: int
    fraction: float  # how far along the segment, from 0 at its start


class GeoPackageRoadNetwork:
    """Answers whether a scenario's trip can be driven."""

    def __init__(self, road_graph: RoadGraph, snap_max_m: float) -> None:
        self.road_graph = road_graph
        self.snap_max_m = snap_max_m

    def _snap(self, location: RoadLocation) -> _Snap | None:
        """Attach a location to its nearest segment within the limit."""
        road_graph = self.road_graph
        centre_x, centre_y = _cell(location.longitude, location.latitude, road_graph.cell_deg)
        candidates = {
            index
            for x in range(centre_x - 1, centre_x + 2)
            for y in range(centre_y - 1, centre_y + 2)
            for index in road_graph.cells.get((x, y), ())
        }

        # Flat metres around the location, which is accurate at this range.
        metres_x = METRES_PER_DEGREE * math.cos(math.radians(location.latitude))

        def project(node: Node) -> tuple[float, float]:
            return (
                (node[0] - location.longitude) * metres_x,
                (node[1] - location.latitude) * METRES_PER_DEGREE,
            )

        best: tuple[float, int, float] | None = None
        for index in sorted(candidates):
            segment = road_graph.segments[index]
            start_x, start_y = project(segment.start)
            end_x, end_y = project(segment.end)
            run_x, run_y = end_x - start_x, end_y - start_y
            fraction = -(start_x * run_x + start_y * run_y) / (run_x**2 + run_y**2)
            fraction = max(0.0, min(1.0, fraction))
            distance = math.hypot(start_x + fraction * run_x, start_y + fraction * run_y)
            if best is None or distance < best[0]:
                best = (distance, index, fraction)

        if best is None or best[0] > self.snap_max_m:
            return None
        return _Snap(segment_index=best[1], fraction=best[2])

    def check(
        self, depot: RoadLocation, points: list[RoadLocation], facility: RoadLocation
    ) -> RoadCheckResult:
        """Test every route the trip shape requires.

        Depot to every point, every point to every other point (either
        vehicle may visit them in any order), and every point to the
        facility. The facility needs no route back, as the trip ends there.
        """
        graph, groups = self.road_graph.graph, self.road_graph.groups
        segments = self.road_graph.segments
        snaps = {
            location.name: self._snap(location) for location in (depot, *points, facility)
        }
        too_far = [name for name, snap in snaps.items() if snap is None]
        reachable: dict[Node, set[Node]] = {}

        def connected(source: _Snap, target: _Snap) -> bool:
            # Two spots on one segment: on a one-way road the end nodes alone
            # would say a dead end cannot reach a spot just ahead on it.
            if source.segment_index == target.segment_index and (
                segments[source.segment_index].two_way or source.fraction <= target.fraction
            ):
                return True
            leaves_by = segments[source.segment_index].end
            enters_by = segments[target.segment_index].start
            if groups[leaves_by] == groups[enters_by]:
                return True
            if leaves_by not in reachable:
                reachable[leaves_by] = nx.descendants(graph, leaves_by) | {leaves_by}
            return enters_by in reachable[leaves_by]

        routes = [(depot.name, point.name) for point in points]
        routes.extend(
            (first.name, second.name) for first in points for second in points if first != second
        )
        routes.extend((point.name, facility.name) for point in points)

        unreachable = [
            f"{source} → {target}"
            for source, target in routes
            if snaps[source] is not None
            and snaps[target] is not None
            and not connected(snaps[source], snaps[target])
        ]
        return RoadCheckResult(too_far=too_far, unreachable=unreachable)


ROAD_NETWORK_UNAVAILABLE_WARNING = {
    "code": "ROAD_NETWORK_UNAVAILABLE",
    "message": (
        "Road connectivity has not been checked because the road network could "
        "not be loaded. A scenario is not marked valid until connectivity is "
        "verified."
    ),
}

_network: GeoPackageRoadNetwork | None = None
_load_lock = threading.Lock()


def get_road_network() -> RoadNetwork:
    """The process-wide road network, built on first use.

    A failed load is not kept, so repairing the file needs no restart.
    """
    global _network
    if _network is not None:
        return _network
    if not settings.road_network_path:
        return NullRoadNetwork()

    with _load_lock:
        if _network is not None:
            return _network
        path = REPOSITORY_ROOT / settings.road_network_path
        started = time.perf_counter()
        try:
            road_graph = load_road_graph(path, settings.road_snap_max_m)
        except RoadDataError as error:
            logger.error("Road network unavailable: %s", error)
            return NullRoadNetwork(ROAD_NETWORK_UNAVAILABLE_WARNING)
        logger.info(
            "Loaded road network with %s segments in %.1f s.",
            len(road_graph.segments),
            time.perf_counter() - started,
        )
        _network = GeoPackageRoadNetwork(road_graph, settings.road_snap_max_m)
        return _network


def reset_road_network() -> None:
    """Forget the loaded network, so each test chooses its own."""
    global _network
    _network = None
