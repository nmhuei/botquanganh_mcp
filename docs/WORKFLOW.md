# 🏗️ MCP CTF Runner — Kiến trúc & Vận hành

> **Mục đích:** FastMCP server chạy CTF/lab solver tools, expose qua Cloudflare Tunnel.
> ChatGPT / MCP clients kết nối đến endpoint URL và gọi các tool để giải CTF.

---

## 1. 🔭 Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│                      INTERNET / ChatGPT                              │
│              MCP Client (streamable-http)                             │
└────────────────────────┬────────────────────────────────────────────┘
                         │  https://xxx.trycloudflare.com/mcp
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Cloudflare Tunnel       (cloudflared tunnel --url ...)              │
│  logs/cloudflared.log                                               │
│  Thoát terminal được nhờ run_mcp_tunnel.sh (nohup + daemon)        │
└────────────────────────┬─────────────────────────────────────────────┘
                         │  http://127.0.0.1:8000
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastMCP Server  (fastmcp run app/main.py --transport streamable-http)
│  port 8000                                                           │
│                                                                      │
│  Middleware stack (ASGI, applied outermost → innermost):            │
│    1. MetricsMiddleware      — ghi request count + latency           │
│    2. TokenAuthMiddleware    — auth + rate limiter                   │
│                                                                      │
│  Routes:                                                             │
│    GET  /healthz       → PlainTextResponse("OK") — no auth          │
│    POST /mcp           → MCP Streamable HTTP endpoint               │
│    GET  /events/{id}   → SSE event stream (auth qua query param)    │
│                                                                      │
│  MCP Tools (58 tools total):                                        │
│    Core: health_check, probe, basic_runner, smoke, ctf_harness      │
│    Advanced: fallback, shell, workspace, agent, github_ops, runs    │
└──────────────────────────────────────────────────────────────────────┘
```

> 📝 **Cloudflare free tunnel — URL thay đổi mỗi lần restart.**
> `trycloudflare.com` tạo URL ngẫu nhiên mới (`xxx.trycloudflare.com`) mỗi khi tunnel restart.
> ChatGPT connector settings phải cập nhật URL sau mỗi `--restart`.
> Để có URL cố định: dùng `cloudflared tunnel create` + `cloudflared tunnel route dns` (named tunnel).

---

## 2. 🔄 Startup flow

```
Terminal: ./run_mcp_tunnel.sh
            │
            ├─ [nohup] ── start_tunnel_server.sh
            │              (daemonized, thoát terminal được)
            │
            ├─ Kill cũ: lsof port 8000 + cloudflared cũ
            ├─ Log rotation: logs >10MB → .gz
            ├─ install_basic.sh (venv + uv pip install)
            │
            ├─ fastmcp run app/main.py ... → port 8000
            │   ├─ app/mcp_server.py: patch FastMCP
            │   │   - Bỏ check Content-Type / Accept
            │   │   - Inject /healthz route
            │   │   - Inject MetricsMiddleware + TokenAuthMiddleware
            │   │   - Inject SSE /events/ route
            │   ├─ app/config.py: load .env → ~40 config vars
            │   ├─ app/main.py: import tools theo feature flags
            │   │   - Basic: health, probe, basic_runner, smoke, ctf_harness
            │   │   - Nếu ENABLE_ADVANCED: fallback, shell, runs, agent...
            │   └─ mcp.run()
            │
            ├─ Poll socket readiness: 30 lần x 0.5s = max 15s
            ├─ cloudflared tunnel --url http://127.0.0.1:8000
            ├─ Poll URL: 15 lần x 1s = max 15s
            │
            └─ Enter watchdog loop (mỗi 3s)
```

---

## 3. 🛡️ Request flow (từng request)

```
ChatGPT gửi JSON-RPC POST /mcp
  │
  ▼
MetricsMiddleware
  ├─ Ghi start time
  ├─ await app(scope, receive, wrapped_send)
  └─ Khi response: metrics.record_request(path, latency_ms, status)
  │
  ▼
TokenAuthMiddleware
  ├─ Client IP: X-Forwarded-For → scope.client
  ├─ Rate limit check:
  │   └─ sliding window: 200 request / IP / 60s (configurable)
  │       → vượt: trả 429 + Retry-After header
  ├─ Auth check:
  │   └─ Authorization: Bearer <token> hoặc X-Gateway-Token
  │       → sai: trả 401
  │
  ▼
