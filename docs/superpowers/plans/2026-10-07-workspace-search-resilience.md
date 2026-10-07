# Workspace Search Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `workspace_search` fast, bounded, observable, and safe under broad or hostile searches.

**Architecture:** Split search limits, engines, and payload fitting into focused modules. Keep the MCP tool as a thin adapter. Use configured deadlines, work budgets, process cleanup, and capacity admission. Return partial results for exhausted work budgets.

**Tech Stack:** Python 3.14, FastMCP, ripgrep 15, pytest, Rust desktop shell, WebKit UI, QML settings UI.

**Spec:** `docs/superpowers/specs/2026-10-07-workspace-search-resilience-design.md`

## Global Constraints

- Read the spec before every task.
- Do not modify, restart, or terminate the Cloudflare tunnel.
- Do not commit, push, reset, checkout, or discard existing worktree changes.
- Use `app.config` as the single source for operational values.
- Expose every search operational value in both Desktop Settings implementations.
- Persist `.env` updates atomically.
- Keep functions below 50 lines. Use typed enums for states and actions.
- Return partial search results for deadline and work-budget limits.
- Run commands with `.venv/bin/python` and place temporary artifacts only in `~/Downloads/bqa-trash/`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `app/search_models.py` | Typed limits, outcomes, counters, and `SearchLimitReason`. |
| `app/search_runtime.py` | Deadline checks, process-group cleanup, and concurrency admission. |
| `app/search_engines.py` | Ripgrep and Python fallback search engines. |
| `app/tools_common.py` | Shared linear JSON-list response fitting helper. |
| `app/tools/workspace_search.py` | MCP validation, engine selection, response mapping, and journaling. |
| `app/config.py` | Validated search and MCP payload configuration. |
| `app/cli/config_view.py` | CLI/Desktop config defaults, validation, and atomic persistence. |
| `app/cli/desktop_ui.py` | Python Desktop Settings controls. |
| `app/qml_ui/backend.py` and QML settings files | QML Settings controls. |
| `crates/bqa_desktop/src/main.rs` | Rust desktop config read/write contract. |
| `crates/bqa_desktop/ui/index.html` | Rust Desktop Settings controls. |
| `app/observability.py` | Per-search timing and safe counters. |
| `tests/test_workspace_search*.py` | Unit, security, payload, limit, and concurrency regression tests. |

## Task 1: Define one validated search configuration contract

**Files:**
- Modify: `app/config.py:211,236-250`
- Modify: `.env.example:45-57`
- Modify: `app/cli/config_view.py:20-100`
- Modify: `tests/test_config_env_parity.py`
- Modify: `tests/test_scope_permissions.py`
- Create: `tests/test_workspace_search_config.py`

**Interfaces:**
- Produces immutable configuration names used by all later tasks.
- Reuses `SEARCH_TEXT_DEADLINE_SECONDS` and `MAX_SINGLE_FILE_BYTES`.
- Adds `MCP_MAX_PAYLOAD_BYTES` as the canonical bridge ceiling.

- [x] **Step 1: Write failing configuration tests**

```python
def test_workspace_search_limits_are_validated(monkeypatch):
    monkeypatch.setenv("WORKSPACE_SEARCH_MAX_WORK_MATCHES", "0")
    with pytest.raises(ValueError, match="WORKSPACE_SEARCH_MAX_WORK_MATCHES"):
        importlib.reload(app.config)


def test_workspace_search_keys_have_env_and_cli_parity():
    assert required_search_keys <= env_example_keys
    assert required_search_keys <= config_view.DEFAULTS
```

- [x] **Step 2: Run the new tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_config.py tests/test_config_env_parity.py`

Expected: FAIL because finite limits and settings keys do not exist.

- [x] **Step 3: Add validated configuration values**

Add these keys to `app.config`, `.env.example`, and `config_view` defaults and limits:

```text
WORKSPACE_SEARCH_MAX_WORK_MATCHES
WORKSPACE_SEARCH_MAX_SCANNED_FILES
WORKSPACE_SEARCH_MAX_SCANNED_BYTES
WORKSPACE_SEARCH_MAX_CONCURRENT
WORKSPACE_SEARCH_MAX_PER_CHAT
WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS
WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES
WORKSPACE_SEARCH_MAX_RETURNED_MATCHES
WORKSPACE_SEARCH_MAX_LINE_CHARS
MCP_MAX_PAYLOAD_BYTES
MCP_TOOL_RESULT_OVERHEAD_BYTES
```

Use a finite positive default for work matches, files, bytes, and capacity.
Use `SEARCH_TEXT_DEADLINE_SECONDS` for the deadline. Reject zero and negative
values where zero would disable a safety control. Keep values out of business
modules.

- [x] **Step 4: Run configuration tests**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_config.py tests/test_config_env_parity.py tests/test_scope_permissions.py`

