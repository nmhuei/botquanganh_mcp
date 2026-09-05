import json
import os
from datetime import datetime

import pytest

from app.cli.main import main
from app.cli.parser import build_parser


def _configure(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", root)
    monkeypatch.setattr("app.cli.output.terminal_width", lambda *_a, **_k: 100)
    monkeypatch.setenv("NO_COLOR", "1")
    return root


def _make_workspace(
    root,
    chat_id,
    *,
    archived=False,
    created="2026-01-02T03:04:05+00:00",
    journal_lines=(),
    state_md=None,
    mtime=None,
    with_meta=True,
):
    base = root / ".archive" if archived else root
    ws = base / chat_id
    (ws / "notes").mkdir(parents=True, exist_ok=True)
    if with_meta:
        meta = {
            "chat_id": chat_id,
            "created_at": created,
            "schema": 1,
        }
        (ws / "meta.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")
    if journal_lines:
        (ws / "journal.jsonl").write_text(
            "\n".join(journal_lines) + "\n", encoding="utf-8"
        )
    if state_md is not None:
        (ws / "STATE.md").write_text(state_md, encoding="utf-8")
    if mtime is not None:
        for path in [ws, *ws.rglob("*")]:
            os.utime(path, (mtime, mtime))
    return ws


def _journal_line(seq, op, event_type):
    return json.dumps({"seq": seq, "op": op, "type": event_type})


def test_bare_chats_parses_as_alias_of_list():
    args = build_parser().parse_args(["chats"])
    assert args.command == "chats"
    assert args.chats_command is None
    assert build_parser().parse_args(["chats", "list"]).chats_command == "list"
    show = build_parser().parse_args(["chats", "show", "abc123"])
    assert show.chats_command == "show"
    assert show.chat_id == "abc123"


def test_missing_root_human_message_exits_zero(monkeypatch, tmp_path, capsys):
    _configure(monkeypatch, tmp_path)
    assert main(["chats"]) == 0
    assert "No chat workspace storage found yet." in capsys.readouterr().out


def test_empty_root_human_message_exits_zero(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    root.mkdir()
    assert main(["chats"]) == 0
    assert f"No chat workspaces under {root} yet." in capsys.readouterr().out


def test_empty_root_json_and_quiet_shapes(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    root.mkdir()
    assert main(["chats", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert main(["chats", "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_list_orders_by_last_activity_descending(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    _make_workspace(root, "beta-old", mtime=1_000_000_000)
    _make_workspace(root, "alpha-new", mtime=1_700_000_000)
    assert main(["chats"]) == 0
    out = capsys.readouterr().out
    assert "CHAT_ID" in out and "FILES" in out and "LAST-ACTIVE" in out
    assert out.index("alpha-new") < out.index("beta-old")


def test_list_marks_archived_and_missing_meta_states(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    _make_workspace(root, "active-one")
    _make_workspace(root, "archived-one", archived=True)
    _make_workspace(root, "metaless", with_meta=False)
    assert main(["chats", "--json"]) == 0
    entries = {item["chat_id"]: item for item in json.loads(capsys.readouterr().out)}
    assert entries["active-one"]["state"] == "active"
    assert entries["archived-one"]["state"] == "archived"
    assert entries["metaless"]["state"] == "missing-meta"


def test_quiet_lists_ids_one_per_line(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    _make_workspace(root, "older-ws", mtime=1_000_000_000)
    _make_workspace(root, "newer-ws", mtime=1_700_000_000)
    assert main(["chats", "--quiet"]) == 0
    assert capsys.readouterr().out == "newer-ws\nolder-ws\n"


def test_json_entries_use_iso_timestamps_and_byte_sizes(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(root, "shape-ok", journal_lines=["not json at all"])
    assert main(["chats", "--json"]) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert set(entry) == {
        "chat_id",
        "files",
        "created",
        "last_active",
        "state",
    }
    datetime.fromisoformat(entry["created"])
    datetime.fromisoformat(entry["last_active"])
    assert entry["files"] == sum(
        p.stat().st_size for p in ws.rglob("*") if p.is_file()
    )


def test_show_happy_path_counts_journal(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(
        root,
        "journal-1",
        journal_lines=[
            _journal_line(1, "op-a", "op_started"),
            _journal_line(2, "op-b", "op_started"),
            _journal_line(3, "op-c", "op_started"),
            _journal_line(4, "op-a", "op_result"),
            "{broken json",
            _journal_line(5, "op-b", "op_result"),
        ],
        state_md="# State\n\n- step one\n- step two\n",
    )
    assert main(["chats", "show", "journal-1"]) == 0
    out = capsys.readouterr().out
    assert str(ws) in out
    assert "- step two" in out
    assert "3 started" in out
    assert "2 completed" in out


def test_show_caps_state_md_head_at_40_lines(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    body = "\n".join(f"- item {index}" for index in range(50)) + "\n"
    _make_workspace(root, "long-state", state_md=body)
    assert main(["chats", "show", "long-state"]) == 0
    out = capsys.readouterr().out
    assert "- item 0" in out
    assert "- item 39" in out
    assert "- item 40" not in out


def test_show_json_shape(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(
        root,
        "json-show",
        journal_lines=[
            _journal_line(1, "op-a", "op_started"),
            _journal_line(2, "op-a", "op_result"),
            _journal_line(3, "op-b", "op_started"),
        ],
        state_md="# State\n- only line\n",
    )
    assert main(["chats", "show", "json-show", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"path", "state_md_head", "journal"}
    assert payload["path"] == str(ws)
    assert payload["path"].startswith(str(root))
    assert payload["state_md_head"] == ["# State", "- only line"]
    assert payload["journal"] == {"started": 2, "completed": 1}


def test_show_prints_absolute_path_in_quiet_mode(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(root, "quiet-show")
    assert main(["chats", "show", "quiet-show", "--quiet"]) == 0
    assert capsys.readouterr().out.strip() == str(ws)


def test_show_finds_archived_workspace(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(root, "archived-1", archived=True)
    assert main(["chats", "show", "archived-1", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == str(ws)
    assert ".archive" in payload["path"]


def test_show_rejects_invalid_chat_id(monkeypatch, tmp_path, capsys):
    _configure(monkeypatch, tmp_path)
    for bad in ("no", "../escape", "has space!!"):
        code = main(["chats", "show", bad])
        assert code == 2, bad
        assert "Chat ids use 6-64 characters" in capsys.readouterr().err


def test_show_unknown_chat_id_exits_nonzero(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    root.mkdir()
    _make_workspace(root, "present-1")
    assert main(["chats", "show", "absent-id"]) == 6
    assert "No chat workspace found for 'absent-id'." in capsys.readouterr().err


def test_show_without_any_root_still_reports_not_found(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    assert main(["chats", "show", "absent-id"]) == 6


@pytest.mark.parametrize("command", ["chats", "status", "health", "logs"])
def test_top_level_help_still_lists_inspection_commands(command):
    assert command in build_parser().format_help()


def test_workspace_management_subcommands_parse():
    parser = build_parser()
    assert parser.parse_args(["chats", "archive", "abc123"]).chats_command == "archive"
    assert parser.parse_args(["chats", "restore", "abc123"]).chats_command == "restore"
    logs = parser.parse_args(
        ["chats", "logs", "abc123", "--severity", "error", "--category", "process", "--limit", "25"]
    )
    assert logs.chats_command == "logs"
    assert (logs.severity, logs.category, logs.limit) == ("error", "process", 25)
    deleted = parser.parse_args(["chats", "delete", "abc123", "--yes"])
    assert deleted.chats_command == "delete" and deleted.yes is True
    pruned = parser.parse_args(["chats", "prune", "--apply"])
    assert pruned.chats_command == "prune" and pruned.apply is True
    assert parser.parse_args(["chats", "stats"]).chats_command == "stats"


def test_archive_then_restore_workspace(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    source = _make_workspace(root, "manage-1", state_md="# State\n")

    assert main(["chats", "archive", "manage-1", "--json"]) == 0
    archived_result = json.loads(capsys.readouterr().out)
    archived = root / ".archive" / "manage-1"
    assert archived_result["status"] == "archived"
    assert not source.exists()
    assert archived.is_dir()

    assert main(["chats", "restore", "manage-1", "--json"]) == 0
    restored_result = json.loads(capsys.readouterr().out)
    assert restored_result["status"] == "restored"
    assert source.is_dir()
    assert not archived.exists()


def test_delete_requires_confirmation_and_only_deletes_archived(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    active = _make_workspace(root, "delete-active")
    archived = _make_workspace(root, "delete-old", archived=True)

    assert main(["chats", "delete", "delete-old"]) == 2
    assert "requires --yes" in capsys.readouterr().err
    assert archived.exists()

    assert main(["chats", "delete", "delete-active", "--yes"]) == 6
    assert "No archived workspace found" in capsys.readouterr().err
    assert active.exists()

    assert main(["chats", "delete", "delete-old", "--yes", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "deleted"
    assert not archived.exists()
    assert active.exists()


def test_stats_reports_counts_and_total_bytes(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    active = _make_workspace(root, "stats-active")
    archived = _make_workspace(root, "stats-archived", archived=True)
    (active / "payload.bin").write_bytes(b"abc")
    (archived / "payload.bin").write_bytes(b"12345")

    expected_bytes = sum(
        path.stat().st_size
        for workspace in (active, archived)
        for path in workspace.rglob("*")
        if path.is_file()
    )
    assert main(["chats", "stats", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "active": 1,
        "archived": 1,
        "total": 2,
        "bytes": expected_bytes,
        "root": str(root),
    }


def test_prune_defaults_to_dry_run_and_apply_mutates(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    workspace = _make_workspace(root, "idle-prune", mtime=1_000_000_000)
    monkeypatch.setattr("app.config.HOST_CHAT_IDLE_ARCHIVE_HOURS", 0)
    monkeypatch.setattr("app.config.HOST_CHAT_RETENTION_DAYS", 999999)
    monkeypatch.setattr("app.config.HOST_CHAT_MAX_WORKSPACES", 128)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT_MAX_GB", 24)

    assert main(["chats", "prune", "--json"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["apply"] is False
    assert dry["planned"][0]["action"] == "ARCHIVE_IDLE"
    assert dry["results"][0]["status"] == "would_archive"
    assert workspace.is_dir()

    assert main(["chats", "prune", "--apply", "--json"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["apply"] is True
    assert applied["results"][0]["status"] == "archived"
    assert not workspace.exists()
    assert (root / ".archive" / "idle-prune").is_dir()


def test_logs_view_normalizes_filters_and_redacts_rotated_records(
    monkeypatch, tmp_path, capsys
):
    root = _configure(monkeypatch, tmp_path)
    current = json.dumps(
        {
            "seq": 2,
            "ts": "2026-08-26T17:00:01+00:00",
            "type": "op_result",
            "op": "op-log1",
            "ok": False,
            "payload": {"command": "--token current-secret echo failed"},
        }
    )
    ws = _make_workspace(root, "logs-view", journal_lines=[current])
    previous = json.dumps(
        {
            "seq": 1,
            "ts": "2026-08-26T17:00:00+00:00",
            "type": "op_started",
            "op": "op-log1",
            "kind": "host_run_command",
            "payload": {"command": "GATEWAY_TOKEN=old-secret echo start"},
        }
    )
    (ws / "journal.jsonl.1").write_text(previous + "\n", encoding="utf-8")

    assert main(["chats", "logs", "logs-view", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 2
    assert payload["summary"]["categories"] == {"process": 2}
    assert payload["summary"]["severities"] == {"DEBUG": 1, "ERROR": 1}
    assert [record["severity_text"] for record in payload["records"]] == [
        "DEBUG",
        "ERROR",
    ]
    serialized = json.dumps(payload)
    assert "old-secret" not in serialized
    assert "current-secret" not in serialized
    assert serialized.count("command_sha256") == 2
    assert serialized.count('"command": "<redacted>"') == 2

    assert main(
        ["chats", "logs", "logs-view", "--severity", "error", "--json"]
    ) == 0
    filtered = json.loads(capsys.readouterr().out)
    assert filtered["count"] == 1
    assert filtered["records"][0]["event_outcome"] == "failure"

    assert main(
        ["chats", "logs", "logs-view", "--category", "file", "--json"]
    ) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0


def test_show_counts_rotated_and_current_journal_generations(monkeypatch, tmp_path, capsys):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(
        root,
        "logs-count",
        journal_lines=[
            json.dumps(
                {
                    "seq": 2,
                    "ts": "2026-08-26T17:00:01+00:00",
                    "type": "op_result",
                    "op": "op-log2",
                    "kind": "host_read_file",
                    "ok": True,
                    "payload": {},
                }
            )
        ],
    )
    (ws / "journal.jsonl.1").write_text(
        json.dumps(
            {
                "seq": 1,
                "ts": "2026-08-26T17:00:00+00:00",
                "type": "op_started",
                "op": "op-log2",
                "kind": "host_read_file",
                "payload": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert main(["chats", "show", "logs-count"]) == 0
    out = capsys.readouterr().out
    assert "1 started" in out
    assert "1 completed" in out


def test_logs_view_supports_min_severity_outcome_action_and_phase_filters(
    monkeypatch, tmp_path, capsys
):
    root = _configure(monkeypatch, tmp_path)
    ws = _make_workspace(
        root,
        "logs-filter",
        journal_lines=[
            json.dumps(
                {
                    "seq": 1,
                    "ts": "2026-08-26T17:00:00+00:00",
                    "type": "op_started",
                    "op": "op-file",
                    "kind": "host_read_file",
                    "payload": {"path": "README.md"},
                }
            ),
            json.dumps(
                {
                    "seq": 2,
                    "ts": "2026-08-26T17:00:00.250000+00:00",
                    "type": "op_result",
                    "op": "op-file",
                    "ok": True,
                    "payload": {"path": "README.md"},
                }
            ),
            json.dumps(
                {
                    "seq": 3,
                    "ts": "2026-08-26T17:00:01+00:00",
                    "type": "op_started",
                    "op": "op-cmd",
                    "kind": "host_run_command",
                    "payload": {"cwd": "/tmp"},
                }
            ),
            json.dumps(
                {
                    "seq": 4,
                    "ts": "2026-08-26T17:00:02+00:00",
                    "type": "op_result",
                    "op": "op-cmd",
                    "ok": False,
                    "payload": {"exit_code": 2},
                }
            ),
        ],
    )
    assert ws.is_dir()

    assert main(["chats", "logs", "logs-filter", "--min-severity", "error", "--json"]) == 0
    errors = json.loads(capsys.readouterr().out)
    assert errors["count"] == 1
    assert errors["records"][0]["event_action"] == "host_run_command"
    assert errors["records"][0]["event_duration_ms"] == 1000.0

    assert main(["chats", "logs", "logs-filter", "--outcome", "failure", "--json"]) == 0
    failures = json.loads(capsys.readouterr().out)
    assert failures["count"] == 1
    assert failures["records"][0]["seq"] == 4

    assert main(["chats", "logs", "logs-filter", "--action", "host_read_file", "--phase", "result", "--json"]) == 0
    file_results = json.loads(capsys.readouterr().out)
    assert file_results["count"] == 1
    assert file_results["records"][0]["event_category"] == "file"
    assert file_results["records"][0]["event_duration_ms"] == 250.0
