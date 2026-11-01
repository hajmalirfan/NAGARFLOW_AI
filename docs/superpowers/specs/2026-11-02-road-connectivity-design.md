# Step 10 completion: road connectivity check

**Date:** 2026-11-02
**Status:** Design approved in conversation; awaiting review of this written spec.

## Goal

Finish Step 10 by replacing `NullRoadNetwork` with a real road check built from the Trichy OpenStreetMap GeoPackage. A scenario can then reach `valid` because its locations were actually checked against roads, and an unreachable location fails with a named error.

Success means:

- A scenario that passes every check, including `road_connectivity`, is `valid` and `can_optimize` is true, with `REQUIRE_ROAD_CONNECTIVITY` left at its default of true.
- A location that cannot take part in the trip makes the scenario `invalid`, and the error names it.
- If the road network cannot be used, the scenario is `incomplete`. It never passes by default.

## Scope

**In scope:** the road graph loader, the connectivity check, its wiring into validation, configuration, the map default centre, and related documentation.

**Out of scope:** road distance or travel time (Step 12), showing roads or routes on a map (Steps 11 and 16), algorithms, a truck dimension or weight profile, turn restrictions, and any change to DEC-003 availability logic.

## Authority for this work

`Problem statement and requirements.txt` and `implementation_roadmap.md` say not to implement before the boundary and road network are approved. The project owner chose on 2026-11-02 to proceed with this dataset for Step 10. That decision covers this check only. It does not make the OSM data a validated municipal record, and no output may be presented as one.

## Dataset

- File: `docs/dataset/planet_78.163_11.047_55136793-geopackage/planet_78.163_11.047_55136793.gpkg` (35 MB, MD5 `7a49c60500312d0dc4b932fda4b957ed`, matches `CHECKSUM.txt`).
- Source: BBBike extract of OpenStreetMap, EPSG:4326, requested rectangle 78.163–79.005°E, 10.301–11.385°N. Trichy lies well inside it.
- Layer used: `lines`, columns `geom`, `highway`, `other_tags`.

An undirected probe on 2026-11-02 found 36,930 drivable ways, 292,789 vertices and 49 connected groups. The largest group holds 99.6% of vertices, and 67,319 of the 67,396 vertices inside the bounding box of the OSM "Trichy Corporation Limits" feature. Ways share 53,415 exact vertices. This supersedes the finding in `osm_dataset_analysis.md` that topology cannot be recovered, but the probe ignored direction, so it does not prove directed reachability. The whole extract is used and nothing is clipped, so the unresolved study boundary does not block this check.

## Road rules

**Included `highway` values:** `motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `unclassified`, `residential`, `service`, `living_street`, `road`, and `motorway_link`, `trunk_link`, `primary_link`, `secondary_link`, `tertiary_link`.

**Everything else is excluded**, including `track`, `path`, `footway`, `steps`, `corridor`, `cycleway`, `pedestrian`, `busway` and `construction`.

**Excluded by tag:** `access=private`, `access=no`, `motor_vehicle=private`, `motor_vehicle=no`. A road with no access tag counts as usable.

**Direction:** roads are two-way by default. `oneway=yes` and `junction=roundabout` follow the coordinate order. `oneway=-1` follows the reverse order. It does not occur in this extract, but it is handled. `oneway=no` is two-way and takes precedence over a roundabout tag.

**Junctions:** two ways connect only at an identical vertex, compared after rounding to 7 decimal places. Geometric crossings without a shared vertex do not connect.

**Snapping:** each location attaches to the nearest point on any road segment, not the nearest vertex. Distance is measured in metres with an equirectangular projection at the location's latitude. The limit is `ROAD_SNAP_MAX_M`, default 200. **The 200 m value is an assumption, not a measured figure.** A segment gives a location an exit node (the segment's end) and an entry node (the segment's start). On a two-way segment, either end can serve as both, because the two are mutually reachable.

**Required reachability** for one depot D, points P, and one facility F:

1. D reaches every point in P.
2. Every point in P reaches every other point in P.
3. Every point in P reaches F.

F does not need a route back to D.

## Components

### `backend/app/services/road_network.py` (new)

- `load_road_graph(path) -> RoadGraph`: reads the GeoPackage through the standard library `sqlite3` module in read-only mode, parses the WKB geometry, applies the road rules, and builds a directed `networkx` graph plus a grid index of segments. This is the only code that knows the GeoPackage format.
- The grid index uses cells at least as wide as the snap limit, so a search of a location's cell and its eight neighbours is guaranteed to include every segment in range.
- `GeoPackageRoadNetwork`: holds a `RoadGraph` and implements `RoadNetwork`. It runs one forward reachability search from D and from each point, so a scenario costs at most 11 searches.
- `get_road_network() -> RoadNetwork`: returns a process-wide instance, built on first use behind a `threading.Lock` so concurrent validations build it once. A failed load is not cached.

### `backend/app/services/validation.py`

The `RoadNetwork` protocol changes, because a list of names cannot express why a location failed:

```python
@dataclass(frozen=True)
class RoadLocation:
    name: str
    latitude: float
    longitude: float

@dataclass
class RoadCheckResult:
    too_far: list[str]           # location names beyond the snap limit
    unreachable: list[str]       # failed required pairs, as "A → B"

