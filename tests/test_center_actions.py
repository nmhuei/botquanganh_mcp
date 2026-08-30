import threading
import time

from app.cli.center.actions import ActionController, ActionSpec
from app.cli.center.events import ActionFinished


def test_action_controller_rejects_second_action_in_same_group():
    events = []
    release = threading.Event()
    controller = ActionController(events.append)

    first = controller.request(
        ActionSpec(
            kind="one",
            group="runtime_mutation",
            work=lambda: release.wait(timeout=1) or {"ok": True},
        )
    )
    second = controller.request(
        ActionSpec(
            kind="two",
            group="runtime_mutation",
            work=lambda: {"ok": True},
        )
    )

    assert first
    assert second is None
    release.set()


def test_action_controller_delivers_terminal_event():
    events = []
    done = threading.Event()

    def emit(event):
        events.append(event)
        if isinstance(event, ActionFinished):
            done.set()

    controller = ActionController(emit)
    action_id = controller.request(
        ActionSpec(
            kind="read",
            group="read",
            work=lambda: {"ok": True, "message": "done"},
        )
    )

    assert action_id
    assert done.wait(timeout=1)
    terminal = next(event for event in events if isinstance(event, ActionFinished))
    assert terminal.ok is True
    assert terminal.message == "done"
    assert terminal.elapsed_seconds >= 0


def test_action_controller_clears_group_after_failure():
    done = threading.Event()

    def emit(event):
        if isinstance(event, ActionFinished):
            done.set()

    controller = ActionController(emit)

    def fail():
        raise RuntimeError("boom")

    assert controller.request(ActionSpec("bad", "runtime_mutation", fail))
    assert done.wait(timeout=1)
    deadline = time.monotonic() + 1
    while controller.running("runtime_mutation") and time.monotonic() < deadline:
        time.sleep(0.001)
    assert controller.running("runtime_mutation") is False
