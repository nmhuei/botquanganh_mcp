# Seamless Chat Workspaces & Auto-Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the chat workspace system from an error-prone token-gated mechanism into a seamless, self-healing, zero-token auto-continuation experience where ChatGPT sessions maintain perfect state continuity across dead sessions and multi-prompt turns.

**Architecture:** 
- Implement **Zero-Token Auto-Resume & Auto Un-Archive** in `app/chat_workspace.py` using `.last_session` pointer and automatic `.archive/` recovery.
- Add **Context Auto-Hydration & Idempotency** to `host_workspace_bind` so subsequent prompt binds in the same session reuse the active workspace and inject recent `STATE.md` + notes into the response payload.
- Introduce **`host_workspace_list`** MCP discovery tool for proactive project resumption.
- Provide **Implicit Attribution Fallback** in `app/tools/host.py` when `chat_id` is omitted in subsequent turns.
- Add CLI commands (`bqa chats resume`, `bqa chats unlock`, `bqa chats token`) in `app/cli/chats_view.py`.

**Tech Stack:** Python 3.10+, FastMCP, Starlette, pytest.

**Spec Reference:** Architectural Design for Seamless Chat Workspaces (Session Dead Continuity, Zero-Token Resume, Single-Session Sticky Affinity).

---

## Global Constraints

- Preserve verbatim `CHAT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")`.
- Maintain full backwards compatibility for existing `meta.json` files (Schema 1 and 2).
- Zero-token mode must be safe under `GATEWAY_TOKEN` authentication; optional PIN/token verification is retained for multi-tenant setups.
- Never leak raw secrets, passwords, or authentication bearer tokens in `journal.jsonl`, `STATE.md`, or CLI output.
- All file operations must respect strict path validation and `0o600` / `0o700` permission masks.

---

### Task 1: Zero-Token Auto-Resume, `.last_session` Pointer & Auto Un-Archive

**Files:**
- Modify: `app/chat_workspace.py:720-860`
- Modify: `app/config.py:253-283`
- Test: `tests/test_chat_workspace.py`

**Interfaces:**
- Consumes: `app.config.HOST_CHAT_ROOT`, `app.config.HOST_CHAT_AUTH_MODE`
- Produces: `WorkspaceManager.create_or_bind(chat_id, label, resume_token, require_token, force_new)`
- Produces: `WorkspaceManager.get_latest_active_chat_id() -> str | None`
- Produces: `WorkspaceManager.record_last_session(chat_id)`

- [ ] **Step 1: Write the failing tests for Auto Un-Archive and `resume_id="latest"`**

Add tests in `tests/test_chat_workspace.py`:
```python
def test_create_or_bind_auto_unarchives_expired_workspace(tmp_path: Path):
    manager = WorkspaceManager(tmp_path)
    # 1. Create a workspace
    bound = manager.create_or_bind(label="archive-test")
    chat_id = bound.chat_id
    assert (tmp_path / chat_id / "meta.json").is_file()

    # 2. Simulate sweeper archiving it to .archive/
    archive_dir = tmp_path / ".archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / chat_id).rename(archive_dir / chat_id)
    assert not (tmp_path / chat_id).exists()
    assert (archive_dir / chat_id).is_dir()

    # 3. Call create_or_bind with the archived chat_id
    rebound = manager.create_or_bind(chat_id)
    assert rebound.chat_id == chat_id
    assert not rebound.created  # Must be resumed, not created fresh
    assert (tmp_path / chat_id).is_dir()  # Must be restored to active root
    assert not (archive_dir / chat_id).exists()


def test_create_or_bind_latest_alias(tmp_path: Path):
    manager = WorkspaceManager(tmp_path)
    # Create initial workspace
    bound1 = manager.create_or_bind(label="first")
    # Resume with "latest"
    bound2 = manager.create_or_bind("latest")
    assert bound2.chat_id == bound1.chat_id
    assert not bound2.created
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_chat_workspace.py -k "test_create_or_bind_auto_unarchives or test_create_or_bind_latest_alias" -v`
Expected: FAIL.

