# Security Policy

This project exposes local compute and network reachability through MCP tools.
Treat every public connector URL as a remote-control surface for the enabled
tools in `.env`.

The runtime uses MCP Streamable HTTP, normally at `/mcp`, and is often exposed
with Cloudflare Quick Tunnel. The MCP specification recommends three controls
for Streamable HTTP servers: validate `Origin`, bind local servers to localhost
when possible, and require authentication for remote connections. This repo's
launcher binds the tunnel-facing server to `127.0.0.1` by default and exports
`MCP_DISABLE_DNS_REBINDING=1`.

## Security Boundary

Primary boundary:

```text
ChatGPT/MCP client -> /mcp -> FastMCP tools -> local host / Docker / target
```

Policy is configured by `.env`, loaded in `app/config.py`, and enforced mainly
by `app/security.py`, `app/tools/probe.py`, `app/tools/basic_runner.py`, and
`app/tools/shell.py`.

## Recommended Public Profile

Use this when exposing a connector URL outside your machine:

```env
REQUIRE_AUTH=true
DISABLE_SECURITY_POLICIES=false
ALLOWED_TCP_TARGETS=target.host:port
BLOCK_PRIVATE_IPS=true
ENABLE_EGRESS_FIREWALL=false
ENABLE_AGENT_TOOLS=false
ENABLE_WORKSPACE_TOOLS=false
ENABLE_ADVANCED_TOOLS=false
```

Enable advanced or agent tools only when you intentionally need them and trust
the client.

## High-Risk Switches

```env
DISABLE_SECURITY_POLICIES=true
```

This is a broad bypass. It effectively widens target access and relaxes several
path/network restrictions. Use only for local debugging.

```env
ALLOWED_TCP_TARGETS=*
```

Allows target-oriented helpers to connect broadly. Avoid this on a public
connector.

```env
ENABLE_AGENT_TOOLS=true
```

Exposes local file and command helpers. Keep false unless you explicitly want an
agent to operate inside `AGENT_WORKSPACE_DIR`.

```env
ENABLE_ADVANCED_TOOLS=true
```

Exposes Docker runner, shell, GitHub, run-log, and autonomous-agent helpers.
This is useful for a private VPS/toolbox, not as a default public surface.

## Threats And Mitigations

### Remote Code Execution Through Solvers

Risk: a caller submits malicious solver code.

Mitigations:

- Basic solver writes files into a per-run directory.
- Paths are normalized and traversal is rejected when policies are enabled.
- Advanced runners are intended to run inside Docker with memory, CPU, PID, and
  user limits.
- Host command helpers pass through command policy checks and block forbidden
  destructive patterns even when general policies are disabled.

### SSRF And Internal Network Access

Risk: a caller uses your machine to reach localhost, private networks, cloud
metadata endpoints, or arbitrary external hosts.

Mitigations:

- `ALLOWED_TCP_TARGETS` restricts target host:port pairs.
- `BLOCK_PRIVATE_IPS=true` rejects private, loopback, and link-local targets
  when policies are enabled.
- `ENABLE_EGRESS_FIREWALL=true` is available for Docker egress control where
  implemented.

### Duplicate Execution From Client Retries

Risk: connector/network retries run the same solver or command multiple times.

Mitigation:

- `app/idempotency.py` caches short-lived identical calls for selected execution
  tools.
- Repeated identical calls return the first result with
  `idempotency_cache_hit=true`.

### File System Escape

Risk: uploaded files or agent paths escape the intended workspace.

Mitigations:

- Relative path validators reject absolute paths and `..` traversal when
  policies are enabled.
- Agent paths resolve through `app/agent_paths.py`.
- `AGENT_RESTRICT_TO_WORKSPACE=true` keeps agent file operations inside
  `AGENT_WORKSPACE_DIR` unless policies are globally disabled.

### Credential Leakage

Risk: logs capture tokens, cookies, keys, or credentials.

Mitigations:

- Audit logging redacts common secret-like keys and key material.
- `.env` and `logs/` are ignored by git.

Still avoid pasting real credentials into solver payloads or tool arguments.

## Authentication Notes

`GATEWAY_TOKEN` and `REQUIRE_AUTH` are local gateway controls. For long-lived
public deployments, prefer a real identity layer or reverse proxy policy in
front of the MCP endpoint.

Quick Tunnel is convenient for temporary exposure, but the URL is public to
anyone who has it. Do not treat obscurity of the random hostname as
authorization.

## Operational Checklist

Before sharing a connector URL:

```bash
rg -n '^(DISABLE_SECURITY_POLICIES|ALLOWED_TCP_TARGETS|REQUIRE_AUTH|ENABLE_.*TOOLS)=' .env
./scripts/restart_server_only.sh
```

Then smoke test:

```text
health_check
run_safe_smoke_test
get_capabilities
```

Review exposed tools. If `agent_run_command` or `run_host_command` appears, you
are exposing command execution.

## Cleanup

Runtime files are local state:

```text
logs/*.pid
logs/*.log
logs/artifacts/
logs/workspaces/
```

Delete logs only after stopping the launcher/server/tunnel. Use
`scripts/cleanup_runs.sh` for old run directories.
