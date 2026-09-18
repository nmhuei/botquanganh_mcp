"""About view presenting README tools and ChatGPT Web usage guides."""

from __future__ import annotations

from typing import Any, Callable

from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings
from app.cli.desktop_views.theme import PALETTE, InspectorTabs


CHATGPT_PROMPT_TEMPLATE_VI = """Bạn là Trợ lý Vận hành Kỹ thuật kết nối với máy chủ qua BotQuangAnh Host MCP.
Bạn có khả năng thao tác tệp tin và thực thi lệnh shell an toàn trên máy chủ.

QUY TẮC VẬN HÀNH BẮT BUỘC:
1. KHỞI TẠO PHIÊN (BẮT BUỘC LƯỢT ĐẦU TIÊN):
   - Ngay trong lượt chat đầu tiên, hãy sinh mã phiên ngẫu nhiên (ví dụ: bqa-session-xxxxx) và gọi ngay tool:
     host_workspace_bind(chat_id="bqa-session-xxxxx")
   - Tuyệt đối không gọi các tool khác trước khi bind workspace thành công (nếu không sẽ bị từ chối với lỗi E6 BIND_REQUIRED).
2. KHÁM PHÁ MÔI TRƯỜNG & DANH MỤC:
   - Gọi host_knowledge(section="overview") để nắm phạm vi workspace và danh sách tài liệu.
   - Khi cần dùng công cụ dòng lệnh nào đó, gọi host_knowledge(section="tools", query="<tên_tool>") để xác minh tool đã được cài đặt.
3. AN TOÀN TỆP TIN:
   - Sử dụng đường dẫn tương đối trong workspace.
   - Đọc kỹ file bằng host_read_file trước khi sửa.
   - Ưu tiên host_replace_in_file để thay thế chính xác từng đoạn mã; hạn chế ghi đè cả file bằng host_write_file.
4. THỰC THI LỆNH SHELL:
   - Luôn gọi host_check_command(command="...") để kiểm tra chính sách an toàn trước khi chạy lệnh mới hoặc lệnh có tác động lớn.
   - Sau đó thực thi bằng host_run_command(command="...", cwd="...").
   - Đặt cwd phù hợp với thư mục dự án cần thao tác.
5. DUY TRÌ VÀ HỒI SINH TRẠNG THÁI:
   - Sau mỗi mốc công việc quan trọng, gọi host_save_note(title="...", content="...") để lưu ghi chú vào workspace.
   - Khi tiếp tục một phiên cũ, hãy đọc tệp STATE.md để khôi phục toàn bộ ngữ cảnh."""


CHATGPT_PROMPT_TEMPLATE_EN = """You are a Technical Operations Assistant connected to the host machine via BotQuangAnh Host MCP.
You have permissions to safely manipulate files and execute guarded shell commands.

MANDATORY OPERATING RULES:
1. SESSION INITIALIZATION (FIRST TURN REQUIREMENT):
   - On your very first turn, generate a unique session id (e.g. bqa-session-xxxxx) and immediately call:
     host_workspace_bind(chat_id="bqa-session-xxxxx")
   - Do not call any other tool before workspace binding succeeds (otherwise the server rejects calls with E6 BIND_REQUIRED).
2. ENVIRONMENT & TOOL DISCOVERY:
   - Call host_knowledge(section="overview") to inspect the active workspace root and system policies.
   - Before assuming a command is available, call host_knowledge(section="tools", query="<tool_name>").
3. FILESYSTEM SAFETY:
   - Use relative paths within the workspace.
   - Inspect files with host_read_file before making modifications.
   - Prefer host_replace_in_file for surgical text substitutions; avoid wholesale overwrite with host_write_file unless creating new files.
4. SHELL COMMAND SAFETY:
   - Always run host_check_command(command="...") to verify security policy before executing new or impactful commands.
   - Execute commands with host_run_command(command="...", cwd="...").
   - Always specify the appropriate working directory (cwd).
5. STATE PERSISTENCE & CONTEXT RESUMPTION:
   - After completing important milestones, call host_save_note(title="...", content="...") to persist durable notes into the workspace.
   - When resuming an existing chat session, inspect STATE.md to restore context before proceeding."""