- [ ] **Step 3: Implement Auto Un-Archive, `.last_session` pointer, and `latest` alias**

In `app/config.py`:
```python
HOST_CHAT_AUTH_MODE = os.getenv("HOST_CHAT_AUTH_MODE", "trust_gateway").strip().lower()
```

In `app/chat_workspace.py`:
- Add `LAST_SESSION_POINTER = ".last_session"`
- Update `create_or_bind` to:
  1. Resolve `latest` / `@latest` alias by reading `LAST_SESSION_POINTER` or newest directory mtime.
  2. Check if `(self.root / ".archive" / validated).is_dir()`, and if so, atomically move `(self.root / ".archive" / validated)` back to `(self.root / validated)`.
  3. Update `.last_session` with `{"chat_id": chat_id, "updated_at": _utc_now_iso()}`.
  4. In `_bind_existing`, respect `HOST_CHAT_AUTH_MODE`: if `trust_gateway`, bypass strict `ResumeUnauthorizedError` when no token is provided.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_workspace.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/chat_workspace.py app/config.py tests/test_chat_workspace.py
git commit -m "feat(workspace): add auto-unarchive, .last_session pointer, and zero-token resume"
```

---

### Task 2: Context Auto-Hydration & Idempotent Bind in `host_workspace_bind`

**Files:**
- Modify: `app/chat_workspace.py:840-865`
- Modify: `app/tools/workspace_tools.py:70-155`
- Test: `tests/test_chat_tools_unit.py`

**Interfaces:**
- Produces: `BindResult.auto_hydrated_context: dict[str, Any]` containing recent notes, state summary, pending ops.
- Produces: `host_workspace_bind(label, resume_id, new, chat_id)` response containing `resume_prompt` and `resume_badge_markdown`.

- [ ] **Step 1: Write the failing tests for Auto-Hydration and Idempotent Bind**

Add test in `tests/test_chat_tools_unit.py`:
```python
@pytest.mark.asyncio
async def test_host_workspace_bind_auto_hydrates_and_provides_resume_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.tools.workspace_tools._chat_root", lambda: tmp_path)
    monkeypatch.setattr("app.tools.workspace_tools._workspaces_enabled", lambda: True)

    # 1. First bind
    res1 = await host_workspace_bind(label="my-task")
    assert res1["ok"] is True
    chat_id = res1["chat_id"]
    assert "resume_prompt" in res1
    assert "resume_badge_markdown" in res1
    assert (tmp_path / chat_id / "RESUME.md").is_file()

    # 2. Append note
    await host_save_note(text="Step 1 completed: installed deps", chat_id=chat_id)

    # 3. Second bind without arguments (simulating prompt #2 in same session or new chat)
    res2 = await host_workspace_bind()
    assert res2["ok"] is True
    assert res2["chat_id"] == chat_id
    assert res2["created"] is False
    assert "auto_hydrated_context" in res2
    notes = res2["auto_hydrated_context"]["recent_notes"]
    assert any("Step 1 completed" in n for n in notes)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_chat_tools_unit.py -k "test_host_workspace_bind_auto_hydrates" -v`
Expected: FAIL.

- [ ] **Step 3: Implement Auto-Hydration, `RESUME.md` file generation, and Prompt Badges**

1. In `app/chat_workspace.py`:
   - In `_initialize`, write `RESUME.md` to `ws / "RESUME.md"`.
   - In `_bind_existing`, build `auto_hydrated_context`:
     - Load last 10 lines of `notes/log.txt`.
     - Load pending ops from `read_journal_records(ws)`.
     - Summarize event counts from `summarize_journal_records`.
   - Populate `BindResult.auto_hydrated_context`.

2. In `app/tools/workspace_tools.py`:
   - Update `host_workspace_bind` parameter list:
     `async def host_workspace_bind(label: str | None = None, resume_id: str | None = None, new: bool = False, chat_id: str | None = None) -> dict[str, Any]`
   - Update tool description to clearly instruct GPT to call it only once and reuse `chat_id`.
   - Include `resume_prompt`, `resume_badge_markdown`, and `auto_hydrated_context` in `tool_success`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_tools_unit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/chat_workspace.py app/tools/workspace_tools.py tests/test_chat_tools_unit.py
git commit -m "feat(tools): add auto-hydration, resume badges, and idempotent host_workspace_bind"
```

