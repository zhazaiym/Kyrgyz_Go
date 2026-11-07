# Client travel requests design

## Goal

Allow an authenticated client to submit a travel request from an existing saved selection, see their own requests, and cancel one while preserving the request for administrators.

## Current project context

`TravelSelection` stores selected tour/hotel/transport IDs and belongs to a client or session. `TravelRequest` stores contact and travel details but has no client owner. Its public POST is currently disabled, and admin routes manage existing requests. Request statuses include `new`, `in_progress`, `completed`, and `cancelled`. The admin request WebSocket already broadcasts new request events.

## Design

- Add nullable `TravelRequest.client_id` referencing the shared client account. Backfill ownership for historical chat-created requests from `ChatBookingLink`; leave unlinked legacy requests unowned.
- Enable authenticated `POST /travel-requests/`. Accept `selection_id`, travel date, travelers count, phone, and optional comment. Require a client-owned selection and at least one selected active service. Resolve the service snapshot on the server; do not trust client-supplied service IDs or names. Use the authenticated profile/account for name and email.
- Require a future or current travel date and positive traveler count. Keep existing request contact fields; submitted phone may override the profile phone. Normalize/validate phone using existing project conventions.
- Permit one request from a selection. Enforce this in the database and mark the selection submitted atomically with request creation. A consumed selection cannot create another request.
- Add `GET /travel-requests/me/` returning only the caller's requests, newest first.
- Add `DELETE /travel-requests/me/{request_id}/` as cancellation: set status to `cancelled`, preserve the row, and reject cancellation of completed requests. Repeated cancellation is idempotent. Admins retain visibility and existing status management.
- Publish the existing `new_request` admin WebSocket event only after transaction commit for each new direct request.
- Document all endpoints and response schemas in OpenAPI and API docs.

## Validation and risks

Ownership checks must prevent using another client's selection or viewing/cancelling another client's request. Request creation, selection consumption, and uniqueness must be atomic to prevent duplicate submissions. Existing chat booking flow must continue to work and set ownership when it has a known client.

## Verification

Add tests first for authenticated submission, ownership, duplicate selection use, list scoping, cancellation rules, and WebSocket publication after commit. Run relevant tests and migration checks. Production migration/deployment must wait for disk space and a verified database backup.
