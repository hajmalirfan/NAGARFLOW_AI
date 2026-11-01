# Road Connectivity Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `NullRoadNetwork` with a real road check built from the Trichy GeoPackage, so a scenario can reach `valid` and unreachable locations fail by name.

**Architecture:** A new `services/road_network.py` reads the GeoPackage with `sqlite3`, builds a directed `networkx` graph with a grid index of segments, and implements a revised `RoadNetwork` protocol. The graph loads once per process on first use. The validation engine stays independent of the file format.

**Tech Stack:** Python, FastAPI, `networkx`, standard library `sqlite3` and `struct`, pytest, React.

**Spec:** `docs/superpowers/specs/2026-11-02-road-connectivity-design.md`

**Branch:** `feat/road-connectivity`. All commits go here.

## Global Constraints

- Snap limit default: `ROAD_SNAP_MAX_M` = 200, labelled as an assumption wherever documented.
- Vertices are compared after rounding to 7 decimal places.
- Dataset MD5: `7a49c60500312d0dc4b932fda4b957ed`. The dataset is read-only and never committed.
- Road problems never pass by default: an unusable network gives `not_checked` and `incomplete`.
- The default test suite never reads the real dataset.
- No invented municipal records. Test locations are synthetic or taken from the road data itself.
- Error codes: `ROAD_TOO_FAR`, `ROAD_UNREACHABLE`. Warning codes: `ROAD_NETWORK_NOT_CONFIGURED`, `ROAD_NETWORK_UNAVAILABLE`.

## Review Focus

1. Two locations on the same one-way segment must connect when the first comes before the second, and must not connect the other way unless a loop exists. Start and end nodes alone get this wrong. Test in Task 3.
2. Two locations at identical coordinates must count as mutually reachable. Test in Task 3.
3. A location outside the extract, such as the old 79.54°E map centre, must give `ROAD_TOO_FAR` and not an exception. Test in Task 3.
4. A malformed or NULL `geom` row must skip that row, not lose the whole network. Test in Task 2.
5. A dataset path containing spaces must load, because the repository's folders include spaces. Test in Task 2.

---

### Task 1: Validation engine contract

**Files:**
- Modify: `backend/app/services/validation.py:64-87`, `:371-397`
- Test: `backend/tests/test_validation.py`

**Interfaces:**
- Produces, all in `app.services.validation`:
  - `RoadLocation(name: str, latitude: float, longitude: float)`, a frozen dataclass.
  - `RoadCheckResult(too_far: list[str], unreachable: list[str])`, a dataclass. Entries in `unreachable` are `"A → B"`.
  - `RoadNetwork` protocol: `check(depot: RoadLocation, points: list[RoadLocation], facility: RoadLocation) -> RoadCheckResult | None`.
  - `NullRoadNetwork(warning: dict[str, str] = ROAD_NETWORK_NOT_CONFIGURED_WARNING)`, whose `check` returns `None`.
  - Constant `ROAD_NETWORK_NOT_CONFIGURED_WARNING`, a dict with the existing code and message.

- [ ] **Step 1: Confirm the baseline**

Run: `cd backend; py -m pytest -q`
Expected: all tests pass. Stop and report if any fail.

- [ ] **Step 2: Write the failing tests**

Add a `FakeRoadNetwork` helper to `test_validation.py`, taking a `RoadCheckResult | None`, recording calls in `.calls`, and with a `warning` attribute. Tests call `validate_scenario(db_session, build_scenario(db_session, registered_user["email"]), fake)` directly:

