# botquanganh MCP

FastMCP server để ChatGPT hoặc MCP client khác dùng máy của bạn làm runner cho
CTF/lab: kiểm tra target, chạy solver Python, quản lý harness, và nếu bật thêm
advanced mode thì chạy workflow/Docker/toolchain nặng hơn.

Runtime hiện tại dùng MCP Streamable HTTP tại một endpoint duy nhất, thường là
`/mcp`. Khi public qua Cloudflare Quick Tunnel, URL sẽ có dạng:

```text
https://<random>.trycloudflare.com/mcp
```

Quick Tunnel là URL tạm thời. Mỗi lần restart tunnel có thể đổi URL.

## Mental Model

```text
ChatGPT / MCP client
  -> https://<trycloudflare>/mcp
  -> cloudflared tunnel
  -> 127.0.0.1:8000/mcp
  -> FastMCP app/main.py
  -> app/tools/*
```

Các tool được register theo `.env`:

```text
Always on:
  health/probe/basic runner/smoke/ctf harness

ENABLE_ADVANCED_TOOLS=true:
  Docker runners, run logs, shell helpers, GitHub helpers, autonomous agent

ENABLE_WORKSPACE_TOOLS=true:
  workspace file helpers

ENABLE_AGENT_TOOLS=true:
  agent_* local file and command helpers
```

## Quick Start

```bash
cd /home/light/Workspace/agy/botquanganh_mcp
chmod +x scripts/*.sh
./scripts/install_basic.sh
./scripts/start_tunnel_server.sh
```

Copy URL được in ra, ví dụ:

```text
https://example.trycloudflare.com/mcp
```

Dùng URL đó trong ChatGPT connector.

Smoke test từ ChatGPT:

```text
health_check
run_safe_smoke_test
```

## Important Config

File chính: `.env`

Các biến hay chỉnh nhất:

```env
MCP_BIND_HOST=0.0.0.0
MCP_PORT=8000
FASTMCP_MESSAGE_PATH=/mcp

REQUIRE_AUTH=false
GATEWAY_TOKEN=...

DISABLE_SECURITY_POLICIES=true
ALLOWED_TCP_TARGETS=*
BLOCK_PRIVATE_IPS=true

ENABLE_ADVANCED_TOOLS=true
ENABLE_WORKSPACE_TOOLS=false
ENABLE_AGENT_TOOLS=true
```

Khuyến nghị khi expose public:

```env
DISABLE_SECURITY_POLICIES=false
ALLOWED_TCP_TARGETS=target.host:port
BLOCK_PRIVATE_IPS=true
ENABLE_AGENT_TOOLS=false
ENABLE_WORKSPACE_TOOLS=false
```

Lưu ý: thay đổi `.env` chỉ có hiệu lực sau khi restart server.

## Start, Restart, Stop

Start server + Cloudflare tunnel:

```bash
./scripts/start_tunnel_server.sh
```

Restart server nhưng giữ tunnel hiện tại:

```bash
./scripts/restart_server_only.sh
```

Kiểm tra process:

```bash
cat logs/launcher.pid logs/server.pid logs/tunnel.pid
ps -p "$(cat logs/launcher.pid logs/server.pid logs/tunnel.pid | paste -sd, -)" -o pid,ppid,comm,args
```

Stop toàn bộ runtime:

```bash
kill "$(cat logs/launcher.pid)"
```

## Tool Profiles

### Basic Profile

Basic profile không cần Docker image. Phù hợp để test connector, kiểm tra
host/port, chạy solver Python nhẹ, và dùng CTF harness.

Nhóm tool chính:

```text
health_check
get_capabilities
check_target_allowed
probe_target_from_runner
tcp_connect_ssl
run_basic_python_solver
run_safe_smoke_test
ctf_harness_capabilities
ctf_harness_instructions
ctf_harness_init
ctf_harness_check
ctf_harness_local
ctf_harness_solve
ctf_harness_verify
ctf_harness_report
ctf_harness_pack
```

`run_basic_python_solver` nhận danh sách file:

