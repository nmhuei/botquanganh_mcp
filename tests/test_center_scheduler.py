from app.cli.center.scheduler import TkRenderScheduler


class Root:
    def __init__(self):
        self.idle = []
        self.timed = []

    def after_idle(self, callback):
        self.idle.append(callback)

    def after(self, delay, callback):
        self.timed.append((delay, callback))


def test_scheduler_coalesces_requests_and_uses_idle_for_small_queue():
    root = Root()
    calls = []
    scheduler = TkRenderScheduler(
        root,
        drain=lambda _limit: calls.append("drain") or 0,
        render=lambda: calls.append("render"),
    )

    scheduler.request(2)
    scheduler.request(2)

    assert len(root.idle) == 1
    root.idle.pop()()
    assert calls == ["drain", "render"]


def test_scheduler_uses_timed_tick_for_large_queue():
    root = Root()
    scheduler = TkRenderScheduler(root, drain=lambda _limit: 0, render=lambda: None)
    scheduler.request(500)
    assert root.timed and root.timed[0][0] == 1