```python
def test_clean_road_check_makes_the_scenario_valid(...):
    report = run(RoadCheckResult(too_far=[], unreachable=[]))
    assert report.checks["road_connectivity"] == "passed"
    assert report.validation_status == "valid"
    assert report.can_optimize is True

def test_location_too_far_from_a_road_is_named(...):
    report = run(RoadCheckResult(too_far=["SP-1"], unreachable=[]))
    assert report.checks["road_connectivity"] == "failed"
    assert report.validation_status == "invalid"
    error = next(e for e in report.errors if e["code"] == "ROAD_TOO_FAR")
    assert "SP-1" in error["message"] and "200" in error["message"]

def test_unreachable_message_lists_five_pairs_and_counts_the_rest(...):
    pairs = [f"A{i} → B{i}" for i in range(7)]
    report = run(RoadCheckResult(too_far=[], unreachable=pairs))
    message = next(e for e in report.errors if e["code"] == "ROAD_UNREACHABLE")["message"]
    assert "A4 → B4" in message and "A5 → B5" not in message and "2 more" in message

def test_both_road_errors_appear_together(...):
    report = run(RoadCheckResult(too_far=["SP-1"], unreachable=["SP-2 → SP-3"]))
    assert {"ROAD_TOO_FAR", "ROAD_UNREACHABLE"} <= {e["code"] for e in report.errors}

def test_network_warning_is_reported_when_the_network_cannot_answer(...):
    fake = FakeRoadNetwork(None, warning={"code": "ROAD_NETWORK_UNAVAILABLE", "message": "x"})
    report = validate_scenario(db_session, scenario, fake)
    assert report.validation_status == "incomplete"
    assert "ROAD_NETWORK_UNAVAILABLE" in {w["code"] for w in report.warnings}

def test_road_check_is_skipped_when_coordinates_failed(...):
    # Give one storage point invalid coordinates in memory, without committing.
    assert fake.calls == []
    assert report.checks["road_connectivity"] == "not_checked"
    assert report.validation_status == "invalid"

def test_road_check_is_skipped_without_a_depot(...):
    # Set scenario.depot to None in memory.
    assert fake.calls == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend; py -m pytest tests/test_validation.py -q`
Expected: the new tests fail on import of `RoadCheckResult`.

- [ ] **Step 4: Implement the contract and Rule 10 in `validation.py`**

Rule 10 calls `check` only when depot and facility exist and `checks["coordinates"] == PASSED`. Use `depot.code or depot.name`, `point_code` and `facility_code` as names. When `check` returns `None`, append `getattr(network, "warning", ROAD_NETWORK_NOT_CONFIGURED_WARNING)`. `ROAD_TOO_FAR` reads `settings.road_snap_max_m`, so add that setting in `core/config.py` now as `road_snap_max_m: float = Field(default=200, gt=0)`. Replace the `settings.require_road_connectivity` comment's "before the OpenStreetMap road network lands" with "when no road network is available". Update the `NullRoadNetwork` docstring so it no longer says "until Step 11".

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend; py -m pytest tests/test_validation.py -q`
Expected: PASS, including the existing `test_road_connectivity_is_not_claimed_before_the_road_network_exists`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/validation.py backend/app/core/config.py backend/tests/test_validation.py
git commit -m "feat: let the road check report too-far and unreachable locations"
```

### Task 2: GeoPackage road graph loader

**Files:**
- Create: `backend/app/services/road_network.py`
- Create: `backend/tests/road_fixtures.py`
- Create: `backend/tests/test_road_network.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces, in `app.services.road_network`:
  - `Node = tuple[float, float]`, as (longitude, latitude) rounded to 7 places.
  - `Segment(start: Node, end: Node, two_way: bool)`, a frozen dataclass.
  - `RoadGraph(graph: nx.DiGraph, segments: list[Segment], cells: dict[tuple[int, int], list[int]], cell_deg: float)`, a dataclass.
  - `load_road_graph(path: Path, snap_max_m: float) -> RoadGraph`. Raises `RoadDataError` for an unreadable file, a missing `lines` table, or no usable roads.
  - `class RoadDataError(Exception)`.
- Produces, in `tests/road_fixtures.py`: `write_gpkg(path: Path, ways: list[tuple[str, list[Node], str]]) -> Path`. Each way is `(highway, coords, other_tags)`. It writes a `lines` table with `highway`, `other_tags` and `geom`, each geometry being a GeoPackage header (`b"GP"`, version 0, flags `0x01`, srs 4326, no envelope) followed by a little-endian WKB LineString. `write_gpkg` also accepts raw `bytes | None` in place of coords, for malformed rows.

- [ ] **Step 1: Write the failing tests**

Tests in `test_road_network.py`, using `write_gpkg` under `tmp_path`:

```python
@pytest.mark.parametrize("highway", [
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "service", "living_street", "road", "motorway_link",
    "trunk_link", "primary_link", "secondary_link", "tertiary_link",
])
def test_truck_roads_are_included(highway, tmp_path): ...  # graph has the edge

@pytest.mark.parametrize("highway", [
    "track", "path", "footway", "steps", "corridor", "cycleway",
    "pedestrian", "busway", "construction",
])
def test_other_road_types_are_excluded(highway, tmp_path): ...  # RoadDataError, no usable roads

@pytest.mark.parametrize("tags", [
    '"access"=>"private"', '"access"=>"no"',
    '"motor_vehicle"=>"private"', '"motor_vehicle"=>"no"',
])
def test_refused_access_is_excluded(tags, tmp_path): ...

