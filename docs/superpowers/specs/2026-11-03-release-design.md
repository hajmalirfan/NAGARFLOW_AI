# Stage 4: PostgreSQL and Deployment Package

Roadmap Steps 24 and 25. Branch `feat/release`, stacked on `feat/access-hardening`.

## Goal

Prove the backend on PostgreSQL, and prepare a tested deployment package. Nothing goes live.

## Decisions

- **No hosting:** there is no account, domain or cost. Step 25 is recorded as "prepared, not deployed".
- **No Alembic:** the startup upgrade functions in `app/db/migrations.py` stay. They exist and are tested, and moving to Alembic would mean rebuilding their history. The guide states the cost: there is no version history or rollback for schema changes.
- **Throwaway database:** PostgreSQL work uses a cluster created with `initdb` in a temporary folder, on its own port. The installed `postgresql-x64-18` service and its data are never touched, and no admin rights are needed.
- **Version gap:** the throwaway cluster is PostgreSQL 18, while `docker-compose.yml` uses `postgres:16`. The production compose file pins 16 to match local development. The guide records that the tests ran on 18, and the container check runs on 16.
- **Synthetic data:** every value is synthetic, as in earlier stages.

## Step 24: PostgreSQL

**Tests on PostgreSQL.** `backend/tests/conftest.py` reads `TEST_DATABASE_URL`.
- When it is unset, tests use in-memory SQLite as now.
- When it is set, each test gets an empty schema in that database, and the URL must name a database whose name ends in `_test`. Otherwise the suite stops before touching it.
- The whole backend suite must pass both ways.

**New PostgreSQL tests.** These run only when `TEST_DATABASE_URL` is set, and are skipped otherwise.
- Removing a planner removes its linked accounts through the foreign key cascade.
- Every upgrade function runs on tables that already exist, twice, without error.
- Decimal waste and capacity values, and timezone handling of shift times, round-trip unchanged.
- Two sessions saving the same unique code: one succeeds and the other gets the existing 409, never a 500.

**Performance on PostgreSQL.**
- `perf_check.py seed` accepts a PostgreSQL URL, but only for a database that exists and has no tables. Otherwise it refuses.
- Measurements are added to `docs/performance/performance-report.md` beside the SQLite results, with the same caveats.

**Backups.** The guide gives `pg_dump` and `pg_restore` commands. These are run once on the throwaway database, and the restored row counts must match.

## Step 25: Deployment package

**Containers.**
- `backend/Dockerfile`: Python 3.12 slim, installs `requirements.txt`, runs `uvicorn` as a non-root user, and has no test tools.
- `frontend/Dockerfile`: builds with Node, then serves `dist` from nginx. `frontend/nginx.conf` sends the SPA fallback and these headers:
    - `X-Content-Type-Options`
    - `X-Frame-Options`
    - `Referrer-Policy`
    - A `Content-Security-Policy` that allows the API origin and the map's tile sources only.
- The API address is set when the frontend is built, through `VITE_API_BASE_URL`.
- `.dockerignore` files keep `.env`, `node_modules`, the dataset, `dev_emails` and test databases out of the images.

**`docker-compose.prod.yml`.**
- Runs `db` (`postgres:16` with a named volume and a health check), `backend` and `frontend`.
- Sets `ENVIRONMENT=production`.
- Mounts the roads GeoPackage read-only from a host path named by `ROAD_NETWORK_HOST_PATH`, so it is never in an image or in git.
- Takes every secret from an env file that is not committed. `.env.production.example` lists them with placeholders.

**Production checks.** `check_production_settings` also refuses to start in these cases:
- `CORS_ORIGINS` or `FRONTEND_BASE_URL` still contains `localhost` or `127.0.0.1`.
- `SMTP_HOST` is empty, because reset links would otherwise be written to disk and logged.
- `DATABASE_URL` still contains the example password `change-this-local-password`.
- `ROAD_NETWORK_PATH` is empty, or does not point at a file. It warns, and does not refuse, if the file is missing at startup, because a mount can arrive late.

**Proxy addresses.** `TRUSTED_PROXY_HOPS`, default 0.
- At 0, the rate limit uses the connection's address as now.
- At N, it reads the address N hops from the right of `X-Forwarded-For`, and falls back to the connection's address when the header is missing or too short.
- This closes the Stage 3 open item, where everyone behind a proxy shared one address.

**Smoke check.** `backend/scripts/smoke_check.py --url URL` checks a running deployment:
- Health returns 200.
- Docs return 404.
- The security headers are present.
- An unauthenticated request gets 401.
- The frontend index loads.

It signs in to nothing, and writes nothing.

**Container check.** If Docker Desktop is running, the images are built, the compose stack is started with throwaway values and the real roads file, the smoke check passes, and one planner optimization runs. The stack and its volume are then removed. If Docker is not running, I ask the user once to start it. If they don't, the package is recorded as "written, not built", and the gap is stated plainly.

**Guide.** `docs/deployment/deployment-guide.md` covers:
- What a server needs: memory for the Trichy road network, measured during the container check, and about 18 seconds per optimization.
- Every setting, and how to make secrets.
- First start, and creating the first planner.
- The roads file mount.
- Backups and restore.
- Upgrades, and the cost of not having Alembic.
- The smoke check.
- What is not done: hosting, HTTPS and domains, a job queue, shared rate limits, and the deferred minor issues.

## Testing

- Test-first for every code change: the conftest switch, production checks, proxy addresses, the perf seed guard and the smoke check.
- The smoke check is tested against the test client.
- Both test suites pass, and the backend suite also passes on PostgreSQL.
- One fresh review of the whole branch at the end.

## Out of scope

- Going live, domains, HTTPS certificates and a hosting account.
- Alembic, a job queue and shared rate-limit storage.
- Deferred minor issues from earlier stages.

## Done when

- The backend suite passes on SQLite and on PostgreSQL.
- The frontend suite and build pass.
- The PostgreSQL-only tests pass.
- PostgreSQL performance results are recorded.
- A backup restores with matching counts.
- The deployment package exists, and is either built and smoke-checked or plainly recorded as unbuilt.
- The deployment guide is written.
- The README and Master Guide record Step 24 as done and Step 25 as prepared, not deployed.
