# Chat consultation implementation plan

> Status checked on 2026-10-29: this local plan is not an accurate description of the current implementation. `mysite/api/booking_text.py:preview_text` renders trip details and contacts; `mysite/api/chat_service.py:build_preview` returns the complete state in `data`. The agent uses read-only tools; the local `mysite/chain/catalog.py` helper has no callers. Checked boxes and historical test results below do not establish that these changes are integrated. See the [current change inventory](../../project-changes.md) and [API contract](../../../API.md).

**Goal:** Explain selected services, collect trip requirements and contacts conversationally, and show one short contact confirmation before sending the request.

**Approved design:** Discuss selected tour, hotel and transport using actual catalogue facts. Ask about interests, dates, group and budget (currency and per-person/group basis) before contacts, one or two questions per turn. Request name and phone, optional email; do not request registration or passport numbers. Show «Проверьте заявку» and contacts only; keep preferences and trip details in the manager's request. Keep history and saved data after sending. No frontend sources exist in this repository. Public preview `data` contains contacts only; validation and saved booking state keep all fields. Consumers must not assume trip fields are returned in the public preview.

**Architecture:** Load selected catalogue entries by exact ID, avoiding catalogue limits and extra model tool rounds. Generate the selection welcome in one model call, with a factual fallback on failure. Keep server-side confirmation, revision checks, and duplicate protection. Budget is asked but a refusal is respected; it remains optional in validation.

**Validation:** Dedicated pytest directory uses a minimal FastAPI app and isolated SQLite database so the unrelated existing merge conflict in `mysite/api/tour.py` does not prevent checking this flow. Stub model responses; make no external model calls. Existing full-app suite remains blocked by that conflict.

- [x] Add failing tests for contact summary, exact selected-service details, generated selection welcome, and confirmation persistence.
- [x] Implement catalogue context, selection welcome, focused initial prompt and concise localized summaries.
- [x] Update affected existing assertions and booking documentation.
- [x] Run isolated regressions and inspect the final diff. Do not modify unrelated staged work.

Review identified a concurrent selection-start race introduced by awaiting the model. A conditional SQL update now binds the selection only if its services and draft state still match the snapshot and no chat is linked. Losing requests roll back their candidate session and return the winner, or return 409 when the selection changed. Regression coverage simulates a competing binding during model generation.

Validation uses SQLite in memory: 15 new checks plus 17 existing agent/catalogue checks. No live Gemini or frontend checks were performed. The full app still contains the unrelated tour merge conflict.