def test_two_way_by_default(tmp_path):            # edges a→b and b→a
def test_oneway_follows_coordinate_order(tmp_path):      # '"oneway"=>"yes"': a→b only
def test_oneway_minus_one_reverses(tmp_path):            # b→a only
def test_roundabout_is_one_way(tmp_path):                # '"junction"=>"roundabout"'
def test_oneway_no_overrides_roundabout(tmp_path):       # both directions
def test_ways_crossing_without_a_shared_vertex_stay_separate(tmp_path):
    # Two ways crossing at a point neither has as a vertex: nx.has_path is False.
def test_ways_sharing_a_vertex_connect(tmp_path):
def test_vertices_match_after_rounding_to_seven_places(tmp_path):
    # 78.70000001 and 78.70000004 are the same node.
def test_malformed_geometry_row_is_skipped(tmp_path):
    # One good way, one NULL geom, one b"junk": loads, with the good edge.
def test_path_with_spaces_loads(tmp_path):
    # Fixture under tmp_path / "folder with spaces".
def test_missing_file_raises(tmp_path):
def test_non_geopackage_file_raises(tmp_path):
def test_missing_lines_table_raises(tmp_path):
def test_every_segment_is_indexed_in_each_cell_it_spans(tmp_path):
    # A long way across several cells appears in the cells of both its ends.
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend; py -m pytest tests/test_road_network.py -q`
Expected: FAIL on import of `app.services.road_network`.

- [ ] **Step 3: Implement the loader, and add `networkx>=3.4,<4.0` to `requirements.txt`**

- Open with `sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)`. Check `path.is_file()` first, because SQLite would otherwise raise a less useful error. Wrap `sqlite3.DatabaseError` in `RoadDataError`.
- Query `SELECT highway, other_tags, geom FROM lines WHERE highway IS NOT NULL`.
- Parse tags with `re.findall(r'"([^"]+)"=>"([^"]*)"', other_tags or "")`.
- Geometry offset is `8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]`. Read endianness from the first WKB byte, and accept only type 2. Catch `struct.error`, `KeyError`, `IndexError`, `TypeError` per row, count skips, and log the total at warning level.
- Direction: `oneway=no` is two-way; `oneway=yes` or `junction=roundabout` is forward; `oneway=-1` is reversed by flipping the coordinate list; any other value is two-way.
- Skip zero-length segments after rounding.
- `cell_deg = snap_max_m / 55660`. That is 111,320 m per degree halved, so a cell stays wider than the limit at any latitude below 60°.
- A segment is added to every cell its bounding box overlaps.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend; py -m pytest tests/test_road_network.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/road_network.py backend/requirements.txt backend/tests/road_fixtures.py backend/tests/test_road_network.py
git commit -m "feat: build a directed road graph from the GeoPackage"
```

### Task 3: Snapping and reachability

**Files:**
- Modify: `backend/app/services/road_network.py`
- Test: `backend/tests/test_road_network.py`

**Interfaces:**
- Consumes: `RoadGraph`, `Segment`, `Node`; `RoadLocation`, `RoadCheckResult`.
- Produces: `GeoPackageRoadNetwork(road_graph: RoadGraph, snap_max_m: float)` with `check(depot, points, facility) -> RoadCheckResult`.

- [ ] **Step 1: Write the failing tests**

```python
def test_all_locations_connected_passes(tmp_path):
    assert result == RoadCheckResult(too_far=[], unreachable=[])
def test_snaps_to_the_middle_of_a_long_segment(tmp_path):
    # Segment 2 km long, location 50 m beside its midpoint: not too_far.
def test_location_just_inside_the_limit_attaches(tmp_path):    # about 190 m
def test_location_just_outside_the_limit_is_too_far(tmp_path): # about 210 m
def test_location_outside_the_extract_is_too_far(tmp_path):
    # Location at 10.89918, 79.54393 with roads near 78.7, 10.8. No exception.
def test_too_far_location_is_left_out_of_pair_checks(tmp_path):
    assert result.too_far == ["SP-9"]
    assert not any("SP-9" in pair for pair in result.unreachable)
def test_point_that_can_be_entered_but_not_left(tmp_path):
    # Point on a one-way dead end: "SP-1 → SP-2" and "SP-1 → FAC" reported.
def test_location_in_a_separate_road_group(tmp_path):
def test_depot_that_cannot_reach_a_point(tmp_path):        # "DEP → SP-1"
def test_point_that_cannot_reach_the_facility(tmp_path):   # "SP-1 → FAC"
def test_facility_needs_no_route_back_to_the_depot(tmp_path):
    # Facility on a one-way dead end: passes.
def test_same_one_way_segment_connects_forward_only(tmp_path):
    # A before B on a dead-end one-way: "A → B" passes, "B → A" reported.
def test_same_one_way_segment_with_a_loop_connects_both_ways(tmp_path):
def test_identical_coordinates_connect(tmp_path):
```

