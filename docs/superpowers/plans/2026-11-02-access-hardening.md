# Access, Security and Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five server-enforced roles, test and fix the application's security, and measure its performance.

**Architecture:** Every route declares one permission through `Depends(require("name"))`, which returns the signed-in `User`, and a test walks the routes to prove it. Ownership queries use `workspace_owner_id(user)`, so a linked account reads its planner's data. Rate limits and the optimizer limit are small in-process modules.

**Tech Stack:** FastAPI, SQLAlchemy, PyJWT, pytest, React, Vitest. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-11-02-access-hardening-design.md`

## Global Constraints

- Branch `feat/access-hardening`. Backend tests: `.venv/Scripts/python -m pytest -q` from `backend`. Frontend tests: `npx vitest run` from `frontend`.
- Role values: `planner`, `reviewer`, `management`, `driver`, `facility`. Existing accounts become planners.
- Public sign-up always creates a planner, and `role` cannot be set through it.
- No screen may imply dispatch authority, approval or a vehicle instruction.
- Preview banner, exact text: `Synthetic preview, not a dispatch instruction`.
- Rate limits: 5 failed logins in 15 minutes; 5 forgot-password requests per hour; per email and per client address.
- `OPTIMIZER_MAX_CONCURRENT` default 2. Busy message, exact text: `The optimizer is busy. Try again shortly.`
- A disallowed role gets 403 with a plain message. Another workspace's record gets 404.
- Failed runs never carry a distance or a route.
- Do not commit `.env`, real credentials, `.claude/` or the untracked `docs/` folders.

## Decisions the spec left open

- **Third scoped endpoint.** The spec gives driver and facility "scenario names" but `GET /scenarios` returns full records. Add `GET /api/v1/scenarios/names`, returning `[{id, name}]` only.
- **Validate is a write.** `POST /scenarios/{id}/validate` saves a record, so it is planner-only.
- **Permissions move.** `get_current_user` and `require` live in `app/api/dependencies.py` to avoid an import cycle. `app/api/auth.py` keeps importing `get_current_user`.
- **Newest batch only.** A preview never falls back to an older batch. If both methods failed in the newest batch it returns 404.
- **Planners can open Route Preview,** so they can see what those accounts see. Reviewers and management cannot.
- **Temporary passwords** are not forced to change. The security report records this as open.

## Review Focus

Each line has a test in the owning task.

1. A role is changed or an account removed while its token is still valid: the next request uses the new role, or returns 401 (Tasks 2, 3).
2. The newest run failed, or the scenario changed after the run: the preview shows no older route, and flags a changed scenario as out of date (Task 4).
3. The correct password after the limit is reached still gets 429, and an unknown email counts the same as a known one, so the limit reveals nothing (Task 7).
4. The optimizer crashes mid-run: its slot is released, and later runs are not stuck at 503 (Task 10).
5. A linked account reads the planner's data on the dashboard and report, and never another planner's (Task 1).

---

### Task 1: Roles on accounts, and workspaces

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/schemas/auth.py`, `backend/app/db/migrations.py`, `backend/app/main.py`, `backend/app/api/{depots,evaluation,facilities,history,scenarios,storage_points,vehicles}.py`, `backend/app/services/{dashboard,evaluation_report}.py`, `backend/app/evaluation/catalog_loader.py`
- Create: `backend/app/core/permissions.py`
- Test: `backend/tests/test_roles.py`

**Interfaces:**
- Produces: `workspace_owner_id(user: User) -> int` in `app/core/permissions.py`; `ROLE_PLANNER`, `ROLE_REVIEWER`, `ROLE_MANAGEMENT`, `ROLE_DRIVER`, `ROLE_FACILITY`; `User.role`, `User.planner_id`; `upgrade_legacy_user_schema(engine)`; `UserResponse.role`; test helper `linked_user(db, planner, role, email) -> User` in `tests/test_roles.py`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_roles.py`:

```python
def test_a_new_account_is_a_planner(client):
    body = client.post("/api/v1/auth/register", json=CREDENTIALS).json()
    assert body["user"]["role"] == "planner"

