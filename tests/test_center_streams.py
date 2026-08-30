from app.cli.center.streams import ReconnectBackoff


def test_reconnect_backoff_caps_and_resets():
    backoff = ReconnectBackoff(jitter_ratio=0, maximum_seconds=4)
    assert [backoff.next_delay() for _ in range(5)] == [0.5, 1.0, 2.0, 4, 4]
    backoff.reset()
    assert backoff.next_delay() == 0.5
