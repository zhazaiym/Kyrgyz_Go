# One-command manual deployment plan

**Approved design:** A PowerShell command uploads the current working source tree directly to the existing server over SSH, without GitHub access. Reuse the trusted server deployment entrypoint for database/config backups, serialization, disk guards, building, health checks and image rollback.

**Implementation:** Add a stdlib-only Python CLI and PowerShell wrapper. Default to the existing personal SSH key; use the independently verified public host key with strict SSH host checking. Stream tar bytes through Python subprocess stdin, never a PowerShell text pipeline. Include uncommitted source changes but exclude secrets, databases and caches. Use an archive content digest as the manual snapshot identifier, not a fabricated Git commit.

**Verification:** Unit-test archive selection, symlink rejection, pinned SSH options and binary streaming. Provide a check-only mode which validates prerequisites and packaging without restarting the server. Run full local tests and check-only against the server; actual deployments remain an explicit user command.

**Constraints:** Do not commit, push, change GitHub secrets or issue a production restart merely to test the wrapper. Team members need individual authorized SSH keys and must coordinate deployments.
