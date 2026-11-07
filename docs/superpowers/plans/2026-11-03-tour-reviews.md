# Tour Reviews Implementation Plan

> **For agentic workers:** Execute inline in this session, one task at a time with review checkpoints. Steps use checkbox syntax for tracking.

**Goal:** Add public tour reviews, one authenticated review per client and tour, owner-only deletion, and aggregate ratings on tour cards.

**Architecture:** Store reviews in a dedicated SQLAlchemy model with database uniqueness on `(tour_id, client_id)`. Add public and authenticated routes in a focused router, include it under `/tours`, and join grouped rating aggregates into `/tours/` results without per-tour queries.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, PostgreSQL.

## Global Constraints

- Ratings are integers from 1 through 5; review text is 1 through 2000 characters.
- A client may have at most one review for a tour; the database constraint is authoritative.
- Public output contains display name, rating, text, and UTC creation time, never email.
- Tour list aggregate fields are `average_rating` (nullable, rounded to two decimals) and `review_count` (zero when empty).
- Keep existing tour filtering, localization, ordering, and pagination behavior.
- Write and observe a failing behavior test before production code; run tests only in the configured isolated PostgreSQL test environment.

---

### Task 1: Add the review model and migration

**Files:**
- Create: `mysite/database/tour_review_models.py`
- Modify: `alembic/env.py`
- Create: `alembic/versions/20261103_0021_tour_reviews.py`
- Test: `tests/test_tour_reviews.py`

**Interfaces:**
- Produces `TourReview(id, tour_id, client_id, display_name, rating, text, created_at)`.
- Database uniqueness constraint: `uq_tour_reviews_tour_client` on `(tour_id, client_id)`.

- [ ] Write `test_tour_review_unique_per_client_and_tour` that inserts a review and expects `IntegrityError` on a second insert for the same pair, while allowing another client or tour.
- [ ] Run `pytest tests/test_tour_reviews.py::test_tour_review_unique_per_client_and_tour -q`; confirm the expected missing model/table failure.
- [ ] Define the model with cascading foreign keys to tours and client accounts, UTC timestamp default, rating check constraint `rating BETWEEN 1 AND 5`, bounded text/display name columns, and a named unique constraint.
- [ ] Import the new module from Alembic `env.py`; create revision `20261103_0021` after `20261030_0020` with upgrade/downgrade for the table, index, and constraints.
- [ ] Re-run the focused test and migration upgrade/downgrade check; confirm both pass.

### Task 2: Add review request/response schemas and endpoints

**Files:**
- Create: `mysite/api/tour_reviews.py`
- Create: `mysite/database/tour_review_schema.py`
- Modify: `main.py`
- Test: `tests/test_tour_reviews.py`

**Interfaces:**
- `GET /tours/{tour_id}/reviews/` returns newest-first list of `{id, display_name, rating, text, created_at}` without authentication.
- `POST /tours/{tour_id}/reviews/` accepts `{rating, text}` and requires `current_client`.
- `DELETE /tours/{tour_id}/reviews/{review_id}/` deletes only the authenticated owner's review.

- [ ] Add failing route tests for public listing with no auth, non-existing tour 404, rating/text validation 422, duplicate review 409, and owner-only deletion (foreign/missing review returns 404).
- [ ] Run the five focused tests and confirm they fail because the routes/schemas are absent.
- [ ] Define Pydantic input and output schemas. Resolve the public display name from `ClientProfile.name`, falling back to `ChatClient.username`; do not serialize email.
- [ ] Implement list/create/delete using `get_db`, `current_client`, a tour existence/active check, stable `created_at DESC, id DESC` ordering, and database integrity handling for concurrent duplicate submissions.
- [ ] Register the router after the existing tour router so review routes are mounted at `/tours/{tour_id}/reviews/` and do not shadow tour detail routes.
- [ ] Re-run focused tests; verify anonymous GET succeeds and only the owning account can delete.

### Task 3: Add aggregate fields to tour cards

**Files:**
- Modify: `mysite/database/catalogue_schema.py`
- Modify: `mysite/api/tour.py`
- Test: `tests/test_tour_reviews.py`

**Interfaces:**
- Tour card schema fields default to `average_rating=None` and `review_count=0`, preserving category-card callers; `/tours/` fills populated aggregates.
- Empty aggregates are `null` and `0`; populated averages are rounded to two decimal places.

- [ ] Add failing tests for tours with no reviews and several reviews; assert the response values and unchanged localized title/pagination.
- [ ] Run the aggregate tests and confirm the new response fields are absent.
- [ ] Add defaulted fields to `TourCardSchema`; query grouped review count and average for the IDs returned by `/tours/` `filtered_list`, merge the aggregate map into each serialized result, and avoid a query per tour. Keep category card callers valid through defaults.
- [ ] Re-run aggregate tests and existing tour list tests. Confirm the category listing and homepage response schemas remain unchanged unless they already use the shared tour card endpoint.

### Task 4: Document and verify the review contract

**Files:**
- Modify: `API.md`
- Create: `tests/test_api_contract_docs.py`

- [ ] Add OpenAPI assertions in `tests/test_api_contract_docs.py` for all three paths, security requirements, status codes, and tour card aggregate properties; run them to observe missing contract fields.
- [ ] Document request/response examples, public access, 409 duplicate behavior, and 404 ownership behavior in `API.md`.
- [ ] Run `pytest tests/test_tour_reviews.py tests/test_api_contract_docs.py -q`, `ruff check mysite/api/tour_reviews.py mysite/database/tour_review_models.py mysite/database/tour_review_schema.py mysite/api/tour.py mysite/database/catalogue_schema.py`, and `git diff --check`.
- [ ] Confirm generated OpenAPI matches `API.md`; record local PostgreSQL/Docker blockers instead of reporting unrun tests as passing.
