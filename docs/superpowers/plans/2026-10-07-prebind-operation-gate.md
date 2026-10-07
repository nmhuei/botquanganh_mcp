# MCP Pre-Bind Operation Gate Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement each task. Track steps with checkboxes. Delegate only when the user requests delegation.

**Goal:** Chỉ cho phép server_info, workspace_context(bind) và workspace_context(list) trước bind thành công.

**Architecture:** Giữ tám MCP tool hiện tại. Dùng guard chung nhận tool, action và chat_id. Lưu binding theo workspace trong bộ nhớ server vì HTTP đang stateless.

**Tech Stack:** Python, FastMCP, pytest, threading.RLock và các helper workspace hiện có.

**Spec:** Yêu cầu trong hội thoại và /home/light/Downloads/bqa-trash/mcp_prebind_deep_research/report.json.

## 1. Phạm vi và quyết định

- MCP chỉ có một người dùng.
- Cho phép list trước bind để chọn workspace cần tiếp tục.
- Giữ workspace_context là một tool chứa sáu action.
- Chặn tại server khi gọi tool, kể cả tool đã được discovery.
- Không cần tách bind hoặc list thành MCP tool mới.
- Không cần đổi schema hoặc thêm token cho mô hình một người dùng.
- Giữ action mặc định là bind.
- Giữ chuẩn hóa action bằng strip và lower để bảo toàn tương thích.
- Không thêm kiểm soát tenant hoặc quyền sở hữu nhiều người dùng.
- Sandbox của terminal là công việc riêng. Guard này kiểm soát điều kiện bind.

## 2. Các lỗi đã đối chiếu với mã nguồn

1. app/tools_common.py miễn bind cho toàn bộ workspace_context.
2. workspace_context gọi guard cho note, state, hypotheses và resume nhưng guard miễn trừ chính tool đó.
3. Guard hiện nhận chat_id hợp lệ và kiểm tra meta.json; không chứng minh đã gọi bind qua MCP.
4. app/tools/task.py tạo task manager và dispatch ngay, không gọi guard.
5. workspace_context xử lý action không hợp lệ sau khi tạo workspace manager.
6. server_info bỏ qua rejection của guard: validated, _ = _guard_chat_id(...).
7. MCP_STATELESS_HTTP mặc định true; ContextVar chỉ có phạm vi context thực thi, không đảm bảo lưu giữa request.

Research đưa ra nguyên tắc thiết kế. Các điểm trên đến từ đọc mã hiện tại, không phải kết quả kiểm thử.

## 3. Định nghĩa bind để triển khai

Đơn vị binding là workspace chat_id trong một tiến trình MCP server.

Sau workspace_context(bind) thành công, server ghi nhận workspace đó đã bind.
Các request sau gửi chat_id đã ghi nhận được phép dùng tool thao tác.
List không ghi nhận binding.
Chỉ tạo directory hoặc meta.json không ghi nhận binding.
Restart server xóa binding trong bộ nhớ; gọi bind lại để tiếp tục workspace trên đĩa.

Không dùng một biến global active_chat_id để tự chọn workspace cho mọi request.
Mỗi request thao tác phải xác định chat_id; không tự lấy latest hoặc .last_session.
Một người dùng vẫn có thể chạy nhiều workspace đồng thời.

Giới hạn cần nói rõ: đây là binding theo workspace trong server, không phải theo từng hội thoại ChatGPT.
Một hội thoại khác biết chat_id đã bind có thể dùng lại workspace đó trong cùng tiến trình.
Muốn bắt từng hội thoại bind riêng cần danh tính hội thoại hoặc binding token trong giao thức.
Điều đó thay đổi schema và vượt phạm vi cơ chế tương thích hiện tại.

## 4. Ma trận chính sách

| Tool hoặc action | Chưa bind | Đã bind |
|---|---|---|
| server_info | Cho phép | Cho phép |
| workspace_context(bind) | Cho phép | Cho phép tạo hoặc bind lại |
| workspace_context(list) | Cho phép | Cho phép |
| workspace_context(note) | E6 BIND_REQUIRED | Cho phép |
| workspace_context(state) | E6 BIND_REQUIRED | Cho phép |
| workspace_context(hypotheses) | E6 BIND_REQUIRED | Cho phép |
| workspace_context(resume) | E6 BIND_REQUIRED | Cho phép |
| workspace_explore | E6 BIND_REQUIRED | Cho phép |
| workspace_search | E6 BIND_REQUIRED | Cho phép |
| workspace_edit | E6 BIND_REQUIRED | Cho phép |
| terminal_execute | E6 BIND_REQUIRED | Cho phép |
| task, tất cả action | E6 BIND_REQUIRED | Cho phép |
| web_intelligence | E6 BIND_REQUIRED | Cho phép |
| workspace_context action không hợp lệ | INVALID_ACTION | INVALID_ACTION |

