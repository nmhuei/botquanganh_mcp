# Desktop UI View Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the native desktop UI into Runtime, Workspace Log, and Activity views while retaining current user-visible behaviour, deleting the retired workflow stream, and rebranding the desktop surface as UCS-SecretAgent.

**Architecture:** `app.cli.desktop_ui` remains the public launcher and a thin `DesktopDashboard` coordinator. `app.cli.desktop_views` owns the widgets and local state for each tab; the dashboard supplies narrow callbacks and runs one coordinated activity refresh. The workspace-log view retains its SSE worker but delivers cross-view activity through a callback on Tk's event loop.

**Tech Stack:** Python 3.13, Tkinter/ttk, pytest, httpx SSE reader.

**Spec:** `docs/superpowers/specs/2026-08-27-desktop-ui-view-refactor-design.md`

## Global Constraints

- Preserve `bqa ui`, detached launcher/PID behaviour, Runtime, Workspace Logs, and Hoạt động ChatGPT tabs.
- Preserve WORKPLACES enable/disable/close/reopen actions, splitter/collapse controls, and activity scroll retention.
- Do not change host-command, journal, REST, SSE, or parser contracts.
- Remove the retired workflow-stream implementation, its `/api/v1/jobs` reader, and its private `stream_reader` injection completely.
- Keep `bqa`, the Python package name, and the backend/MCP identity unchanged; only the desktop display name and launcher are rebranded to `UCS-SecretAgent`.
- Derive the installed desktop icon from the supplied UCS image as `resources/ucs-secretagent.png` at 512×512.
- Tk widgets are mutated only on the Tk event loop; worker threads communicate with `root.after`.
- Use test-driven development for every behavioural change and commit only files owned by the task.

---

## File structure

| Path | Role after refactor |
| --- | --- |
| `app/cli/desktop_ui.py` | Public launcher/PID helpers, thin `DesktopDashboard`, root refresh/action/shutdown coordination. |
| `app/cli/desktop_views/__init__.py` | Explicit view-package exports. |
| `app/cli/desktop_views/runtime.py` | Runtime status presentation model and `RuntimeView`. |
| `app/cli/desktop_views/activity.py` | `WorkspaceSession`, activity formatters, `ActivityView`, session rail, input/output and splitter state. |
| `app/cli/desktop_views/workspace_logs.py` | `WorkspaceLogRow`, SSE reader/parser, filters and `WorkspaceLogView`. |
| `tests/test_desktop_runtime_view.py` | Runtime presenter/view unit tests. |
| `tests/test_desktop_activity_view.py` | Activity model, selection, scroll and splitter tests. |
| `tests/test_desktop_workspace_logs_view.py` | Workspace log normalization, SSE callback and selection tests. |
| `tests/test_cli_desktop_ui.py` | Launcher and thin-coordinator tests. |
| `docs/CLI_UI.md` | User contract for the retained splitter and three views. |
| `resources/ucs-secretagent.png` | Derived 512×512 window and launcher icon. |
| `resources/ucs-secretagent.desktop.in` | UCS-SecretAgent desktop-entry template. |
| `scripts/install_desktop_launcher.sh` | Installs the renamed launcher and icon into XDG data directories. |

### Task 1: Establish the view package and RuntimeView

**Files:**
- Create: `app/cli/desktop_views/__init__.py`
- Create: `app/cli/desktop_views/runtime.py`
- Create: `tests/test_desktop_runtime_view.py`
- Modify: `app/cli/desktop_ui.py:680-930`
- Modify: `tests/test_cli_desktop_ui.py:1-60`

**Interfaces:**
- Produces `RuntimePresentation`, `runtime_presentation(data)`, and `RuntimeView`.
- `RuntimeView.render(presentation: RuntimePresentation) -> None` updates runtime fact variables without reading lifecycle state itself.
- `RuntimeView.set_busy(busy: bool) -> None` enables/disables only the buttons it owns.

- [ ] **Step 1: Write the failing runtime-presentation test**

