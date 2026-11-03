"""Shared test fixtures.

Tests run against an in-memory SQLite database so they never touch the
development PostgreSQL data, and so they can run without Docker or a
database server. Set TEST_DATABASE_URL to run them on PostgreSQL instead,
against a database whose name ends in _test, which each test empties. The FastAPI ``get_db`` dependency is replaced with a
session bound to that SQLite database.
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.rate_limit import forgot_password_limiter, login_limiter
from app.db.base import Base
from app.main import app

# Importing every model registers its table on ``Base.metadata`` so that
# ``create_all`` below builds the full schema.
import app.models as all_models  # noqa: F401
from app.services.road_network import reset_road_network


@pytest.fixture(autouse=True)
def no_real_road_network(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep tests off the real dataset, even if a local .env points at it."""
    monkeypatch.setattr(settings, "road_network_path", "")
    reset_road_network()
    yield
    reset_road_network()


@pytest.fixture(autouse=True)
def fresh_rate_limits() -> Generator[None, None, None]:
    login_limiter.reset()
    forgot_password_limiter.reset()
    yield


def postgres_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or None


def require_test_database(url: str) -> None:
    """Refuse any database that is not plainly a throwaway test one."""
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise pytest.UsageError(
            f"TEST_DATABASE_URL must name a database ending in _test, not {name!r}. "
            "Every table in it is emptied before each test."
        )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "postgres_only: needs TEST_DATABASE_URL")
    url = postgres_url()
    if url:
        require_test_database(url)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if postgres_url():
        return
    skip = pytest.mark.skip(reason="needs TEST_DATABASE_URL")
    for item in items:
        if "postgres_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    engine = create_engine(postgres_url())
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(request: pytest.FixtureRequest) -> Generator[Session, None, None]:
    if postgres_url():
        engine = request.getfixturevalue("postgres_engine")
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        try:
            yield session
        finally:
            session.close()
        return

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # No ``with`` block: that would run the application lifespan, which
    # connects to the real PostgreSQL database.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Capture outgoing email instead of sending it.

    SMTP is the one external side effect these tests cannot perform for
    real, so it is replaced at the boundary. Everything inside the
    application still runs as it does in production.
    """
    import app.services.email as email_service

    sent: list[dict[str, str]] = []

    def record(to: str, subject: str, body: str) -> None:
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(email_service, "send_email", record)
    return sent


@pytest.fixture
def registered_user(client: TestClient) -> dict[str, str]:
    credentials = {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "password": "original-password-123",
    }
    response = client.post("/api/v1/auth/register", json=credentials)
    assert response.status_code == 201, response.text
    return credentials
