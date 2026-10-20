# KYRGYZGO Docker and CORS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the existing FastAPI backend as an app-only Docker service that connects to the team's existing database and accepts frontend requests only from configured origins.

**Architecture:** Build one non-root Python 3.12 application image. Compose injects the existing `.env`, maps port 8000, exposes the Docker host under `host.docker.internal`, applies Alembic migrations before Uvicorn, and checks the public root endpoint. HTTP and WebSocket origins remain semicolon-separated environment settings.

**Tech Stack:** Docker, Docker Compose, Python 3.12, FastAPI, Uvicorn, Alembic, pytest.

## Execution status (2026-10-20)

- Docker packaging, runtime environment examples, and server/frontend instructions implemented.
- API port binds to localhost by default for a host HTTPS proxy; `API_BIND_HOST`
  allows an explicit override. Local frontend examples cover ports 3000 and 5173.
- Existing CORS behavior verified with allowed/denied origins, whitespace parsing,
  and Authorization/Content-Type preflight headers. Full suite: 112 passed.
- `docker compose config --quiet` passed; `git diff --check` passed.
- Docker Desktop started and `docker compose build api` passed. The `.env`
  database hostname now uses `host.docker.internal`; credentials are preserved.
- The configured local PostgreSQL database `kyrgyzgo_db` did not exist; it was
  created without changing other databases. Container startup applied both
  migrations; `alembic current` confirms `20261020_0002 (head)`.
- `docker compose up -d --wait --wait-timeout 60` passed; service is healthy
  and bound to `127.0.0.1:8000`. Live checks returned HTTP 200 for `/`,
  `/openapi.json`, and `/countries/`. CORS preflight with Authorization and
  Content-Type passed for localhost ports 3000/5173 and rejected an untrusted
  origin with HTTP 400 and no Access-Control-Allow-Origin header.
- This is a local deployment. Public server DNS, frontend production origins,
  HTTPS certificates, and a reverse proxy still require target server details.
- Configuration checks used the existing test suite and Compose validation;
  no tests were added that merely duplicate Dockerfile/YAML text.

## Global Constraints

- Do not create a PostgreSQL container or copy the team's database.
- Do not commit `.env` or any real credential.
- Do not modify business endpoints or response shapes.
- Use `DATABASE_URL` for the database, `CORS_ALLOWED_ORIGINS` for HTTP, and `CHAT_ALLOWED_ORIGINS` for WebSockets.
- Run migrations before starting Uvicorn.

---

### Task 1: Add tested Docker packaging

**Files:**
- Modify: `tests/test_deployment_files.py`
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `requirements.txt`, `.env`, `alembic.ini`, `main:app`, and `DATABASE_URL`.
- Produces: image `kyrgyzgo-api`, Compose service `api`, host port `${API_PORT:-8000}`, and `/` healthcheck.

- [ ] **Step 1: Add failing deployment assertions**

Extend `tests/test_deployment_files.py` with assertions that `Dockerfile`,
`compose.yaml`, and `.dockerignore` exist; the Dockerfile uses Python 3.12,
runs as a non-root user, runs `alembic upgrade head`, and starts Uvicorn; the
Compose file uses `.env`, maps port 8000, adds `host.docker.internal`, and has
no database service; `.dockerignore` excludes `.env`, `.git`, virtualenvs,
caches, and `*.db`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -B -m pytest tests/test_deployment_files.py -q`

Expected: FAIL because the three Docker files do not exist.

- [ ] **Step 3: Add the minimal Dockerfile**

Create a `python:3.12-slim` image, set `/app`, install `requirements.txt`, copy
the source, change ownership to a dedicated `app` user, expose 8000, then use:

```dockerfile
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 4: Add app-only Compose and build exclusions**

Create one `api` service with `env_file: .env`, `${API_PORT:-8000}:8000`,
`host.docker.internal:host-gateway`, `restart: unless-stopped`, and a Python
stdlib HTTP healthcheck. Create `.dockerignore` that excludes secrets, Git,
virtual environments, caches, tests, local databases, IDE files, and docs.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run: `python -B -m pytest tests/test_deployment_files.py -q`

Expected: all deployment tests pass.

### Task 2: Document frontend and database connectivity

**Files:**
- Modify: `.env.example`
- Modify: `DEPLOY.md`
- Modify: `tests/test_deployment_files.py`
- Modify: `tests/test_app_config.py`

**Interfaces:**
- Consumes: semicolon-separated frontend origins and the existing database URL.
- Produces: documented local/frontend CORS defaults and exact Docker commands for host or network databases.

- [ ] **Step 1: Add failing documentation/config assertions**

Assert that `.env.example` demonstrates both localhost frontend origins, that
`DEPLOY.md` contains `docker compose up --build -d`, and that it explains
replacing `127.0.0.1` with `host.docker.internal` only when PostgreSQL runs on
the same Docker host.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -B -m pytest tests/test_deployment_files.py tests/test_app_config.py -q`

Expected: FAIL because Docker deployment and host-database instructions are absent.

- [ ] **Step 3: Update safe example settings and deployment documentation**

Set both origin examples to:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:3000;http://127.0.0.1:3000
CHAT_ALLOWED_ORIGINS=http://localhost:3000;http://127.0.0.1:3000
```

Document `.env` setup, external database addressing, `docker compose config`,
`docker compose up --build -d`, health/status checks, logs, migration behavior,
and replacing local origins with the frontend's HTTPS domain in production.

- [ ] **Step 4: Run focused and full tests**

Run: `python -B -m pytest tests/test_deployment_files.py tests/test_app_config.py -q`

Run: `python -B -m pytest -q`

Expected: all tests pass.

### Task 3: Validate the real container lifecycle safely

**Files:**
- No source changes expected.

**Interfaces:**
- Consumes: Docker daemon and an isolated SQLite URL used only for verification.
- Produces: validated Compose model, built image, migrated temporary database, and healthy HTTP container.

- [ ] **Step 1: Validate Compose rendering**

Run: `docker compose config --quiet`

Expected: exit 0.

- [ ] **Step 2: Build the image**

Run: `docker compose build api`

Expected: exit 0 with the application image created.

- [ ] **Step 3: Run an isolated smoke container**

Run the image with a temporary `DATABASE_URL=sqlite:////tmp/kyrgyzgo-smoke.db`,
a test-only secret, and local CORS origins. Wait for the healthcheck, then
request `/`, `/openapi.json`, and a CORS preflight request.

Expected: HTTP 200, OpenAPI 200, and the configured origin echoed in
`Access-Control-Allow-Origin`.

- [ ] **Step 4: Remove only smoke resources**

Stop and remove the named smoke container. Do not remove volumes, databases,
images, or unrelated containers.

- [ ] **Step 5: Final verification**

Run: `git diff --check`

Run: `git status --short`

Expected: no whitespace errors, no `.env`, database, cache, or container output newly added.
