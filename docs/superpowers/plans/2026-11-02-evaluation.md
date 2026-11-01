# Evaluation, History, Reports and Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report S01–S10 for both methods, add run history, and make failures readable.

**Architecture:** The catalogue is versioned JSON loaded as ordinary owned records, so it uses the real validation, solvers and checker. A pure report service derives each case's state from saved runs and validations. The browser runs cases one at a time through the existing optimize endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vitest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-02-evaluation-design.md`

## Global Constraints

- All ten cases are reported. A case with no route never shows a distance.
- All catalogue values are synthetic and labelled so.
- Nothing runs on a scenario that fails validation.
- OR-Tools is never described as optimal unless it proves it.
- A difference is shown only where both methods found routes.
- History `limit` defaults to 25, maximum 100.
- Tests run from `backend` with `.venv/Scripts/python -m pytest -q`, and from `frontend` with `npx vitest run`.

## Review Focus

1. A coordinator deletes one loaded scenario and loads again: only that case returns, and its records' codes do not clash with survivors. Test in Task 2.
2. Two coordinators both load the catalogue: both succeed, and neither sees the other's. Test in Task 2.
3. A scenario renamed to `=HYPERLINK(...)` is neutralised in the CSV. Test in Task 5.
4. One case returns a server error during Run all: the run continues and that case shows the failure. Test in Task 7.
5. An existing database gains the two new columns on startup, on SQLite and PostgreSQL paths. Test in Task 1.

---

### Task 1: Schema additions and provenance (Step 18)

**Files:**
- Modify: `backend/app/models/scenario.py`, `backend/app/models/optimization_run.py`, `backend/app/db/migrations.py`, `backend/app/main.py`, `backend/app/services/optimization.py`
- Test: `backend/tests/test_optimization.py`

**Interfaces:**
- Produces: `Scenario.evaluation_code: str | None` (String(3), indexed); `OptimizationRun.provenance: dict | None` (JSON); `upgrade_legacy_evaluation_schema(engine) -> None`; `run_provenance(scenario) -> dict` with keys `catalog_version`, `road_dataset`, `ortools_version`, `time_limit_s`, `snap_limit_m`.

- [ ] **Step 1: Write failing tests:** `test_upgrade_adds_evaluation_columns` builds old tables without the columns, upgrades, asserts both columns exist, and upgrading twice is harmless. `test_runs_record_provenance` asserts both rows hold `ortools_version` and `time_limit_s` from settings, and `catalog_version` is None for a non-catalogue scenario.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Follow `upgrade_legacy_scenario_schema` for `ALTER TABLE ... ADD COLUMN`. `road_dataset` is the file name only, never the full path. `ortools_version` is `ortools.__version__`. Call the upgrade in `lifespan` after the optimization-run upgrade.
- [ ] **Step 4: Run them, then the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: record evaluation code and run provenance`

### Task 2: Catalogue and loader (Step 17)

**Files:**
- Create: `backend/app/evaluation/__init__.py`, `backend/app/evaluation/catalog/manifest.json`, `S01.json`–`S10.json`, `backend/app/evaluation/catalog_loader.py`, `backend/app/api/evaluation.py`, `backend/app/schemas/evaluation.py`, `backend/tests/test_evaluation.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `Scenario.evaluation_code`.
- Produces: `read_catalog() -> list[dict]` (verifies checksums, raises `ValueError` on mismatch); `CATALOG_VERSION: str`; `load_catalog(db, user) -> list[Scenario]`; `POST /api/v1/evaluation/scenarios` returning `[{code, scenario_id, name}]`.

- [ ] **Step 1: Author the files.** Coordinates are road nodes from the largest connected group inside the city box in `test_optimization_real_data.py`, read once and stored. Values follow the spec's table. Each file has `"synthetic": true` and a `purpose`. Names start `SYNTH-S01`. S10 starts with `expected.outcome: "routes"`, re-pinned in Task 8 if measurement differs.
- [ ] **Step 2: Write failing tests:** `test_manifest_contains_s01_through_s10`; `test_checksums_match`; `test_a_changed_file_is_refused`; `test_every_case_has_two_vehicles_and_six_to_ten_points`; `test_every_case_is_labelled_synthetic`; `test_blocked_cases_fail_validation_with_expected_codes` (load with `FakeRoadNetwork`, validate S04, S05, S09, compare codes); `test_routes_cases_pass_validation`; `test_loading_twice_creates_nothing_new`; `test_a_failed_load_leaves_nothing` (patch the seventh case to raise); `test_a_deleted_case_is_restored_alone` (Focus 1); `test_two_coordinators_load_separately` (Focus 2); `test_loading_needs_authentication`.
- [ ] **Step 3: Run them.** Expected: FAIL.
- [ ] **Step 4: Implement.** Insert models directly in one transaction. For each missing case, reuse any record the caller owns with the same `SYNTH-` code, otherwise create it. Skip a case whose scenario exists.
- [ ] **Step 5: Run them, then the full backend suite.** Expected: PASS.
- [ ] **Step 6: Commit** `feat: add the S01-S10 evaluation catalogue`