README_TOOLS_VI = """================================================================================
           BOTQUANGANH HOST MCP — DANH MỤC VÀ TÀI LIỆU CÔNG CỤ (TOOLS)
================================================================================

BotQuangAnh Host MCP (UCS // SecretAgent) là máy chủ MCP chuyên dụng vận hành trên
giao thức Streamable HTTP (Stateless JSON) kết hợp Cloudflare Tunnel. Hệ thống cung
cấp 17 công cụ chuẩn hóa được thiết kế với cơ chế kiểm soát an toàn nghiêm ngặt,
cho phép mô hình AI (như ChatGPT, Claude) thực thi tác vụ trên máy chủ một cách
minh bạch, có lưu vết và không thể bị vượt quyền.

--------------------------------------------------------------------------------
1. NHÓM CÔNG CỤ HỆ THỐNG & SỨC KHỎE (SYSTEM & HEALTH)
--------------------------------------------------------------------------------
● health_check
  - Mục đích: Kiểm tra khả năng kết nối tới máy chủ MCP và thu thập các chỉ số
    vận hành cơ bản.
  - Tham số: Không có tham số.
  - Dữ liệu trả về:
    * ok (bool): Trạng thái hoạt động của server.
    * service & version: Tên và phiên bản dịch vụ ("botquanganh-host-mcp").
    * server_time: Thời gian hiện tại của máy chủ theo chuẩn UTC ISO-8601.
    * workspace: Đường dẫn thư mục gốc workspace đang được cấu hình.
    * command_policy: Chính sách thực thi lệnh hiện tại ("guarded" hoặc "allowlist").
    * metrics: Uptime hệ thống, tổng số request đã xử lý, số lỗi, lỗi xác thực.

● get_capabilities
  - Mục đích: Đọc danh sách năng lực chi tiết của máy chủ, các hạn mức an toàn
    đang kích hoạt và toàn bộ danh sách 17 công cụ host có sẵn.
  - Tham số: Không có tham số.
  - Dữ liệu trả về:
    * tools: Danh sách tên 17 công cụ MCP đang hoạt động.
    * limits:
      - max_timeout_seconds: Thời gian chờ tối đa cho mỗi lệnh (mặc định 60 giây).
      - max_single_file_bytes: Kích thước tệp tối đa khi đọc/ghi (3,000,000 bytes ~ 3MB).
      - max_output_bytes: Giới hạn byte đầu ra stdout/stderr (500,000 bytes ~ 500KB).
      - max_concurrent_commands: Số lệnh đồng thời tối đa (100 lệnh).
    * features: Các tính năng host_filesystem, host_command_execution, host_knowledge.

--------------------------------------------------------------------------------
2. NHÓM CÔNG CỤ KIẾN THỨC & TÀI LIỆU HƯỚNG DẪN (KNOWLEDGE & GUIDES)
--------------------------------------------------------------------------------
● host_knowledge
  - Mục đích: Tra cứu tài liệu quy tắc làm việc hoặc kiểm tra danh mục các phần mềm,
    công cụ dòng lệnh đã được cài đặt sẵn trên máy chủ host.
  - Tham số:
    * section (string, bắt buộc): Phân mục cần đọc:
      - "overview": Đọc cấu hình workspace, policy và danh sách file hướng dẫn.
      - "guide": Đọc quy tắc vận hành an toàn (WORKING_GUIDE.md).
      - "tools": Tra cứu danh mục công cụ đã cài đặt trên máy host (TOOL_CATALOG).
      - "search": Tìm kiếm từ khóa đồng thời trong tài liệu và danh mục tool.
      - "all": Đọc tổng hợp toàn bộ tài liệu và danh mục.
    * query (string, tùy chọn): Từ khóa tìm kiếm công cụ hoặc nội dung (ví dụ: "git", "python", "curl").
    * category (string, tùy chọn): Lọc theo nhóm công cụ ("version-control", "languages", "packages", "forensics").
    * available_only (bool, mặc định true): Chỉ hiển thị các công cụ đã được cài đặt thực tế trên máy host.
  - Trình tự làm việc khuyến nghị:
    1. host_knowledge(section="overview") -> Khám phá tổng quan môi trường.
    2. host_knowledge(section="guide") -> Đọc quy tắc làm việc an toàn.
    3. host_knowledge(section="tools", query="<tên_tool>") -> Xác minh lệnh trước khi gọi.

--------------------------------------------------------------------------------
3. NHÓM CÔNG CỤ THAO TÁC TỆP TIN & THƯ MỤC (FILESYSTEM TOOLS)
--------------------------------------------------------------------------------
● host_list_directory
  - Mục đích: Liệt kê các tệp tin và thư mục con tại đường dẫn chỉ định.
  - Tham số:
    * path (string, tùy chọn): Đường dẫn thư mục cần liệt kê (mặc định là thư mục hiện tại).
    * recursive (bool, mặc định false): Có quét đệ quy các thư mục con hay không.
    * max_entries (int, mặc định 200, tối đa 1000): Số lượng tệp/thư mục tối đa trả về.

● host_read_file
  - Mục đích: Đọc nội dung tệp tin văn bản định dạng UTF-8.
  - Tham số:
    * path (string, bắt buộc): Đường dẫn tệp tin cần đọc.
    * offset (int, mặc định 0): Vị trí byte bắt đầu đọc (dùng khi đọc file từng phần).
    * limit (int, tùy chọn): Số byte tối đa cần đọc.
    * max_bytes (int, mặc định 3,000,000): Ngưỡng an toàn chống tràn bộ nhớ (tối đa 3MB).

● host_write_file
  - Mục đích: Tạo mới hoặc ghi đè nội dung tệp tin văn bản UTF-8.
  - Tham số:
    * path (string, bắt buộc): Đường dẫn tệp tin cần ghi.
    * content (string, bắt buộc): Nội dung văn bản ghi vào tệp.
    * overwrite (bool, mặc định true): Cho phép ghi đè nếu tệp đã tồn tại. Nếu false và tệp đã có, sẽ báo lỗi.

● host_replace_in_file
  - Mục đích: Thay thế chính xác một đoạn văn bản trong tệp tin. Đây là phương thức
    khuyến nghị hàng đầu để chỉnh sửa mã nguồn, tránh nguy cơ ghi đè làm mất toàn bộ file.
  - Tham số:
    * path (string, bắt buộc): Đường dẫn tệp tin cần sửa.
    * old_text (string, bắt buộc): Đoạn văn bản chính xác cần tìm và thay thế.
    * new_text (string, bắt buộc): Đoạn văn bản mới thay thế vào.
    * expected_count (int, tùy chọn): Số lần xuất hiện dự kiến của old_text (mặc định 1).
      Nếu số lần tìm thấy thực tế khác expected_count, thao tác sẽ bị hủy để bảo vệ file.

● host_append_file
  - Mục đích: Nối thêm nội dung văn bản vào cuối tệp tin đã có (tạo mới nếu chưa có).
  - Tham số:
    * path (string, bắt buộc): Đường dẫn tệp tin.
    * content (string, bắt buộc): Nội dung văn bản cần nối thêm vào cuối file.

● host_make_directory
  - Mục đích: Tạo một thư mục mới trên hệ thống tệp tin host.
  - Tham số:
    * path (string, bắt buộc): Đường dẫn thư mục cần tạo.
    * parents (bool, mặc định true): Tự động tạo các thư mục cha nếu chưa tồn tại (tương đương mkdir -p).

● host_search_text
  - Mục đích: Tìm kiếm chuỗi ký tự đệ quy bên trong các tệp tin của thư mục.
  - Tham số:
    * query (string, bắt buộc): Chuỗi văn bản cần tìm kiếm.
    * path (string, tùy chọn): Thư mục bắt đầu quét tìm (mặc định là workspace).
    * max_results (int, mặc định 50, tối đa 200): Số kết quả khớp tối đa.
    * Có bộ đếm thời gian an toàn (deadline 15s) để chống treo khi quét thư mục khổng lồ.

--------------------------------------------------------------------------------
4. NHÓM CÔNG CỤ THỰC THI LỆNH TRÊN HOST (COMMAND EXECUTION)
--------------------------------------------------------------------------------
● host_check_command
  - Mục đích: Kiểm tra trước xem câu lệnh có được phép chạy theo chính sách bảo mật
    hiện tại hay không mà KHÔNG thực thi lệnh (Dry-run policy inspection).
  - Tham số:
    * command (string, bắt buộc): Chuỗi câu lệnh cần kiểm tra.
    * cwd (string, tùy chọn): Thư mục thực thi dự kiến.
  - Dữ liệu trả về:
    * allowed (bool): Câu lệnh có được phép chạy hay không.
    * reason: Lý do cho phép hoặc từ chối.
    * risk_score: Điểm số rủi ro ước lượng.
    * matched_patterns: Các mẫu quy tắc nhận diện được trong câu lệnh.

● host_run_command
  - Mục đích: Thực thi một lệnh shell có bảo vệ (guarded) trên máy chủ host.
  - Tham số:
    * command (string, bắt buộc): Chuỗi câu lệnh cần thực thi.
    * cwd (string, tùy chọn): Thư mục làm việc cho lệnh (mặc định là workspace).
    * timeout_seconds (int, mặc định 30, tối đa 60): Thời gian chờ tối đa.
    * check_first (bool, mặc định true): Tự động kiểm tra policy an toàn trước khi chạy.
  - Tính năng bảo vệ:
    * Ngăn chặn các câu lệnh nguy hiểm (như rm -rf /, ghi đè đĩa thô, fork bomb...).
    * Tự động che giấu (redact) token, API key, mật khẩu và biến môi trường nhạy cảm.
    * Cắt bớt (truncate) nếu dữ liệu stdout hoặc stderr vượt quá 500KB.
    * Ghi nhận đầy đủ vào nhật ký kiểm toán (audit log) và nhật ký hai pha của workspace.

--------------------------------------------------------------------------------
5. NHÓM CÔNG CỤ QUẢN LÝ PHIÊN & CHAT WORKSPACE (WORKSPACE TOOLS)
--------------------------------------------------------------------------------
● host_workspace_bind
  - Mục đích: RÀNG BUỘC PHIÊN CHAT VỚI WORKSPACE RIÊNG BIỆT.
  - QUAN TRỌNG: Đây là công cụ BẮT BUỘC phải gọi đầu tiên trong mỗi phiên chat khi
    hệ thống bật ATTRIBUTION_MODE=enforce (mặc định).
  - Tham số:
    * chat_id (string, bắt buộc): Mã định danh phiên chat (6 đến 64 ký tự chữ, số, '.', '-', '_').
  - Cơ chế hoạt động:
    * Khởi tạo thư mục riêng tại: ~/Downloads/bqa-workspaces/<chat_id>/
    * Tạo journal.jsonl (nhật ký hai pha bền vững) và STATE.md (bản chụp trạng thái).
    * Tạo thư mục notes/ chứa ghi chú dài hạn của mô hình.
    * Nếu gọi bất kỳ tool nào khác trước khi bind, server trả về mã lỗi E6 (BIND_REQUIRED).

● host_save_note
  - Mục đích: Lưu ghi chú dài hạn hoặc tóm tắt trạng thái phiên làm việc vào workspace.
  - Tham số:
    * title (string, bắt buộc): Tiêu đề ngắn gọn của ghi chú.
    * content (string, bắt buộc): Nội dung ghi chú chi tiết.
    * tags (list of string, tùy chọn): Danh sách các nhãn phân loại (tags).

--------------------------------------------------------------------------------
6. NHÓM CÔNG CỤ ĐIỀU TRA CTF (CTF INVESTIGATION SUITE)
--------------------------------------------------------------------------------
● ctf_triage_artifact
  - Mục đích: Tự động phân tích sơ bộ và phân loại tệp tin challenge / artifact CTF.
  - Tham số:
    * path (string, bắt buộc): Đường dẫn tệp tin artifact cần khảo sát.
  - Dữ liệu trả về: Định dạng tệp (MIME/magic), kích thước, hash MD5/SHA256,
    độ đo entropy, kiến trúc nhị phân, các chuỗi ký tự đáng ngờ.

● ctf_fetch_url
  - Mục đích: Gửi HTTP request có kiểm soát và lưu vết tới mục tiêu challenge web CTF.
  - Tham số:
    * url (string, bắt buộc): URL mục tiêu challenge được cấp phép.
    * method (string, mặc định "GET"): Phương thức HTTP (GET, POST, HEAD, OPTIONS).
    * headers (dict, tùy chọn): Các header HTTP gửi kèm.
    * data (string, tùy chọn): Body dữ liệu gửi kèm khi dùng POST/PUT.

● ctf_render_fetch_result
  - Mục đích: Hiển thị kết quả phản hồi HTTP từ ctf_fetch_url dưới dạng cấu trúc trực quan.
  - Tham số:
    * fetch_id (string, bắt buộc): Mã định danh kết quả fetch cần hiển thị.
"""


