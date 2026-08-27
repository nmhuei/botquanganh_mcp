# Chat Workspaces (DRAFT)

> **DRAFT** — tính năng đang phát triển trên nhánh `feature/new-features`, **chưa có** trong bản phát hành hiện tại; mọi khóa cấu hình và hành vi dưới đây có thể thay đổi trước khi release.

Mỗi session ChatGPT một workspace riêng dưới `~/Downloads/bqa-workspaces/<chat_id>`; log nằm ngay trong workspace nên khi chat chết, chỉ cần đọc lại `STATE.md` là hồi sinh được ngữ cảnh, không phải làm lại từ đầu.

## Bắt tay 3 bước

1. GPT gửi `chat_id` cho MCP.
2. MCP kiểm tra/tạo workspace tương ứng với `chat_id`.
3. MCP trả về đường dẫn workspace; GPT làm việc bằng đường dẫn tương đối trong đó.

## Cấu hình

Toàn bộ nằm trong `.env`, nạp khi khởi động (xem thêm bảng chung trong README).

| Khóa | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `ATTRIBUTION_MODE` | `off` | Gán thao tác host về chat: `off` tắt; `tag` gắn nhãn `chat_id` vào log/kết quả; `strict` từ chối thao tác ghi không mang `chat_id` hợp lệ; `enforce` từ chối toàn bộ thao tác (kể cả đọc) nếu chưa bind |
| `HOST_CHAT_WORKSPACES` | `false` | Công tắc bật/tắt cả tính năng workspace theo chat |
| `HOST_CHAT_ROOT` | `~/Downloads/bqa-workspaces` | Thư mục gốc chứa mọi workspace |
| `HOST_CHAT_IDLE_ARCHIVE_HOURS` | `72` | Số giờ không hoạt động trước khi workspace bị archive |
| `HOST_CHAT_RETENTION_DAYS` | `30` | Số ngày giữ (kể cả đã archive) trước khi xóa vĩnh viễn |
| `HOST_CHAT_MAX_WORKSPACES` | `128` | Trần số workspace tồn tại đồng thời trên root |
| `HOST_CHAT_QUOTA_MB` | `2048` | Dung lượng tối đa của một workspace (MB) |
| `HOST_CHAT_ISOLATE` | `false` | Khi bật: chặn ghi ra ngoài workspace của chính chat đó |
| `HOST_CHAT_RESUME_HINT_MINUTES` | `30` | Khoảng lặng (phút) sau đó MCP nhắc GPT đọc `STATE.md` để hồi sinh phiên |
| `HOST_CHAT_ROOT_MAX_GB` | `24` | Trần dung lượng toàn bộ root (GB) |
| `HOST_CHAT_JOURNAL_MAX_BYTES` | `8388608` | Giới hạn kích thước tối đa của `journal.jsonl` (8 MB) |

## Layout workspace

```text
<chat_id>/
├── journal.jsonl   # nhật ký hai pha: op_started → op_result cho từng thao tác
├── STATE.md        # cache chiếu bất biến từ journal — nguồn thật vẫn là journal
├── meta.json       # thông tin workspace: chat_id, thời điểm tạo/hoạt động, trạng thái
└── notes/          # ghi chú dài hạn do GPT tự quản
```

`STATE.md` có thể bị xây lại từ `journal.jsonl` bất cứ lúc nào; journal mới là dữ liệu bất biến.

## Log workspace: ghi, phân loại và hiển thị

Journal trên đĩa cố ý giữ record JSONL nhỏ gọn để giảm write amplification và không làm rotation sớm. Khi đọc, MCP chiếu record sang schema observability giàu thông tin hơn; vì vậy log cũ cũng được phân loại mà không cần rewrite/migrate file lịch sử.

Mỗi operation dùng cùng một `op`/`interaction_id` và được ghi theo write-ahead hai pha:

