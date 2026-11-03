"""The performance script's seed and arithmetic. Its results are in the report."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, make_url, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from perf_check import percentile, seed  # noqa: E402

from app.core.security import verify_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models import OptimizationRun, Scenario, StoragePoint, User  # noqa: E402
from conftest import postgres_url  # noqa: E402


def test_percentile_of_a_known_list() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([4, 3, 2, 1], 95) == pytest.approx(3.85)


def test_percentile_of_one_value() -> None:
    assert percentile([7.0], 95) == 7.0


def test_seed_creates_the_stated_size(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'perf.db').as_posix()}"

    counts = seed(url, "a-long-password-1")

    engine = create_engine(url)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Scenario)) == 50
        assert db.scalar(select(func.count()).select_from(StoragePoint)) == 500
        assert db.scalar(select(func.count()).select_from(OptimizationRun)) == 2000
        user = db.scalar(select(User))
        assert user.role == "planner"
        assert verify_password("a-long-password-1", user.hashed_password)
        assert db.scalar(
            select(func.count()).select_from(Scenario).where(Scenario.evaluation_code.is_(None))
        ) == 40
    engine.dispose()
    assert counts == {"scenarios": 50, "points": 500, "runs": 2000}


def test_seed_refuses_an_existing_file(tmp_path: Path) -> None:
    existing = tmp_path / "perf.db"
    existing.write_bytes(b"keep me")

    with pytest.raises(ValueError):
        seed(f"sqlite:///{existing.as_posix()}", "a-long-password-1")

    assert existing.read_bytes() == b"keep me"


def test_seed_still_refuses_other_urls() -> None:
    with pytest.raises(ValueError):
        seed("mysql://user:pass@127.0.0.1/nagarflow", "a-long-password-1")


@pytest.fixture
def empty_schema_url() -> Iterator[str]:
    """The test database seen through a new, empty schema, dropped afterwards."""
    url = postgres_url()
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA perf_seed"))
    try:
        yield str(make_url(url).update_query_dict({"options": "-csearch_path=perf_seed"})
                  .render_as_string(hide_password=False))
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA perf_seed CASCADE"))
        engine.dispose()


@pytest.mark.postgres_only
def test_seed_refuses_a_postgres_database_with_tables(empty_schema_url: str) -> None:
    engine = create_engine(empty_schema_url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    with pytest.raises(ValueError):
        seed(empty_schema_url, "a-long-password-1")


@pytest.mark.postgres_only
def test_seed_fills_an_empty_postgres_database(empty_schema_url: str) -> None:
    counts = seed(empty_schema_url, "a-long-password-1")

    engine = create_engine(empty_schema_url)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Scenario)) == 50
        assert db.scalar(select(func.count()).select_from(StoragePoint)) == 500
        assert db.scalar(select(func.count()).select_from(OptimizationRun)) == 2000
    engine.dispose()
    assert counts == {"scenarios": 50, "points": 500, "runs": 2000}
