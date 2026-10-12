# Repository Assessment — Cycle 01

## Executive summary
The repository baseline passed 38 tests, compile checks, Bash syntax checks, local/public REST health, and MCP initialize. A confirmed command-policy parsing defect split shell separators inside quoted strings.

## Repository identity and baseline commit
- Branch: `refactor/host-core-clean-v1`
- Baseline commit: `0d63fa331d219311c0219f9dbc4f28119844c223`
- Working tree: contains the uncommitted CLI and tunnel lifecycle work already requested by the user.

## Detected stack
Python 3.13, FastMCP 3.4.0, Starlette HTTP/REST, Bash lifecycle scripts, argparse/urllib CLI, pytest.

## Architecture and main data flows
CLI or ChatGPT → local/public HTTP → auth/rate-limit middleware → REST or MCP adapters → host filesystem/command/knowledge core.

## Build/test/lint baseline
- `38 passed`
- compileall: PASS
- Bash syntax: PASS
- `git diff --check`: PASS

## Logic and reliability risks
`_CHAIN_SPLIT_RE` split `;` and `|` before quote parsing, producing `<parse-error>` for valid commands and potentially blocking valid allowlisted commands.

## Security risks
Incorrect command-name extraction weakens audit fidelity and can create inconsistent allowlist decisions. No destructive testing was performed.

## Prioritized backlog
1. Replace regex chain splitting with quote-aware parsing.
2. Add regression coverage for quoted separators and real command chains.

## Evidence and commands executed
`pytest`, `compileall`, `bash -n`, `bqa doctor`, direct `inspect_host_command()` reproduction.
