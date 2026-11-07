# Kerben Travel backend deployment

## Docker + external PostgreSQL

The project includes a FastAPI API, SQLAlchemy/psycopg2 database access,
Alembic migrations, SQLAdmin, and a Gemini-powered AI chat. Docker
Compose runs only the API. PostgreSQL remains on your host or database server.

The AI model is called through Google's Gemini API; there is no separate AI
container. Set a valid `GEMINI_API_KEY` in the API environment for chat replies.
The WebSocket greeting and HTTP healthcheck do not verify Gemini. Without a
working key, a connected chat can still return `ai_unavailable` after a message.

Required on the server: Docker Engine with the Compose plugin, access to
PostgreSQL, and an HTTPS reverse proxy (for example Nginx). Python and Postman
are not required on the host for Docker deployment. Docker Desktop is suitable
for local Windows development; it must be running to build or start containers.

### Environment and database

On a new server, copy `.env.example` to `.env`. Keep your existing `.env` if
already configured. Set a long random `SECRET_KEY` and real database credentials.
The image excludes `.env` and local database files; Compose injects the runtime
environment with `env_file`.

Admin cookies are Secure by default. For local HTTP development explicitly
set `ADMIN_COOKIE_SECURE=false`; keep it true for production HTTPS.
Admin sessions do not expire on a timer; the login is cleared by the admin
logout action. Browsers may discard a session cookie when the browser closes.

The admin panel and admin API require a password and TOTP MFA, or a single-use
recovery code. For an existing deployment, apply the MFA migration during a
maintenance window, enroll every active admin from a trusted local shell, and
only then reopen admin access:

```powershell
python -m scripts.enroll_admin_mfa admin-username
```

The command displays a one-time authenticator secret, verifies a current code,
then stores the TOTP secret encrypted with a key derived from `SECRET_KEY` and
stores only hashes of recovery codes. Keep `SECRET_KEY` stable; rotating it
requires re-enrolling administrators. The login limiter permits at most
**20 attempts/minute per source IP** and **5 attempts/minute for each
account/IP pair**. Use HTTPS in production.

If an enrolled account loses its device and recovery codes, an active owner can
authorize a reset from a trusted shell with
`python -m scripts.enroll_admin_mfa target-username --reset-by owner-username`;
the command verifies the owner's password and MFA before replacing the target's
MFA secret.

There are three server-enforced roles: `owner` manages all data and admins,
`manager` manages travel requests and selections, and `catalog_editor` manages
catalogue and public content. Existing accounts migrate as `owner`; assign
least-privilege roles through SQLAdmin after an owner has enrolled.
The trusted deployment helper also requires a valid `ADMIN_ALLOWED_IPS` value
in the resolved server Compose configuration. The application middleware
currently does not enforce that value at request time; use a firewall or
reverse-proxy rule if admin routes must be restricted by network.

### About page content

The About page uses one `About` record and ordered `AboutSection` records. Each
slide's title, Russian description, and photo URL are returned by
`GET /about-sections/?lang=ru`; the introductory title is returned by
`GET /abouts/?lang=ru`. The frontend must render `AboutSection.image` to show
the per-slide photos. This backend repository does not include the frontend
layout.

### Homepage copy

The public endpoint `GET /home/content/?lang=ru` returns the homepage title and
supporting copy. It supports `ru`, `en`, `de`, and `zh`. The frontend must fetch
this endpoint and render its `title`, `description`, `details`, and `promise`
fields for the copy to appear on the homepage.

To replace all existing About content, first run
`python -m scripts.replace_about_content` to review the current and new row
counts. Then run it with `--apply --backup /path/to/new/about-backup.json`.
The command refuses to overwrite a backup, writes the old About rows before
the database transaction, replaces the rows atomically, and queues translations
to English, German, and Chinese using the existing worker. No schema migration
is needed.

The deployment helper carries the existing Compose environment into its
generated `/home/ubuntu/kyrgyzgo-deploy.override.yml`.

Database addressing:

- PostgreSQL on the same computer as Docker: use
  `postgresql+psycopg2://app_user:password@host.docker.internal:5432/kyrgyzgo_db`.
  Compose provides this hostname on Linux as well. `127.0.0.1` inside the API
  container refers to that container, not your host PostgreSQL server.
