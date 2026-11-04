# Repository cleanup design

## Goal

Remove the confirmed inactive root `migrations/` scaffold without changing the active Alembic migration chain or deleting repository snapshots, databases, test artifacts, or package markers.

## Evidence

- `alembic.ini` sets `script_location = %(here)s/alembic`.
- The root `migrations/` folder contains only a README, a default Alembic `env.py` with `target_metadata = None`, and a template; it has no `versions/` directory.
- No runtime, deployment, or project configuration references this root folder.
- The configured `alembic/` folder contains the active migration environment and version history.

## Design

- Delete only `migrations/README`, `migrations/env.py`, and `migrations/script.py.mako`, then remove the empty `migrations/` directory.
- Preserve all exact duplicate package `__init__.py` files because each marks a distinct Python package.
- Preserve Alembic migration helper duplicates because migration revisions are historical records.
- Preserve `.chat-deploy`, `.ml-test-tmp`, database files, archives, patches, snapshots, and temporary deployment directories.
- Do not edit Alembic configuration, active migration files, application code, or deployment files.

## Verification

Confirm `alembic.ini` still points to `alembic/`, `alembic/versions/` remains intact, `ruff check .` and Python compilation succeed, and `git diff --check` reports no whitespace errors. Do not run pytest in this cleanup because the user deferred tests and Docker/PostgreSQL are unavailable.

## Limits

This cleanup does not prove application behavior; functional tests remain pending. The environment has read-only Git metadata, so the deletion can appear in the working tree but cannot be committed here.