class RoadNetwork(Protocol):
    def check(
        self, depot: RoadLocation, points: list[RoadLocation], facility: RoadLocation
    ) -> RoadCheckResult | None: ...
```

`None` keeps its meaning: no road network is available to answer. `NullRoadNetwork` stays as the fallback.

Rule 10 in `validate_scenario` changes as follows:

- If a depot or facility is missing, or the `coordinates` check failed, `road_connectivity` stays `not_checked` and the road network is not called. The scenario is already `invalid`.
- `None` keeps `not_checked` and adds a warning.
- A location in `too_far` is left out of the pair checks, so it does not also produce unreachable errors.
- A non-empty `too_far` adds `ROAD_TOO_FAR`, naming each location with the limit in metres.
- A non-empty `unreachable` adds `ROAD_UNREACHABLE`. The message lists the first five pairs and the number of others.
- Both errors can appear on one report. Either one sets the check to `failed`.
- Otherwise the check is `passed`.

### Other backend changes

- `api/scenarios.py`: the validate endpoint calls `validate_scenario(db, scenario, get_road_network())`.
- `core/config.py`: adds `road_network_path: str = ""` and `road_snap_max_m: float = 200`. A relative path resolves from the repository root.
- `.env.example`: documents both, with `ROAD_NETWORK_PATH` set to the dataset path above.
- `requirements.txt`: adds `networkx`.

### Frontend

- `LocationMap.jsx`: `INITIAL_CENTER` moves to central Trichy, `[78.6856, 10.8050]`, because the current 10.89918, 79.54393 is about 58 km east of the extract. It remains a view position, not a stored location.
- `FacilityMap.jsx` and `StoragePointMap.jsx`: update the description text with those coordinates, along with the OpenStreetMap link in `LocationMap.jsx`.
- `ValidationReport.jsx`: no change. It already renders any error, warning and check result.

### Repository and documentation

- `.gitignore`: adds `*.gpkg`. The dataset stays local.
- `README.md` and `NAGARFLOW_AI_Master_Guide.pdf`: describe the setup and the check, and correct the map centre text in the README.
- `osm_dataset_analysis.md`: gains a dated note that this finding is superseded. The rest of the document is left as written.

## Failure handling

| Situation | Check | Scenario | Warning |
|---|---|---|---|
| `ROAD_NETWORK_PATH` empty | `not_checked` | `incomplete` | `ROAD_NETWORK_NOT_CONFIGURED` |
| File missing or unreadable, not a GeoPackage, no `lines` layer, or no usable roads | `not_checked` | `incomplete` | `ROAD_NETWORK_UNAVAILABLE`, with the cause logged |

The unavailable warning needs the engine to tell the two cases apart. `get_road_network()` returns a `NullRoadNetwork` carrying a `warning` code and message, which the engine reports in place of the default. Each validation retries a failed load, so repairing the file needs no restart.

`REQUIRE_ROAD_CONNECTIVITY=false` stays as the explicit, logged development override.

## Known limitations

- **Turn restrictions are not modelled**, because the file does not contain them. A pass means a route exists on the network, not that a truck may legally take it. This also applies to Step 12 distances.
- A road with no access tag counts as usable. Truck width, weight and height limits are not checked.
- A vertex shared by ways at different grade would connect them. This is believed to be rare, because OSM mappers do not normally share nodes across a grade separation, but it has not been measured.
- Graph load time is unmeasured. The first validation after a server start pays for it. The real-data test records the figure.

## Testing

Tests follow the existing style in `backend/tests/` and are written first.

**Loader and rules, using small synthetic `.gpkg` fixtures built in the test:** each included and excluded road type, each excluding access tag, `oneway=yes`, `oneway=-1`, roundabouts, `oneway=no` on a roundabout, ways that cross without a shared vertex staying unconnected, snapping to mid-segment, and the limit on either side of 200 m.

**Reachability:** a passing case, a point that can be entered but not left, a location in a separate group, a depot that cannot reach a point, a point that cannot reach the facility, and a facility with no route back to the depot still passing.

**Validation engine, using a fake `RoadNetwork`:** `valid` on a clean result, `invalid` with `ROAD_TOO_FAR`, `invalid` with `ROAD_UNREACHABLE`, both errors together, `incomplete` with each warning, the road network not being called when coordinates failed, and the override's existing behaviour. Existing tests that use the old `unreachable` method are updated.

**Loading:** one build under concurrent first calls, a failed load being retried, and each failure case in the table above.

**Isolation:** `conftest.py` forces `ROAD_NETWORK_PATH` empty and resets the cached instance, so the default suite never reads the real dataset, even when a developer's `.env` sets it.

**Real data:** one test skips if the file is absent. It loads the Trichy dataset, confirms that locations on city roads connect, and records load time.

The full backend suite, frontend suite and Vite build must pass before Step 10 is called complete. The frontend tests must be updated for any assertion on the old map text.

## Done when

1. The tests above pass, and the existing suites still pass.
2. In the running app, with `ROAD_NETWORK_PATH` set, a scenario with real coordinates in Trichy validates as `valid`, and moving a location more than 200 m from any road gives `ROAD_TOO_FAR`.
3. Measured load time is recorded in the Master Guide.
