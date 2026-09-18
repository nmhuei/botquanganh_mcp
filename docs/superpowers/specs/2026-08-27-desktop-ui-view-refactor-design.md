# Desktop UI view refactor

## Status

Approved direction; awaiting final review before implementation.

## Goals

- Split the desktop control centre into `RuntimeView`, `WorkspaceLogView`, and
  `ActivityView`.
- Keep `DesktopDashboard` as the coordinator for the Tk root, scheduled
  refresh, lifecycle actions, and cross-view callbacks.
- Remove every remnant of the retired workflow-stream UI.
- Update activity sessions and records as one refresh transaction, so activity
  rendering is not invoked once from session rendering and again from the
  activity reader.
- Rebrand the user-facing desktop application as `UCS-SecretAgent` and use the
  supplied UCS logo for the window and installed launcher icon.
- Preserve the existing command line (`bqa ui`), visible tabs, splitter,
  collapse controls, workspace session behaviour, and scroll preservation.

## Non-goals

- No change to host-command policy, journal schema, REST/SSE endpoint, or CLI
  command grammar.
- The `bqa` command, Python package names, backend service identity, and MCP
  server name remain BotQuangAnh-compatible; the rebrand covers only the
  desktop application's user-facing surface.
- No new visual design, persistence of splitter positions, or floating panes.
- No change to the terminal dashboard (`app/cli/dashboard.py`).

## Target structure

`app/cli/desktop_ui.py` remains the public module. It owns graphical-session
detection, detached-launch/PID helpers, small UI-neutral formatters, and
`run_desktop_ui`. The private `DesktopDashboard` (renamed from
`_DesktopDashboard`) owns only:

- the Tk root and shared header/message state;
- the two-second refresh schedule and lifecycle worker actions;
- construction of the three views;
- callbacks that cross view boundaries, such as focusing the activity tab when
  a closed workplace receives new activity;
- shutdown ordering.

The concrete views live in `app/cli/desktop_views/`:

| Module | Responsibility | Public view operations |
| --- | --- | --- |
| `runtime.py` | Runtime facts tab and global action bar widgets. | `render_status`, `set_message`, `set_busy` |
| `workspace_logs.py` | Workspace Logs tab, chip/filter state, cached rows, SSE worker and log detail/copy actions. | `start_stream`, `render`, `close` |
| `activity.py` | WORKPLACES rail, session state, INPUT/OUTPUT selection, nested split panes, collapse controls, and scroll-safe rendering. | `refresh(sessions, records)`, `reopen_session`, `focus_activity`, `close` |

Views receive `tk`, `ttk`, their parent widget, and narrow callbacks rather
than the dashboard object. This keeps each view testable with fake widgets and
prevents a view from reaching into another view's state.

## Desktop branding

The desktop-only display name is `UCS-SecretAgent`. `desktop_ui.py` exposes a
single `DESKTOP_APP_NAME` constant used by the root title, header, toast title,
desktop-launch error/status copy, and workspace picker title. The root loads
`resources/ucs-secretagent.png` with `tk.PhotoImage`, stores the reference for
its full lifetime, and applies it with `root.iconphoto(True, image)`. A missing
or unsupported icon degrades silently through `tk.TclError`; the window still
opens.

The user-supplied 2048×2048 JPEG is resized and converted for desktop use to
`resources/ucs-secretagent.png` (512×512 PNG). The launcher template is
renamed to `resources/ucs-secretagent.desktop.in`, with `Name=UCS-SecretAgent`,
`Icon=ucs-secretagent`, and the existing `bqa ui --foreground` command. The
installer copies the PNG to
`$XDG_DATA_HOME/icons/hicolor/512x512/apps/ucs-secretagent.png` (or the
equivalent path under `~/.local/share`) and writes
`ucs-secretagent.desktop` in the applications directory. It does not remove a
previous BQA launcher automatically.

## Data flow

```text
DesktopDashboard.refresh()
  -> status_reader()                 -> RuntimeView.render_status()
  -> discover_workspace_sessions()
  -> activity_reader(100)
  -> ActivityView.refresh(sessions, records)

WorkspaceLogView SSE worker
  -> root.after(... event ...)
  -> WorkspaceLogView.render()
  -> callback(chat_id)
  -> ActivityView.reopen_session(chat_id)
  -> DesktopDashboard focuses Hoạt động ChatGPT when reopened
```

The activity view owns the closed/disabled session sets, selected session,
visible-record fingerprint, selected record fingerprint, and Treeview/Text
widgets. A single `refresh(sessions, records)` call computes both session and
activity changes, so it never calls itself indirectly through another view. It
returns chat ids found in previously unseen activity records; the dashboard
then calls `reopen_session` and focuses only when that method reports a real
closed-tab transition.

The workspace-log stream remains asynchronous. It continues to marshal every
UI update onto Tk's event loop via `root.after`; `close()` sets its stop event
before destroying the root.

## Stream retirement

Delete the retired `/api/v1/jobs` desktop-only path completely:

- `StreamRow`, stream constants and normalizers;
- `make_stream_jobs_reader` and the `RESTClient` dependency used only by it;
- stream fields and methods on the dashboard;
- `_build_stream_tab` and its stale test cases;
- the `stream_reader` injection from `run_desktop_ui` and the dashboard
  constructor.

This is intentionally a private API cleanup. `bqa ui`, its parser, launcher,
and the visible UI do not expose or use that argument.

## Test strategy

- Move pure models/formatters into focused test files alongside their view.
- Keep the existing activity scroll and splitter regression cases, but target
  `ActivityView` directly rather than the dashboard.
- Test one coordinator refresh calls activity refresh once with both snapshots.
- Test that workspace-log activity invokes the reopen callback exactly once.
- Delete tests that only exercise the removed workflow stream.
- Preserve CLI/launcher tests for `run_desktop_ui` unchanged except for the
  removed private injection parameter.
- Add a GUI smoke test when `xvfb-run` is available; otherwise retain the
  widget-adapter tests without requiring a display.

## Migration and risks

The refactor moves private implementation only. Imports used by `app.cli.main`
continue to resolve from `app.cli.desktop_ui`. Incremental commits would leave
the UI broken while views are in transit, so implementation must move each view
with its tests before deleting the old code, then run the desktop UI test group
and a syntax check.

## Acceptance criteria

- No `StreamRow`, `stream_reader`, `make_stream_jobs_reader`, or
  `_build_stream_tab` remains in the desktop UI implementation.
- `DesktopDashboard` does not own per-view Treeview/Text/cached-row state.
- One scheduled refresh calls `ActivityView.refresh` once.
- Closing/reopening/disable session, activity selection, scroll retention,
  splitter controls, workspace-log streaming, and runtime lifecycle buttons
  retain their current behaviour.
- UI-specific tests and the desktop UI syntax check pass.
- The window title, header, toast, installed launcher, and installed icon use
  `UCS-SecretAgent`; the `bqa` invocation continues to start the application.