- PostgreSQL on another computer: replace `host.docker.internal` with its
  private IP or DNS name. The database must accept connections from the Docker
  host. Configure PostgreSQL `listen_addresses`, `pg_hba.conf`, and the firewall
  for the actual client network; keep port 5432 restricted to trusted clients.
- Without Docker: use the commented `127.0.0.1` URL for a local PostgreSQL
  server. URL-encode special characters in database credentials.

Set the exact frontend origins (scheme, hostname, and port, no trailing slash):

```dotenv
CORS_ALLOWED_ORIGINS=https://kyrgyzgo-admin.vercel.app;https://tours-app-teal.vercel.app
CHAT_ALLOWED_ORIGINS=https://kyrgyzgo-admin.vercel.app;https://tours-app-teal.vercel.app
FRONTEND_RESET_URL=https://tours-app-teal.vercel.app/ru/reset-password
```

Multiple origins are separated by `;`. The example file includes the admin
Vercel origin and localhost ports 3000 and 5173. Add the production site origins
on the server. HTTP CORS accepts the `Authorization` header and preflight requests.
Chat WebSockets use their own origin check through `CHAT_ALLOWED_ORIGINS`. The admin
request notification socket stays on the same origin as SQLAdmin and requires its
authenticated admin session. Reset emails use `FRONTEND_RESET_URL` and include a
single-use token that expires after 15 minutes. SMTP settings must also be valid for
delivery; the HTTP forgot-password response does not confirm that a message arrived.
Do not set `*` for CORS origins when using credentials.

The Vercel URL above is the frontend, not an API hostname. To use a custom API domain
and certificate, point a DNS A record for a domain you control to this server and set
`API_DOMAIN` to that hostname. Keep enough free disk space for Caddy's certificate
renewal and take a verified PostgreSQL backup before applying migrations.

Back up an existing database before deployment. Every API container start runs
`alembic upgrade head` and starts Uvicorn only if migrations succeed. A database
created outside Alembic needs its schema reviewed and baselined first; do not
blindly stamp a populated PostgreSQL database. PostgreSQL is required in all environments. Do not scale this service to multiple replicas without moving
migrations to a separate deployment step.

GitHub Actions runs checks and tests by default. An opt-in `deploy` job is
prepared locally but remains disabled unless the repository variable
`DEPLOY_ENABLED` is exactly `true`. It runs only after successful tests on a
push to `main`; see [automatic deployment](docs/automatic-deployment.md) for
the required target, verified host keys and secrets. No production rollout
has been confirmed by the local checks.
Production updates can also be started manually by an administrator using
`scripts/deploy.ps1` from a workstation or the server's documented Docker
commands. The trusted server-side deploy script compares the current database
revision with the candidate source and reports `migration_required` before
replacing the running image if they differ. Back up the database, review and
apply the required migrations from the candidate source with
`python -m alembic upgrade head`, then deploy the matching image. The current
source migration head is `20261107_0024`; revisions `20261030_0018` through
`20261030_0020` replace and repopulate FAQ content, `20261103_0021` adds tour
reviews, `20261103_0022` adds client-owned travel requests, `20261107_0023`
adds admin MFA/roles, and `20261107_0024` persists translation jobs. After
applying `20261107_0023`, enroll active admins using the command above before
reopening admin access. Do not assume the production
database is at a particular revision; check it before deployment. Although the
Docker image runs `alembic upgrade head` on startup, the guarded production
deploy flow requires schema changes to be applied as a backed-up maintenance
step first.
The opt-in job requires fresh `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS` secrets
in the `production` environment and a repository variable `DEPLOY_TARGET`.
Do not reuse historical server settings without verifying them. Keep
`DEPLOY_ENABLED` unset until the actual server and trusted helper are ready.
Pause catalogue writes through REST and SQLAdmin during a maintenance migration.
Activate the matching image after the migration and before reopening catalogue
writes.

### Uploaded photos

Admins upload JPEG, PNG or WEBP photos from the SQLAdmin forms or through
`POST /admin/media/`. The API stores them as WEBP in the `media` Compose volume
(`/app/media`, override with `MEDIA_ROOT`) and serves them from `/media/`; the
database keeps only the returned absolute URL. Back up the `media` volume together
with PostgreSQL: a database restore without it leaves broken photo links. URLs
include the API host, so a move to a new domain needs the stored URLs rewritten.
`MAX_IMAGE_UPLOAD_BYTES` limits one upload (default 10 MB).

### Start and verify

