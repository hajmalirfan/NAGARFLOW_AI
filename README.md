# NagarFlow

Starter monorepo for a React frontend, FastAPI backend, and PostgreSQL database.

## Project structure

```text
frontend/          React application (Vite)
backend/           FastAPI application
database/           Database setup and migration notes
docker-compose.yml  Local PostgreSQL service
```

## Requirements

- Node.js and npm
- Python 3.10+
- Docker Desktop (for PostgreSQL)

## Getting started

1. Copy `.env.example` to `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Make sure PostgreSQL is listening on port `5433`.

   If you already run PostgreSQL natively on that port, skip this step —
   check with `netstat -ano | findstr :5433`. Otherwise start the bundled
   container:

   ```powershell
   docker compose up -d db
   ```

   Do not start the container if something is already serving `5433`: you
   would be pointing the API at a second, empty database.

3. Start the backend in a terminal:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt -r requirements-dev.txt
   uvicorn app.main:app --reload
   ```

   The API is available at <http://localhost:8000>; interactive API docs are at
   <http://localhost:8000/docs>. Endpoints live under `/api/v1`; the original
   unversioned `/auth/*` paths still work but are no longer documented.

4. Start the frontend in another terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

   Vite prints the local frontend URL when it starts.

The bundled PostgreSQL container listens on port `5433` on your computer, so it
can run alongside a PostgreSQL service already using port `5432`. The backend
reads `DATABASE_URL` from the repository-root `.env` file. The
frontend reads `VITE_API_BASE_URL` from `frontend/.env` if you want to override
its default API URL.

If signup says the API cannot be reached, start the API in a separate terminal
using the backend steps above.

## Running the tests

Backend:

```powershell
cd backend
py -m pytest
```

The backend suite runs against an in-memory SQLite database, so it needs no
running PostgreSQL and never touches your development data.

Frontend:

```powershell
cd frontend
npm test
```

The frontend suite renders the real app in jsdom and replaces only the API
module, so routing, the auth guard and the dashboard are exercised for real.

## Accounts

Create an account with your name, email address, and a password of at least
8 characters. Passwords are hashed before they are stored in PostgreSQL. After
registration or sign-in, the API issues a short-lived access token and the
frontend opens the dashboard. Public sign-up always creates a planner. Set a
unique, random `JWT_SECRET_KEY` of at least 32 characters in `.env` before
deploying; the example value is for local development only.

## Roles

Each planner has a separate workspace. From the Team page, a planner can add,
change and remove linked accounts, which read that planner's data. These roles
are proposed views from the requirements document, not municipal job titles, and
their real authority is unconfirmed.

| Role | Can read | Can change |
| --- | --- | --- |
| Planner | Everything in their workspace | Everything, and team accounts |
| Reviewer | Dashboard, records, scenarios, validations, optimization, history, reports | Nothing |
| Management | Dashboard, reports, history list | Nothing |
| Driver preview | Scenario names, and saved routes for a run | Nothing |
| Facility preview | Scenario names, and expected load against capacity for a run | Nothing |

The server enforces this on every request and reads the role from the database
each time, so a change applies at once. The permission table is in
`backend/app/core/permissions.py`, and a test fails if any route has no declared
permission. Route Preview is marked "Synthetic preview, not a dispatch
instruction". It shows the newest run only, never an older route in place of a
failed run, and says so if the scenario changed after that run.

## Security

Five failed logins in 15 minutes, or five forgot-password requests in an hour,
per email or client address, get a 429. These counts are held in memory, so they
are per process and reset on restart.

Set `ENVIRONMENT` to anything but `development` when deploying. The server then
refuses to start on the default, example or a short JWT secret, turns off the API
docs and sends `Strict-Transport-Security`. If it stays unset, none of this
applies. The tests, audits, fixes and open items are in
[the security report](docs/security/security-report.md).

## Performance

`backend/scripts/perf_check.py` seeds a new SQLite file with synthetic data and
measures a running API. Results and their limits are in
[the performance report](docs/performance/performance-report.md). On a laptop
with SQLite and five concurrent users, the dashboard, scenario list and history
stayed under the assumed 500 ms p95, and the evaluation report did not, at 600 to
683 ms. PostgreSQL has not been measured.

