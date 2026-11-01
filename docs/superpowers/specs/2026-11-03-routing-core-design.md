# Stage 1: routing core (Steps 11–16)

**Date:** 2026-11-03
**Status:** Design approved in conversation; awaiting review of this written spec.
**Builds on:** `feat/road-connectivity` (Step 10), `2026-11-02-road-connectivity-design.md`.

## Goal

A coordinator validates a scenario, runs Greedy and OR-Tools on identical inputs, and compares their total road distance and routes on a map. Both results are checked by one independent validator, and a run that produced no valid route never shows a distance.

Success means:

- A valid Trichy scenario returns a route per used vehicle from both algorithms, following real road geometry.
- Every point is served whole by exactly one vehicle, and each vehicle runs depot → points → facility once.
- Both algorithms use the same matrix and pass the same validator.
- The comparison shows a difference only when both produced a valid result.

## Decisions

**DEC-003, resolved 2026-11-03: the vehicle waits.** A vehicle that reaches a point before `available_from` waits there. The owner chose this on 2026-11-03. Skipping and returning does not fit a one-trip vehicle. Waiting adds no road distance.

**Shift window.** Without a time limit, waiting could never make a scenario fail, so scenarios gain an optional shift. No shift means no time limit.

**Authority.** The older requirements call the blockers unresolved. The owner has chosen to proceed; this does not make any figure here a municipal measurement.

## Scope

**In scope:** road distance and time matrix, time inputs, Greedy, OR-Tools, independent result validation, optimize API, Route Optimization page, route map.

**Out of scope:** the ten scenarios, history and reports pages (Stage 2), roles (Stage 3), live traffic, repeated trips, primary collection.

## Time rules

- All times are Indian Standard Time, stored as naive local datetimes.
- `Scenario` gains nullable `shift_start` and `shift_end`. Both or neither must be set, and end must be after start.
- `available_from` on storage points becomes editable through the API and form. Null means available from the start of the trip.
- Trip clock zero is `shift_start`. With no shift it is the earliest `available_from`, or 00:00 today if no point has one, so that offsets stay small.
- Vehicles leave the depot at clock zero and do not delay departure, because waiting is modelled at the point.
- Loading time at a stop is zero. **This is an assumption.**
- With a shift, a vehicle must reach the facility by `shift_end`.
- Arrival at a point is `max(travel arrival, available_from)` for service purposes. Both are reported.

Validation gains a check, `availability`, placed after `coordinates` in `CHECK_ORDER`: with a shift set, a point whose `available_from` is after `shift_end` fails with `AVAILABILITY_AFTER_SHIFT`. It passes when no shift is set.

## Steps 11–12: road costs

`RoadGraph` edges gain `length_m` (haversine) and `time_s`. Assumed speeds, **all assumptions, not measurements**:

| Road type | km/h |
|---|---|
| `motorway`, `trunk` and their links | 50 |
| `primary` and link | 40 |
| `secondary` and link | 35 |
| `tertiary` and link | 30 |
| `unclassified`, `road` | 25 |
| `residential`, `living_street` | 20 |
| `service` | 15 |

New module `services/road_costs.py`:

- `build_cost_matrix(network, locations) -> CostMatrix`, with `CostMatrix(names, distance_m: list[list[int | None]], time_s: list[list[int | None]])`. `None` is an explicit no-path value, never a large number.
- Costs run from each location's snap point: remaining part of its segment, the network path, then the part-segment to the target. The gap between a location and its road is not counted. Same-segment forward pairs use the direct part-segment.
- Distance is the shortest-distance path. `time_s` is the time along that same path, so both figures describe one route.
- Values are rounded to whole metres and seconds, with non-zero costs never rounding to 0.
- `route_geometry(network, source, target) -> list[(lon, lat)]` returns the path's coordinates for the map.
- Searches use `scipy.sparse.csgraph.dijkstra` on a compressed adjacency matrix built at load. `networkx` remains for connected groups.

`CostMatrix` is built once per run and passed to both algorithms.

## Steps 13–14: algorithms

Shared input `RoutingProblem`: location names, point demands in kg (`Decimal`, scaled to whole grams for the solver), vehicle capacities, `CostMatrix`, ready times, and `shift_end_s` or `None`.

Shared output `MethodResult`:

```python
status: "feasible" | "optimal" | "no_solution" | "infeasible" | "timeout" | "invalid_result"
routes: list[VehicleRoute]     # empty unless status is feasible or optimal
total_distance_m: int | None   # None unless status is feasible or optimal
solve_ms: int
message: str
```

`VehicleRoute(vehicle_id, stops, load_kg, distance_m, finish_s)`, where each stop has its code, `arrival_s`, `service_s` and `wait_s`.

**Greedy** (`services/optimizer/greedy.py`): vehicles start at the depot. Each round considers every unserved point with every vehicle that has capacity, keeps pairs where the vehicle can still reach the point and then the facility by `shift_end`, and takes the shortest distance. Ties go to the lower point code, then the lower vehicle id. If points remain and no pair is feasible, the status is `no_solution`, meaning construction failed, not that none exists.

**OR-Tools** (`services/optimizer/ortools_solver.py`): `ortools>=9.15,<10`. One start at the depot and one end at the facility per vehicle, with no disjunctions, so every point is mandatory. A vehicle may be left unused; its zero-length depot-to-facility trip is not counted. Arc cost is `distance_m`. Capacity dimension in grams, with vehicle start load 0. Time dimension with unlimited slack up to the horizon, so waiting is allowed, and each point's window starting at its ready time. With a shift, the horizon is `shift_end_s`. First solution `PATH_CHEAPEST_ARC`, then `GUIDED_LOCAL_SEARCH`, limited by `OPTIMIZER_TIME_LIMIT_S` (default 10).

