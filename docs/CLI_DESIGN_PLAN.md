# CLI Design Plan

## 1. Mục tiêu

Thiết kế một CLI thống nhất cho repo `botquanganh_mcp`, phục vụ cả hai nhóm nhu cầu:

1. Vận hành local service, server bridge và Cloudflare Tunnel.
2. Gọi các chức năng Host MCP/REST từ terminal mà không cần viết `curl` thủ công.

Tên lệnh đề xuất:

```text
bqa
```

CLI phải ưu tiên:

- dễ nhớ;
- output rõ ràng;
- exit code đúng semantics;
- hỗ trợ JSON để dùng trong script;
- không restart tunnel khi chỉ thay đổi hoặc restart server;
- không phá vỡ 12 MCP tools và REST API hiện tại;
- không tạo thêm một lớp business logic độc lập với core host service.

---

## 2. Nguyên tắc thiết kế

### 2.1. Một CLI, hai execution mode

CLI có hai nhóm lệnh:

#### Local operations

Chạy trực tiếp trên máy host và quản lý process/file runtime:

```text
bqa start
bqa stop
bqa restart
bqa status
bqa url
bqa server restart
bqa logs
bqa config
```

#### API operations

Gọi REST API hiện có:

```text
bqa health
bqa capabilities
bqa fs ...
bqa cmd ...
bqa knowledge ...
```

Mặc định API mode gọi local server:

```text
http://127.0.0.1:8000
```

Có thể chuyển sang tunnel hiện tại:

```text
bqa --public health
```

Hoặc chỉ định URL cụ thể:

```text
bqa --base-url https://example.trycloudflare.com health
```

### 2.2. Không duplicate core logic

CLI không tự triển khai lại logic:

- path boundary;
- file read/write/search;
- command policy;
- command execution;
- inventory;
- knowledge;
- authentication.

Các chức năng này phải gọi lại REST API hoặc các script lifecycle chính thức.

### 2.3. JSON-first nhưng human-friendly

Mỗi lệnh hỗ trợ:

```text
--json
```

Mặc định output tối ưu cho người đọc. Khi có `--json`, stdout chỉ chứa JSON hợp lệ để dùng với `jq` hoặc script CI.

### 2.4. Exit code có ý nghĩa

Đề xuất:

```text
0   Thành công
1   Operation thất bại
2   Sai tham số CLI
3   Không kết nối được server
4   Authentication thất bại
5   Operation bị policy chặn
6   Resource không tồn tại
7   Timeout
8   Conflict, ví dụ file đã tồn tại
```

Command được chạy thành công ở phía server nhưng trả exit code khác `0` phải giữ nguyên semantics của command, không coi là lỗi server.

---

## 3. Cây lệnh đề xuất

```text
bqa
├── start
├── stop
├── restart
├── status
├── url
├── server
│   ├── restart
│   └── status
├── health
├── capabilities
├── fs
│   ├── ls
│   ├── cat
│   ├── write
│   ├── append
│   ├── replace
│   ├── mkdir
│   └── search
├── cmd
│   ├── check
│   └── run
├── knowledge
│   ├── overview
│   ├── guide
│   ├── tools
│   ├── search
│   └── all
├── logs
│   ├── server
│   ├── tunnel
│   ├── launcher
│   ├── audit
│   └── follow
├── config
│   ├── show
│   ├── get
│   ├── path
│   └── validate
├── doctor
├── completion
│   ├── bash
│   ├── zsh
│   └── fish
└── version
```

---

## 4. Chi tiết từng nhóm lệnh

## 4.1. Lifecycle

### `bqa start`

Tương đương:

```bash
./run_mcp_tunnel.sh start
```

Yêu cầu:

- idempotent;
- không tạo tunnel thứ hai nếu supervisor đang chạy;
- in URL ngay khi Cloudflare cấp URL;
- không đợi bridge ready mới in URL;
- không đọc URL cũ từ log.

### `bqa stop`

Tương đương:

```bash
./run_mcp_tunnel.sh stop
```

Phải dừng supervisor trước, sau đó mới dừng tunnel và server.

### `bqa restart`

Restart toàn bộ supervisor/server/tunnel.

Lệnh này phải có cảnh báo rõ rằng Quick Tunnel có thể cấp URL mới.

