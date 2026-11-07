# Tour reviews design

## Goal

Add public, read-only tour reviews and allow an authenticated client to leave one review per tour and delete their own review. Include review averages and counts in tour cards.

## Current project context

The backend is FastAPI with SQLAlchemy and Alembic. Tours are exposed through the public `/tours/` catalogue and `TourCardSchema`. Authentication uses the shared `ChatClient` account identity; both `/auth/login` and `/account/login` authenticate against that identity. No review model or endpoints currently exist.

## Design

- Add a `TourReview` table related to `Tour` and `ChatClient`. Enforce one review per `(tour_id, client_id)` in the database.
- Store integer rating 1–5, review text (1–2000 characters), and UTC creation time. Capture a display name from the client's profile when present, otherwise use the account username; do not expose email.
- `GET /tours/{tour_id}/reviews/` is public and returns display name, rating, text, and creation date in stable newest-first order. A nonexistent tour returns 404.
- `POST /tours/{tour_id}/reviews/` requires client authentication. Invalid ratings/text return 422; a second review by the same client for the same tour returns 409.
- `DELETE /tours/{tour_id}/reviews/{review_id}/` requires authentication and only deletes the caller's review. Return 404 for a missing review or one owned by another client.
- Extend each `/tours/` card with `average_rating` and `review_count`. The average is nullable when no reviews exist and otherwise rounded to two decimal places; count is zero when empty. Fetch aggregates in a grouped query rather than one query per tour.
- Add Alembic migration and update API documentation/OpenAPI examples.

## Validation and risks

Database uniqueness is the authority for concurrent duplicate submissions. Aggregate queries must retain existing locale, pagination, and filtering behavior. Review creation must only reference an existing tour. Historical rows do not need backfill.

## Verification

Add tests first for public listing, rating bounds, duplicate prevention, owner-only deletion, and card aggregates. Run relevant tests and schema/lint checks. Production migration/deployment must wait for disk space and a verified database backup.