README_TOOLS_EN = """================================================================================
           BOTQUANGANH HOST MCP — TOOL CATALOG & SPECIFICATION
================================================================================

BotQuangAnh Host MCP (UCS // SecretAgent) is a dedicated host-management MCP
server operating over Streamable HTTP (Stateless JSON) paired with Cloudflare
Tunnel. It exposes 17 standardized tools designed under strict defense-in-depth
principles, enabling AI models (such as ChatGPT or Claude) to operate on the
host environment transparently, predictably, and securely.

--------------------------------------------------------------------------------
1. SYSTEM & HEALTH TOOLS
--------------------------------------------------------------------------------
● health_check
  - Purpose: Verify host MCP server reachability and collect fundamental runtime metrics.
  - Parameters: None.
  - Returns:
    * ok (bool): Server health status.
    * service & version: Service identity ("botquanganh-host-mcp", version).
    * server_time: Current UTC timestamp (ISO-8601).
    * workspace: Configured root workspace path on the host.
    * command_policy: Active execution policy ("guarded" or "allowlist").
    * metrics: Uptime seconds, total requests, error count, auth failure count.

● get_capabilities
  - Purpose: Retrieve service capabilities, active safety bounds, and the list of
    available host tools.
  - Parameters: None.
  - Returns:
    * tools: Array of all 17 registered and callable MCP tool names.
    * limits:
      - max_timeout_seconds: Hard execution deadline for shell commands (default: 60s).
      - max_single_file_bytes: Maximum single file read/write size (3,000,000 bytes ~ 3MB).
      - max_output_bytes: Truncation threshold for stdout/stderr (500,000 bytes ~ 500KB).
      - max_concurrent_commands: Maximum concurrent command executions (100).
    * features: host_filesystem, host_command_execution, host_knowledge flags.

--------------------------------------------------------------------------------
2. KNOWLEDGE & GUIDES TOOLS
--------------------------------------------------------------------------------
● host_knowledge
  - Purpose: Query workspace guidelines, operating procedures, or the catalog of
    installed CLI packages and development tools on the host.
  - Parameters:
    * section (string, required): Section to inspect:
      - "overview": Workspace paths, security policy, and guide document list.
      - "guide": Standard operating procedure and safety rules (WORKING_GUIDE.md).
      - "tools": Hardware & software tool inventory on the host (TOOL_CATALOG).
      - "search": Combined search across guides and tool inventory.
      - "all": Comprehensive dump of overview, guides, and tools.
    * query (string, optional): Search keyword (e.g. "git", "python", "curl", "gdb").
    * category (string, optional): Filter category ("version-control", "languages", "packages").
    * available_only (bool, default true): Restrict results to binaries verified installed on host.
  - Recommended Sequence:
    1. host_knowledge(section="overview") -> Discover workspace boundaries & policies.
    2. host_knowledge(section="guide") -> Read safety and editing rules.
    3. host_knowledge(section="tools", query="<tool>") -> Check tool existence before invocation.

--------------------------------------------------------------------------------
3. FILESYSTEM TOOLS
--------------------------------------------------------------------------------
● host_list_directory
  - Purpose: List files and subdirectories at a target path.
  - Parameters:
    * path (string, optional): Target directory (defaults to current workspace).
    * recursive (bool, default false): Recursively list nested subdirectories.
    * max_entries (int, default 200, max 1000): Maximum directory entries to return.

● host_read_file
  - Purpose: Read UTF-8 text file content.
  - Parameters:
    * path (string, required): Path to the target text file.
    * offset (int, default 0): Byte offset to begin reading from.
    * limit (int, optional): Maximum bytes to read in this call.
    * max_bytes (int, default 3,000,000): Hard safety limit against memory exhaustion (3MB).

● host_write_file
  - Purpose: Create a new UTF-8 text file or completely overwrite an existing file.
  - Parameters:
    * path (string, required): Path of the file to write.
    * content (string, required): Full text content to write.
    * overwrite (bool, default true): Whether to permit overwriting an existing file.

● host_replace_in_file
  - Purpose: Surgically replace an exact text snippet within an existing file.
    Strongly recommended over host_write_file to prevent accidental file clobbering.
  - Parameters:
    * path (string, required): Path to the file.
    * old_text (string, required): Exact string to search for and replace.
    * new_text (string, required): Exact replacement string.
    * expected_count (int, optional): Expected occurrence count (default 1).
      Aborts if the actual match count does not equal expected_count.

● host_append_file
  - Purpose: Append text content to the end of a file (creates file if non-existent).
  - Parameters:
    * path (string, required): Path of the file.
    * content (string, required): Text content to append.

● host_make_directory
  - Purpose: Create a directory on the host filesystem.
  - Parameters:
    * path (string, required): Directory path to create.
    * parents (bool, default true): Automatically create intermediate parent directories (mkdir -p).

● host_search_text
  - Purpose: Recursively search files for an exact text pattern.
  - Parameters:
    * query (string, required): String pattern to search for.
    * path (string, optional): Root directory to search within (defaults to workspace).
    * max_results (int, default 50, max 200): Maximum search match rows.
    * Includes a 15-second deadline timer to protect against directory traversal hangs.

--------------------------------------------------------------------------------
4. COMMAND EXECUTION TOOLS
--------------------------------------------------------------------------------
● host_check_command
  - Purpose: Inspect how a command would be handled under the current security policy
    WITHOUT executing the command (Dry-run inspection).
  - Parameters:
    * command (string, required): Command line string to analyze.
    * cwd (string, optional): Intended working directory.
  - Returns:
    * allowed (bool): Whether the policy permits this command.
    * reason: Policy rationale or matched rule.
    * risk_score: Estimated risk classification.
    * matched_patterns: Recognized command structure and tokens.

● host_run_command
  - Purpose: Execute a guarded shell command on the host.
  - Parameters:
    * command (string, required): Shell command line to execute.
    * cwd (string, optional): Working directory for the process (defaults to workspace).
    * timeout_seconds (int, default 30, max 60): Execution timeout limit.
    * check_first (bool, default true): Automatically run policy check prior to execution.
  - Guardrails:
    * Rejects dangerous patterns (e.g. destructive disk commands, fork bombs, rm -rf /).
    * Strips and redacts sensitive environment variables, tokens, and credentials.
    * Truncates stdout/stderr exceeding 500KB to maintain message safety.
    * Every invocation is recorded to audit logs and the workspace two-phase journal.

--------------------------------------------------------------------------------
5. WORKSPACE & SESSION MANAGEMENT TOOLS
--------------------------------------------------------------------------------
● host_workspace_bind
  - Purpose: BIND SESSION TO A DEDICATED PER-CHAT WORKSPACE.
  - CRITICAL: Must be invoked on the very first turn of any conversation when
    ATTRIBUTION_MODE=enforce (the default setting).
  - Parameters:
    * chat_id (string, required): Session identifier (6 to 64 chars [a-zA-Z0-9._-]).
  - Mechanics:
    * Creates or re-opens directory at: ~/Downloads/bqa-workspaces/<chat_id>/
    * Initializes durable two-phase journal.jsonl and STATE.md projection.
    * Creates notes/ directory for long-term agent notes.
    * Unbound calls to other tools trigger an immediate E6 (BIND_REQUIRED) error.

● host_save_note
  - Purpose: Save durable notes or milestone summaries to the active chat workspace.
  - Parameters:
    * title (string, required): Descriptive title.
    * content (string, required): Note markdown content.
    * tags (list of string, optional): Categorical tags.

--------------------------------------------------------------------------------
6. CTF INVESTIGATION SUITE
--------------------------------------------------------------------------------
● ctf_triage_artifact
  - Purpose: Automatically inspect and categorize a CTF challenge artifact.
  - Parameters:
    * path (string, required): Path to the artifact file.
  - Returns: File format, byte size, MD5/SHA256 hashes, entropy, suspicious strings.

● ctf_fetch_url
  - Purpose: Send scoped, audited HTTP requests to authorized CTF web challenge targets.
  - Parameters:
    * url (string, required): Target challenge URL.
    * method (string, default "GET"): HTTP method (GET, POST, HEAD, OPTIONS).
    * headers (dict, optional): Custom HTTP request headers.
    * data (string, optional): Payload body for POST/PUT.

● ctf_render_fetch_result
  - Purpose: Render or inspect raw fetch responses in structured format.
  - Parameters:
    * fetch_id (string, required): Fetch identifier to render.
"""


