# KYRGYZGO Docker and CORS design

## Goal

Package the existing FastAPI backend for repeatable Docker deployment and
allow the frontend to call it from explicitly configured origins.

## Container architecture

The repository will receive one application image and an app-only Compose
service. It will not create or own a PostgreSQL container because the project
uses the team's existing database. The application receives `DATABASE_URL`
and all secrets from `.env`; no credential is copied into the image.

The container will apply `alembic upgrade head` before starting Uvicorn. If
the PostgreSQL server runs on the same physical computer as Docker, its URL
must use `host.docker.internal` rather than `127.0.0.1`, because localhost
inside the container refers to the container itself. Compose will provide the
host-gateway mapping required for that hostname on Linux hosts as well.

## Docker files

- `Dockerfile` builds a Python 3.12 slim image, installs pinned dependencies,
  copies the application, runs as a non-root user, exposes port 8000, and
  starts migrations followed by Uvicorn.
- `compose.yaml` runs the API, imports `.env`, maps host port 8000, adds the
  database-host mapping, and defines an HTTP healthcheck.
- `.dockerignore` excludes Git data, virtual environments, caches, local
  databases, tests, secrets, and generated files from the image context.

## CORS

HTTP CORS continues to use the semicolon-separated
`CORS_ALLOWED_ORIGINS` environment variable. WebSocket origin checks continue
to use `CHAT_ALLOWED_ORIGINS`. `.env.example` and deployment documentation
will show localhost frontend origins and explain how to replace them with the
real HTTPS frontend domain. Wildcard origins will not be enabled because the
API permits credentials.

## Error handling and operations

Container startup will fail visibly if the database is unreachable or a
migration fails; Uvicorn must not start against an unprepared schema. The
healthcheck will call the public root endpoint without requiring the database.
Deployment instructions will distinguish a database on the Docker host from a
database on another machine and will not contain real secrets.

## Verification

Automated checks will validate the Dockerfile, Compose configuration, ignored
secret files, and CORS environment parsing. Verification will include the full
Python test suite, `docker compose config`, a Docker image build, and a live
container smoke test using an isolated SQLite database override so the team's
PostgreSQL data is never modified.

## Non-goals

- No PostgreSQL container or database copy.
- No changes to business endpoints or response formats.
- No frontend implementation.
- No real credentials committed to Git.
