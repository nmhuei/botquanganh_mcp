# Current Documentation Design

## Goal

Make active documentation describe BQA MCP 2.0 accurately.

## Active documentation

Keep these files in their current locations:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/CHAT_WORKSPACES.md`
- `docs/CLI_USAGE.md`
- `docs/CLI_UI.md`
- `docs/MCP_FORENSICS_RUNBOOK.md`
- `docs/OPERATIONS_RUNBOOK.md`
- `docs/QML_CENTER_UI.md`
- `docs/RELEASE_CHECKLIST.md`
- `knowledge/WORKING_GUIDE.md`
- `knowledge/HOST_ENVIRONMENT.md`
- `.env.example`

Describe the eight active MCP tools only:

1. `server_info`
2. `workspace_context`
3. `workspace_explore`
4. `workspace_edit`
5. `workspace_search`
6. `terminal_execute`
7. `task`
8. `web_intelligence`

Use `workspace_context(action="bind")` in all binding guidance.
Use `server_info` for capability and health discovery.

## Historical documentation

Create `docs/old_docs/` for completed plans, investigations, and reports.
Add `docs/old_docs/README.md` with the archive purpose and a warning.

Move completed implementation plans, design specifications, and dated reports there.
Keep ADRs in `docs/adr/`. They document decisions that still explain current behavior.
Keep the current audit handoff outside the archive. It tracks open reconciliation work.

## Operational scripts

Update maintained validation scripts to call active MCP tools.
Use `server_info` instead of `health_check` and `get_capabilities`.
Use current super-tool names in fixture activity records.

## Verification

Run the full pytest suite.
Run `git diff --check`.
Search active documentation and maintained scripts for removed MCP tool names.
Do not search `docs/old_docs/`, ADRs, or archived evidence for this validation.
