# BQA CLI UI Contract

BQA follows the terminal progress grammar used by `uv pip install`. This is a
visual/interaction contract, not a loose inspiration.

## Streams

- Primary data and copyable artifacts stay on stdout.
- Transient progress, completion summaries, warnings, and errors stay on stderr.
- `--json` and `--quiet` never emit progress.

## uv progress grammar

The primary long-running form mirrors uv's `PrepareReporter`:

```text
⠹ Establishing Quick Tunnel... (1/4) · 3.1s
tunnel   ------------------------------   0/1
bridge   ------------------------------   0/1
endpoint ------------------------------   0/1
```

Rules:

- Spinner sequence: `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`.
- Spinner tick: 200 ms.
- Root template: `spinner + message + (pos/len)`.
- Once 2 seconds have elapsed, the root line gains a dim ` · Ns` suffix; shorter commands render exactly as before.
- Active child rows are rendered underneath the root line.
- Child names align to the longest active name.
- Numeric child rows use a 30-character `-` bar, matching uv's request rows.
- Completed child rows disappear from the live region (`finish_and_clear` behavior).
- Lifecycle progress is milestone-driven: each row (`server`/`tunnel`/`bridge`/`endpoint` on start and restart; `supervisor`/`tunnel`/`server` on stop) ticks complete only when its real condition turns true, polled every ~150 ms — rows never complete as one batch.
- On `start`/`restart` the root message narrates stages as rows complete: `Starting MCP server...` -> `Establishing Quick Tunnel...` -> `Warming bridge...` -> `Publishing connector URL...`; `stop` keeps a single working message.
- Rendering is diff-based: a tick rewrites only lines whose text changed (an unchanged line receives zero writes); structural changes fall back to a full erase + redraw.
- Unknown-size rows use uv's literal four-dot form:

```text
workspace ....
```

- When byte totals are meaningful, use uv's binary-byte row shape:

```text
torch ------------------------------  1.43 MiB/502.22 MiB
```

Do not use `█`, `░`, percentages, boxed progress, or a BQA-specific progress
visual for lifecycle/doctor operations.

## Single opaque operations

Operations without meaningful child work use uv's spinner-only form:

```text
⠹ Searching files...
```

Examples include a single REST request, file mutation, command policy check, or
knowledge query.

## Completion

Live progress is cleared before the persistent result. `finish()` draws no
final frame: the transient block is erased and exactly one summary line is
printed. Summaries use the same compact `verb ... in TIME` shape:

```text
Started runtime in 184ms
```

The primary artifact follows separately on stdout when applicable:

```text
https://example.trycloudflare.com/mcp
```

Filesystem/result changes use uv-style change markers (`+`, `-`, or `~` when an
existing object is updated) rather than a success panel.

## Copy-safe values

A connector URL or absolute path value is presented as one contiguous string
somewhere in the output, at any terminal width: never ellipsized, never split
mid-token. The terminal may soft-wrap the line visually, but selection and
redirected output keep one logical string.

- `Renderer.facts` accepts `no_wrap` protected labels; `bqa status` protects
  `Endpoint`, so when its value cannot fit beside the label the value moves
  to its own line instead of wrapping.
- `bqa doctor` lifts check messages that embed a URL (and any message too
  long for the inline value budget at narrow widths) out of the truncating
  checks grid and emits each through `Renderer.copyable_value` on its own
  line.

## Progress suppression

Live progress is suppressed for:

- `--json`
- `--quiet`
- `--no-progress`
- `BQA_NO_PROGRESS=1|true|yes|on`
- non-TTY stderr
- `TERM=dumb`
- `--verbose` (matching uv's behavior of hiding progress to avoid interleaving
  with debug output)
- Animation follows the same suppression matrix as color: pipe | `NO_COLOR` |
  `TERM=dumb` => no animation, no escape bytes (not an uncolored spinner).

`--no-progress` suppresses the transient region but keeps the normal persistent
completion/result output.

## Errors

Any live progress region is cleared before the error tree is printed:

```text
  × Could not complete `start`
  ╰─▶ Connector URL is unavailable.
      hint: bqa doctor
```

The hint line is not a fixed `bqa doctor`: hints are chosen from the exit
code (`_error_hint`):

| Exit | Class | Hint |
| --- | --- | --- |
| 2 | usage | `bqa <operation> --help` (`bqa --help` when no subcommand applies) |
| 4, 5 | auth / policy | `bqa cmd check '<command>'` |
| 6 | not found | re-run `bqa <operation>` with a corrected path |
| 3, 7 | connection / timeout | `bqa doctor`, or `bqa doctor --local-only` for `status`/`health`/`server`/`doctor` |
| other | fallback | `bqa doctor`, or `bqa doctor --local-only` for `status`/`health`/`server`/`doctor` |

## Command mapping

Multi-line uv-style progress:

- `bqa`, `bqa start`, `bqa stop`, `bqa restart`, `bqa server restart`
- `bqa doctor`

Spinner-only uv-style progress:

- `bqa health`, `bqa capabilities`
- filesystem REST reads/search/mutations
- `bqa cmd check` and interactive `bqa cmd run`
- knowledge queries
- `bqa config validate` when individual substeps are too fast to justify rows

No progress for instant display/streaming operations:

- `status`, `url`, `version`
- help/completion
- config show/get/path
- log output/follow, including the merged `bqa logs all` view (same instant
  display when snapshotting; `-f` streams without a progress region)
- `chats`/`chats list` and `chats show <chat-id>` (local workspace reads, no REST call)

