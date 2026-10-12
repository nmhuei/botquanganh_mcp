# Repository Assessment — Official Cycle 02

## Executive summary
The CLI command tree worked through the project virtual environment, but installation and error handling were incomplete as a user-facing product. Editable package installation did not install a global command, the wrapper had previously failed when invoked through a symlink, and argparse usage failures bypassed the CLI JSON/error contract.

## Baseline
- Official Cycle 01: 45 tests passed.
- `bqa` console entry point existed in `.venv/bin`.
- A manually created `~/.local/bin/bqa` symlink was required for global use.

## Architecture findings
- `bin/bqa` is the repository-aware bootstrap wrapper.
- `pyproject.toml` supplies the virtualenv console entry point.
- `extract_global_options` supports global flags before or after subcommands.
- Native argparse `SystemExit` bypassed `main()` error rendering.

## Prioritized gaps
1. Repeatable global install/uninstall workflow.
2. Safe symlink resolution and external-working-directory execution.
3. JSON usage errors and stable exit code 2.
4. Subprocess regression coverage for actual installed paths.

## Security/operations risks
An uninstall command must never remove an unrelated executable. Installer output must not expose tokens. No production deployment or tunnel restart is required.
