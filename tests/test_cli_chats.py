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
