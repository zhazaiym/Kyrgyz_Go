# Client Authentication and Frontend Configuration Implementation Plan

> **For agentic workers:** Execute inline in this session, one task at a time with review checkpoints. Steps use checkbox syntax for tracking.

**Goal:** Clarify the shared client login contract, configure reset links for the Vercel frontend, and allow its HTTP API and chat WebSocket origins.

**Architecture:** Keep both existing client login endpoints and token format. Change only deployment configuration/documentation for reset URL, HTTP CORS, and chat WebSocket origins. Preserve same-origin, session-authenticated admin WebSocket behavior.

**Tech Stack:** Python, FastAPI, Pydantic, Starlette CORS, SMTP, environment configuration, pytest.

## Global Constraints

- Both login endpoints authenticate the same `ChatClient` records; access tokens expire after seven days and no refresh token is issued.
- Password reset tokens remain hashed at rest and valid for 15 minutes.
- Reset URL is exactly `https://tours-app-teal.vercel.app/ru/reset-password`; the mail builder appends the URL-encoded `token` parameter.
- HTTP CORS and chat WebSocket allow the exact origin `https://tours-app-teal.vercel.app`; never use wildcard origins.
- Keep the admin notification WebSocket same-origin to SQLAdmin and preserve admin session/active-admin checks.
- Configuration changes do not prove SMTP credentials work or imply a production deployment has occurred.

---

### Task 1: Prove and document the shared login contract

**Files:**
- Modify: `API.md`
- Test: `tests/test_client_auth_contract.py`

**Interfaces:**
- `/auth/login` returns `access_token`, `token_type`, client ID/code, username, and email.
- `/account/login` uses the same account identity and adds profile name/phone.

- [ ] Add a failing test that registers a client, authenticates the same account through `/account/login`, and confirms both responses issue valid bearer tokens for the same client ID.
- [ ] Run the test and confirm account identity or documented response expectations fail if mismatched.
- [ ] Add assertions for each endpoint's response fields, token validity, and that no `refresh_token` field is returned.
- [ ] Document identifier differences (username/email versus email), shared account storage, seven-day token expiry, logout/revoke behavior, and absence of refresh token in `API.md`.
- [ ] Run the focused test and existing auth tests.

### Task 2: Verify and configure password reset URL

**Files:**
- Modify: `.env.example`
- Modify: `DEPLOY.md`
- Modify: `API.md`
- Test: `tests/test_password_reset_config.py`

**Interfaces:**
- `.env`: `FRONTEND_RESET_URL=https://tours-app-teal.vercel.app/ru/reset-password`.
- Email link: `https://tours-app-teal.vercel.app/ru/reset-password?token=<encoded token>`.

- [ ] Add a failing unit test for `send_reset_email` that stubs SMTP transport, captures the message body, and expects the exact Vercel reset URL with URL-encoded token.
- [ ] Run the test and confirm it fails under the placeholder URL configuration.
- [ ] Update `.env.example` and deployment instructions to use the exact frontend URL and explain required `SMTP_HOST`/`SMTP_FROM` plus optional credentials and port behavior.
- [ ] Assert reset token expiry remains 15 minutes and token persistence stores only the digest; add no changes to that policy.
- [ ] Run focused password reset tests and inspect the generated email content without sending real email.

### Task 3: Configure frontend HTTP and chat WebSocket origins

**Files:**
- Modify: `.env.example`
- Modify: `DEPLOY.md`
- Test: `tests/test_frontend_origins.py`

**Interfaces:**
- `CORS_ALLOWED_ORIGINS` includes `https://tours-app-teal.vercel.app`.
- `CHAT_ALLOWED_ORIGINS` includes `https://tours-app-teal.vercel.app`.
- Admin notification socket remains same-origin and session authenticated.

- [ ] Add failing tests that set the Vercel origin and confirm the CORS preflight includes the exact allowed origin, while an unrelated origin is denied.
- [ ] Add a chat WebSocket handshake test that accepts the Vercel origin and rejects an unrelated origin before session work begins.
- [ ] Run focused tests and confirm they fail with current environment defaults.
- [ ] Add the Vercel origin to both semicolon-separated example settings and the deployment instructions, retaining existing explicitly trusted origins and no wildcard.
- [ ] Re-run focused tests. Ensure the admin WebSocket test still rejects cross-origin access and accepts same-origin authenticated admin sessions.

### Task 4: Verify documentation and deployment readiness

**Files:**
- Modify: `API.md`
- Modify: `DEPLOY.md`
- Test: `tests/test_api_contract_docs.py`, relevant configuration tests.

- [ ] Add OpenAPI login and reset response assertions to `tests/test_api_contract_docs.py`; compare them with `API.md` and fix documented field/path mismatches.
- [ ] Run `pytest tests/test_client_auth_contract.py tests/test_password_reset_config.py tests/test_frontend_origins.py tests/test_api_contract_docs.py -q`, `ruff check main.py mysite/api/client_auth.py mysite/api/password_reset.py mysite/admin/realtime.py`, and `git diff --check`.
- [ ] Inspect production configuration only after a verified backup and safe disk headroom are available. Set the Vercel URL/origins through the deployment's supported environment mechanism and verify running container configuration after restart.
- [ ] Do not delete Docker data, change live TLS/DNS, or deploy migrations while production root disk has no free space. A custom API hostname and its TLS certificate require a domain controlled by the user; the Vercel frontend URL alone is not an API hostname.
