# BotQuangAnh Host MCP

MCP server tối giản để ChatGPT thao tác trực tiếp trên máy của bạn trong phạm vi `HOST_WORKSPACE_DIR`.

Repo này chỉ còn hai chức năng chính:

1. Đọc, ghi, tìm kiếm file và chạy command trên host.
2. Cung cấp hướng dẫn làm việc cùng danh mục tool thực tế có trong máy qua `host_knowledge`.

## Cấu trúc

```text
app/
├── host/                 # Logic file, command, policy và tool inventory
├── tools/                # MCP adapters: health, host, host_knowledge
├── config.py
├── mcp_server.py
└── main.py

knowledge/
├── WORKING_GUIDE.md
├── HOST_ENVIRONMENT.md
└── TOOL_CATALOG.json

install.sh
scripts/
├── install_basic.sh
├── install_cli.sh
├── uninstall_cli.sh
├── restart_server_only.sh
├── start_tunnel_server.sh
├── dev.sh
└── test.sh
```

## Cài đặt

### 1. One-line Install (khuyên dùng)

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | bash
```

Script mặc định clone nhánh `main` vào `~/.botquanganh_mcp`, tạo `.venv`, cài dependencies, tạo `.env` với quyền `600`, rồi liên kết CLI tại `~/.local/bin/bqa`. Chạy lại cùng lệnh sẽ cập nhật installation bằng fast-forward; nếu working tree có file chưa commit, installer sẽ dừng để tránh ghi đè dữ liệu người dùng.

Có thể tùy chỉnh bằng biến môi trường:

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | \
  BQA_INSTALL_DIR="$HOME/apps/botquanganh_mcp" \
  BQA_BIN_DIR="$HOME/.local/bin" \
  BQA_BRANCH=main \
  bash
```

Các biến hỗ trợ: `BQA_REPO_URL`, `BQA_INSTALL_DIR`, `BQA_BIN_DIR`, `BQA_BRANCH`. `BQA_SKIP_PIP_UPGRADE=true` chỉ nên dùng trong môi trường kiểm thử hoặc offline đã chuẩn bị sẵn package cache.

### 2. Cài đặt thủ công từ repository local

```bash
cd botquanganh_mcp
./install.sh
```

`scripts/install_basic.sh` được giữ để tương thích và chuyển tiếp trực tiếp sang installer gốc.

### 3. Cấu hình và kiểm tra sau khi cài đặt

Đảm bảo `~/.local/bin` có trong `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Thêm dòng này vào `~/.bashrc` hoặc `~/.zshrc` để duy trì qua các session.

Cấu hình `.env` trước khi public service. Mặc định mẫu yêu cầu authentication:

```env
REQUIRE_AUTH=true
GATEWAY_TOKEN=<secret-random-token>
HOST_WORKSPACE_DIR=/home/user
```

Sau đó xác minh:

```bash
bqa version
bqa config validate
bqa doctor
```


## Chạy qua Cloudflare Tunnel

```bash
./run_mcp_tunnel.sh
./run_mcp_tunnel.sh --status
./run_mcp_tunnel.sh --url
./run_mcp_tunnel.sh --stop
```

URL connector có dạng:

```text
https://<random>.trycloudflare.com/mcp
```

Streamable HTTP được cấu hình ở chế độ stateless và trả JSON trực tiếp. Mỗi request của ChatGPT hoạt động độc lập, không cần `mcp-session-id` và không giữ SSE stream cho các tool call thông thường.

```env
MCP_JSON_RESPONSE=true
MCP_STATELESS_HTTP=true
```

## REST API

REST API dùng chung host services với MCP và chạy trên cùng server/tunnel. Base path:

```text
/api/v1
```

OpenAPI document:

```text
/api/v1/openapi.json
```

Các endpoint chính:

| Method | Endpoint | Chức năng |
|---|---|---|
| `GET` | `/api/v1/health` | Trạng thái server |
| `GET` | `/api/v1/capabilities` | Tool, workspace và giới hạn |
| `GET` | `/api/v1/files` | Liệt kê thư mục |
| `GET` | `/api/v1/files/content` | Đọc file text |
| `PUT` | `/api/v1/files/content` | Tạo hoặc ghi đè file |
| `PATCH` | `/api/v1/files/content` | Thay thế text trong file |
| `POST` | `/api/v1/files/append` | Nối nội dung vào file |
| `POST` | `/api/v1/directories` | Tạo thư mục |
| `GET` | `/api/v1/search` | Tìm text trong workspace |
| `POST` | `/api/v1/commands/check` | Kiểm tra command |
| `POST` | `/api/v1/commands/run` | Chạy command trên host |
| `GET` | `/api/v1/knowledge` | Đọc guide và tool inventory |

Khi `REQUIRE_AUTH=true`, dùng một trong hai header:

```text
Authorization: Bearer <GATEWAY_TOKEN>
X-Gateway-Token: <GATEWAY_TOKEN>
```

Ví dụ:

```bash
BASE_URL="https://<tunnel>.trycloudflare.com"
TOKEN="<GATEWAY_TOKEN>"

curl -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/files?path=GitHub"

curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path":"Workspace/demo.txt","content":"hello REST\n"}' \
  "$BASE_URL/api/v1/files/content"

curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command":"git status --short","cwd":"GitHub/botquanganh_mcp"}' \
  "$BASE_URL/api/v1/commands/run"