```python
from app.cli.desktop_views.runtime import RuntimePresentation, runtime_presentation


def test_runtime_presentation_normalizes_live_runtime_fields():
    presentation = runtime_presentation(
        {"ok": True, "bridge": "ready", "server": {"running": True}}
    )
    assert presentation.status == "Sẵn sàng"
    assert presentation.server == "running"
```

- [ ] **Step 2: Run the focused tests and verify they fail because the view module and delegation do not exist**

Run: `./.venv/bin/python -m pytest tests/test_desktop_runtime_view.py -q`

Expected: FAIL with an import error for `app.cli.desktop_views.runtime`.

- [ ] **Step 3: Implement the runtime boundary**

```python
@dataclass(frozen=True)
class RuntimePresentation:
    status: str
    color: str
    summary: str
    bridge: str
    server: str
    tunnel: str
    endpoint: str
    authentication: str


def runtime_presentation(data: dict[str, Any]) -> RuntimePresentation:
    if data.get("ok"):
        state, color, summary = "Sẵn sàng", "#147a45", "MCP bridge và Cloudflare tunnel đang hoạt động."
    elif data.get("server", {}).get("running") or data.get("tunnel", {}).get("running"):
        state, color, summary = "Cần kiểm tra", "#a16207", "Một hoặc nhiều thành phần chưa sẵn sàng."
    else:
        state, color, summary = "Đã dừng", "#64748b", "Service chưa được khởi động."
    return RuntimePresentation(
        status=state, color=color, summary=summary,
        bridge=str(data.get("bridge", "unknown")),
        server="running" if data.get("server", {}).get("running") else "stopped",
        tunnel="running" if data.get("tunnel", {}).get("running") else "stopped",
        endpoint=str(data.get("url") or data.get("last_known_url") or "chưa có"),
        authentication="enabled" if data.get("auth_required") else "disabled",
    )
```

Move Runtime tab widgets and global action controls into `RuntimeView`. Pass
dashboard callbacks (`start_service`, `restart_bridge`, `apply_workspace`,
`refresh`, `close`) into the view constructor. Replace direct status-label,
values, and action-button mutation in `DesktopDashboard.refresh` and
`_run_action` with `RuntimeView.render`, `set_message`, and `set_busy`.

- [ ] **Step 4: Run focused runtime and launcher tests**

Run: `./.venv/bin/python -m pytest tests/test_desktop_runtime_view.py tests/test_cli_desktop_ui.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the runtime extraction**

```bash
git add app/cli/desktop_views/__init__.py app/cli/desktop_views/runtime.py \
  app/cli/desktop_ui.py tests/test_desktop_runtime_view.py tests/test_cli_desktop_ui.py
git commit -m "refactor: extract desktop runtime view"
```

### Task 2: Extract ActivityView and make activity refresh atomic

**Files:**
- Create: `app/cli/desktop_views/activity.py`
- Create: `tests/test_desktop_activity_view.py`
- Modify: `app/cli/desktop_ui.py:120-460,1248-1621,1867-2012`
- Modify: `tests/test_desktop_ui_stream.py`

**Interfaces:**
- Produces `WorkspaceSession`, `discover_workspace_sessions`,
  `filter_activity_records_for_session`, `command_activity_metadata`,
  `command_activity_human_output`, and `ActivityView`.
- `ActivityView.refresh(sessions: Sequence[WorkspaceSession], records: Sequence[dict[str, Any]]) -> set[str]` updates rail and command input once, returning chat ids from previously unseen activity records without reopening them itself.
- `ActivityView.reopen_session(chat_id: str) -> bool` returns whether a closed session was reopened.
- `ActivityView.focus() -> None` selects its notebook tab and raises the root safely.

- [ ] **Step 1: Write failing ActivityView tests for one combined refresh and retained interactions**

```python
def test_activity_refresh_updates_sessions_and_records_once():
    view = make_activity_view()
    view.refresh([WorkspaceSession("chat-a", Path("/a"), 1.0)], [record("one", "chat-a")])
    assert view.session_tree.inserted == ["workspace-0"]
    assert view.activity_tree.inserted == ["one"]


