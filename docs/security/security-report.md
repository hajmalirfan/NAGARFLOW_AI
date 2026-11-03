# Security Report

Date: November 2, 2026. Branch `feat/access-hardening`. This covers the application code and its dependencies, tested locally on SQLite. It is not an independent penetration test, and the deployed system has not been tested because it does not exist yet.

## What was tested

| Area | What the tests do | Result |
| --- | --- | --- |
| Roles | Every protected API route against all five roles, with a test that fails if a route is missing from the matrix | Pass |
| Permission coverage | Walks every route and fails if one has no declared permission, apart from health checks and the sign-in and password reset routes | Pass |
| Workspace separation | One planner calls every id-taking route with another planner's records. A test fails if an id route is left out | All 404 |
| Linked account writes | A valid reviewer token calls every id-taking write route on its planner's real records. Create routes are covered by the role matrix, with an empty body | All 403 |
| Live changes | A changed role applies on the next request. A removed account gets 401 | Pass |
| Tokens | Tampered, expired, wrong secret, `alg: none`, deleted account, missing subject, non-numeric subject | All 401 |
| Oversized input | 100,000 characters in each text field on the create forms, and in the login password | All 422, except fixed choice fields, which reject any other value |
| SQL-shaped text | In a name, a history filter and a password | Stored or compared as plain text |
| Rate limits | Limit reached, correct password while limited, case, address, window expiry, memory clean-up, known and unknown emails | Pass |
| Production settings | Default, placeholder and short secrets stop the server | Pass |
| Headers | Present on normal responses, 404s and unexpected 500s | Pass |
| API docs | Off outside development, checked in a separate process | Pass |

## Findings and fixes

| Finding | Fix |
| --- | --- |
| Any signed-in account could read and change everything in its own workspace, with no roles | Five roles enforced on every route |
| No limit on login or forgot-password attempts | 5 failed logins in 15 minutes, 5 forgot-password requests per hour, per email and per address |
| The server would start on the default JWT secret | Refused outside development |
| The placeholder secret in `.env.example` is 52 characters, so a length check alone would accept it | Refused by name |
| No security headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Strict-Transport-Security` outside development |
| API docs were always public | Off outside development |
| `pytest` 8.4.2 had a known advisory (PYSEC-2026-1845). It is a test tool and does not run in production | Requirement raised to 9.0.3 or later. The installed version is 9.2.0, and all 711 backend tests pass on it |

The new attack tests in `backend/tests/test_security.py` found no further defects. Access, tokens and input handling held up as built.

## Closed in Stage 4

| Item | What changed |
| --- | --- |
| Client address behind a proxy | `TRUSTED_PROXY_HOPS` takes the address from the trusted proxy's `X-Forwarded-For` entry. Entries a client writes further left are ignored, and a header shorter than the hop count falls back to the connection address. The compose file publishes the backend on 127.0.0.1 only, so only a proxy on the host can reach it |
| Reset emails without SMTP | Production refuses to start with `SMTP_HOST` empty |
| `ENVIRONMENT` defaults to `development` | The compose file sets `ENVIRONMENT=production`. Production also refuses localhost CORS and frontend addresses, the example database password and an empty roads path, and names every problem at once |
| Frontend headers | nginx sends `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a Content-Security-Policy. The smoke check confirms them |
| SQLite foreign keys and ids | The suite now also runs on PostgreSQL, where removing a planner removes their linked accounts. Production uses PostgreSQL, which does not reuse ids |
| A duplicate code saved in a race | Two saves of one depot, storage point or facility code could both pass the check, and the second got a 500. It now gets a 409 |

## Dependency audits

Both ran once, on November 2, 2026.

- `npm audit` in `frontend`: 0 vulnerabilities.
- `pip-audit` on the versions installed in `backend/.venv`: the one `pytest` advisory above, now fixed.

## What stays open

| Item | Effect | When to address |
| --- | --- | --- |
| Rate limits are held in memory | Counts are per process and reset on restart. Several server processes each keep their own count | Before running more than one process |
| Per-email limit | Someone who knows an email can lock that person out of login for up to 15 minutes, though a successful password reset lifts it, and can block that person's reset emails for up to an hour | Accepted for now |
| Limit under a burst | The limit is checked before the slow password hash and counted after it, so parallel requests can get past 5 in one window, up to the server's thread pool size (about 40). This comes from reading the code and was not measured | Later |
| Reset clears the address count | A successful reset clears the login count for that client address too, so someone with their own account could clear it, at most five times an hour | Accepted for now |
| Shared address limit | Five failed logins from one office network block that address for 15 minutes | Accepted for now |
| Temporary passwords | A team account is not forced to change the one its planner set | Later, with a password policy |
| Tokens after a password reset | An existing token stays valid until it expires, up to 60 minutes | Later |
| Token storage | The frontend keeps the token in `localStorage`, which a script injection could read. No injection was found, and React escapes displayed text | Later |
| Email discovery | Sign-up reports that an email is taken, and a login for an unknown email skips the password hash, so it returns faster | Later |
| Role authority | The five roles are proposed views, and their real authority is unconfirmed | Needs a decision from the municipality |

These are outside this stage's scope: single sign-on, audit logs, shared rate-limit storage and a full password policy.
