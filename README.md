# Kerben Travel

Backend API and AI travel assistant for the Kerben Travel website. The repository and some runtime identifiers still use the legacy name `Kyrgyz_Go`/`KYRGYZGO`; those names are kept in commands, image names, environment settings, and API responses for compatibility.

## What is included

- FastAPI HTTP API and authenticated WebSocket chat.
- Gemini-powered travel assistant that reads the active catalogue and can prepare a travel request.
- PostgreSQL persistence with Alembic migrations.
- SQLAdmin interface for catalogue and request management.
- Docker Compose setup for the API, optional Caddy HTTPS proxy, and persistent media uploads.

This repository contains the backend, not the website frontend. GitHub Actions runs checks and tests; it does not deploy to a server.

## Run locally with Docker

Requirements: Docker Desktop with Compose, PostgreSQL reachable from the API container, and a Gemini API key for real AI responses.

1. Create `.env` from the example and set `DATABASE_URL`, a strong `SECRET_KEY`, and `GEMINI_API_KEY`. Keep `.env` local; never commit it.

   ```powershell
   Copy-Item .env.example .env
   ```

2. Start the API:

   ```powershell
   docker compose config --quiet
   docker compose up --build -d
   docker compose ps
   docker compose logs --tail=100 api
   ```

3. Open `http://127.0.0.1:8000/docs`. `GET /` is only an HTTP liveness check; it does not verify database or Gemini connectivity. If `GEMINI_API_KEY` is missing or invalid, the API can start but AI chat requests will fail.

Compose applies Alembic migrations on API startup. PostgreSQL is external to the Compose stack; configure a reachable database before starting the service.

## Run locally without Docker

Use Python 3.12 or newer and a reachable PostgreSQL database. Install dependencies, configure `.env`, apply migrations, and start Uvicorn:

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## Checks

Install development dependencies with `python -m pip install -r requirements-dev.txt`. The full suite uses a disposable PostgreSQL service in Docker unless `TEST_DATABASE_URL` points to a dedicated test database with `CREATEDB` permission.

```powershell
python -m scripts.run_tests -q
ruff check .
python -m scripts.format_code --check
```

## Local monitoring and load smoke

`GET /metrics` is disabled until `METRICS_BEARER_TOKEN` is set to a generated
secret of at least 32 characters. Use `Authorization: Bearer <token>` to scrape.
The output contains aggregate operation and latency values, not chat text or
identifiers.

The local WebSocket/PostgreSQL load harness creates and drops a uniquely named
temporary database. Point it at a local PostgreSQL account with `CREATEDB`:

```powershell
$env:LOAD_TEST_DATABASE_URL = "postgresql+psycopg2://test_user:password@127.0.0.1:5432/postgres"
python -m scripts.load_test --users 4 --messages 2
```

Gemini is stubbed by default. A live run requires both `--live-gemini` and
`LOAD_TEST_ALLOW_LIVE_GEMINI=true`, and is limited to one user, one message, and
eight provider calls. Never point the harness at a deployed host or application
database.

See [API.md](API.md) for the HTTP and WebSocket contract, [DEPLOY.md](DEPLOY.md) for deployment configuration, and [docs/README.md](docs/README.md) for the documentation index. Production updates itself: every green commit on `main` is deployed with its migrations within 2-3 minutes; read «Перед мержем в main» in [DEPLOY.md](DEPLOY.md) before merging.
