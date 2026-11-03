# Performance Report

Date: November 2, 2026, with PostgreSQL added on November 3, 2026. Measured with `backend/scripts/perf_check.py` against one local `uvicorn` process.

These numbers come from one laptop, first on SQLite and then on PostgreSQL 18. They show how the code behaves under load, not how a deployed system will.

## Setup

| Item | Value |
| --- | --- |
| Machine | Intel Core i5-12450HX, 12 threads, 16 GB memory, Windows 11 |
| Database | Throwaway SQLite file |
| Seeded data, all synthetic | 50 scenarios, 500 storage points, 2,000 saved runs |
| Road network | The Trichy OpenStreetMap dataset |
| Load | 5 concurrent clients, 20 requests each, 100 requests per endpoint |
| Target | p95 under 500 ms for reads at 5 concurrent users. This is an assumption, because no target has been set |

## Results

Both runs came after the dashboard fix below. No request failed.

| Endpoint | Run 1 p50 | Run 1 p95 | Run 2 p50 | Run 2 p95 | Target |
| --- | --- | --- | --- | --- | --- |
| Dashboard | 194 ms | 249 ms | 186 ms | 414 ms | Met |
| Scenario list | 136 ms | 187 ms | 147 ms | 404 ms | Met |
| History | 312 ms | 375 ms | 262 ms | 434 ms | Met |
| Evaluation report | 422 ms | 601 ms | 434 ms | 683 ms | **Missed** |
| Validation (a write) | 161 ms | 1,054 ms | 184 ms | 289 ms | Target covers reads only |

The p95 figures moved noticeably between the two runs, so treat them as rough rather than exact. Only the first run's validation p95 went over a second. No cause was established for that spike.

## Optimization limit

Three optimizations were started together, with `OPTIMIZER_MAX_CONCURRENT` at its default of 2.

| Run | First result | Second result |
| --- | --- | --- |
| Two runs that got a slot | 200 in about 18.8 s | 200 in about 17.6 s |
| The third run | 503 in 1.2 s | 503 in 1.1 s |

The limit worked as designed. The 503 takes about a second because the scenario is validated first. A run takes about 18 seconds in total, because the 10 second limit covers the OR-Tools search only. The rest of the time goes on road distances, Greedy and route geometry.

## PostgreSQL

The same seed and load were run against a throwaway local PostgreSQL 18 cluster on the same laptop, with the server and database on one machine. No request failed.

| Endpoint | Run 1 p50 | Run 1 p95 | Run 2 p50 | Run 2 p95 | SQLite p95 (runs 1 / 2) | Target |
| --- | --- | --- | --- | --- | --- | --- |
| Dashboard | 352 ms | 583 ms | 358 ms | 521 ms | 249 / 414 ms | **Missed** |
| Scenario list | 282 ms | 392 ms | 334 ms | 761 ms | 187 / 404 ms | Met in run 1 only |
| History | 696 ms | 966 ms | 400 ms | 1,070 ms | 375 / 434 ms | **Missed** |
| Evaluation report | 1,320 ms | 1,647 ms | 495 ms | 696 ms | 601 / 683 ms | **Missed** |
| Validation (a write) | 170 ms | 1,635 ms | 131 ms | 173 ms | 1,054 / 289 ms | Target covers reads only |

Three optimizations started together again gave 200, 200 and 503. The two runs took about 21.3 s in the first run and 16.0 s in the second. The 503 came back in 124 ms and 88 ms.

Reads were slower on PostgreSQL than on SQLite here, and they varied more between runs. The first run was the first to touch the new database, so a cold cache may explain part of it, but no cause was established. A local SQLite file has no network or connection cost, so this comparison does not predict a hosted server, where the database usually sits on its own machine. Treat these as a baseline to repeat on the real hosting, not as a verdict on PostgreSQL.

## Backup and restore

The PostgreSQL performance database was backed up and restored into a new database, then the row counts were compared.

```bash
pg_dump -h HOST -U nagarflow -Fc -f nagarflow.dump nagarflow_perf
createdb -h HOST -U nagarflow nagarflow_restore
pg_restore -h HOST -U nagarflow --no-owner -d nagarflow_restore nagarflow.dump
```

| Table | Original | Restored |
| --- | --- | --- |
| users | 1 | 1 |
| scenarios | 50 | 50 |
| storage_points | 500 | 500 |
| optimization_runs | 2,008 | 2,008 |

All four counts match. The dump was about 330 KB. The 2,008 runs are the 2,000 seeded ones plus the 8 saved by the optimization checks above.

## What was fixed

The first measurement showed the dashboard at p50 4,644 ms and p95 6,801 ms. It loaded the full saved routes of every run but only read each run's status and distance. It now selects those two columns, and a test keeps saved routes out of that query. This cut the dashboard's p50 to about 190 ms.

## What stays open

- **Evaluation report:** p95 is 600 to 683 ms against the assumed 500 ms. It loads saved routes for all ten cases to show vehicle loads. There was no small fix, and it is a page used occasionally, so this is recorded, not changed.
- **No job queue:** an optimization holds its request open for about 18 seconds. A proxy with a short timeout could cut it off, which Stage 4 needs to allow for.
- **The limit is per process:** several server processes would each allow two runs.
- **PostgreSQL reads:** dashboard, history and report p95 all missed the assumed 500 ms on PostgreSQL. This needs measuring again on the real hosting before anything is changed.
- **Not measured:** a database on its own machine, network delay, frontend load time, and more than five users.