def test_activity_refresh_does_not_rebuild_unchanged_input_or_output():
    view = make_activity_view()
    view.refresh([], [record("one", "chat-a")])
    view.activity_tree.clear_calls()
    view.refresh([], [record("one", "chat-a")])
    assert view.activity_tree.deleted == []


def test_reopen_session_returns_true_once_and_focus_is_explicit():
    view = make_activity_view(closed_session_ids={"chat-a"})
    assert view.reopen_session("chat-a") is True
    assert view.reopen_session("chat-a") is False
```

- [ ] **Step 2: Run the ActivityView tests and verify they fail before extraction**

Run: `./.venv/bin/python -m pytest tests/test_desktop_activity_view.py -q`

Expected: FAIL with an import error for `ActivityView`.

- [ ] **Step 3: Implement ActivityView without dashboard reach-through**

Move the activity dataclass, formatting helpers, scroll helpers, session state,
nested `ttk.Panedwindow` construction, collapse handlers, selection handlers,
and output fingerprinting to `activity.py`. Make `ActivityView` receive its
workspace root as a `Path` during refresh, not `CLIContext`. Its `refresh`
method must render the session rail first and then the filtered activity list
without calling another public render method. Return unseen-activity chat ids
to the dashboard; do not select a notebook tab from the view's refresh path.

Replace dashboard `refresh_sessions`, `render_sessions`, activity-panel
methods, and individual widget attributes with one coordinator call:

```python
sessions = discover_workspace_sessions(self.chat_workspaces_root())
records = self.activity_reader(100)
new_activity_chat_ids = self.activity_view.refresh(sessions, records)
for chat_id in new_activity_chat_ids:
    if self.activity_view.reopen_session(chat_id):
        self.activity_view.focus()
```

- [ ] **Step 4: Move existing activity regression tests and run them**

Run: `./.venv/bin/python -m pytest tests/test_desktop_activity_view.py tests/test_cli_desktop_ui.py -q`

Expected: PASS, including scroll retention, no-op refresh, collapse, splitter,
enable/disable/close, and auto-reopen cases.

- [ ] **Step 5: Commit the activity extraction**

```bash
git add app/cli/desktop_views/activity.py app/cli/desktop_ui.py \
  tests/test_desktop_activity_view.py tests/test_desktop_ui_stream.py \
  tests/test_cli_desktop_ui.py
git commit -m "refactor: extract desktop activity view"
```

### Task 3: Extract WorkspaceLogView and retain safe SSE delivery

**Files:**
- Create: `app/cli/desktop_views/workspace_logs.py`
- Create: `tests/test_desktop_workspace_logs_view.py`
- Modify: `app/cli/desktop_ui.py:350-650,730-746,934-1245,2170-2180`
- Modify: `tests/test_desktop_ui_stream.py`

**Interfaces:**
- Produces `WorkspaceLogRow`, `make_workspace_log_stream_reader`,
  `parse_sse_lines`, `filter_workspace_log_rows`, and `WorkspaceLogView`.
- `WorkspaceLogView.start_stream() -> None` starts at most one daemon worker.
- `WorkspaceLogView.close() -> None` sets its stop event and cancels further UI work.
- `WorkspaceLogView` accepts `on_new_activity: Callable[[str], None]` and calls it only for a previously unseen workspace event with a chat id.

- [ ] **Step 1: Write failing workspace-log tests against the new view**

```python
def test_workspace_log_view_reopens_a_chat_once_for_a_new_event():
    reopened = []
    view = make_workspace_log_view(on_new_activity=reopened.append)
    view.accept_event(workspace_event("evt-1", chat_id="chat-a"))
    view.accept_event(workspace_event("evt-1", chat_id="chat-a"))
    assert reopened == ["chat-a"]


