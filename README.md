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
frontend opens the dashboard. Set a unique, random
`JWT_SECRET_KEY` in `.env` before deploying; the example value is for local
development only.

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
which takes about four seconds. After that a check takes milliseconds.

A location must be within `ROAD_SNAP_MAX_M` metres of a usable road. The
default of 200 is an assumption, not a measured figure. Beyond it the location
is reported as `ROAD_TOO_FAR`. The depot must then reach every storage point,
every point must reach every other point, and every point must reach the
facility; a missing route is reported as `ROAD_UNREACHABLE`.

Roads marked private or closed to motor vehicles are excluded, and roads with
no access tag count as usable. Truck size and weight limits are not checked,
and the dataset has no turn restrictions, so a passing check means a route
exists on the network, not that a truck may legally take it.

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
