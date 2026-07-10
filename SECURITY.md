# Security

## Mô hình tin cậy

Server này cố ý chạy command trên host bằng quyền của user khởi động MCP. Đây không phải container sandbox và không nên được mở công khai nếu chưa bật authentication.

## Ranh giới bảo vệ

- `HOST_WORKSPACE_DIR` giới hạn phạm vi file và working directory.
- `HOST_RESTRICT_TO_WORKSPACE=true` chặn path thoát ra ngoài workspace.
- `HOST_COMMAND_POLICY=guarded` chặn một số thao tác phá máy hoặc nâng quyền rõ ràng.
- `HOST_COMMAND_POLICY=allowlist` giới hạn thêm tên command được phép.
- `MAX_TIMEOUT_SECONDS`, `MAX_OUTPUT_BYTES` và `MAX_SINGLE_FILE_BYTES` giới hạn tài nguyên.
- `GATEWAY_TOKEN` bảo vệ HTTP endpoint.
- `TRUST_PROXY_HEADERS` chỉ nên bật khi server nằm sau reverse proxy tin cậy.

## Những gì policy không đảm bảo

Command shell hợp lệ vẫn có thể:

- Sửa hoặc xóa dữ liệu trong workspace.
- Truy cập mạng theo quyền của host.
- Đọc environment nếu `HOST_INHERIT_ENV=true`.
- Chạy binary hoặc script tùy ý có trong workspace.

Do đó nên:

1. Chạy server bằng user không có quyền root.
2. Đặt `HOST_WORKSPACE_DIR` ở phạm vi nhỏ nhất cần thiết.
3. Không để secret trong workspace nếu ChatGPT không cần đọc.
4. Dùng token mạnh khi chạy qua tunnel.
5. Chuyển sang `HOST_COMMAND_POLICY=allowlist` nếu cần kiểm soát chặt.
6. Đặt `HOST_INHERIT_ENV=false` nếu child process không cần toàn bộ environment.

## Báo cáo sự cố

Kiểm tra:

```text
logs/server.log
logs/gateway.log
logs/cloudflared.log
```

Dừng server và tunnel ngay bằng:

```bash
./run_mcp_tunnel.sh --stop
```