ID sai định dạng trả E1 INVALID_CHAT_ID.
ID đúng định dạng nhưng chưa bind trả E6.
Workspace bị xóa hoặc metadata thay đổi danh tính trả E6 và hủy binding cũ.
Giữ payload error và giới hạn response hiện có.

## 5. File và interface dự kiến

| File | Trách nhiệm |
|---|---|
| app/workspace_binding.py, mới | Registry binding trong bộ nhớ; khóa truy cập; kiểm tra workspace incarnation |
| app/tools_common.py | Policy theo tool/action; guard chung; error E1/E6 |
| app/tools/workspace_context.py | Chuẩn hóa action; guard trước dispatch; ghi nhận bind thành công |
| app/tools/server_info.py | Cho phép thông tin server trước bind; xử lý lỗi ID rõ ràng |
| app/tools/workspace_explore.py | Dùng guard trước journal và filesystem |
| app/tools/workspace_search.py | Dùng guard trước search engine |
| app/tools/workspace_edit.py | Dùng guard trước journal và ghi file |
| app/tools/terminal_execute.py | Dùng guard trước mkdir, task manager và subprocess |
| app/tools/task.py | Thêm guard trước get_task_manager |
| app/tools/web_intelligence.py | Dùng guard trước fetch |
| app/chat_identity.py | Sửa mô tả cũ về ngoại lệ bind |
| app/chat_errors.py | Đồng bộ contract ba thao tác pre-bind |
| knowledge/WORKING_GUIDE.md | Quy trình server_info → list → bind → thao tác |
| knowledge/TOOL_CATALOG.json | Đồng bộ mô tả theo cơ chế discovery hiện có |
| docs/CHAT_WORKSPACES.md | Giải thích bind, resume và restart |
| tests/test_workspace_binding.py, mới | Binding registry và concurrency |
| tests/test_prebind_operation_gate.py, mới | Ma trận quyền và không chạy business effects |
| tests/test_workspace_context.py | Bind, list, resume và action không hợp lệ |
| tests/test_task_tool.py | Guard cho task; bảo toàn action và output |
| tests/test_enforce_mode_config.py | Contract và chế độ cấu hình |

Interface nội bộ:

```python
class WorkspaceContextAction(str, Enum):
    BIND = "bind"
    LIST = "list"
    NOTE = "note"
    STATE = "state"
    HYPOTHESES = "hypotheses"
    RESUME = "resume"

register_workspace_binding(root: Path, chat_id: str, created_at: str) -> None
has_workspace_binding(root: Path, chat_id: str) -> bool
validate_workspace_binding(root: Path, chat_id: str) -> bool
forget_workspace_binding(root: Path, chat_id: str) -> None

_guard_operation(
    tool: str,
    chat_id: str | None,
    *,
    action: WorkspaceContextAction | None = None,
) -> tuple[str | None, dict[str, Any] | None]
```

Dùng Enum cho action nội bộ.
Có thể giữ action: str ở API để bảo toàn hành vi strip/lower.
Không thêm registry thủ công cho mọi tool mới: tool ngoài bootstrap mặc định cần bind.

## 6. Task 1 — Registry binding thực sự

**Files:** app/workspace_binding.py; tests/test_workspace_binding.py.

- [x] Viết test: registry ban đầu rỗng; chat_id chưa đăng ký bị từ chối.
- [x] Viết test: directory và meta.json tự tạo không đủ để có binding.
- [x] Viết test: đăng ký một workspace không cho phép workspace khác.
- [x] Viết test: quên binding khiến workspace quay lại trạng thái chưa bind.
- [x] Viết test: workspace bị xóa hoặc tạo lại với created_at khác không dùng binding cũ.
- [x] Viết test: hai workspace đăng ký đồng thời giữ nguyên danh tính riêng.
- [x] Chạy test trước implementation và ghi nhận lỗi đúng nguyên nhân.
- [x] Tạo registry với threading.RLock và key gồm root chuẩn hóa cùng chat_id.
- [x] Lưu created_at từ meta.json làm danh tính phiên tạo workspace.
- [x] Dùng load_workspace_meta hiện có để kiểm tra metadata sau khi registry có entry.
- [x] Không truy cập directory workspace nếu registry không có entry.
- [x] Chạy lại các test registry.

Run:

```bash
pytest tests/test_workspace_binding.py -q --basetemp=/home/light/Downloads/bqa-trash/prebind-registry-tests
```

Expected: test phân biệt được workspace tồn tại và workspace đã bind.

## 7. Task 2 — Policy theo thao tác

**Files:** app/tools_common.py; tests/test_prebind_operation_gate.py.

