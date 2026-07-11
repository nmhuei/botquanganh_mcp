# Host MCP Architecture

## Runtime flow

```text
ChatGPT / MCP client
        │
        ▼
Cloudflare Tunnel (optional)
        │
        ▼
FastMCP Streamable HTTP + Starlette
        │
        ├── authentication
        ├── rate limiting
        ├── request metrics
        ├── /healthz
        ├── /mcp
        │     └── MCP tool adapters
        │           ├── app/tools/health.py
        │           ├── app/tools/host.py
        │           └── app/tools/host_knowledge.py
        └── /api/v1
              └── app/rest_api.py
                        │
                        ▼
        Shared host services
        ├── paths.py
        ├── files.py
        ├── policy.py
        ├── executor.py
        └── inventory.py
```

## Quy tắc phụ thuộc

- `app/host/` không chứa MCP decorator hoặc HTTP route.
- `app/tools/` chỉ chuyển đổi MCP request sang host service và chuẩn hóa lỗi.
- `app/rest_api.py` chuyển đổi REST request sang cùng host service, không nhân đôi business logic.
- `app/main.py` đăng ký tool rõ ràng; không tự động import plugin.
- `knowledge/` là nguồn tài liệu và catalog, không chứa executable code.
- Branch này chỉ chứa host core, knowledge catalog và lớp vận hành cần thiết.

## Tool surface

Core luôn có đúng 12 tool:

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

## Command execution

`host_run_command`:

1. Kiểm tra timeout.
2. Đánh giá command bằng policy phía server.
3. Resolve `cwd` trong `HOST_WORKSPACE_DIR`.
4. Chạy `bash -lc` bằng user của MCP process.
5. Ghi stdout/stderr vào temporary files.
6. Kill process group khi timeout.
7. Trả output đã giới hạn kích thước.
8. Ghi audit bằng command hash thay vì nguyên command.

## Knowledge flow

`host_knowledge` đọc:

- Markdown guides trong `knowledge/`.
- `TOOL_CATALOG.json`.
- Tool availability từ `PATH` thực tế.
- Version qua argument cố định khai báo trong catalog.

Caller không thể truyền một command tùy ý vào version probe.