FastMCP dispatch → tool function
  ├─ health_check → { ok: true, metrics: {...} }
  ├─ run_basic_python_solver → subprocess trong venv
  ├─ run_solver_fallback → Docker container lifecycle
  ├─ probe_target → TCP/SSL connect
  └─ ... mỗi tool đều wrap try/except + format_error_response()
```

---

## 4. 🐳 Docker execution flow

```
run_solver_fallback(target, files, language, entrypoint, ...)
  │
  ▼
execute_fallback_solver()
  ├─ Tạo run_id, thư mục runs/<run_id>/
  ├─ Validate + decode files (base64/text)
  ├─ Ghi files vào runs/<run_id>/input/
  │
  ├─ Nếu USE_DOCKER=true:
  │   └─ run_in_docker()
  │       ├─ docker run -d --cap-drop=ALL --security-opt=no-new-privileges
  │       │   --network=bridge (có target) hoặc none (không target)
  │       │   image: ctf-runner:{latest|web|forensics} hoặc ctf-sage-runner
  │       │   cmd: sleep timeout+30
  │       ├─ docker exec python3 solve.py
  │       ├─ subprocess.run(timeout=timeout)
  │       └─ finally: docker kill + docker rm
  │
  ├─ Nếu USE_DOCKER=false:
  │   └─ run_locally() → python3 subprocess trong host venv
  │
  ├─ Truncate output nếu > MAX_OUTPUT_BYTES
  ├─ Ghi stdout.txt, stderr.txt, transcript.txt, metadata.json
  └─ Return { ok, run_id, exit_code, stdout, stderr, ... }
```

---

## 5. 🔄 Watchdog & Recovery

```
start_tunnel_server.sh: watchdog loop (mỗi 3 giây)
  │
  ├─ [1] Server PID alive?
  │   NO  → restart_server("process_died")
  │           ├─ kill old PID, start new fastmcp
  │           ├─ poll socket readiness (15 tries)
  │           ├─ restart counter ≤ 5
  │           └─ counter quá 5 → cleanup + exit(2)
  │
  ├─ [2] Tunnel PID alive?
  │   NO  → restart_tunnel("process_died")
  │           ├─ kill old cloudflared, start new
  │           ├─ poll URL (15 tries)
  │           └─ fail → cleanup
  │
  ├─ [3] Local health check (TCP + /healthz HTTP 200)?
  │   6 lần fail liên tiếp → restart_server("health_check_failed")
  │
  ├─ [4] Tunnel health check (qua curl ${URL}/healthz)?
  │   429 detected  → restart_server("rate_limited")
  │                   + restart_tunnel("rate_limited")
  │   Unreachable   → restart_tunnel("unreachable")
  │
  └─ [5] SIGINT/SIGTERM → cleanup()
                            ├─ kill tunnel
                            ├─ kill server
                            └─ rm PID files
```

### ⚠️ Failure modes & error budget

| Failure scenario | Behavior | Post-mortem |
|:----------------|:---------|:------------|
| Server restart >5 lần nhanh | `cleanup()` → `exit(2)` | Watchdog dừng hẳn. Cần `--restart` thủ công. Kiểm tra `logs/server.log` để tìm nguyên nhân gốc. |
| Tunnel restart >5 lần nhanh | `cleanup()` → `exit(2)` | Như trên. Kiểm tra `logs/cloudflared.log` (network issues, Cloudflare outage). |
| Cloudflare unreachable kéo dài | Watchdog loop restart tunnel forever | Disk sẽ đầy log. Cần can thiệp thủ công: `--stop`, fix network, `--restart`. |
| Health check fail liên tục | `restart_server()` tối đa 5 lần | Nếu restart không fix được → `exit(2)`, cần debug server. |

**Hiện tại không có webhook/alert.** Nếu cần notify khi server crash:
- Viết systemd unit với `Restart=on-failure` thay vì script watchdog
- Hoặc thêm webhook call trong `cleanup()` trước khi `exit(2)`

---

## 6. ⚡ Rate Limiting

```
app/ratelimit.py — SlidingWindowRateLimiter

Cấu hình trong .env:
  RATE_LIMIT_ENABLED=true          # bật/tắt (mặc định false ở code, bật trước khi public!)
  RATE_LIMIT_MAX_REQUESTS=200      # max request per window
  RATE_LIMIT_WINDOW_SECONDS=60     # window (giây)

