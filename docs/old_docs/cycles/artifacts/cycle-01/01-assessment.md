# Repository Assessment — Official Cycle 01

## Executive summary
The core host service and new CLI were operational, but five related correctness gaps existed across command parsing, public error envelopes, REST command semantics, rate-limit observability, and concurrent limiter state. The baseline had 38 passing tests; these gaps could produce false policy decisions, misleading server-error metrics, ambiguous client behavior, and inaccurate abuse telemetry.

## Repository identity and baseline commit
- Repository: `/home/light/GitHub/botquanganh_mcp`
- Branch: `refactor/host-core-clean-v1`
- Baseline commit: `0d63fa331d219311c0219f9dbc4f28119844c223`
- Working tree: intentionally contains the uncommitted CLI and tunnel lifecycle implementation requested by the user.

## Detected stack
- Python 3.13
- FastMCP 3.4.0
- Starlette REST/ASGI middleware
- Bash lifecycle scripts
- argparse/urllib CLI
- pytest

## Architecture and data flow
Client/CLI/ChatGPT → local or Cloudflare HTTP → token/rate-limit middleware → REST or MCP adapter → host filesystem, command policy/executor, or knowledge inventory → structured response and metrics/audit.

## Baseline execution
- Unit/integration tests: 38 passed
- compileall: PASS
- Bash syntax: PASS
- local/public REST health: PASS
- local/public MCP initialize: PASS
- diff check: PASS

## Confirmed gaps
1. Quote-unaware command chain parsing returned `<parse-error>` for valid commands containing `;` or `|` inside quotes.
2. `FileExistsError` was exposed as `INTERNAL_ERROR` through MCP tools.
3. A normally executed command with non-zero exit code was mapped to HTTP 500.
4. 429 rate-limit rejections did not increment `rate_limit_hits`.
5. Rate-limiter state was updated without synchronization and used wall-clock time.

## Security and reliability risks
- Inaccurate command identity can cause false allowlist rejection and weak audit evidence.
- Ambiguous errors and false HTTP 500s impair reliable automation and monitoring.
- Missing limiter metrics reduce abuse visibility.
- Concurrent limiter races may allow requests beyond configured limits.

## Prioritized backlog for this cycle
Unify these behaviors into one correctness layer and add regression tests at parser, adapter, REST integration, ASGI middleware, and concurrency levels.

## Limits
No dedicated SAST/SCA scanner was installed, so no complete CVE claim is made.
