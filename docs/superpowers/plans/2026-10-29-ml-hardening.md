# ML hardening implementation plan

**Goal:** Implement the approved [design](../specs/2026-10-29-ml-hardening-design.md) while preserving the current HTTP/WS booking contract and local work.

**Architecture:** Root `ML` package owns prompts, Gemini configuration, provider errors, extraction and read-only tools. Backend owns authorization, persistence, confirmation and translation jobs. Keep old imports compatible during migration.

**Constraints:** No production deployment, production migrations or live Gemini calls. Use disposable PostgreSQL databases. Work in the existing checkout; preserve pre-existing changes. No commits required.

- [x] Establish local PostgreSQL test connectivity and baseline; isolate agent unit tests from DB/network.
  Files: `tests/test_agent_budget.py`, new `tests/ml/` run with `--confcutdir=tests/ml`.
  Check: run existing target suite with TEST_DATABASE_URL pointing to local maintenance DB; the fixture creates and drops only generated test databases.
- [x] Add failing import/packaging tests, then move AI implementation into `ML`; retain compatibility imports.
  Files: `ML/{agent,prompts,tools,schemas,context,provider,config,translation}.py`, `mysite/chain/`, `mysite/translations/translator.py`, API imports, `Dockerfile`, `.github/workflows/ci.yml`, `scripts/{manual_deploy,ci_deploy}.py`, `pyproject.toml`.
  Check: unit imports without API key; runtime archive includes ML and rejects unsafe paths; existing config/company/budget tests.
- [x] Add failing provider/agent regressions before implementing typed errors, safe logs, lazy clients, bounded tool calls and generation validation.
  Files: `ML/errors.py`, `ML/provider.py`, `ML/agent.py`, `mysite/api/chat_ws.py`, `tests/ml/`.
  Check: synthetic real SDK exceptions (429/503/504/403), blocked and malformed finish reasons, invalid tool calls, output overflow, extraction failure and cancellation; no DB/key/network for units.
- [x] Separate booking confirmation phrases from ML; expand transport/ownership and booking regressions.
  Files: `mysite/api/booking_intent.py`, `mysite/api/chat_service.py`, `tests/test_chat_auth.py`, `tests/test_chat_booking_flow.py`, new hardening regression tests.
  Check: revoked token, foreign session/selection, invalid frames, provider failure recovery, stale revision, concurrent confirmation and stored data.
- [x] Validate PostgreSQL migrations, whole suite, lint and formatting; request independent review and fix substantiated findings.
  Check: empty/legacy upgrade and schema check through existing tests; AST/OpenAPI access inventory; full pytest on isolated PostgreSQL. Review changes against approved design, including packaging.
- [x] Update `API.md`, `docs/README.md`, `docs/chat-efficiency.md` and a dated results report with actual test evidence, limitations and migration/deployment instructions.

Each behavioral fix follows red → green: assert the consumer-visible failure, run it against the old behavior, implement the smallest correction, then rerun relevant existing tests. Refactoring uses existing behavior tests plus import/archive regressions. Review and execution continue in this session under the user's approval.
