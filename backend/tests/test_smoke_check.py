"""The deployment smoke check reads a running site and reports each check."""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from smoke_check import run_checks  # noqa: E402

from app.core.config import api_doc_urls, settings  # noqa: E402
from app.main import app  # noqa: E402

DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
FRONTEND_HEADERS = {
    "content-type": "text/html",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'self'",
}


def production_app() -> FastAPI:
    """The real routes and middleware, built the way production builds them."""
    built = FastAPI(**api_doc_urls("production"))
    built.router.routes.extend(r for r in app.routes if getattr(r, "path", "") not in DOC_PATHS)
    built.user_middleware = list(app.user_middleware)
    built.dependency_overrides = app.dependency_overrides
    return built


def frontend(body: str = '<html><div id="root"></div></html>', **headers: str) -> httpx.Client:
    sent = {**FRONTEND_HEADERS, **headers}
    sent = {name: value for name, value in sent.items() if value}
    return httpx.Client(
        base_url="http://frontend",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body, headers=sent)),
    )


def failed(checks) -> list[str]:
    return [check.name for check in checks if not check.ok]


def test_a_production_api_passes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")

    checks = run_checks(TestClient(production_app()), frontend())

    assert failed(checks) == []
    assert len(checks) == 5


def test_development_fails_the_docs_check(client: TestClient) -> None:
    checks = run_checks(client, None)

    assert failed(checks) == ["API docs are off", "Security headers"]


def test_a_missing_header_fails_that_check(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    checks = run_checks(TestClient(production_app()), frontend(**{"content-security-policy": ""}))

    assert failed(checks) == ["Frontend"]
    assert "content-security-policy" in next(c for c in checks if not c.ok).detail


def test_an_unreachable_server_is_a_failure_not_a_crash() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    down = httpx.Client(base_url="http://api", transport=httpx.MockTransport(refuse))

    checks = run_checks(down, frontend())

    assert set(failed(checks)) == {
        "Health", "API docs are off", "Security headers", "Sign-in required",
    }
    assert all(check.detail for check in checks if not check.ok)


def test_an_html_error_page_is_a_failure() -> None:
    bad_gateway = httpx.Client(
        base_url="http://api",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(502, text="<html>Bad gateway</html>",
                                           headers={"content-type": "text/html"})
        ),
    )

    checks = run_checks(bad_gateway, None)

    assert "Health" in failed(checks)


def test_the_frontend_needs_the_root_element_and_headers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    api = TestClient(production_app())

    assert failed(run_checks(api, frontend(body="<html>Welcome to nginx</html>"))) == ["Frontend"]
    assert failed(run_checks(api, frontend(**{"x-frame-options": ""}))) == ["Frontend"]
