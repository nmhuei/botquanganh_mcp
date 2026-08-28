# Activity Session Observability and Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop GPT activity tab discover the configured chat root, display an attributed MCP command while it is running, and refresh the native operations-console visual hierarchy.

**Architecture:** The desktop coordinator resolves `HOST_CHAT_ROOT` from the existing CLI context. The append-only MCP activity log receives paired `started` and terminal records sharing an `operation_id`; a pure projector in `ActivityView` coalesces those records into one display row and derives the session rail's live state. Theme-only presentation changes keep the three-pane Tk structure and existing callbacks intact.

**Tech Stack:** Python 3.10+, Tkinter/ttk, pytest 9, existing JSONL activity journal.

**Spec:** `docs/superpowers/specs/2026-08-28-activity-session-observability-and-visual-refresh.md`

## Global Constraints

- Use `HOST_CHAT_ROOT` as the sole desktop session-root configuration; do not introduce `BQA_CHAT_WORKSPACES_DIR`.
- Do not change MCP tool parameters, workspace authorization, REST/SSE contracts, command policy, redaction, or the `bqa` command.
- The activity journal remains append-only, bounded, mode `0600`, and safe to fail without interrupting a command.
- A command is only recorded as `running` after command policy and CWD validation and immediately before process spawn.
- Preserve compatibility with activity records that lack the new lifecycle fields.
- Keep Tk updates on the Tk event loop; preserve selection, scroll, filters, sorting, collapsed panes, and closed-tab behavior.
- Restrict visual changes to native Tk theme/style and ActivityView presentation; do not add a web toolkit, animations, or persistent UI settings.
- Use `.venv/bin/python -m pytest`; do not add lint/format tooling.

---

## File Structure

| File | Responsibility after implementation |
| --- | --- |
| `app/cli/desktop_ui.py` | Resolves the configured chat root for the desktop coordinator. |
| `app/activity_log.py` | Encodes optional lifecycle span fields on redacted, bounded activity records. |
| `app/host/executor.py` | Emits one activity start callback just before spawn and one terminal activity record per MCP command. |
| `app/cli/desktop_views/activity.py` | Projects raw lifecycle records into one command row, derives live session IDs, and renders semantic row/session states. |
| `app/cli/desktop_views/theme.py` | Defines the graphite operations-console palette and ttk styles/tags used by the desktop views. |
| `tests/test_cli_desktop_ui.py` | Covers the desktop root-resolution regression. |
| `tests/test_mcp_command_activity.py` | Covers journal lifecycle fields and executor ordering/error boundaries. |
| `tests/test_desktop_activity_view.py` | Covers pure lifecycle projection, live rail state, legacy compatibility, and retained view behavior. |
| `docs/CLI_UI.md` | Documents the visible running-state and visual/interaction contract. |

### Task 1: Resolve the actual configured session root

**Files:**
- Modify: `app/cli/desktop_ui.py:328-330`
- Test: `tests/test_cli_desktop_ui.py`

**Interfaces:**
- Consumes: `CLIContext.values["HOST_CHAT_ROOT"]` loaded by `app.cli.config_view.load_env`.
- Produces: `_DesktopDashboard.chat_workspaces_root() -> Path`, pointing only to the configured root (with `Path.expanduser()`).

- [ ] **Step 1: Write the failing root-resolution regression test**

```python
def test_desktop_activity_root_uses_host_chat_root(tmp_path):
    configured = tmp_path / "real-chat-workspaces"
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.ctx = type(
        "Context",
        (),
        {
            "repo_root": tmp_path / "repo",
            "values": {
                "HOST_CHAT_ROOT": str(configured),
                "BQA_CHAT_WORKSPACES_DIR": str(tmp_path / "wrong-root"),
            },
        },
    )()

    assert dashboard.chat_workspaces_root() == configured
```