def test_sign_up_cannot_choose_a_role(client):
    body = client.post("/api/v1/auth/register", json={**CREDENTIALS, "role": "reviewer"}).json()
    assert body["user"]["role"] == "planner"

def test_workspace_owner_of_a_planner_is_themselves(db_session, planner):
    assert workspace_owner_id(planner) == planner.id

def test_workspace_owner_of_a_linked_account_is_the_planner(db_session, planner):
    assert workspace_owner_id(linked_user(db_session, planner, "reviewer", "r@example.com")) == planner.id

def test_a_linked_account_sees_the_planners_dashboard(client, db_session, planner):
    """Create one depot as the planner; the reviewer's dashboard counts it."""

def test_a_linked_account_sees_the_planners_report(db_session, planner):
    """build_report for the linked account shows S01 loaded, and a second planner's shows not_loaded."""

def test_a_linked_account_lists_the_planners_records_only(client, db_session, planner):
    """GET /depots as the linked account returns the planner's depot, not a second planner's."""

def test_upgrade_adds_role_and_planner_to_old_users(tmp_path):
    """Build a SQLite users table without the columns, add a row, run
    upgrade_legacy_user_schema twice; the row reads role == 'planner' and planner_id is None,
    and an index exists on planner_id."""

def test_planner_foreign_key_cascades():
    key = next(iter(User.__table__.c.planner_id.foreign_keys))
    assert key.ondelete == "CASCADE"
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_roles.py -q`
Expected: FAIL on the import of `app.core.permissions`.

- [ ] **Step 3: Implement.** `role: String(20)`, default and server default `planner`. `planner_id`: nullable, indexed, FK `users.id` `ondelete="CASCADE"`. Add `role: str` to `UserResponse`. `upgrade_legacy_user_schema` follows `upgrade_legacy_evaluation_schema`, adds both columns, creates `ix_users_planner_id` if missing, and runs first in `lifespan`. Replace every ownership comparison on `user.id` with `workspace_owner_id(user)`, including `user_id=` on new records and the two filters in `catalog_loader` and `evaluation_report`.

- [ ] **Step 4: Run the whole backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: add account roles and shared workspaces"
```

### Task 2: One permission on every route

**Files:**
- Modify: `backend/app/core/permissions.py`, `backend/app/api/dependencies.py`, `backend/app/api/auth.py`, and every router in `backend/app/api/`
- Test: `backend/tests/test_permissions.py`

**Interfaces:**
- Consumes: `ROLE_*`, `User.role`.
- Produces: `PERMISSIONS: dict[str, frozenset[str]]`; `require(name: str) -> Callable[..., User]`, whose returned dependency has a `.permission` attribute; `get_current_user` in `app/api/dependencies.py`.

The table, one entry per name:

| Permission | Roles | Routes |
| --- | --- | --- |
| `account` | all five | `GET /auth/me` |
| `dashboard.read` | planner, reviewer, management | `GET /dashboard/summary` |
| `records.read` | planner, reviewer | every `GET` on depots, vehicles, storage points, facilities, scenarios, `GET /scenarios/options`, `GET /scenarios/{id}/validations` |
| `records.write` | planner | every `POST`, `PUT`, `DELETE` on those records, `POST /scenarios/{id}/validate`, `POST /scenarios/{id}/optimize`, `POST /evaluation/scenarios` |
| `optimization.read` | planner, reviewer | `GET /scenarios/{id}/optimization`, `GET /scenarios/{id}/optimization/{batch_id}` |
| `history.read` | planner, reviewer, management | `GET /optimization-history` |
| `reports.read` | planner, reviewer, management | `GET /evaluation/report`, `GET /evaluation/report.csv` |
| `scenarios.names` | planner, driver, facility | `GET /scenarios/names` (Task 4) |
| `preview.routes` | planner, driver | `GET /scenarios/{id}/preview/routes` (Task 4) |
| `preview.facility` | planner, facility | `GET /scenarios/{id}/preview/facility` (Task 4) |
| `team.manage` | planner | `/team` routes (Task 3) |

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_permissions.py`:

```python
PUBLIC = {"/health", "/api/v1/health", "/auth/register", "/auth/login", "/auth/forgot-password",
          "/auth/verify-reset-token", "/auth/reset-password", "/api/v1/auth/register",
          "/api/v1/auth/login", "/api/v1/auth/forgot-password",
          "/api/v1/auth/verify-reset-token", "/api/v1/auth/reset-password"}

