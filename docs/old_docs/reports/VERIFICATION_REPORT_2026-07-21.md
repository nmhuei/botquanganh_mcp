# Customer-Ready Verification Report — 2026-07-21

## Scope

This verification covered the current working tree, with emphasis on the root installer, CLI packaging, lifecycle safety, source quality, security posture, and customer installation flows.

## Installer verification

`./scripts/manual_test_installer.sh` passed all seven scenarios in isolated temporary directories:

1. Local `./install.sh` execution.
2. Compatibility delegation through `scripts/install_basic.sh`.
3. `cat install.sh | bash` from inside a repository.
4. Remote-style piped installation from a Git repository.
5. Safe fast-forward update of an existing installation.
6. Rejection of dirty installations and origin mismatches.
7. Clear failure for invalid remote branches.

The test also verified:

- `.venv` creation and dependency installation.
- Editable CLI package installation.
- `.env` creation, preservation, and mode `600`.
- `~/.local/bin/bqa`-style symlink resolution.
- `bqa version` output.
- `pip check` success.

## Server-only restart regression

A live `bqa server restart --json` test reproduced and fixed a lifecycle bug where `lsof -i :PORT` treated the Cloudflare client connection as a process occupying the listening port.

The corrected implementation:

- inspects only TCP listeners;
- coordinates with the active supervisor instead of racing it;
- changes only the MCP server PID;
- preserves the Cloudflare tunnel PID and connector URL.

No live tunnel restart was performed after the operator explicitly prohibited it.

## Automated quality

- Pytest: **106 passed**.
- Python compileall: **PASS**.
- Bash syntax: **PASS**.
- Git diff whitespace check: **PASS**.
- Project dependency closure: **PASS** (19 packages).
- CLI version and configuration validation: **PASS**.
- Installer manual regression: **7/7 PASS**.

## Security and static analysis

Final scan artifacts are stored in `artifacts/cycle-10/scans/`.

- Ruff: **0 issues**.
- Bandit: **0 findings**.
- pip-audit: **0 known vulnerabilities** across 70 resolved dependencies.
- detect-secrets: **0 candidates**.
- ShellCheck: **0 issues**.
- zizmor workflow scan: **0 issues** in offline mode.

## Residual operational warning

The checked development runtime intentionally has `REQUIRE_AUTH=false`. The repository default in `.env.example` is `REQUIRE_AUTH=true`, and customer/public deployment must configure a fresh `GATEWAY_TOKEN` before exposing the service.

## Decision

**READY_WITH_ACCEPTED_RISK** for branch review and customer installation testing.

The only accepted risk is the local development runtime's explicitly disabled authentication; it is not the shipped default.
