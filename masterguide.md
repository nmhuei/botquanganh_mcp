# Master Guide: Fallback Runner MCP

Tài liệu này hướng dẫn cách cài, chạy và nối **Fallback Runner MCP** với ChatGPT qua máy của bạn.

Mục tiêu hiện tại:
- **Basic mode**: nhẹ, để ChatGPT connect tới server MCP, kiểm tra target/server, và chạy solver Python pwn/web cơ bản qua máy bạn.
- **Advanced mode**: cài thêm Docker runner images để chạy solver, workspace, log, shell command trong container.

---

## 1. Hai Chế Độ Tool

### 1.1 Basic Mode

Basic mode là mặc định. Không cần build Docker image.

Tool basic hiện có:

```text
health_check
get_capabilities
check_target_allowed
probe_target_from_runner
run_basic_python_solver
run_safe_smoke_test
```

Ý nghĩa:
- `health_check`: kiểm tra MCP server còn sống.
- `get_capabilities`: xem server đang basic hay advanced.
- `check_target_allowed`: kiểm tra host:port có được phép probe không.
- `probe_target_from_runner`: thử DNS/TCP/TLS/banner tới target qua máy bạn.
- `run_basic_python_solver`: chạy solver Python nhẹ trong `.venv` host, phù hợp pwn/web cơ bản.
- `run_safe_smoke_test`: test nhanh server/capabilities/basic solver bằng một call, không Docker, không connect target.

Basic packages cho solver:

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

`run_basic_python_solver` chấp nhận file dùng `path` hoặc `name`. Nếu truyền `content` mà thiếu `encoding`, server tự hiểu là `encoding="text"`. Khi chạy solver connect thật, truyền `target={"host": "...", "port": ...}`; target đó phải nằm trong `ALLOWED_TCP_TARGETS`. Solver sẽ nhận `TARGET_HOST` và `TARGET_PORT` qua environment. Nếu chỉ test import/package thì có thể bỏ `target`.

Basic phù hợp khi bạn gặp bài liên quan tới server/network/pwn/web và muốn ChatGPT dùng máy bạn để connect thật, chạy solver nhẹ thật.

### 1.2 Advanced Mode

Advanced mode bật sau khi chạy:

```bash
./scripts/install_advanced_tools.sh
```

Tool advanced sẽ có thêm:

