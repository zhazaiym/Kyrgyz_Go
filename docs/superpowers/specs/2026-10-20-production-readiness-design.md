# KYRGYZGO production readiness design

## Goal

Prepare the existing FastAPI backend for deployment without adding product
features or unnecessarily changing the frontend API contract.

## Scope

- Make dependency installation reproducible on a clean server.
- Configure the database from environment variables, with the current SQLite
  database remaining the local default.
- Repair Alembic configuration and add migrations for the current schema.
- Keep public catalogue reads and public form submissions available.
- Require administrator authentication for catalogue writes and access to
  private customer data.
- Protect the SQLAdmin interface with the existing administrator credentials.
- Verify application startup, OpenAPI generation, CRUD behavior,
  authentication, chat authentication, booking confirmation, and AI-provider
  configuration.

## API access policy

Public access:

- Read-only catalogue endpoints.
- Creating contact messages and travel requests.
- Chat registration, login, owned sessions, and owned history.

Administrator access:

- Creating, updating, translating, and deleting catalogue records.
- Listing, reading, updating, and deleting contacts and travel requests.
- SQLAdmin pages.

Existing route paths and response shapes will be preserved unless a confirmed
runtime defect makes that impossible.

## Configuration and database

`mysite.database.db` will be the single source for `DATABASE_URL`. It will read
the value from the environment and fall back to the current local SQLite URL.
SQLite-only connection arguments will be applied only to SQLite connections.
Alembic will import this resolved URL and all model modules so migration
metadata is complete.

The current database file will not be deleted or reset. A migration will bring
a deployed database from the repository schema to the current model schema.

## Authentication

The existing administrator JWT dependency will be reused by protected API
handlers. SQLAdmin will use an authentication backend backed by the same Admin
table and password hashing. No second administrator account system will be
introduced.

Authentication failures will return 401 or 403 without exposing credentials or
internal exception details.

## Dependencies and deployment

A pinned dependency manifest will be generated from imports actually required
by this application, not from unrelated packages installed globally. The
documented server command will run Uvicorn without development reload.

Secrets and environment-specific values remain outside Git. An `.env.example`
will document required variable names with non-secret placeholders.

## Verification

Tests will use an isolated temporary database and will not modify
`kyrgyzgo.db`. Verification will cover:

- import, mapper configuration, and application startup;
- Alembic upgrade on an empty temporary database;
- public reads and public submissions;
- rejection of unauthenticated protected operations;
- administrator login and authorized operations;
- chat registration/login, ownership boundaries, and booking idempotency;
- OpenAPI generation and representative HTTP smoke tests;
- AI configuration/import, with a live Gemini request performed only when it
  can be done safely and without exposing keys.

## Non-goals

- No frontend implementation.
- No new business features.
- No renaming or redesign of the API.
- No Docker, CI pipeline, or PostgreSQL migration unless the target hosting
  environment later requires them.