def test_workspace_log_view_close_stops_future_stream_work():
    view = make_workspace_log_view()
    view.close()
    assert view.stop_event.is_set()
```

- [ ] **Step 2: Run the focused workspace-log tests and verify they fail before extraction**

Run: `./.venv/bin/python -m pytest tests/test_desktop_workspace_logs_view.py -q`

Expected: FAIL with an import error for `WorkspaceLogView`.

- [ ] **Step 3: Implement WorkspaceLogView**

Move workspace-log row state, chips, filter, Treeview rendering, detail/copy,
SSE parser and worker lifecycle into `workspace_logs.py`. Keep every callback
from the worker wrapped in `root.after(0, ...)`. The dashboard passes a callback
that calls `activity_view.reopen_session(chat_id)` and only focuses the activity
tab when it returns `True`.

```python
def _on_workspace_activity(self, chat_id: str) -> None:
    if self.activity_view.reopen_session(chat_id):
        self.activity_view.focus()
```

- [ ] **Step 4: Run workspace-log and coordinator tests**

Run: `./.venv/bin/python -m pytest tests/test_desktop_workspace_logs_view.py tests/test_cli_desktop_ui.py -q`

Expected: PASS, including stream reset, duplicate event suppression, keyboard
selection, copy text, and no direct Tk mutation from a worker.

- [ ] **Step 5: Commit the workspace-log extraction**

```bash
git add app/cli/desktop_views/workspace_logs.py app/cli/desktop_ui.py \
  tests/test_desktop_workspace_logs_view.py tests/test_desktop_ui_stream.py \
  tests/test_cli_desktop_ui.py
git commit -m "refactor: extract workspace log view"
```

### Task 4: Retire the workflow stream and finalize the thin coordinator

**Files:**
- Modify: `app/cli/desktop_ui.py:1-2230`
- Modify: `tests/test_cli_desktop_ui.py`
- Modify: `tests/test_desktop_ui_stream.py`
- Modify: `docs/CLI_UI.md:167-184`

**Interfaces:**
- Consumes the three extracted view classes.
- Produces the unchanged public `run_desktop_ui(ctx, *, initial_message, status_reader, start_action, restart_action, activity_reader, workspace_log_stream_reader) -> int`.
- Removes `StreamJobsReader` and every stream-only symbol from the desktop UI public module.

- [ ] **Step 1: Write failing tests that enforce the coordinator and stream-retirement contract**

```python
def test_desktop_ui_has_no_retired_workflow_stream_symbols():
    import app.cli.desktop_ui as desktop_ui
    assert not hasattr(desktop_ui, "StreamRow")
    assert not hasattr(desktop_ui, "make_stream_jobs_reader")


def test_one_dashboard_refresh_calls_activity_view_once(monkeypatch):
    activity = SimpleNamespace(refresh=Mock(return_value=set()))
    dashboard = make_dashboard(activity_view=activity)
    dashboard.refresh()
    activity.refresh.assert_called_once()
```

- [ ] **Step 2: Run the contract tests and verify they fail while stream code remains**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'retired_workflow or activity_view_once' -q`

Expected: FAIL because workflow-stream symbols still exist or activity refresh
is still invoked through a view render path.

- [ ] **Step 3: Remove retired stream code and simplify DesktopDashboard**

Delete the stream constants, data model, reader, state, methods, constructor
injection, and their tests. Remove the `RESTClient` import if it is no longer
needed by `desktop_ui.py`. Make `refresh()` perform exactly this ordered work:

```python
presentation = runtime_presentation(self.status_reader(self.ctx.repo_root, self.ctx.values))
self.runtime_view.render(presentation)
sessions = discover_workspace_sessions(self.chat_workspaces_root())
records = self.activity_reader(100)
new_activity_chat_ids = self.activity_view.refresh(sessions, records)
for chat_id in new_activity_chat_ids:
    if self.activity_view.reopen_session(chat_id):
        self.activity_view.focus()
```

