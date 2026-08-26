#!/usr/bin/env python3
"""One-command E2E demo of per-chat workspaces (handshake -> journal ->
resurrection -> quota/E-codes -> sweeper -> live services -> cleanup).

Self-contained: runs against a throwaway temp root, never the real
HOST_CHAT_ROOT, never mutates production state. Read-only GETs against the
local runtime (127.0.0.1:18427) are best-effort; if unreachable the section
prints SKIP and the demo still exits 0.

Usage: .venv/bin/python scripts/demo_chat_workspaces.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import app.chat_workspace as cw  # noqa: E402
from app.chat_errors import ChatCatalogError, to_tool_error  # noqa: E402
from app.chat_errors import validate_chat_id as catalog_validate_chat_id  # noqa: E402
from app.chat_sweeper import SweepLimits, apply_actions, plan_actions, scan  # noqa: E402

BASE_URL = "http://127.0.0.1:18427"
FAILURES: list[str] = []


def banner(text: str) -> None:
    print(f"\n=== {text} ===")


def section(name: str, fn) -> None:
    banner(name)
    try:
        fn()
    except Exception as exc:  # unexpected -> FAIL marker, demo keeps going
        FAILURES.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"FAIL [{name}] {type(exc).__name__}: {exc}")


def envelope(exc: BaseException) -> str:
    payload = to_tool_error(exc)
    err = payload["error"]
    return f"{err['code']}/{err['name']}: {err['message'][:96]}"


def get_json(path: str, timeout: float = 2.0):
    with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main() -> int:
    t0 = time.time()
    ctx: dict = {}

    def setup() -> None:
        root = Path(tempfile.mkdtemp(prefix="bqa-demo-ws-"))
        ctx["root"] = root
        old_hint = cw.app.config.HOST_CHAT_RESUME_HINT_MINUTES
        cw.app.config.HOST_CHAT_RESUME_HINT_MINUTES = 30  # deterministic hint
        ctx["old_hint"] = old_hint
        mgr = cw.WorkspaceManager(root)
        ctx["mgr"] = mgr
        for chat_id in ("demo-chat-0001", "ctf-session-42"):
            r = mgr.create_or_bind(chat_id)
            print(f"create_or_bind({chat_id}) -> created={r.created} path={r.path}")
        again = mgr.create_or_bind("demo-chat-0001")
        print(f"re-bind(demo-chat-0001): created={again.created} resumed_hint={again.resumed_hint!r}")

    def journal() -> None:
        mgr, ws = ctx["mgr"], ctx["root"] / "demo-chat-0001"
        mgr.append_op_result("demo-chat-0001", "op-fs-1", True,
                             {"kind": "fs_write", "path": "notes/a.txt"})
        mgr.append_op_started("demo-chat-0001", "op-cmd-1", "cmd_run", {"cmd": "false"})
        mgr.append_op_result("demo-chat-0001", "op-cmd-1", False, {"exit_code": 1})
        mgr.append_op_started("demo-chat-0001", "op-hang-1", "fs_write", {"path": "notes/b.txt"})
        print(f"events={len(mgr.read_events('demo-chat-0001'))} "
              f"pending={[p['op'] for p in mgr.pending_ops('demo-chat-0001')]}")
        journal_path = ws / cw.JOURNAL_NAME
        size_before = journal_path.stat().st_size
        with journal_path.open("ab") as fh:  # crash mid-write: torn line, no \n
            fh.write(b'{"seq":999,"type":"op_started","op":"torn-garbage"')
        fresh = cw.WorkspaceManager(ctx["root"])
        pending_after = [p["op"] for p in fresh.pending_ops("demo-chat-0001")]
        size_after = journal_path.stat().st_size
        print(f"torn-tail repair: bytes {size_before}->{size_after} "
              f"(garbage dropped={size_after == size_before}), pending={pending_after}")
        assert "torn-garbage" not in str(pending_after), "torn record must not surface"

    def resurrect() -> None:
        mgr = ctx["mgr"]
        first = mgr.rebuild_state("demo-chat-0001")
        print("--- STATE.md head ---")
        for line in first.splitlines()[:15]:
            print(line)
        print("--- /head ---")
        second = mgr.rebuild_state("demo-chat-0001")
        print(f"rebuild_state byte-equal across renders: {first.encode() == second.encode()}")
        assert first == second

    def quota_and_codes() -> None:
        mgr, ws = ctx["mgr"], ctx["root"] / "demo-chat-0001"
        cfg = cw.app.config
        saved_mb = cfg.HOST_CHAT_QUOTA_MB
        filler = ws / cw.NOTES_NAME / "filler.bin"
        try:
            cfg.HOST_CHAT_QUOTA_MB = 1  # tiny quota, same knob the env sets
            filler.write_bytes(b"\0" * (2 * 1024 * 1024))
            seq_before = cw.load_workspace_meta(ws)["next_seq"]
            try:
                mgr.append_op_started("demo-chat-0001", "op-quota-1", "fs_write")
                raise AssertionError("QuotaError expected")
            except cw.QuotaError as exc:
                seq_after = cw.load_workspace_meta(ws)["next_seq"]
                print(f"E3 mapped: {envelope(exc)}; seq unchanged={seq_before == seq_after}")
            finally:
                cfg.HOST_CHAT_QUOTA_MB = saved_mb
                filler.unlink()
            try:
                catalog_validate_chat_id("bad id!")
                raise AssertionError("ChatCatalogError expected")
            except ChatCatalogError as exc:
                print(f"E1 mapped: {envelope(exc)}")
            try:
                mgr.create_or_bind("ab")
                raise AssertionError("ValueError expected")
            except ValueError as exc:
                print(f"manager rejects short id: ValueError({str(exc)[:48]}...)")
            squat = ctx["root"] / "squat-chat-9"
            squat.mkdir()
            (squat / cw.META_NAME).write_text('{"chat_id":"other-owner-1","schema":1,"next_seq":1}\n')
            try:
                mgr.create_or_bind("squat-chat-9")
                raise AssertionError("SquatError expected")
            except cw.SquatError as exc:
                exc.path = str(squat)  # enrich mapping with validated path only
                print(f"E5 mapped: {envelope(exc)}")
        finally:
            cfg.HOST_CHAT_QUOTA_MB = saved_mb
            if filler.exists():
                filler.unlink()

    def sweeper() -> None:
        root, ws_old = ctx["root"], ctx["root"] / "ctf-session-42"
        stale = time.time() - 3 * 3600
        paths = [ws_old, *ws_old.rglob("*")]
        for p in paths:
            os.utime(p, (stale, stale))
        limits = SweepLimits(idle_archive_hours=1, retention_days=30,
                             max_workspaces=64, root_max_gb=10)
        actions = plan_actions(scan(root), limits)
        print(f"planned: {[(a['action'], Path(a['target']).name) for a in actions]}")
        dry = apply_actions(actions, root, dry_run=True)
        real = apply_actions(actions, root, dry_run=False)
        print(f"dry_run -> {[(r['action'], r['status']) for r in dry]}")
        print(f"applied  -> {[(r['action'], r['status']) for r in real]}")
        after = scan(root)
        for entry in after:
            tag = "ARCHIVED" if entry["archived"] else "active"
            print(f"{tag}: {entry['chat_id']} (under .archive/={entry['archived']})")

    def live() -> None:
        try:
            body = get_json_or_text("/healthz")
            print(f"/healthz -> {body!r}")
            jobs = get_json("/api/v1/jobs?limit=3")
            sample = jobs["jobs"][0] if jobs.get("jobs") else None
            print(f"/api/v1/jobs?limit=3 -> ok={jobs.get('ok')} count={jobs.get('count')}"
                  + (f" sample[id={sample.get('id')}, status={sample.get('status')}]"
                     if sample else ""))
            act = get_json("/api/v1/activity?limit=3")
            print(f"/api/v1/activity?limit=3 -> ok={act.get('ok')} source={act.get('source')} "
                  f"count={act.get('count')}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"SKIP live services (runtime unreachable: {exc})")

    def cleanup() -> None:
        shutil.rmtree(ctx["root"], ignore_errors=True)
        cfg = cw.app.config
        cfg.HOST_CHAT_RESUME_HINT_MINUTES = ctx["old_hint"]
        print(f"temp root removed; elapsed={time.time() - t0:.2f}s")

    section("PHẦN 1 · Handshake: tạo/bind workspace theo chat", setup)
    section("PHẦN 2 · Journal hai pha + sửa đuôi rách (torn tail)", journal)
    section("PHẦN 3 · Hồi sinh STATE.md từ journal", resurrect)
    section("PHẦN 4 · Hạn mức và mã lỗi E-catalog (E3/E1/E5)", quota_and_codes)
    section("PHẦN 5 · Sweeper vòng đời: lưu trữ workspace idle", sweeper)
    section("PHẦN 6 · Dịch vụ runtime (GET chỉ đọc trên localhost)", live)
    section("PHẦN 7 · Dọn dẹp", cleanup)

    if FAILURES:
        print(f"\nKET QUA: FAIL ({len(FAILURES)} phan khong mong doi)")
        return 1
    print("\nKET QUA: PASS")
    return 0


def get_json_or_text(path: str) -> str:
    with urllib.request.urlopen(BASE_URL + path, timeout=2.0) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    return raw[:60]


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # catastrophic guard
        print(f"KET QUA: FAIL (fatal: {type(exc).__name__}: {exc})")
        sys.exit(2)