- [x] Viết test ba thao tác bootstrap được phép khi không có chat_id.
- [x] Viết test các action khác và sáu tool thao tác trả E6 khi không có binding.
- [x] Viết test truyền chat_id có meta.json nhưng chưa đăng ký vẫn trả E6.
- [x] Viết test ID sai định dạng trả E1.
- [x] Viết test ID đã bind được guard trả lại nguyên trạng.
- [x] Viết test cấu hình enforce không cho HOST_CHAT_WORKSPACES=False bỏ qua bind.
- [x] Chạy test để ghi nhận lỗi trước sửa.
- [x] Xóa miễn trừ theo toàn bộ workspace_context.
- [x] Thêm predicate bootstrap cho server_info và context action bind/list.
- [x] Thêm _guard_operation và kết nối registry.
- [x] Giữ _guard_chat_id làm wrapper nếu còn caller nội bộ; wrapper không miễn toàn bộ context.
- [x] Bảo toàn hành vi off/tag/strict khi không yêu cầu enforce.
- [x] Nếu enforce nhưng workspace infrastructure tắt, từ chối operational call với E6.
- [x] Chạy lại test.

Luồng guard:

```text
Nhận tool/action/chat_id
→ Xác định thao tác bootstrap
→ Nếu bootstrap: cho handler xử lý
→ Nếu enforce: kiểm tra định dạng chat_id
→ Kiểm tra registry đã ghi nhận bind
→ Kiểm tra metadata còn thuộc workspace đã đăng ký
→ Cho handler chạy hoặc trả E1/E6
```

Run:

```bash
pytest tests/test_prebind_operation_gate.py -q --basetemp=/home/light/Downloads/bqa-trash/prebind-gate-tests
```

Expected: có ID hoặc metadata không đủ để bỏ qua bind.

## 8. Task 3 — Context dispatch và đăng ký bind

**Files:** app/tools/workspace_context.py; tests/test_workspace_context.py; tests/test_workspace_context_regressions.py.

- [x] Viết test list trước bind trả danh sách và không mở quyền thao tác.
- [x] Viết test bind mới thành công rồi state/note hoạt động.
- [x] Viết test list → chọn chat_id → bind(resume_id) → resume.
- [x] Viết test bind lỗi không đăng ký workspace.
- [x] Viết test action không hợp lệ không gọi _get_workspace_manager.
- [x] Viết test chuẩn hóa " LIST " thành list; giữ mặc định bind.
- [x] Viết test reset registry mô phỏng restart; list vẫn hoạt động, state cần bind lại.
- [x] Chạy các test mới để ghi nhận lỗi.
- [x] Parse action thành Enum trước khi tạo manager.
- [x] Gọi guard cho mọi context action, bao gồm bind và list.
- [x] Chỉ tạo manager sau action validation và authorization.
- [x] Bind thực hiện create_or_bind và khởi tạo các context file hiện có.
- [x] Đăng ký binding sau tất cả bước bind bắt buộc hoàn tất, ngay trước success response.
- [x] Ghi nhận created_at từ metadata do WorkspaceManager tạo.
- [x] Không đăng ký binding trong list hoặc helper create_or_bind thông thường.
- [x] Giữ response bind/list hiện tại.
- [x] Chạy lifecycle và regression tests.

Run:

```bash
pytest tests/test_workspace_context.py tests/test_workspace_context_regressions.py tests/test_prebind_operation_gate.py -q --basetemp=/home/light/Downloads/bqa-trash/prebind-context-tests
```

Expected: chọn session cũ rồi bind lại hoạt động qua các request độc lập.

## 9. Task 4 — Tích hợp đủ tám tool