Run from the project directory:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api
curl --fail http://127.0.0.1:8000/
```

The container runs as an unprivileged user, uses one Uvicorn worker, rotates
logs, and restarts after process failures. The healthcheck verifies HTTP
availability; it does not verify PostgreSQL or Gemini connectivity. An unhealthy
status alone does not trigger Docker's restart policy.

Database-backed rate limits are enabled by default and shared across workers:
client registration is limited by IP/account, client and admin login by IP and
identifier, password-reset requests by IP/email, WebSocket handshakes by IP,
and AI messages by client account. The AI limit is 10 messages per minute and
300 per day per client. Counters store hashed identifiers and old windows are
cleaned automatically. Keep `RATE_LIMIT_ENABLED=true` in production.

The coarse HTTP/IP limit uses a bounded in-memory counter per worker, with no
PostgreSQL writes. GET/HEAD health checks and SQLAdmin static assets bypass
this counter; admission, header and body limits still apply. With N workers,
the coarse allowance can reach N times the configured value. Use the proxy
or an upstream service for network-level and cross-worker traffic limits.
Numeric resource settings are validated at startup; restart after changing them.

The coarse counter uses LRU eviction and groups IPv6 addresses by /64. Evicted
counters can restart; account/chat limits remain database-backed. Expired login
and reset tokens are cleaned hourly, retaining one day after expiry; active
tokens are not revoked. Manual cleanup: `python -m scripts.cleanup_tokens`.

Create an administrator interactively after the API starts:

```bash
docker compose exec api python create_admin.py
```

For manual updates, back up PostgreSQL, update the source, then run
`docker compose up --build -d` when the server can handle a build. Stop the API with `docker compose down`.
Neither command manages the external PostgreSQL server. The Docker configuration
requires an external PostgreSQL database.

### HTTPS on a Linux server

Alternatively, use the included Caddy proxy with automatic HTTPS:

1. Use your public IP (currently `13.53.40.37`), or point a domain's DNS A/AAAA
   records to the server. Allow inbound TCP ports 80 and 443. Stop any other
   service using these ports after checking how the current API is hosted.
2. Set `API_DOMAIN=13.53.40.37` (or your domain) and keep
   `FORWARDED_ALLOW_IPS=172.30.240.2` in `.env`, along with the real HTTPS frontend origins in `CORS_ALLOWED_ORIGINS`
   and `CHAT_ALLOWED_ORIGINS`. Keep `API_BIND_HOST=127.0.0.1` so the API port
   remains accessible only locally and through the proxy.
   Compose gives Caddy this fixed address on a dedicated proxy network. If
   `172.30.240.0/28` overlaps an existing network, change `PROXY_SUBNET`,
   `CADDY_PROXY_IP`, `API_PROXY_IP`, and `FORWARDED_ALLOW_IPS` together. Never set trust to `*`
   merely to make forwarded headers work.
3. Run `docker compose --profile https config --quiet`, then
   `docker compose --profile https up --build -d`.
4. Verify `https://13.53.40.37/` and `/contacts/` without authorization, using your
   domain instead if configured. Check the certificate without bypassing TLS verification.

