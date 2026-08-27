# BotQuangAnh Host MCP

Máy chủ Host MCP và CLI vận hành `bqa` để thực thi các lệnh cho phép trên máy này qua MCP.

## Cài đặt

Yêu cầu: Python >= 3.10, `git` và `uv` (cài nếu thiếu: `curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | bash
```

Installer sẽ clone repo về `~/.botquanganh_mcp` (nếu chạy ngoài thư mục repo), tạo virtualenv `.venv` bằng `uv venv --seed`,
cài dependencies và CLI, sinh `.env` từ `.env.example`, rồi symlink `bqa` vào `~/.local/bin/bqa`.

Khởi động service; khi từng thành phần sẵn sàng (server → tunnel → bridge → endpoint), URL connector được in ra như một dòng copy-safe:

```text
https://<random>.trycloudflare.com/mcp
```

## Cấu hình

Toàn bộ cấu hình nằm trong `.env` ở thư mục repo, được nạp khi tiến trình khởi động; sửa xong chạy `bqa restart` (hoặc `bqa server restart` nếu muốn giữ nguyên tunnel).

| Khóa | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `HOST_WORKSPACE_DIR` | `~` (`$HOME`) | Thư mục gốc mà tool được phép thao tác |
| `HOST_DEFAULT_DIR` | `~` (`$HOME`) | Thư mục mặc định cho đường dẫn tương đối |
| `HOST_RESTRICT_TO_WORKSPACE` | `true` | Giới hạn mọi thao tác file nằm trong workspace |
| `HOST_READ_SCOPE` | *(trống)* | Phạm vi đọc hẹp hơn (mặc định lấy `HOST_WORKSPACE_DIR`) |
| `HOST_WRITE_SCOPE` | *(trống)* | Phạm vi ghi hẹp hơn (mặc định lấy `HOST_WORKSPACE_DIR`) |
| `HOST_READ_DENY_GLOBS` | *(trống)* | Danh sách mẫu glob từ chối đọc, phân tách bằng dấu phẩy |
| `HOST_COMMAND_POLICY` | `guarded` | `guarded` chặn mẫu lệnh phá hủy; `allowlist` chỉ cho phép lệnh được liệt kê |
| `HOST_ALLOWED_COMMANDS` | `all` | Danh sách lệnh cho phép, phân tách bằng dấu phẩy |
| `HOST_INHERIT_ENV` | `true` | Kế thừa biến môi trường khi chạy command (đã lọc secret/token) |
| `HOST_ENV_ALLOWLIST` | *(trống)* | Danh sách biến môi trường cho phép thêm khi chạy command |
| `MAX_CONCURRENT_COMMANDS` | `100` | Số lệnh chạy đồng thời tối đa |
| `MAX_TIMEOUT_SECONDS` | `60` | Thời gian chờ tối đa của một lệnh (giây) |
| `MAX_OUTPUT_BYTES` | `500000` | Giới hạn byte stdout/stderr trả về |
| `MAX_SINGLE_FILE_BYTES` | `3000000` | Giới hạn kích thước file tối đa khi đọc/ghi |
| `SEARCH_TEXT_DEADLINE_SECONDS` | `15` | Giới hạn thời gian quét text đệ quy trước khi trả kết quả một phần |
| `MCP_PORT` | `18427` | Cổng MCP bridge cục bộ |
| `MCP_BIND_HOST` | `127.0.0.1` | Địa chỉ bind của bridge |
| `REQUIRE_AUTH` | `false` | Bật xác thực token cho HTTP API |
| `GATEWAY_TOKEN` | *(trống)* | Token dùng cùng `REQUIRE_AUTH=true` |
| `ALLOWED_ORIGINS` | *(trống)* | Danh sách CORS origin cho phép qua HTTP API |
| `TRUST_PROXY_HEADERS` | `false` | Tin cậy header proxy khi đứng sau Cloudflare Tunnel / reverse proxy |
| `HOST_TOOL_CACHE_SECONDS` | `300` | Thời gian cache catalog tool |
| `ATTRIBUTION_MODE` | `off` | Gán thao tác host về chat: `off` / `tag` / `strict` / `enforce` |
| `HOST_CHAT_WORKSPACES` | `false` | Bật tính năng tạo workspace riêng cho từng chat |
| `HOST_CHAT_ROOT` | `~/Downloads/bqa-workspaces` | Thư mục gốc chứa các chat workspace |
| `HOST_CHAT_ISOLATE` | `false` | Khóa ghi: không cho ghi ra ngoài workspace riêng của chat |
| `HOST_CHAT_QUOTA_MB` | `2048` | Dung lượng tối đa của một chat workspace (MB) |
| `HOST_CHAT_IDLE_ARCHIVE_HOURS` | `72` | Số giờ không hoạt động trước khi tự động archive workspace |
| `HOST_CHAT_RETENTION_DAYS` | `30` | Số ngày lưu giữ workspace trước khi dọn dẹp vĩnh viễn |
| `HOST_CHAT_MAX_WORKSPACES` | `128` | Giới hạn số lượng workspace tồn tại đồng thời |

## Cách dùng

Gõ `bqa` (không đối số) tương đương `bqa start`; mọi lệnh hỗ trợ `--help` và chế độ đầu ra chung `--json`, `--quiet`.

```bash
# Lifecycle
bqa start              # khởi động/đón nhận runtime: server → tunnel → bridge → URL connector
bqa stop               # dừng toàn bộ; URL hiện tại sẽ mất
bqa restart            # khởi động lại MCP server, giữ nguyên tunnel PID/URL
bqa server restart     # chỉ restart bridge cục bộ
bqa server status      # trạng thái riêng của bridge
bqa url                # in URL connector (--quiet: chỉ chuỗi URL)
# Interface
bqa ui                 # BQA Control Center trên desktop
bqa ui --detach        # mở cửa sổ desktop tách khỏi terminal
bqa tui                # bản TUI trong terminal (dùng khi SSH/headless)
# Inspection
bqa status             # trạng thái runtime tổng thể
bqa health             # đọc REST health
bqa capabilities       # capabilities của service
bqa capabilities --tools|--limits|--host      # lọc: tools / limits / host
bqa knowledge overview|guide|tools|search|all # guides + catalog tool (--query để lọc)
bqa logs <server|tunnel|launcher|audit|follow> [-n 100] [-f] [--since 10m] [--grep TEXT]
bqa logs all [-n 100] [-f] [--since 10m] [--grep TEXT]   # gộp cả 4 nguồn log, tiền tố [source]
bqa chats list                                # liệt kê chat workspace cục bộ theo hoạt động gần nhất
bqa chats show <chat_id>                      # xem path, STATE.md và thống kê journal
bqa chats logs <chat_id> [--min-severity warn] [--category process]  # log phân loại/redact
bqa chats archive|restore <chat_id>            # quản lý vòng đời workspace
bqa chats delete <chat_id> --yes               # xóa vĩnh viễn workspace đã archive
bqa chats prune [--apply]                      # dry-run/apply lifecycle sweep
bqa chats stats                                # số lượng và dung lượng workspace
# Files & commands
bqa fs ls [path] --max 500                    # liệt kê thư mục (mặc định workspace root)
bqa fs cat <path> --lines 1:50                # đọc file UTF-8 (--max-bytes N)
bqa fs write <path> --text "hi"|--from FILE|--stdin   # tạo/ghi đè file (--no-overwrite)
bqa fs append <path> --text "..."|--from FILE|--stdin # nối nội dung
bqa fs replace <path> --old "A" --new "B" --expected-count 1  # thay text chính xác
bqa fs mkdir <path>                           # tạo thư mục (mặc định tạo cả thư mục cha)
bqa fs search "từ khóa" --path docs --max 100 # tìm kiếm text đệ quy
bqa cmd check "ls -la"                        # soi chính sách mà không chạy lệnh
bqa cmd run "df -h" --timeout 30 --cwd DIR --check-first
# Diagnostics
bqa doctor              # chẩn đoán cục bộ + tunnel công khai
bqa doctor --local-only # bỏ qua kiểm tra public tunnel
bqa doctor --strict     # coi cảnh báo là thất bại
# Config & help
bqa config show|get KEY|path|validate [--strict]
bqa completion bash|zsh|fish
bqa version
bqa help [command]
```

Khi cần debug runtime, `bqa logs all` gộp log server, tunnel, launcher và audit; REST `GET /api/v1/logs/tail` trả cùng bản chụp qua HTTP. Với log theo chat/workspace, dùng `bqa chats logs <chat_id>` hoặc live SSE `GET /api/v1/activity/stream`; Control Center có tab `Workspace Logs` dùng chính stream này.

Chat workspace cục bộ mặc định nằm dưới `~/Downloads/bqa-workspaces`.

Probe sức khỏe trực tiếp: `curl -s http://127.0.0.1:18427/healthz` · endpoint MCP: `<URL>/mcp`.

## Tài liệu

[Kiến trúc](docs/ARCHITECTURE.md) · [Vận hành](docs/OPERATIONS_RUNBOOK.md) · [Checklist phát hành](docs/RELEASE_CHECKLIST.md) · [Bảo mật](SECURITY.md) · [Giao diện CLI](docs/CLI_UI.md) · [Chat workspaces](docs/CHAT_WORKSPACES.md)
