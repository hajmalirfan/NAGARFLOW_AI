# Routing Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Greedy and OR-Tools on identical road costs for a validated scenario, check both independently, save them, and compare them on a map.

**Architecture:** `road_costs.py` turns the road graph into one cost matrix per run. `services/optimizer/` holds shared types, two solvers and one independent checker, none of which know about the database or the road file. `services/optimization.py` connects scenario records to the solvers and to `OptimizationRun`.

**Tech Stack:** Python, FastAPI, SQLAlchemy, `scipy`, `ortools`, React, MapLibre.

**Spec:** `docs/superpowers/specs/2026-11-03-routing-core-design.md`

**Branch:** `feat/routing-core`. Run backend commands from `backend/` with `.venv/Scripts/python -m pytest`.

## Global Constraints

- Internal units: whole metres, whole seconds, whole grams for solver load. Reported waste stays in kg.
- A non-feasible result never carries a distance. `None`, never 0 or a large number, means no path.
- Times are Indian Standard Time, stored naive. Loading time is 0, an assumption.
- Assumed speeds in km/h: motorway/trunk 50, primary 40, secondary 35, tertiary 30, unclassified/road 25, residential/living_street 20, service 15. Links take their parent's speed.
- `OPTIMIZER_TIME_LIMIT_S` default 10.
- Statuses: `feasible`, `optimal`, `no_solution`, `infeasible`, `timeout`, `invalid_result`.
- Greedy ties: lower point code, then lower vehicle id.
- The default test suite never reads the real dataset.

## Review Focus

1. A point with zero waste is still mandatory and must be visited by both solvers. Test in Tasks 3 and 4.
2. A load exactly equal to capacity, with decimals such as 1234.56 kg, must fit: no float rounding. Test in Task 4.
3. Two points at the same coordinates give a 0 m leg, which must not read as no path. Test in Tasks 1 and 3.
4. `available_from` before `shift_start` means ready at once, not a negative time. Test in Task 2.
5. Old `OptimizationRun` rows with no `batch_id` must not break `GET /optimization`. Test in Task 6.

---

### Task 1: Road cost matrix (Steps 11–12)

**Files:**
- Modify: `backend/app/services/road_network.py`, `backend/requirements.txt`
- Create: `backend/app/services/road_costs.py`
- Test: `backend/tests/test_road_costs.py`

**Interfaces:**
- Produces: `RoadGraph` gains `edge_index: dict[Node, int]`, `nodes: list[Node]`, `distance_csr`, `edge_time: dict[tuple[Node, Node], float]`. `GeoPackageRoadNetwork.snap(location) -> Snap | None` becomes public (rename `_snap`/`_Snap`).
- Produces: `CostMatrix(names: list[str], distance_m: list[list[int | None]], time_s: list[list[int | None]])`, `build_cost_matrix(network: GeoPackageRoadNetwork, locations: list[RoadLocation]) -> CostMatrix`, `route_geometry(network, source: RoadLocation, target: RoadLocation) -> list[tuple[float, float]]`.
- Produces: `road_speed_kmh(highway: str) -> int`.

