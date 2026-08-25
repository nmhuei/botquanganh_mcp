---
adr: 0007
title: CLI UX overhaul — milestone rows, diff rendering, copy-safe output, fast first paint
status: Accepted
date: 2026-08-25
---

## Context

The lifecycle progress UI completed every row simultaneously only after the
underlying action returned, so rows reported success in a burst instead of as
each component actually came up; the transient block was fully erased and
redrawn on every spinner tick (~0.20s), which visibly flickered on terminals;
the long Quick Tunnel wait (~40s worst case) presented no feedback between
start and finish and felt frozen; connector URLs were truncated or wrapped
mid-token at common terminal widths, breaking copy/paste; error hints suggested
`bqa doctor` regardless of the actual failure cause; and bare startup paid the
full import cost of every subcommand module before printing anything.

## Decision

1. Milestone-driven rows (`app/cli/main.py`, `_run_lifecycle_action`): the
   lifecycle action runs in a worker thread while the main thread polls
   `status_data` every ~150 ms and completes each row only when its real
   condition turns true (`_row_satisfied`: process running, bridge ready, URL
   present). Stage narration chains through server → tunnel → bridge →
   endpoint via `_START_STAGE_MESSAGES`, so the root line always names the
   stage currently being waited on.
2. Diff-based transient rendering (`app/cli/progress.py`, `_render`): the
   renderer keeps `_last_lines` and, when the block shape is unchanged,
   rewrites only lines whose content changed; structural changes fall back to
   full erase-and-redraw (`_erase_previous`). `finish()` renders no final
   frame and prints exactly one green summary line after close().
3. Perceived-latency feedback: the root line gains a dim `· elapsed` suffix
   only past 2 seconds; during multi-second waits (tunnel establishment) the
   stage message replaces silence instead of leaving a static spinner.
4. Copy-safe guarantee generalized: `Renderer.facts(..., no_wrap=...)`
   protects labeled values from wrapping (runtime status protects the
   Endpoint row), and `bqa doctor` lifts any check whose message embeds a URL
   or exceeds the inline width budget out of the table into a
   `copyable_value` block. URL and path values therefore remain one
   contiguous string at any terminal width.
5. Grouped help (`app/cli/parser.py`): commands render under named groups via
   `GroupedHelpFormatter` (unknown entries fall back to an "Other" bucket);
   Python ≥ 3.14's built-in argparse help color palette is disabled because
   this CLI owns all styling through `app.cli.output`; the subcommand
   metavar is `<command>`.
6. Startup latency: dispatch imports each command module lazily inside its
   `_dispatch` branch, urllib imports are deferred into request paths
   (`app/cli/client.py`), and the dependency-free `.env` parser
   (`app.config._load_env_file`) keeps python-dotenv off the CLI import path.
   First paint targets the ~45–70 ms band, measured by the firstpaint harness
   (final gate run: 45.7–68.6 ms across help / badcmd / status / health /
   url / config_show / doctor).

## Consequences

- The progress renderer's state machine now carries `_last_lines`
  bookkeeping; regressions in the diff path are locked by unit tests
  (`test_cli_progress.py`: changed-lines-only rewrite, fallback on row-count
  change, reset on close).
- Completion scripts are static templates keyed off a fixed command list, so
  parser changes do not propagate there automatically — the new `help`
  command was added manually; adding a subcommand requires touching both.
- The width/suppression certification matrices and firstpaint measurement
  runs live outside the repo (in `~/Downloads/bqa_ux_audit` and
  `~/Downloads/bqa_ux_probe`) and serve as repeatable acceptance harnesses;
  they must be re-run after any renderer, help, or startup-path change.