Luồng:
  1. Mỗi request vào → check IP (từ X-Forwarded-For hoặc scope.client)
  2. Nếu IP đã gửi ≥ max requests trong window → 429 Too Many Requests
     + header: Retry-After: <giây>
  3. TokenAuthMiddleware ghi metrics.record_rate_limit()
```

> **Lưu ý:** Rate limiting **mặc định `false`** trong code (`app/config.py`).
> Cài `.env` `RATE_LIMIT_ENABLED=true` trước khi expose ra internet.

---

## 7. 📊 Metrics

```
app/metrics.py — MetricsTracker (thread-safe, in-memory)

  uptime_seconds      → thời gian server chạy
  total_requests      → tổng số request
  error_count         → số lỗi 5xx
  rate_limit_hits     → số lần bị 429
  avg_latency_ms      → latency trung bình
  tool_calls          → breakdown theo path/tool

Exposed qua:
  • GET /healthz       → "OK" (plain, cho infrastructure)
  • health_check tool  → metrics object

⚠️ In-memory: mất khi server restart. Không dùng để billing.
```

---

## 8. 🔁 Idempotency (Dedup Cache)

```
app/idempotency.py — run_once(key, ttl, fn)

ChatGPT có thể retry requests khi network timeout → cùng một solver chạy nhiều lần.
Idempotency cache giải quyết vấn đề này:
  • Key: SHA-256 của (tool_name + serialized parameters)
  • Cache: Python dict, lock-protected, không dùng Redis
  • TTL: max(30, min(timeout_solver + 15, 180)) giây
  • Scope: per-process. Mỗi lần restart server → cache mới.

Khi nào dùng:
  • run_basic_python_solver — dedup by full payload
  • Các tool GET (health_check, get_capabilities) — không dedup

Cache chỉ áp dụng cho cùng request y hệt. Khác IP, khác timeout → key khác.
```

---

## 9. 🧩 Cấu trúc file (chính)

```
.
├── .env                          # Runtime config
├── Dockerfile                    # Main container (multi-stage, docker CLI)
├── docker-compose.yml            # Orchestration
├── run_mcp_tunnel.sh             # DAEMON — nohup, --status/--stop/--restart
│
├── app/
│   ├── main.py                   # Entrypoint: import tools, log startup
│   ├── mcp_server.py             # FastMCP init, patches, middleware (auth + rate + metrics)
│   ├── config.py                 # ~40 env vars → constants
│   ├── security.py               # Target allowlist, private IP, timeout validation
│   ├── auth.py                   # Constant-time token compare
│   ├── ratelimit.py              # Sliding window rate limiter
│   ├── metrics.py                # Thread-safe request metrics tracker
│   ├── logging_audit.py          # JSON audit log + secret redaction
│   ├── event_bus.py              # Async pub/sub cho SSE events + approval registry
│   ├── sse_events.py             # SSE /events/{goal_id} endpoint (15s heartbeat)
│   ├── docker_runner.py          # Docker container lifecycle (đã đơn giản hóa)
│   ├── runner.py                 # Fallback solver orchestrator
│   ├── file_package.py           # Upload decode + SHA-256
│   ├── idempotency.py            # Request dedup cache (run_once)
│   ├── schemas.py                # Pydantic models
│   ├── transcript.py             # Proof transcript generator
│   ├── agent_paths.py            # Agent workspace boundary enforcement
│   │
│   └── tools/
│       ├── health.py             # health_check, get_capabilities, get_runner_environments
│       ├── probe.py              # TCP/SSL target probe
│       ├── basic_runner.py       # In-venv Python solver
│       ├── smoke.py              # Self-test (health + capabilities + solver)
│       ├── ctf_harness.py        # 9 CTF workflow tools
│       ├── fallback.py           # Docker fallback + validate + upload + rerun
│       ├── shell.py              # Host/workspace command execution
│       ├── runs.py               # Log management
│       ├── workspace.py          # Workspace file CRUD
│       ├── agent.py              # Agent file/command ops
│       └── autonomous_agent.py   # Autonomous CTF solving agent
│
├── runner_images/
│   ├── ctf-runner.Dockerfile     # Consolidated multi-stage (base/web/forensics)
│   └── sage-ctf.Dockerfile       # SageMath (riêng vì ~3GB)
│
├── scripts/
│   ├── start_tunnel_server.sh    # Watchdog: server + tunnel lifecycle
│   ├── restart_server_only.sh    # Kill + start + verify socket
│   ├── build_runner_images.sh    # Docker build (1 lệnh)
│   ├── install_basic.sh          # venv + pip install
│   ├── install_advanced_tools.sh # Build images + enable flag
│   └── install_ctf_tools_min.sh # apt/pip CTF tools
│
├── tests/                        # pytest, 77 tests
└── logs/
    ├── server.log                # FastMCP stdout
    ├── cloudflared.log           # Tunnel output
    ├── gateway.log               # Audit events
    ├── launcher.log              # Daemon output
    ├── restart_count             # Restart counter (tự xóa sau)
    ├── server.pid / tunnel.pid / launcher.pid
    └── runs/ / artifacts/ / workspaces/
