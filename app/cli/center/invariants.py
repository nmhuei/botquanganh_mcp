"""Safety invariants for BQA Center runtime actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TunnelSnapshot:
    pid: int | None
    url: str


@dataclass(frozen=True)
class TunnelInvariantResult:
    ok: bool
    before: TunnelSnapshot
    after: TunnelSnapshot
    error: str = ""


def tunnel_snapshot(status: dict[str, Any]) -> TunnelSnapshot:
    tunnel = status.get("tunnel") or {}
    return TunnelSnapshot(
        pid=tunnel.get("pid"),
        url=str(status.get("url") or status.get("last_known_url") or ""),
    )


def check_tunnel_invariant(
    before_status: dict[str, Any],
    after_status: dict[str, Any],
) -> TunnelInvariantResult:
    before = tunnel_snapshot(before_status)
    after = tunnel_snapshot(after_status)
    errors: list[str] = []
    if before.pid != after.pid:
        errors.append(f"tunnel pid changed: {before.pid} -> {after.pid}")
    if before.url != after.url:
        errors.append("connector URL changed")
    return TunnelInvariantResult(
        ok=not errors,
        before=before,
        after=after,
        error="; ".join(errors),
    )
