from concurrent.futures import ThreadPoolExecutor

import app.ratelimit as ratelimit


def test_rate_limiter_enforces_limit_under_concurrency(monkeypatch):
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_ENABLED", True)
    limiter = ratelimit.SlidingWindowRateLimiter()
    limiter.max_requests = 10
    limiter.window_seconds = 60

    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(lambda _index: limiter.is_allowed("same-client"), range(100)))

    assert sum(1 for allowed, _retry in results if allowed) == 10
    assert sum(1 for allowed, _retry in results if not allowed) == 90
    assert all(retry >= 1 for allowed, retry in results if not allowed)


def test_rate_limiter_uses_monotonic_clock(monkeypatch):
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(
        ratelimit.time,
        "time",
        lambda: (_ for _ in ()).throw(AssertionError("wall clock must not be used")),
    )
    limiter = ratelimit.SlidingWindowRateLimiter()
    limiter.max_requests = 1
    limiter.window_seconds = 60

    assert limiter.is_allowed("client")[0] is True
    assert limiter.is_allowed("client")[0] is False
