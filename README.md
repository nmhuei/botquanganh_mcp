# Fallback Runner MCP

MCP server để ChatGPT có thể dùng máy của bạn kiểm tra kết nối tới các target/server CTF hoặc lab.

Repo có 2 chế độ:

- **Basic**: nhẹ, dùng để test/local, có tool kiểm tra kết nối và chạy solver Python pwn/web cơ bản.
- **Full / Advanced**: cài thêm Docker runner images, phù hợp chạy trên VPS hoặc máy chủ cloud.

---

## Tool Modes

### Basic Mode

Basic là chế độ mặc định (`ENABLE_ADVANCED_TOOLS=false`). Không cần Docker image.

Tool basic:

```text
health_check
get_capabilities
check_target_allowed
probe_target_from_runner
run_basic_python_solver
run_safe_smoke_test
ctf_harness_capabilities
ctf_harness_init
ctf_harness_check
ctf_harness_local
ctf_harness_solve
ctf_harness_verify
ctf_harness_report
ctf_harness_pack
```

Dùng basic khi:

- bạn chỉ muốn ChatGPT connect tới MCP server,
- cần kiểm tra host/port từ mạng máy bạn,
- cần chạy solver Python nhẹ cho pwn/web qua máy bạn,
- đang test connector,
- chạy trên laptop/local machine.

Basic Python packages:

```text
requests
beautifulsoup4
lxml
pwntools
pycryptodome
z3-solver
sympy
gmpy2
websocket-client
websockets
```

`run_basic_python_solver` accepts files with either `path` or `name`. If inline `content` is provided without `encoding`, it defaults to `encoding="text"`. For real pwn/web connections, pass a `target` object (`host` and `port`); that target must be allowed by `ALLOWED_TCP_TARGETS`, and the solver receives `TARGET_HOST` and `TARGET_PORT` in its environment. For import-only smoke tests, `target` may be omitted.

`run_safe_smoke_test` is a harmless one-call check for ChatGPT connector setup. It runs health, capabilities, and a print-only basic Python solver without Docker or target network access.

### CTF Harness

Repo also includes a local-first CTF harness imported from `ctf_harness_full_fixed_v030.zip`.
`GPT.md` also folds in operating rules adapted from `multica-ai/andrej-karpathy-skills`: think before coding, keep solvers simple, make surgical changes, and define verification criteria.

Direct CLI:

```bash
./scripts/ctfh init --name baby-web --category web --force
./scripts/ctfh check
./scripts/ctfh local --solve
./scripts/ctfh verify --mode local
./scripts/ctfh report
```

ChatGPT/MCP tools:

