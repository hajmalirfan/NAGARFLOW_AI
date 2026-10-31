"""Authentication tests for the versioned API surface."""

from fastapi.testclient import TestClient


def test_health_check_reports_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_creates_account_and_returns_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Asha Rao", "email": "asha@example.com", "password": "original-password-123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "asha@example.com"
    assert "password" not in body["user"]
    assert "hashed_password" not in body["user"]


def test_register_rejects_duplicate_email(client: TestClient, registered_user: dict[str, str]) -> None:
    response = client.post("/api/v1/auth/register", json=registered_user)
    assert response.status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Asha Rao", "email": "short@example.com", "password": "tiny"},
    )
    assert response.status_code == 422


def test_login_succeeds_with_correct_password(client: TestClient, registered_user: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


def test_login_rejects_wrong_password(client: TestClient, registered_user: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": "not-the-right-password"},
    )
    assert response.status_code == 401


def test_me_returns_profile_for_valid_token(client: TestClient, registered_user: dict[str, str]) -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    ).json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.json()["email"] == registered_user["email"]


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_legacy_unversioned_auth_path_still_works(client: TestClient, registered_user: dict[str, str]) -> None:
    """The original /auth/* paths stay mounted so nothing already deployed breaks."""
    response = client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == 200, response.text