### Task 3: Error handling, backend (Step 20)

**Files:**
- Modify: `backend/app/main.py`, `backend/app/services/validation.py`, `backend/app/services/optimizer/ortools_solver.py`, `backend/app/services/optimizer/greedy.py`, `backend/app/schemas/scenario.py`, `backend/app/api/scenarios.py`, `README.md`
- Test: `backend/tests/test_errors.py`, `backend/tests/test_validation.py`, `backend/tests/test_optimizer.py`

**Interfaces:**
- Produces: 500 body `{"detail": "Something went wrong on the server.", "reference": "<8 hex>"}`; a `no_route_message(problem) -> str` in `optimizer/types.py`, used by both solvers.

- [ ] **Step 1: Write failing tests:** `test_server_error_hides_internals` (route raising `RuntimeError("secret")`: 500, body lacks `secret`, has `reference`, and CORS header present); `test_http_errors_are_unchanged`; `test_point_ready_at_shift_end_fails_validation`; `test_override_without_a_network_returns_409`; `test_mixed_timezone_shift_returns_422`; `test_no_route_message_points_at_the_shift` (shift set: mentions the shift and availability times; no shift: does not).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Change the validation check to `>=`. In the optimize endpoint, return the existing 409 shape when `network` is a `NullRoadNetwork`. Reword the README `infeasible` row to say most impossible problems report `no_solution`.
- [ ] **Step 4: Run the full backend suite.** Expected: PASS. Fix any test that relied on the old `>`.
- [ ] **Step 5: Commit** `fix: give failures clear reasons and safe server errors`

### Task 4: History API (Step 18)

**Files:**
- Modify: `backend/app/api/scenarios.py`, `backend/app/schemas/optimization.py`, `backend/app/main.py`
- Create: `backend/app/api/history.py`, `backend/tests/test_history.py`

**Interfaces:**
- Consumes: `_comparison(runs)`.
- Produces: `GET /api/v1/optimization-history` returning `{items: [HistoryRow], total}`, with `HistoryRow` fields `scenario_id, scenario_name, batch_id, created_at, greedy_status, greedy_distance_m, or_tools_status, or_tools_distance_m, difference_m`; `GET /api/v1/scenarios/{id}/optimization/{batch_id}`; `OptimizationComparison.provenance`.

- [ ] **Step 1: Write failing tests:** `test_history_is_newest_first`; `test_history_pages`; `test_limit_above_100_is_422`; `test_filters_by_scenario`; `test_status_matches_either_method`; `test_history_hides_other_coordinators`; `test_rows_without_a_batch_are_left_out`; `test_saved_comparison_opens`; `test_unknown_batch_is_404`; `test_another_coordinators_batch_is_404`; `test_a_batch_from_another_scenario_is_404`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Page over distinct `batch_id` by newest run id, then load those batches' rows.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add optimization history endpoints`

### Task 5: Evaluation report API (Step 19)

**Files:**
- Create: `backend/app/services/evaluation_report.py`
- Modify: `backend/app/api/evaluation.py`, `backend/app/schemas/evaluation.py`
- Test: `backend/tests/test_evaluation_report.py`

**Interfaces:**
- Consumes: `read_catalog()`, `OptimizationRun.provenance`.
- Produces: `build_report(db, user) -> dict` with `{rows, summary, catalog_version, synthetic: True}`. A row has `code, name, purpose, state, scenario_id, errors, greedy, or_tools, difference_m, difference_pct, input_hash, provenance`; each method has `status, message, distance_m, vehicle_loads, facility_load_kg, facility_capacity_kg`. `report_csv(report) -> str`. `GET /api/v1/evaluation/report` and `GET /api/v1/evaluation/report.csv`.

