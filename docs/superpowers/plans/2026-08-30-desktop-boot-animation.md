# Desktop Boot Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a short, non-blocking terminal-inspired UCS startup animation before the native dashboard appears.

**Architecture:** `BootSequence` owns phase scheduling and can run on a fake scheduler. `DesktopBootScreen` owns the `Toplevel` and Canvas drawing, delegates timing to the sequence, then deiconifies the already-built root when the final phase completes. `run_desktop_ui()` wires the splash into the existing root lifecycle.

**Tech Stack:** Python 3, Tkinter Canvas/Toplevel, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-desktop-boot-animation-design.md`

## Global Constraints

- Use no bitmap assets, external GUI toolkit, sleep, worker thread, focus call, lift call, or topmost window attribute.
- Show `INITIALIZING INTERFACE`, `LOADING WORKSPACES`, `CONNECTING ACTIVITY STREAM`, and `READY` in that order.
- Use 750 ms between phases and 750 ms after the ready phase.
- Retain all existing dashboard close, refresh, and activity-session behavior.

---

### Task 1: Testable boot sequence controller

**Files:**

- Create: `app/cli/desktop_views/boot.py`
- Test: `tests/test_desktop_boot.py`

**Interfaces:**

- Produces `BOOT_PHASES: tuple[str, ...]` and `BootSequence(schedule, cancel, on_phase, on_ready)`.
- `BootSequence.start() -> None` emits the first phase immediately; `BootSequence.cancel() -> None` prevents a future ready callback.

- [x] **Step 1: Write the failing sequence-order test**

```python
def test_boot_sequence_emits_each_phase_then_ready_once():
    scheduled, phases, ready = [], [], []
    sequence = BootSequence(
        lambda delay, callback: scheduled.append((delay, callback)) or len(scheduled),
        lambda _job: None,
        phases.append,
        lambda: ready.append(True),
    )
    sequence.start()
    while scheduled:
        _, callback = scheduled.pop(0)
        callback()
    assert phases == list(BOOT_PHASES)
    assert ready == [True]
```

- [x] **Step 2: Run the focused test to verify red**

Run: `.venv/bin/python -m pytest tests/test_desktop_boot.py -q`

Expected: FAIL because `app.cli.desktop_views.boot` does not exist.

- [x] **Step 3: Write the minimal sequence controller**

```python
BOOT_PHASES = (
    "INITIALIZING INTERFACE",
    "LOADING WORKSPACES",
    "CONNECTING ACTIVITY STREAM",
    "READY",
)

class BootSequence:
    def start(self) -> None: ...
    def cancel(self) -> None: ...
```

The first phase is immediate, the first three callback schedules use 750 ms,
and the last callback schedules ready in 750 ms.

- [x] **Step 4: Re-run green and add cancellation coverage**

```python
def test_boot_sequence_cancel_prevents_pending_ready_callback():
    # Start, advance to READY, cancel, then invoke the saved callback.
    # The ready list remains empty.
```

Run: `.venv/bin/python -m pytest tests/test_desktop_boot.py -q`

### Task 2: Canvas splash and launcher lifecycle

**Files:**

- Modify: `app/cli/desktop_views/boot.py`
- Modify: `app/cli/desktop_ui.py:682-704`
- Test: `tests/test_desktop_boot.py`

**Interfaces:**

- Consumes `BootSequence` and `BOOT_PHASES` from Task 1.
- Produces `DesktopBootScreen(root, tk, on_ready)` with `start()` and `close()`.

- [x] **Step 1: Write the failing fake-scheduler rendering test**

```python
def test_boot_screen_destroys_splash_then_reveals_dashboard_once():
    screen = DesktopBootScreen(fake_root, fake_tk, on_ready=fake_root.deiconify)
    screen.start()
    fake_root.run_all_after_callbacks()
    assert fake_window.destroyed is True
    assert fake_root.calls == ["deiconify"]
```

The test double must provide the same `Toplevel` and `Canvas` methods used by
the screen; it must not assert internal drawing coordinates.

- [x] **Step 2: Run the focused test to verify red**

Run: `.venv/bin/python -m pytest tests/test_desktop_boot.py -q`

Expected: FAIL because `DesktopBootScreen` is absent.

- [x] **Step 3: Implement the splash and wire it before `mainloop()`**

Build the dark Canvas with procedural UCS lettering, scan lines, phase text,
and four progress cells. In `run_desktop_ui()`, call `root.withdraw()`, build
`_DesktopDashboard`, create/start the splash, and pass `root.deiconify` as its
ready callback. On dashboard-construction error, destroy the root and re-raise.

- [x] **Step 4: Run all desktop UI tests**

Run: `.venv/bin/python -m pytest tests/test_desktop_boot.py tests/test_cli_desktop_ui.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py -q`

- [ ] **Step 5: Manually inspect after a controlled UI restart**

Run: `bqa ui`

Expected: one ~3 s splash followed by the normal dashboard; no window is
raised by activity refreshes or SSE events.