def declared_permission(route: APIRoute) -> str | None:
    """Walk route.dependant.dependencies recursively for a call with `.permission`."""

def test_every_route_declares_a_permission():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in PUBLIC:
            assert declared_permission(route) in PERMISSIONS, route.path

# Method, path template, the permission's roles from the table.
MATRIX = [...]  # one row per protected API route

@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("method,path,allowed", MATRIX)
def test_role_matrix(client, accounts, role, method, path, allowed):
    """Allowed roles never get 403. Others get 403 with a string detail."""

def test_matrix_covers_every_protected_route():
    """Compare MATRIX with the /api/v1 routes from app.routes."""

def test_a_refused_write_changes_nothing(client, accounts, db_session):
    """A reviewer's POST /depots gets 403 and the depot count is unchanged."""

def test_a_role_change_applies_on_the_next_request(client, accounts, db_session):
    """Reviewer reads /depots, role set to driver in the database, same token gets 403."""
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_permissions.py -q`
Expected: FAIL, routes have no permission.

- [ ] **Step 3: Implement.** Move `bearer_scheme` and `get_current_user` to `dependencies.py`. `require` raises `ValueError` at import for an unknown name, and 403 with detail `Your account does not have access to this.` Replace each route's `Depends(get_current_user)` with the table's `Depends(require(...))`. `dependencies.py` imports `jwt`, `settings` and `User`; nothing under `app/core` imports from `app/api`.

- [ ] **Step 4: Run the whole backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: enforce a permission on every route"
```

### Task 3: Team accounts

**Files:**
- Create: `backend/app/api/team.py`, `backend/app/schemas/team.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_team.py`

**Interfaces:**
- Consumes: `require("team.manage")`.
- Produces: `GET /api/v1/team`, `POST /api/v1/team`, `PUT /api/v1/team/{id}` (body `{role}`), `DELETE /api/v1/team/{id}`; `TeamMember {id, name, email, role}`.

- [ ] **Step 1: Write the failing tests**, each through the API:

```python
test_planner_creates_a_linked_account          # 201, role kept, the new account can sign in
test_team_cannot_create_a_planner               # role "planner" gets 422
test_team_lists_only_your_own_accounts          # a second planner's linked account is absent
test_duplicate_email_is_refused                 # "Rev@Example.com" after "rev@example.com" gets 409
test_blank_name_is_refused                      # "   " gets 422
test_short_password_is_refused                  # under 8 characters gets 422
test_changing_a_role_applies_at_once            # PUT, then the old token gets 403 on the old route
test_another_planners_account_cannot_be_changed # PUT and DELETE get 404
test_a_planner_cannot_change_their_own_role     # PUT on own id gets 404, role unchanged
test_removing_an_account_ends_its_session       # DELETE gets 204, the old token gets 401
test_removing_an_account_removes_its_reset_tokens  # no PasswordResetToken row remains
test_linked_accounts_cannot_manage_the_team     # every /team route gets 403
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_team.py -q`
Expected: FAIL with 404 on `/api/v1/team`.

- [ ] **Step 3: Implement.** `TeamMemberCreate` has `role: Literal["reviewer", "management", "driver", "facility"]` and the name, email and password rules of `UserCreate`. Lookups filter on `User.planner_id == user.id`, so the planner's own id is 404. Delete reset tokens explicitly, because SQLite does not enforce the cascade.

- [ ] **Step 4: Run the file**

Run: `.venv/Scripts/python -m pytest tests/test_team.py -q`
Expected: all pass.

- [ ] **Step 5: Add the team routes to `MATRIX` in `test_permissions.py`, run the backend suite, and commit**

```bash
git add backend
git commit -m "feat: let planners manage team accounts"
```

### Task 4: Preview endpoints

**Files:**
- Create: `backend/app/services/route_preview.py`, `backend/app/schemas/preview.py`
- Modify: `backend/app/api/scenarios.py`, `backend/app/services/evaluation_report.py`
- Test: `backend/tests/test_preview.py`

