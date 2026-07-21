# Security

## Trust model

BotQuangAnh Host MCP intentionally reads files and executes commands with the privileges of the operating-system user that starts the service. It is **not a sandbox**. The `guarded` command policy blocks explicit destructive or privileged patterns, but it does not make arbitrary shell execution safe against an untrusted caller.

The development runtime currently uses `REQUIRE_AUTH=false` by explicit operator choice. Production exposure must enable authentication and use a fresh token.

## Enforced boundaries

### Filesystem

- `HOST_WORKSPACE_DIR` defines the file and command working-directory boundary.
- `HOST_RESTRICT_TO_WORKSPACE=true` performs lexical and resolved-path checks.
- Public file operations reject symlink components and use no-follow final opens.
- Directory listing/search do not follow symlink targets.
- Writes are atomic and fsynced; no-overwrite creation is race-safe.
- Append and replace enforce the configured final/source file-size limits.

### Command execution

- `HOST_COMMAND_POLICY=guarded` blocks explicit host-destruction, power-management, and privilege-boundary patterns.
- `HOST_COMMAND_POLICY=allowlist` additionally restricts command names and rejects dynamic shell substitution.
- Commands run through a non-login, no-profile shell.
- Credential-shaped environment variables are removed unless explicitly listed in `HOST_ENV_ALLOWLIST`.
- Shell-startup and dynamic-loader injection variables are always removed.
- stdout/stderr are continuously drained but retained only up to `MAX_OUTPUT_BYTES` per stream.
- Timeouts terminate the command process group.
- `MAX_CONCURRENT_COMMANDS` and `COMMAND_QUEUE_TIMEOUT_SECONDS` bound process creation and overload queues.

### HTTP and middleware

- `GATEWAY_TOKEN` protects HTTP/MCP traffic when `REQUIRE_AUTH=true`.
- Authentication, rate limiting, metrics, REST, and MCP use a shared error taxonomy.
- `RATE_LIMIT_MAX_CLIENTS` bounds in-memory client state.
- `TRUST_PROXY_HEADERS=true` is appropriate only behind a trusted proxy such as the configured Cloudflare Tunnel.
- Public errors redact known host paths and mask unexpected exception details.

### Audit and diagnostics

- Audit records redact sensitive keys and inline credential/key formats.
- Audit fields are length-bounded and log files rotate.
- Audit events include a schema version, event ID, service version, and UTC timestamp.
- `scripts/collect_diagnostics.sh` excludes `.env` and runtime log bodies.
- `.env` is installed and validated with mode `600` when it contains credentials.

## What is not guaranteed

An allowed command can still:

- modify or delete data inside the workspace;
- access the network with the host user's permissions;
- execute binaries or scripts available to that user;
- consume resources up to the configured concurrency, timeout, and output limits;
- interact with other same-user processes and resources outside a true sandbox.

For stronger isolation, run the service in a dedicated account, container, VM, or purpose-built sandbox and use the smallest practical workspace.

## Recommended deployment posture

1. Use a dedicated non-root account.
2. Set the smallest possible `HOST_WORKSPACE_DIR`.
3. Enable `REQUIRE_AUTH=true` and rotate the gateway token before deployment.
4. Keep `.env` mode `600`.
5. Prefer `HOST_COMMAND_POLICY=allowlist` for narrowly defined workflows.
6. Set `HOST_INHERIT_ENV=false` when commands need only the base/allowlisted environment.
7. Size command/rate limits for the host.
8. Run `bqa config validate --strict` and `./scripts/quality_gate.sh --full`.
9. Use a clean dedicated virtualenv for production.

## Security verification

```bash
./scripts/quality_gate.sh --full
uvx bandit -q -r app
uvx pip-audit -r requirements.txt
uvx detect-secrets scan --all-files \
  --exclude-files '(^|/)(\.env$|\.venv/|logs/|artifacts/|manual_test_workspace_|\.pytest_cache/)'
```

Scanner results require manual triage. A clean scan does not prove absence of vulnerabilities.

## Incident response

Collect redacted diagnostics first when safe:

```bash
./scripts/collect_diagnostics.sh artifacts/incident-diagnostics
```

Inspect managed status and logs:

```bash
bqa status
bqa doctor
bqa logs server -n 200
bqa logs audit -n 200
bqa logs tunnel -n 200
```

Stop managed processes when necessary:

```bash
bqa stop
```

Lifecycle scripts validate process ownership before termination and refuse to kill unrelated reused PIDs.

See `docs/OPERATIONS_RUNBOOK.md` for recovery and rollback procedures.
