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
