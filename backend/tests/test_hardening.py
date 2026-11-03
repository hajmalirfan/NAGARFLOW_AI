"""Unsafe production settings stop the server, and every response carries headers."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import dashboard
from app.core.config import (
    DEFAULT_JWT_SECRET,
    EXAMPLE_JWT_SECRET,
    Settings,
    check_production_settings,
    production_warnings,
    settings,
)
from app.main import app
from test_validation import auth_headers  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]
STRONG_SECRET = "x" * 32


def production_values(**overrides) -> Settings:
    """A production configuration that passes every check on its own."""
    return Settings(**{
        "environment": "production",
        "jwt_secret_key": "a-private-secret-" + "x" * 30,
        "cors_origins": ["https://nagarflow.example"],
        "frontend_base_url": "https://nagarflow.example",
        "smtp_host": "smtp.nagarflow.example",
        "database_url": "postgresql+psycopg://nagarflow:a-private-password@db:5432/nagarflow",
        "road_network_path": str(Path(__file__)),
        **overrides,
    })


def values(environment: str, secret: str) -> Settings:
    return production_values(environment=environment, jwt_secret_key=secret)


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


def test_a_valid_production_set_starts() -> None:
    values = production_values()

    check_production_settings(values)
    assert production_warnings(values) == []


@pytest.mark.parametrize("overrides", [
    {"cors_origins": ["http://localhost:5173"]},
    {"cors_origins": ["https://nagarflow.example", "http://127.0.0.1:5173"]},
    {"frontend_base_url": "http://localhost:5173"},
    {"smtp_host": ""},
    {"database_url": "postgresql+psycopg://nagarflow:change-this-local-password@db/nagarflow"},
    {"road_network_path": ""},
    {"database_url": "postgresql+psycopg://nagarflow:replace-with-a-private-database-password@db:5432/nagarflow"},
    {"jwt_secret_key": "replace-with-a-generated-secret-of-enough-length"},
])
def test_each_unsafe_setting_alone_is_refused(overrides: dict) -> None:
    with pytest.raises(RuntimeError):
        check_production_settings(production_values(**overrides))


def test_every_problem_is_named_at_once() -> None:
    with pytest.raises(RuntimeError) as refusal:
        check_production_settings(production_values(smtp_host="", road_network_path=""))

    assert "SMTP_HOST" in str(refusal.value)
    assert "ROAD_NETWORK_PATH" in str(refusal.value)


def test_a_missing_roads_file_only_warns(tmp_path: Path) -> None:
    values = production_values(road_network_path=str(tmp_path / "absent.gpkg"))

    check_production_settings(values)
    assert any("ROAD_NETWORK_PATH" in warning for warning in production_warnings(values))


def test_development_ignores_all_of_these() -> None:
    values = production_values(
        environment="development", cors_origins=["http://localhost:5173"], smtp_host="",
        road_network_path="", jwt_secret_key=DEFAULT_JWT_SECRET,
    )

    check_production_settings(values)
    assert production_warnings(values) == []


def test_every_example_value_in_the_production_file_is_refused() -> None:
    """Copying .env.production.example unchanged must not start a server."""
    example = {}
    for line in (BACKEND.parent / ".env.production.example").read_text().splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            example[name] = value
    with pytest.raises(RuntimeError) as refusal:
        check_production_settings(production_values(
            database_url=example["DATABASE_URL"], jwt_secret_key=example["JWT_SECRET_KEY"],
        ))

    assert "DATABASE_URL" in str(refusal.value)
    assert "JWT_SECRET_KEY" in str(refusal.value)


def test_compose_takes_each_backend_setting_from_the_env_file() -> None:
    """A setting the env file offers must not be pinned in the compose file."""
    offered = {
        line.partition("=")[0]
        for line in (BACKEND.parent / ".env.production.example").read_text().splitlines()
        if line and not line.startswith("#")
    }
    compose = (BACKEND.parent / "docker-compose.prod.yml").read_text()
    pinned = [
        name for name in offered
        if f"      {name}: " in compose and f"      {name}: ${{{name}" not in compose
    ]

    assert pinned == []
