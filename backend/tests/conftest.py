"""Shared test fixtures.

Tests run against an in-memory SQLite database so they never touch the
development PostgreSQL data, and so they can run without Docker or a
database server. The FastAPI ``get_db`` dependency is replaced with a
session bound to that SQLite database.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app

# Importing every model registers its table on ``Base.metadata`` so that
# ``create_all`` below builds the full schema.
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.user import User  # noqa: F401


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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
