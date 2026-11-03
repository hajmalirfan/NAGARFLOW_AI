# Deployment Guide

**Status: prepared, not deployed.** Everything here was built and run on one laptop with Docker on November 3, 2026. Nothing has been hosted, and no real address, mail server or database exists yet.

The package is three containers in `docker-compose.prod.yml`:

| Service | Image | What it does |
| --- | --- | --- |
| `db` | `postgres:16` | The database, with its data in the `db-data` volume |
| `backend` | `python:3.12-slim`, built from `backend/` | The API on port 8000, running as user `app` |
| `frontend` | built with `node:20-alpine`, served by `nginx:1.27-alpine` | The React app on port 8080, with its own security headers |

A proxy that ends TLS is not included. It belongs in front of both web services, on the same host.

## Server needs

These come from the local container run, not from a hosted server.

| Item | Measured or assumed |
| --- | --- |
| Backend memory | About 585 MiB after one optimization of S01. Allow at least 1 GB for it |
| Database memory | About 43 MiB with one planner and the ten catalogue cases |
| Frontend memory | About 10 MiB |
| CPU | Each optimization uses one core for about 16 to 22 seconds. Two may run at once by default |
| Disk | The roads file, plus the database. The seeded performance database dumped to about 330 KB |

A small server with 2 CPU cores and 2 GB of memory is a reasonable starting assumption. It has not been tried.

## Settings

Copy `.env.production.example` to `.env.production` and fill in every value. Never commit the copy. Generate secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

| Setting | What to put |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER` | The database name and user. `nagarflow` for both is fine |
| `POSTGRES_PASSWORD` | A generated password. The server refuses the example one |
| `DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@db:5432/DB`, with the same three values |
| `JWT_SECRET_KEY` | A generated secret of at least 32 characters. The server refuses the default and example ones |
| `CORS_ORIGINS` | The frontend's public address, as a JSON list, such as `["https://nagarflow.example.org"]`. No localhost |
| `FRONTEND_BASE_URL` | The same address. Password reset links point here |
| `API_ORIGIN` | The API's public address. It is built into the frontend and its Content-Security-Policy, so rebuild the frontend after changing it |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | The mail server for password resets. `SMTP_HOST` is required |
| `EMAIL_FROM` | The sender shown on reset emails |
| `ROAD_NETWORK_HOST_PATH` | Where the OpenStreetMap GeoPackage sits on the host |
| `ROAD_SNAP_MAX_M` | How far a point may be from a road, in metres. Default 200 |
| `OPTIMIZER_TIME_LIMIT_S` | The OR-Tools search limit in seconds. Default 10 |
| `OPTIMIZER_MAX_CONCURRENT` | How many optimizations may run at once. Default 2. Another gets a 503 |
| `TRUSTED_PROXY_HOPS` | Set to 1 in the compose file. See the proxy section |

The compose file also sets `ENVIRONMENT=production`. In production the server refuses to start, and names every problem at once, when:

- the JWT secret is the default, the example one, or shorter than 32 characters
- `CORS_ORIGINS` or `FRONTEND_BASE_URL` contains localhost or 127.0.0.1
- `SMTP_HOST` is empty
- the database password is the example one
- `ROAD_NETWORK_PATH` is empty

A roads path that points at a missing file only logs a warning, because the file may be mounted after the check.

## First start

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml ps
```

All three services should show `healthy`. The backend waits for the database to be healthy, then creates its tables on first start.

Create the first planner by signing up in the browser. Every sign-up is a planner, who then adds reviewer, management, driver and facility accounts from the Team page.

## The roads file

The GeoPackage is mounted read-only at `/data/roads.gpkg` and is never copied into an image. Place it at `ROAD_NETWORK_HOST_PATH` before starting. To replace it, copy the new file over the old one and run `docker compose ... restart backend`.

## Backup and restore

This was tried on the local PostgreSQL performance database. All four checked tables (`users`, `scenarios`, `storage_points`, `optimization_runs`) had the same row counts after the restore.

Back up from the running container:

```bash
docker compose -f docker-compose.prod.yml exec db pg_dump -U nagarflow -Fc -f /tmp/nagarflow.dump nagarflow
docker compose -f docker-compose.prod.yml cp db:/tmp/nagarflow.dump ./nagarflow.dump
```

Restore into a new database, then point `DATABASE_URL` at it:

```bash
docker compose -f docker-compose.prod.yml cp ./nagarflow.dump db:/tmp/nagarflow.dump
docker compose -f docker-compose.prod.yml exec db createdb -U nagarflow nagarflow_restore
docker compose -f docker-compose.prod.yml exec db pg_restore -U nagarflow --no-owner -d nagarflow_restore /tmp/nagarflow.dump
```

Keep backups off the server. How often to take them has not been decided.

## Upgrades

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

There is no Alembic. On start, the backend creates missing tables and runs eight upgrade functions that add missing columns. Each one is safe to run again, and all eight were run twice on PostgreSQL in the tests. What they cannot do is rename a column, change a type, or remove anything. A change like that needs a hand-written step, so take a backup before every upgrade.

## The proxy

Put one proxy in front, such as nginx or Caddy, that ends TLS and forwards to `127.0.0.1:8080` for the frontend and `127.0.0.1:8000` for the API.

`TRUSTED_PROXY_HOPS=1` tells the backend to take the client address for rate limiting from the last entry the proxy adds to `X-Forwarded-For`. That is only safe while nothing else can reach the backend, so the compose file publishes both ports on 127.0.0.1 only. If the proxy runs on another machine, change that binding and allow only the proxy through the firewall. With no proxy at all, set `TRUSTED_PROXY_HOPS=0`, or clients could choose their own address.

An optimization holds its request open for up to about 22 seconds. Give the proxy a read timeout of at least 60 seconds for the API.

## The smoke check

After every start or upgrade, run this from any machine:

```bash
python backend/scripts/smoke_check.py --api https://api.nagarflow.example.org --frontend https://nagarflow.example.org
```

It only sends GET requests and signs in to nothing. It checks that health returns ok, the API docs are off, the security headers and HSTS are present, an unsigned request gets 401, and the frontend serves the app with its headers and Content-Security-Policy. It prints one line per check and exits 1 if any fails.

In the local container run all five passed. One planner then signed up, loaded the ten catalogue cases and optimized S01 with a 200 response.

## What is not done

- **Nothing is hosted.** There is no server, domain, TLS certificate, mail server or backup schedule.
- **PostgreSQL versions differ.** The tests and performance runs used PostgreSQL 18. The compose file uses `postgres:16`. Version 16 ran only in the container check, not the full test suite.
- **Performance on PostgreSQL** missed the assumed 500 ms p95 for the dashboard, history and report on the laptop. Measure again on the real server. See [the performance report](../performance/performance-report.md).
- **One backend process.** The rate limits and the optimizer limit are held in memory, per process. Do not scale the backend past one process without moving them.
- **No job queue** for optimizations.
- **The browser path through CORS** was not exercised in the containers, because the check used placeholder public addresses.