Expected: PASS.

## Task 2: Add typed search outcomes and bounded admission

**Files:**
- Create: `app/search_models.py`
- Create: `app/search_runtime.py`
- Modify: `app/error_contract.py`
- Create: `tests/test_workspace_search_concurrency.py`

**Interfaces:**
- Produces `SearchLimitReason`, `SearchCounters`, `SearchOutcome`, and `SearchCapacity`.
- `SearchCapacity.acquire(chat_id: str | None) -> SearchLease` raises `ServiceBusyError` after the configured queue timeout.
- `SearchLease.release()` is idempotent and is always called in `finally`.

- [x] **Step 1: Write failing concurrency and outcome tests**

```python
def test_capacity_rejects_second_chat_search_before_engine(monkeypatch):
    manager = SearchCapacity(global_limit=1, per_chat_limit=1, queue_timeout=0)
    first = manager.acquire("chat-a")
    with pytest.raises(ServiceBusyError):
        manager.acquire("chat-b")
    first.release()


def test_partial_outcome_marks_deadline_without_error():
    outcome = SearchOutcome.partial(SearchLimitReason.DEADLINE)
    assert outcome.ok is True
    assert outcome.count_complete is False
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_concurrency.py`

Expected: FAIL because the types and capacity manager do not exist.

- [x] **Step 3: Implement typed models and capacity manager**

Use `Enum` subclasses for limit reasons and engine names. Use `threading.Condition`
and `time.monotonic`. Track global and per-chat active counts under one lock.
Map exhausted admission to existing `SERVICE_BUSY` semantics. Do not add a raw
string state or a polling loop.

- [x] **Step 4: Run focused tests**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_concurrency.py tests/test_error_contract.py`

Expected: PASS.

## Task 3: Implement deadline-safe engines and secure traversal

**Files:**
- Create: `app/search_engines.py`
- Modify: `app/host/paths.py`
- Modify: `app/tools/workspace_search.py:74-305`
- Create: `tests/test_workspace_search_engines.py`
- Modify: `tests/test_workspace_search.py`
- Modify: `tests/test_filesystem_security.py`

**Interfaces:**
- Consumes: `SearchOutcome`, `SearchCounters`, and config from Tasks 1–2.
- Produces: `run_ripgrep_search(...) -> SearchOutcome` and `run_python_search(...) -> SearchOutcome`.
- Both engines return ordered matches, observed count, count completeness, counters, and one `SearchLimitReason | None`.

- [x] **Step 1: Write failing engine-limit tests**

```python
def test_ripgrep_deadline_terminates_and_reaps_process(fake_slow_process, monkeypatch):
    monkeypatch.setattr(app.config, "SEARCH_TEXT_DEADLINE_SECONDS", 0.01)
    outcome = run_ripgrep_search(...)
    assert outcome.limit_reason is SearchLimitReason.DEADLINE
    assert fake_slow_process.terminated is True
    assert fake_slow_process.reaped is True


def test_python_engine_skips_fifo_symlink_and_large_binary(tmp_path, monkeypatch):
    outcome = run_python_search(...)
    assert outcome.matches == []
    assert outcome.counters.skipped_special_files >= 1
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_engines.py tests/test_filesystem_security.py`

Expected: FAIL because both engines lack bounded cleanup and secure traversal.

- [x] **Step 3: Implement ripgrep engine**

Build argv with `--no-config`, `--json`, `--binary-files=without-match`,
configured `--max-filesize`, ignore rules, deny glob exclusions, and `--`.
Start a new process group. Read with a deadline-aware mechanism. Do not wait
until stdout iteration finishes before checking time. On any early exit,
terminate the group, drain bounded stderr, and reap in `finally`.

Treat exit code `0` as matches and `1` as no matches. Convert invalid regex,
I/O errors, and other exit codes into typed error responses. Preserve literal
and regex behaviour.

- [x] **Step 4: Implement Python fallback**

Use `lstat`, regular-file checks, no-follow opens, binary detection, and
configured size, file, byte, match, and deadline budgets. Reuse path-policy
helpers so deny globs apply to descendants. Precompute a case-folded literal
once. Never follow symlinks.

- [x] **Step 5: Run focused engine tests**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_engines.py tests/test_workspace_search.py tests/test_filesystem_security.py`