`OPTIMIZER_MAX_CONCURRENT` (default 2) limits optimizations running at once. A
run past the limit gets a 503 and can be tried again. There is no queue, and an
optimization holds its request open for about 18 seconds.

## Dashboard

After signing in, the dashboard shows six summary cards and five sections
describing the municipality's waste transportation status. Every figure comes
from `GET /api/v1/dashboard/summary`, which aggregates the signed-in
coordinator's configured records and scenarios. Nothing is sampled or
estimated: with no data configured the cards genuinely read zero, and the
facility card reads "Not configured" rather than implying a real capacity of
zero.

Sidebar destinations whose development step has not been reached say so plainly
instead of showing an empty shell or placeholder statistics.

## Scenarios

The authenticated `/api/v1/scenarios` API and the Scenarios page support
listing, creating, viewing, editing, and deleting planning scenarios. A
scenario uses existing database records: one configured depot, one processing
facility, exactly two vehicles, and six to ten storage points. No sample
resources are inserted. The form explains which setup records are missing;
depots are managed through Depot Management. A scenario
with an optimization run marked as queued, pending, running, or in progress
cannot be deleted.

## Depot management

The authenticated `/api/v1/depots` API and Depot Management page support
listing, adding, viewing, editing, and deleting the signed-in coordinator's
depots. Depot codes are unique, coordinates are range-validated, and only one
active depot is allowed per coordinator. Inactive depots are excluded from
scenario choices; a depot linked to a scenario cannot be deleted. The backend
adds the depot fields to the earlier minimal depot table on startup. Existing
records without coordinates remain incomplete until an administrator enters
their real location.

## Vehicle management

The authenticated `/api/v1/vehicles` API and Vehicles page manage the
registered fleet. Each scenario selects exactly two vehicles. Registration numbers are unique, capacity must be
positive, and each vehicle uses an active configured depot as its starting
point. Available vehicles are the only vehicles offered to new scenarios, and
the selected vehicles must belong to that scenario's depot. Scenarios cannot
exceed the selected fleet's combined single-trip capacity; a vehicle linked to
a scenario cannot be deleted or made unavailable until its scenario is
updated. The startup schema upgrade preserves older scenario-owned vehicle
records without inventing their missing registration or depot details.

## Storage point management

The authenticated `/api/v1/storage-points` API and Storage Point Management
page provide create, list, detail, update, and delete operations for the
signed-in coordinator's real collection locations. Point codes are unique,
coordinates are range-checked, and waste quantity is stored as
`NUMERIC(12,2)` with a non-negative constraint. Points are independent records
that scenarios reference through `scenario_storage_points`; a linked point
cannot be deleted, and a quantity change is rejected if it would exceed the
combined capacity of a linked scenario's vehicles. Scenarios continue to
require six to ten selected points.

The management page supports search and availability filtering and displays
registered coordinates on a MapLibre map using OpenStreetMap raster tiles,
with OpenStreetMap attribution. The initial map view uses central Trichy
(10.8050, 78.6856); that is only a map center, not a seeded storage point. Availability is stored as a static status only; no
time-dependent collection logic is applied before the DEC-003 decision.
Existing scenario-owned points are migrated to coordinator ownership;
legacy records without codes receive a clearly marked `LEGACY-SP-<id>` code.

## Road connectivity

A scenario is only marked valid once its trip has been checked against real
roads. The check reads an OpenStreetMap GeoPackage named by
`ROAD_NETWORK_PATH` in `.env`; a relative path starts at the repository root.
The dataset is 35 MB, covers about 78.163–79.005°E and 10.301–11.385°N, and
is local only, so `*.gpkg` is ignored by git. Without a usable file, scenarios
stay `incomplete` and optimization stays blocked.

The network loads once, on the first validation after the server starts,
which takes about nine seconds. After that a check takes milliseconds.

A location must be within `ROAD_SNAP_MAX_M` metres of a usable road. The
default of 200 is an assumption, not a measured figure. Beyond it the location
is reported as `ROAD_TOO_FAR`. The depot must then reach every storage point,
every point must reach every other point, and every point must reach the
facility; a missing route is reported as `ROAD_UNREACHABLE`.

