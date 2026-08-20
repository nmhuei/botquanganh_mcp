# BotQuangAnh Host MCP

## Cài đặt

```bash
curl -fsSL https://raw.githubusercontent.com/nmhuei/botquanganh_mcp/main/install.sh | bash
```

## Khởi động

```bash
bqa
```

Lệnh trên khởi động MCP server và in URL để kết nối:

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

Sửa file `.env` nếu cần thay đổi workspace hoặc bật xác thực:

```env
HOST_WORKSPACE_DIR=/home/user
HOST_DEFAULT_DIR=/home/user/Downloads
REQUIRE_AUTH=false
GATEWAY_TOKEN=
```

Sau khi sửa cấu hình:

```bash
bqa restart
```

## Tài liệu

- [Kiến trúc hệ thống](docs/ARCHITECTURE.md)
- [Hướng dẫn vận hành](docs/OPERATIONS_RUNBOOK.md)
- [Checklist phát hành](docs/RELEASE_CHECKLIST.md)
- [Chính sách bảo mật](SECURITY.md)
