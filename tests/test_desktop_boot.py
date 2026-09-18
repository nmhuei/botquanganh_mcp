from app.cli.desktop_ui import _start_desktop_boot
from app.cli.desktop_views.boot import BOOT_PHASES, BootSequence, DesktopBootScreen


class _Scheduler:
    def __init__(self):
        self.jobs = {}
        self.cancelled = []
        self.delays = []
        self.next_job_id = 1

    def after(self, delay, callback):
        self.delays.append(delay)
        job_id = self.next_job_id
        self.next_job_id += 1
        self.jobs[job_id] = (delay, callback)
        return job_id

    def after_cancel(self, job_id):
        self.cancelled.append(job_id)
        self.jobs.pop(job_id, None)

    def run_next(self):
        job_id = min(self.jobs)
        _delay, callback = self.jobs.pop(job_id)
        callback()


def test_boot_sequence_emits_each_phase_then_ready_once():
    scheduler = _Scheduler()
    phases = []
    ready = []
    sequence = BootSequence(
        scheduler.after,
        scheduler.after_cancel,
        phases.append,
        lambda: ready.append(True),
    )

    sequence.start()
    while scheduler.jobs:
        scheduler.run_next()

    assert phases == list(BOOT_PHASES)
    assert ready == [True]
    assert scheduler.delays == [750, 750, 750, 750]


def test_boot_sequence_cancel_prevents_pending_ready_callback():
    scheduler = _Scheduler()
    ready = []
    sequence = BootSequence(
        scheduler.after,
        scheduler.after_cancel,
        lambda _phase: None,
        lambda: ready.append(True),
    )

    sequence.start()
    scheduler.run_next()
    scheduler.run_next()
    scheduler.run_next()
    _ready_delay, pending_ready = next(iter(scheduler.jobs.values()))
    sequence.cancel()
    pending_ready()

    assert ready == []
    assert scheduler.cancelled == [4]


class _BootWindow:
    def __init__(self, _root):
        self.destroyed = False

    def configure(self, **_kwargs):
        pass

    def overrideredirect(self, _enabled):
        pass

    def resizable(self, _width, _height):
        pass

    def geometry(self, _value):
        pass

    def winfo_screenwidth(self):
        return 1440

    def winfo_screenheight(self):
        return 900

    def destroy(self):
        self.destroyed = True


class _Canvas:
    def __init__(self, parent, **_kwargs):
        self.parent = parent
        self.next_item = 1

    def pack(self, **_kwargs):
        pass

    def create_rectangle(self, *_args, **_kwargs):
        item = self.next_item
        self.next_item += 1
        return item

    def create_line(self, *_args, **_kwargs):
        item = self.next_item
        self.next_item += 1
        return item

    def create_text(self, *_args, **_kwargs):
        item = self.next_item
        self.next_item += 1
        return item

    def itemconfigure(self, _item, **_kwargs):
        pass


class _BootTk:
    def __init__(self):
        self.window = None

    def Toplevel(self, root):
        self.window = _BootWindow(root)
        return self.window

    Canvas = _Canvas


class _BootRoot(_Scheduler):
    def __init__(self):
        super().__init__()
        self.calls = []

    def deiconify(self):
        self.calls.append("deiconify")

    def withdraw(self):
        self.calls.append("withdraw")


def test_boot_screen_destroys_splash_then_reveals_dashboard_once():
    root = _BootRoot()
    tk = _BootTk()
    screen = DesktopBootScreen(root, tk, on_ready=root.deiconify)

    screen.start()
    while root.jobs:
        root.run_next()

    assert tk.window.destroyed is True
    assert root.calls == ["deiconify"]


def test_desktop_boot_hides_root_until_splash_finishes():
    root = _BootRoot()
    tk = _BootTk()

    _start_desktop_boot(root, tk)
    assert root.calls == ["withdraw"]
    while root.jobs:
        root.run_next()

    assert root.calls == ["withdraw", "deiconify"]
