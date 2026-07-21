# CLI Implementation Report

## Tổng quan

CLI `bqa` đã được triển khai đầy đủ cho repo `botquanganh_mcp` theo kế hoạch Phase 1–5.

Ngày hoàn tất: 20/07/2026.

Branch:

```text
refactor/host-core-clean-v1
```

## Cấu trúc được thêm

```text
app/cli/
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
    ├── __init__.py
    ├── health.py
    ├── filesystem.py
    ├── command.py
    ├── knowledge.py
    ├── logs.py
    ├── config.py
    ├── doctor.py
    └── completion.py

bin/
└── bqa

pyproject.toml
scripts/manual_test_cli.sh
docs/CLI_MANUAL_TEST_PLAN.md
```

## Command tree

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
├── config
├── doctor
├── completion
└── version
```

## Kiến trúc

### Local operations

Các lệnh lifecycle chỉ wrap script chính thức:

```text
run_mcp_tunnel.sh
scripts/restart_server_only.sh
```

CLI không copy lại logic quản lý process.

### API operations

Các lệnh filesystem, command, knowledge, health và capabilities gọi REST API hiện có.

CLI không triển khai lại:

- path boundary;
- command policy;
- file service;
- command executor;
- knowledge inventory;
- authentication.

### HTTP client

REST client sử dụng `urllib.request` trong standard library và hỗ trợ:

- local URL;
- canonical public tunnel URL;
- custom base URL;
- bearer token;
- request timeout;
- JSON encode/decode;
- HTTP error mapping;
- command failure payload dù REST trả HTTP 500.

## Exit-code semantics

```text
0  Thành công
1  Operation thất bại
2  Sai tham số
3  Không kết nối được server
4  Authentication thất bại
5  Policy chặn
6  Resource không tồn tại
7  Timeout
8  Conflict
```

`bqa cmd run` giữ nguyên exit code thật của command khi request đã được server xử lý.

## Packaging

Đã thêm:

```text
pyproject.toml
```

Console entry point:

```toml
[project.scripts]
bqa = "app.cli.main:main"
```

Đã xác minh:

```text
.venv/bin/bqa version
bqa 1.0.0
```

`install_basic.sh` hiện cài dependency rồi chạy editable install để tạo entry point.

## Automated tests

Kết quả cuối:

```text
37 passed in 8.44s
```

Bao gồm test cũ và các nhóm test mới:

- parser;
- global option normalization;
- line ranges;
- output và secret redaction;
- REST client;
- auth/error mapping;
- command non-zero semantics;
- lifecycle helpers;
- CLI integration.

## Manual regression

Script:

```text
scripts/manual_test_cli.sh
```

Kết quả cuối:

```text
TOTAL_PASS=18
ALL_CLI_MANUAL_TESTS=PASS
```

Các nhóm đã pass:

1. Build, executable, packaging, help, version.
2. Bash, Zsh và Fish completion.
3. Status, JSON và global option placement.
4. Local/public REST health.
5. Capabilities và filters.
6. Filesystem write sources.
7. File line ranges.
8. Append, replace, search, list và conflict.
9. Command policy.
10. Command execution semantics.
11. Knowledge sections.
12. Logs, grep, since và follow.
13. Config và token redaction.
14. Doctor local/public REST và MCP initialize.
15. Lifecycle cô lập.
16. Live idempotent start.
17. Live server-only restart.
18. Pytest, compileall, Bash syntax và Git diff check.

## Lifecycle cô lập

Full lifecycle được kiểm tra trong repo giả với environment sạch:

```text
ISOLATED_STATUS:
bridge=ready
ok=true
url=https://isolated-1.trycloudflare.com/mcp
workspace=/tmp/.../isolated-repo
```

Đã xác minh:

- start;
- start idempotent;
- status;
- server-only restart;
- stop;
- restart confirmation;
- full restart;
- URL mới sau full restart;
- không có process hồi sinh sau stop.

## Runtime thật

Trước regression cuối:

```text
Tunnel PID: 65323
URL: https://cambridge-plays-jessica-albums.trycloudflare.com/mcp
```

Sau `bqa server restart`:

```text
Supervisor: running (65413)
Server:     running (106663)
Tunnel:     running (65323)
Bridge:     ready
URL:        https://cambridge-plays-jessica-albums.trycloudflare.com/mcp
```

Kết luận:

- server PID thay đổi;
- tunnel PID không đổi;
- URL không đổi;
- local health pass;
- public REST pass;
- public MCP initialize pass.

Full tunnel restart không được chạy trên runtime thật.

## Security behavior

Runtime hiện vẫn giữ:

```text
REQUIRE_AUTH=false
```

Theo yêu cầu của người dùng, CLI không thay đổi cấu hình này.

CLI vẫn hỗ trợ token khi auth được bật sau này và luôn che secret trong:

- `config show`;
- `config get`;
- JSON output;
- error details.

## Tài liệu

- `README.md` có phần hướng dẫn CLI.
- `docs/CLI_DESIGN_PLAN.md` có thiết kế và trạng thái triển khai.
- `docs/CLI_MANUAL_TEST_PLAN.md` có ma trận regression.
- File này ghi nhận kết quả triển khai và nghiệm thu.