Interactive interfaces (own full screens; no uv progress region):

- `bqa ui` — UCS-SecretAgent desktop control center (native PySide6/Qt Widgets window); detaches from the
  terminal by default via the background launcher (PID in `logs/desktop-ui.pid`,
  follow with `bqa logs launcher -n 100`); `--foreground` and `--detach` also
  detach for compatibility; use `--inline` to keep it attached to the terminal
- `bqa tui` — keyboard-driven terminal control center

### GPT activity workspace rail

The `GPT Activity` tab is a Burp-style command-inspection view. A vertical
`WORKPLACES` rail on its left represents direct folders under the exact
`HOST_CHAT_ROOT` configured for host chat workspaces, excluding `.archive`.
The rail starts empty: its initial journal snapshot and Workspace Logs SSE
replay are only a baseline and do not open historical host-chat folders. Each
command received after that baseline reveals or restores its session, selects
it, and focuses this activity tab.
Selecting a workplace filters the command table to that chat id; `Disable`
keeps the folder but marks its UI tab off, while `Close tab` hides it until the
next command for that session arrives.

Each MCP `host_run_command` is journaled as one operation: it receives an opaque
`operation_id`, emits `started/running` after policy and CWD validation just
before the process is spawned, then emits `completed` with `succeeded`,
`failed`, or `timed_out`. The UI joins those events into one command row. While
only the start event exists, the command row and its workplace state explicitly
read `RUNNING`; a terminal event replaces it without duplicating the command.
Older journal records without lifecycle fields remain visible as standalone
completed records. The separate `OUTPUT` panel exposes `Metadata` (bounded
result facts, without raw stdout/stderr) and `Human-readable output` (command,
status, stdout, and stderr) for the selected call.

The rail and the `INPUT`/`OUTPUT` boxes are independently collapsible. Use the
left chevron to shrink `WORKPLACES` to a thin rail and the `Input`/`Output`
chevrons in the toolbar to hide or restore either inspection panel. You can
also drag the splitter between `WORKPLACES` and activity content, and the
splitter between `INPUT` and `OUTPUT`, to size the boxes directly. This only
changes the local desktop layout; it never closes a workplace or drops cached
command data.

### UCS-SecretAgent desktop layout

`bqa ui` opens the native PySide6/Qt Widgets **UCS-SecretAgent** console. Its thin header
contains the unchanged compact UCS emblem, a runtime badge, language selector,
and Close control. A left navigation rail selects the existing Runtime,
Workspace Logs, and GPT Activity notebook views; the fixed footer reports
backend state, selected workspace, last refresh, SSE state, and the newest
short message. The shared visual language is a graphite security console with
near-black surfaces, lime only for active/focus state, and semantic teal,
amber, and coral status accents. Text plus colour always communicate running,
success, warning, and error states, so command state never depends on colour
alone.

`BQA_UI_LANGUAGE=en` is the official default language preference for this
desktop UI; set it to `vi` for Vietnamese. The Language selector persists the
same value to `.env` and applies it to the open desktop window immediately. It
does not alter terminal CLI output, MCP/API contracts, or journal data. If the
process already exports `BQA_UI_LANGUAGE`, that environment value wins and the
selector refuses to write a conflicting `.env` value.

Runtime is a factual control centre: it shows an overall health banner plus MCP
Bridge, Server, and Cloudflare Tunnel cards, followed by Start, Stop, Restart,
Refresh, endpoint-copy, and workspace controls. Stop always asks for a native
confirmation before taking effect. A confirmed Stop uses the existing managed
runtime operation to stop the supervisor, MCP server, and Cloudflare tunnel;
canceling it does nothing. This UI action does not change MCP tools, API
contracts, lifecycle implementation, or journal data. Workspace Logs keeps up
to 500 cached journal rows and exposes category chips, a Chat ID filter, an
outcome menu, and Clear. Its drag splitter separates the table from a Summary,
Metadata, and pretty-JSON Payload inspector. A stream reset deliberately
clears the cursor, cached rows, and selection.

The GPT activity rail and COMMAND ACTIVITY table filter only the data already cached by
the client; no keystroke makes a backend request. Column headings sort the
command table. The OUTPUT inspector separates Metadata, STDOUT, STDERR, and
Human-readable views, and retains a tab's scroll position when its content has
not changed. `Copy tab` copies the entire active inspector tab; `Ctrl+C` inside
an inspector copies only the highlighted text. `/` focuses the input filter,
`Esc` clears local filters, and `Up`/`Down` moves a selected log row. All major
buttons retain a visible keyboard-accessible control.


## Help screens

Top-level help lists subcommands in grouped sections (Lifecycle, Interface,
Inspection, Files & commands, Diagnostics, Config & help) with the subcommand
metavar
rendered as `<command>`. On Python 3.14+ the parser disables argparse's own
color palette unconditionally, so all help styling stays owned by the shared
output layer. The Inspection group carries `status`, `health`, `capabilities`,
`knowledge`, `logs`, and `chats`; bare `bqa chats` is an alias for
`bqa chats list` (workspaces ordered by recent activity) and
`bqa chats show <chat-id>` prints one workspace's path, state notes head, and
journal counts — both honor the shared `--json`/`--quiet` modes and read the
local workspace root (`~/Downloads/bqa-workspaces` by default) without a REST
call.

## Automation contract

Machine modes remain stable. JSON/quiet output is unchanged by progress, and
raw command execution does not inject BQA progress summaries into captured child
stderr in non-TTY mode.