Đề xuất yêu cầu xác nhận khi chạy interactive:

```text
This may replace the current Cloudflare URL. Continue? [y/N]
```

Có thể bỏ qua xác nhận bằng:

```text
--yes
```

### `bqa server restart`

Tương đương:

```bash
./scripts/restart_server_only.sh
```

Đây là lệnh mặc định sau thay đổi code thông thường.

Yêu cầu:

- không restart tunnel;
- kiểm tra tunnel PID trước và sau;
- cảnh báo nếu tunnel PID thay đổi ngoài dự kiến;
- xác minh bridge socket ready.

### `bqa status`

Output đề xuất:

```text
Supervisor  running   pid=65413
Server      running   pid=76445
Tunnel      running   pid=65323
Bridge      ready
URL         https://example.trycloudflare.com/mcp
Auth        disabled
Workspace   /home/light/GitHub
```

Với `--json`:

```json
{
  "ok": true,
  "supervisor": {"running": true, "pid": 65413},
  "server": {"running": true, "pid": 76445},
  "tunnel": {"running": true, "pid": 65323},
  "bridge": "ready",
  "url": "https://example.trycloudflare.com/mcp",
  "auth_required": false,
  "workspace": "/home/light/GitHub"
}
```

---

## 4.2. Health và capabilities

### `bqa health`

Gọi:

```text
GET /api/v1/health
```

Output human-readable:

```text
Service       botquanganh-host-mcp
Version       1.0.0
Status        healthy
Uptime        12m 31s
Requests      120
Errors        0
Avg latency   1.2 ms
```

### `bqa capabilities`

Gọi:

```text
GET /api/v1/capabilities
```

Có thể lọc:

```text
bqa capabilities --tools
bqa capabilities --limits
bqa capabilities --host
```

---

## 4.3. File system

### `bqa fs ls`

```bash
bqa fs ls GitHub
bqa fs ls GitHub --max 100
bqa fs ls GitHub --json
```

Gọi:

```text
GET /api/v1/files
```

### `bqa fs cat`

```bash
bqa fs cat GitHub/project/README.md
bqa fs cat file.txt --lines 20:50
bqa fs cat file.txt --max-bytes 100000
```

Gọi:

```text
GET /api/v1/files/content
```

Quy ước `--lines`:

```text
20:50
20:
:50
20
```

### `bqa fs write`

Hỗ trợ ba nguồn nội dung:

```bash
bqa fs write path.txt --text "hello"
bqa fs write path.txt --from local.txt
printf 'hello' | bqa fs write path.txt --stdin
```

Flag:

```text
--no-overwrite
--no-create-parents
```

### `bqa fs append`

```bash
bqa fs append path.txt --text "next line"
printf 'next line' | bqa fs append path.txt --stdin
```

### `bqa fs replace`

```bash
bqa fs replace path.txt --old "before" --new "after"
bqa fs replace path.txt --old-file old.txt --new-file new.txt
bqa fs replace path.txt --expected-count 1
```

### `bqa fs mkdir`

```bash
bqa fs mkdir project/data
bqa fs mkdir project/data --no-parents
```

### `bqa fs search`

```bash
bqa fs search "FastMCP" --path GitHub/botquanganh_mcp
bqa fs search "REQUIRE_AUTH" --case-sensitive --max 50
```

---

## 4.4. Command execution

### `bqa cmd check`

```bash
bqa cmd check 'git status --short'
```

Output:

```text
Allowed       yes
Policy        guarded
Commands      git
Severity      none
```

Nếu bị chặn:

```text
Allowed       no
Rule          privilege_escalation
Message       Privilege escalation is blocked through MCP host tools.
```

### `bqa cmd run`

```bash
bqa cmd run 'git status --short' --cwd GitHub/botquanganh_mcp
bqa cmd run --timeout 60 'pytest -q'
```

Quy tắc output:

- stdout của command in ra stdout;
- stderr của command in ra stderr;
- metadata chỉ in khi dùng `--verbose`;
- `--json` trả toàn bộ response envelope;
- exit code CLI mặc định phản ánh exit code command nếu request được xử lý thành công;
- lỗi server, policy hoặc timeout dùng exit code riêng của CLI.