CHATGPT_WEB_GUIDE_VI = """================================================================================
          HƯỚNG DẪN CHI TIẾT KẾT NỐI VÀ SỬ DỤNG VỚI CHATGPT WEB
================================================================================

Tài liệu này hướng dẫn chi tiết từng bước cách kết nối BotQuangAnh Host MCP
với giao diện ChatGPT Web (chatgpt.com), giúp AI có khả năng thao tác tệp tin,
kiểm tra phần mềm và thực thi lệnh trực tiếp trên máy tính của bạn thông qua
đường truyền Cloudflare Tunnel bảo mật.

--------------------------------------------------------------------------------
BƯỚC 1: KHỞI ĐỘNG DỊCH VỤ VÀ LẤY URL CONNECTOR
--------------------------------------------------------------------------------
1. Kiểm tra dịch vụ trên máy của bạn:
   - Trên giao diện Desktop UI này, vào tab "Runtime".
   - Quan sát 2 mục: "MCP bridge" và "Cloudflare tunnel".
   - Cả hai đều phải hiển thị trạng thái màu xanh: "đang chạy" (running).
   - Nếu chưa chạy, bấm nút "Khởi động / nhận service" (Start / adopt service).

2. Sao chép URL Connector:
   - Nhấn nút "Sao chép URL connector" ngay trên thanh công cụ của tab About này.
   - Hoặc tại tab "Runtime", nhấn nút "Sao chép" (Copy) bên cạnh trường Endpoint.
   - Định dạng URL công khai:
     https://<subdomain-ngau-nhien>.trycloudflare.com/mcp
   * LƯU Ý: URL hợp lệ luôn có đuôi "/mcp". Không dùng URL trang chủ.

--------------------------------------------------------------------------------
BƯỚC 2: CẤU HÌNH TRÊN CHATGPT WEB (CHATGPT.COM)
================================================================================
Bạn có 2 lựa chọn tích hợp tùy theo loại tài khoản ChatGPT:

--- LỰA CHỌN A: DÙNG TÍNH NĂNG MCP CONNECTOR TRỰC TIẾP ---
(Áp dụng khi tài khoản ChatGPT của bạn có tính năng Connected Apps / MCP Servers)
1. Đăng nhập vào https://chatgpt.com.
2. Bấm vào ảnh đại diện cá nhân ở góc dưới bên trái -> Chọn "Settings" (Cài đặt).
3. Tìm mục "Connected Apps" (Ứng dụng đã kết nối) hoặc "Developer" -> "MCP Servers".
4. Bấm nút "Add MCP Server" (Thêm máy chủ MCP):
   - Server Name: BotQuangAnh MCP
   - Endpoint URL: Dán URL có đuôi /mcp đã sao chép ở Bước 1.
   - Transport Type: Chọn "Streamable HTTP" (hoặc HTTP Stateless JSON).
   - Authentication:
     * Chọn "None" (mặc định nếu REQUIRE_AUTH=false).
     * Hoặc chọn "Bearer Token" và nhập giá trị GATEWAY_TOKEN nếu máy chủ của bạn
       đã cấu hình REQUIRE_AUTH=true trong file .env.
5. Bấm "Save" hoặc "Connect".
   ChatGPT sẽ gửi request kiểm tra health_check và nạp toàn bộ 17 công cụ có sẵn.

--- LỰA CHỌN B: TẠO CUSTOM GPT (KHUYÊN DÙNG CHO TRẢI NGHIỆM TỐT NHẤT) ---
1. Truy cập https://chatgpt.com/gpts/editor (hoặc bấm "Explore GPTs" -> "Create").
2. Chọn tab "Configure":
   - Name: BotQuangAnh Host Assistant
   - Description: Trợ lý điều hành máy chủ và hỗ trợ lập trình qua BotQuangAnh MCP.
   - Instructions: Nhấn nút "Sao chép Prompt mẫu" trên tab About này và dán vào ô
     Instructions (xem chi tiết nội dung prompt ở BƯỚC 4 dưới đây).
3. Tại mục "Actions" hoặc "MCP Connectors":
   - Nhấn "Create new action" hoặc "Add connector".
   - Dán URL endpoint /mcp của bạn.
   - Cấu hình xác thực (None hoặc API Key / Bearer).
4. Bấm "Create" hoặc "Save" (chọn "Only me" để sử dụng riêng tư).

--------------------------------------------------------------------------------
BƯỚC 3: QUY TẮC BẮT TAY BẮT BUỘC TRONG PHIÊN CHAT (HANDSHAKE 3 BƯỚC)
--------------------------------------------------------------------------------
Hệ thống BotQuangAnh được cấu hình mặc định ATTRIBUTION_MODE=enforce để đảm bảo
tính cách ly và an toàn tuyệt đối giữa các cuộc hội thoại.

1. BƯỚC BẮT BUỘC — WORKSPACE BINDING:
   - Trong mỗi cuộc trò chuyện mới, câu lệnh ĐẦU TIÊN mà ChatGPT phải gọi là:
     host_workspace_bind(chat_id="bqa-<chuoi_dinh_danh>")
   - Quy tắc đặt chat_id:
     * Độ dài từ 6 đến 64 ký tự.
     * Bắt đầu bằng chữ cái hoặc chữ số.
     * Chỉ bao gồm các ký tự: chữ cái, chữ số, '.', '-', '_'.
     * Ví dụ hợp lệ: "chat-project-alpha", "bqa-investigation-01", "session_2026_09".
   - Tác dụng: Server sẽ tạo thư mục riêng tại:
     ~/Downloads/bqa-workspaces/<chat_id>/
     Mọi file, nhật ký thao tác (journal.jsonl) và trạng thái (STATE.md) của phiên
     chat đó sẽ được cô lập hoàn toàn trong thư mục này.
   - CẢNH BÁO QUAN TRỌNG: Nếu ChatGPT quên gọi host_workspace_bind mà gọi ngay các tool
     khác (như host_read_file hay host_run_command), máy chủ sẽ TỪ CHỐI THỰC THI và
     trả về mã lỗi: E6 (BIND_REQUIRED).

2. ĐỌC TÀI LIỆU & QUY TẮC:
   - ChatGPT gọi host_knowledge(section="overview") để kiểm tra đường dẫn thư mục
     gốc và các chính sách hệ thống.
   - ChatGPT gọi host_knowledge(section="guide") để tuân thủ quy tắc chỉnh sửa an toàn.

3. THỰC HIỆN TÁC VỤ AN TOÀN:
   - Luôn kiểm tra câu lệnh trước khi chạy: host_check_command(command="...").
   - Chạy lệnh với thư mục làm việc xác định: host_run_command(command="...", cwd="...").
   - Thay thế mã nguồn chính xác bằng host_replace_in_file.
   - Định kỳ lưu lại kết quả bằng host_save_note.

--------------------------------------------------------------------------------
BƯỚC 4: MẪU SYSTEM PROMPT CHUẨN ĐỂ DÁN VÀO CHATGPT
--------------------------------------------------------------------------------
Bấm nút "Sao chép Prompt mẫu" ở trên thanh công cụ, hoặc copy đoạn sau:

```
Bạn là Trợ lý Vận hành Kỹ thuật kết nối với máy chủ qua BotQuangAnh Host MCP.
Bạn có khả năng thao tác tệp tin và thực thi lệnh shell an toàn trên máy chủ.

QUY TẮC VẬN HÀNH BẮT BUỘC:
1. KHỞI TẠO PHIÊN (BẮT BUỘC LƯỢT ĐẦU TIÊN):
   - Ngay trong lượt chat đầu tiên, hãy sinh mã phiên ngẫu nhiên (ví dụ: bqa-session-xxxxx) và gọi ngay tool:
     host_workspace_bind(chat_id="bqa-session-xxxxx")
   - Tuyệt đối không gọi các tool khác trước khi bind workspace thành công (nếu không sẽ bị từ chối với lỗi E6 BIND_REQUIRED).
2. KHÁM PHÁ MÔI TRƯỜNG & DANH MỤC:
   - Gọi host_knowledge(section="overview") để nắm phạm vi workspace và danh sách tài liệu.
   - Khi cần dùng công cụ dòng lệnh nào đó, gọi host_knowledge(section="tools", query="<tên_tool>") để xác minh tool đã được cài đặt.
3. AN TOÀN TỆP TIN:
   - Sử dụng đường dẫn tương đối trong workspace.
   - Đọc kỹ file bằng host_read_file trước khi sửa.
   - Ưu tiên host_replace_in_file để thay thế chính xác từng đoạn mã; hạn chế ghi đè cả file bằng host_write_file.
4. THỰC THI LỆNH SHELL:
   - Luôn gọi host_check_command(command="...") để kiểm tra chính sách an toàn trước khi chạy lệnh mới hoặc lệnh có tác động lớn.
   - Sau đó thực thi bằng host_run_command(command="...", cwd="...").
   - Đặt cwd phù hợp với thư mục dự án cần thao tác.
5. DUY TRÌ VÀ HỒI SINH TRẠNG THÁI:
   - Sau mỗi mốc công việc quan trọng, gọi host_save_note(title="...", content="...") để lưu ghi chú vào workspace.
   - Khi tiếp tục một phiên cũ, hãy đọc tệp STATE.md để khôi phục toàn bộ ngữ cảnh.
```

--------------------------------------------------------------------------------
BƯỚC 5: QUAN SÁT THỜI GIAN THỰC QUA BẢNG ĐIỀU KHIỂN (DESKTOP UI)
--------------------------------------------------------------------------------
Trong lúc ChatGPT thực hiện các yêu cầu, bạn có thể giám sát toàn bộ hoạt động:
- Tab "Nhật ký Workspace" (Workspace Logs):
  Hiển thị luồng sự kiện hai pha trực tiếp qua SSE:
  * op_started: Ghi lại thời điểm bắt đầu thao tác.
  * op_result: Ghi lại kết quả trả về, thời gian thực thi (ms) và trạng thái thành công/thất bại.
  * Bộ lọc nhanh: ALL, ERROR, PROCESS, FILE, SESSION và tìm kiếm theo chat_id.
- Tab "Hoạt động GPT" (GPT Activity):
  Hiển thị danh sách các thư mục phiên làm việc, từng lệnh host_run_command đã chạy,
  mã thoát (exit code), thời lượng chạy và toàn bộ stdout/stderr.

--------------------------------------------------------------------------------
BƯỚC 6: XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING)
--------------------------------------------------------------------------------
1. Lỗi "Could not connect to server" hoặc "Connection refused" trên ChatGPT:
   - Nguyên nhân: Server hoặc Cloudflare tunnel chưa được khởi động.
   - Khắc phục: Vào tab Runtime trên UI, bấm "Khởi động / nhận service". Đợi trạng thái
     chuyển sang "Sẵn sàng" (Ready).

2. URL Tunnel bị đổi khi khởi động lại:
   - Hiện tượng: Khi chạy `bqa stop` rồi `bqa start`, Cloudflare tunnel sinh ra URL mới.
   - MẸO QUAN TRỌNG: Nếu bạn sửa file cấu hình .env hoặc cập nhật mã nguồn Python,
     hãy dùng nút "Khởi động lại MCP bridge" (Restart MCP bridge) hoặc lệnh `bqa restart`.
     Nút này chỉ khởi động lại bridge nội bộ mà GIỮ NGUYÊN tiến trình Cloudflare tunnel
     và URL hiện tại, bạn không cần phải cập nhật lại URL trên ChatGPT!

3. Lỗi E6: "BIND_REQUIRED":
   - ChatGPT quên gọi `host_workspace_bind` ở lượt đầu.
   - Khắc phục: Gõ tin nhắn cho ChatGPT: "Hãy gọi tool host_workspace_bind trước".

4. Lỗi E1: "INVALID_CHAT_ID":
   - Chat ID chứa ký tự không hợp lệ hoặc quá ngắn (<6 ký tự).
   - Khắc phục: Dùng định dạng chuẩn như "chat-2026-09-01-a".

5. Lỗi Command Blocked / Policy Denied:
   - Lệnh chứa các chuỗi nằm trong danh sách cấm của chế độ guarded (như rm -rf /, dd, mkfs...).
   - Khắc phục: Dùng `host_check_command` để xem lý do từ chối. Thay thế bằng lệnh an toàn hơn.
"""