**Files:** toàn bộ app/tools/*.py; tests/test_prebind_operation_gate.py; tests/test_task_tool.py.

- [x] Thêm ma trận test handler thực tế, không chỉ unit test guard.
- [x] Chặn context manager getter trong test context bị từ chối.
- [x] Chặn journal/path resolver/search engine trong test explore/search/edit.
- [x] Chặn get_task_manager, mkdir và Popen trong test terminal bị từ chối.
- [x] Chặn get_task_manager và bridge_task_coro trong test task bị từ chối.
- [x] Chặn _fetch_url trong test web bị từ chối.
- [x] Test mọi task action: wait, tail, kill, list, status và send_input.
- [x] Test task(list) khác workspace_context(list): task(list) vẫn cần bind.
- [x] Chạy ma trận để tìm handler bỏ sót.
- [x] Cập nhật sáu tool operational dùng guard chung trước business effects.
- [x] Thêm guard vào task trước dòng manager = get_task_manager().
- [x] Trả payload E6 từ async task khi bị từ chối.
- [x] Sửa server_info để xử lý rejection ID thay vì bỏ qua biến rejection.
- [x] Giữ server_info không có chat_id được phép.
- [x] Điều chỉnh test task hiện dùng ID "chat" để dùng ID hợp lệ và bind fixture.
- [x] Chạy targeted tests cho đủ tám tool.

Expected: request bị từ chối không chạy hiệu ứng nghiệp vụ.
Guard có thể đọc metadata để xác minh một entry đã đăng ký.
Transport log có thể ghi nhận request bị từ chối; không tạo workspace journal cho thao tác đó.

## 10. Task 5 — Contract, metadata và tài liệu

**Files:** app/chat_errors.py; app/chat_identity.py; tool descriptions; knowledge/WORKING_GUIDE.md; knowledge/TOOL_CATALOG.json; docs/CHAT_WORKSPACES.md.

- [x] Sửa comment hiện nói bind là ngoại lệ duy nhất.
- [x] Ghi rõ ba thao tác pre-bind được phép.
- [x] Mô tả workspace_context theo từng action, tránh nói cả tool được miễn bind.
- [x] Giữ hướng dẫn lỗi E6: list workspace nếu cần, bind, rồi dùng chat_id trả về.
- [x] Mô tả restart server yêu cầu bind lại.
- [x] Mô tả binding theo workspace/server, không tự chọn latest cho operational calls.
- [x] Đối chiếu catalog với cơ chế discovery hiện có trước khi cập nhật metadata.
- [x] Giữ tools/list và api_tool.list_resources chỉ phục vụ discovery.
- [x] Sửa test_semantic_contract_block_is_present_in_chat_errors theo chính sách mới.
- [x] Kiểm tra tên tám tool và schema công khai không đổi.

Không cần dynamic tools/list để đạt việc chặn server.
Nếu bổ sung ẩn tool theo trạng thái sau này, vẫn phải giữ guard tại invocation.

## 11. Task 6 — Kiểm chứng và đưa thay đổi vào runtime

- [x] Chạy suite targeted gồm registry, guard, context và sáu tool operational.
- [x] Dùng --basetemp trong /home/light/Downloads/bqa-trash/ cho dữ liệu kiểm thử.
- [x] Kiểm tra binding giữa hai request MCP riêng biệt.
- [x] Kiểm tra ContextVar của request đầu không tự lan sang request sau.
- [x] Kiểm tra metadata cũ vẫn list được và bind lại được.
- [x] Kiểm tra một workspace đã bind không mở quyền cho chat_id khác.
- [x] Kiểm tra direct tools/call bị từ chối dù client có cache schema cũ.
- [x] Chạy các test contract/schema có liên quan.
- [x] Chỉ mở rộng test khi phát hiện lỗi hoặc rủi ro chưa được giải quyết.
- [x] Review diff và ghi nhận các thay đổi có sẵn trong dirty worktree.
- [x] Không git add toàn file đang chứa thay đổi ngoài phạm vi mà chưa kiểm tra từng hunk.
- [x] Chuẩn bị thay đổi runtime sau khi source và kiểm chứng đã sẵn sàng.
- [x] Nếu cần restart MCP service, xác định service riêng; giữ nguyên tiến trình Cloudflare tunnel.
- [x] Kiểm tra trực tiếp server_info, list, bind và một operational call sau restart.
- [x] Ghi nhận kết quả thực tế từ tool result và event log.

## 12. Điều kiện nghiệm thu

1. Trước bind, ba thao tác được phép đều hoạt động.
2. Mọi operational action khác trả E6 trước business effects.
3. Truyền ID của workspace tồn tại mà chưa bind không mở quyền.
4. List không mở quyền thao tác.
5. Bind thành công mở quyền đúng chat_id.
6. Bind thất bại không mở quyền mới.
7. Restart server yêu cầu bind lại; dữ liệu workspace còn nguyên.
8. Unknown action trả INVALID_ACTION trước manager access.
9. Task được bảo vệ giống các tool khác.
10. Các request đồng thời không dùng nhầm workspace.
11. Tên tool và schema tương thích với connector hiện tại.
12. Kết quả nghiệm thu có tool result hoặc test evidence.

## 13. Bằng chứng và hạn chế research

Research có năm session, mỗi session mười lượt.
Event log ghi nhận truy vấn web mới trong mười lăm lượt.
Các lượt còn lại phân tích hoặc dùng lại nguồn trước đó.
Không diễn giải số lượt thành năm mươi lần kiểm tra nguồn độc lập.

Nguồn nguyên tắc:
- MCP Tools: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- MCP Security: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/SECURITY.md
- OWASP Authorization: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

Các thiết kế registry và trạng thái restart trong plan là quyết định triển khai.
Chúng dựa trên HTTP stateless và mô hình một người dùng đã xác nhận.

