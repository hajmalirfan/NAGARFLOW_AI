# Stage 3: Access, Security and Performance

Roadmap Steps 21–23. Branch `feat/access-hardening`, stacked on `feat/evaluation`.

## Goal

Add five roles enforced on the server, test the application's security and fix
what is found, and measure how it performs.

## Rules carried from the project documents

- Roles are the five proposed views in the requirements document, not municipal
  job titles. Their real authority is unconfirmed.
- No screen may imply dispatch authority, approval or a vehicle instruction.
- Driver and facility views are read-only previews of synthetic plans, and say so.
- This decision replaces the older roadmap's role list, and the Master Guide
  records that.

## Step 21: Roles

`User` gains `role` (String(20), default `planner`) and a nullable `planner_id`
foreign key to `users.id`, on delete cascade. Existing accounts become planners.

| Role | Value | Reads | Writes |
| --- | --- | --- | --- |
| Planner | `planner` | Everything | Everything, and team accounts |
| Reviewer | `reviewer` | Dashboard, all records, scenarios, validations, optimization, history, reports | Nothing |
| Management | `management` | Dashboard, reports, history list | Nothing |
| Driver preview | `driver` | Scenario names, and saved routes for a run | Nothing |
| Facility preview | `facility` | Scenario names, and expected load by vehicle against capacity for a run | Nothing |

**Workspaces.** `workspace_owner_id(user)` returns `user.planner_id` or else
`user.id`. Every ownership query uses it, so a linked account reads its planner's
data. Planners stay separated from one another. Public sign-up always creates a
planner, and `role` cannot be set through it.

**Team.** A Team page, for planners only, lists linked accounts and creates,
changes the role of, and removes them. `POST /api/v1/team` takes name, email,
role and a temporary password. A planner cannot create another planner, change
an account outside their team, or change their own role. Removing a planner's
account removes its linked accounts.

**Enforcement.** `app/core/permissions.py` holds one table of permission to
roles. Routes declare `Depends(require("name"))`, which reads the role from the
database on each request, so a change applies at once. A disallowed role gets 403
with a plain message. A test walks every API route and fails if one has no
permission declared, apart from a short list of public routes.

**Frontend.** `/auth/me` returns the role. The sidebar and page actions show only
what the role can use, and a page the role cannot use redirects to the dashboard
or the first page it can use. A **Route Preview** page serves driver and facility
accounts, carries a "Synthetic preview, not a dispatch instruction" banner, and
reads three new scoped endpoints:

- `GET /api/v1/scenarios/names`: id and name only, because the full scenario
  list holds more than these roles may read.
- `GET /api/v1/scenarios/{id}/preview/routes`: vehicle, stops, quantities and
  planned times for the newest run's OR-Tools routes, or Greedy's when OR-Tools
  has none. 404 if no route exists.
- `GET /api/v1/scenarios/{id}/preview/facility`: expected total, per-vehicle
  loads and capacity for the same run.

## Step 22: Security

**Fixes.**

- Rate limits, held in memory, per email and per client address: 5 failed logins
  in 15 minutes, and 5 forgot-password requests per hour, then 429 with a plain
  message. A successful login clears the email's count.
- With `ENVIRONMENT` set to anything but `development`, the server refuses to
  start on the default JWT secret, or on a secret shorter than 32 characters.
- Security headers on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and
  `Strict-Transport-Security` outside development.
- API docs are off outside development.

**Tests.**

- A role-by-endpoint matrix covering every route.
- One workspace reaching for another's records through every id-taking route,
  expecting 404.
- Tampered, expired and wrong-algorithm tokens, and a token for a deleted account.
- A linked account's writes are refused even with a valid token.
- Oversized input and SQL-shaped text in search and code fields.

**Audit.** `pip-audit` and `npm audit` run once, and fixable findings are fixed.

**Report.** `docs/security/security-report.md` lists what was tested, found and
fixed, and what stays open. In-memory rate limits are per process, which it
records as a limit.

## Step 23: Performance

`backend/scripts/perf_check.py` seeds a throwaway SQLite database with a realistic
size (50 scenarios, 500 points, 2,000 runs), starts nothing itself, and measures
the running API with five concurrent clients. It reports p50 and p95 for the
dashboard, scenario list, history, report and validation, plus three concurrent
optimizations. No new dependency: it uses `httpx`, already present for tests, and
threads.

Targets are assumptions, since none are set: p95 under 500 ms for reads at five
concurrent users. Results go in `docs/performance/performance-report.md` whether
or not they meet them. A miss with a small fix is fixed. Others are recorded.

**Concurrency limit.** `OPTIMIZER_MAX_CONCURRENT`, default 2. A run past the limit
returns 503 with "The optimizer is busy. Try again shortly." Run all treats this
as a failure for that case and carries on. No job queue.

## Testing

Test-first throughout. End to end, sign in as each role in the browser against a
throwaway database. One whole-branch review at the end.

## Out of scope

Single sign-on, password policies beyond the current one, audit logs, shared
rate-limit storage, a job queue, PostgreSQL performance testing (Stage 4).

## Done when

Every route has a declared permission, the matrix tests pass, the security and
performance reports are written, both suites pass, and README and Master Guide
record the role decision and results.