Unit: compare with `pytest.approx` where measuring; offsets use 1° latitude = 111,320 m.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend; py -m pytest tests/test_road_network.py -q`
Expected: the new tests fail on import of `GeoPackageRoadNetwork`.

- [ ] **Step 3: Implement `GeoPackageRoadNetwork`**

Snap: search the location's cell and eight neighbours. Project to metres around the location (`x = (lon - lon0) * 111320 * cos(lat0)`, `y = (lat - lat0) * 111320`). Take the nearest point on each segment, keep the minimum, and record `Snap(segment_index, fraction, entry=segment.start, exit=segment.end)`. On a tie, prefer the lower segment index, so results are deterministic.

A pair A → B holds when either:

```python
same = a.segment_index == b.segment_index
if same and (segments[a.segment_index].two_way or a.fraction <= b.fraction):
    return True
return b.entry in reachable_from(a.exit)
```

`reachable_from(n)` is `nx.descendants(graph, n) | {n}`, cached per check call by source node, so a scenario costs at most 11 searches. Required pairs and their order: depot to each point, each point to each other point, each point to the facility. Pairs use the location's name.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend; py -m pytest tests/test_road_network.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/road_network.py backend/tests/test_road_network.py
git commit -m "feat: check road reachability for a scenario"
```

### Task 4: Wire the network into the app

**Files:**
- Modify: `backend/app/services/road_network.py`
- Modify: `backend/app/core/config.py`, `backend/app/api/scenarios.py:386`, `backend/tests/conftest.py`, `.env.example`, `.gitignore`
- Test: `backend/tests/test_road_network.py`, `backend/tests/test_validation.py`

**Interfaces:**
- Consumes: `load_road_graph`, `RoadDataError`, `GeoPackageRoadNetwork`, `NullRoadNetwork`.
- Produces: `get_road_network() -> RoadNetwork`; `reset_road_network() -> None` for tests.

- [ ] **Step 1: Write the failing tests**

```python
def test_empty_path_gives_the_not_configured_network(monkeypatch):
    monkeypatch.setattr(settings, "road_network_path", "")
    assert get_road_network().warning["code"] == "ROAD_NETWORK_NOT_CONFIGURED"

def test_missing_file_gives_the_unavailable_network(monkeypatch, tmp_path):
    assert network.warning["code"] == "ROAD_NETWORK_UNAVAILABLE"

def test_failed_load_is_retried_once_the_file_is_fixed(monkeypatch, tmp_path):
    # First call with no file is unavailable; write_gpkg; next call is GeoPackageRoadNetwork.

def test_concurrent_first_calls_build_once(monkeypatch, tmp_path):
    # Wrap load_road_graph in a counter; 8 threads behind a threading.Barrier call
    # get_road_network; assert count == 1 and all results are the same object.

def test_relative_path_resolves_from_the_repository_root(monkeypatch, tmp_path):
    # Monkeypatch REPOSITORY_ROOT to tmp_path and use a relative road_network_path.
```

In `test_validation.py`, through the API:

```python
def test_validate_endpoint_uses_the_road_network(client, auth_headers, registered_user, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.api.scenarios.get_road_network",
        lambda: FakeRoadNetwork(RoadCheckResult(too_far=[], unreachable=[])),
    )
    report = validate(client, auth_headers, scenario.id)
    assert report["validation_status"] == "valid"
    assert report["can_optimize"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend; py -m pytest tests/test_road_network.py tests/test_validation.py -q`
Expected: FAIL on import of `get_road_network`.

- [ ] **Step 3: Implement**

- `config.py`: add `road_network_path: str = ""` beside `road_snap_max_m`.
- `road_network.py`: `REPOSITORY_ROOT = Path(__file__).resolve().parents[3]`. `get_road_network()` returns the cached instance without locking if present. Otherwise it takes the module `threading.Lock`, rechecks, and builds. An empty path returns `NullRoadNetwork()`. `RoadDataError` is logged with its cause and returns `NullRoadNetwork(warning={"code": "ROAD_NETWORK_UNAVAILABLE", "message": ...})`, uncached. Log load time at info level on success.
- `api/scenarios.py`: `validate_scenario(db, scenario, get_road_network())`.
- `conftest.py`: an autouse fixture sets `settings.road_network_path` to `""` with `monkeypatch`, and calls `reset_road_network()` before and after each test.
- `.env.example`: add, under a `# Road network` comment explaining the 200 m limit is an assumption:

