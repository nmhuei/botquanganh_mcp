# BQA CLI Visual Contract

## Scope

This document defines the presentation contract for the canonical executable:

```text
bqa
```

The CLI remains static and transcript-oriented. It does not use a full-screen TUI.

## Visual system

```text
Style          Minimal, linear, whitespace-first
Brand          ◆ BotQuangAnh
Header         Maximum two lines
Accent         Cyan
Success        ● + green + text
Warning        ▲ + yellow + text
Failure        × + red + text
Offline        ○ + dim + text
Tables         Borderless by default
Outer indent   2 cells
Continuation   4 cells
Label gap      3 cells
```

A human-readable command normally follows:

```text
Brand header
Context

Primary status

Facts or table

Summary

Next action
```

Raw-data commands such as `bqa fs cat`, `bqa cmd run`, log streams, and shell completion intentionally skip decorative headers so their primary data remains usable.

## Output modes

### Human

Default mode for direct terminal use.

- Header and semantic status symbols are allowed.
- Color follows `--color auto|always|never`.
- `NO_COLOR`, `TERM=dumb`, non-TTY output, and CI disable automatic color.
- Long values wrap or truncate according to terminal width.
- Copy-critical values such as the connector URL use `Renderer.copyable_value`: the terminal may soft-wrap visually, but the CLI never inserts a hard newline inside the value.
- Tables are borderless.

### Quiet

Enabled with:

```bash
bqa <command> --quiet
```

Contract:

- Primary value only.
- No header, hint, spinner, or ANSI.
- Suitable for command substitution and shell scripts.
- Multiple primary values are emitted one per line.

Examples:

```bash
state=$(bqa health --quiet)
endpoint=$(bqa url --quiet)
bqa capabilities --tools --quiet
```

### JSON

Enabled with:

```bash
bqa <command> --json
```

Contract:

- stdout contains one valid JSON document.
- Successful and failed operations both use stdout.
- Exit code still reflects success or failure.
- Structured errors contain `ok`, `status`, `operation`, `message`, `exit_code`, and optional `details`.
- Secret-like fields are redacted as `<redacted>`.
- Human text is never mixed into JSON output.

Example error:

```json
{
  "details": null,
  "exit_code": 2,
  "message": "the following arguments are required: fs_command",
  "ok": false,
  "operation": "fs",
  "status": "error"
}
```

## Responsive behavior

The renderer supports three layouts:

- Wide: 100 columns and above.
- Medium: 70–99 columns.
- Compact: below 70 columns.

At compact widths:

- Facts become stacked label/value blocks.
- Tables become repeated fact lists.
- Hints wrap with a continuation indent.

Width calculations use visible Unicode cell width after removing ANSI and OSC control sequences. Vietnamese combining characters and East Asian wide characters are supported.

## Shared presentation layer

All styled command output is built through `app/cli/output.py`.

Primary primitives:

```text
Renderer.header
Renderer.status
Renderer.section
Renderer.facts
Renderer.copyable_value
Renderer.table
Renderer.checks
Renderer.summary
Renderer.hint
Renderer.error
```

Text helpers:

```text
strip_ansi
visible_width
truncate_visible
pad_to_width
wrap_visible
external_text
```

Command handlers gather data first and render that same data in human, quiet, or JSON mode. Raw command output remains raw by design.

## stdout and stderr

- Successful primary data: stdout.
- Human diagnostic errors: stderr.
- Quiet diagnostic errors: stderr.
- JSON success and JSON structured errors: stdout.
- Exit codes remain authoritative.
- External log ANSI is removed when color is disabled.

## Security

- Secret-like JSON fields are redacted recursively.
- Human config output shows `configured` or `not configured` instead of secret values.
- Quiet config output never reveals configured secret values.
- Full stack traces are not shown for normal user-facing errors.

## Error contract

Human errors answer:

1. Which operation failed.
2. The direct reason.
3. A copyable next command.

Example:

```text
◆ BotQuangAnh
  Operation failed

  × Could not complete `health`

  Unable to connect to http://127.0.0.1:8000.

  Try:
    bqa doctor --local-only
```

## Verification matrix

Automated tests cover:

```text
Widths       50, 60, 70, 80, 100, 120, 160
Output       human, quiet, JSON
Color        auto, always, never, NO_COLOR, non-TTY
Text         ANSI, OSC, Vietnamese, East Asian wide characters
Layout       facts, tables, wrapping, truncation, trailing spaces
Security     nested secret redaction
Errors       structured JSON on stdout
```

Manual verification must use only read-only commands unless lifecycle behavior is explicitly being tested. Routine CLI presentation work must not restart the Cloudflare tunnel.

## Definition of done

```text
[x] Header is at most two lines
[x] No large or nested boxes
[x] Shared visual tokens and renderer
[x] Human, quiet, and JSON contracts
[x] JSON errors remain parseable
[x] Quiet mode has no ANSI or decoration
[x] Borderless responsive tables
[x] Unicode-aware visible width
[x] Human errors include next action
[x] Secrets are redacted by default
[x] External logs honor color policy
[x] Width and output matrices are tested
[x] Tunnel is not restarted during presentation verification
```
