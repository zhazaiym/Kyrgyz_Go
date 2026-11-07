# Client Travel Requests Implementation Plan

> **For agentic workers:** Execute inline in this session, one task at a time with review checkpoints. Steps use checkbox syntax for tracking.

**Goal:** Let an authenticated client submit a request from their saved selection, list their own requests, and cancel without deleting request history.

**Architecture:** Link requests to clients and (for direct submissions) to one selection. Enforce a single request per selection with a nullable unique foreign key. Reuse existing service snapshot validation, request status rules, and admin notification publisher.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, PostgreSQL, existing admin WebSocket.

## Global Constraints

- Direct request creation requires a bearer-authenticated client and a selection owned by that client.
- Request service names/IDs are resolved from current active catalogue rows on the server.
- A selection can create at most one request; creation and selection status change are atomic.
- Cancellation sets status to `cancelled`; it never deletes the request and completed requests cannot be cancelled.
- Existing chat booking requests continue to work; their client ownership is backfilled from `ChatBookingLink` where possible.
- New request notifications are published only after commit.
- Write and observe failing behavior tests before production code; use the isolated PostgreSQL test environment.

---

### Task 1: Add request ownership and selection linkage migration

**Files:**
- Modify: `mysite/database/models.py`
- Create: `alembic/versions/20261103_0022_client_travel_requests.py`
- Test: `tests/test_client_travel_requests.py`

**Interfaces:**
- Add nullable `TravelRequest.client_id` FK to `chat_clients.id`.
- Add nullable `TravelRequest.selection_id` FK to `travel_selections.id` with a unique constraint; null is allowed for legacy/chat requests.

- [ ] Write `test_request_selection_link_is_unique_and_legacy_nullable` to prove one linked request per selection and multiple legacy null links are allowed.
- [ ] Run the test and confirm it fails on the absent columns/constraint.
- [ ] Add model columns and migration `20261103_0022` after `20261103_0021` (the reviews migration); backfill `client_id` from `chat_booking_links` before leaving legacy rows nullable.
- [ ] Add downgrade dropping constraints/indexes/columns in reverse order.
- [ ] Run the focused migration test and `alembic upgrade head` against the isolated test DB.

### Task 2: Implement direct request creation

**Files:**
- Modify: `mysite/api/travel_request.py`
- Modify: `mysite/api/selected_services.py` only if an existing helper needs a narrow extension.
- Modify: `mysite/api/travel_selection.py`
- Test: `tests/test_client_travel_requests.py`

**Interfaces:**
- `POST /travel-requests/` accepts `{selection_id, travel_date, travelers_count, phone, message?}` and returns `TravelRequestOutSchema` with 201.
- `TravelSelection.status` becomes `in_progress` after submission; selection detail/list includes the new request ID and status.

- [ ] Add failing tests for unauthenticated 401, successful authenticated submission, foreign selection 404, empty/invalid selection rejection, inactive service rejection, and duplicate submission 409.
- [ ] Run these tests and confirm they fail because POST is currently disabled.
- [ ] Add a Pydantic request schema: positive selection ID and travelers count, phone 7–25 characters, optional message bounded to 2000, and date not before today.
- [ ] Resolve the client's name from `ClientProfile.name` or username fallback and email from `ChatClient.email`; allow the submitted phone to override the saved phone.
- [ ] Lock the selection row, verify owner and `status == 'draft'`, use `selected_services(db, state)` to verify active services and create the trusted service snapshot, insert request with client/selection IDs, set selection status to `in_progress`, then commit once. Catch unique conflicts and return 409.
- [ ] Extend `selection_context`/`requests_for_selections` so direct `selection_id` links and existing `ChatBookingLink` links both resolve request ID/status. Preserve session-based chat behavior.
- [ ] Re-run the focused tests and existing travel selection tests; verify repeat requests are blocked after concurrent submissions.

### Task 3: Add client request listing and cancellation

**Files:**
- Modify: `mysite/api/travel_request.py`
- Test: `tests/test_client_travel_requests.py`

**Interfaces:**
- `GET /travel-requests/me/` returns only the caller's rows newest first, paginated by the existing `Pagination` dependency.
- `DELETE /travel-requests/me/{request_id}/` changes status to `cancelled` and returns the updated request.

- [ ] Add failing tests for list scoping, missing/foreign request 404, successful cancellation, idempotent repeat cancellation, and completed request 409.
- [ ] Run the tests and confirm routes are missing.
- [ ] Add the static `/me/` route before `/{request_id}/`; add the cancel route with row locking, owner filtering, and `require_status_transition` validation.
- [ ] Re-run tests; verify cancellation leaves the row and admin list still sees it.

### Task 4: Notify admins and document API

**Files:**
- Modify: `mysite/api/travel_request.py`
- Modify: `API.md`
- Create: `tests/test_api_contract_docs.py`
- Test: `tests/test_client_travel_requests.py`

- [ ] Add a failing test that subscribes to the existing publisher hook and asserts the direct request ID is published only after successful commit; assert failed requests publish nothing.
- [ ] Import `publish_new_request` and invoke it after commit; do not introduce another notification channel or frontend polling protocol.
- [ ] Add contract assertions in `tests/test_api_contract_docs.py`; document POST/list/cancel shapes, ownership, status codes, one-request-per-selection, and the existing admin WebSocket event.
- [ ] Run `pytest tests/test_client_travel_requests.py tests/test_main_regressions.py tests/test_api_contract_docs.py -q`, `ruff check mysite/api/travel_request.py mysite/api/travel_selection.py mysite/database/models.py`, and `git diff --check`.
- [ ] Confirm chat confirmation regression tests still pass and document any environment blocker without claiming unrun checks passed.
