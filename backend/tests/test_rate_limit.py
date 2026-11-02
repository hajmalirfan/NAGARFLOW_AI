"""Repeated login and password reset requests are limited, and reveal nothing."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.rate_limit import RateLimiter, login_limiter
from app.core.security import hash_reset_token
from app.models import User
from app.models.password_reset_token import PasswordResetToken

LOGIN = "/api/v1/auth/login"
FORGOT = "/api/v1/auth/forgot-password"
BUSY = "Too many attempts. Try again later."


def fail_login(client: TestClient, email: str, times: int = 1) -> int:
    status = 0
    for _ in range(times):
        status = client.post(LOGIN, json={"email": email, "password": "wrong-password"}).status_code
    return status


def test_five_failed_logins_then_429(client: TestClient, registered_user: dict[str, str]) -> None:
    assert fail_login(client, registered_user["email"], 5) == 401

    response = client.post(LOGIN, json={"email": registered_user["email"], "password": "wrong"})

    assert response.status_code == 429
    assert response.json()["detail"] == BUSY


def test_the_correct_password_is_also_refused_once_limited(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    fail_login(client, registered_user["email"], 5)

    response = client.post(
        LOGIN, json={"email": registered_user["email"], "password": registered_user["password"]}
    )

    assert response.status_code == 429
    assert "access_token" not in response.text


def test_the_limit_is_per_email_ignoring_case(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    fail_login(client, registered_user["email"].upper(), 5)

    assert fail_login(client, registered_user["email"]) == 429


def test_the_limit_is_per_client_address(client: TestClient) -> None:
    for number in range(5):
        assert fail_login(client, f"person{number}@example.com") == 401

    assert fail_login(client, "someone-new@example.com") == 429


def test_a_successful_login_clears_the_emails_count(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    fail_login(client, registered_user["email"], 4)
    client.post(
        LOGIN, json={"email": registered_user["email"], "password": registered_user["password"]}
    )

    assert not login_limiter.count(f"email:{registered_user['email']}")


def test_a_successful_login_keeps_the_address_count(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    fail_login(client, registered_user["email"], 4)
    client.post(
        LOGIN, json={"email": registered_user["email"], "password": registered_user["password"]}
    )

    assert login_limiter.count("ip:testclient") == 4


def test_the_window_expires() -> None:
    now = [0.0]
    limiter = RateLimiter(5, 900, clock=lambda: now[0])
    for _ in range(5):
        limiter.record("a")
    assert limiter.is_blocked("a")

    now[0] = 900.1

    assert not limiter.is_blocked("a")


def test_unknown_and_known_email_are_limited_alike(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    known = [
        client.post(LOGIN, json={"email": registered_user["email"], "password": "wrong"})
        for _ in range(6)
    ]
    login_limiter.reset()
    unknown = [
        client.post(LOGIN, json={"email": "nobody@example.com", "password": "wrong"})
        for _ in range(6)
    ]

    assert [(r.status_code, r.json()) for r in known] == [(r.status_code, r.json()) for r in unknown]


@pytest.mark.parametrize("email", ["asha@example.com", "nobody@example.com"])
def test_forgot_password_limits_after_five(
    client: TestClient, registered_user: dict[str, str], email: str
) -> None:
    for _ in range(5):
        assert client.post(FORGOT, json={"email": email}).status_code == 202

    response = client.post(FORGOT, json={"email": email})

    assert response.status_code == 429
    assert response.json()["detail"] == BUSY


def test_expired_keys_are_removed() -> None:
    now = [0.0]
    limiter = RateLimiter(5, 10, clock=lambda: now[0], sweep_at=3)
    for key in ("a", "b", "c"):
        limiter.record(key)

    now[0] = 11.0
    limiter.record("d")

    assert limiter.size() == 1


def test_a_password_reset_lifts_the_login_limit(
    client: TestClient, registered_user: dict[str, str], db_session: Session
) -> None:
    fail_login(client, registered_user["email"], 5)
    user = db_session.scalar(select(User).where(User.email == registered_user["email"]))
    db_session.add(PasswordResetToken(
        user_id=user.id, token_hash=hash_reset_token("reset-token"), created_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=15),
    ))
    db_session.commit()

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "reset-token", "password": "a-new-password-123"},
    )

    assert reset.status_code == 200
    login = client.post(
        LOGIN, json={"email": registered_user["email"], "password": "a-new-password-123"}
    )
    assert login.status_code == 200


def test_a_failed_password_reset_leaves_the_limit(
    client: TestClient, registered_user: dict[str, str]
) -> None:
    fail_login(client, registered_user["email"], 5)

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "password": "a-new-password-123"},
    )

    assert reset.status_code == 400
    assert fail_login(client, registered_user["email"]) == 429