Expected: PASS.

## Task 4: Replace quadratic response trimming with a shared linear helper

**Files:**
- Modify: `app/tools_common.py:38-69`
- Modify: `app/observability.py:203-295`
- Modify: `app/tools/workspace_search.py:406-445`
- Create: `tests/test_workspace_search_payload.py`
- Modify: `tests/test_workspace_search.py`

**Interfaces:**
- Produces `fit_json_list_response(envelope: dict[str, Any], list_key: str, budget_bytes: int) -> dict[str, Any]`.
- Returns the longest ordered prefix that fits the reserved payload budget.
- Uses `MCP_MAX_PAYLOAD_BYTES` minus `MCP_TOOL_RESULT_OVERHEAD_BYTES`.

- [x] **Step 1: Write failing payload tests**

```python
def test_fitter_keeps_utf8_prefix_with_one_final_serialization(monkeypatch):
    result = fit_json_list_response(envelope_with_500_long_unicode_matches, "matches", 512_000)
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 512_000
    assert result["truncated"] is True


def test_real_mcp_tool_result_fits_wire_limit(client):
    response = client.call_tool("workspace_search", huge_search_arguments)
    assert serialized_call_tool_result_bytes(response) <= app.config.MCP_MAX_PAYLOAD_BYTES
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_payload.py tests/test_workspace_search.py`

Expected: FAIL because current trimming serializes a shrinking complete list.

- [x] **Step 3: Implement the linear fitter**

Serialize each item once. Count brackets, commas, item bytes, and fixed
envelope bytes. Reserve final `truncated` and `limit_reason` fields before
accepting items. Keep `enforce_bridge_payload_limit` only as a hostile-output
fallback. Use the same helper in content and path modes.

Set `truncated=true` in path mode when cap or payload omits paths. Keep current
content field meanings. Set the primary limit reason in this order:
deadline, work matches, result cap, then payload.

- [x] **Step 4: Run payload tests**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_payload.py tests/test_workspace_search.py tests/test_mcp_forensics.py`

Expected: PASS.

## Task 5: Integrate engines, partial responses, policy, and telemetry

**Files:**
- Modify: `app/tools/workspace_search.py:308-445`
- Modify: `app/tools_common.py`
- Modify: `app/observability.py:203-295`
- Modify: `app/activity_log.py` if journal schema requires a safe extension
- Create: `tests/test_workspace_search_limits.py`
- Modify: `tests/test_agent_guidance.py`
- Modify: `tests/test_br_guidance.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces additive result fields: `limit_reason`, `scanned_files`, and `scanned_bytes`.
- Returns `SERVICE_BUSY` when capacity admission fails.

- [x] **Step 1: Write failing integration tests**

```python
def test_deadline_returns_safe_partial_result(bound_search_workspace, monkeypatch):
    result = workspace_search(query="needle", path=str(bound_search_workspace))
    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["limit_reason"] == "deadline"
    assert result["count_complete"] is False


def test_search_telemetry_never_contains_raw_query(secret_query):
    workspace_search(query=secret_query, path=".")
    assert secret_query not in read_recent_search_events()
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_limits.py tests/test_agent_guidance.py tests/test_br_guidance.py`

Expected: FAIL because partial metadata and safe telemetry do not exist.

- [x] **Step 3: Simplify the MCP adapter**

Validate inputs and acquire `SearchCapacity`. Resolve the root. Select an
engine. Map `SearchOutcome` to the existing response contract. Fit `matches`
with Task 4. Record telemetry counters. Release the lease and finish the
journal in `finally`.

Do not journal raw query data. Replace it with query length and a keyed digest.
Keep `server_info` tool discovery accurate for the new limits.