CHATGPT_WEB_GUIDE_EN = """================================================================================
          STEP-BY-STEP INTEGRATION GUIDE FOR CHATGPT WEB
================================================================================

This document walks you through connecting BotQuangAnh Host MCP to ChatGPT Web
(chatgpt.com), giving AI models safe and audited capabilities to inspect files,
check installed tools, and execute guarded commands on your computer through an
encrypted Cloudflare Tunnel.

--------------------------------------------------------------------------------
STEP 1: START THE RUNTIME & COPY CONNECTOR URL
--------------------------------------------------------------------------------
1. Ensure the host service is active:
   - In this desktop interface, open the "Runtime" tab.
   - Verify that both "MCP bridge" and "Cloudflare tunnel" show green "running" badges.
   - If stopped, click "Start / adopt service".

2. Copy the Connector URL:
   - Click "Copy connector URL" in the toolbar of this About tab.
   - Alternatively, in the "Runtime" tab, click "Copy" beside the Endpoint field.
   - Or run in terminal: `bqa url`
   - The connector URL matches the format:
     https://<random-subdomain>.trycloudflare.com/mcp
   * IMPORTANT: A valid connector URL always ends with "/mcp". Do not use root URLs.

--------------------------------------------------------------------------------
STEP 2: CONFIGURE IN CHATGPT WEB (CHATGPT.COM)
--------------------------------------------------------------------------------
Choose either integration approach based on your ChatGPT tier:

--- OPTION A: DIRECT MCP CONNECTOR (RECOMMENDED WHEN AVAILABLE) ---
(Available if your account has Connected Apps or Developer MCP settings)
1. Sign in to https://chatgpt.com.
2. Open Settings (bottom-left avatar -> Settings) -> Connected Apps / MCP Servers.
3. Click "Add MCP Server":
   - Server Name: BotQuangAnh MCP
   - Endpoint URL: Paste your URL ending in /mcp copied from Step 1.
   - Transport Type: Streamable HTTP (Stateless JSON).
   - Authentication:
     * Select "None" (default when REQUIRE_AUTH=false).
     * Or select "Bearer Token" and enter your GATEWAY_TOKEN if REQUIRE_AUTH=true.
4. Click "Connect" or "Save". ChatGPT validates health_check and discovers all 17 tools.

--- OPTION B: CUSTOM GPT (RECOMMENDED FOR SPECIALIZED AGENTS) ---
1. Navigate to https://chatgpt.com/gpts/editor (or Explore GPTs -> Create).
2. Open the "Configure" tab:
   - Name: BotQuangAnh Host Assistant
   - Description: Host operations and technical investigation assistant via MCP.
   - Instructions: Click "Copy ChatGPT Prompt" in this tab's toolbar and paste the text
     into the Instructions box (see full text in STEP 4 below).
3. Under "Actions" or "MCP Connectors":
   - Add a connector pointing to your https://<subdomain>.trycloudflare.com/mcp endpoint.
   - Configure authentication (None or Bearer Token).
4. Save the GPT (e.g. set visibility to "Only me").

--------------------------------------------------------------------------------
STEP 3: MANDATORY 3-STEP HANDSHAKE PROTOCOL
--------------------------------------------------------------------------------
BotQuangAnh enforces ATTRIBUTION_MODE=enforce by default to guarantee complete
session isolation and audit integrity.

1. MANDATORY FIRST CALL — WORKSPACE BINDING:
   - In every new conversation, the VERY FIRST tool call ChatGPT makes MUST be:
     host_workspace_bind(chat_id="bqa-<unique_identifier>")
   - chat_id specifications:
     * 6 to 64 characters in length.
     * Starts with an ASCII letter or digit.
     * Contains only letters, numbers, '.', '-', and '_'.
     * Examples: "chat-alpha-01", "bqa-session-12345", "proj-refactor".
   - Purpose: Initializes an isolated directory at:
     ~/Downloads/bqa-workspaces/<chat_id>/
     All subsequent files, the two-phase journal.jsonl, and STATE.md are scoped here.
   - CRITICAL WARNING: If ChatGPT attempts to call any other tool (e.g. host_read_file
     or host_run_command) before binding, the server immediately REJECTS the request
     with error code: E6 (BIND_REQUIRED).

2. ENVIRONMENT DISCOVERY:
   - Call host_knowledge(section="overview") to inspect the active workspace root.
   - Call host_knowledge(section="guide") to review file editing safety rules.

3. CAREFUL EXECUTION:
   - Inspect command safety first: host_check_command(command="...").
   - Execute with guarded runner: host_run_command(command="...", cwd="...").
   - Apply surgical edits with host_replace_in_file.
   - Record durable progress notes with host_save_note.

--------------------------------------------------------------------------------
STEP 4: SYSTEM PROMPT TEMPLATE FOR CHATGPT
--------------------------------------------------------------------------------
Click "Copy ChatGPT Prompt" in the toolbar above, or copy this block:

```
You are a Technical Operations Assistant connected to the host machine via BotQuangAnh Host MCP.
You have permissions to safely manipulate files and execute guarded shell commands.

MANDATORY OPERATING RULES:
1. SESSION INITIALIZATION (FIRST TURN REQUIREMENT):
   - On your very first turn, generate a unique session id (e.g. bqa-session-xxxxx) and immediately call:
     host_workspace_bind(chat_id="bqa-session-xxxxx")
   - Do not call any other tool before workspace binding succeeds (otherwise the server rejects calls with E6 BIND_REQUIRED).
2. ENVIRONMENT & TOOL DISCOVERY:
   - Call host_knowledge(section="overview") to inspect the active workspace root and system policies.
   - Before assuming a command is available, call host_knowledge(section="tools", query="<tool_name>").
3. FILESYSTEM SAFETY:
   - Use relative paths within the workspace.
   - Inspect files with host_read_file before making modifications.
   - Prefer host_replace_in_file for surgical text substitutions; avoid wholesale overwrite with host_write_file unless creating new files.
4. SHELL COMMAND SAFETY:
   - Always run host_check_command(command="...") to verify security policy before executing new or impactful commands.
   - Execute commands with host_run_command(command="...", cwd="...").
   - Always specify the appropriate working directory (cwd).
5. STATE PERSISTENCE & CONTEXT RESUMPTION:
   - After completing important milestones, call host_save_note(title="...", content="...") to persist durable notes into the workspace.
   - When resuming an existing chat session, inspect STATE.md to restore context before proceeding.
```

--------------------------------------------------------------------------------
STEP 5: REAL-TIME OBSERVABILITY (DESKTOP UI)
--------------------------------------------------------------------------------
While ChatGPT executes operations, monitor activity live from the desktop console:
- "Workspace Logs" tab:
  Streams real-time two-phase events via Server-Sent Events (SSE):
  * op_started: Records operation start and timestamp.
  * op_result: Records result status, duration in milliseconds, and outcome.
  * Quick filter chips: ALL, ERROR, PROCESS, FILE, SESSION, and chat_id search.
- "GPT Activity" tab:
  Inspects per-chat workspace directories, every host_run_command invocation,
  exit codes, execution duration, and full stdout/stderr streams.

--------------------------------------------------------------------------------
STEP 6: TROUBLESHOOTING COMMON ISSUES
--------------------------------------------------------------------------------
1. "Connection refused" or "Could not connect to server" on ChatGPT:
   - Check the Runtime tab in this desktop console to confirm Cloudflare Tunnel is running.
   - Click "Start / adopt service" if components are stopped.

2. Preserving the Tunnel URL across server restarts:
   - Free Cloudflare tunnels generate a new subdomain if the tunnel process is stopped.
   - PRO TIP: To apply code changes or update .env WITHOUT breaking your ChatGPT URL,
     use the "Restart MCP bridge" button (or `bqa restart` in CLI). This restarts the
     Python backend while preserving the tunnel process and URL unchanged!

3. Error E6: "BIND_REQUIRED":
   - ChatGPT called a tool without binding first.
   - Solution: Send ChatGPT a message saying: "Please call host_workspace_bind first."

4. Error E1: "INVALID_CHAT_ID":
   - The chat_id format was invalid. Use 6-64 characters matching [a-zA-Z0-9._-].

5. Command Blocked / Policy Denied:
   - The command triggered guarded rules (e.g. destructive commands).
   - Solution: Use `host_check_command` to inspect the rationale and choose a safe alternative.
"""


