# Core Operating Rules & Engineering Principles (ASD-STE100 Standard)

Use the connected BQA MCP instead of container.exec for host operations.

## 1. Network and Cloudflare Tunnel Invariant
- **Critical Tunnel Rule:** Do NOT modify, restart, or terminate the running Cloudflare tunnel process.
- **Tunnel URL Persistence:** The tunnel URL is stored in `logs/tunnel_url.txt`. Read this file dynamically. Do NOT hardcode tunnel URLs.

## 2. Zero-Hardcoding and Dynamic Configuration Standard
- **Single Source of Truth:**
  - Load all configuration parameters from `.env` via `app.config`.
  - Use `app.chat_workspace.read_limits()` to read workspace quotas and capacity thresholds.
  - Do NOT hardcode numbers (for example: workspace limits, timeouts, buffer sizes) in business modules.
- **Desktop UI Synchronization:**
  - Operational parameters (`HOST_CHAT_MAX_WORKSPACES`, `HOST_CHAT_QUOTA_MB`, `HOST_CHAT_ROOT_MAX_GB`, timeouts) MUST be configurable via the Desktop Settings UI.
  - Updates saved in UI MUST persist to `.env` using atomic file writes.

## 3. Desktop GUI and WebKit Event Safety
- **Event Suppression:**
  - Stop drag and pointer propagation on interactive buttons (such as delete and action buttons) in WebKitGTK.
  - Prevent WebKit drag conflicts using `mousedown`, `pointerdown`, and `dragstart` event listeners.
- **IPC Serialization:**
  - Use structured JSON serialization via `serde_json`.
  - Do NOT assemble JSON strings manually in IPC communication.

## 4. File Deletion and Permission Resilience
- **Robust Removal:**
  - Handle read-only files and directory permissions before recursive deletion.
  - Apply `chmod 0o700` to directories and `chmod 0o600` to files when encountering permission failures during workspace cleanup.
- **Workspace Eviction:**
  - Evict the lightest workspace (smallest byte footprint) when workspace capacity reaches the configured threshold.
  - Use older modification time (`st_mtime`) as the deterministic tie-breaker.
  - Protect all active and bound workspace IDs from eviction.

## 5. Isolated Test Environment & Sandbox Rule (bqa-trash)
- **Mandatory Sandbox Location (`~/Downloads/bqa-trash/`):**
  1. *Sân chơi nghịch ngợm thoải mái:* Cho phép tải file tạm, chạy script nháp, cào dữ liệu rác, bung file nén trong `~/Downloads/bqa-trash/`.
  2. *Không bị mất khi tắt máy:* Nằm trên ổ cứng thật nên dữ liệu không bị xóa khi shutdown (ưu điểm hơn `/tmp`).
  3. *Thùng rác một chạm:* Người dùng có thể xóa sạch toàn bộ thư mục này bất kỳ lúc nào mà không sợ xóa nhầm mã nguồn chính.
- **Cleanliness:**
  - Do NOT create test artifacts directly in repository roots.

## 6. ASD-STE100 Documentation and Communication Standard
- **Scope:** All documentation, guidelines, code comments, and agent communications MUST follow ASD-STE100 principles.
- **Rules:**
  - Write short, clear sentences (< 25 words).
  - Use imperative verbs for technical instructions.
  - Present data in structured tables or numbered lists.
  - Eliminate ambiguous phrasing and duplicate terminology.

## 7. Mandatory Multi-Source and Multi-Agent Deep Research Standard
- **Zero Single-Turn Research Invariant:**
  - Never accept findings from a single, isolated GPT research turn.
  - Single-turn answers contain superficial reasoning and unverified assumptions.
- **Mandatory Multi-Agent Deep Research Protocol:**
  - Launch multiple concurrent GPT research tracks for complex architectural tasks.
  - Combine distinct perspectives: system ergonomics, Linux kernel mechanics, resource quotas, and adversarial red-teaming.
  - Cross-validate outputs across independent research sessions before drafting implementation plans.
  - Require concrete code patterns, failure mode analyses, and testable invariants from research agents.

## 8. Anti-Duplication (DRY), Anti-Hardcoding, and Code Cleanliness Invariants
- **Anti-Duplication (DRY) Rule:**
  - Do NOT duplicate code across tools, services, or test files.
  - Extract common logic (payload limits, process supervision, validation) into shared utility modules.
  - Reuse pytest fixtures instead of copying test setups.
- **Zero-Hardcoding & Magic Value Prohibition:**
  - Do NOT use magic numbers in code. Define all constants in configuration models.
  - Do NOT use raw string literals for states, actions, or event types. Use typed Enums.
  - Load all timeouts, memory limits, byte ceilings, and task quotas from `app.config`.
- **Code Cleanliness & Anti-Pattern Defense:**
  - Eliminate dead code, unused variables, and unused imports before audit.
  - Do NOT shadow Python built-in names (such as `id`, `input`, `format`, `type`, `dir`).
  - Keep functions small and focused on one task (< 50 lines).
  - Wrap shared mutable state with asynchronous locks to prevent race conditions.


