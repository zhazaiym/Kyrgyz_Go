# Repository Cleanup Implementation Plan

> **For agentic workers:** Execute inline in this session. Steps use checkbox syntax for tracking.

**Goal:** Remove only the inactive root Alembic scaffold named `migrations/`.

**Architecture:** Keep the configured `alembic/` migration system unchanged. Remove the three tracked files in the unused root `migrations/` directory and verify repository structure and static checks.

**Tech Stack:** Git, Alembic configuration, Ruff, Python compileall.

## Global Constraints

- Do not modify `alembic.ini` or any path under `alembic/`.
- Preserve `.chat-deploy`, `.ml-test-tmp`, all database files, archives, snapshots, package `__init__.py` files, and temporary deployment data.
- Do not run pytest; the user deferred test execution.
- Do not commit or push because `.git` is read-only in this workspace.

---

### Task 1: Remove the inactive scaffold

**Files:**
- Delete: `migrations/README`
- Delete: `migrations/env.py`
- Delete: `migrations/script.py.mako`

- [ ] Confirm `alembic.ini` still points to `alembic/`, and `migrations/` has no version scripts.
- [ ] Delete only the three listed files and the resulting empty `migrations/` directory.

### Task 2: Verify repository structure

**Files:**
- Verify: `alembic.ini`
- Verify: `alembic/env.py`
- Verify: `alembic/versions/`

- [ ] Confirm the active Alembic path and version history remain present.
- [ ] Run `ruff check .`, `python -m compileall -q main.py mysite ML scripts tests alembic`, and `git diff --check`.
- [ ] Confirm `git status --short -- migrations` lists only the intended three deletions; do not run tests or alter other dirty files.