**Interfaces:**
- Consumes: `add_batch` shape from `test_evaluation_report.py`.
- Produces: rename `_newest_batch` to `newest_batch` and `_records` to `scenario_records`. `preview_run(db, scenario) -> OptimizationRun | None`. `RoutePreview {scenario_name, method, out_of_date, routes: [{vehicle_name, stops: [{code, name, quantity_kg, arrival_s, ...}]}]}`. `FacilityPreview {scenario_name, method, out_of_date, expected_total_kg, facility_capacity_kg, vehicles: [{vehicle_name, load_kg, capacity_kg}]}`. Stop fields follow what `_route_json` stores; latitude, longitude and `geometry` are left out.

- [ ] **Step 1: Write the failing tests:**

```python
test_names_return_only_id_and_name          # keys == {"id", "name"}
test_names_are_workspace_scoped
test_routes_prefer_or_tools                 # method == "or_tools"
test_routes_fall_back_to_greedy             # OR-Tools no_solution, method == "greedy"
test_routes_404_when_no_run_exists
test_routes_404_when_both_methods_failed
test_a_failed_newest_batch_hides_an_older_route  # older good batch, newest failed: 404
test_routes_leave_out_geometry
test_facility_totals_match_vehicle_loads    # expected_total_kg == sum of loads
test_facility_uses_the_same_method_as_routes
test_a_changed_scenario_is_out_of_date      # edit a point after the run: out_of_date is True
test_a_fresh_run_is_not_out_of_date
test_another_workspace_gets_404
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_preview.py -q`
Expected: FAIL with 404 or 422 on the new routes.

- [ ] **Step 3: Implement.** A run qualifies only with status `feasible` or `optimal`. `out_of_date` uses the same `updated_at` against `created_at` rule as the report. Declare `/names` before `/{scenario_id}`. Both 404 details: `No saved route exists for this scenario.`

- [ ] **Step 4: Run the file**

Run: `.venv/Scripts/python -m pytest tests/test_preview.py -q`
Expected: all pass.

- [ ] **Step 5: Add the three routes to `MATRIX`, run the backend suite, and commit**

```bash
git add backend
git commit -m "feat: add scoped route and facility previews"
```

### Task 5: Role-aware frontend

**Files:**
- Create: `frontend/src/auth/permissions.js`, `frontend/src/auth/RequirePermission.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/components/AppLayout.jsx`, the six management pages, `DashboardPage.jsx`, `HistoryPage.jsx`, `ReportsPage.jsx`, `RouteOptimizationPage.jsx`, and each test file's account fixture
- Test: `frontend/src/test/roles.test.jsx`

**Interfaces:**
- Produces: `can(user, permission) -> boolean`, false for a missing or unknown role; `homePath(user) -> string`; `ROLE_LABELS`; `<RequirePermission permission="...">`, which wraps routes and redirects to `homePath(user)`.
- `permissions.js` mirrors the Task 2 table.

- [ ] **Step 1: Write the failing tests:**

```jsx
it("treats an unknown role as having no access")
it.each(ROLE_CASES)("shows %s only its pages in the sidebar")
it("sends a driver from /dashboard to /route-preview without a redirect loop")
it("sends management from /depot to /dashboard")
it("hides create, edit and delete from a reviewer")
it("hides Validate and Run from a reviewer on the scenario and route pages")
it("hides Load and Run all from a reviewer on the report page")
it("shows management the history list without links to run details")
it("shows the role label instead of Municipal coordinator")
```

- [ ] **Step 2: Run them**

Run: `npx vitest run src/test/roles.test.jsx`
Expected: FAIL on the import of `permissions.js`.

- [ ] **Step 3: Implement.** Add `permission` to each `NAV_ITEMS` entry and filter on it. Settings has none. Guard routes with `records.read`, `records.write`, `optimization.read`, `history.read`, `reports.read`, `dashboard.read`. Hide dashboard links a role cannot open. Labels: Planner, Reviewer, Management, Driver preview, Facility preview. Add `role: "planner"` to existing test fixtures.

- [ ] **Step 4: Run the frontend suite**

