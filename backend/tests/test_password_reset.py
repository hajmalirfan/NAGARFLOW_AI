"""Password reset tests.

These cover the Step 3 testing checklist and every stated security
requirement: generic responses, 15 minute expiry, hash-only storage,
single use, and invalidation of outstanding tokens after a reset.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken

FORGOT = "/api/v1/auth/forgot-password"
VERIFY = "/api/v1/auth/verify-reset-token"
RESET = "/api/v1/auth/reset-password"

NEW_PASSWORD = "a-brand-new-password-456"


def token_from_outbox(outbox: list[dict[str, str]]) -> str:
    """Pull the reset token out of the most recent email's link."""
    assert outbox, "no email was sent"
    match = re.search(r"token=([A-Za-z0-9_\-]+)", outbox[-1]["body"])
    assert match, "no reset link was found in the email body"
    return match.group(1)


@pytest.fixture
def reset_token(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> str:
    response = client.post(FORGOT, json={"email": registered_user["email"]})
    assert response.status_code == 202, response.text
    return token_from_outbox(outbox)


# --- Requesting a reset -------------------------------------------------


def test_forgot_password_emails_a_reset_link_to_a_registered_user(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> None:
    response = client.post(FORGOT, json={"email": registered_user["email"]})

    assert response.status_code == 202, response.text
    assert len(outbox) == 1
    assert outbox[0]["to"] == registered_user["email"]
    assert "token=" in outbox[0]["body"]


def test_forgot_password_never_emails_an_unregistered_address(
    client: TestClient, outbox: list[dict[str, str]]
) -> None:
    response = client.post(FORGOT, json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert outbox == []


def test_forgot_password_response_is_identical_for_registered_and_unregistered_emails(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> None:
    """Security requirement: never reveal whether an email is registered."""
    registered = client.post(FORGOT, json={"email": registered_user["email"]})
    unregistered = client.post(FORGOT, json={"email": "nobody@example.com"})

    assert registered.status_code == unregistered.status_code
    assert registered.json() == unregistered.json()


def test_forgot_password_is_case_insensitive_about_the_email(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> None:
    response = client.post(FORGOT, json={"email": registered_user["email"].upper()})

    assert response.status_code == 202
    assert len(outbox) == 1


def test_forgot_password_rejects_a_malformed_email(client: TestClient) -> None:
    response = client.post(FORGOT, json={"email": "not-an-email"})
    assert response.status_code == 422


def test_reset_email_does_not_contain_the_password(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> None:
    """Security requirement: never send passwords through email."""
    client.post(FORGOT, json={"email": registered_user["email"]})

    assert registered_user["password"] not in outbox[0]["body"]


# --- Token storage -----------------------------------------------------


def test_raw_token_is_never_stored_only_its_hash(
    reset_token: str, db_session: Session
) -> None:
    """Security requirement: store only a hash of the reset token."""
    stored = db_session.scalars(select(PasswordResetToken)).all()

    assert len(stored) == 1
    assert stored[0].token_hash != reset_token
    assert reset_token not in stored[0].token_hash


def test_token_expires_fifteen_minutes_after_it_is_issued(
    reset_token: str, db_session: Session
) -> None:
    stored = db_session.scalars(select(PasswordResetToken)).one()
    lifetime = stored.expires_at - stored.created_at

    assert lifetime == timedelta(minutes=15)


def test_each_request_issues_a_different_token(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> None:
    client.post(FORGOT, json={"email": registered_user["email"]})
    first = token_from_outbox(outbox)
    client.post(FORGOT, json={"email": registered_user["email"]})
    second = token_from_outbox(outbox)

    assert first != second


# --- Verifying a token -------------------------------------------------


def test_verify_accepts_a_fresh_token(client: TestClient, reset_token: str) -> None:
    response = client.post(VERIFY, json={"token": reset_token})

    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True


def test_verify_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.post(VERIFY, json={"token": "this-token-was-never-issued"})
    assert response.status_code == 400


def test_verify_rejects_an_expired_token(
    client: TestClient, reset_token: str, db_session: Session
) -> None:
    stored = db_session.scalars(select(PasswordResetToken)).one()
    stored.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    db_session.commit()

    response = client.post(VERIFY, json={"token": reset_token})

    assert response.status_code == 400


def test_verify_rejects_an_already_used_token(client: TestClient, reset_token: str) -> None:
    client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})

    response = client.post(VERIFY, json={"token": reset_token})

    assert response.status_code == 400


# --- Resetting the password -------------------------------------------


def test_reset_password_succeeds_with_a_valid_token(
    client: TestClient, reset_token: str
) -> None:
    response = client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})
    assert response.status_code == 200, response.text


def test_login_works_with_the_new_password(
    client: TestClient, registered_user: dict[str, str], reset_token: str
) -> None:
    client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})

    response = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": NEW_PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


def test_old_password_stops_working_after_a_reset(
    client: TestClient, registered_user: dict[str, str], reset_token: str
) -> None:
    client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})

    response = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )

    assert response.status_code == 401


def test_a_token_cannot_be_used_twice(client: TestClient, reset_token: str) -> None:
    """Security requirement: allow each token to be used only once."""
    first = client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})
    assert first.status_code == 200, first.text

    second = client.post(
        RESET, json={"token": reset_token, "password": "yet-another-password-789"}
    )

    assert second.status_code == 400


def test_reset_rejects_an_expired_token(
    client: TestClient, reset_token: str, db_session: Session
) -> None:
    stored = db_session.scalars(select(PasswordResetToken)).one()
    stored.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    db_session.commit()

    response = client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})

    assert response.status_code == 400


def test_reset_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.post(
        RESET, json={"token": "this-token-was-never-issued", "password": NEW_PASSWORD}
    )
    assert response.status_code == 400


def test_reset_rejects_a_short_password(client: TestClient, reset_token: str) -> None:
    response = client.post(RESET, json={"token": reset_token, "password": "tiny"})
    assert response.status_code == 422


def test_successful_reset_invalidates_every_other_outstanding_token(
    client: TestClient, registered_user: dict[str, str], outbox: list[dict[str, str]]
) -> None:
    """Security requirement: invalidate existing reset tokens after a reset."""
    client.post(FORGOT, json={"email": registered_user["email"]})
    first_token = token_from_outbox(outbox)
    client.post(FORGOT, json={"email": registered_user["email"]})
    second_token = token_from_outbox(outbox)

    reset = client.post(RESET, json={"token": second_token, "password": NEW_PASSWORD})
    assert reset.status_code == 200, reset.text

    response = client.post(
        RESET, json={"token": first_token, "password": "yet-another-password-789"}
    )

    assert response.status_code == 400


def test_reset_does_not_affect_another_users_password(
    client: TestClient, registered_user: dict[str, str], reset_token: str
) -> None:
    other = {"name": "Bala N", "email": "bala@example.com", "password": "bala-password-123"}
    assert client.post("/api/v1/auth/register", json=other).status_code == 201

    client.post(RESET, json={"token": reset_token, "password": NEW_PASSWORD})

    response = client.post(
        "/api/v1/auth/login", json={"email": other["email"], "password": other["password"]}
    )
    assert response.status_code == 200, response.text
