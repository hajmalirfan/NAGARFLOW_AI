# Stage 2: Evaluation, History, Reports and Error Handling

Roadmap Steps 17–20. Branch `feat/evaluation`, stacked on `feat/routing-core`.

## Goal

Report all ten S01–S10 categories for both methods, including those with no
valid route. Let a coordinator look back at past runs. Make failures readable.

## Rules carried from the project documents

- All ten cases are reported. A case with no route never shows a distance.
- All catalogue values are synthetic and labelled so. Only the road locations
  are real, and they are OpenStreetMap road positions, not municipal sites.
- Nothing runs on a scenario that fails validation.
- OR-Tools is never described as optimal unless it proves it.
- A difference is shown only where both methods found routes.

## Step 17: Evaluation catalogue

**Files.** `backend/app/evaluation/catalog/S01.json` to `S10.json`, plus
`manifest.json` holding `catalog_version` and each file's SHA-256. Each case
holds its depot, two vehicles, 6–10 points, facility, optional shift and
availability times, and an `expected` block: `outcome` (`routes` or
`blocked`) and, when blocked, the validation error codes.

| Case | Design | Expected |
| --- | --- | --- |
| S01 | Ordinary loads, about 60% of capacity | routes |
| S02 | One heavy point and several light ones | routes |
| S03 | Total at least 95% of combined vehicle and facility capacity | routes |
| S04 | One point larger than either vehicle | blocked |
| S05 | Total above facility capacity, within vehicle capacity | blocked |
| S06 | Points available at different times within the shift | routes, with waiting |
| S07 | Points spread across the study area | routes |
| S08 | Layout where nearest-first choices are poor | routes |
| S09 | Total above combined vehicle capacity, within facility capacity | blocked |
| S10 | Near capacity, spread out, staggered availability, tight shift | as measured |

S10's `expected` is recorded from the first real-data run, then pinned. S08
makes no claim that OR-Tools wins; the gap is measured.

**Loading.** `POST /api/v1/evaluation/scenarios` creates the catalogue as
ordinary records owned by the caller, with codes such as `SYNTH-S01-P1`.
`Scenario` gains a nullable `evaluation_code` (`S01`...). A case the caller
already has is skipped, so loading twice creates nothing new. Records are
inserted directly, so S04, S05 and S09 can exist; validation then blocks them.
Loading is all or nothing. The response lists each case and its scenario id.

**Running.** The Reports page offers **Run all**, which calls the existing
`POST /scenarios/{id}/optimize` for each case in order, shows progress, and
carries on after a blocked or failed case. No long-running new endpoint.

## Step 18: Optimization history

`OptimizationRun` gains a JSON `provenance`: catalogue version when the
scenario is a catalogue case, road dataset file name, OR-Tools version,
time limit and snap limit. Old rows hold null.

- `GET /api/v1/optimization-history` takes `scenario_id`, `status`, `limit`
  (default 25, maximum 100) and `offset`. It returns one row per batch, newest
  first, for the caller's scenarios: date, scenario, both statuses and
  distances, and the difference. `status` matches either method. Rows with no
  `batch_id` are left out.
- `GET /api/v1/scenarios/{id}/optimization/{batch_id}` returns one saved
  comparison, and 404 for another coordinator's scenario or an unknown batch.

A new History page lists these with filters, and a row opens the saved
comparison and map, reusing the Route Optimization display. That page also
shows when its result was run.

## Step 19: Reports

`GET /api/v1/evaluation/report` returns one row per case, always ten, in
order. Each row has a `state`:

- `not_loaded`: the caller has no such scenario.
- `not_run`: no batch and no failing validation.
- `blocked`: the newest validation is not valid. Shows its error codes and
  messages, with no distance, even if an older batch exists.
- `ran`: both methods' status, message, distance, vehicle loads and combined
  load against facility capacity; the difference where both have routes; and
  provenance and input hash.

The summary counts cases by state, cases where both found routes, and the
mean difference over those cases. It is labelled synthetic.

`GET /api/v1/evaluation/report.csv` returns the same rows, one per case, with
blank distances for no route, never zero. Cells are neutralised against
spreadsheet formula injection. The page has a print stylesheet for PDF.

The Reports placeholder becomes this page, with **Load evaluation scenarios**,
**Run all** and **Download CSV**. Assumptions and limits are stated on it.

## Step 20: Error handling

- Backend: a catch-all handler logs the exception with a short reference and
  returns 500 `{detail, reference}`, with no internal detail. Existing 4xx
  responses are unchanged.
- Frontend: `api.js` shows the reference with server errors. An error boundary
  around the signed-in routes shows a recovery screen with a reload action.
- A failed run says why: when no route is found and a shift is set, the message
  points at the shift length and availability times.
- A point ready at or after shift end is a validation error, since it cannot
  also reach the facility. This tightens the current strict `>` check.
- Optimizing with the road-connectivity override and no road network returns
  409, not a server error.
- Mixed timezone-aware and plain shift times return 422.
- The README `infeasible` row is reworded to match what the solver reports.

## Testing

- Catalogue: `test_manifest_contains_s01_through_s10`, checksums match, every
  case has 6–10 points and two vehicles, and every value is labelled synthetic.
- Loading twice creates nothing new, and a failure leaves nothing behind.
- With fake roads: all cases report both methods, blocked cases match their
  `expected` codes, and `test_infeasible_results_have_no_distance`.
- History: paging, filters, ownership, old rows.
- Report: all four states, a blocked case hiding an older batch, CSV blanks and
  formula neutralising.
- Errors: the 500 body leaks nothing, the error boundary renders, plus a test
  each for the new 409, 422 and messages.
- A real-data test runs all ten on the Trichy dataset and skips if absent.
- End to end: load, run all, and read the report in the browser against a
  throwaway database.

## Out of scope

Background job queues, per-role access (Stage 3), PDF generation on the
server, charts, and removing loaded catalogue records.

## Done when

All ten cases appear in the report with both methods or a blocked reason, CSV
matches the page, history reopens a past run, both suites pass, and README and
Master Guide record the measured results.
