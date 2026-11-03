"""Seed a throwaway database, then measure a running API against it.

    python scripts/perf_check.py seed --db perf.db
    python scripts/perf_check.py seed --db postgresql+psycopg://USER:PASSWORD@HOST/nagarflow_perf
    # Start uvicorn with DATABASE_URL set to the same database and ROAD_NETWORK_PATH set.
    python scripts/perf_check.py measure --url http://127.0.0.1:8000 --password <printed>

Every value it seeds is synthetic. It starts nothing itself, and it refuses
to touch any database except a new SQLite file or an empty PostgreSQL one.
"""

import argparse
import secrets
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.evaluation.catalog_loader import _create_case, load_catalog, read_catalog  # noqa: E402
from app.models import OptimizationRun, StoragePoint, User  # noqa: E402

EMAIL = "perf@example.com"
SCENARIOS = 50
POINTS = 500
RUNS = 2000
SQLITE_PREFIX = "sqlite:///"
POSTGRES_PREFIX = "postgresql+psycopg://"
READS = {
    "Dashboard": "/api/v1/dashboard/summary",
    "Scenario list": "/api/v1/scenarios",
    "History": "/api/v1/optimization-history",
    "Report": "/api/v1/evaluation/report",
}


def percentile(values: list[float], pct: float) -> float:
    """Linear interpolation between the closest ranks."""
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _saved_route(index: int) -> dict:
    stops = [
        {"code": f"P{stop}", "arrival_s": 300 * stop, "service_s": 60, "wait_s": 0,
         "latitude": 10.8, "longitude": 78.7}
        for stop in range(1, 5)
    ]
    geometry = [[10.8 + step / 1000, 78.7 + step / 1000] for step in range(200)]
    return {
        "vehicle_id": 1, "vehicle_name": f"Synthetic vehicle {index}", "capacity_kg": 6000.0,
        "load_kg": 1000.0, "distance_m": 10000, "finish_s": 3600, "stops": stops,
        "geometry": geometry,
    }


def seed(database_url: str, password: str) -> dict[str, int]:
    if database_url.startswith(SQLITE_PREFIX):
        if Path(database_url[len(SQLITE_PREFIX):]).exists():
            raise ValueError("That file already exists, and this script never overwrites one.")
        engine = create_engine(database_url)
    elif database_url.startswith(POSTGRES_PREFIX):
        engine = create_engine(database_url)
        if inspect(engine).get_table_names():
            engine.dispose()
            raise ValueError("That database already has tables, and this script never adds to one.")
    else:
        raise ValueError("Performance data only goes in a new SQLite file or an empty PostgreSQL database.")

    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        user = User(name="Performance", email=EMAIL, hashed_password=hash_password(password))
        db.add(user)
        db.commit()

        scenarios = list(load_catalog(db, user))
        cases = read_catalog()
        for number in range(SCENARIOS - len(scenarios)):
            case = {**cases[number % len(cases)], "code": f"X{number:02d}"}
            scenario = _create_case(db, user, case)
            scenario.evaluation_code = None
            scenarios.append(scenario)
        db.flush()

        existing = sum(len(scenario.selected_storage_points) for scenario in scenarios)
        db.add_all(
            StoragePoint(
                user_id=user.id, name=f"Synthetic point {number}", point_code=f"PERF-{number}",
                latitude=10.8, longitude=78.7, waste_kg=Decimal("100"),
                availability_status="available",
            )
            for number in range(POINTS - existing)
        )

        routes = [_saved_route(1), _saved_route(2)]
        for number in range(RUNS // 2):
            scenario = scenarios[number % len(scenarios)]
            for algorithm, distance in (("greedy", 20000.0), ("or_tools", 18000.0)):
                db.add(OptimizationRun(
                    scenario_id=scenario.id, algorithm=algorithm, status="feasible",
                    total_distance_m=distance, batch_id=f"perf{number:028d}", message="",
                    routes=routes, input_hash="perf", provenance={},
                ))
        db.commit()
    engine.dispose()
    return {"scenarios": SCENARIOS, "points": POINTS, "runs": RUNS}


def _timed(client: httpx.Client, method: str, path: str) -> tuple[float, int]:
    started = time.perf_counter()
    response = client.request(method, path)
    return (time.perf_counter() - started) * 1000, response.status_code


def measure(
    base_url: str, email: str, password: str, clients: int = 5, requests_each: int = 20
) -> dict:
    token = httpx.post(
        f"{base_url}/api/v1/auth/login", json={"email": email, "password": password}, timeout=30
    ).raise_for_status().json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(120)

    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        rows = client.get("/api/v1/evaluation/report").raise_for_status().json()["rows"]
    case_ids = [row["scenario_id"] for row in rows if row["scenario_id"]][:3]

    calls = {name: ("GET", path) for name, path in READS.items()}
    calls["Validation"] = ("POST", f"/api/v1/scenarios/{case_ids[0]}/validate")

    def one_client(call: tuple[str, str]) -> list[tuple[float, int]]:
        with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
            return [_timed(client, *call) for _ in range(requests_each)]

    results: dict[str, dict] = {}
    for name, call in calls.items():
        with ThreadPoolExecutor(clients) as pool:
            samples = [s for batch in pool.map(one_client, [call] * clients) for s in batch]
        times = [elapsed for elapsed, _ in samples]
        results[name] = {
            "requests": len(samples),
            "failures": sum(status >= 400 for _, status in samples),
            "p50_ms": round(statistics.median(times), 1),
            "p95_ms": round(percentile(times, 95), 1),
        }

    def optimize(scenario_id: int) -> tuple[float, int]:
        with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
            return _timed(client, "POST", f"/api/v1/scenarios/{scenario_id}/optimize")

    with ThreadPoolExecutor(3) as pool:
        runs = list(pool.map(optimize, case_ids))
    results["Three optimizations"] = {
        "statuses": sorted(status for _, status in runs),
        "times_ms": [round(elapsed) for elapsed, _ in runs],
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seeding = commands.add_parser("seed")
    seeding.add_argument("--db", required=True)
    measuring = commands.add_parser("measure")
    measuring.add_argument("--url", required=True)
    measuring.add_argument("--password", required=True)
    options = parser.parse_args()

    if options.command == "seed":
        password = secrets.token_urlsafe(16)
        url = options.db if options.db.startswith(POSTGRES_PREFIX) else (
            f"{SQLITE_PREFIX}{Path(options.db).resolve().as_posix()}"
        )
        print(seed(url, password))
        print(f"Sign in as {EMAIL} with {password}")
        return

    for name, result in measure(options.url, EMAIL, options.password).items():
        print(name, result)


if __name__ == "__main__":
    main()