Status mapping: a solution found gives `feasible`, because guided local search does not prove optimality. No solution with the routing status marked infeasible gives `infeasible`. No solution at the time limit gives `timeout`. `optimal` is reserved for a proof and is not produced by this configuration. The UI says "best found".

**Unused vehicles and the empty route:** a used vehicle has at least one point. The model allows depot → facility directly only as "unused", and an unused vehicle adds nothing to the total.

**Independent validator** (`services/optimizer/result_check.py`): `check_result(problem, result) -> list[str]`. It recomputes everything from the matrix and confirms each point appears exactly once on one vehicle, each load fits, the combined load fits the facility, no stop is served before its ready time, arrival is correct, every finish is within the shift, no leg lacks a path, and the reported distances add up. A non-empty list turns a `feasible` result into `invalid_result`, with no distance.

## Step 15: API and persistence

`OptimizationRun` changes, with a targeted upgrade function in `db/migrations.py`:

- `total_distance_m` becomes nullable. Existing rows are left as they are.
- Add `batch_id` (string, shared by the two runs), `solve_ms`, `message`, `routes` (JSON), `input_hash`.
- `status` holds the `MethodResult` values. `dashboard.py`'s query counts only `feasible` and `optimal`, replacing `success`. `STATUS_SUCCESS` and `STATUS_FAILED` are removed.

`input_hash` is the SHA-256 of the canonical `RoutingProblem` JSON, recorded on both rows.

Endpoints, both scoped to the signed-in coordinator:

- `POST /api/v1/scenarios/{id}/optimize`: runs validation and records it. If `can_optimize` is false, returns 409 with the report and runs nothing. Otherwise builds the matrix, runs both algorithms, checks both, saves both rows and returns the comparison.
- `GET /api/v1/scenarios/{id}/optimization`: the latest batch, or 404.

Comparison response: `batch_id`, `created_at`, `greedy`, `or_tools`, `difference_m` and `difference_pct`. The last two are null unless both are feasible. `difference_m` is Greedy minus OR-Tools. Each route includes `geometry` for the map, kept in `routes`.

A coordinator's own second optimize simply creates a new batch.

Optimization runs in the request. With a 10 second limit it fits the existing sync endpoints, and the frontend shows a "running" state with no fake percentage.

## Step 16: Route Optimization page

`RouteOptimizationPage.jsx` replaces the placeholder at `/route-optimization`, reading `?scenario=` as the Proceed to Optimization button already links.

- Scenario selector, Run Optimization button, and running state.
- A blocked scenario shows the validation errors with a link to the scenario.
- Comparison panel: status, total distance in km, solve time, used vehicles, and the difference when both are feasible. A non-feasible method shows its status and message, never a distance.
- Per-vehicle list: ordered stops, load against capacity, arrival, wait and distance.
- `RouteMap.jsx`: MapLibre with OpenStreetMap attribution, one line per vehicle in distinct colours, numbered stops, depot and facility markers, and a Greedy/OR-Tools toggle.
- Labels state that speeds and times are assumed estimates.

Forms: the scenario form gains shift start and end. The storage point form gains `available_from`. Both are optional.

`requirements.txt` gains `scipy` and `ortools`.

## Failure handling

| Situation | Result |
|---|---|
| Scenario not valid | 409 with the validation report; no runs saved |
| Road network unavailable | Validation is `incomplete`, so the same 409 |
| A required pair has no path | Should be stopped by validation; if not, both methods report `no_solution` with the pair named |
| Algorithm raises | That method saves `no_solution` with a message and the cause is logged; the other still reports |
| OR-Tools finds nothing in time | `timeout`, no distance |
| Result fails the checker | `invalid_result`, no distance, cause logged |

## Testing

Written first, in the existing style.

- **Costs:** hand-computed fixtures for distance, part-segments, one-way direction, time by road type, and explicit no-path.
- **Time rules:** shift pair validation, `AVAILABILITY_AFTER_SHIFT`, waiting adds no distance, shift end enforced by both algorithms.
- **Greedy:** every point once, whole, tie-breaks, `no_solution` where a bad early choice strands a point.
- **OR-Tools:** beats Greedy on a fixture built so Greedy is suboptimal, serves all points, respects capacity, `timeout` path using an injected limit, one vehicle left unused when best.
- **Checker:** one failing case per rule, including a duplicate point and a split load.
- **API:** 409 for invalid scenarios, identical `input_hash` on both rows, no distance on failed runs, coordinator scoping, migration of an old table.
- **Frontend:** comparison hides the difference when either failed, map toggle, blocked state, new form fields.
- **Real data:** one skippable test runs both algorithms on Trichy locations and records timing.

The full backend suite, frontend suite and build must pass.

## Known limitations

- Speeds are assumed, so times and shift outcomes are estimates. Distance does not depend on them.
- The Step 10 limits still apply: no turn restrictions, no truck size or weight limits.
- `feasible` from OR-Tools means best found in the time limit, not proven optimal.
- Comparing algorithms says nothing about real-world savings, because scenario inputs are synthetic.

## Done when

1. The tests above pass with the existing suites.
2. A Trichy scenario through the live API returns routes from both algorithms that pass the checker, and the page shows them on the map.
3. README and Master Guide describe the stage, including measured run times.
