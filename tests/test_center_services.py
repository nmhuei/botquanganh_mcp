from __future__ import annotations

import json
import os
from pathlib import Path
import time

from app.cli.center.services import (
    archive_workspace,
    attention_items,
    delete_archived_workspace,
    overall_health,
    restore_workspace,
    runtime_log_rows,
    security_posture,
    workspace_inventory,
    workspace_prune,
    workspace_summary,
)


def _workspace(root: Path, chat_id: str) -> Path:
    path = root / chat_id
    path.mkdir(parents=True)
    (path / "meta.json").write_text(
        json.dumps({"created_at": "2026-08-30T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (path / "STATE.md").write_text("# state\n", encoding="utf-8")
    return path


def test_workspace_lifecycle_services_archive_restore_and_delete(tmp_path):
    root = tmp_path / "chats"
    root.mkdir()
    chat_id = "chat123"
    _workspace(root, chat_id)

    rows = workspace_inventory(root)
    assert len(rows) == 1
    assert rows[0]["chatId"] == chat_id
    assert rows[0]["workspaceState"] == "active"

    archived = archive_workspace(root, chat_id)
    assert archived["status"] == "archived"
    assert not (root / chat_id).exists()
    assert (root / ".archive" / chat_id).is_dir()

    restored = restore_workspace(root, chat_id)
    assert restored["status"] == "restored"
    assert (root / chat_id).is_dir()

    archive_workspace(root, chat_id)
    deleted = delete_archived_workspace(root, chat_id)
    assert deleted["status"] == "deleted"
    assert not (root / ".archive" / chat_id).exists()


def test_workspace_summary_and_prune_preview_do_not_mutate(tmp_path):
    root = tmp_path / "chats"
    root.mkdir()
    path = _workspace(root, "chat456")
    old = time.time() - 48 * 3600
    os.utime(path, (old, old))
    for child in path.iterdir():
        os.utime(child, (old, old))

    rows = workspace_inventory(root)
    summary = workspace_summary(rows)
    assert summary["active"] == 1
    assert summary["archived"] == 0
    assert summary["bytes"] > 0

    report = workspace_prune(
        root,
        {
            "HOST_CHAT_IDLE_ARCHIVE_HOURS": "1",
            "HOST_CHAT_RETENTION_DAYS": "30",
            "HOST_CHAT_MAX_WORKSPACES": "128",
            "HOST_CHAT_ROOT_MAX_GB": "24",
        },
        apply=False,
    )
    assert report["apply"] is False
    assert any(result["status"] == "would_archive" for result in report["results"])
    assert (root / "chat456").is_dir()
    assert not (root / ".archive").exists()


def test_security_posture_never_exposes_gateway_token():
    secret = "super-secret-token"
    rows = security_posture(
        {
            "REQUIRE_AUTH": "true",
            "GATEWAY_TOKEN": secret,
            "HOST_RESTRICT_TO_WORKSPACE": "true",
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ISOLATE": "true",
            "HOST_COMMAND_POLICY": "guarded",
            "ATTRIBUTION_MODE": "enforce",
        }
    )
    rendered = json.dumps(rows)
    assert secret not in rendered
    auth = next(row for row in rows if row["itemId"] == "auth")
    assert auth["value"] == "Enabled"
    assert auth["tone"] == "success"


def test_overall_health_and_attention_distinguish_stale_public_connector():
    runtime = {
        "server": {"running": True},
        "tunnel": {"running": True},
        "bridge": "ready",
        "connector_ready": False,
        "url_state": "stale",
        "auth_required": True,
    }
    health = {
        "metrics": {
            "error_count": 0,
            "auth_failures": 0,
            "rate_limit_hits": 0,
        }
    }
    overall = overall_health(runtime, health, "live", [])
    assert overall["state"] == "stale_data"

    items = attention_items(runtime, health, "live", [])
    stale = next(row for row in items if row["itemId"] == "connector-stale")
    assert stale["severity"] == "warning"
    assert "stale" in stale["title"].lower()


def test_overall_health_security_warning_for_public_unauthenticated_connector():
    runtime = {
        "server": {"running": True},
        "tunnel": {"running": True},
        "bridge": "ready",
        "connector_ready": True,
        "url_state": "active",
        "auth_required": False,
    }
    overall = overall_health(runtime, {"metrics": {}}, "live", [])
    assert overall["state"] == "security_warning"

    items = attention_items(runtime, {"metrics": {}}, "live", [])
    assert any(row["itemId"] == "public-auth-disabled" for row in items)


def test_runtime_log_rows_are_bounded_searchable_and_source_scoped(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    server = log_dir / "server.log"
    server.write_text(
        "\n".join(
            [
                "2026-08-30 10:00:00 server ready",
                "2026-08-30 10:00:01 request ok",
                "2026-08-30 10:00:02 warning degraded",
                "2026-08-30 10:00:03 request recovered",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (log_dir / "cloudflared.log").write_text(
        "2026-08-30 10:00:00 tunnel ready\n",
        encoding="utf-8",
    )

    rows = runtime_log_rows(tmp_path, source="server", lines=2)
    assert len(rows) == 2
    assert all(row["source"] == "server" for row in rows)
    assert rows[-1]["line"].endswith("request recovered")

    warning = runtime_log_rows(tmp_path, source="server", lines=20, query="warning")
    assert len(warning) == 1
    assert "warning degraded" in warning[0]["line"]
