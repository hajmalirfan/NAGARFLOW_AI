"""Account roles and the workspaces linked accounts share with their planner."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.core.permissions import workspace_owner_id
from app.core.security import create_access_token, hash_password
from app.db.migrations import upgrade_legacy_user_schema
from app.evaluation.catalog_loader import load_catalog
from app.models import Depot, User
from app.services.evaluation_report import build_report
from test_dashboard import seed_scenario

CREDENTIALS = {"name": "Asha Rao", "email": "asha@example.com", "password": "original-password-123"}


def linked_user(db: Session, planner: User, role: str, email: str) -> User:
    user = User(
        name=role.title(), email=email, hashed_password=hash_password("linked-password-123"),
        role=role, planner_id=planner.id,
    )
    db.add(user)
    db.commit()
    return user


def headers_for(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def add_depot(db: Session, owner: User, code: str) -> Depot:
    depot = Depot(
        user_id=owner.id, name=f"Depot {code}", code=code, address="Trichy",
        latitude=10.8, longitude=78.7,
    )
    db.add(depot)
    db.commit()
    return depot


@pytest.fixture
def planner(client: TestClient, registered_user: dict[str, str], db_session: Session) -> User:
    return db_session.scalar(select(User).where(User.email == registered_user["email"]))


@pytest.fixture
def other_planner(client: TestClient, db_session: Session) -> User:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "another-password-123"},
    )
    return db_session.scalar(select(User).where(User.email == "other@example.com"))


def test_a_new_account_is_a_planner(client: TestClient) -> None:
    body = client.post("/api/v1/auth/register", json=CREDENTIALS).json()

    assert body["user"]["role"] == "planner"


def test_sign_up_cannot_choose_a_role(client: TestClient) -> None:
    body = client.post(
        "/api/v1/auth/register", json={**CREDENTIALS, "role": "reviewer", "planner_id": 1}
    ).json()

    assert body["user"]["role"] == "planner"


def test_workspace_owner_of_a_planner_is_themselves(planner: User) -> None:
    assert workspace_owner_id(planner) == planner.id


def test_workspace_owner_of_a_linked_account_is_the_planner(
    db_session: Session, planner: User
) -> None:
    reviewer = linked_user(db_session, planner, "reviewer", "r@example.com")

    assert workspace_owner_id(reviewer) == planner.id


def test_a_linked_account_sees_the_planners_dashboard(
    client: TestClient, db_session: Session, planner: User
) -> None:
    seed_scenario(db_session, planner.email)
    planners_view = client.get("/api/v1/dashboard/summary", headers=headers_for(planner)).json()
    manager = linked_user(db_session, planner, "management", "m@example.com")

    response = client.get("/api/v1/dashboard/summary", headers=headers_for(manager))

    assert response.status_code == 200
    assert planners_view["total_scenarios"] == 1
    assert response.json() == planners_view


def test_a_linked_account_sees_the_planners_report(
    db_session: Session, planner: User, other_planner: User
) -> None:
    load_catalog(db_session, planner)
    reviewer = linked_user(db_session, planner, "reviewer", "r@example.com")

    assert build_report(db_session, reviewer)["rows"][0]["state"] == "not_run"
    assert build_report(db_session, other_planner)["rows"][0]["state"] == "not_loaded"


def test_a_linked_account_lists_the_planners_records_only(
    client: TestClient, db_session: Session, planner: User, other_planner: User
) -> None:
    add_depot(db_session, planner, "OURS")
    add_depot(db_session, other_planner, "THEIRS")
    reviewer = linked_user(db_session, planner, "reviewer", "r@example.com")

    response = client.get("/api/v1/depots", headers=headers_for(reviewer))

    assert [depot["code"] for depot in response.json()] == ["OURS"]


def test_upgrade_adds_role_and_planner_to_old_users(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100), "
            "email VARCHAR(254), hashed_password VARCHAR(255))"
        ))
        connection.execute(text("INSERT INTO users VALUES (1, 'Old', 'old@example.com', 'x')"))

    upgrade_legacy_user_schema(engine)
    upgrade_legacy_user_schema(engine)

    with engine.connect() as connection:
        row = connection.execute(text("SELECT role, planner_id FROM users")).one()
    assert tuple(row) == ("planner", None)
    assert "ix_users_planner_id" in {index["name"] for index in inspect(engine).get_indexes("users")}
    engine.dispose()


def test_planner_foreign_key_cascades() -> None:
    key = next(iter(User.__table__.c.planner_id.foreign_keys))

    assert key.ondelete == "CASCADE"