```json
{
  "files": [
    {"path": "solve.py", "content": "print('hello')\n"}
  ],
  "entrypoint": "solve.py",
  "timeout_seconds": 10
}
```

Nếu solver cần connect remote, truyền thêm target và target đó phải match
`ALLOWED_TCP_TARGETS`:

```json
{
  "target": {"host": "chal.example", "port": 1337}
}
```

### Advanced Profile

Bật bằng:

```bash
./scripts/install_advanced_tools.sh
```

Advanced profile thêm:

```text
run_solver_fallback
validate_run_request
upload_artifact
rerun_run
get_run_log / list_recent_runs / get_run_summary
get_run_stdout / get_run_stderr / tail_run_output
run_command / run_host_command / run_workspace_command
github_* helpers
agent_goal_create / agent_step / agent_status / agent_report
```

Advanced profile phù hợp cho VPS hoặc máy riêng có Docker/toolchain. Không nên
bật rộng trên public connector nếu chưa khóa policy.

### Agent Tools

`ENABLE_AGENT_TOOLS=true` expose các tool thao tác local workspace:

```text
agent_list_directory
agent_read_file
agent_write_file
agent_edit_file
agent_grep_search
agent_run_command
```

Đây là nhóm quyền mạnh. Nếu connector public chỉ dùng để chạy harness/solver,
hãy để `ENABLE_AGENT_TOOLS=false`.

## CTF Harness

Harness là workflow local-first cho CTF:

```text
TRIAGE -> RECON -> HYPOTHESIS -> EXPLOIT -> VERIFY -> REPORT
```

CLI trực tiếp:

```bash
./scripts/ctfh init --name baby-web --category web --force
./scripts/ctfh check
./scripts/ctfh local --solve
./scripts/ctfh verify --mode local
./scripts/ctfh report
```

Qua MCP, gọi `ctf_harness_instructions` trước để client đọc `GPT.md`.

Harness dùng:

```text
ctf.yaml
workspaces/<challenge>/
logs/artifacts/
```

Flag-like output chỉ là candidate cho tới khi verifier hoặc submit remote xác
nhận.

## Logs And Runtime Files

```text
logs/launcher.log      launcher script output
logs/server.log        FastMCP/uvicorn output
logs/cloudflared.log   Cloudflare tunnel output and URL
logs/gateway.log       audit/application events
logs/*.pid             current launcher/server/tunnel PIDs
logs/artifacts/        uploaded/generated small artifacts
logs/workspaces/       workspace tool state
```

Không xóa `logs/*.pid` khi server/tunnel đang chạy.

## Testing

Chạy test chuẩn:

```bash
DISABLE_SECURITY_POLICIES=false ALLOWED_TCP_TARGETS=1.1.1.1:80 .venv/bin/python -m pytest tests -q
```

Không dùng `pytest -q` ở root nếu chưa cấu hình ignore, vì `scripts/test_*` là
CLI smoke scripts và có thể bị pytest collect nhầm.

Smoke public MCP bằng client thật:

```bash
./scripts/verify_mcp.py https://<random>.trycloudflare.com/mcp
```

## Project Layout

```text
app/             FastMCP server and MCP tool implementations
ctfharness/      CTF harness CLI and challenge helpers
scripts/         install/start/restart/test/verify utilities
runner_images/   Dockerfiles for advanced runners
skills/          category playbooks loaded by agents
templates/       challenge workspace templates
tests/           regression tests
docs/            operator docs and archived planning notes
logs/            runtime logs/PIDs, ignored by git
```

Full map: `docs/REPO_STRUCTURE.md`

Research/source notes: `docs/REFERENCES.md`

Harness roadmap: `docs/HARNESS_IMPROVEMENT_PLAN.md`

## Safety Defaults

For public use, prefer:

```env
DISABLE_SECURITY_POLICIES=false
ALLOWED_TCP_TARGETS=<only-needed-host:port>
BLOCK_PRIVATE_IPS=true
REQUIRE_AUTH=true
ENABLE_AGENT_TOOLS=false
ENABLE_WORKSPACE_TOOLS=false
```

For local CTF debugging, you may temporarily loosen policy, but assume every
enabled tool is callable by the connected MCP client.
