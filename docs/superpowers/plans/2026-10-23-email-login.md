# Email and username login implementation plan

**Goal:** Add email registration and email-or-username login without breaking existing accounts.

**Design approved:** Keep usernames and existing credentials valid. Add an optional, normalized, unique email to client accounts. Registration validates email format when supplied. Login accepts either `email` or `username`, returning the same generic 401 for missing accounts and incorrect passwords. Email ownership verification is out of scope.

**Architecture:** Extend the shared authentication router used by chat and catalogue details, and add a nullable indexed email column through Alembic. Existing users keep a null email. Never match a contact email collected during a conversation to an authentication account.

**Tech stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest.

## Steps
- Add regression tests for email registration, normalization, duplicates, invalid formats, login by either identifier, wrong passwords and unchanged legacy login; run to observe failures.
- Add the database column and reversible migration, implement separate registration/login schemas and validation, and preserve shared bearer tokens.
- Run targeted tests, migration round-trip and full test suite. Document request examples and the absence of ownership verification.

No commits, server deployment, frontend modifications or changes to admin authentication are included in this task.
