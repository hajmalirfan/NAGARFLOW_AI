"""Behaviour SQLite hides. The marked tests run only against PostgreSQL."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import migrations
from app.models import StoragePoint, User
from conftest import require_test_database
from test_roles import linked_user

UPGRADES = [name for name in dir(migrations) if name.startswith("upgrade_legacy_")]


def make_planner(db: Session) -> User:
    planner = User(name="Planner", email="p@example.com", hashed_password=hash_password("x" * 12))
    db.add(planner)
    db.commit()
    return planner


def test_a_test_database_name_must_end_in_test() -> None:
    with pytest.raises(pytest.UsageError):
        require_test_database("postgresql+psycopg://u:p@127.0.0.1:55432/nagarflow")


def test_a_test_database_name_ending_in_test_is_accepted() -> None:
    require_test_database("postgresql+psycopg://u:p@127.0.0.1:55432/nagarflow_test")


@pytest.mark.postgres_only
def test_removing_a_planner_removes_linked_accounts(db_session: Session) -> None:
    planner = make_planner(db_session)
    member = linked_user(db_session, planner, "reviewer", "r@example.com")
    member_id = member.id

    db_session.delete(planner)
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(User, member_id) is None


@pytest.mark.postgres_only
def test_every_upgrade_runs_twice_on_existing_tables(db_session: Session) -> None:
    engine = db_session.get_bind()
    assert len(UPGRADES) == 8

    for _ in range(2):
        for name in UPGRADES:
            getattr(migrations, name)(engine)


@pytest.mark.postgres_only
def test_decimals_round_trip_exactly(db_session: Session) -> None:
    planner = make_planner(db_session)
    db_session.add(StoragePoint(
        user_id=planner.id, name="Point", point_code="PG-1", latitude=10.8, longitude=78.7,
        waste_kg=Decimal("1234.56"), availability_status="available",
    ))
    db_session.commit()
    db_session.expire_all()

    assert db_session.scalar(select(StoragePoint.waste_kg)) == Decimal("1234.56")


@pytest.mark.postgres_only
def test_availability_times_round_trip(db_session: Session) -> None:
    planner = make_planner(db_session)
    moment = datetime(2026, 11, 3, 6, 30)
    db_session.add(StoragePoint(
        user_id=planner.id, name="Point", point_code="PG-2", latitude=10.8, longitude=78.7,
        waste_kg=Decimal("10"), availability_status="available", available_from=moment,
    ))
    db_session.commit()
    db_session.expire_all()

    assert db_session.scalar(select(StoragePoint.available_from)) == moment