- [ ] **Step 1: Write failing tests** in `test_road_costs.py`, using `write_gpkg`: `test_length_of_a_known_segment` (0.01° of latitude is about 1,112 m, `pytest.approx(abs=2)`), `test_speed_by_road_type` (parametrized from the Global Constraints), `test_time_uses_the_road_type_speed` (1,112 m of residential at 20 km/h is about 200 s), `test_cost_counts_part_segments_from_each_snap` (locations at 25% and 75% of one 1,112 m segment give about 556 m), `test_one_way_costs_differ_by_direction` (forward direct, reverse via the loop), `test_no_path_is_none`, `test_same_location_costs_zero_not_none`, `test_short_leg_never_rounds_to_zero` (0.3 m apart gives 1), `test_shortest_path_prefers_distance_over_time`, `test_route_geometry_follows_the_road` (starts near source, ends near target, includes the bend vertex).

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_road_costs.py -q`
Expected: import error for `app.services.road_costs`.

- [ ] **Step 3: Implement**

Add `scipy>=1.14,<2` to requirements. In the loader, keep each edge's haversine length, keep the shortest when two ways share a node pair, and store time from that edge's `highway`. Build a `scipy.sparse.csr_matrix` of lengths. Run `dijkstra(csr, indices=sources, return_predecessors=True)` once from all location exit nodes. Add part-segment lengths per the spec. Walk predecessors to sum `edge_time`, so time is along the distance path. Same-segment forward pairs use the direct part. Identical snaps cost 0.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_road_costs.py tests/test_road_network.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** `feat: build a road distance and time matrix`

### Task 2: Time inputs and availability check

**Files:**
- Modify: `backend/app/models/scenario.py`, `backend/app/schemas/scenario.py`, `backend/app/schemas/storage_point.py`, `backend/app/api/scenarios.py`, `backend/app/api/storage_points.py`, `backend/app/db/migrations.py`, `backend/app/main.py`, `backend/app/services/validation.py`, `frontend/src/components/ValidationReport.jsx`
- Test: `backend/tests/test_scenarios.py`, `test_storage_points.py`, `test_validation.py`

**Interfaces:**
- Produces: `Scenario.shift_start`, `Scenario.shift_end: datetime | None`; `available_from` on storage point write and response schemas; `shift_start` and `shift_end` on scenario write and response schemas; `upgrade_legacy_scenario_schema(engine)`.
- Produces: check name `availability`, after `coordinates` in `CHECK_ORDER`, error `AVAILABILITY_AFTER_SHIFT`.

- [ ] **Step 1: Write failing tests**: `test_shift_needs_both_ends` (422), `test_shift_end_must_follow_start` (422), `test_shift_round_trips`, `test_available_from_round_trips`, `test_point_available_after_shift_end_fails` (names the point code), `test_availability_passes_without_a_shift`, `test_point_available_before_shift_start_passes`, `test_upgrade_adds_shift_columns` (old table without them keeps rows).

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_scenarios.py tests/test_storage_points.py tests/test_validation.py -q`
Expected: new tests FAIL. Extend `stub_scenario` with `shift_end=None` and `available_from=None` so stubs keep working.

- [ ] **Step 3: Implement** the columns, schema validators, upgrade function called from `main.py` after `upgrade_legacy_facility_schema`, the check, and label `["availability", "Waste availability"]` in `CHECK_LABELS`.

- [ ] **Step 4: Run the full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit** `feat: add scenario shifts and editable waste availability`

### Task 3: Shared types, checker and Greedy (Step 13)

**Files:**
- Create: `backend/app/services/optimizer/__init__.py`, `types.py`, `result_check.py`, `greedy.py`
- Test: `backend/tests/test_optimizer.py`

**Interfaces:**
- Produces in `types.py`, dataclasses:
  - `RoutingProblem(names: list[str], demand_g: list[int], ready_s: list[int], vehicle_ids: list[int], capacity_g: list[int], facility_capacity_g: int, distance_m, time_s, shift_end_s: int | None)`. Index 0 is the depot, the last index is the facility, and points lie between. `demand_g` and `ready_s` have one entry per location, 0 for depot and facility. Point order is ascending code.
  - `Stop(code: str, arrival_s: int, service_s: int, wait_s: int)`, `VehicleRoute(vehicle_id: int, stops: list[Stop], load_g: int, distance_m: int, finish_s: int)`, `MethodResult(status: str, routes: list[VehicleRoute], total_distance_m: int | None, solve_ms: int, message: str)`.
- Produces: `check_result(problem: RoutingProblem, result: MethodResult) -> list[str]`, `solve_greedy(problem: RoutingProblem) -> MethodResult`, and test helper `problem_from(...)` in `tests/test_optimizer.py`.

- [ ] **Step 1: Write failing tests**: `test_checker_accepts_a_correct_result`, then one rejection each: `test_checker_rejects_a_missing_point`, `..._a_duplicate_point`, `..._an_overloaded_vehicle`, `..._a_combined_load_over_facility_capacity`, `..._service_before_ready`, `..._a_wrong_distance`, `..._a_finish_after_shift`, `..._a_leg_with_no_path`. Greedy: `test_greedy_serves_every_point_once`, `test_greedy_takes_the_nearest_feasible_pair`, `test_greedy_ties_go_to_lower_code_then_vehicle`, `test_greedy_waits_without_adding_distance`, `test_greedy_stops_at_shift_end` (`no_solution`, `total_distance_m is None`), `test_greedy_strands_a_point_after_a_bad_choice` (`no_solution`), `test_greedy_visits_a_zero_waste_point`, `test_greedy_handles_a_zero_metre_leg`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_optimizer.py -q`
Expected: import error.

- [ ] **Step 3: Implement** per the spec. The feasibility test for a pair includes reaching the facility from that point by `shift_end_s`. `solve_ms` uses `time.perf_counter`.

- [ ] **Step 4: Run to verify they pass.** Expected: PASS.

- [ ] **Step 5: Commit** `feat: add the Greedy baseline and an independent result checker`

### Task 4: OR-Tools (Step 14)

**Files:**
- Create: `backend/app/services/optimizer/ortools_solver.py`
- Modify: `backend/requirements.txt`, `backend/app/core/config.py`, `.env.example`
- Test: `backend/tests/test_optimizer.py`

**Interfaces:**
- Consumes: Task 3 types.
- Produces: `solve_ortools(problem: RoutingProblem, time_limit_s: int) -> MethodResult`; setting `optimizer_time_limit_s: int = Field(default=10, gt=0)`.

- [ ] **Step 1: Write failing tests**, with `time_limit_s=1`: `test_ortools_beats_greedy_where_greedy_is_short_sighted`, `test_ortools_serves_every_point`, `test_ortools_respects_capacity`, `test_ortools_fits_a_load_exactly_at_capacity` (demand from `Decimal("1234.56")`), `test_ortools_leaves_a_vehicle_unused_when_shorter` (one route, no empty route in output), `test_ortools_waits_for_late_waste` (same distance, later service), `test_ortools_enforces_shift_end`, `test_ortools_reports_impossible_capacity_as_not_feasible` (distance `None`), `test_ortools_timeout_has_no_distance` (monkeypatch the solve to return nothing with routing status `ROUTING_FAIL_TIMEOUT`), `test_ortools_visits_a_zero_waste_point`, `test_every_ortools_result_passes_the_checker`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_optimizer.py -q`
Expected: import error. Install first: `.venv/Scripts/python -m pip install "ortools>=9.15,<10"`, adding that line to requirements.

