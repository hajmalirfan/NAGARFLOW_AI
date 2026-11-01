"""Road distance and time between a scenario's locations.

Both algorithms receive the one matrix built here, so they compare on
identical costs. ``None`` means no path: it is never a large number, which
could otherwise be mistaken for a long route.
"""

from dataclasses import dataclass

import numpy as np
from scipy.sparse.csgraph import dijkstra

from app.services.road_network import (
    GeoPackageRoadNetwork,
    Node,
    Snap,
    road_speed_kmh,
)
from app.services.validation import RoadLocation

__all__ = ["CostMatrix", "build_cost_matrix", "road_speed_kmh", "route_geometry"]

NO_PREDECESSOR = -9999


@dataclass
class CostMatrix:
    names: list[str]
    distance_m: list[list[int | None]]
    time_s: list[list[int | None]]


@dataclass
class _Leg:
    distance_m: float
    time_s: float
    path: list[Node]  # road nodes between the two snap points


def _whole(value: float) -> int:
    """Whole units, where a real cost never rounds down to nothing."""
    return max(1, round(value)) if value > 0 else 0


class _RoadSearch:
    """Shortest paths from a set of snapped locations."""

    def __init__(self, network: GeoPackageRoadNetwork, snaps: list[Snap]) -> None:
        self.road_graph = network.road_graph
        self.segments = self.road_graph.segments
        sources = sorted({
            self.road_graph.node_index[node]
            for snap in snaps
            for node, _ in self._exits(snap)
        })
        self.row = {index: row for row, index in enumerate(sources)}
        self.distances, self.predecessors = dijkstra(
            self.road_graph.distance_csr, indices=sources, return_predecessors=True
        )

    def _exits(self, snap: Snap) -> list[tuple[Node, float]]:
        """Nodes a vehicle can leave by, with the share of the segment driven."""
        segment = self.segments[snap.segment_index]
        exits = [(segment.end, 1 - snap.fraction)]
        if segment.two_way:
            exits.append((segment.start, snap.fraction))
        return exits

    def _entries(self, snap: Snap) -> list[tuple[Node, float]]:
        """Nodes a vehicle can arrive by, with the share of the segment driven."""
        segment = self.segments[snap.segment_index]
        entries = [(segment.start, snap.fraction)]
        if segment.two_way:
            entries.append((segment.end, 1 - snap.fraction))
        return entries

    def _path(self, source: Node, target: Node) -> list[Node]:
        road_graph = self.road_graph
        row = self.row[road_graph.node_index[source]]
        index = road_graph.node_index[target]
        path = [target]
        while (index := int(self.predecessors[row, index])) != NO_PREDECESSOR:
            path.append(road_graph.nodes[index])
        path.reverse()
        return path

    def leg(self, source: Snap, target: Snap) -> _Leg | None:
        """The shortest drive between two snap points, or ``None``."""
        from_segment = self.segments[source.segment_index]
        to_segment = self.segments[target.segment_index]

        if source.segment_index == target.segment_index:
            share = target.fraction - source.fraction
            if share >= 0 or from_segment.two_way:
                return _Leg(
                    abs(share) * from_segment.length_m, abs(share) * from_segment.time_s, []
                )

        node_index = self.road_graph.node_index
        best: tuple[float, Node, Node, float, float] | None = None
        for leaves_by, leave_share in self._exits(source):
            row = self.row[node_index[leaves_by]]
            for enters_by, enter_share in self._entries(target):
                road = self.distances[row, node_index[enters_by]]
                if not np.isfinite(road):
                    continue
                total = (
                    leave_share * from_segment.length_m
                    + road
                    + enter_share * to_segment.length_m
                )
                if best is None or total < best[0]:
                    best = (total, leaves_by, enters_by, leave_share, enter_share)
        if best is None:
            return None

        total, leaves_by, enters_by, leave_share, enter_share = best
        path = self._path(leaves_by, enters_by)
        graph = self.road_graph.graph
        road_time = sum(graph[a][b]["time_s"] for a, b in zip(path, path[1:]))
        time_s = leave_share * from_segment.time_s + road_time + enter_share * to_segment.time_s
        return _Leg(total, time_s, path)


def _snap_all(network: GeoPackageRoadNetwork, locations: list[RoadLocation]) -> list[Snap]:
    snaps = [network.snap(location) for location in locations]
    missing = [loc.name for loc, snap in zip(locations, snaps) if snap is None]
    if missing:
        raise ValueError(f"Not on the road network: {', '.join(missing)}")
    return snaps


def build_cost_matrix(
    network: GeoPackageRoadNetwork, locations: list[RoadLocation]
) -> CostMatrix:
    """Directed distance and time between every pair of locations."""
    snaps = _snap_all(network, locations)
    search = _RoadSearch(network, snaps)
    size = len(locations)
    distance: list[list[int | None]] = [[0] * size for _ in range(size)]
    time: list[list[int | None]] = [[0] * size for _ in range(size)]
    for first in range(size):
        for second in range(size):
            if first == second:
                continue
            leg = search.leg(snaps[first], snaps[second])
            distance[first][second] = None if leg is None else _whole(leg.distance_m)
            time[first][second] = None if leg is None else _whole(leg.time_s)
    return CostMatrix([location.name for location in locations], distance, time)


def route_geometry(
    network: GeoPackageRoadNetwork, source: RoadLocation, target: RoadLocation
) -> list[tuple[float, float]]:
    """The road line between two locations, as ``(longitude, latitude)`` points."""
    snaps = _snap_all(network, [source, target])
    leg = _RoadSearch(network, snaps).leg(*snaps)
    if leg is None:
        return []
    return [
        (source.longitude, source.latitude),
        *leg.path,
        (target.longitude, target.latitude),
    ]