```

### Chi tiết một số module ít rõ

| File | Vai trò | Ghi chú |
|------|---------|---------|
| `event_bus.py` | Pub/sub cho SSE event streaming + **approval registry** | `register_approval(goal_id)` tạo Future, `resolve_approval(goal_id, bool)` set result thread-safe. Dùng cho autonomous agent approval workflow (agent approve/reject step). |
| `autonomous_agent.py` | Autonomous CTF agent: goal creation, step execution, budget tracking, approval gates | 10 tools: agent_goal_create, agent_step, agent_approve, agent_report... Xem §12. |
| `idempotency.py` | Short-lived dedup cache | Tránh chạy solver 2 lần khi ChatGPT retry. TTL động theo timeout. |

---

## 10. ⚙️ Configuration Reference (.env)

### Authentication
| Var | Default | Mô tả |
|-----|---------|-------|
| `GATEWAY_TOKEN` | `""` | Token auth cho MCP |
| `REQUIRE_AUTH` | `true` | Bắt buộc token |

### Network
| Var | Default | Mô tả |
|-----|---------|-------|
| `MCP_BIND_HOST` | `0.0.0.0` | Bind interface |
| `MCP_PORT` | `8000` | HTTP port |
| `ALLOWED_TCP_TARGETS` | `[]` | Allowlist host:port |
| `BLOCK_PRIVATE_IPS` | `true` | Chặn IP private |

### Rate Limiting (mặc định **tắt** — bật trước khi public)
| Var | Default | Mô tả |
|-----|---------|-------|
| `RATE_LIMIT_ENABLED` | `false` | Bật rate limit |
| `RATE_LIMIT_MAX_REQUESTS` | `200` | Max request / window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window (giây) |

### Security
| Var | Default | Mô tả |
|-----|---------|-------|
| `DISABLE_SECURITY_POLICIES` | `false` | ⚠️ **Bypass TẤT CẢ policy — chỉ dev/test, KHÔNG bật trên internet** |
| `ENABLE_EGRESS_FIREWALL` | `false` | iptables (không còn dùng) |

### Docker Runners
| Var | Default | Mô tả |
|-----|---------|-------|
| `RUNNER_IMAGE_PYTHON` | `ctf-runner:latest` | Image cho python/pwn |
| `RUNNER_IMAGE_WEB` | `ctf-runner:web` | Image cho web CTF |
| `RUNNER_IMAGE_FORENSICS` | `ctf-runner:forensics` | Image cho forensics |
| `RUNNER_IMAGE_SAGE` | `ctf-sage-runner:latest` | Image cho sage |
| `DOCKER_MEMORY` | `512m` | RAM giới hạn |
| `DOCKER_CPUS` | `1` | CPU giới hạn |

### Limits
| Var | Default | Mô tả |
|-----|---------|-------|
| `MAX_TIMEOUT_SECONDS` | `60` | Timeout ceiling |
| `MAX_CODE_BYTES` | `5000000` | Max upload size |
| `MAX_OUTPUT_BYTES` | `500000` | Max stdout/stderr |

### Feature Flags
| Flag | Default | Mô tả |
|------|---------|-------|
| `ENABLE_ADVANCED_TOOLS` | `false` | Docker runner + shell + runs |
| `ENABLE_AGENT_TOOLS` | `true` | File/command agent tools |
| `ENABLE_WORKSPACE_TOOLS` | `false` | Workspace CRUD |

---

## 11. 🚀 Operation Commands

```bash
# === DAEMON ===
./run_mcp_tunnel.sh               # Khởi động (background, thoát terminal OK)
./run_mcp_tunnel.sh --status      # Xem PID + endpoint URL
./run_mcp_tunnel.sh --stop        # Dừng
./run_mcp_tunnel.sh --restart     # Khởi động lại