Roads marked private or closed to motor vehicles are excluded, and roads with
no access tag count as usable. Truck size and weight limits are not checked,
and the dataset has no turn restrictions, so a passing check means a route
exists on the network, not that a truck may legally take it.

## Route optimization

**Route Optimization** runs two methods on identical inputs for a valid
scenario: a Greedy baseline and Google OR-Tools. Both results are saved and
shown side by side, and each passes through an independent checker before it
is reported. OR-Tools searches for `OPTIMIZER_TIME_LIMIT_S` seconds, 10 by
default, and reports the best route it found, not a proven optimum.

A scenario may set a shift start and end. Each storage point may set when its
waste becomes available. Under decision DEC-003, a vehicle that arrives early
waits at the point until the waste is ready. A point that becomes available
at or after the end of the shift fails validation.

Distances come from the road network. Travel times are estimates from assumed
speeds in km/h, because no measured speeds exist for these roads: motorway and
trunk 50, primary 40, secondary 35, tertiary 30, unclassified 25, residential
20, service 15.

| Status | Meaning |
| --- | --- |
| `feasible` | Best route found, and it passed the checker. |
| `optimal` | Proven best route, and it passed the checker. |
| `no_solution` | The method found no route, though one may exist. |
| `infeasible` | A pre-check proved no route can meet the limits. Most impossible problems report `no_solution` instead. |
| `timeout` | Time ran out before any route was found. |
| `invalid_result` | The checker rejected the route, so it is not shown. |

Only `feasible` and `optimal` results carry a distance. Optimizing a scenario
that is not valid returns a 409 with the validation report.

## Evaluation report

**Reports** runs the S01–S10 evaluation cases. **Load evaluation scenarios**
creates them as records named `SYNTH-`, and adds about 10 depots, 10 facilities,
20 vehicles and 76 storage points to your lists. They stay out of the dashboard
totals and the one-active-depot rule, and codes starting `SYNTH-U` are reserved
for them. Pressing it again creates nothing new. **Run all** optimizes each case in turn, which takes about
a minute and a half. **Download CSV** saves the same rows, and printing the page
gives a PDF.

All waste, capacity and time values in these cases are synthetic. Locations are
OpenStreetMap road positions, not municipal sites. The cases live in
`backend/app/evaluation/catalog`, and a file that no longer matches
`manifest.json` is refused.

A case that fails validation shows as **Blocked** with its reason, even if an
older run exists, and never shows a distance. S04, S05 and S09 are blocked by
design once they have been checked. A run older than a change to its records
shows as **Out of date** and leaves the averages until it is run again. A case
whose inputs no longer match the catalogue is marked as edited, and an outcome
other than the expected one is flagged. A difference appears only where both
methods found routes.

## Optimization history

**History** lists every paired run, newest first, and can be filtered by
scenario and status. Opening a run shows that saved result and its map, which do
not change if the scenario does.

## Unexpected errors

An unexpected server failure returns a plain message with a short reference.
The details go only to the server log, under that reference. A page that crashes
shows a recovery screen and leaves the rest of the app usable.

## Forgotten passwords

From the sign-in screen, **Forgot password?** asks for an email address and the
API emails a reset link. The link opens `/reset-password?token=…` in the
frontend, which checks the token before showing the new-password form.

Reset tokens are 256 bits of cryptographically secure randomness. Only a
SHA-256 hash of each token is stored, so a copy of the database cannot be used
to take over an account. A token expires 15 minutes after it is issued, works
exactly once, and a completed reset invalidates every other outstanding token
for that account. The `forgot-password` endpoint always returns the same
response whether or not the address has an account, so it cannot be used to
discover which addresses are registered.

### Email in development

`SMTP_HOST` is empty by default, so **no real email is sent**. Each message is
instead written to `backend/dev_emails/` and the path is logged by the API.
Open the newest file there and copy the reset link out of it.

To send real email, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD` and `EMAIL_FROM` in `.env`. Also set `FRONTEND_BASE_URL` to the
address your users' browsers can open, because that is what the reset link
points at.