Run: `npx vitest run`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: show each role only what it can use"
```

### Task 6: Team and Route Preview pages

**Files:**
- Create: `frontend/src/pages/TeamPage.jsx`, `frontend/src/pages/RoutePreviewPage.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/components/AppLayout.jsx`, `frontend/src/services/api.js`, `frontend/src/styles.css`
- Test: `frontend/src/test/team.test.jsx`, `frontend/src/test/routePreview.test.jsx`

**Interfaces:**
- Consumes: Tasks 3 and 4 endpoints, `can`.
- Produces: `getTeam`, `createTeamMember`, `updateTeamMemberRole`, `deleteTeamMember`, `getScenarioNames`, `getRoutePreview`, `getFacilityPreview`. Routes `/team` (`team.manage`) and `/route-preview` (`scenarios.names`).

- [ ] **Step 1: Write the failing tests:**

```jsx
it("lists team accounts and adds one")
it("does not offer Planner as a team role")
it("changes a role and removes an account after confirming")
it("shows a server refusal on the team page")
it("always shows the synthetic preview banner")
it("shows a driver stops, quantities and planned times but no facility section")
it("shows a facility account loads against capacity but no stops")
it("says no saved route exists on a 404, not that the server is old")
it("flags an out-of-date preview")
```

- [ ] **Step 2: Run them**

Run: `npx vitest run src/test/team.test.jsx src/test/routePreview.test.jsx`
Expected: FAIL, the pages do not exist.

- [ ] **Step 3: Implement.** Use the existing `Panel`, `PageError` and table patterns. On `error.status === 404`, the preview page shows `No saved route exists for this scenario.` Out-of-date text: `This scenario changed after the run, so this preview may no longer match it.` Avoid the words dispatch, assign, approve and instruction, apart from the fixed banner.

- [ ] **Step 4: Run the frontend suite and the build**

Run: `npx vitest run; npm run build`
Expected: all pass, and the build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add the team and route preview pages"
```

### Task 7: Rate limits

**Files:**
- Create: `backend/app/core/rate_limit.py`
- Modify: `backend/app/api/auth.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_rate_limit.py`

**Interfaces:**
- Produces: `RateLimiter(limit: int, window_s: float, clock=time.monotonic)` with `is_blocked(key) -> bool`, `record(key)`, `clear(key)`, `reset()`; module instances `login_limiter`, `forgot_password_limiter`.

- [ ] **Step 1: Write the failing tests:**

```python
test_five_failed_logins_then_429
test_the_correct_password_is_also_refused_once_limited   # 429 and no token
test_the_limit_is_per_email_ignoring_case
test_the_limit_is_per_client_address                     # five emails, then a sixth gets 429
test_a_successful_login_clears_the_emails_count
test_a_successful_login_keeps_the_address_count
test_the_window_expires                                  # fake clock moves 15 minutes
test_unknown_and_known_email_are_limited_alike           # same statuses and bodies
test_forgot_password_limits_after_five                   # sixth is 429 for known and unknown email
test_expired_keys_are_removed                            # internal store shrinks after the window
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_rate_limit.py -q`
Expected: FAIL on the import.

- [ ] **Step 3: Implement.** Keep a `threading.Lock` and a dict of deques. Prune a key when it is touched, and sweep all keys when the dict passes 10,000. Keys are `email:<lowercase>` and `ip:<request.client.host>`. Check before verifying the password. 429 details: `Too many attempts. Try again later.` Add an autouse fixture in `conftest.py` that resets both limiters.

