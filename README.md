# BotQuangAnh Host MCP

## Cài đặt

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | bash
```

## Khởi động

```bash
bqa
```

Lệnh trên khởi động MCP server và in URL để kết nối (URL chỉ được in sau khi connector xác nhận sẵn sàng):

```text
https://<random>.trycloudflare.com/mcp
```

Trên máy có graphical desktop, có thể mở thêm cửa sổ Python **BQA Control Center**
để theo dõi và điều khiển service:

- xem trạng thái MCP bridge, Cloudflare tunnel, endpoint và workspace;
- nút Start/Adopt, Restart bridge, Refresh và Copy endpoint;
- nút **Chọn thư mục…** để duyệt workspace và **Áp dụng workspace** để lưu cấu hình,
  restart riêng MCP bridge và giữ nguyên tunnel. Không cần sửa `.env` thủ công;
- tab **Hoạt động ChatGPT** hiển thị các lần `host_run_command` gần nhất qua MCP,
  gồm command, exit code, `stdout` và `stderr` đã giới hạn/redact;
- tự cập nhật trạng thái mỗi 2 giây mà không tạo request CTF mới.

Mở giao diện bất kỳ lúc nào:

```bash
bqa ui
```

Không cần giữ terminal: sau cài đặt, mở **BQA Control Center** từ menu ứng dụng.
Launcher không mở terminal và tách cửa sổ khỏi phiên shell. Có thể làm tương tự từ dòng lệnh:

```bash
bqa ui --detach
```

Nếu đang SSH/headless không có graphical display, dùng bản TUI trong terminal:

```bash
bqa tui
```

## Giao diện CLI

- Tiến trình theo mốc: các lệnh vòng đời (`start`, `restart`, `stop`) đánh dấu từng thành phần khi thực sự sẵn sàng, lần lượt qua server → tunnel → bridge → URL connector; chờ lâu sẽ hiển thị thời gian đã trôi.
- Render không nhấp nháy: chỉ vẽ lại những dòng thực sự thay đổi.
- Copy an toàn: URL connector và đường dẫn tuyệt đối luôn là một chuỗi liền ở mọi độ rộng terminal.
- Help gom nhóm theo chủ đề; lỗi kèm gợi ý lệnh kế tiếp được chọn theo exit code.
- Khởi động nhanh: mỗi lệnh vẽ khung đầu tiên trong ~45–70ms.

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
- [CLI UI contract](docs/CLI_UI.md)
- [Hướng dẫn vận hành](docs/OPERATIONS_RUNBOOK.md)
- [Runbook điều tra MCP 502](docs/MCP_FORENSICS_RUNBOOK.md)
- [Checklist phát hành](docs/RELEASE_CHECKLIST.md)
- [Chính sách bảo mật](SECURITY.md)
