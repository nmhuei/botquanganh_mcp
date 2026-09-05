# UCS Desktop UI 2.0 Safe Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely integrate the reviewed premium UCS UI 2.0 with the uncommitted desktop boot and activity-focus work, then push `feature/vjp-pro` only after final verification is clean.

**Architecture:** Compose and review a clean integration branch before touching the user checkout. Apply only the verified desktop delta back with a recoverable three-way patch. Boot owns root hide/reveal and cleanup; the dashboard receives the injected Stop dependencies.

**Tech Stack:** Python 3.13, Tkinter/ttk, pytest, Git linked worktrees, fake-widget UI tests.

**Spec:** `docs/superpowers/specs/2026-09-01-ucs-desktop-premium-ui-design.md`; retain boot behavior in `docs/superpowers/specs/2026-08-30-desktop-boot-animation-design.md`.

## Global Constraints

- Touch only desktop UI modules, desktop UI tests, and desktop UI documentation. Never alter `app/host`, MCP tools, API/REST/SSE schemas, lifecycle implementation/scripts, journal schema, CLI grammar, or unrelated dirty files.
- Keep `resources/ucs-secretagent.png` unchanged and preserve the boot lifecycle.
- `run_desktop_ui` must retain `_start_desktop_boot(root, tk)`, exception cleanup, `stop_action`, and `stop_confirmation` propagation to `_DesktopDashboard`.
- Stop stays translated, native-confirmed, default-deny, cancel-safe, and uses existing `lifecycle.stop` through the UI worker flow.
- New activity may reveal a session only; it must not focus the window, navigate the notebook, or change the selected session.
- Test using `env HOST_READ_SCOPE= HOST_WRITE_SCOPE= /home/undertaker/Downloads/bqa/botquanganh_mcp/.venv/bin/python -m pytest`; this test-only override prevents the ancestor `.env` from overriding pytest fixtures.
- Push occurs only after clean source-checkout verification. If a non-UI project test fails, do not change it; report the exact blocker and do not push.

## File Scope

`app/cli/desktop_ui.py`, `app/cli/desktop_views/{boot,activity,theme,i18n,runtime,workspace_logs}.py`, `tests/test_cli_desktop_ui.py`, `tests/test_desktop_{boot,activity_view,theme,i18n,runtime_view,workspace_logs_view}.py`, and `docs/CLI_UI.md`.

---

### Task 1: Create an isolated composition branch

**Files:**

- Create transient recovery patches under `/tmp/opencode/`.
- Create linked worktree `.worktrees/ucs-ui2-integration-20260901` on `integration/ucs-ui2-20260901`.

**Interfaces:**

- Consumes reviewed head `fa3ea42` and only the source checkout's uncommitted desktop delta.
- Produces a clean branch containing UI 2.0 plus boot/activity behavior and no backend path.

- [ ] **Step 1: Back up only the dirty desktop delta**

```bash
mkdir -p /tmp/opencode
git diff --binary -- app/cli/desktop_ui.py app/cli/desktop_views/activity.py tests/test_cli_desktop_ui.py tests/test_desktop_activity_view.py > /tmp/opencode/ucs-ui2-user-desktop.patch
git diff --no-index --binary /dev/null app/cli/desktop_views/boot.py > /tmp/opencode/ucs-ui2-boot.patch || test $? -eq 1
git diff --no-index --binary /dev/null tests/test_desktop_boot.py > /tmp/opencode/ucs-ui2-boot-test.patch || test $? -eq 1
```

Verify every changed filename belongs to File Scope.

- [ ] **Step 2: Create and verify the integration worktree**

```bash
git worktree add .worktrees/ucs-ui2-integration-20260901 -b integration/ucs-ui2-20260901 fa3ea42
git -C .worktrees/ucs-ui2-integration-20260901 status --short
```

Expected: empty status before applying a patch.

- [ ] **Step 3: Apply the desktop-only user delta with three-way merge**

```bash
git -C .worktrees/ucs-ui2-integration-20260901 apply --3way /tmp/opencode/ucs-ui2-user-desktop.patch
git -C .worktrees/ucs-ui2-integration-20260901 apply /tmp/opencode/ucs-ui2-boot.patch
git -C .worktrees/ucs-ui2-integration-20260901 apply /tmp/opencode/ucs-ui2-boot-test.patch
```

Resolve only desktop conflicts. The resulting launcher must follow this exact handoff:

```python
boot_screen = _start_desktop_boot(root, tk)
try:
    _DesktopDashboard(
        root, tk, ttk, ctx,
        initial_message=initial_message,
        status_reader=status_reader,
        start_action=start_action,
        restart_action=restart_action,
        stop_action=stop_action,
        stop_confirmation=stop_confirmation,
        activity_reader=activity_reader,
        workspace_log_stream_reader=workspace_log_stream_reader,
    )
except Exception:
    boot_screen.close()
    root.destroy()
    raise
```

`_on_workspace_activity()` calls `self.activity_view.reveal_session(notification.chat_id)` only.

- [ ] **Step 4: Commit only composed desktop files**

```bash
git add app/cli/desktop_ui.py app/cli/desktop_views/boot.py app/cli/desktop_views/activity.py tests/test_cli_desktop_ui.py tests/test_desktop_boot.py tests/test_desktop_activity_view.py
git commit -m "feat: integrate UCS desktop UI 2.0"
```

