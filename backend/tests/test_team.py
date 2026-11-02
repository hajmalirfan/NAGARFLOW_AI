"""Planners manage the accounts linked to their workspace."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.security import hash_reset_token
from app.models import User
from app.models.password_reset_token import PasswordResetToken
from test_permissions import ALL_ROLES
from test_roles import headers_for, linked_user

TEAM = "/api/v1/team"
MEMBER = {
    "name": "Ravi",
    "email": "ravi@example.com",
    "role": "reviewer",
    "password": "temporary-password-1",
}


@pytest.fixture
def planner(client: TestClient, registered_user: dict[str, str], db_session: Session) -> User:
    return db_session.scalar(select(User).where(User.email == registered_user["email"]))


@pytest.fixture
def headers(planner: User) -> dict[str, str]:
    return headers_for(planner)


@pytest.fixture
def other_planner(client: TestClient, db_session: Session) -> User:
    client.post(
        "/api/v1/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "another-password-123"},
    )
    return db_session.scalar(select(User).where(User.email == "other@example.com"))


def test_planner_creates_a_linked_account(
    client: TestClient, headers: dict[str, str], planner: User, db_session: Session
) -> None:
    response = client.post(TEAM, headers=headers, json=MEMBER)

    assert response.status_code == 201
    assert response.json()["role"] == "reviewer"
    assert "password" not in response.text
    login = client.post(
        "/api/v1/auth/login", json={"email": MEMBER["email"], "password": MEMBER["password"]}
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "reviewer"
    member = db_session.scalar(select(User).where(User.email == MEMBER["email"]))
    assert member.planner_id == planner.id


def test_team_cannot_create_a_planner(client: TestClient, headers: dict[str, str]) -> None:
    assert client.post(TEAM, headers=headers, json={**MEMBER, "role": "planner"}).status_code == 422


def test_team_lists_only_your_own_accounts(
    client: TestClient, headers: dict[str, str], planner: User, other_planner: User,
    db_session: Session,
) -> None:
    linked_user(db_session, planner, "driver", "mine@example.com")
    linked_user(db_session, other_planner, "driver", "theirs@example.com")

    body = client.get(TEAM, headers=headers).json()

    assert [member["email"] for member in body] == ["mine@example.com"]


def test_duplicate_email_is_refused(client: TestClient, headers: dict[str, str]) -> None:
    client.post(TEAM, headers=headers, json=MEMBER)

    response = client.post(TEAM, headers=headers, json={**MEMBER, "email": "RAVI@Example.com"})

    assert response.status_code == 409


def test_blank_name_is_refused(client: TestClient, headers: dict[str, str]) -> None:
    assert client.post(TEAM, headers=headers, json={**MEMBER, "name": "   "}).status_code == 422


def test_short_password_is_refused(client: TestClient, headers: dict[str, str]) -> None:
    assert client.post(TEAM, headers=headers, json={**MEMBER, "password": "short"}).status_code == 422


def test_changing_a_role_applies_at_once(
    client: TestClient, headers: dict[str, str], planner: User, db_session: Session
) -> None:
    member = linked_user(db_session, planner, "reviewer", "r@example.com")
    member_headers = headers_for(member)
    assert client.get("/api/v1/depots", headers=member_headers).status_code == 200

    response = client.put(f"{TEAM}/{member.id}", headers=headers, json={"role": "driver"})

    assert response.status_code == 200
    assert response.json()["role"] == "driver"
    assert client.get("/api/v1/depots", headers=member_headers).status_code == 403


def test_a_role_cannot_be_changed_to_planner(
    client: TestClient, headers: dict[str, str], planner: User, db_session: Session
) -> None:
    member = linked_user(db_session, planner, "reviewer", "r@example.com")

    response = client.put(f"{TEAM}/{member.id}", headers=headers, json={"role": "planner"})

    assert response.status_code == 422


def test_another_planners_account_cannot_be_changed(
    client: TestClient, headers: dict[str, str], other_planner: User, db_session: Session
) -> None:
    member = linked_user(db_session, other_planner, "reviewer", "r@example.com")

    assert client.put(f"{TEAM}/{member.id}", headers=headers, json={"role": "driver"}).status_code == 404
    assert client.delete(f"{TEAM}/{member.id}", headers=headers).status_code == 404
    db_session.refresh(member)
    assert member.role == "reviewer"


def test_a_planner_cannot_change_their_own_role(
    client: TestClient, headers: dict[str, str], planner: User, db_session: Session
) -> None:
    response = client.put(f"{TEAM}/{planner.id}", headers=headers, json={"role": "reviewer"})

    assert response.status_code == 404
    db_session.refresh(planner)
    assert planner.role == "planner"


def test_removing_an_account_ends_its_session(
    client: TestClient, headers: dict[str, str], planner: User, db_session: Session
) -> None:
    member = linked_user(db_session, planner, "reviewer", "r@example.com")
    member_headers = headers_for(member)

    assert client.delete(f"{TEAM}/{member.id}", headers=headers).status_code == 204

    assert client.get("/api/v1/auth/me", headers=member_headers).status_code == 401


def test_removing_an_account_removes_its_reset_tokens(
    client: TestClient, headers: dict[str, str], planner: User, db_session: Session
) -> None:
    member = linked_user(db_session, planner, "reviewer", "r@example.com")
    db_session.add(PasswordResetToken(
        user_id=member.id, token_hash=hash_reset_token("abc"), created_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=15),
    ))
    db_session.commit()

    client.delete(f"{TEAM}/{member.id}", headers=headers)

    assert db_session.scalar(select(func.count()).select_from(PasswordResetToken)) == 0


@pytest.mark.parametrize("role", ALL_ROLES[1:])
def test_linked_accounts_cannot_manage_the_team(
    client: TestClient, planner: User, db_session: Session, role: str
) -> None:
    member = linked_user(db_session, planner, role, "r@example.com")
    member_headers = headers_for(member)

    assert client.get(TEAM, headers=member_headers).status_code == 403
    assert client.post(TEAM, headers=member_headers, json=MEMBER).status_code == 403
    assert client.put(f"{TEAM}/{member.id}", headers=member_headers, json={"role": "reviewer"}).status_code == 403
    assert client.delete(f"{TEAM}/{member.id}", headers=member_headers).status_code == 403
