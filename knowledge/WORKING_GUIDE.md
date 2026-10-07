# Working Guide

## Recommended sequence

1. Call `server_info` to inspect status, limits and the active catalog.
2. Call `workspace_context(action="bind")` to create or resume a workspace.
3. Use `workspace_explore` to inspect directories and bounded file windows.
4. Use `workspace_search` for text, regex and path searches.
   - Pass `path` as the search root.
   - Expect partial results with `truncated` and `limit_reason` on budgets.
   - Prefer capped searches; use `exact_count` only when a full total is required.
   - Tune `SEARCH_TEXT_DEADLINE_SECONDS` and Search Limits in Settings.
5. Use `workspace_edit` for writes, appends and verified replacements.
6. Use `terminal_execute` for commands. Use `task` for long-running commands.
7. Use `web_intelligence` only for required HTTP or HTTPS research.

## Code-change rules

- Check `git status` and `git diff` before editing.
- Make small changes with relevant tests.
- Report test evidence before claiming a fix.
- Do not write secrets or sensitive command output into logs or documents.
- Prefer paths relative to `HOST_WORKSPACE_DIR`.

## Commands and tasks

- Set the correct working directory before execution.
- Read the exit code, standard output, standard error and truncation fields.
- Use `task(action="wait")` instead of repeated polling.
- Do not bypass a policy rejection from the caller.

## Scratch location

Use `~/Downloads/bqa-trash/` for temporary downloads, test data and unpacked
archives. Keep repository roots free from test artifacts.