class AboutView:
    """Desktop view displaying README tools specification and ChatGPT Web guide."""

    def __init__(
        self,
        *,
        root: Any,
        tk: Any,
        ttk: Any,
        parent: Any,
        on_message: Callable[[str, str], None],
        on_copy_endpoint: Callable[[], None] | None = None,
        get_endpoint: Callable[[], str] | None = None,
        translator: DesktopTranslator | None = None,
    ) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.parent = parent
        self.on_message = on_message
        self.on_copy_endpoint = on_copy_endpoint
        self.get_endpoint = get_endpoint
        self.translator = translator or DesktopTranslator()
        self.bindings = TranslationBindings(self.translator)
        self.inspector: InspectorTabs | None = None
        self._build(parent)

    def _build(self, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = self.ttk.Frame(parent, style="Surface.TFrame", padding=(12, 10))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        title_box = self.ttk.Frame(header, style="Surface.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        title_label = self.ttk.Label(title_box, style="SectionHeader.TLabel")
        self.bindings.bind(title_label, "about.title")
        title_label.pack(anchor="w")

        subtitle_label = self.ttk.Label(title_box, style="SurfaceSubtle.TLabel")
        self.bindings.bind(subtitle_label, "about.subtitle")
        subtitle_label.pack(anchor="w", padx=(8, 0))

        actions = self.ttk.Frame(header, style="Surface.TFrame")
        actions.grid(row=0, column=1, sticky="e")

        copy_endpoint_btn = self.ttk.Button(
            actions,
            style="Primary.TButton",
            command=self.copy_endpoint,
        )
        self.bindings.bind(copy_endpoint_btn, "about.action.copy_endpoint")
        copy_endpoint_btn.pack(side="left", padx=(0, 6))

        copy_prompt_btn = self.ttk.Button(
            actions,
            style="Secondary.TButton",
            command=self.copy_chatgpt_prompt,
        )
        self.bindings.bind(copy_prompt_btn, "about.action.copy_prompt")
        copy_prompt_btn.pack(side="left", padx=(0, 6))

        copy_section_btn = self.ttk.Button(
            actions,
            style="Secondary.TButton",
            command=self.copy_active_section,
        )
        self.bindings.bind(copy_section_btn, "about.action.copy_section")
        copy_section_btn.pack(side="left")

        holder = self.ttk.LabelFrame(parent, padding=8, style="InspectorCard.TLabelframe")
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)

        self.inspector = InspectorTabs(
            root=self.root,
            tk=self.tk,
            ttk=self.ttk,
            parent=holder,
            tabs=(
                ("readme_tools", self.translator.text("about.tab.readme_tools")),
                ("chatgpt_web", self.translator.text("about.tab.chatgpt_web")),
            ),
            on_message=self.on_message,
            copy_empty_message=self.translator.text("inspector.copy_empty"),
            copy_success_message=self.translator.text("about.copied_section"),
            copy_selection_success_message=self.translator.text("inspector.copy_selection_success"),
        )
        self.inspector.grid(row=0, column=0, sticky="nsew")

        for text in self.inspector.text_by_key.values():
            try:
                text.configure(wrap="word", padx=14, pady=12)
            except Exception:
                pass

        self._refresh_content()

    def set_translator(self, translator: DesktopTranslator) -> None:
        """Update active language for headers, button labels, tabs, and guide content."""
        self.translator = translator
        self.bindings.set_translator(translator)
        if self.inspector is not None:
            self.inspector.set_tab_label("readme_tools", translator.text("about.tab.readme_tools"))
            self.inspector.set_tab_label("chatgpt_web", translator.text("about.tab.chatgpt_web"))
            self.inspector.set_copy_messages(
                empty=translator.text("inspector.copy_empty"),
                success=translator.text("about.copied_section"),
                selection_success=translator.text("inspector.copy_selection_success"),
            )
        self._refresh_content()

    def _refresh_content(self) -> None:
        """Load text content according to the active language."""
        if self.inspector is None:
            return
        is_vi = self.translator.language == "vi"
        readme_content = README_TOOLS_VI if is_vi else README_TOOLS_EN
        chatgpt_content = CHATGPT_WEB_GUIDE_VI if is_vi else CHATGPT_WEB_GUIDE_EN
        self.inspector.set_content("readme_tools", readme_content)
        self.inspector.set_content("chatgpt_web", chatgpt_content)

    def copy_endpoint(self) -> None:
        """Copy the public connector endpoint URL to the clipboard."""
        if self.on_copy_endpoint is not None:
            self.on_copy_endpoint()
            return
        url = self.get_endpoint() if self.get_endpoint is not None else ""
        if not url:
            self.on_message("warn", self.translator.text("message.no_endpoint"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.root.update_idletasks()
        self.on_message("success", self.translator.text("about.copied_endpoint"))

    def copy_chatgpt_prompt(self) -> None:
        """Copy the ready-to-use ChatGPT system prompt to the clipboard."""
        is_vi = self.translator.language == "vi"
        prompt = CHATGPT_PROMPT_TEMPLATE_VI if is_vi else CHATGPT_PROMPT_TEMPLATE_EN
        self.root.clipboard_clear()
        self.root.clipboard_append(prompt)
        self.root.update_idletasks()
        self.on_message("success", self.translator.text("about.copied_prompt"))

    def copy_active_section(self) -> None:
        """Copy the full text of the currently selected section."""
        if self.inspector is not None:
            self.inspector.copy_active()