```
ROAD_NETWORK_PATH=docs/dataset/planet_78.163_11.047_55136793-geopackage/planet_78.163_11.047_55136793.gpkg
ROAD_SNAP_MAX_M=200
```

- `.gitignore`: add `*.gpkg` to the "Local environment and database files" block.

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend; py -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/road_network.py backend/app/core/config.py backend/app/api/scenarios.py backend/tests/conftest.py backend/tests/test_road_network.py backend/tests/test_validation.py .env.example .gitignore
git commit -m "feat: use the OpenStreetMap road network in scenario validation"
```

### Task 5: Real data, map default, docs and acceptance

**Files:**
- Create: `backend/tests/test_road_network_real_data.py`
- Modify: `frontend/src/components/LocationMap.jsx:4`, `:129`, `frontend/src/components/FacilityMap.jsx:37`, `frontend/src/components/StoragePointMap.jsx:21`
- Modify: `README.md`, `docs/dataset/osm_dataset_analysis.md`, `NAGARFLOW_AI_Master_Guide.pdf`

**Interfaces:**
- Consumes: `load_road_graph`, `GeoPackageRoadNetwork`, `RoadLocation`.

- [ ] **Step 1: Write and run the real-data test**

Skip with `pytest.mark.skipif` when the file is absent. It calls `load_road_graph` directly, takes the largest strongly connected component, picks eight evenly spaced nodes inside the city box (78.6306621–78.7835251°E, 10.7273005–10.8805108°N), uses them as depot, six points and facility, asserts `RoadCheckResult(too_far=[], unreachable=[])`, and prints load time and the component's share of nodes.

Run: `cd backend; py -m pytest tests/test_road_network_real_data.py -s -q`
Expected: PASS. Record the printed load time and share. If the check takes over 2 seconds or the share is below 90%, stop and report it; the design may need revisiting.

- [ ] **Step 2: Move the map default**

Set `INITIAL_CENTER = [78.6856, 10.8050]`, the OpenStreetMap link to `#map=14/10.8050/78.6856`, and both descriptions to "Map view centered on 10.8050, 78.6856 when no ... are registered." Keep each description's existing noun. Leave the coordinates in `depots.test.jsx` and `storagePoints.test.jsx`; they are fake geolocation readings.

- [ ] **Step 3: Verify the frontend**

Run: `cd frontend; npm test -- --run` then `npm run build`
Expected: PASS and a successful build.

- [ ] **Step 4: Update the docs**

- `README.md`: add a "Road connectivity" section covering `ROAD_NETWORK_PATH`, `ROAD_SNAP_MAX_M` (an assumption), the local-only dataset, the load cost on first validation, and the turn-restriction limitation. Change the map centre text in the storage point section to Trichy.
- `osm_dataset_analysis.md`: add a dated note at the top that the road-network topology finding is superseded by the spec, leaving the body unchanged.
- `NAGARFLOW_AI_Master_Guide.pdf`: no source file exists, so insert one addendum page after page 11 with PyMuPDF, using the same header and footer text. It records Step 10 complete, the rules, the two error codes, the new settings, the measured load time and test counts, and that it supersedes the road connectivity paragraph of section 10 and the Step 11 note in section 14. Keep the script in the scratchpad directory.

- [ ] **Step 5: Run the app end to end**

Add `ROAD_NETWORK_PATH` to the local `.env`, start the backend and frontend, sign in, and use a scenario with coordinates on Trichy roads. Do not leave invented records in the development database as if real; name them `TEST-` and delete them afterwards.

Expected: Validate gives `valid` and "Can optimize". Then move one storage point about 500 m from any road, such as into the Cauvery, and validate again: `invalid` with `ROAD_TOO_FAR`. Restore it.

- [ ] **Step 6: Final verification**

Run: `cd backend; py -m pytest -q`, then `cd frontend; npm test -- --run`
Expected: both pass. Confirm `git status --short` shows no `.gpkg`.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_road_network_real_data.py frontend/src/components README.md docs/dataset/osm_dataset_analysis.md NAGARFLOW_AI_Master_Guide.pdf
git commit -m "docs: complete Step 10 and centre maps on Trichy"
```