- [ ] **Step 3: Implement** per the spec. Pairs with no path get a callback cost above any route total and are checked out of any result by `check_result`. The time dimension uses `fix_start_cumul_to_zero=True`, slack and capacity equal to the horizon. Horizon is `shift_end_s`, or the sum of the largest ready time and every leg's maximum time when no shift is set. A vehicle counts as used when `IsVehicleUsed` is true, and unused vehicles add no route.

- [ ] **Step 4: Run to verify they pass.** Expected: PASS.

- [ ] **Step 5: Commit** `feat: add OR-Tools route optimization`

### Task 5: Optimization service

**Files:**
- Create: `backend/app/services/optimization.py`
- Modify: `backend/app/models/optimization_run.py`, `backend/app/db/migrations.py`, `backend/app/main.py`, `backend/app/services/dashboard.py`
- Test: `backend/tests/test_optimization.py`, `backend/tests/test_dashboard.py`

**Interfaces:**
- Consumes: `build_cost_matrix`, `route_geometry`, solvers, `check_result`, `validate_scenario`'s helpers `_scenario_points`, `_scenario_vehicles`, `_scenario_facility`.
- Produces: `build_problem(scenario, matrix) -> RoutingProblem`, `problem_hash(problem) -> str`, `run_method(solver, problem) -> MethodResult`, `optimize_scenario(db, scenario, network) -> list[OptimizationRun]`, `upgrade_legacy_optimization_run_schema(engine)`, and `SUCCESSFUL_STATUSES = ("feasible", "optimal")` in the model file.

- [ ] **Step 1: Write failing tests**, using a fake network and direct matrix: `test_problem_scales_kg_to_grams_exactly`, `test_ready_times_count_from_shift_start`, `test_ready_time_before_shift_start_is_zero`, `test_clock_without_a_shift_starts_at_earliest_availability`, `test_hash_is_stable_and_changes_with_input`, `test_both_runs_share_batch_and_hash`, `test_a_crashing_solver_saves_no_solution_and_the_other_still_runs`, `test_a_result_failing_the_checker_becomes_invalid_result` (distance `None`), `test_failed_runs_store_no_distance`, `test_upgrade_makes_distance_nullable` (old table keeps rows), `test_dashboard_counts_feasible_as_successful`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_optimization.py -q`
Expected: import error.

- [ ] **Step 3: Implement.** Convert kg to grams with `int(Decimal(str(value)) * 1000)`. `run_method` wraps a solver in `try/except Exception`, logs it and applies `check_result`. Store each route's `geometry` inside `routes` JSON. SQLite needs a table rebuild for the nullable change; follow `_rebuild_sqlite_vehicle_table`. Update `dashboard.py` so successful means `SUCCESSFUL_STATUSES`, failed means any other status, and remove the old constants. Update the `test_dashboard.py` and `test_scenarios.py` rows that use old status values.

- [ ] **Step 4: Run the full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit** `feat: run and save paired optimization results`

### Task 6: Optimize API (Step 15)

**Files:**
- Create: `backend/app/schemas/optimization.py`
- Modify: `backend/app/api/scenarios.py`
- Test: `backend/tests/test_optimization.py`

**Interfaces:**
- Consumes: `optimize_scenario`, `get_road_network`, `record_validation`.
- Produces: `POST /api/v1/scenarios/{id}/optimize`, `GET /api/v1/scenarios/{id}/optimization`. Response `OptimizationComparison(batch_id, created_at, greedy: MethodRun, or_tools: MethodRun, difference_m: int | None, difference_pct: float | None)`. `MethodRun(status, total_distance_m, solve_ms, message, routes)`.
- Consumes in the frontend later: those JSON shapes.

- [ ] **Step 1: Write failing tests**: `test_optimize_requires_authentication`, `test_optimize_refuses_an_invalid_scenario` (409, report in `detail`, no rows), `test_optimize_returns_both_methods`, `test_difference_needs_both_feasible` (nulls when one failed), `test_difference_is_greedy_minus_or_tools`, `test_another_coordinators_scenario_is_404`, `test_latest_optimization_returns_the_newest_batch`, `test_no_optimization_yet_is_404`, `test_rows_without_a_batch_are_ignored`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_optimization.py -q`
Expected: new tests FAIL with 404 or 405.

