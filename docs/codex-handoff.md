# Handoff for the next Codex session

Last updated: 2026-10-28 (Asia/Bishkek)

## Current task

Address the latest reviewer report in `docs/reviewer-context.md`. The user explicitly asked to publish the result to the remote `master` branch only. Do not push to `main`.

## Current repository state

- Working directory: `C:\Users\Amin\Kyrgyz_Go`
- Current branch: `master`
- Remote: `origin` (`git@github.com:zhazaiym/Kyrgyz_Go.git`)
- Last published commit before this work: `7a139dc` (`Add context for next code review`)
- Changes for the review are currently in the working tree and have not yet been committed or pushed.
- The user authorized the push to `master`; no additional approval is needed for that push.

## Work completed for the reviewer findings

The detailed item-by-item decisions and rationale are in `docs/reviewer-context.md`. Main changes:

- Added a fail-closed Caddy allowlist for `/admin*` using `ADMIN_ALLOWED_CIDR`; documented VPN/static egress setup and the attempt-rate calculation. For 100 unapproved source IPs, zero reach password auth. A single permitted egress has the configured per-IP limit (up to 10 in the fixed-window boundary case). Do not configure a broad allowlist.
- Fixed SQLAdmin translation editing so only genuinely changed values become manual translations. Empty/deleted fields clear their manual/hash metadata and can be translated automatically. Text comparisons normalize CRLF/LF.
- Added shared source-hash, text-normalization, translation-readiness, manual-field, and hash-attachment helpers in `mysite/translations/source.py`. Stale manual translations are released and requeued; user-facing translation and recovery use the same readiness rule.
- Made Alembic migration `20261028_0014_translation_source_identity.py` self-contained with frozen field lists/hash logic, and made downgrade remove stale translations before dropping hash columns.
- Added migration `20261028_0015_rate_limit_account_group.py`; rate-limit counters now support deleting all account/IP groups at password reset, including local blocked-cache entries.
- Improved admin login protection with a network allowlist. The documented tradeoff is intentional: this avoids both cross-IP guessing and account-wide denial-of-service; production must configure a stable VPN/admin egress CIDR.
- Avoided duplicate correlated translation subqueries in tour search/sort by using a translation join.
- Split internal `complete` from public, stage-dependent `can_confirm` in booking previews. Removing an unavailable optional service with complete data now shows the summary and allows confirmation without another LLM turn.
- Improved legacy Alembic separator parsing, including `space`, `newline`, and comma cases.
- Updated tests and the reviewer-context document. See the latter for accepted/partial items and deployment notes.

## Verification already completed

- Full suite: `458 passed in 152.25s` (`pytest -q`).
- `ruff check .`: passed.
- `git diff --check`: passed.
- `docker compose --profile https config --quiet`: passed earlier in this session.
- `ruff format --check` across the entire repository reports 11 pre-existing/unrelated formatting issues in untouched files. Do not mass-format those files as part of this task. Run format check against changed Python files only if needed.
- Caddy runtime validation could not run because Docker Desktop's Linux engine was unavailable. The compose configuration itself validated.
- Production migrations were not applied. The deployment guard intentionally requires manual application of schema changes; see `DEPLOY.md` and `docs/reviewer-context.md`.

## Next actions

1. Recheck `git status`, `git diff --check`, and formatting for changed Python files.
2. Update `docs/reviewer-context.md` with the passing full-suite result and final commit hash after creating the commit.
3. Review the diff, commit the completed changes on `master`, and push only `origin master` (normal push; no force push).
4. Verify the remote `master` points to the new commit and report clearly that `main` was not changed.

The previous Codex session may end at any point. Continue from this file and the live working tree; do not reset or discard the uncommitted changes.
