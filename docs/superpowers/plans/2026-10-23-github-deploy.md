# GitHub automatic deployment plan

**Design:** Test pull requests and main pushes in GitHub Actions without production secrets. After successful tests, only main pushes or manual main runs may deploy. Stream an explicit source archive over pinned-host SSH using a separate restricted key. Never copy .env or local databases. Preserve server Compose/Caddy and database volumes.

**Server:** A trusted deployment entrypoint serializes deployments, validates revision and archive members, creates a database/config backup, builds before replacing the healthy backend, and restores the old override if activation fails. Reuse the running runtime when Dockerfile and requirements are unchanged; dependency changes require a normal full build and sufficient disk. Never prune volumes or unrelated images.

**Steps:**
- Add failing unit tests for deployment archive validation and workflow safeguards.
- Implement GitHub Actions workflow and trusted server entrypoint with strict archive allowlist, free-space guards, backups and rollback.
- Test locally and in server dry-run mode. Install a root-owned entrypoint and a separate restricted SSH key only after configuration is validated.
- Publish code only with explicit commit/push approval. GitHub repository secrets require owner access; do not expose keys in chat or commits.

**Activation:** Automatic deployment is not active until workflow is published, repository secrets are configured and a successful GitHub Actions run is observed. Preserve current production until then.
