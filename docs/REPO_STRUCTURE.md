# Repository Structure

This repository is a FastMCP server for CTF and lab automation. The layout is
split by runtime server code, tool implementations, harness helpers, scripts,
templates, and generated runtime state.

## Source Directories

```text
app/
  main.py              FastMCP entrypoint and tool registration
  config.py            Environment-driven settings from .env
  security.py          Policy enforcement and target allowlist checks
  auth.py              Gateway token validation
  sse_events.py        SSE/event endpoint helpers
  mcp_server.py        MCP server construction helpers
  runner.py            Local runner primitives
  docker_runner.py     Docker runner primitives
  egress_firewall.py   Optional egress firewall helpers
  file_package.py      File packaging helpers
  transcript.py        Transcript/artifact helpers
  logging_audit.py     Audit log helpers
  event_bus.py         In-process event distribution
  agent_paths.py       Side-effect-free agent path resolver
  idempotency.py       Short-lived duplicate-call suppression
  schemas.py           Shared Pydantic/data schemas
  tools/               MCP tool implementations

app/tools/
  health.py            Health, capabilities, and smoke-test tools
  probe.py             Target allowlist checks and TCP/TLS probes
  basic_runner.py      Basic Python solver execution
  fallback.py          Advanced solver runner tools
  shell.py             Host/workspace/container command tools
  runs.py              Run lookup and artifact tools
  workspace.py         Workspace file helpers
  agent.py             Agent-mode command/file tools
  autonomous_agent.py  Autonomous workflow helpers
  ctf_harness.py       Harness-oriented MCP tools
  github_ops.py        GitHub/local repo operation helpers

ctfharness/
  cli.py               Harness CLI
  config.py            Harness config loading
  constants.py         Harness constants
  flag.py              Flag validation/submission helpers
  logging_utils.py     Harness logging helpers
  scope.py             Challenge scope helpers
```

## Operational Directories

```text
scripts/
  install_basic.sh             Install the minimal Python/MCP runtime
  install_advanced_tools.sh    Install advanced Docker/CTF dependencies
  start_tunnel_server.sh       Start MCP server plus Cloudflare quick tunnel
  restart_server_only.sh       Restart only the local MCP server process
  build_runner_images.sh       Build runner Docker images
  cleanup_runs.sh              Clean old run directories
  test.sh                      Run the normal test suite
  verify_mcp.py                MCP verification helper
  mcp_manager.py               Local MCP management helper

runner_images/                 Dockerfiles for advanced runner containers
skills/                        CTF skill instruction packs exposed to agents
templates/                     Challenge workspace templates by category
examples/                      Small request/solver examples
docs/                          Design and operator documentation
docs/archive/                  Planning notes and historical audits
docs/HARNESS_IMPROVEMENT_PLAN.md
                               Roadmap for the next CTF harness architecture
docs/REFERENCES.md             External references used for operator docs
tests/                         Unit and integration-style regression tests
```

## Root Files

```text
.env                 Local runtime configuration, ignored by git
.env.example         Shareable config template
.gitignore           Ignore rules for generated/local state
requirements.txt     Python dependencies
Dockerfile           Container image for the MCP service
docker-compose.yml   Compose entrypoint for containerized runs
README.md            Primary user-facing setup guide
SECURITY.md          Security notes
GPT.md               CTF harness operating instructions returned by MCP
CLAUDE.md            Local coding-agent instructions
ctf.example.yaml     Example CTF harness config
run_mcp_tunnel.sh    Small tunnel launcher wrapper
```

The markdown files below are kept at the repository root because tools or common
agent conventions reference them directly:

```text
GPT.md
CLAUDE.md
README.md
SECURITY.md
```

Historical planning/audit notes live under `docs/archive/`:

```text
docs/archive/CHECK_RESULTS.md
docs/archive/FIX_AUDIT.md
docs/archive/autonomous_ws_plan.md
docs/archive/harnes_ctf.md
docs/archive/masterguide.md
docs/archive/plan.md
docs/archive/skill_plan.md
```

## Generated Or Local State

These paths are intentionally local and should not be committed:

```text
.venv/               Local Python virtual environment
.pytest_cache/       Pytest cache
__pycache__/         Python bytecode cache
logs/                Runtime logs, PID files, and small artifacts
.env                 Local secrets and runtime policy
mcp_workspace/       Local MCP workspace state, if created
scratch/             Temporary manual experiments
```

The file `botquanganh_mcp.zip` is an untracked export/archive artifact. Keep it
only if you still need that exact snapshot; otherwise it is safe to remove after
confirming it is not your backup source.

## Cleanup Guide

Safe to delete anytime:

```bash
find app ctfharness tests -type d -name '__pycache__' -prune -exec rm -rf {} +
rm -rf .pytest_cache
find app ctfharness tests -type f -name '*.pyc' -delete
```

Delete only when the server is stopped:

```text
logs/*.pid
logs/server.log
logs/cloudflared.log
logs/launcher.log
```

Review before deleting:

```text
botquanganh_mcp.zip
logs/artifacts/
logs/workspaces/
docs/archive/
```

Do not delete as part of normal cleanup:

```text
.env
.venv/
app/
ctfharness/
scripts/
skills/
templates/
tests/
```

## Runtime Shape

Normal public-tunnel runtime:

```text
scripts/start_tunnel_server.sh
  -> .venv/bin/fastmcp run app/main.py --transport streamable-http --path /mcp
  -> cloudflared tunnel --url http://127.0.0.1:8000
```

The launcher writes:

```text
logs/launcher.pid
logs/server.pid
logs/tunnel.pid
logs/launcher.log
logs/server.log
logs/cloudflared.log
```

If `.env` changes, restart the server process so `app/config.py` is reloaded.