- [ ] **Step 3: Implement.** A 409 uses `HTTPException(detail={"message": ..., "report": ...})`. The optimize handler remains a sync `def`.

- [ ] **Step 4: Run the full backend suite.** Expected: PASS.

- [ ] **Step 5: Commit** `feat: add optimize and comparison endpoints`

### Task 7: Route Optimization page and forms (Step 16)

**Files:**
- Create: `frontend/src/pages/RouteOptimizationPage.jsx`, `frontend/src/components/RouteMap.jsx`, `frontend/src/test/optimization.test.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/services/api.js`, `frontend/src/styles.css`, `frontend/src/pages/ScenarioManagementPage.jsx`, `frontend/src/pages/StoragePointManagementPage.jsx`, `frontend/src/test/scenarios.test.jsx`, `frontend/src/test/storagePoints.test.jsx`

**Interfaces:**
- Consumes: Task 6 JSON.
- Produces: `api.js` functions named to match the file's style for optimize and latest optimization. `<RouteMap routes={routes} />`, where each route has `geometry`, `stops`, `vehicle_id`.

- [ ] **Step 1: Write failing tests**: `shows both methods after a run`, `hides distance for a failed method`, `hides the difference unless both are feasible`, `shows validation errors when blocked` (409), `says best found rather than optimal`, `labels times as estimates`, `switches the map between algorithms`, `preselects the scenario from the URL`, `saves shift times on a scenario`, `saves available from on a storage point`. Mock `RouteMap` in jsdom as the existing map tests do.

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend; npx vitest run src/test/optimization.test.jsx`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement.** Remove the `route-optimization` entry from `UPCOMING_PAGES` and add a real route. Reuse the MapLibre setup and attribution from `LocationMap.jsx`. Use GeoJSON line layers, one colour per vehicle, numbered stop markers. Fit bounds to the routes. Show no percentage while running.

- [ ] **Step 4: Run all frontend tests and build**

Run: `cd frontend; npx vitest run; npm run build`
Expected: PASS and a built bundle.

- [ ] **Step 5: Commit** `feat: add the Route Optimization page and route map`

### Task 8: Real data, docs and acceptance

**Files:**
- Create: `backend/tests/test_optimization_real_data.py`
- Modify: `README.md`, `NAGARFLOW_AI_Master_Guide.pdf`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write and run the real-data test.** It skips if the dataset is absent. It takes ten city nodes as in `test_road_network_real_data.py`, with two 6,000 kg vehicles, builds the matrix, runs both solvers with `time_limit_s=10`, asserts both pass `check_result` and OR-Tools is no longer than Greedy, and prints matrix and solve times.

Run: `.venv/Scripts/python -m pytest tests/test_optimization_real_data.py -s -q`
Expected: PASS. Stop and report if the matrix takes over 10 seconds.

- [ ] **Step 2: Run end to end.** Use the live API on a throwaway SQLite database and `TEST-` records, as in Step 10. Then open the page in the built-in browser against that server and confirm both routes draw on the map. Delete the database.

- [ ] **Step 3: Update the docs.** README gains a "Route optimization" section covering shifts, DEC-003, assumed speeds, statuses and `OPTIMIZER_TIME_LIMIT_S`. Add a Master Guide addendum page after page 11A, numbered 11B, recording DEC-003 as resolved and the measured times.

- [ ] **Step 4: Final verification**

Run: `.venv/Scripts/python -m pytest -q`, then `cd frontend; npx vitest run`
Expected: both pass.

- [ ] **Step 5: Commit** `docs: complete Stage 1 routing core`