- [ ] **Step 4: Run the backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat: limit repeated login and password reset requests"
```

### Task 8: Production settings and headers

**Files:**
- Modify: `backend/app/core/config.py`, `backend/app/main.py`, `.env.example`
- Test: `backend/tests/test_hardening.py`

**Interfaces:**
- Produces: `Settings.environment` default `development`; `DEFAULT_JWT_SECRET`; `check_production_settings(values: Settings) -> None`, raising `RuntimeError`; `api_doc_urls(environment: str) -> dict`.

- [ ] **Step 1: Write the failing tests:**

```python
test_production_refuses_the_default_secret
test_production_refuses_a_31_character_secret
test_production_accepts_a_32_character_secret
test_development_keeps_the_default_secret
test_the_server_will_not_start_on_the_default_secret  # `with TestClient(app)` raises before any DB use
test_security_headers_on_a_normal_response
test_security_headers_on_a_404
test_security_headers_on_an_unexpected_500             # uses the test_errors.py pattern
test_hsts_only_outside_development
test_docs_are_off_outside_development                  # subprocess with ENVIRONMENT=production asserts app.openapi_url is None
test_docs_stay_on_in_development
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_hardening.py -q`
Expected: FAIL on the missing names.

- [ ] **Step 3: Implement.** Call `check_production_settings(settings)` on the first line of `lifespan`. Add the headers middleware after `CORSMiddleware`, so it is outermost and covers 500s. HSTS value: `max-age=31536000; includeSubDomains`. Add `ENVIRONMENT=development` to `.env.example` with a one-line comment.

- [ ] **Step 4: Run the backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend .env.example
git commit -m "feat: refuse unsafe production settings and add security headers"
```

### Task 9: Security tests, audits and report

**Files:**
- Create: `backend/tests/test_security.py`, `docs/security/security-report.md`
- Modify: whatever the tests or audits show needs fixing

**Interfaces:**
- Consumes: `declared_permission`, `MATRIX`, `linked_user`.

- [ ] **Step 1: Write the tests:**

```python
ID_ROUTES = [...]  # method, path with the other workspace's ids, valid body

def test_id_route_list_is_complete():
    """Every /api/v1 route with a path parameter appears in ID_ROUTES."""

@pytest.mark.parametrize("method,path,body", ID_ROUTES)
def test_another_workspace_gets_404(client, two_workspaces, method, path, body): ...

test_a_tampered_token_is_refused
test_an_expired_token_is_refused
test_a_wrong_secret_token_is_refused
test_an_alg_none_token_is_refused
test_a_token_for_a_deleted_account_is_refused
test_a_token_without_a_subject_is_refused
test_every_write_refuses_a_linked_account           # parametrized over MATRIX writes with valid tokens
test_oversized_text_is_refused                      # one case per create schema's text fields: 422, not 500
test_sql_shaped_text_is_stored_as_text              # "'; DROP TABLE users; --" as a code round-trips and users remain
test_sql_shaped_history_filter_returns_no_rows
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_security.py -q`
Expected: read each failure. A failure is a finding: fix it test-first and list it in the report.

- [ ] **Step 3: Run the audits once**

Install `pip-audit` into a throwaway venv in the scratchpad, not `backend/.venv`.
Run: `pip-audit -r backend/requirements.txt`, then `npm audit` from `frontend`.
Expected: findings read. Upgrade fixable ones within the requirement ranges, rerun both suites, and record the rest.

- [ ] **Step 4: Write `docs/security/security-report.md`**

Sections: what was tested, findings and fixes, audit results with dates, and what stays open. Open items include: limits are per process and reset on restart; behind a proxy every client shares one address until Stage 4 configures forwarded addresses; per-email limits let someone temporarily lock another person out; temporary passwords are not forced to change; tokens stay valid until expiry after a password reset; the frontend stores tokens in `localStorage`.

- [ ] **Step 5: Run both suites and commit**

```bash
git add backend frontend docs/security
git commit -m "test: cover access and input security, and add the report"
```

### Task 10: Optimizer limit

**Files:**
- Create: `backend/app/services/optimizer_slots.py`
- Modify: `backend/app/core/config.py`, `backend/app/api/scenarios.py`, `frontend/src/pages/ReportsPage.jsx`, `.env.example`
- Test: `backend/tests/test_optimizer_slots.py`, `frontend/src/test/reports.test.jsx`

**Interfaces:**
- Produces: `Settings.optimizer_max_concurrent` default 2, `gt=0`; `optimizer_slot()` context manager; `OptimizerBusy`; `reset_slots()` for tests.

- [ ] **Step 1: Write the failing tests:**

```python
test_a_run_past_the_limit_gets_503     # hold two slots: 503 with the exact busy message
test_no_batch_is_saved_when_busy
test_a_finished_run_frees_its_slot
test_a_crashed_run_frees_its_slot      # optimize_scenario raises, later run does not get 503
test_the_limit_comes_from_settings     # limit 1, hold one: 503
```