# === Developer ===
./scripts/restart_server_only.sh  # Restart server, giữ tunnel
./scripts/build_runner_images.sh  # Build Docker runner images

# === Test ===
.venv/bin/python -m pytest tests -q           # Full suite
DISABLE_SECURITY_POLICIES=false ALLOWED_TCP_TARGETS=1.1.1.1:80 \
  .venv/bin/python -m pytest tests -q         # Với security checks

# === Debug ===
tail -f logs/launcher.log        # Daemon log
tail -f logs/server.log           # Server stdout
tail -f logs/gateway.log          # Audit events
tail -f logs/cloudflared.log      # Tunnel log
curl http://127.0.0.1:8000/healthz  # Health check (local)

# === Auth check ===
# Verify token auth đang hoạt động
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/healthz
# Nếu có token → OK. Nếu sai token → 401. Nếu REQUIRE_AUTH=false → OK luôn.
```

---

## 12. 📌 CTF Solve Flow (với error paths)

```
1. ChatGPT gọi ctf_harness_init → tạo workspace
   └─ FAIL → báo MCP server not ready / workspace conflict

2. ChatGPT gọi ctf_harness_check + probe_target → check target alive
   ├─ OK → tiếp bước 3
   └─ UNREACHABLE → dừng, báo target không reachable
        └─ User kiểm tra lại network / target host:port

3. User upload solve.py → run_basic_python_solver (host venv, nhanh)
   ├─ OK (exit_code=0 + có flag output) → tiếp bước 5
   ├─ OK (exit_code=0 + không flag) → solver không tìm thấy flag, cần sửa
   └─ FAIL (timeout / crash) → thử run_solver_fallback (Docker isolation)
        ├─ OK → tiếp bước 5
        └─ FAIL → ctf_harness_report với status=failed + logs

4. (Nếu cần Docker isolation mà step 3 OK) → run_solver_fallback

5. ChatGPT gọi ctf_harness_verify → kiểm tra flag
   ├─ FLAG MATCH → tiếp bước 6
   └─ FLAG MISMATCH → retry với solver khác hoặc báo unsolved

6. ChatGPT gọi ctf_harness_report → tạo proof bundle
   ├─ OK → done
   └─ FAIL → kiểm tra workspace permissions
```

---

## 13. 🤖 Autonomous Agent Flow

Dùng cho CTF solve tự động không cần can thiệp tay từng bước.

```
1. agent_goal_create(toolchain="ctf", cwd="...", budget=50)
   → Tạo goal với trạng thái, budget steps, toolchain config

2. agent_goal_start(goal_id) → bắt đầu execution
   → Chuyển goal sang RUNNING

3. agent_step(goal_id) vòng lặp:
   ├─ LLM quyết định bước tiếp theo dựa trên trạng thái hiện tại
   ├─ Thực thi command / solver
   ├─ Ghi kết quả vào goal
   ├─ Nếu cần human approval → agent_approve / agent_reject
   └─ Lặp đến khi hết budget hoặc tìm thấy flag

4. agent_status(goal_id) → kiểm tra progress giữa chừng
5. agent_report(goal_id) → kết thúc, xuất report + transcript
6. agent_cancel(goal_id) → hủy giữa chừng nếu sai hướng
```

**Approval registry** (`event_bus.py`): `register_approval()` tạo Future blocking,
`resolve_approval()` set result từ SSE handler → agent step đợi human confirm
trước khi thực thi các bước nguy hiểm.

---

## 14. 📦 Docker Images

### Consolidated Runner (`runner_images/ctf-runner.Dockerfile`)

Một Dockerfile multi-stage, 3 tags:

| Tag | Stage | Base | Nội dung | Dung tích ~ |
|-----|-------|------|----------|-------------|
| `ctf-runner:latest` | `base` | python:3.12-slim | Python + pwntools + crypto + OS tools | 800MB |
| `ctf-runner:web` | `with-web` | base | + Playwright + CloakBrowser | 1.5GB |
| `ctf-runner:forensics` | `forensics` | ubuntu:24.04 | + volatility + binwalk + sleuthkit | 2GB |

Build: `./scripts/build_runner_images.sh`

### SageMath (riêng)

`ctf-sage-runner:latest` — Dockerfile riêng vì SageMath ~3GB, không gộp được.
Build thủ công: `docker build --load -t ctf-sage-runner:latest -f runner_images/sage-ctf.Dockerfile .`