Keep exception handling so a status failure still schedules the next refresh,
and an activity-reader failure reports through `ActivityView.show_error` without
clearing a healthy RuntimeView.

- [ ] **Step 4: Update the UI contract and run the complete desktop test group**

Update `docs/CLI_UI.md` to state that WORKPLACES/content and INPUT/OUTPUT have
drag splitters as well as collapse controls. Remove references to the retired
workflow stream. Run:

`./.venv/bin/python -m py_compile app/cli/desktop_ui.py app/cli/desktop_views/runtime.py app/cli/desktop_views/activity.py app/cli/desktop_views/workspace_logs.py`

Then run:

`./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the coordinator cleanup and documentation**

```bash
git add app/cli/desktop_ui.py docs/CLI_UI.md tests/test_cli_desktop_ui.py \
  tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py \
  tests/test_desktop_workspace_logs_view.py
git commit -m "refactor: split desktop UI into views"
```

### Task 5: Rebrand the desktop surface and install the UCS icon

**Files:**
- Create: `resources/ucs-secretagent.png`
- Create: `resources/ucs-secretagent.desktop.in`
- Modify: `app/cli/desktop_ui.py:1-2230`
- Modify: `scripts/install_desktop_launcher.sh`
- Modify: `docs/CLI_UI.md:160-184`
- Modify: `tests/test_cli_desktop_ui.py`
- Delete: `resources/bqa-control-center.desktop.in`

**Interfaces:**
- Produces `DESKTOP_APP_NAME = "UCS-SecretAgent"` and `apply_desktop_icon(root, tk) -> None` in `app.cli.desktop_ui`.
- Produces a launcher with `Name=UCS-SecretAgent`, `Icon=ucs-secretagent`, and `Exec="@BQA_BIN@" ui --foreground`.
- The launcher installer writes `$XDG_DATA_HOME/applications/ucs-secretagent.desktop` and `$XDG_DATA_HOME/icons/hicolor/512x512/apps/ucs-secretagent.png`.

- [ ] **Step 1: Write failing branding and launcher tests**

```python
def test_desktop_branding_uses_ucs_secret_agent_name():
    from app.cli.desktop_ui import DESKTOP_APP_NAME
    assert DESKTOP_APP_NAME == "UCS-SecretAgent"


def test_desktop_launcher_installs_ucs_name_and_icon(tmp_path):
    from pathlib import Path
    import subprocess

    repo_root = Path(__file__).resolve().parents[1]
    fake_bqa = tmp_path / "bqa"
    fake_bqa.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bqa.chmod(0o755)
    data_home = tmp_path / "data"
    completed = subprocess.run(
        ["bash", "scripts/install_desktop_launcher.sh"],
        cwd=repo_root,
        env={**os.environ, "BQA_BIN": str(fake_bqa), "XDG_DATA_HOME": str(data_home)},
        check=True,
        capture_output=True,
        text=True,
    )
    desktop_entry = (data_home / "applications" / "ucs-secretagent.desktop").read_text()
    assert "Name=UCS-SecretAgent" in desktop_entry
    assert (data_home / "icons/hicolor/512x512/apps/ucs-secretagent.png").is_file()
    assert completed.returncode == 0
```

- [ ] **Step 2: Run the branding tests and verify they fail before the asset and launcher change exist**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'branding or launcher_installs_ucs' -q`

Expected: FAIL because the UCS constant, template, target launcher, and icon installation do not exist.

- [ ] **Step 3: Create the icon asset and implement rebranding**

Derive the PNG from the user-provided image with ImageMagick:

```bash
convert /home/undertaker/Downloads/app_logo.jpg -resize 512x512 resources/ucs-secretagent.png
```

Add `DESKTOP_APP_NAME` and an icon helper that retains the `PhotoImage` object
on the dashboard instance:

```python
DESKTOP_APP_NAME = "UCS-SecretAgent"
DESKTOP_ICON_PATH = Path(__file__).resolve().parents[2] / "resources" / "ucs-secretagent.png"


def load_desktop_icon(root: Any, tk: Any) -> Any | None:
    try:
        image = tk.PhotoImage(file=DESKTOP_ICON_PATH)
        root.iconphoto(True, image)
        return image
    except tk.TclError:
        return None
```

