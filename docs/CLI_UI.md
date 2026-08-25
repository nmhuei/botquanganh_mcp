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
- log output/follow

## Help screens

Top-level help lists subcommands in grouped sections (Lifecycle, Inspection,
Files & commands, Diagnostics, Config & help) with the subcommand metavar
rendered as `<command>`. On Python 3.14+ the parser disables argparse's own
color palette unconditionally, so all help styling stays owned by the shared
output layer.

## Automation contract

Machine modes remain stable. JSON/quiet output is unchanged by progress, and
raw command execution does not inject BQA progress summaries into captured child
stderr in non-TTY mode.
