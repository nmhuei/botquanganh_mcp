# botquanganh-host-mcp

Host MCP server (FastMCP) + `bqa` operations CLI for executing allow-listed commands on the host machine.

## Commands

- Install (editable + test deps): `.venv/bin/pip install -e ".[test]"` (or via `uv pip`, see `install.sh`)
- Test: `.venv/bin/python -m pytest`
- Strength/stress subset: `.venv/bin/python -m pytest tests/strength`
- Live-server load test: `.venv/bin/python scripts/stress_mcp.py` (requires running server)
- Start runtime (daemonized): `bqa start` — stops with `bqa stop`, status via `bqa status`

## Notes

- Server binds `127.0.0.1:18427`, MCP endpoint at `/mcp` (streamable-http, stateless JSON), REST under `/api/v1/*`, health at `/healthz`.
- Configuration comes from `.env` (see `app/config.py`); notable overrides in local dev: `MAX_OUTPUT_BYTES`, `MAX_TIMEOUT_SECONDS`, `MAX_CONCURRENT_COMMANDS`.
- Default policy is `guarded`: blocks explicitly destructive patterns (mkfs, fork bombs, sudo, shutdown...); `HOST_ALLOWED_COMMANDS=all` short-circuits the allowlist.
- No lint/format tooling is configured; do not add one without asking.
- Python >= 3.10; dependencies pinned in `pyproject.toml` (`fastmcp==3.4.0`).
