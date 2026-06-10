# Claude Code Instructions

This repo is a FastMCP-based CTF/lab runner. When operating here, act as a
careful local engineering agent: inspect first, patch narrowly, and verify with
the real command path.

## Repository Mission

Provide MCP tools for:

- target allowlist checks and TCP/TLS probes
- lightweight Python solver execution
- CTF harness workflows
- optional Docker-backed advanced runners
- optional local agent/workspace operations

Do not widen the public tool surface or policy defaults casually. This project
can expose command execution and network reachability.

## First Checks

Before changing behavior:

```bash
git status --short
rg -n '<symbol-or-setting>'
```

For runtime/debug tasks, inspect:

```text
.env
app/config.py
app/main.py
app/security.py
app/tools/
logs/server.log
logs/cloudflared.log
```

## Runtime Model

Normal tunnel runtime:

```text
scripts/start_tunnel_server.sh
  -> fastmcp run app/main.py --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
  -> cloudflared tunnel --url http://127.0.0.1:8000
```

Server-only restart:

```bash
./scripts/restart_server_only.sh
```

Do not kill the tunnel unless the task requires a new public URL.

## Editing Rules

- Keep changes scoped to the reported bug or documentation task.
- Do not revert user changes.
- Use structured parsers or existing helpers where available.
- Do not add broad abstractions for one narrow fix.
- Keep comments useful and sparse.
- Keep `.env` values stable unless the user explicitly asks to change runtime
  behavior.

## Test Commands

Preferred full test command:

```bash
DISABLE_SECURITY_POLICIES=false ALLOWED_TCP_TARGETS=1.1.1.1:80 .venv/bin/python -m pytest tests -q
```

Do not use bare `pytest -q` from repo root unless collection has been configured
to ignore CLI scripts under `scripts/`.

Targeted smoke:

```bash
bash -n scripts/start_tunnel_server.sh scripts/restart_server_only.sh
.venv/bin/python -m py_compile app/config.py app/security.py app/main.py
```

Public MCP smoke should use a real MCP client session against `/mcp`, not only
`curl`, because Streamable HTTP is session-aware.

## Security Rules

Treat these as high-risk:

```text
DISABLE_SECURITY_POLICIES=true
ALLOWED_TCP_TARGETS=*
ENABLE_AGENT_TOOLS=true
ENABLE_ADVANCED_TOOLS=true
```

When debugging policy:

- verify whether `app.config` was loaded before env overrides
- restart the server after `.env` changes
- separate connector/session errors from actual origin failures
- remember that 400 missing session ID can mean the route is alive

## CTF Harness Rules

For CTF work, load `GPT.md` and follow:

```text
TRIAGE -> RECON -> HYPOTHESIS -> EXPLOIT -> VERIFY -> REPORT
```

No verified exploit means no claimed flag.

## Documentation Rules

Keep documentation split by purpose:

```text
README.md                 operator quickstart
SECURITY.md               threat model and hardening
docs/REPO_STRUCTURE.md    file/directory map
docs/REFERENCES.md        researched external references
GPT.md                    CTF harness instructions exposed by MCP
CLAUDE.md                 local coding-agent instructions
```

When external behavior is documented, prefer primary sources: official MCP spec,
FastMCP docs, Cloudflare docs, and local code.