Set `self.app_icon = load_desktop_icon(self.root, self.tk)` during dashboard
construction. Replace every desktop-facing `BQA Control Center` title/header,
toast title, workspace chooser title, launcher error, and launcher status copy
with `DESKTOP_APP_NAME`; retain BotQuangAnh wording where it identifies the MCP
service rather than the desktop app.

Rename the desktop template and update the installer to copy the icon before
atomically moving the desktop entry:

```bash
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"
mkdir -p "$APPLICATIONS_DIR" "$ICON_DIR"
install -m 644 "$ROOT_DIR/resources/ucs-secretagent.png" "$ICON_DIR/ucs-secretagent.png"
TARGET="$APPLICATIONS_DIR/ucs-secretagent.desktop"
```

- [ ] **Step 4: Run branding tests and the desktop syntax check**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'branding or launcher_installs_ucs' -q`

Run: `./.venv/bin/python -m py_compile app/cli/desktop_ui.py`

Expected: PASS.

- [ ] **Step 5: Commit the UCS-SecretAgent branding**

```bash
git add app/cli/desktop_ui.py resources/ucs-secretagent.png \
  resources/ucs-secretagent.desktop.in scripts/install_desktop_launcher.sh \
  docs/CLI_UI.md tests/test_cli_desktop_ui.py
git rm resources/bqa-control-center.desktop.in
git commit -m "feat: brand desktop UI as UCS-SecretAgent"
```

### Task 6: Verify the final user-visible contract

**Files:**
- Modify: `tests/test_cli_desktop_ui.py`
- Modify: `tests/test_desktop_activity_view.py`
- Modify: `tests/test_desktop_workspace_logs_view.py`

**Interfaces:**
- Consumes the finished coordinator and the three view public APIs.
- Produces a verified desktop UI refactor with no behaviour outside the stated scope changed.

- [ ] **Step 1: Write a failing cross-view callback regression test**

```python
def test_new_workspace_log_reopens_then_focuses_activity_once():
    class FakeActivityView:
        def __init__(self):
            self.reopened = []
            self.focus_count = 0
            self.closed = {"chat-a"}

        def reopen_session(self, chat_id):
            self.reopened.append(chat_id)
            if chat_id not in self.closed:
                return False
            self.closed.remove(chat_id)
            return True

        def focus(self):
            self.focus_count += 1

    activity = FakeActivityView()
    dashboard = make_dashboard(activity_view=activity)
    dashboard._on_workspace_activity("chat-a")
    assert activity.reopened == ["chat-a"]
    assert activity.focus_count == 1
```

- [ ] **Step 2: Run the regression test and verify it fails if callback ordering is wrong**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'reopens_then_focuses' -q`

Expected: FAIL until the dashboard callback checks the boolean result from
`ActivityView.reopen_session` before calling `ActivityView.focus`.

- [ ] **Step 3: Implement the minimal callback ordering fix and optional GUI smoke test**

Keep `_on_workspace_activity` as the sole cross-view path. When `xvfb-run` is
available, add this non-interactive smoke command to CI/local verification:

```bash
xvfb-run -a ./.venv/bin/python -c \
  "import tkinter as tk; from tkinter import ttk; root=tk.Tk(); panes=ttk.Panedwindow(root, orient='vertical'); panes.pack(fill='both', expand=True); root.update_idletasks(); root.destroy()"
```

- [ ] **Step 4: Run final verification**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py -q`

Run: `git diff --check`

Expected: all listed tests pass and diff check has no output.

- [ ] **Step 5: Commit the final regression coverage**

```bash
git add tests/test_cli_desktop_ui.py tests/test_desktop_activity_view.py \
  tests/test_desktop_workspace_logs_view.py
git commit -m "test: cover desktop UI view coordination"
```