---

### Task 3: Workspace Discovery Tool `host_workspace_list`

**Files:**
- Modify: `app/tools/workspace_tools.py`
- Modify: `app/tools/__init__.py`
- Modify: `app/main.py`
- Test: `tests/test_chat_tools_unit.py`

**Interfaces:**
- Produces: `host_workspace_list(limit: int = 5, include_archived: bool = True, query: str | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test for `host_workspace_list`**

Add test in `tests/test_chat_tools_unit.py`:
```python
@pytest.mark.asyncio
async def test_host_workspace_list_returns_recent_workspaces(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.tools.workspace_tools._chat_root", lambda: tmp_path)
    monkeypatch.setattr("app.tools.workspace_tools._workspaces_enabled", lambda: True)

    # Create two workspaces
    res1 = await host_workspace_bind(label="crawler-job", new=True)
    res2 = await host_workspace_bind(label="analysis-job", new=True)

    list_res = await host_workspace_list(limit=5)
    assert list_res["ok"] is True
    assert len(list_res["workspaces"]) >= 2
    chat_ids = [w["chat_id"] for w in list_res["workspaces"]]
    assert res1["chat_id"] in chat_ids
    assert res2["chat_id"] in chat_ids
    assert "last_active_human" in list_res["workspaces"][0]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_chat_tools_unit.py -k "test_host_workspace_list" -v`
Expected: FAIL with "host_workspace_list not defined".

- [ ] **Step 3: Implement `host_workspace_list` tool**

In `app/tools/workspace_tools.py`:
```python
@mcp.tool(
    name="host_workspace_list",
    description=(
        "List recent host workspaces with their chat_id, label, last active time, "
        "and summary. Use this tool when the user wants to resume an earlier project, "
        "continue previous work, or find existing workspaces."
    ),
)
async def host_workspace_list(
    limit: int = 5,
    include_archived: bool = True,
    query: str | None = None,
) -> dict[str, Any]:
    # 1. Scan workspace root and archive
    # 2. Extract metadata: chat_id, label, created_at, mtime, state (active/archived), notes count
    # 3. Filter and sort by last_active descending
    # 4. Return formatted list with resume suggestions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_tools_unit.py -k "test_host_workspace_list" -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/tools/workspace_tools.py tests/test_chat_tools_unit.py
git commit -m "feat(tools): add host_workspace_list discovery tool"
```

---

### Task 4: Implicit Attribution Fallback in Host Tools

**Files:**
- Modify: `app/tools/host.py:144-189`
- Modify: `app/chat_identity.py:60-98`
- Test: `tests/test_chat_identity.py`
- Test: `tests/test_chat_tools_unit.py`

**Interfaces:**
- Consumes: `app.chat_identity.get_active_workspace() -> str | None`
- Produces: `_guard_chat_id(tool, chat_id)` with graceful fallback to active workspace.

- [ ] **Step 1: Write failing test for implicit chat_id fallback**

Add test in `tests/test_chat_tools_unit.py`:
```python
def test_guard_chat_id_falls_back_to_latest_workspace_under_enforce(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.chat_identity.is_enforcing", lambda: True)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))

    # Bind a workspace so it becomes active
    manager = WorkspaceManager(tmp_path)
    bound = manager.create_or_bind(label="active-test")
    chat_id = bound.chat_id

    # Call _guard_chat_id without chat_id
    from app.tools.host import _guard_chat_id
    validated, rejection = _guard_chat_id("host_write_file", None)
    assert rejection is None
    assert validated == chat_id
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_chat_tools_unit.py -k "test_guard_chat_id_falls_back" -v`
Expected: FAIL.

- [ ] **Step 3: Implement active workspace fallback in `_guard_chat_id`**

In `app/chat_identity.py`:
- Add `get_active_workspace() -> str | None` which checks `_CHAT_ID.get()` first, then reads `.last_session` pointer from `HOST_CHAT_ROOT`.

In `app/tools/host.py`:
- In `_guard_chat_id`: if `resolved is None`, attempt fallback using `get_active_workspace()`. If an active workspace directory with `meta.json` exists, resolve to it seamlessly.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_tools_unit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/tools/host.py app/chat_identity.py tests/test_chat_tools_unit.py tests/test_chat_identity.py
git commit -m "feat(attribution): add implicit active workspace fallback for host tools"
```

---

### Task 5: CLI Extensions (`bqa chats resume`, `bqa chats unlock`, `bqa chats token`)

**Files:**
- Modify: `app/cli/parser.py`
- Modify: `app/cli/chats_view.py`
- Test: `tests/test_cli_chats.py`

**Interfaces:**
- Produces: CLI commands `bqa chats resume`, `bqa chats unlock <chat-id>`, `bqa chats token <chat-id>`.

- [ ] **Step 1: Write failing test for `bqa chats resume` and `bqa chats unlock`**

Add tests in `tests/test_cli_chats.py`:
```python
def test_cli_chats_resume_outputs_formatted_prompt(tmp_path: Path, monkeypatch, capsys):
    manager = WorkspaceManager(tmp_path)
    bound = manager.create_or_bind(label="cli-test")
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))

    ctx = CLIContext(json_output=False, quiet=False, color=False)
    args = argparse.Namespace(chats_command="resume")
    code = handle_chats(ctx, args)
    assert code == 0
    captured = capsys.readouterr().out
    assert bound.chat_id in captured
    assert "Tiếp tục làm việc trong workspace" in captured
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_cli_chats.py -k "test_cli_chats_resume" -v`
Expected: FAIL.

- [ ] **Step 3: Implement CLI handlers in `app/cli/chats_view.py` and `app/cli/parser.py`**

- Add subcommands in `app/cli/parser.py`: `resume`, `unlock`, `token`.
- In `app/cli/chats_view.py`:
  - `_resume_workspace(ctx)`: Read `.last_session`, display formatted card with copyable prompt.
  - `_unlock_workspace(ctx, chat_id)`: Remove `token_hash` from `meta.json`.
  - `_token_status(ctx, chat_id)`: Show whether workspace has a token or is unlocked.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_chats.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/cli/parser.py app/cli/chats_view.py tests/test_cli_chats.py
git commit -m "feat(cli): add bqa chats resume, unlock, and token commands"
```

---

### Task 6: Documentation & Custom GPT Instructions Synchronization

**Files:**
- Modify: `docs/CHAT_WORKSPACES.md`
- Modify: `README.md`
- Modify: `knowledge/WORKING_GUIDE.md`
- Modify: `knowledge/TOOL_CATALOG.json`

- [ ] **Step 1: Update documentation and knowledge base**

- Document `host_workspace_list` and new `host_workspace_bind` signature in `docs/CHAT_WORKSPACES.md` and `README.md`.
- Update `knowledge/TOOL_CATALOG.json` to include `host_workspace_list`.
- Update `knowledge/WORKING_GUIDE.md` with the new zero-token auto-continuation workflow and single-session sticky binding protocol.

- [ ] **Step 2: Run full test suite and quality gate**

Run: `pytest -v`
Run: `./scripts/quality_gate.sh --quick`
Expected: All tests PASS.

- [ ] **Step 3: Commit documentation updates**

```bash
git add docs/ README.md knowledge/
git commit -m "docs(workspace): update guide and tool catalog for zero-token auto-continuation"
```
