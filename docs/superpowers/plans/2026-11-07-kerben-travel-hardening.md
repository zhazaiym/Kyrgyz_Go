# Kerben Travel Reliability and Security Plan

> **For agentic workers:** Execute inline in this session. Work only on the eight areas listed below and preserve existing uncommitted user changes.

**Goal:** Improve AI answer grounding, booking correctness, diagnostics, local load coverage, administrator security, translation recovery, deployment rollback evidence, and the directly related docs/CI.

**Architecture:** Keep the current FastAPI, PostgreSQL, WebSocket, Gemini, SQLAdmin, and manual deployment boundaries. Add changes behind existing service seams, test each behavior before implementation, and avoid broad rewrites. Metrics and load output must not expose prompts, credentials, client identifiers, or production data.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, pytest, Docker Compose, Gemini SDK, SQLAdmin.

## Global Constraints

- Scope is limited to the eight requested work areas; do not alter frontend, domain, production server, or unrelated project files.
- Do not call real Gemini in normal tests or CI. Any live call must require an explicit opt-in and have a small fixed request ceiling.
- Do not run deployment or load traffic against a production host. Use disposable local/test resources only.
- Admin roles: `owner` (all permissions and admin management), `manager` (travel requests and selections), `catalog_editor` (catalogue and public content, no admin management).
- Require TOTP MFA for both SQLAdmin and the admin Bearer API. Recovery material must be single-use and stored hashed; TOTP secrets must not be stored in plaintext.
- Keep API contracts compatible except for the intentionally strengthened administrator login challenge.
- Preserve all pre-existing working-tree edits; do not commit or push unless separately requested.

---

### Task 1: AI accuracy and booking safety

**Files:** `ML/agent.py`, `ML/prompts.py`, `ML/tools.py`, `mysite/api/chat.py`, `mysite/api/chat_service.py`, chat/database tests.

- [x] Add regression tests for unsupported catalogue claims, empty FAQ results, country-aware search, and repeated/concurrent booking confirmation.
- [x] Confirm the FAQ, country-search, and separate-session concurrency regressions fail on the original behavior.
- [x] Make the smallest behavior changes that preserve grounded answers and idempotent booking across separate DB sessions/workers.
- [x] Run targeted ML and booking tests against isolated PostgreSQL; the targeted booking/AI set passed 85 tests.

### Task 2: Monitoring and diagnostics

**Files:** new `mysite/api/observability.py`, `main.py`, `ML/agent.py`, `mysite/api/chat_ws.py`, `mysite/translations/jobs.py`, `.env.example`, `tests/unit`.

- [x] Add tests for bounded metric labels and no sensitive payload capture; instrument AI, WebSocket, PostgreSQL, booking conflicts, and translation outcomes.
- [x] Implement the protected scrape endpoint, counters/histograms/gauges, and payload-free diagnostics.
- [x] Run metrics unit tests; assert expected aggregates and no message text or identifiers.

### Task 3: Repeatable load tests

**Files:** new `scripts/load_test.py`, new local load Compose configuration if needed, `tests/unit`, `requirements-dev.txt`, README/deployment guidance.

- [x] Add profile tests for loopback-only PostgreSQL, bounded concurrency, and safe provider selection.
- [x] Implement the authenticated local WebSocket/PostgreSQL harness; Gemini is stubbed by default and live calls require two explicit opt-ins and an eight-call ceiling.
- [x] Report throughput, p50/p95/p99, error rate, disconnects, provider mode, target errors, and generator errors.
- [x] Run a two-user local smoke profile: two messages completed with zero errors/disconnects.

### Task 4: Administrator MFA, roles, and limits

**Files:** admin schemas/auth, `mysite/admin/setup.py`, `mysite/admin/views.py`, admin dependencies/routes, `mysite/database/models.py`, new Alembic migration, `create_admin.py` or a scoped admin MFA command, `.env.example`, admin tests.

- [x] Add tests for TOTP login, replay rejection, recovery-code single use, role permissions, and SQLAdmin MFA form/access.
- [x] Add encrypted TOTP storage, hashed recovery codes, API/SQLAdmin MFA, and three roles. Existing admins migrate as `owner`.
- [x] Enforce manager and catalog-editor permissions in API dependencies and SQLAdmin view access checks.
- [x] Run targeted admin login, access, MFA, and role tests against disposable PostgreSQL.

### Task 5: Translation background-job reliability

**Files:** `mysite/translations/jobs.py`, translation database models and migration, `main.py`, translation tests.

- [x] Add tests for transient failure/retry state, duplicate concurrent enqueue, source updates, and retry ceiling persistence.
- [x] Persist jobs with database claims/leases, bounded retries/backoff, and startup discovery; retain stale-source/manual protections.
- [x] Run translation identity and persistence tests against disposable PostgreSQL.

### Task 6: Deployment backup and rollback rehearsal

**Files:** `scripts/ci_deploy.py`, `scripts/manual_deploy.py` only if evidence identifies gaps, `tests/test_ci_deploy.py`, `tests/test_manual_deploy.py`, local deployment docs.

- [x] Add tests for custom-dump header validation, failed activation rollback, and deployment-state preservation.
- [x] Factor the existing rollback into a reviewable helper; keep schema compatibility and backup guards.
- [ ] Exercise the rehearsal using disposable local resources; do not SSH, upload, migrate, or restart any production service.

### Task 7: Quality gates and regression coverage

**Files:** `.github/workflows/ci.yml`, `tests`, `pyproject.toml` only where needed.

- [ ] Add tests first for any CI gate or test-harness behavior changed.
- [ ] Run syntax, Ruff/format, security, unit, PostgreSQL integration, AI-stub load smoke, and deployment rehearsal checks locally where available.
- [ ] Add CI gates for deterministic checks only; never run paid Gemini traffic or production deployment from CI.

### Task 8: Documentation aligned to implementation

**Files:** `README.md`, `API.md`, `DEPLOY.md`, `ML/README.md`, `docs/README.md`, scoped runbooks.

- [x] Document role permissions, MFA enrollment/reset, metrics access, load-test modes/limits, translation retry, backups/rollback, and health-check limits.
- [x] Keep Kerben Travel as the product name while retaining legacy identifiers only where required for compatibility.
- [ ] Check all local Markdown links, relevant commands, and environment variable names against implementation.

## Final verification

Run `ruff check .`, `python -m scripts.format_code --check`, `python -m compileall -q main.py ML mysite scripts alembic`, Bandit, all ML and unit tests, the complete PostgreSQL integration suite, Compose config validation, local stubbed load smoke, migration graph checks, and local backup/rollback rehearsal. Report any check blocked by local infrastructure separately from a passing result.
