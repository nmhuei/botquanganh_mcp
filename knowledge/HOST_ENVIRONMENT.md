# Host Environment

## Runtime

- MCP server chạy trực tiếp bằng user đã khởi động process.
- File và command được giới hạn bởi `HOST_WORKSPACE_DIR`.
- `HOST_RESTRICT_TO_WORKSPACE=true` nên được giữ mặc định.
- `HOST_COMMAND_POLICY=guarded` chặn các thao tác phá máy hoặc nâng quyền rõ ràng.
- Đây không phải sandbox; command hợp lệ vẫn có quyền của user chạy server.

## Tool discovery

`host_knowledge` đối chiếu `TOOL_CATALOG.json` với `PATH` thực tế của process MCP.

- `available=true` nghĩa là command được tìm thấy trong `PATH`.
- Version chỉ được probe bằng argument cố định khai báo trong catalog.
- Dùng `refresh=true` để bỏ cache và kiểm tra lại.

## Workspace hiện tại

Kiểm tra cấu hình thực tế bằng:

```text
host_knowledge(section="overview")
get_capabilities
```