1. `op_started` được fsync/ghi vào journal **trước khi** host operation chạy; nếu process chết giữa chừng, operation còn lại trong `Pending Operations`.
2. `op_result` được ghi sau khi operation kết thúc. Reader tương quan hai record để kế thừa `kind`, tính duration và xác định outcome.

Projection khi đọc có các trường chính:

| Trường | Ý nghĩa |
| --- | --- |
| `event_dataset` | nguồn ổn định `bqa.workspace` |
| `event_action` | host tool/action cụ thể, ví dụ `host_read_file`, `host_run_command` |
| `event_category` | nhóm chuẩn hóa: `api`, `configuration`, `file`, `host`, `process`, `session` |
| `operation_phase` | `started` hoặc `result` |
| `event_outcome` | `unknown`, `success`, `failure` |
| `severity_text` / `severity_number` | mức chuẩn hóa dùng cho filter/UI; `DEBUG=5`, `INFO=9`, `WARN=13`, `ERROR=17` |
| `interaction_id` | cùng giá trị `op` để nối start/result |
| `event_duration_ms` | thời gian từ start đến result khi có đủ timestamp |

Payload được sanitize cả lúc ghi và lúc đọc. Các key/chuỗi phổ biến chứa password, token, API key, authorization, session id và Bearer token bị thay bằng `<redacted>`; command output không được chép nguyên vào journal. Lỗi của chính cơ chế journal được đẩy sang audit event `WORKSPACE_JOURNAL_ERROR` bằng loại lỗi/phase thay vì nuốt im lặng hoặc ghi message có thể chứa secret.

### CLI

```bash
bqa chats logs <chat-id>
bqa chats logs <chat-id> --min-severity error
bqa chats logs <chat-id> --category process --outcome failure
bqa chats logs <chat-id> --action host_run_command --phase result --limit 100
bqa chats logs <chat-id> --json
```

`bqa chats show <chat-id>` đếm cả `journal.jsonl.1` lẫn `journal.jsonl`; `STATE.md` có `Log Summary` theo category/severity/outcome. REST `/api/v1/activity` cũng trả projection đã redact và hỗ trợ filter `severity`, `category`, `outcome`, `action`, `phase` khi đọc journal.

Thiết kế này lấy ý tưởng từ OpenTelemetry Logs (severity/event name/correlation) và Elastic Common Schema (category/action/outcome), nhưng **không tuyên bố journal JSONL là wire-format tương thích OTel/ECS**.

## Lỗi

| Mã | Ý nghĩa |
| --- | --- |
| `E1` | `chat_id` thiếu hoặc sai định dạng |
| `E2` | Vượt trần số workspace (`HOST_CHAT_MAX_WORKSPACES`) khi tạo mới |
| `E3` | Vượt quota: workspace đầy (`HOST_CHAT_QUOTA_MB`) hoặc journal chạm trần (`HOST_CHAT_JOURNAL_MAX_BYTES`) |
| `E4` | Root đầy (`HOST_CHAT_ROOT_MAX_GB`) |
| `E5` | Phát hiện chiếm chỗ: thư mục workspace tồn tại nhưng không có `meta.json` hợp lệ |
| `E6` | Chưa bind workspace (`host_workspace_bind`) khi đang bật `ATTRIBUTION_MODE=enforce` |

## Vòng đời

- Không hoạt động quá 72 giờ (`HOST_CHAT_IDLE_ARCHIVE_HOURS`) → archive.
- Archive quá 30 ngày (`HOST_CHAT_RETENTION_DAYS`) → xóa vĩnh viễn.
- Trần cứng: 128 workspace · 2 GB mỗi workspace · 24 GB tổng root.

## Quy tắc cho GPT

- Bind workspace (bắt tay 3 bước) **trước** khi làm việc bất cứ việc gì.
- Ghi chú dài hạn vào `notes/`; trạng thái ngắn nằm ở `STATE.md`.
- Khi hồi sinh phiên: đọc `STATE.md` trước, không đoán lại ngữ cảnh cũ.
- Không ghi ra ngoài workspace của mình khi chưa được mở rộng quyền.


