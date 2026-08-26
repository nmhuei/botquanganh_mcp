# Architecture Decision Records

This directory holds the project's architecture decision records in MADR-lite style: Context, Decision, Consequences, numbered sequentially from 0001. Each record captures one accepted decision that still shapes how the host MCP server and `bqa` CLI behave today.

| #    | Title                                                                        | Status   | Date       | One-line essence                                                                                                     |
|------|------------------------------------------------------------------------------|----------|------------|-----------------------------------------------------------------------------------------------------------------------|
| 0001 | Remove the HTTP rate limiter; rely on command capacity gating                | Accepted | 2026-08-24 | Backpressure comes only from `CommandCapacity` (100 concurrent commands, queue then 503); no HTTP-layer throttling.     |
| 0002 | No caller-supplied approval flow                                             | Accepted | 2026-08-24 | Authorization is purely server-side policy (`guarded`/`allowlist`); the caller approval bypass surface was deleted.     |
| 0003 | Stateless JSON streamable-http as the only MCP transport                     | Accepted | 2026-08-22 | Exactly one transport: streamable-http with JSON responses, stateless forced on — self-contained POSTs, no sessions.    |
| 0004 | setsid daemonization with a shell supervisor loop                            | Accepted | 2026-08-21 | `bqa start` runs under its own session via `setsid`, supervised by a shell loop that respawns and health-checks hourly. |
| 0005 | uv pip replaces pip in install.sh                                            | Accepted | 2026-08-20 | `install.sh` installs into `.venv` via `uv pip` with pinned deps for faster, deterministic setup.                       |
| 0006 | Hardening round 2 — bounded drains, honest readiness, serialized replace     | Accepted | 2026-08-25 | Bounded drain joins with `output_incomplete`, honest connector-ready reporting, flock-serialized file writes, REST capacity limiter, supervisor lock, per-variant cache TTLs. |
| 0007 | CLI UX overhaul — milestone rows, diff rendering, copy-safe output, fast paint | Accepted | 2026-08-25 | Milestone-driven progress rows, diff-based rendering, wrap-proof URL output, grouped help, lazy imports for fast first paint. |
| 0008 | Dependency-bump PRs merge only after a local pytest rehearsal | Accepted | 2026-08-26 | Throwaway uv venv rehearsal gates every bump; only the two pin-guard failures may stay red, dotenv needs oracle parity, manifests bump in lockstep. |

New ADRs use the next sequential number (`0008`, `0009`, ...). For the most recent decision waves, see [0006](0006-hardening-round-2.md) and [0007](0007-cli-ux-overhaul.md).