Confirm `git show --name-only --format=` names no backend/MCP/API/lifecycle file.

### Task 2: Prove the boot-plus-Stop launcher contract

**Files:**

- Modify: `tests/test_cli_desktop_ui.py`
- Modify only if RED requires it: `app/cli/desktop_ui.py`

**Interfaces:**

- Consumes `run_desktop_ui(..., stop_action, stop_confirmation)` and `_start_desktop_boot(root, tk)`.
- Produces a regression test for dependency propagation and exception cleanup.

- [ ] **Step 1: Add a failing fake-Tk launcher test**

Use fake `Tk`, root, boot-screen, and dashboard spies. Assert:

```python
assert run_desktop_ui(ctx, stop_action=stop_action, stop_confirmation=stop_confirmation) == 0
assert captured["stop_action"] is stop_action
assert captured["stop_confirmation"] is stop_confirmation
assert boot_calls == [(root, fake_tk)]
assert root.mainloop_calls == 1
```

In a dashboard-error path, assert `boot.close()` and `root.destroy()` each occur exactly once before the `RuntimeError` propagates.

- [ ] **Step 2: Demonstrate RED**

```bash
env HOST_READ_SCOPE= HOST_WRITE_SCOPE= /home/undertaker/Downloads/bqa/botquanganh_mcp/.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'boot and stop' -q
```

Expected: failure until the launcher has both boot and Stop dependencies.

- [ ] **Step 3: Make the smallest UI-only launcher resolution and demonstrate GREEN**

Keep the exact Task 1 launcher code. Do not alter `boot.py`, lifecycle code, workers, or any backend path. Re-run the focused test and commit:

```bash
git add app/cli/desktop_ui.py tests/test_cli_desktop_ui.py
git commit -m "test: cover boot and stop desktop integration"
```

Do not create an empty commit.

### Task 3: Review, promote, verify, and push

**Files:** promote only File Scope.

**Interfaces:**

- Consumes a reviewed integration head and its green desktop suite.
- Produces verified UI 2.0 in the source checkout, then a push of `feature/vjp-pro` only if final verification is errorless.

- [ ] **Step 1: Independent review**

Review the integration diff from `fa3ea42` to integration head. Require no Critical/Important findings for boot/Stop propagation, cancel safety, non-focus activity, logo/rail/runtime/log/activity contracts, or prohibited paths.

- [ ] **Step 2: Safely promote the verified UI delta**

Capture a second desktop-only recovery patch under `/tmp/opencode/`. Apply the verified integration diff into the source checkout with `git apply --3way`. If a non-UI path appears or a desktop conflict cannot preserve both user boot behavior and UI 2.0, stop without push.

- [ ] **Step 3: Final source-checkout verification**

```bash
env HOST_READ_SCOPE= HOST_WRITE_SCOPE= /home/undertaker/Downloads/bqa/botquanganh_mcp/.venv/bin/python -m pytest tests/test_desktop_theme.py tests/test_desktop_i18n.py tests/test_desktop_runtime_view.py tests/test_desktop_workspace_logs_view.py tests/test_desktop_activity_view.py tests/test_desktop_boot.py tests/test_cli_desktop_ui.py -q
git diff --check
/home/undertaker/Downloads/bqa/botquanganh_mcp/.venv/bin/python -m compileall -q app/cli/desktop_ui.py app/cli/desktop_views
env HOST_READ_SCOPE= HOST_WRITE_SCOPE= /home/undertaker/Downloads/bqa/botquanganh_mcp/.venv/bin/python -m pytest tests -q
```

If a display is available, run `bqa ui` once and check boot handoff, compact logo header, rail, EN/VI, activity focus preservation, and Stop cancel/confirm. A failed full suite blocks push; do not repair non-UI source without new authorization.

- [ ] **Step 4: Commit and push only after all checks pass**

```bash
git add app/cli/desktop_ui.py app/cli/desktop_views/boot.py app/cli/desktop_views/activity.py app/cli/desktop_views/theme.py app/cli/desktop_views/i18n.py app/cli/desktop_views/runtime.py app/cli/desktop_views/workspace_logs.py tests/test_cli_desktop_ui.py tests/test_desktop_boot.py tests/test_desktop_activity_view.py tests/test_desktop_theme.py tests/test_desktop_i18n.py tests/test_desktop_runtime_view.py tests/test_desktop_workspace_logs_view.py docs/CLI_UI.md
git commit -m "feat: ship UCS desktop UI 2.0"
git push origin feature/vjp-pro
```

Do not stage or push `.env.example`, `README.md`, `app/activity_log.py`, any `app/host` path, server/MCP/API/lifecycle code, or unrelated tests.

## Plan Self-Review

- Coverage: tasks protect user work, compose boot and UI 2.0, test Stop safety, independently review, verify, and gate promotion/push.
- Completeness scan: every task includes exact paths, commands, assertions, and stop conditions.
- Interface consistency: `run_desktop_ui` passes `stop_action` and `stop_confirmation` into `_DesktopDashboard`; boot owns handoff; activity uses `reveal_session` only.