- [ ] **Step 1: Write failing tests:** `test_report_always_has_ten_rows`; `test_state_not_loaded`; `test_state_not_run`; `test_state_blocked_shows_errors_and_no_distance`; `test_blocked_hides_an_older_batch`; `test_state_ran`; `test_infeasible_results_have_no_distance`; `test_summary_means_only_cases_where_both_found_routes`; `test_csv_leaves_no_route_blank`; `test_csv_neutralises_formulas` (Focus 3: leading `=`, `+`, `-`, `@` gain a leading `'`); `test_csv_matches_report`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** The state comes from the newest `ScenarioValidation` and the newest batch: blocked when the newest validation is not valid. Keep the module free of request objects.
- [ ] **Step 4: Run them, then the full backend suite.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add the evaluation report and CSV`

### Task 6: Error boundary and history page (Steps 18, 20)

**Files:**
- Create: `frontend/src/components/ErrorBoundary.jsx`, `frontend/src/pages/HistoryPage.jsx`, `frontend/src/components/ComparisonView.jsx`, `frontend/src/test/history.test.jsx`, `frontend/src/test/errors.test.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/components/AppLayout.jsx`, `frontend/src/services/api.js`, `frontend/src/pages/RouteOptimizationPage.jsx`, `frontend/src/styles.css`, the maplibre-mocking tests only if a new nav link breaks them

**Interfaces:**
- Consumes: Task 4 endpoints.
- Produces: `<ComparisonView comparison={...} />`, which holds the cards, difference note, map and stops and shows the run date; `getOptimizationHistory(params)`, `getOptimizationBatch(scenarioId, batchId)`; route `/history` and `/history/:scenarioId/:batchId`.

- [ ] **Step 1: Write failing tests:** "it lists runs newest first"; "it filters by scenario"; "it opens a saved run"; "it shows no distance for a failed method"; "it shows an empty state"; "the route page shows when a result was run"; "a crashing page shows the recovery screen"; "server errors show their reference".
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Move the display out of `RouteOptimizationPage` unchanged. Wrap the signed-in routes in `ErrorBoundary`, keyed by path so moving away clears it.
- [ ] **Step 4: Run the full frontend suite.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add the history page and error recovery`

### Task 7: Reports page (Steps 17, 19)

**Files:**
- Create: `frontend/src/pages/ReportsPage.jsx`, `frontend/src/test/reports.test.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/services/api.js`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 2 and 5 endpoints, `optimizeScenario`.
- Produces: `loadEvaluationScenarios()`, `getEvaluationReport()`, `downloadEvaluationCsv()`.

- [ ] **Step 1: Write failing tests:** "it shows all ten cases"; "it labels the results synthetic"; "it loads the scenarios"; "run all goes through each case in order with progress"; "a blocked case does not stop the run"; "a server error on one case does not stop the run and is shown" (Focus 4); "it shows no distance for a blocked case"; "it shows the difference only where both found routes"; "it downloads the CSV"; "it locks the buttons during a run".
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Run all skips `not_loaded` rows and reloads the report when finished. Add a `@media print` block hiding the sidebar and buttons.
- [ ] **Step 4: Run the full frontend suite and `npm run build`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add the evaluation report page`

### Task 8: Real-data evaluation

**Files:**
- Create: `backend/tests/test_evaluation_real_data.py`

- [ ] **Step 1: Write the test.** It skips if the dataset is absent. It loads the catalogue on real roads, runs validation and `optimize_scenario` with a 10 s limit for each `routes` case, and asserts each case matches `expected`, both checks pass, and every blocked case stays blocked.
- [ ] **Step 2: Run it.** Expected: PASS, or a case that disagrees. If a case disagrees, adjust that case's synthetic values, update the manifest, and ledger a ruling. Pin S10's `expected` from the measured outcome.
- [ ] **Step 3: Commit** `test: run the evaluation catalogue on the Trichy roads`

### Task 9: End to end and docs

**Files:**
- Modify: `README.md`, `NAGARFLOW_AI_Master_Guide.pdf`, `docs/PROJECT_TRACKER.md` only if it is tracked by then

- [ ] **Step 1: Run end to end.** Use a throwaway SQLite database and the real `ROAD_NETWORK_PATH`. In the built-in browser: load, Run all, read the report, download the CSV, open a run from History. Delete the database.
- [ ] **Step 2: Update the docs.** README gains "Evaluation" and "History" sections. Add Master Guide page 11C with the measured S01–S10 results and test counts.
- [ ] **Step 3: Final verification.** Both suites and `npm run build`. Expected: all pass.
- [ ] **Step 4: Commit** `docs: complete Stage 2 evaluation`