Đề xuất thêm:

```text
--check-first
```

để gọi command policy endpoint trước khi thực thi.

---

## 4.5. Knowledge và inventory

### `bqa knowledge overview`

```bash
bqa knowledge overview
```

### `bqa knowledge guide`

```bash
bqa knowledge guide
bqa knowledge guide --query docker
```

### `bqa knowledge tools`

```bash
bqa knowledge tools
bqa knowledge tools --query python
bqa knowledge tools --category security
bqa knowledge tools --versions
bqa knowledge tools --all
bqa knowledge tools --uncatalogued
bqa knowledge tools --refresh
```

### `bqa knowledge search`

```bash
bqa knowledge search docker
```

Tìm đồng thời trong guide và tool inventory.

---

## 4.6. Logs

```bash
bqa logs server
bqa logs tunnel
bqa logs launcher
bqa logs audit
bqa logs follow server
bqa logs follow --all
```

Flag:

```text
-n, --lines 100
-f, --follow
--since 10m
--grep ERROR
```

CLI chỉ đọc file log local. Không cung cấp thao tác xóa log mặc định.

---

## 4.7. Config

### `bqa config show`

Chỉ hiển thị các cấu hình không nhạy cảm và che secret:

```text
MCP_BIND_HOST=127.0.0.1
MCP_PORT=8000
REQUIRE_AUTH=false
GATEWAY_TOKEN=********
HOST_WORKSPACE_DIR=/home/light/GitHub
HOST_COMMAND_POLICY=guarded
```

### `bqa config get`

```bash
bqa config get HOST_WORKSPACE_DIR
```

Không được in giá trị thật của `GATEWAY_TOKEN` trừ khi có flag rõ ràng, và mặc định không nên hỗ trợ flag đó.

### `bqa config path`

```text
/home/light/GitHub/botquanganh_mcp/.env
```

### `bqa config validate`

Kiểm tra:

- `.env` tồn tại;
- port hợp lệ;
- workspace tồn tại;
- knowledge directory tồn tại;
- command policy hợp lệ;
- auth/token nhất quán;
- `cloudflared` tồn tại nếu dùng tunnel;
- `.venv/bin/fastmcp` tồn tại;
- PID file có stale PID hay không.

---

## 4.8. Doctor

```bash
bqa doctor
```

Thực hiện một bộ kiểm tra không phá hoại:

1. Kiểm tra Python virtual environment.
2. Kiểm tra `fastmcp` và `cloudflared`.
3. Validate `.env`.
4. Kiểm tra PID file.
5. Kiểm tra bridge socket.
6. Gọi local `/healthz`.
7. Gọi local REST health.
8. Nếu tunnel đang chạy, gọi public REST health.
9. Nếu có URL, kiểm tra MCP initialize.
10. Cảnh báo auth đang tắt khi endpoint public.

Output:

```text
PASS  virtualenv
PASS  fastmcp
PASS  cloudflared
PASS  config
PASS  bridge socket
PASS  local REST
PASS  public REST
PASS  MCP initialize
WARN  public endpoint has REQUIRE_AUTH=false
```

`doctor` không tự sửa cấu hình và không restart process.

---

## 5. Global options

```text
--base-url URL
--public
--local
--token TOKEN
--token-file PATH
--timeout SECONDS
--json
--no-color
--verbose
--quiet
--version
-h, --help
```

Ưu tiên lấy token theo thứ tự:

1. `--token`.
2. `--token-file`.
3. `BQA_TOKEN`.
4. `GATEWAY_TOKEN` trong environment.
5. `.env` của repo.

Token không được xuất hiện trong error message, debug log hoặc command history do CLI tự tạo.

---

## 6. Kiến trúc code đề xuất

```text
app/
└── cli/
    ├── __init__.py
    ├── main.py
    ├── parser.py
    ├── context.py
    ├── client.py
    ├── output.py
    ├── errors.py
    ├── lifecycle.py
    ├── config_view.py
    └── commands/
        ├── health.py
        ├── filesystem.py
        ├── command.py
        ├── knowledge.py
        ├── logs.py
        ├── config.py
        └── doctor.py

bin/
└── bqa

tests/
├── test_cli_parser.py
├── test_cli_output.py
├── test_cli_client.py
├── test_cli_lifecycle.py
└── test_cli_integration.py
```

