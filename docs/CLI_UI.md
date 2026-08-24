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
⠋ Starting runtime... (0/4)
server   ------------------------------   0/1
tunnel   ------------------------------   0/1
bridge   ------------------------------   0/1
endpoint ------------------------------   0/1
```

Rules:

- Spinner sequence: `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`.
- Spinner tick: 200 ms.
- Root template: `spinner + message + (pos/len)`.
- Active child rows are rendered underneath the root line.
- Child names align to the longest active name.
- Numeric child rows use a 30-character `-` bar, matching uv's request rows.
- Completed child rows disappear from the live region (`finish_and_clear` behavior).
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

Live progress is cleared before the persistent result. Completion summaries use
the same compact `verb ... in TIME` shape:

```text
Started runtime in 184ms
```

The primary artifact follows separately on stdout when applicable:

```text
https://example.trycloudflare.com/mcp
```

Filesystem/result changes use uv-style change markers (`+`, `-`, or `~` when an
existing object is updated) rather than a success panel.

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

## Automation contract

Machine modes remain stable. JSON/quiet output is unchanged by progress, and
raw command execution does not inject BQA progress summaries into captured child
stderr in non-TTY mode.