```text
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

Advanced cần Docker và sẽ build các image:

```text
ctf-python-runner:latest
ctf-pwn-runner:latest
ctf-sage-runner:latest
ctf-forensics-runner:latest
```

---

## 2. Cài Đặt Basic

Chạy từ thư mục repo:

```bash
cd /home/light/Workspace/agy/botquanganh_mcp
chmod +x scripts/*.sh
./scripts/install_basic.sh
```

Script này sẽ:
- tạo `.venv` nếu chưa có,
- cài dependency Python basic bằng `uv pip install -r requirements.txt`, gồm package pwn/web phổ biến,
- tạo `.env` từ `.env.example` nếu chưa có.

Không build Docker image.

---

## 3. Cấu Hình `.env`

Các biến quan trọng:

```env
MCP_BIND_HOST=0.0.0.0
MCP_PORT=8000
ENABLE_ADVANCED_TOOLS=false
ALLOWED_TCP_TARGETS=example.com:443,host.example:31337
BLOCK_PRIVATE_IPS=true
```

### 3.1 `ENABLE_ADVANCED_TOOLS`

Basic mode:

```env
ENABLE_ADVANCED_TOOLS=false
```

Advanced mode:

```env
ENABLE_ADVANCED_TOOLS=true
```

`install_advanced_tools.sh` sẽ tự bật biến này.

### 3.2 `ALLOWED_TCP_TARGETS`

Đây là allowlist cho tool `check_target_allowed` và `probe_target_from_runner`.

Ví dụ chỉ cho phép vài target:

```env
ALLOWED_TCP_TARGETS=socket.cryptohack.org:13418,example.com:443
```

Cho phép mọi target:

```env
ALLOWED_TCP_TARGETS=*
```

Chỉ dùng `*` khi bạn hiểu rủi ro. Server này chạy qua máy bạn, nên allowlist càng cụ thể càng an toàn.

### 3.3 `BLOCK_PRIVATE_IPS`

Khuyến nghị:

```env
BLOCK_PRIVATE_IPS=true
```

Biến này chặn probe tới localhost/private IP như `127.0.0.1`, `192.168.x.x`, `10.x.x.x`, trừ khi target local được allowlist rõ cho mục đích test.

---

## 4. Chạy Server Và Tunnel

Chạy server kèm Cloudflare Tunnel:

```bash
./scripts/start_tunnel_server.sh
```

Script sẽ:
- đảm bảo basic install đã sẵn sàng,
- start FastMCP HTTP server ở `127.0.0.1:8000`,
- mở TryCloudflare tunnel,
- in endpoint dạng:

```text
https://xxxx.trycloudflare.com/mcp
```

Dùng URL đó để tạo MCP connector trong ChatGPT.

Dừng server:

```text
Ctrl+C
```

---

## 5. Nối Với ChatGPT

Trong ChatGPT:

1. Vào phần tạo hoặc chỉnh GPT/Connector.
2. Thêm MCP Connector.
3. Dán URL tunnel, ví dụ:

```text
https://xxxx.trycloudflare.com/mcp
```

4. Lưu connector.
5. Test bằng tool `health_check`.

Nếu basic mode hoạt động đúng, ChatGPT sẽ thấy 5 tool:

```text
health_check
get_capabilities
check_target_allowed
probe_target_from_runner
run_basic_python_solver
```

---

## 6. Khi Nào Cần Advanced

Dùng advanced khi bạn muốn ChatGPT:
- chạy solver script qua Docker,
- chạy Sage/PWN/Python CTF environment,
- upload/read workspace file,
- chạy command trong container,
- xem stdout/stderr/log của các lần chạy.

Cài advanced:

```bash
./scripts/install_advanced_tools.sh
```

Sau khi xong, restart server:

```bash
./scripts/start_tunnel_server.sh
```

---

## 7. Kiểm Tra Nhanh

Kiểm tra test suite:

```bash
./scripts/test.sh
```

Xem process server/tunnel:

```bash
ps aux | grep -E 'fastmcp|cloudflared'
```

Xem log server:

```bash
tail -n 80 logs/server.log
```

Kiểm tra Docker image advanced:

```bash
docker images | grep 'ctf-.*runner'
```

---

## 8. Workflow Gợi Ý

### Chỉ cần ChatGPT probe server qua máy bạn

```bash
./scripts/install_basic.sh
./scripts/start_tunnel_server.sh
```

Cấu hình target trong `.env`:

```env
ALLOWED_TCP_TARGETS=target.host:port
ENABLE_ADVANCED_TOOLS=false
```

### Cần ChatGPT chạy solver pwn/web nhẹ

Vẫn dùng basic:

```bash
./scripts/install_basic.sh
./scripts/start_tunnel_server.sh
```

Solver Python có thể import `pwn`, `requests`, `bs4`, `Crypto`, `z3`, `sympy`, `gmpy2`, `websocket`.

### Cần chạy solver/container

```bash
./scripts/install_advanced_tools.sh
./scripts/start_tunnel_server.sh
```

---

## 9. Ghi Chú Bảo Mật

- Đừng dùng `ALLOWED_TCP_TARGETS=*` lâu dài nếu không cần.
- Giữ `BLOCK_PRIVATE_IPS=true` trừ khi bạn đang test local có chủ đích.
- Basic mode không chạy Docker command, không có workspace, không có shell tool. Nó chỉ chạy Python solver trong `.venv` host với timeout và allowlist target.
- Advanced mode mạnh hơn, nên chỉ bật khi cần.
