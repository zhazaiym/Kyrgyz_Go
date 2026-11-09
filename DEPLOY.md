# Deployment and administrator access

The current server updates tested revisions of `main` itself. GitHub Actions only
checks code and the runtime image. The retired workstation scripts and old CI
deployment job have been removed. Submit changes through a PR: merging `main`
starts the server's existing deployment process.

## Configuration and media

Copy `.env.example` for local development. PostgreSQL and a random `SECRET_KEY`
of at least 32 bytes are required. Never commit real credentials.
Set `API_DOMAIN` to the current server/domain; Compose refuses an empty value.
Caddy is pinned to `2.11.9-alpine`. It serves the media volume read only at
`/media/` with immutable one-year caching. Compose defaults to disabling Uvicorn's
media mount; `.env.example` explicitly enables it for local development with
`SERVE_MEDIA_LOCALLY=true`.

Uploads return `/media/YYYY/MM/<uuid>.webp`. Resolve these paths against the API
base URL. A migration removes old hosts from `/media/` references in every image
column. External catalogue images keep their external sources.

## Administrator login

API and SQLAdmin login require an active administrator account and its password.
Administrator MFA is no longer enforced; `ADMIN_MFA_REQUIRED` and old TOTP fields
do not enable a second factor. Historical MFA data and utility scripts remain for
compatibility and are not part of the login flow.

Create a password-based account with:

```sh
docker compose exec api python create_admin.py
```

Role checks, login rate limits and revocable sessions remain enabled. Password
changes and account deactivation revoke existing sessions and trusted devices.

## Sessions and trusted browsers

Password is always required. Login with `remember_device=true` issues a
30-day device token; at most ten devices are kept, revoking the oldest first.
API login preserves the existing response fields and adds refresh metadata.
Refresh rotates tokens, accepts the previous token for 30 seconds, expires after
30 unused days and has an absolute 90-day limit. Only token hashes are stored.
Authenticated refresh envelopes and keyed rotation reproduce the same replacement
pair across workers during the grace period without recoverable tokens in the DB.
Reusing an older issued refresh outside that window revokes its session.

SQLAdmin sessions expire after seven idle days, renew on active HTTP use every
ten minutes and require login after 30 days. Logout revokes the session and keeps
browser trust. **Забыть этот браузер** revokes trust separately. Owner-only SQLAdmin
sections list all sessions/devices and allow revocation; API endpoints list/revoke
only the caller's own records.

| Setting | Backend rollout default |
| --- | --- |
| `ADMIN_ACCESS_TOKEN_MINUTES` | `60` until the admin frontend supports refresh |
| `ADMIN_REFRESH_DAYS` | `30` |
| `ADMIN_SESSION_HOURS` | `168` |
| `ADMIN_TRUSTED_DEVICE_DAYS` | `30` |
| `ADMIN_MAX_TRUSTED_DEVICES` | `10` |
| `GEMINI_REQUESTS_PER_MINUTE` | `10` shared translation calls |

Set `ADMIN_ACCESS_TOKEN_MINUTES=15` after the new Vercel frontend ships. Keep 60
during this backend-only rollout. Notify the reviewer of these settings before
merging. This change does not edit the production `.env` or operate the server.

## Translation recovery

Temporary `ai_unavailable`, `ai_rate_limit` and `ai_timeout` errors remain pending
with exponential backoff capped at one hour. Retry delays do not occupy workers.
Due persisted jobs are dispatched continuously; catalogue recovery runs at startup
and every 15 minutes. Old failed rows with a temporary code, or the old ambiguous
`failed` diagnostic, automatically become eligible again. Permanent invalid or
blocked responses stop after three attempts until the source changes. Logs and
`translation_jobs.last_error` retain the error code.

Translation quota is reserved atomically in PostgreSQL across workers before a
provider call. Set `GEMINI_REQUESTS_PER_MINUTE` to the actual key's quota. After
deploying recovery, no manual SQL reset is needed when provider access returns.

## Checks before a PR

For a fictional local catalogue, use a loopback PostgreSQL database named
`kyrgyzgo_dev` (or `kyrgyzgo_dev_*`), apply migrations and run
`python -m scripts.seed_dev`. The command is repeatable and refuses remote or
non-development databases. It creates no client accounts and imports no production data.

Use a clean checkout without `.env` and disposable PostgreSQL test databases:

```sh
python -m scripts.format_code --check
python -m scripts.run_tests -q
python -m pytest --confcutdir=tests/ml tests/ml -q
python -m pytest --confcutdir=tests/unit tests/unit -q
```

CI also checks syntax, Ruff, security and dependencies, builds the runtime image
and checks the historical MFA utility entry point inside that image. This build
check does not enable MFA or make enrollment a deployment requirement.
Post-deployment verification is performed by the server operator.
