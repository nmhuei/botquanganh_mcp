# Rust Native Desktop Studio (VJP-PRO Suite) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a pure Rust Native Desktop Studio (`crates/bqa_desktop` using Tao + Wry/WebKitGTK + embedded HTML/CSS/JS in `crates/bqa_desktop/ui/index.html`) that ports all visual, interaction, and data capabilities from the other UI branches while permanently eliminating the GUI freeze/hang during workspace loading.

**Architecture:** The Rust backend (`crates/bqa_desktop/src/main.rs`) acts as an asynchronous, non-blocking data provider using a background worker thread for disk I/O (scanning workspaces, reading `meta.json`, streaming reverse-tail lines from `journal.jsonl`). It communicates bi-directionally with the embedded Webview visual layer via typed IPC messages and JavaScript callbacks (`evaluate_script`). The Webview layer (`crates/bqa_desktop/ui/index.html`) features a hard failsafe boot sequence (guaranteed auto-dismiss under 1.8s), live workspace session switching, 4-tab command inspector, live log tailing with filter chips, runtime lifecycle controls with modal confirmation, 16 themes, and bilingual EN/VI support.

**Tech Stack:** Rust 2021, Tao, Wry (WebKitGTK on Linux), Serde/Serde-JSON, HTML5, Tailwind CSS, JavaScript (ES6+), Python FastMCP/bqa CLI.

---

## Global Constraints

- Exclusively use the Rust Desktop Studio engine (`crates/bqa_desktop`). No Python Qt (`PySide6`) or Tkinter UI dependencies.
- Fix the root cause of GUI freezing on workspace load:
  - NEVER perform synchronous, blocking whole-file reading (`fs::read_to_string`) on multi-megabyte `journal.jsonl` files within the Tao main event loop.
  - Implement non-blocking background scanning and buffered reverse-tail line streaming.
  - Webview boot overlay MUST have a hard-timeout failsafe (maximum 1.8s) so it NEVER freezes at 55% "LOADING WORKSPACES", with `[ESC]` dismiss always active.
- Preserve and integrate all UI features from other branches:
  - Runtime overview (FastMCP server status, tunnel, gateway, start/stop/restart actions with confirmation modal, `.env` config editor).
  - Workspaces & Activity (real sessions list from `~/Downloads/bqa-workspaces`, command history stream with status badges, 4-tab inspector for Metadata, STDOUT, STDERR, Raw JSON).
  - System Logs (log stream, category filter chips: all, error, process, file, session).
  - 16 Themes (UCS Terminal, Command Center, UCS Light Pro, Exodia Neon, Cyberpunk, etc.) and EN/VI translation.
- CLI wiring: `bqa ui` launches `target/release/bqa-desktop`.

---

### Task 1: Asynchronous Rust Data Provider & Two-Way IPC Engine

**Files:**
- Modify: `crates/bqa_desktop/src/main.rs`
- Modify: `crates/bqa_desktop/Cargo.toml`

**Interfaces:**
- Consumes: `~/Downloads/bqa-workspaces` (or `HOST_CHAT_ROOT`), `.env`, `logs/gateway.log`, `logs/server.log`.
- Produces: Two-way IPC dispatcher:
  - `get_workspaces` -> `window.__onWorkspacesLoaded(data)`
  - `get_workspace_journal(chat_id)` -> `window.__onJournalLoaded(chat_id, data)`
  - `get_runtime_status` -> `window.__onRuntimeStatusLoaded(data)`
  - `lifecycle_action(action)` -> `window.__onLifecycleActionFinished(action, success)`
  - `save_env(payload)` -> `window.__onEnvSaved(success)`

- [ ] **Step 1: Update `Cargo.toml` dependencies**
  Ensure `crates/bqa_desktop/Cargo.toml` has `serde`, `serde_json`, `tao`, `wry`, and `crossbeam-channel` or `std::sync::mpsc` for background channel execution.

- [ ] **Step 2: Implement Non-Blocking Workspace Scanner**
  In `crates/bqa_desktop/src/main.rs`:
  - Replace blocking `scan_sessions` with an asynchronous scanner that reads `meta.json` without loading huge files.
  - Implement a reverse-tail journal reader that reads only the last 50 valid JSON lines of `journal.jsonl`.
  - Ensure zero blocking on the main Tao GUI event loop thread.

