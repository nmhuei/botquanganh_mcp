# Current Documentation Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make maintained BQA MCP documentation and validation scripts describe the eight active super-tools.

**Architecture:** Keep current operator guidance in its existing paths. Move completed plans, specifications, investigations, and reports to `docs/old_docs/`. Keep ADRs in `docs/adr/` because they retain technical context.

**Tech Stack:** Markdown, JSON, Bash, Python pytest, ripgrep, Git.

**Spec:** `docs/superpowers/specs/2026-10-07-current-documentation-design.md`

## Global Constraints

- Describe only the eight active MCP tools in maintained documentation.
- Use `workspace_context(action="bind")` for workspace binding.
- Use `server_info` for health and capability discovery.
- Preserve completed records in `docs/old_docs/`.
- Preserve ADRs in `docs/adr/`.
- Do not restart or modify the Cloudflare tunnel.
- Keep sentences short and direct.

---

### Task 1: Create the historical documentation archive

**Files:**
- Create: `docs/old_docs/README.md`
- Move: dated completed reports from `docs/`
- Move: completed plans from `docs/superpowers/plans/`
- Move: completed specifications from `docs/superpowers/specs/`

**Interfaces:**
- Consumes: current file history and Git rename detection.
- Produces: `docs/old_docs/` with a clear archive index.

- [ ] **Step 1: Classify documents**

Keep `docs/adr/`, `docs/BQA_MCP_AUDIT_HANDOFF_2026-10-06.md`, and current operator runbooks outside the archive.

Archive dated design, plan, investigation, verification, and implementation reports.

- [ ] **Step 2: Create the archive index**

Create `docs/old_docs/README.md` with this content:

```markdown
# Historical Documentation

This directory preserves completed plans, investigations, and reports.

Do not use these files as operational instructions.
Use the documents in `docs/`, `README.md`, and `knowledge/` for current behavior.
```

- [ ] **Step 3: Move historical files with Git-aware renames**

Run `git mv` for each classified historical document. Preserve filenames and relative subdirectories where practical.

- [ ] **Step 4: Verify archive layout**

Run:

```bash
find docs/old_docs -type f | sort
git status --short
```

Expected: archived files appear as renames, and active operator documents remain outside `docs/old_docs/`.

- [ ] **Step 5: Commit**

```bash
git add docs/old_docs docs
git commit -m "docs: archive completed plans and reports"
```

### Task 2: Rewrite maintained operator documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CHAT_WORKSPACES.md`
- Modify: `docs/MCP_FORENSICS_RUNBOOK.md`
- Modify: `docs/QML_CENTER_UI.md`
- Modify: `knowledge/WORKING_GUIDE.md`
- Modify: `knowledge/HOST_ENVIRONMENT.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `app/discovery.py` and `app/tools/server_info.py`.
- Produces: operational instructions that match the live eight-tool catalog.

- [ ] **Step 1: Replace the tool catalog**

Document these names exactly:

```text
server_info
workspace_context
workspace_explore
workspace_edit
workspace_search
terminal_execute
task
web_intelligence
```

- [ ] **Step 2: Replace binding and discovery guidance**

Use these instructions:

```text
Call workspace_context(action="bind") before workspace operations.
Call server_info for service status and available tool limits.
```

- [ ] **Step 3: Describe each super-tool by responsibility**

Map exploration, editing, search, task lifecycle, terminal execution, web retrieval, context persistence, and server discovery to their active tool names.

- [ ] **Step 4: Remove obsolete configuration descriptions**

Remove `HOST_KNOWLEDGE_DIR` guidance from active configuration documents.
Retain configuration values that current source reads from `.env`.

- [ ] **Step 5: Verify active documentation**

Run:

```bash
rg -n -i 'host_workspace_bind|host_workspace_list|host_run_command|host_read_file|host_list_directory|host_search_text|host_knowledge|health_check|get_capabilities|ctf_fetch_url|ctf_render_fetch_result' README.md docs knowledge .env.example -g '!docs/old_docs/**' -g '!docs/adr/**'
```

Expected: no active operational references remain.

- [ ] **Step 6: Commit**

```bash
git add README.md docs knowledge .env.example
git commit -m "docs: describe BQA MCP 2.0 super-tools"
```

### Task 3: Update maintained validation scripts

**Files:**
- Modify: `scripts/test_sse_client.py`
- Modify: `scripts/stress_mcp.py`
- Modify: `scripts/verify_desktop_ui.py`

**Interfaces:**
- Consumes: the MCP `server_info` contract and active activity event names.
- Produces: scripts that verify active MCP behavior.

- [ ] **Step 1: Replace retired MCP calls**

Replace every `health_check` tool invocation with `server_info`.

- [ ] **Step 2: Replace legacy fixture event names**

Use `workspace_explore` for reads and `terminal_execute` for commands.

- [ ] **Step 3: Run syntax validation**

Run:

```bash
.venv/bin/python -m py_compile scripts/test_sse_client.py scripts/stress_mcp.py scripts/verify_desktop_ui.py
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add scripts/test_sse_client.py scripts/stress_mcp.py scripts/verify_desktop_ui.py
git commit -m "test: use active MCP tool catalog in validation scripts"
```

### Task 4: Verify the documentation migration

**Files:**
- Verify: all files changed by Tasks 1 through 3

**Interfaces:**
- Consumes: active documentation, archived documentation, and active scripts.
- Produces: recorded release-ready verification evidence.

- [ ] **Step 1: Run formatting checks**

```bash
git diff --check
```

Expected: exit code `0`.

- [ ] **Step 2: Run focused and full tests**

```bash
.venv/bin/python -m pytest -q tests/test_tool_surface.py tests/test_agent_guidance.py
.venv/bin/python -m pytest -q
```

Expected: no test failures.

- [ ] **Step 3: Check active references**

Run the Task 2 search command and inspect every result.

Expected: results exist only under `docs/old_docs/` or `docs/adr/`.

- [ ] **Step 4: Review the final file set**

```bash
git status --short
git diff --stat
```

Expected: changes match the archive, active documentation, and validation-script scope.

- [ ] **Step 5: Commit**

```bash
git add README.md docs knowledge scripts .env.example
git commit -m "docs: complete current-state documentation migration"
```
