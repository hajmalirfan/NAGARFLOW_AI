"""Check a deployed NagarFlow site from outside, without changing anything.

    python scripts/smoke_check.py --api https://api.example.org --frontend https://example.org

It only sends GET requests and signs in to nothing. Each check reports on its
own, so one failure never hides the rest. It exits 1 if any check fails.
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass

import httpx

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}
HSTS = "strict-transport-security"
CSP = "content-security-policy"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _missing_headers(response: httpx.Response, expected: dict[str, str]) -> list[str]:
    return [name for name, value in expected.items() if response.headers.get(name) != value]


def _health(api: httpx.Client) -> tuple[bool, str]:
    response = api.get("/health")
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    if response.json() != {"status": "ok"}:
        return False, f"unexpected body {response.text[:80]!r}"
    return True, "200 ok"


def _docs_off(api: httpx.Client) -> tuple[bool, str]:
    found = [path for path in ("/docs", "/openapi.json") if api.get(path).status_code != 404]
    return (False, f"still served: {', '.join(found)}") if found else (True, "404 for both")


def _security_headers(api: httpx.Client) -> tuple[bool, str]:
    response = api.get("/health")
    missing = _missing_headers(response, SECURITY_HEADERS)
    if HSTS not in response.headers:
        missing.append(HSTS)
    return (False, f"missing or wrong: {', '.join(missing)}") if missing else (True, "all present")


def _sign_in_required(api: httpx.Client) -> tuple[bool, str]:
    status = api.get("/api/v1/auth/me").status_code
    return (status == 401, f"status {status} with no token")


def _frontend(frontend: httpx.Client) -> tuple[bool, str]:
    response = frontend.get("/")
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    if not response.headers.get("content-type", "").startswith("text/html"):
        return False, f"content type {response.headers.get('content-type')!r}"
    if '<div id="root">' not in response.text:
        return False, "the page has no root element"
    missing = _missing_headers(response, SECURITY_HEADERS)
    if CSP not in response.headers:
        missing.append(CSP)
    return (False, f"missing or wrong: {', '.join(missing)}") if missing else (True, "200 html")


def _run(name: str, check: Callable[[], tuple[bool, str]]) -> Check:
    try:
        ok, detail = check()
    except httpx.HTTPError as error:
        ok, detail = False, f"request failed: {error}"
    except ValueError as error:
        # A body that is not JSON, such as a proxy's HTML error page.
        ok, detail = False, f"unreadable response: {error}"
    return Check(name, ok, detail)


def run_checks(api: httpx.Client, frontend: httpx.Client | None) -> list[Check]:
    checks = [
        _run("Health", lambda: _health(api)),
        _run("API docs are off", lambda: _docs_off(api)),
        _run("Security headers", lambda: _security_headers(api)),
        _run("Sign-in required", lambda: _sign_in_required(api)),
    ]
    if frontend is not None:
        checks.append(_run("Frontend", lambda: _frontend(frontend)))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--frontend")
    options = parser.parse_args()

    with httpx.Client(base_url=options.api, timeout=10) as api:
        frontend = httpx.Client(base_url=options.frontend, timeout=10) if options.frontend else None
        try:
            checks = run_checks(api, frontend)
        finally:
            if frontend is not None:
                frontend.close()

    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'}  {check.name}: {check.detail}")
    sys.exit(0 if all(check.ok for check in checks) else 1)


if __name__ == "__main__":
    main()