## Structured workspace logs

`journal.jsonl` is both the crash-recovery ledger and the structured per-chat log. New records use journal schema v2; older records are normalized at read time, so no in-place migration is required.

Stable classification fields:

| Field | Meaning |
| --- | --- |
| `log_source` | Stable producer (`workspace_journal`) |
| `event_dataset` | Stable dataset (`bqa.workspace`) |
| `event_name` | Low-cardinality lifecycle event name (`workspace.operation.started` / `workspace.operation.result`) |
| `event_category` | Coarse class: `file`, `process`, `session`, `host`, `configuration`, `api` |
| `event_action` | Exact tool/action name, e.g. `host_read_file` |
| `event_outcome` | `success`, `failure`, or `unknown` |
| `operation_phase` | `started` or `result` |
| `severity_text` / `severity_number` | OTel-style normalized severity (`DEBUG=5`, `INFO=9`, `WARN=13`, `ERROR=17`) |
| `interaction_id` | High-cardinality operation correlation id; never use it as a coarse category |
| `event_duration_ms` | Derived start-to-result duration when both records are available |

Result records now persist their own `kind`; readers additionally correlate historical start/result pairs by `op` so schema-v1 result records receive the correct action/category and duration without rewriting the journal.

Commands are never exposed verbatim by the normalized workspace log. The compatibility `payload.command` field is replaced by `<redacted>` and `payload.command_sha256` is retained for correlation. Secret-looking keys and common bearer/token/password forms are recursively redacted before storage/display.

Inspect and filter one workspace:

```bash
bqa chats logs <chat-id>
bqa chats logs <chat-id> --min-severity error
bqa chats logs <chat-id> --category process --phase result
bqa chats logs <chat-id> --outcome failure
bqa chats logs <chat-id> --action host_read_file --json
```

The REST activity feed accepts the same classification dimensions through `severity`, `category`, `outcome`, `action`, and `phase` query parameters. Without classification filters its legacy response shape is preserved. With a workspace classification filter, unclassified job-registry rows are omitted rather than mixed into a misleading result set.

Host tools bracket execution with durable `op_started` and `op_result` writes. `STATE.md` is refreshed after the start write, so a crash or interrupted long-running command remains visible as a pending operation. Workspace journal failures are best-effort for the host action itself but emit a `WORKSPACE_JOURNAL_ERROR` audit event with tool, chat id, phase, and exception type; raw exception details are not copied into the audit payload.


### Live SSE stream and Control Center

`GET /api/v1/activity/stream` exposes normalized workspace journal records as Server-Sent Events (`text/event-stream`). It uses the same `severity`, `category`, `outcome`, `action`, `phase`, and optional `chat_id` filters as the snapshot activity endpoint.

Key transport behavior:

- event type: `workspace_log`;
- opaque stable `id` per journal record, suitable for `Last-Event-ID` resume without exposing chat/path/payload data in the cursor;
- `retry: 2000` reconnect hint;
- heartbeat comments every ~15 seconds while idle;
- `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no` to avoid proxy buffering;
- bounded initial replay (`replay=0..200`, default `50`);
- bounded server-side seen-id window and bounded desktop cache so long-lived streams do not grow memory without limit.

Example:

```bash
curl -N \
  -H 'Accept: text/event-stream' \
  'http://127.0.0.1:18427/api/v1/activity/stream?category=process&replay=25'
```

The native Control Center now has a `Workspace Logs` tab backed by this stream. It keeps a maximum of 500 events in memory, shows newest matching events first, and supports local chips for `ALL`, `ERROR`, `PROCESS`, `FILE`, and `SESSION` plus a chat-id substring filter. Selecting an event shows the normalized payload, phase, interaction id, dataset/source, and derived duration. Disconnects switch the panel to `RECONNECTING` and automatically reconnect with the last SSE event id.
