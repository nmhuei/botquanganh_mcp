# botquanganh MCP

FastMCP server để ChatGPT hoặc MCP client khác dùng máy của bạn làm runner cho
CTF/lab: kiểm tra target, chạy solver Python, quản lý harness, Docker-backed
runner, autonomous agent, và auto-recovery khi server die hoặc bị rate limit.

```text
ChatGPT / MCP client
  -> https://<trycloudflare>/mcp
  -> cloudflared tunnel
  -> 127.0.0.1:8000/mcp
  -> FastMCP app/main.py
  -> app/tools/*
```

## Quick Start

```bash
cd /home/light/GitHub/botquanganh_mcp
./scripts/install_basic.sh               # venv + pip install
./run_mcp_tunnel.sh                       # daemon (background, thoát terminal OK)
```

Copy URL được in ra, dùng trong ChatGPT connector settings.

Mọi thao tác qua `run_mcp_tunnel.sh`:

| Lệnh | Mô tả |
|------|-------|
| `./run_mcp_tunnel.sh` | Chạy daemon (nohup, thoát terminal được) |
| `./run_mcp_tunnel.sh --status` | Xem PID server/tunnel + endpoint URL |
| `./run_mcp_tunnel.sh --stop` | Dừng daemon + server + tunnel |
| `./run_mcp_tunnel.sh --restart` | Khởi động lại |

## Quick Smoke Test

Từ ChatGPT sau khi kết nối:

```text
health_check
run_safe_smoke_test
```

## Daemon Architecture

```
run_mcp_tunnel.sh        ←─ daemon wrapper (nohup + background)
  └─ start_tunnel_server.sh  ←─ watchdog loop (mỗi 3s)
        ├─ Server die        → auto-restart server
        ├─ Tunnel die        → auto-restart tunnel
        ├─ Health fail (6×)  → auto-restart server
        ├─ 429 rate-limited  → auto-restart server + tunnel
        └─ Restart >5 lần   → dừng hẳn (tránh loop)
```

Chi tiết: `docs/WORKFLOW.md`

## Developer Commands

```bash
# Restart server, giữ tunnel đang chạy
./scripts/restart_server_only.sh

# Build Docker runner images
./scripts/build_runner_images.sh

# Enable advanced tools (Docker runners + shell + runs + agent)
./scripts/install_advanced_tools.sh

# Run tests
DISABLE_SECURITY_POLICIES=false ALLOWED_TCP_TARGETS=1.1.1.1:80 \
  .venv/bin/python -m pytest tests -q

# Debug
tail -f logs/launcher.log      # daemon output
tail -f logs/server.log        # FastMCP stdout
tail -f logs/gateway.log       # audit events
tail -f logs/cloudflared.log   # tunnel log
curl http://127.0.0.1:8000/healthz  # local health check
```

## Config Overview

File `.env` là config trung tâm (~40 biến). Hay chỉnh nhất:

```env
RATE_LIMIT_ENABLED=true           # 200 req/IP/60s sliding window
RATE_LIMIT_MAX_REQUESTS=200
RATE_LIMIT_WINDOW_SECONDS=60

REQUIRE_AUTH=false                # Bật token auth khi public
GATEWAY_TOKEN=...

ENABLE_ADVANCED_TOOLS=true        # Docker runner + shell + runs
ENABLE_AGENT_TOOLS=true           # agent_* file/command tools
ENABLE_WORKSPACE_TOOLS=false      # workspace CRUD
```

Khuyến nghị khi public:

```env
RATE_LIMIT_ENABLED=true
DISABLE_SECURITY_POLICIES=false
ALLOWED_TCP_TARGETS=<chỉ-target-cần-thiết>
BLOCK_PRIVATE_IPS=true
REQUIRE_AUTH=true
ENABLE_AGENT_TOOLS=false
ENABLE_WORKSPACE_TOOLS=false
```

## Docker Runners

Một consolidated image với 3 tags:

| Tag | Công dụng |
|-----|-----------|
| `ctf-runner:latest` | Python + pwntools + crypto (python/pwn) |
| `ctf-runner:web` | + Playwright + CloakBrowser |
| `ctf-runner:forensics` | Ubuntu + volatility + binwalk... |

Build: `./scripts/build_runner_images.sh`

## Tool Profiles

### Core (luôn bật)
`health_check`, `get_capabilities`, `check_target_allowed`, `probe_target_from_runner`,
`tcp_connect_ssl`, `run_basic_python_solver`, `run_safe_smoke_test`,
`ctf_harness_capabilities`, `ctf_harness_instructions`, `ctf_harness_init/check/local/solve/verify/report/pack`

### Advanced (ENABLE_ADVANCED_TOOLS=true)
`run_solver_fallback`, `validate_run_request`, `upload_artifact`, `rerun_run`,
`get_run_log`, `list_recent_runs`, `get_run_summary`, `get_run_stdout/stderr`,
`tail_run_output`, `run_command`, `github_*`, `agent_goal_*`

### Agent Tools (ENABLE_AGENT_TOOLS=true)
`agent_list_directory`, `agent_read/write/edit_file`, `agent_grep_search`, `agent_run_command`

## Logs

```text
logs/launcher.log       daemon output
logs/server.log         FastMCP stdout
logs/cloudflared.log    tunnel output + URL
logs/gateway.log        audit events (JSON)
logs/*.pid              PID files
logs/artifacts/         uploaded artifacts
logs/runs/              run histories
logs/workspaces/        workspace state
```

## Docs

| File | Mô tả |
|------|-------|
| `docs/WORKFLOW.md` | **Kiến trúc & vận hành chi tiết** |
| `docs/REPO_STRUCTURE.md` | File map |
| `docs/REFERENCES.md` | Research notes |
| `SECURITY.md` | Threat model |
| `CLAUDE.md` | Claude Code instructions |