```

## Tool MCP

```text
health_check
get_capabilities
host_list_directory
host_read_file
host_write_file
host_replace_in_file
host_append_file
host_make_directory
host_search_text
host_check_command
host_run_command
host_knowledge
```

`host_run_command` không có tham số `approval="approved"`. Policy được quyết định hoàn toàn ở phía server.

## `host_knowledge`

```text
host_knowledge(section="overview")
host_knowledge(section="guide")
host_knowledge(section="tools", query="python", include_versions=true)
host_knowledge(section="search", query="docker")
```

Tool này đọc tài liệu trong `knowledge/` và đối chiếu `TOOL_CATALOG.json` với `PATH` thực tế của máy.

## Kiểm thử

```bash
./scripts/test.sh
./scripts/quality_gate.sh
./scripts/manual_test_installer.sh
```

`manual_test_installer.sh` dùng repository và HOME tạm trong `/tmp`; nó không khởi động, dừng hoặc restart Cloudflare tunnel thật.

## Cấu hình quan trọng

```env
HOST_WORKSPACE_DIR=/home/light
HOST_RESTRICT_TO_WORKSPACE=true
HOST_COMMAND_POLICY=guarded
MAX_TIMEOUT_SECONDS=60
MAX_OUTPUT_BYTES=500000
REQUIRE_AUTH=true
GATEWAY_TOKEN=<secret>
```

`guarded` chỉ là lớp bảo vệ khỏi các thao tác phá máy rõ ràng, không phải sandbox. MCP server chạy với quyền của user khởi động process.

Xem thêm: `docs/ARCHITECTURE.md` và `SECURITY.md`.


## CLI `bqa`

Repo có CLI thống nhất để vận hành bridge/tunnel và gọi REST API mà không cần viết `curl` thủ công.

Cài editable entry point:

```bash
.venv/bin/python -m pip install -e . --no-deps
```

Có thể chạy bằng một trong hai cách:

```bash
./bin/bqa --help
.venv/bin/bqa --help
```

Nhóm vận hành local:

```bash
bqa start
bqa status
bqa url
bqa server restart   # chỉ restart bridge, giữ nguyên tunnel URL
bqa restart --yes    # restart cả tunnel, có thể đổi URL
bqa stop
```

Nhóm REST API:

```bash
bqa health
bqa --public health
bqa capabilities --tools
bqa fs ls GitHub
bqa fs cat GitHub/project/README.md --lines 1:40
bqa fs write GitHub/demo.txt --text "hello"
printf 'next\n' | bqa fs append GitHub/demo.txt --stdin
bqa fs search FastMCP --path GitHub/botquanganh_mcp
bqa cmd check 'git status --short'
bqa cmd run 'git status --short' --cwd GitHub/botquanganh_mcp
bqa knowledge tools --query python --versions
```

Các nhóm hỗ trợ vận hành:

```bash
bqa logs server -n 100
bqa logs follow server
bqa config show
bqa config validate
bqa doctor
bqa completion bash
```

CLI có ba output mode dùng chung một nguồn dữ liệu:

```bash
bqa health                         # human: header, trạng thái, facts và hint
bqa health --quiet                 # quiet: chỉ in giá trị chính, không ANSI
bqa health --json                  # JSON ổn định cho automation
bqa health --color never           # tắt màu rõ ràng
NO_COLOR=1 bqa health              # tắt màu theo convention của terminal
```

Global options có thể đặt trước hoặc sau subcommand:

```bash
bqa --public health --json
bqa health --public --json
```

Human output dùng layout tuyến tính, bảng không viền và tự chuyển sang compact mode trên terminal hẹp. JSON success và structured error đều được in ra `stdout` để caller luôn parse được; exit code vẫn phản ánh thành công hoặc thất bại. Quiet mode không có header, hint, spinner hay ANSI.

CLI mặc định gọi local REST tại `http://127.0.0.1:<MCP_PORT>`. Dùng `--public` để lấy URL hiện tại từ `logs/tunnel_url.txt`, hoặc `--base-url` để chỉ định endpoint khác.

Exit code chính:

```text
0  thành công
1  operation thất bại
2  sai tham số
3  không kết nối được server
4  authentication thất bại
5  policy chặn
6  resource không tồn tại
7  timeout
8  conflict
```

Riêng `bqa cmd run`, khi server đã thực thi command thành công về mặt request, exit code CLI sẽ phản ánh exit code thật của command.

Thiết kế đầy đủ: `docs/CLI_DESIGN_PLAN.md`.

Tài liệu CLI bổ sung: `docs/CLI_VISUAL_CONTRACT.md`, `docs/CLI_MANUAL_TEST_PLAN.md` và `docs/CLI_IMPLEMENTATION_REPORT.md`.

## Vận hành và recovery

Quality gate thống nhất:

```bash
./scripts/quality_gate.sh
./scripts/quality_gate.sh --runtime
./scripts/quality_gate.sh --full
```

Doctor và config nghiêm ngặt:

```bash
bqa doctor --local-only
bqa doctor --strict
bqa config validate --strict
```

Thu thập diagnostics đã che cấu hình nhạy cảm:

```bash
./scripts/collect_diagnostics.sh
```

Quy trình cài đặt, restart bridge không đổi tunnel, recovery, rollback và checklist production được mô tả tại `docs/OPERATIONS_RUNBOOK.md`.

## Kiến trúc, bảo mật và release

- Kiến trúc runtime và boundary: `docs/ARCHITECTURE.md`
- Mô hình bảo mật và hardening: `SECURITY.md`
- Vận hành, recovery và rollback: `docs/OPERATIONS_RUNBOOK.md`
- Checklist release: `docs/RELEASE_CHECKLIST.md`

GitHub Actions chạy quality gate trên push và pull request; Dependabot theo dõi Python và GitHub Actions dependencies.