The single `docker-compose.yml` includes an optional `https` profile. Without
that profile, only the API starts. With it, Caddy exposes ports 80/443 and
persists TLS certificates in Docker volumes; the API remains bound to localhost.
Continue to use `--profile https` for updates, or set `COMPOSE_PROFILES=https` in
the server `.env` to use plain `docker compose up --build -d`.
Caddy 2.10.1+ obtains and renews short-lived Let's Encrypt certificates
for public IPs and domains. The Caddyfile sets a default SNI for clients connecting
by IP. Keep the certificate volumes and proxy running so renewal is automatic.
See the [Caddy HTTPS guide](https://caddyserver.com/docs/quick-starts/https) and
[Let's Encrypt IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability).

Public catalogue GETs accept `?lang=ru|en|de|zh`; the default is Russian.
Translations are generated on content changes through the API or SQLAdmin and
stored in the database. If generation fails or a field has no translation, GET
returns the original text. Translation jobs are stored in PostgreSQL and retry
transient failures up to five times with backoff; stale source text is discarded.
The SQLAdmin `translations` JSON field also supports
manual translations, for example `{"en":{"question":"Question?","answer":"Answer."}}`.
Existing records need to be saved with changed source text or supplied manual
translations to populate their translations. Public GETs make no AI calls.

### Manual Nginx alternative

The API port binds to `127.0.0.1:8000` by default. Put a host Nginx instance
in front of it, configure DNS and a valid TLS certificate for the API domain,
and expose only the HTTPS proxy publicly. Set `FORWARDED_ALLOW_IPS` in the
server `.env` to the actual peer address of that proxy as seen by Uvicorn
(for a host proxy this may be a Docker bridge gateway). Determine that address
for your network rather than trusting `*` or every private address. The default
fixed Caddy address is intended for the included Compose proxy, not arbitrary
host Nginx setups.

Example Nginx configuration inside an existing TLS `server` block:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 240s;
    proxy_send_timeout 240s;
}
```

Configure CORS in the API; avoid adding duplicate CORS headers in Nginx.
Validate Nginx configuration with `nginx -t` before reloading it. The domain
and certificate must be configured on the target server before public use.

### Frontend connection

Customer registration and login use `/auth/register` and `/auth/login`.
Keep one customer token for both catalogue details and chat. Catalogue lists
return public summary cards; detailed objects, programs, galleries and chat
require the customer token. On HTTP 401, show the shared registration/login
screen and return to the requested page after login. See
`docs/shared-client-auth.md` for the frontend contract. Administrative tokens
remain separate and cannot be replaced with a customer token.

Use `https://your-api.example` as the frontend API base URL and
`wss://your-api.example/ws/chat/{session_id}` for chat WebSockets. OpenAPI is
available at `/openapi.json` and interactive documentation at `/docs`.
For protected HTTP endpoints send `Authorization: Bearer <access_token>`.
For chat WebSockets, send `{"type":"auth","token":"<access_token>"}`
as the first message after opening the connection.

Verify preflight using an origin present in `CORS_ALLOWED_ORIGINS`:

```bash
curl -i -X OPTIONS https://your-api.example/ \
  -H 'Origin: https://your-frontend.example' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: Authorization,Content-Type'
```

Expect HTTP 200 and `Access-Control-Allow-Origin` equal to the frontend origin.
For direct local network development, set `API_BIND_HOST=0.0.0.0` explicitly
and restrict access with your firewall. Change `API_PORT` if port 8000 is busy.

## Manual deployment without Docker

The application is a FastAPI backend. Run the commands below from the project
root with Python 3.12.

## 1. Install

```bash
python -m venv venv
```

Activate the environment and install the pinned dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Configure

Copy `.env.example` to `.env` and replace every placeholder. Use a long random
`SECRET_KEY`. Set both allowed-origin variables to the real HTTPS origin of the
frontend, without a trailing slash.

For PostgreSQL, set `DATABASE_URL` in the standard SQLAlchemy form, for example
`postgresql://user:password@database-host:5432/database-name`. The required
PostgreSQL driver is included in `requirements.txt`.

For a new empty database, apply the schema:

```bash
python -m alembic upgrade head
```

For an existing PostgreSQL database managed by this repository, run
`python -m alembic upgrade head`. The migration history has one unified head.
Back up the database before every schema update. Never stamp an unreviewed
schema or run downgrade against your working data.

## 3. Create an administrator

```bash
python create_admin.py
```

The same administrator can use the bearer-token API and the SQLAdmin login.

## 4. Run

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Put the service behind an HTTPS reverse proxy and keep `.env` and PostgreSQL
backups outside publicly served directories. The API
documentation is available at `/docs`.

## Tests with PostgreSQL

Use `python -m scripts.run_tests -q` for the full suite. Without
`TEST_DATABASE_URL`, it starts a disposable PostgreSQL 17 Compose service; with
the variable, it uses that explicitly selected PostgreSQL server. The test user
needs `CREATEDB`. Tests create randomly named `test_kyrgyzgo_*` databases, apply
Alembic migrations, and delete only those databases after completion. They do
not read `DATABASE_URL` or `.env`. CI starts its own PostgreSQL 17 service.

```bash
python -m pip install -r requirements-dev.txt
python -m scripts.run_tests -q
```

`DATABASE_URL` is mandatory. Unsupported database backends fail at startup.
# Monitoring

The Prometheus text endpoint is `GET /metrics`. It returns 404 unless
`METRICS_BEARER_TOKEN` is set to a random value of at least 32 characters.
Send it as `Authorization: Bearer <token>` and keep the token in the deployment
secret store. Metrics contain bounded operation/outcome labels and durations;
they do not include prompts, message text, account names, or session ids.