```jsx
it("records a busy case as failed and carries on with the rest of Run all")
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_optimizer_slots.py -q`, then `npx vitest run src/test/reports.test.jsx`
Expected: the backend file fails on the import. Read the frontend result: if Run all already stops on the first failure, the new test fails; if it passes first time, make sure it asserts that later cases ran.

- [ ] **Step 3: Implement.** A lock and a counter, read against settings on each acquire. Hold the slot only around `optimize_scenario`, after validation. Make Run all catch per case, add `<code>: <message>` to the error list, and continue.

- [ ] **Step 4: Run both suites**

Run: `.venv/Scripts/python -m pytest -q`, then `npx vitest run`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend frontend .env.example
git commit -m "feat: limit concurrent optimizer runs"
```

### Task 11: Performance check and report

**Files:**
- Create: `backend/scripts/perf_check.py`, `backend/tests/test_perf_check.py`, `docs/performance/performance-report.md`

**Interfaces:**
- Produces: `seed(database_url: str, password: str) -> dict` returning counts; `percentile(values: list[float], pct: float) -> float`; `measure(base_url, email, password, clients=5, requests_each=20) -> dict`; CLI `seed --db PATH` and `measure --url URL`.

- [ ] **Step 1: Write the failing tests:**

```python
test_percentile_of_a_known_list    # percentile([1,2,3,4], 50) == 2.5, and 95 == 3.85
test_percentile_of_one_value
test_seed_creates_the_stated_size  # tmp SQLite: 50 scenarios, 500 points, 2,000 runs
test_seed_refuses_an_existing_file # never overwrites a database
test_seed_refuses_a_non_sqlite_url
```

- [ ] **Step 2: Run them**

Run: `.venv/Scripts/python -m pytest tests/test_perf_check.py -q`
Expected: FAIL, the script does not exist.

- [ ] **Step 3: Implement.** Seed also loads the catalogue, so optimization has real road positions, and generates the password at run time. `measure` covers dashboard, scenario list, history, report and validation at five clients, then three concurrent S01 optimizations, counting 200s and 503s separately. It uses `httpx` and threads.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_perf_check.py -q`
Expected: all pass.

- [ ] **Step 5: Measure for real**

Seed a database in the scratchpad, start `uvicorn` against it with `ROAD_NETWORK_PATH` set, run `measure`, then stop the server by PID.
Expected: p50 and p95 per endpoint, and with three concurrent optimizations, two 200s and one 503.

- [ ] **Step 6: Write `docs/performance/performance-report.md`**

Include machine, dataset size, SQLite note, results against the assumed 500 ms target, misses and what was fixed. Fix a miss only if it is small, test-first where behaviour changes.

- [ ] **Step 7: Run the backend suite and commit**

```bash
git add backend docs/performance
git commit -m "test: measure API performance and add the report"
```

### Task 12: Documents and end-to-end check

**Files:**
- Modify: `README.md`, `NAGARFLOW_AI_Master_Guide.pdf`

**Interfaces:** none.

- [ ] **Step 1: Browser check.** Against a throwaway SQLite database with the Trichy roads, sign in as each of the five roles. Confirm each sidebar, one refused page redirect, and for driver and facility the banner and preview data. Run one planner optimization first. Stop every server afterwards.

- [ ] **Step 2: Update `README.md`**

Add Roles, Security and Performance sections, replace the Accounts text that says all accounts are equal if present, and document `ENVIRONMENT` and `OPTIMIZER_MAX_CONCURRENT`. State that role authority is unconfirmed.

- [ ] **Step 3: Add Master Guide page 11D**

Follow `guide11c.py` in the scratchpad: insert after page 11C. Record that the five roles replace the older roadmap's list, plus security and performance results and test counts.

- [ ] **Step 4: Run both suites and the build**

Run: `.venv/Scripts/python -m pytest -q`, then `npx vitest run; npm run build`
Expected: all pass, and the build succeeds.

- [ ] **Step 5: Commit**

```bash
git add README.md NAGARFLOW_AI_Master_Guide.pdf
git commit -m "docs: complete Stage 3 access and hardening"
```