```text
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

Before working on a CTF challenge, ChatGPT should call `ctf_harness_instructions` first. That tool returns `GPT.md`, which contains the required pipeline, coding guardrails, verification rules, and reporting rules.

The harness keeps challenge context in `ctf.yaml` and `workspaces/<challenge>/`, records logs/proofs/reports, and treats remote flag-like output as a candidate unless an explicit verifier accepts it.

### Full / Advanced Mode

Full mode bật bằng `./scripts/install_advanced_tools.sh`.

Tool advanced thêm:

```text
agent_goal_create
agent_toolchain_capabilities
agent_step
agent_status
agent_cancel
agent_report
get_runner_environments
run_solver_fallback
validate_run_request
upload_artifact
rerun_run
get_run_log
list_recent_runs
get_run_summary
delete_run
get_run_stdout
get_run_stderr
tail_run_output
create_workspace
upload_file_to_workspace
list_workspace_files
read_workspace_file
delete_workspace
run_command
```

Autonomous agent mode is assisted by default: create a goal with scope/budget, then call `agent_step` repeatedly. Each step runs one safe action and persists state under `logs/agent_goals/<goal_id>/`. Risky actions return `needs_approval` instead of executing.

Full mode sẽ build các Docker image nặng:

```text
ctf-python-runner:latest
ctf-pwn-runner:latest
ctf-sage-runner:latest
ctf-forensics-runner:latest
```

---

## Important Note

For normal testing, ChatGPT connector setup, and lightweight pwn/web solving, install **basic** only:

```bash
./scripts/install_basic.sh
```

Install **full/advanced** only on a VPS or cloud server if you need containerized solver execution, Sage, forensics, or heavier isolated tooling. The full install downloads and builds large Docker images and can take a long time on a laptop.

---

## Quick Start: Basic

```bash
cd /home/light/Workspace/agy/botquanganh_mcp
chmod +x scripts/*.sh
./scripts/install_basic.sh
```

Edit `.env`:

```env
ENABLE_ADVANCED_TOOLS=false
ALLOWED_TCP_TARGETS=target.host:port
BLOCK_PRIVATE_IPS=true
```

Start MCP server with Cloudflare Tunnel:

```bash
./scripts/start_tunnel_server.sh
```

The script prints a public endpoint like:

```text
https://xxxx.trycloudflare.com/mcp
```

Use that URL in ChatGPT MCP Connector settings.

---

## ChatGPT Connector Setup

1. Run:

   ```bash
   ./scripts/start_tunnel_server.sh
   ```

2. Copy the printed URL ending in `/mcp`.

3. In ChatGPT, create/add an MCP connector.

4. Paste the URL, for example:

   ```text
   https://xxxx.trycloudflare.com/mcp
   ```

5. Test with:

   ```text
   health_check
   ```

In basic mode, ChatGPT should see exactly:

```text
health_check
get_capabilities
check_target_allowed
probe_target_from_runner
run_basic_python_solver
```

---

## Configure Allowed Targets

`ALLOWED_TCP_TARGETS` controls which host:port ChatGPT may probe through your machine.

Specific allowlist:

```env
ALLOWED_TCP_TARGETS=socket.cryptohack.org:13418,example.com:443
```

Wildcard:

```env
ALLOWED_TCP_TARGETS=*
```

Avoid `*` unless you understand the risk. This server uses your machine/network.

Recommended:

```env
BLOCK_PRIVATE_IPS=true
```

This helps block localhost/private-network targets unless explicitly allowed for testing.

---

## Full Install For VPS / Cloud Server

Use this only when you want ChatGPT to run solver scripts or shell commands inside isolated Docker containers.

```bash
cd /home/light/Workspace/agy/botquanganh_mcp
chmod +x scripts/*.sh
./scripts/install_advanced_tools.sh
```

After installation, restart the server:

```bash
./scripts/start_tunnel_server.sh
```

`install_advanced_tools.sh` will:

- run basic install,
- build all runner Docker images,
- set `ENABLE_ADVANCED_TOOLS=true` in `.env`.

---

## Manual Server Start

Without tunnel:

```bash
source .venv/bin/activate
PYTHONPATH=. python3 -m app.main
```

HTTP mode:

```bash
source .venv/bin/activate
PYTHONPATH=. fastmcp run app/main.py --transport streamable-http --port 8000 --host 127.0.0.1 --path /mcp
```

Dev UI:

```bash
./scripts/dev.sh
```

---

## Test

For local testing and lightweight pwn/web solving, basic install is enough:

```bash
./scripts/install_basic.sh
./scripts/test.sh
```

The test suite uses mocks for Docker paths, so it does not require full install just to validate code.

---

## Project Layout

```text
app/
  main.py              MCP entrypoint
  config.py            environment config
  security.py          allowlist and safety checks
  tools/
    health.py          basic health/capability tools
    probe.py           basic target connectivity probe
    basic_runner.py    basic Python pwn/web solver runner
    fallback.py        advanced solver runner tools
    workspace.py       advanced workspace tools
    runs.py            advanced run log tools
    shell.py           advanced container command tool
runner_images/         Dockerfiles for full install
scripts/
  install_basic.sh
  install_advanced_tools.sh
  start_tunnel_server.sh
  build_runner_images.sh
  test.sh
logs/                  runtime logs, ignored by git
```

---

## Security Notes

- Keep basic mode for laptop/local testing and lightweight pwn/web challenges.
- Use full mode mainly on VPS/cloud servers with Docker.
- Keep `ALLOWED_TCP_TARGETS` narrow when possible.
- Keep `BLOCK_PRIVATE_IPS=true` unless you are intentionally testing local targets.
- Full mode exposes more powerful tools, including container execution and file workspace operations.
