"""Unsafe production settings stop the server, and every response carries headers."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import dashboard
from app.core.config import DEFAULT_JWT_SECRET, EXAMPLE_JWT_SECRET, Settings, check_production_settings, settings
from app.main import app
from test_validation import auth_headers  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]
STRONG_SECRET = "x" * 32


def values(environment: str, secret: str) -> Settings:
    return Settings(environment=environment, jwt_secret_key=secret)


def assert_security_headers(headers) -> None:
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"


def test_production_refuses_the_default_secret() -> None:
    with pytest.raises(RuntimeError):
        check_production_settings(values("production", DEFAULT_JWT_SECRET))


def test_production_refuses_the_example_secret() -> None:
    assert len(EXAMPLE_JWT_SECRET) >= 32
    with pytest.raises(RuntimeError):
        check_production_settings(values("production", EXAMPLE_JWT_SECRET))


def test_production_refuses_a_31_character_secret() -> None:
    with pytest.raises(RuntimeError):
        check_production_settings(values("production", "x" * 31))


def test_production_accepts_a_32_character_secret() -> None:
    check_production_settings(values("production", STRONG_SECRET))


def test_any_other_environment_is_treated_as_production() -> None:
    with pytest.raises(RuntimeError):
        check_production_settings(values("staging", DEFAULT_JWT_SECRET))


def test_development_keeps_the_default_secret() -> None:
    check_production_settings(values("development", DEFAULT_JWT_SECRET))


def test_the_server_will_not_start_on_the_default_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret_key", DEFAULT_JWT_SECRET)

    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_security_headers_on_a_normal_response(client: TestClient) -> None:
    assert_security_headers(client.get("/health").headers)


def test_security_headers_on_a_404(client: TestClient) -> None:
    assert_security_headers(client.get("/no-such-page").headers)


def test_security_headers_on_an_unexpected_500(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(dashboard, "build_dashboard_summary", explode)

    response = client.get("/api/v1/dashboard/summary", headers=auth_headers)

    assert response.status_code == 500
    assert_security_headers(response.headers)


def test_hsts_only_outside_development(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "development")
    assert "strict-transport-security" not in client.get("/health").headers

    monkeypatch.setattr(settings, "environment", "production")
    assert (
        client.get("/health").headers["strict-transport-security"]
        == "max-age=31536000; includeSubDomains"
    )


def test_docs_are_off_outside_development() -> None:
    code = (
        "from app.main import app; "
        "assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True,
        env={**os.environ, "ENVIRONMENT": "production"},
    )

    assert result.returncode == 0, result.stderr


def test_docs_stay_on_in_development() -> None:
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"