### `app/cli/parser.py`

Dùng `argparse` trong standard library để tránh thêm dependency runtime chỉ cho CLI.

### `app/cli/client.py`

REST client dùng `urllib.request` trong standard library.

Trách nhiệm:

- resolve base URL;
- thêm auth header;
- encode query;
- encode/decode JSON;
- timeout;
- map HTTP error sang CLI exception;
- không retry các thao tác ghi mặc định.

### `app/cli/output.py`

Trách nhiệm:

- human-readable rendering;
- JSON rendering;
- stderr/stdout separation;
- color chỉ khi terminal hỗ trợ;
- không color khi pipe hoặc có `NO_COLOR`.

### `app/cli/lifecycle.py`

Chỉ wrap các script chính thức:

```text
run_mcp_tunnel.sh
scripts/restart_server_only.sh
```

Không copy logic process management vào Python.

---

## 7. Packaging và executable

Repo hiện chưa có `pyproject.toml`. Có hai bước triển khai:

### Giai đoạn đầu

Tạo wrapper:

```text
bin/bqa
```

Wrapper gọi:

```bash
exec "$ROOT_DIR/.venv/bin/python" -m app.cli.main "$@"
```

Người dùng có thể chạy:

```bash
./bin/bqa status
```

Có thể tạo symlink local:

```bash
ln -s /home/light/GitHub/botquanganh_mcp/bin/bqa ~/.local/bin/bqa
```

### Giai đoạn packaging

Thêm `pyproject.toml` và console entry point:

```toml
[project.scripts]
bqa = "app.cli.main:main"
```

Sau đó:

```bash
pip install -e .
```

Không bắt buộc packaging ngay trong phiên bản CLI đầu tiên.

---

## 8. UX và output conventions

### Thành công

```text
[+] Host MCP server restarted.
```

### Thông tin

```text
[i] Tunnel was not restarted.
```

### Cảnh báo

```text
[!] Public endpoint is running without authentication.
```

### Lỗi

```text
[-] Unable to connect to http://127.0.0.1:8000.
```

Khi stdout đang được pipe, prefix và màu có thể được loại bỏ để output dễ parse.

---

## 9. Testing plan

## 9.1. Unit tests

### Parser

- mọi command/subcommand;
- required argument;
- alias;
- conflicting flags;
- `--json`;
- `--public` và `--base-url`;
- line range parser.

### REST client

- URL join;
- query encoding;
- auth header;
- JSON response;
- invalid JSON;
- HTTP 400/401/403/404/408/409/429/500;
- network timeout;
- connection refused.

### Output

- human mode;
- JSON mode;
- secret redaction;
- command stdout/stderr;
- no-color mode.

### Lifecycle

- script mapping;
- server-only restart không gọi tunnel restart;
- full restart yêu cầu xác nhận;
- PID và URL checks.

## 9.2. Integration tests

Dùng Starlette TestClient hoặc isolated local server:

- health;
- capabilities;
- fs lifecycle;
- command check/run;
- knowledge;
- auth enabled/disabled;
- exit code mapping.

## 9.3. Manual regression

```text
PASS: bqa status
PASS: bqa health
PASS: bqa --public health
PASS: bqa fs ls
PASS: bqa fs cat
PASS: bqa fs write/append/replace/search
PASS: bqa cmd check
PASS: bqa cmd run success
PASS: bqa cmd run non-zero exit
PASS: bqa cmd run timeout
PASS: bqa knowledge tools
PASS: bqa logs server
PASS: bqa config validate
PASS: bqa doctor
PASS: bqa server restart preserves tunnel PID and URL
PASS: bqa start is idempotent
```

---

## 10. Lộ trình triển khai

### Phase 1 — Core CLI foundation

- `app/cli/main.py`;
- parser;
- context;
- REST client;
- error mapping;
- output formatter;
- `bin/bqa`;
- `version`, `health`, `capabilities`.

### Phase 2 — Host operations

- `fs`;
- `cmd`;
- `knowledge`;
- tests cho API commands.

### Phase 3 — Lifecycle operations

