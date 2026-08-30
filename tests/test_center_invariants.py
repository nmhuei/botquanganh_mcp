from app.cli.center.invariants import check_tunnel_invariant


def status(pid, url):
    return {"tunnel": {"pid": pid, "running": True}, "url": url}


def test_tunnel_invariant_accepts_same_pid_and_url():
    result = check_tunnel_invariant(status(1, "u"), status(1, "u"))
    assert result.ok is True


def test_tunnel_invariant_rejects_pid_or_url_change():
    result = check_tunnel_invariant(status(1, "u"), status(2, "v"))
    assert result.ok is False
    assert "pid changed" in result.error
    assert "URL changed" in result.error