- [ ] **Step 3: Implement Bidirectional IPC Message Dispatcher**
  In `crates/bqa_desktop/src/main.rs`:
  - Handle IPC actions: `get_workspaces`, `get_workspace_journal`, `get_runtime_status`, `lifecycle_action`, `save_env`.
  - Respond back to Webview using `webview.evaluate_script` with serialized JSON payloads.

- [ ] **Step 4: Verify with `cargo check`**
  Run: `cargo check --manifest-path crates/bqa_desktop/Cargo.toml`
  Expected: PASS with 0 errors.

---

### Task 2: Failsafe Boot Sequence & Live Webview Visual Layer

**Files:**
- Modify: `crates/bqa_desktop/ui/index.html`

**Interfaces:**
- Consumes: `window.ipc.postMessage`, `window.__onWorkspacesLoaded`, `window.__onJournalLoaded`, `window.__onRuntimeStatusLoaded`.
- Produces: 3-view navigation (Runtime, Workspaces, Logs), Live session selection, 4-tab command inspector, Log category filter chips, 16 Themes, EN/VI localization.

- [ ] **Step 1: Implement Failsafe Boot Sequence**
  - Add hard 1800ms timeout that unconditionally dismisses the boot screen if still visible.
  - Add error-boundary wrapping around phase transitions so exceptions never trap the user on Phase 2 ("LOADING WORKSPACES 55%").
  - Retain `[ESC]` key handler for instant skip.

- [ ] **Step 2: Connect Live Workspace Sessions & Command Stream**
  - Connect `refreshSessionsFromDisk()` to call `sendToRust('get_workspaces')`.
  - In `window.__onWorkspacesLoaded(sessions)`, dynamically render real directories (e.g. `cw-20260911-prime-calc-local-server-069cd648`, `cw-20260908-430e4a30`) with actual operation counts and last active times.
  - When clicking a session, request `get_workspace_journal` and render the command cards (tool name, command, exit code, duration, status badge).

- [ ] **Step 3: Implement 4-Tab Command Inspector & Log Tail Viewer**
  - Update inspector tabs: `Metadata`, `STDOUT`, `STDERR`, `Raw JSON` with functional clipboard copy.
  - Connect Log Viewer to fetch from `/api/v1/logs/tail?sources=all&lines=100` with fallback to Rust IPC if offline.
  - Implement working filter chips: `All`, `Error`, `Process`, `File`, `Session`.

- [ ] **Step 4: Connect Runtime Controls & Modal Confirmation**
  - Start/Stop/Restart trigger native/in-UI confirmation modal before sending `lifecycle_action`.
  - Real-time status dot and memory/port display.

- [ ] **Step 5: Verify in Browser & Crate Build**
  Run: `cargo check --manifest-path crates/bqa_desktop/Cargo.toml`
  Expected: PASS.

---

### Task 3: CLI Wiring & Launch Integration

**Files:**
- Modify: `app/cli/main.py`
- Modify: `app/cli/parser.py`

**Interfaces:**
- Consumes: `bqa ui` command line arguments.
- Produces: Spawns `target/release/bqa-desktop` or compiles it with `cargo build --release` if missing.

- [ ] **Step 1: Align CLI Parser & Launcher**
  In `app/cli/main.py` and `app/cli/parser.py`, ensure `bqa ui` seamlessly launches the Rust Native Studio binary, properly tracks PID, and handles detached/foreground flags.

- [ ] **Step 2: Test CLI invocation**
  Run: `.venv/bin/pytest tests/test_cli_parser.py -q`
  Expected: PASS.

---

### Task 4: Full System Compilation & End-to-End Verification

**Files:**
- Verify: Entire repository build and tests.

- [ ] **Step 1: Compile Rust Native Studio Release Binary**
  Run: `cargo build --release --manifest-path crates/bqa_desktop/Cargo.toml`
  Expected: Binary generated at `target/release/bqa-desktop`.

- [ ] **Step 2: Run Python Regression Test Suites**
  Run: `.venv/bin/pytest tests/test_activity_feed.py tests/test_chat_workspace.py tests/test_cli_chats.py tests/test_rest_api.py -q`
  Expected: All PASS.

- [ ] **Step 3: Verification of Workspace Loading without Freezing**
  Simulate launch with real workspaces and verify zero GUI hangs.
