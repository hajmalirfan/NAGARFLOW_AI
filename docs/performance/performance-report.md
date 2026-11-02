# Performance Report

Date: November 2, 2026. Measured with `backend/scripts/perf_check.py` against one local `uvicorn` process.

These numbers come from a laptop running SQLite. They show how the code behaves under load, not how a deployed system will. PostgreSQL has not been measured, which belongs to Stage 4.

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

## What was fixed

The first measurement showed the dashboard at p50 4,644 ms and p95 6,801 ms. It loaded the full saved routes of every run but only read each run's status and distance. It now selects those two columns, and a test keeps saved routes out of that query. This cut the dashboard's p50 to about 190 ms.

## What stays open

- **Evaluation report:** p95 is 600 to 683 ms against the assumed 500 ms. It loads saved routes for all ten cases to show vehicle loads. There was no small fix, and it is a page used occasionally, so this is recorded, not changed.
- **No job queue:** an optimization holds its request open for about 18 seconds. A proxy with a short timeout could cut it off, which Stage 4 needs to allow for.
- **The limit is per process:** several server processes would each allow two runs.
- **Not measured:** PostgreSQL, network delay, frontend load time, and more than five users.