- [ ] **Step 2: Run the focused test to verify the current key mismatch fails**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py::test_desktop_activity_root_uses_host_chat_root -q`

Expected: FAIL because the dashboard returns `wrong-root` or the old repo-relative fallback.

- [ ] **Step 3: Implement the single-source resolver**

Replace the old method with:

```python
def chat_workspaces_root(self) -> Path:
    configured = self.ctx.values.get("HOST_CHAT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Downloads" / "bqa-workspaces"
```

Do not test for or read `BQA_CHAT_WORKSPACES_DIR`.

- [ ] **Step 4: Run root and existing activity-desktop tests**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py tests/test_desktop_activity_view.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the focused regression fix**

```bash
git add app/cli/desktop_ui.py tests/test_cli_desktop_ui.py
git commit -m "fix: use configured chat workspace root in desktop UI"
```

### Task 2: Persist observable command lifecycle spans

**Files:**
- Modify: `app/activity_log.py:40-95`
- Modify: `app/host/executor.py:165-314`
- Test: `tests/test_mcp_command_activity.py`

**Interfaces:**
- Consumes: the existing `activity_source="mcp"`, optional `activity_chat_id`, validated CWD, and executor result mapping.
- Produces: `record_mcp_command_activity(..., operation_id: str | None = None, phase: str | None = None, status: str | None = None) -> None` and `_execute_host_command_impl(..., on_started: Callable[[str], None] | None = None)`.

- [ ] **Step 1: Write failing journal and executor tests**

Add a journal assertion:

```python
def test_activity_record_keeps_optional_lifecycle_span_fields(tmp_path, monkeypatch):
    journal = tmp_path / "mcp_command_activity.jsonl"
    monkeypatch.setattr(activity, "MCP_COMMAND_ACTIVITY_LOG", journal)

    activity.record_mcp_command_activity(
        command="sleep 1", cwd="/workspace", chat_id="chat-alpha",
        operation_id="act-1", phase="started", status="running", result={"ok": True},
    )

    record = activity.read_mcp_command_activity()[0]
    assert record["operation_id"] == "act-1"
    assert record["phase"] == "started"
    assert record["status"] == "running"
```

Add an executor-boundary test that replaces `_execute_host_command_impl` with a
fake that calls its supplied `on_started("/workspace")` before returning a
success result. Assert two captured records, ordered `started/running` then
`completed/succeeded`, with identical non-empty `operation_id` and
`chat_id="chat-alpha"`.

- [ ] **Step 2: Run the new lifecycle tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_mcp_command_activity.py -k 'lifecycle_span or executor_lifecycle' -q`

Expected: FAIL because the journal and executor do not accept or emit lifecycle fields.

- [ ] **Step 3: Extend the activity journal without weakening its safety limits**

Extend `record_mcp_command_activity` to add only non-empty optional span fields
to the existing record:

```python
for key, value in {
    "operation_id": operation_id,
    "phase": phase,
    "status": status,
}.items():
    if value:
        record[key] = str(value)
```

Keep existing redaction, size cap, lock, rotation, and `OSError` swallowing
unchanged.

- [ ] **Step 4: Emit the start event at the precise executor boundary**

Add `on_started` to `_execute_host_command_impl`. Call it after
`require_host_command_allowed()` and `resolve_host_path()` succeed, and just
before `subprocess.Popen`. In `execute_host_command`, when `activity_source ==
"mcp"`, generate `operation_id = "act-" + uuid.uuid4().hex`, pass a callback
that writes `phase="started", status="running"`, and write a terminal record
with `phase="completed"` and status selected by this exact mapping:

```python
if result.get("timed_out"):
    terminal_status = "timed_out"
elif result.get("ok"):
    terminal_status = "succeeded"
else:
    terminal_status = "failed"
```

If validation throws before the callback, retain the terminal failure record
but omit `phase="started"`; if a post-start exception occurs, reuse the same
operation ID and write `completed/failed`.

- [ ] **Step 5: Run lifecycle and existing activity tests**

Run: `./.venv/bin/python -m pytest tests/test_mcp_command_activity.py tests/test_host_tools.py -q`

Expected: PASS, including redaction, rejected-command behavior, and lifecycle ordering.

- [ ] **Step 6: Commit lifecycle observation**

```bash
git add app/activity_log.py app/host/executor.py tests/test_mcp_command_activity.py
git commit -m "feat: track MCP command activity lifecycle"
```

### Task 3: Project lifecycle records into one live activity row

**Files:**
- Modify: `app/cli/desktop_views/activity.py:66-190,259-380,500-690`
- Test: `tests/test_desktop_activity_view.py`

**Interfaces:**
- Consumes: newest-first raw JSONL mappings returned by `read_mcp_command_activity`.
- Produces: `project_command_activity_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]`, with `activity_status` (`running`, `succeeded`, `failed`, `timed_out`) and `is_running` fields; `ActivityView.running_session_ids: set[str]`.

- [ ] **Step 1: Write failing pure projection tests**

```python
def test_activity_projection_merges_a_running_span_into_one_terminal_row():
    started = {
        "event_id": "start", "timestamp": "2026-08-28T00:00:00+00:00",
        "operation_id": "act-1", "phase": "started", "status": "running",
        "chat_id": "chat-a", "command": "sleep 30",
    }
    completed = {
        **started, "event_id": "done", "timestamp": "2026-08-28T00:00:30+00:00",
        "phase": "completed", "status": "succeeded", "ok": True, "stdout": "done",
    }

    assert project_command_activity_records([completed, started]) == [
        {**completed, "activity_status": "succeeded", "is_running": False}
    ]


def test_activity_projection_keeps_orphan_start_live_and_legacy_rows_unchanged():
    running = {"event_id": "start", "operation_id": "act-2", "phase": "started", "status": "running", "chat_id": "chat-a"}
    legacy = {"event_id": "old", "chat_id": "chat-b", "command": "pwd", "ok": True}

    rows = project_command_activity_records([running, legacy])
    assert rows[0]["is_running"] is True
    assert rows[0]["activity_status"] == "running"
    assert rows[1] == {**legacy, "activity_status": "succeeded", "is_running": False}
```

Also add a headless `ActivityView.refresh` test asserting a projected running
record puts `"chat-a"` in `running_session_ids` and terminal refresh removes
it without creating a second row.

- [ ] **Step 2: Run the projection tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_desktop_activity_view.py -k 'projection or running_session' -q`

Expected: FAIL because the projector and live-session state do not exist.

- [ ] **Step 3: Implement an explicit backwards-compatible projector**

Implement `project_command_activity_records` as a pure function. Process input
from oldest to newest so a terminal record updates the slot created by its
start record, then return rows newest first. A lifecycle record is valid only
when its non-empty `operation_id`, `phase`, and `status` belong to:

```python
VALID_PHASES = {"started", "completed"}
VALID_STATUSES = {"running", "succeeded", "failed", "timed_out"}
```

Treat all invalid/unknown lifecycle combinations as independent legacy rows.
For a valid completion with no known start, create one terminal row rather than
dropping it. For legacy rows, derive `timed_out` when `record["timed_out"]` is
true, `succeeded` when `record["ok"]` is true, otherwise `failed`. Add
`activity_status` and `is_running` to every projected row.

- [ ] **Step 4: Integrate projection before view state and rendering**

At the start of `ActivityView.refresh`, replace `self.records = list(records)`
with the projector result, calculate `self.running_session_ids` from projected
rows where `is_running` is true, then continue existing filtering, fingerprint,
selection, and unseen-event logic. Make the rail render `ĐANG CHẠY` for a
session in that set and `BẬT` otherwise. Add `Status: …` to metadata and the
human-readable inspector output; retain all pre-existing fields and output.

- [ ] **Step 5: Run all ActivityView behavior tests**

Run: `./.venv/bin/python -m pytest tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py tests/test_cli_desktop_ui.py -q`

Expected: PASS, including filtering, no-op rendering, selection, scroll,
splitter/collapse, closed-tab reopening, and workspace-log callback behavior.

- [ ] **Step 6: Commit the activity projection**

```bash
git add app/cli/desktop_views/activity.py tests/test_desktop_activity_view.py
git commit -m "feat: show live MCP command activity by session"
```

### Task 4: Apply the restrained operations-console visual refresh

**Files:**
- Modify: `app/cli/desktop_views/theme.py`
- Modify: `app/cli/desktop_views/activity.py`
- Test: `tests/test_desktop_theme.py`
- Test: `tests/test_desktop_activity_view.py`

**Interfaces:**
- Consumes: `PALETTE`, ttk style names, projected `activity_status`, and
  `ActivityView.running_session_ids`.
- Produces: stable dark-theme palette keys, semantic Treeview tags for
  `running`, `failed`, and `timed_out`, and state text that never depends on
  color alone.

- [ ] **Step 1: Write failing visual-contract tests**

```python
def test_operations_console_palette_has_contrastful_dark_surfaces():
    assert PALETTE["app_background"] == "#10151d"
    assert PALETTE["surface"] == "#18212c"
    assert PALETTE["accent"] == "#60a5fa"
    assert PALETTE["running"] == "#2dd4bf"


def test_activity_status_text_is_semantic_without_color():
    assert activity_status_label("running") == "ĐANG CHẠY"
    assert activity_status_label("timed_out") == "HẾT THỜI GIAN"
    assert activity_status_label("failed") == "LỖI"
```

- [ ] **Step 2: Run the visual-contract tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_desktop_theme.py tests/test_desktop_activity_view.py -k 'operations_console or status_text' -q`

Expected: FAIL because the graphite palette and semantic label helper do not yet exist.

- [ ] **Step 3: Update only native style tokens and semantic tags**

Set the palette to these fixed core values:

```python
PALETTE.update({
    "app_background": "#10151d", "surface": "#18212c",
    "surface_muted": "#223044", "border": "#334155",
    "text": "#e5edf7", "text_muted": "#b6c4d6",
    "text_subtle": "#8ea1b8", "accent": "#60a5fa",
    "success": "#4ade80", "warning": "#fbbf24",
    "danger": "#fb7185", "running": "#2dd4bf",
})
```

Retain existing style names so Runtime and Workspace Logs inherit the palette.
Configure Treeview selection/focus contrast and explicit row tags in
`ActivityView` for `running`, `failed`, and `timed_out`; render the semantic
status string in the existing session/table state text. Keep disabled/closed,
sort/filter, keyboard handling, pane geometry, and inspector content behavior
unchanged.

- [ ] **Step 4: Run theme and desktop view tests**

Run: `./.venv/bin/python -m pytest tests/test_desktop_theme.py tests/test_desktop_activity_view.py tests/test_desktop_runtime_view.py tests/test_desktop_workspace_logs_view.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the visual refresh**

```bash
git add app/cli/desktop_views/theme.py app/cli/desktop_views/activity.py \
  tests/test_desktop_theme.py tests/test_desktop_activity_view.py
git commit -m "style: modernize desktop activity console"
```

### Task 5: Document and verify the complete operator flow

**Files:**
- Modify: `docs/CLI_UI.md:167-220`
- Test: `tests/test_cli_desktop_ui.py`
- Test: `tests/test_mcp_command_activity.py`
- Test: `tests/test_desktop_activity_view.py`

**Interfaces:**
- Consumes: completed Tasks 1-4 and existing `bqa ui` launch contract.
- Produces: an accurate documented activity-session lifecycle and verified
  end-to-end native desktop behavior.

- [ ] **Step 1: Write the documentation acceptance assertions**

Add a lightweight documentation test or existing CLI contract assertion that
reads `docs/CLI_UI.md` and requires these user-visible phrases:

```python
repo_root = Path(__file__).resolve().parents[1]
contract = (repo_root / "docs" / "CLI_UI.md").read_text(encoding="utf-8")
assert "HOST_CHAT_ROOT" in contract
assert "ĐANG CHẠY" in contract
assert "operation ID" in contract
```

- [ ] **Step 2: Run the new contract test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k activity_contract -q`

Expected: FAIL until the visual and lifecycle contract is documented.

- [ ] **Step 3: Update the GPT activity section of `docs/CLI_UI.md`**

State that the rail uses `HOST_CHAT_ROOT` exactly, an attributed command appears
as `ĐANG CHẠY` after validation and before execution completes, and its final
record replaces that live row using one operation ID. Document the graphite
operations-console treatment as presentation only, and explicitly preserve the
existing keyboard/splitter/collapse controls.

- [ ] **Step 4: Run focused and complete automated verification**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_cli_desktop_ui.py \
  tests/test_mcp_command_activity.py \
  tests/test_desktop_activity_view.py \
  tests/test_desktop_runtime_view.py \
  tests/test_desktop_workspace_logs_view.py \
  tests/test_desktop_theme.py -q
./.venv/bin/python -m pytest -q
```

Expected: both commands PASS.

- [ ] **Step 5: Perform manual desktop lifecycle verification**

Start the local runtime and open the native window using `bqa ui --inline`.
From an attributed chat workspace, run a harmless command that lasts at least
five seconds. Verify in `Hoạt động ChatGPT` that the configured session folder
appears under `WORKPLACES`, displays `ĐANG CHẠY` while the command executes,
then presents a single final row with stdout/stderr in the inspector. Confirm
that filter/sort, `/`, `Esc`, arrow keys, `Ctrl+C`, collapse controls, and
splitters still work; inspect `logs/desktop-ui.log` for no Tk traceback.

- [ ] **Step 6: Commit documentation and verification-facing tests**

```bash
git add docs/CLI_UI.md tests/test_cli_desktop_ui.py
git commit -m "docs: describe live desktop command tracking"
```

## Plan self-review

- **Spec coverage:** Task 1 implements the root cause; Task 2 implements
  lifecycle persistence and error boundaries; Task 3 implements coalescing,
  live rail state, compatibility, and retained interaction behavior; Task 4
  implements every visual/accessibility requirement; Task 5 documents and
  verifies the full user flow.
- **Placeholder scan:** No TODO/TBD/future-work placeholders remain. Every
  code-bearing task includes a concrete test, failing command, implementation
  boundary, and passing command.
- **Type consistency:** The journal field is `operation_id`; the execution
  callback is `on_started`; the projector is
  `project_command_activity_records`; all later tasks use those exact names.
