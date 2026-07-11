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

scripts/
├── install_basic.sh
├── restart_server_only.sh
├── start_tunnel_server.sh
├── dev.sh
└── test.sh
```

## Cài đặt

```bash
cd /home/light/GitHub/botquanganh_mcp
./scripts/install_basic.sh
```

Sau đó điền `GATEWAY_TOKEN` và kiểm tra `HOST_WORKSPACE_DIR` trong `.env`.

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
```

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