- [x] **Step 4: Run integration tests**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search.py tests/test_workspace_search_limits.py tests/test_workspace_search_concurrency.py tests/test_agent_guidance.py tests/test_br_guidance.py`

Expected: PASS.

## Task 6: Expose limits in both Desktop Settings interfaces

**Files:**
- Modify: `app/cli/config_view.py`
- Modify: `app/cli/desktop_ui.py`
- Modify: `app/qml_ui/backend.py`
- Modify: relevant QML settings files under `app/qml_ui/qml/`
- Modify: `crates/bqa_desktop/src/main.rs:1090-1110`
- Modify: `crates/bqa_desktop/ui/index.html:1300-1740,3830-3860`
- Create: `tests/test_workspace_search_settings.py`
- Modify: existing QML and desktop settings tests

**Interfaces:**
- Consumes validated keys from Task 1.
- Produces settings fields that atomically persist every search value to `.env`.

- [x] **Step 1: Write failing settings tests**

```python
def test_search_settings_validate_and_persist_atomically(repo_root):
    result = set_operational_config(repo_root, {
        "WORKSPACE_SEARCH_MAX_CONCURRENT": "2",
        "SEARCH_TEXT_DEADLINE_SECONDS": "5",
    })
    assert result["WORKSPACE_SEARCH_MAX_CONCURRENT"] == "2"
    assert read_env(repo_root)["SEARCH_TEXT_DEADLINE_SECONDS"] == "5"


def test_desktop_settings_payload_includes_search_limits():
    assert "WORKSPACE_SEARCH_MAX_CONCURRENT" in rust_settings_payload()
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_settings.py tests/test_config_env_parity.py`

Expected: FAIL because search limits are not editable from both desktop UIs.

- [x] **Step 3: Implement validated settings controls**

Add a compact Search Limits group to QML and Rust settings. Include labels,
units, validation feedback, and pointer-event suppression for controls. Wire
every value through existing atomic persistence. Restart only the MCP server
after save. Preserve the existing Cloudflare tunnel process and URL.

- [x] **Step 4: Run settings tests**

Run: `.venv/bin/python -m pytest -q tests/test_workspace_search_settings.py tests/test_config_env_parity.py tests/test_qml_backend.py tests/test_ui_preferences.py`

Expected: PASS. Skip unavailable GUI dependency tests only through their
existing skip conditions.

## Task 7: Update documentation and execute verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CHAT_WORKSPACES.md`
- Modify: `knowledge/WORKING_GUIDE.md`
- Modify: `knowledge/TOOL_CATALOG.json`
- Modify: `docs/BQA_MCP_AUDIT_HANDOFF_2026-10-06.md` only if new evidence changes its status

- [x] **Step 1: Document bounded search behaviour**

Document `path` as the search root. Document partial result fields,
`exact_count` cost, deadline semantics, and Settings values. Do not mention
retired tool names. Keep historical records under `docs/old_docs/` unchanged.

- [x] **Step 2: Add reproducible benchmark coverage**

Create only temporary benchmark data under `~/Downloads/bqa-trash/`. Measure
sparse, dense, exact-count, deadline, payload, and concurrency cases. Record
inputs and results in the audit handoff only when measurements are stable.

- [x] **Step 3: Run focused verification**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_workspace_search.py \
  tests/test_workspace_search_config.py \
  tests/test_workspace_search_engines.py \
  tests/test_workspace_search_payload.py \
  tests/test_workspace_search_limits.py \
  tests/test_workspace_search_concurrency.py \
  tests/test_workspace_search_settings.py \
  tests/test_filesystem_security.py
git diff --check
git diff --cached --check
```

Expected: all selected tests pass and both diff checks return zero.

- [x] **Step 4: Run the complete suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass. Report the exact count and duration.

- [x] **Step 5: Inspect live server without lifecycle changes**

Read `logs/tunnel_url.txt` dynamically. Call local `/debug/transport`. Confirm
the tool catalog still contains exactly eight tools. Do not restart or terminate
Cloudflare tunnel processes.

## Plan Self-Review

| Specification item | Plan task |
| --- | --- |
| Partial result contract | Tasks 2, 5 |
| Deadline and cleanup | Task 3 |
| Finite work budgets | Tasks 1, 3, 5 |
| Linear payload fitting | Task 4 |
| Safe fallback and deny policy | Task 3 |
| Concurrency admission | Tasks 2, 5 |
| Desktop configuration | Tasks 1, 6 |
| Safe telemetry | Task 5 |
| Documentation and verification | Task 7 |

The plan has no placeholder tasks. All public behaviour changes have focused
tests before implementation. The plan preserves the active tunnel and dirty
worktree.
