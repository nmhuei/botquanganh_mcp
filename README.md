# BotQuangAnh Host MCP

## Cài đặt

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | bash
```

## Khởi động

```bash
bqa
```

Trên máy có graphical desktop, lệnh trên khởi động/adopt service rồi mở cửa sổ Python
**BQA Control Center**:

- xem trạng thái MCP bridge, Cloudflare tunnel, endpoint và workspace;
- nút Start/Adopt, Restart bridge, Refresh và Copy endpoint;
- nút **Chọn thư mục…** để duyệt workspace và **Áp dụng workspace** để lưu cấu hình,
  restart riêng MCP bridge và giữ nguyên tunnel. Không cần sửa `.env` thủ công;
- tab **Hoạt động ChatGPT** hiển thị các lần `host_run_command` gần nhất qua MCP,
  gồm command, exit code, `stdout` và `stderr` đã giới hạn/redact;
- tự cập nhật trạng thái mỗi 2 giây mà không tạo request CTF mới.

Để mở lại giao diện bất kỳ lúc nào:

```bash
bqa ui
```

Không cần giữ terminal: sau cài đặt, mở **BQA Control Center** từ menu ứng dụng.
Launcher không mở terminal và tách cửa sổ khỏi phiên shell. Có thể làm tương tự từ dòng lệnh:

```bash
bqa ui --detach
```

Nếu đang SSH/headless không có graphical display, `bqa` tự dùng TUI. Có thể mở thẳng TUI với
`bqa tui`.

Khi stdout không phải terminal (script/pipe), `bqa` vẫn khởi động MCP server và in URL để kết nối:

```text
https://<random>.trycloudflare.com/mcp
```

## Các lệnh khác

```bash
bqa status           # xem trạng thái
bqa url --quiet      # lấy URL MCP
bqa restart          # restart server, giữ nguyên tunnel
bqa doctor           # kiểm tra lỗi
bqa logs server -n 100
bqa config validate  # kiểm tra cấu hình
bqa stop             # dừng toàn bộ, URL hiện tại sẽ mất
```

## Cấu hình

Sửa file `.env` nếu cần thay đổi workspace, lệnh cho phép hoặc bật xác thực:

```env
HOST_WORKSPACE_DIR=/home/user
HOST_DEFAULT_DIR=/home/user/Downloads
HOST_COMMAND_POLICY=guarded
HOST_ALLOWED_COMMANDS=all
HOST_INHERIT_ENV=true
MAX_CONCURRENT_COMMANDS=100
REQUIRE_AUTH=false
GATEWAY_TOKEN=
```

Sau khi sửa cấu hình:

```bash
bqa restart
```

## Thẻ kết quả CTF trong ChatGPT

Khi người dùng xác nhận một URL HTTPS CTF được phép truy cập và yêu cầu lấy trang cơ bản,
ChatGPT có thể gọi `ctf_fetch_url`. Tool này chỉ thực hiện một `GET` có giới hạn, không
quét, crawl hoặc fuzz. Sau đó `ctf_render_fetch_result` hiển thị thẻ inline gồm URL cuối,
HTTP status, redirects, content type và phần body đã giới hạn.

Sau khi cập nhật server, chạy `bqa restart`, rồi **Refresh** kết nối MCP trong ChatGPT
Developer Mode để ChatGPT nhận resource UI và tool mới. Thẻ UI chỉ hiển thị kết quả được
truyền vào; nó không tự tạo request HTTP nào.

## Tài liệu

- [Kiến trúc hệ thống](docs/ARCHITECTURE.md)
- [Hướng dẫn vận hành](docs/OPERATIONS_RUNBOOK.md)
- [Checklist phát hành](docs/RELEASE_CHECKLIST.md)
- [Chính sách bảo mật](SECURITY.md)
