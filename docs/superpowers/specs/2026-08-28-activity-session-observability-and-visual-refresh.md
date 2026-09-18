# Activity session observability and visual refresh

## Status

Proposed after root-cause reproduction; approved in chat for implementation.
This specification extends the desktop view-refactor design dated 2026-08-27.
Where the two documents differ, this document takes precedence for the GPT
activity workspace rail and command activity journal.

## Problem and evidence

The `Hoạt động ChatGPT` tab does not list real chat-workspace folders in the
current runtime. `DesktopDashboard.chat_workspaces_root()` reads the undefined
CLI key `BQA_CHAT_WORKSPACES_DIR`; it therefore falls back to
`repo_root / "bqa-chat-workspaces"`. In the configured runtime that directory
does not exist. The actual workspace root is supplied as `HOST_CHAT_ROOT` and
contains the active chat folders.

The MCP command path does receive the chat identifier: it starts a workspace
journal entry and writes the same `chat_id` into `mcp_command_activity.jsonl`.
However, the activity journal gets its only record after `Popen.wait()` ends.
Consequently a long-running command has no visible activity-row state while it
is running.

## Goals

- Make the desktop session rail discover the same root as the MCP host tools:
  `HOST_CHAT_ROOT` from `CLIContext.values`.
- Show a command as running promptly after policy and working-directory
  validation succeed, then show one final outcome for that same command.
- Keep the append-only JSONL activity log bounded and backward-compatible for
  existing completed records.
- Keep the rail/table/inspector workflow, while giving it a denser modern
  operations-console treatment inspired by Burp-UI's management layout rather
  than copying its web implementation.
- Preserve keyboard controls, resize/collapse interactions, output redaction,
  scroll retention, the MCP interface, and existing workspace-journal/SSE
  contracts.

## Non-goals

- No web frontend, new UI toolkit, or change to the `bqa` command.
- No change to command policy, workspace authorization, server API, or
  sensitive-data redaction rules.
- No stored UI preferences or migration of historical JSONL records.
- No automatic focus steal for a session that the operator has not closed.

## Design

### One workspace-root source of truth

`DesktopDashboard.chat_workspaces_root()` will read
`ctx.values["HOST_CHAT_ROOT"]`, expand `~`, and return that path. Its fallback
will be the CLI configuration default for `HOST_CHAT_ROOT`, not a private
repo-relative directory. The session rail continues to list only direct,
non-archived child directories.

An unavailable root remains an empty rail and is reported in the existing
notice line; it must not silently inspect a second location. This makes a
misconfigured root diagnosable and prevents the UI from diverging from MCP.

### Command activity spans

The activity log gains optional span fields:

```json
{
  "operation_id": "act-…",
  "phase": "started | completed",
  "status": "running | succeeded | failed | timed_out"
}
```

For a new MCP command, `execute_host_command()` creates one `operation_id`.
After command policy and CWD validation, immediately before spawning the
process, it appends a redacted `started/running` record containing the supplied
`chat_id`. It appends a second terminal record with the same ID after process
completion. Rejection before process spawn retains the current terminal error
record and never falsely claims the command was running.

The change is limited to activity observation. The existing workspace journal
still owns its `op_started`/`op_result` pair and remains independent for crash
recovery.

### Activity projection

`ActivityView` normalizes raw JSONL records into display rows before filtering,
sorting, fingerprinting, or rendering:

- A `started` record creates one row marked `Đang chạy`.
- Its terminal sibling replaces that row's status/output, retaining selection
  and scroll position when possible.
- Legacy records with no `operation_id` remain individual completed rows.
- An orphaned `started` row remains visible as running; this accurately shows a
  process whose terminal event was not yet observed. A later terminal record
  joins it by `operation_id`.

The session rail renders a compact live marker when its filtered projected rows
include a running command. A newly received command only reopens and focuses a
tab when that tab was explicitly closed, matching current operator intent.

### Visual refresh plan

The native Tk structure stays `WORKPLACES → INPUT → OUTPUT`; visual work is
isolated to `desktop_views/theme.py` plus small style/tag changes owned by the
Activity view.

| Element | Planned treatment |
| --- | --- |
| Shell | Dark graphite background and slightly lifted panels; a single cool-blue accent defines selection and focus. |
| Typography | Strong title/body contrast, calmer secondary text, compact monospace-like command/output treatment when the platform font supports it. |
| Navigation | Slim notebook tabs and a clear selected state; no decorative gradients or animation. |
| Session rail | Short session IDs, muted timestamp, status chip, and a small teal live indicator only for a running command. |
| Command table | Denser rows, fixed semantic status column, readable selected-row contrast, and red/amber reserved for terminal failure/timeout. |
| Inspector | Subtle inset boundary and grouped metadata/output tabs so command input and process output remain immediately distinguishable. |
| Accessibility | Existing keyboard shortcuts, visible focus rings, readable contrast, and semantic labels are preserved; state never relies on color alone. |

The visual direction borrows the useful operational hierarchy of the referenced
Burp-UI (navigation, dense status tables, and details-on-selection), not its
Bootstrap/Slate assets or source code.

## Error handling and compatibility

- A failure to append activity must never interrupt a host command, as today.
- If the initial activity write fails but the terminal write succeeds, the
  terminal event still renders as a completed command.
- Malformed/unknown `phase`, `status`, or `operation_id` fields are treated as
  a legacy standalone record rather than causing a view failure.
- The UI never displays raw credentials; all new lifecycle records use the
  same existing redaction and byte limits as completed activity records.

## Test and verification plan

1. Add a regression test proving the dashboard resolves `HOST_CHAT_ROOT` from
   a `CLIContext`, not the retired key or repository fallback.
2. Add executor/activity tests for the ordered `running` and terminal span
   records, shared operation ID, supplied chat ID, validation failure, timeout,
   and existing secret redaction.
3. Add pure ActivityView projection tests for running, terminal merge, legacy
   records, orphaned starts, filtering, live session status, selection, and
   no-op refresh behavior.
4. Run the desktop/activity focused suites, then the full project test suite.
5. Start the desktop UI against the local MCP runtime and manually verify a
   long harmless command: its configured chat folder appears, gets a live
   marker while executing, transitions once to a final state, and shows no
   Tk/console errors.

## Acceptance criteria

- The configured real chat workspace directory is the only directory used by
  the session rail.
- A long-running attributed MCP command appears under the correct session
  before it finishes, then has exactly one projected activity row afterward.
- Existing completed activity history still renders and remains redacted.
- A process rejection does not display a false running state.
- UI controls, filter/sort, scroll retention, closed-tab reopening, and SSE
  thread handoff retain their documented behavior.
- Focused and full tests pass; manual desktop verification records a clean
  command lifecycle and no visual regressions.