- `start`;
- `stop`;
- `restart`;
- `status`;
- `url`;
- `server restart`;
- xác minh giữ nguyên tunnel khi restart server.

### Phase 4 — Operations UX

- `logs`;
- `config`;
- `doctor`;
- shell completion;
- README examples.

### Phase 5 — Packaging

- `pyproject.toml`;
- editable install;
- version metadata;
- optional release artifact.

---

## 11. Tiêu chí nghiệm thu

CLI được coi là hoàn thành bản v1 khi:

1. `bqa --help` hiển thị đầy đủ command tree.
2. `bqa health` gọi được local REST API.
3. `bqa --public health` dùng đúng URL trong `logs/tunnel_url.txt`.
4. `bqa fs` bao phủ đầy đủ file REST endpoints.
5. `bqa cmd` giữ đúng command exit code semantics.
6. `bqa knowledge` bao phủ đủ các section hiện tại.
7. `bqa server restart` không đổi tunnel PID hoặc URL.
8. `bqa restart` cảnh báo URL tunnel có thể thay đổi.
9. `bqa status --json` trả JSON hợp lệ.
10. Token luôn được che trong output và logs.
11. Toàn bộ test cũ vẫn pass.
12. Test CLI mới pass.
13. Manual regression qua local và public URL pass.
14. Không restart tunnel trong quá trình triển khai thông thường.

---

## 12. Phạm vi ngoài bản v1

Chưa triển khai trong CLI v1:

- interactive TUI;
- remote file upload binary;
- websocket/SSE monitor;
- tự động rotate token;
- tự động deploy production;
- quản lý nhiều remote profile phức tạp;
- plugin system;
- tự động sửa `.env` mà không có lệnh rõ ràng từ người dùng.

Các phần này có thể được xem xét cho v2 sau khi CLI v1 ổn định.


---

## 13. Trạng thái triển khai

Cập nhật ngày 20/07/2026: toàn bộ Phase 1–5 đã được triển khai.

### Phase 1 — Core CLI foundation: DONE

- `app/cli/main.py`;
- parser và global option normalization;
- context/base URL/token resolution;
- REST client dùng standard library;
- error mapping và exit codes;
- output human/JSON, color và secret redaction;
- `version`, `health`, `capabilities`;
- executable `bin/bqa`.

### Phase 2 — Host operations: DONE

- toàn bộ `fs` commands;
- `cmd check` và `cmd run`;
- bảo toàn command exit code khi REST hiện map command failure thành HTTP 500;
- toàn bộ `knowledge` sections;
- unit và integration tests.

### Phase 3 — Lifecycle operations: DONE

- `start`, `stop`, `restart`, `status`, `url`;
- `server restart` và `server status`;
- full restart yêu cầu xác nhận hoặc `--yes`;
- server-only restart xác minh tunnel PID và URL trước/sau;
- status chỉ dùng canonical URL file, không đọc URL từ log cũ.

### Phase 4 — Operations UX: DONE

- logs: targets, tail, follow, grep, since và JSON;
- config: show, get, path và validate;
- doctor: local/public REST và MCP initialize;
- completion: Bash, Zsh và Fish;
- README examples;
- automated manual regression script.

### Phase 5 — Packaging: DONE

- `pyproject.toml`;
- console entry point `bqa`;
- editable install;
- `install_basic.sh` tự cài CLI;
- `.gitignore` cho packaging artifacts.

### Điều chỉnh so với thiết kế ban đầu

Global HTTP timeout dùng tên:

```text
--request-timeout
```

thay vì global `--timeout`, để tránh xung đột với:

```text
bqa cmd run --timeout <command-timeout>
```

### Kết quả nghiệm thu

- pytest: `37 passed`;
- manual regression: `18/18 PASS`;
- marker: `ALL_CLI_MANUAL_TESTS=PASS`;
- server-only restart thật giữ nguyên tunnel PID và URL;
- full stop/restart chỉ được chạy trong môi trường cô lập;
- không restart Cloudflare Tunnel thật trong quá trình triển khai.

Chi tiết xem:

- `docs/CLI_MANUAL_TEST_PLAN.md`;
- `docs/CLI_IMPLEMENTATION_REPORT.md`;
- `scripts/manual_test_cli.sh`.
