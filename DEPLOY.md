# KYRGYZGO deployment

## Docker + external PostgreSQL

The project includes a FastAPI API, SQLAlchemy/psycopg2 database access,
Alembic migrations, SQLAdmin, and an optional Gemini-powered chat. Docker
Compose runs only the API. PostgreSQL remains on your host or database server.

Required on the server: Docker Engine with the Compose plugin, access to
PostgreSQL, and an HTTPS reverse proxy (for example Nginx). Python and Postman
are not required on the host for Docker deployment. Docker Desktop is suitable
for local Windows development; it must be running to build or start containers.

### Environment and database

On a new server, copy `.env.example` to `.env`. Keep your existing `.env` if
already configured. Set a long random `SECRET_KEY` and real database credentials.
The image excludes `.env` and local database files; Compose injects the runtime
environment with `env_file`.

Database addressing:

- PostgreSQL on the same computer as Docker: use
  `postgresql+psycopg2://app_user:password@host.docker.internal:5432/kyrgyzgo_db`.
  Compose provides this hostname on Linux as well. `127.0.0.1` inside the API
  container refers to that container, not your host PostgreSQL server.
- PostgreSQL on another computer: replace `host.docker.internal` with its
  private IP or DNS name. The database must accept connections from the Docker
  host. Configure PostgreSQL `listen_addresses`, `pg_hba.conf`, and the firewall
  for the actual client network; keep port 5432 restricted to trusted clients.
- Without Docker: the current `127.0.0.1` URL is correct for a local PostgreSQL
  server. URL-encode special characters in database credentials.

Set the exact frontend origins (scheme, hostname, and port, no trailing slash):

```dotenv
CORS_ALLOWED_ORIGINS=https://your-frontend.example
CHAT_ALLOWED_ORIGINS=https://your-frontend.example
```

Multiple origins are separated by `;`. The example file includes localhost
ports 3000 and 5173. Replace them with the production frontend origins on the
server. HTTP CORS accepts the `Authorization` header and preflight requests.
WebSockets use their own origin check through `CHAT_ALLOWED_ORIGINS`.
Do not set `*` for CORS origins when using credentials.

Back up an existing database before deployment. Every API container start runs
`alembic upgrade head` and starts Uvicorn only if migrations succeed. A database
created outside Alembic needs its schema reviewed and baselined first; do not
blindly stamp a populated PostgreSQL database. The legacy SQLite procedure is
documented below. Do not scale this service to multiple replicas without moving
migrations to a separate deployment step and reviewing chat session locking.

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

Create an administrator interactively after the API starts:

```bash
docker compose exec api python create_admin.py
```

For updates, back up PostgreSQL, update the source, then run
`docker compose up --build -d`. Stop the API with `docker compose down`.
Neither command manages the external PostgreSQL server. The Docker configuration
requires an external PostgreSQL database; it does not persist a container-local
SQLite database.

### HTTPS on a Linux server

The API port binds to `127.0.0.1:8000` by default. Put a host Nginx instance
in front of it, configure DNS and a valid TLS certificate for the API domain,
and expose only the HTTPS proxy publicly. Set `FORWARDED_ALLOW_IPS=*` in the
server `.env` only while the API is reachable exclusively through your trusted
proxy; this allows Uvicorn to recognize the forwarded HTTPS scheme over Docker
networking. Do not combine that setting with a publicly accessible API port.

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

The repository currently contains a legacy SQLite database created before
Alembic. If deploying that existing file, back it up first, mark its current
schema as the baseline revision, and then apply later migrations:

```bash
python -m alembic stamp 15eb0352f12a
python -m alembic upgrade head
```

Do not run `stamp` against an empty database. For a database that already has
an `alembic_version` table, run only `python -m alembic upgrade head`.

## 3. Create an administrator

```bash
python create_admin.py
```

The same administrator can use the bearer-token API and the SQLAdmin login.

## 4. Run

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Run one worker when using SQLite. Put the service behind an HTTPS reverse proxy
and keep `.env` and `kyrgyzgo.db` outside publicly served directories. The API
documentation is available at `/docs`.
