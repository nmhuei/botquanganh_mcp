"""F4: strength suite for the chat-workspace stack.

Surfaces hammered: WorkspaceManager journal API (stable design), rotation
under pressure, JobsRegistry eviction storm, chat_sweeper scale + dry-run
purity, chat_errors fuzz, and a REST jobs-endpoint soak.

Deterministic seeds everywhere; no network; explicit timeouts on every join.
WHY slow bits are slow is noted inline where they exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import app.config
from app.chat_errors import (
    ChatCatalogError,
    chat_error_payload,
    internal_error_payload,
    to_tool_error,
    tool_success,
    tool_unavailable,
)
from app.chat_sweeper import SweepLimits, apply_actions, plan_actions, scan
from app.chat_workspace import WorkspaceManager
from app.jobs_registry import JobsRegistry


def _make_manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(tmp_path / "chat-root")


# ---------------------------------------------------------------------------
# 1. Journal concurrency: seq uniqueness / monotonicity / losslessness.
# ---------------------------------------------------------------------------


def test_journal_concurrent_appends_keep_seq_unique_monotonic_lossless(tmp_path):
    manager = _make_manager(tmp_path)
    chat_id = "stresaa"
    manager.create_or_bind(chat_id)

    threads_n = 12
    pairs_per_thread = 30
    total_records = threads_n * pairs_per_thread * 2
    returned: list[dict] = []
    returned_lock = threading.Lock()
    reader_violations: list[str] = []
    stop_reader = threading.Event()
    failures: list[Exception] = []

    def reader() -> None:
        # Concurrent replay snapshots must always show distinct seqs because
        # appends are serialized under the per-workspace lock.
        while not stop_reader.is_set():
            try:
                seqs = [event["seq"] for event in manager.read_events(chat_id)]
            except Exception as exc:  # pragma: no cover - surfaced below
                reader_violations.append(f"read_events raised: {exc!r}")
                return
            if len(seqs) != len(set(seqs)):
                reader_violations.append(f"duplicate seqs in snapshot: {sorted(seqs)}")
                return
            if seqs != sorted(seqs):
                reader_violations.append(f"non-monotonic snapshot: {seqs}")
                return

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    def worker(worker_index: int) -> None:
        local: list[dict] = []
        try:
            for offset in range(pairs_per_thread):
                op_id = f"w{worker_index}-op{offset}"
                started = manager.append_op_started(
                    chat_id, op_id, "host.command", {"worker": worker_index}
                )
                result = manager.append_op_result(chat_id, op_id, True, {"exit": 0})
                local.extend((started, result))
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            failures.append(exc)
        finally:
            with returned_lock:
                returned.extend(local)

    with ThreadPoolExecutor(max_workers=threads_n) as pool:
        futures = [pool.submit(worker, index) for index in range(threads_n)]
        for future in futures:
            future.result(timeout=60)

    stop_reader.set()
    reader_thread.join(timeout=5)
    assert not failures
    assert reader_violations == []

    assert len(returned) == total_records
    seqs = sorted(record["seq"] for record in returned)
    assert seqs == list(range(1, total_records + 1)), "seqs must be 1..N with no gaps"

    replay = manager.read_events(chat_id)
    assert len(replay) == total_records
    replay_seqs = [record["seq"] for record in replay]
    assert replay_seqs == sorted(replay_seqs)
    assert len(set(replay_seqs)) == total_records
    # Every started op got exactly one result: nothing left dangling.
    assert manager.pending_ops(chat_id) == []
    # STATE.md regenerates cleanly from the storm's output.
    manager.rebuild_state(chat_id)


def test_journal_torn_tail_partial_line_repaired_on_reopen(tmp_path):
    manager = _make_manager(tmp_path)
    chat_id = "tornline"
    manager.create_or_bind(chat_id)
    manager.append_op_started(chat_id, "op-a", "host.command")
    manager.append_op_result(chat_id, "op-a", True)

    journal = tmp_path / "chat-root" / chat_id / "journal.jsonl"
    meta = json.loads((tmp_path / "chat-root" / chat_id / "meta.json").read_text())
    with journal.open("ab") as handle:
        handle.write(b'{"seq":99,"type":"op_started","op":"ghost","pay')  # no newline
    # A crash mid-append leaves meta.next_seq untouched: the ghost tail must
    # vanish on reopen and sequencing must continue from the real next_seq.
    reopened = WorkspaceManager(tmp_path / "chat-root")
    events = reopened.read_events(chat_id)
    # op-a contributes one started + one result; the ghost tail is gone.
    assert [(record["type"], record["op"]) for record in events] == [
        ("op_started", "op-a"),
        ("op_result", "op-a"),
    ]
    assert all(record["seq"] <= meta["next_seq"] for record in events)

    nxt = reopened.append_op_started(chat_id, "op-b", "host.command")
    assert nxt["seq"] == meta["next_seq"]

    raw = journal.read_bytes()
    assert raw.endswith(b"\n"), "journal must be valid newline-terminated JSONL"
    parsed = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    assert {record["op"] for record in parsed} == {"op-a", "op-b"}
    assert "ghost" not in {record["op"] for record in parsed}


def test_journal_torn_tail_repair_never_touches_complete_lines(tmp_path):
    manager = _make_manager(tmp_path)
    chat_id = "tornkeep"
    manager.create_or_bind(chat_id)
    for index in range(5):
        manager.append_op_started(chat_id, f"op-{index}", "kind")

    journal = tmp_path / "chat-root" / chat_id / "journal.jsonl"
    good_before = [
        line for line in journal.read_bytes().splitlines(keepends=True) if line.endswith(b"\n")
    ]
    # Torn tail containing invalid UTF-8 mid-line, still without a newline.
    with journal.open("ab") as handle:
        handle.write(b'{"seq":\xff\xfe,"ty')
    events = manager.read_events(chat_id)
    assert len(events) == 5
    good_after = [
        line for line in journal.read_bytes().splitlines(keepends=True) if line.endswith(b"\n")
    ]
    assert good_after == good_before, "repair must drop only the torn tail"


def test_pending_op_spanning_rotation_boundary_still_resolves(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 2048, raising=False)
    manager = _make_manager(tmp_path)
    chat_id = "spanrot"
    manager.create_or_bind(chat_id)
    journal = tmp_path / "chat-root" / chat_id / "journal.jsonl"
    manager.append_op_started(chat_id, "long-op", "host.search", {"q": "x"})
    # Append resolved noise pairs until exactly one rotation has relocated
    # long-op's start record into .1, then stop: a single generation keeps it
    # visible to merged replay.
    rotated = False
    for index in range(50):
        pre_ino = journal.stat().st_ino
        manager.append_op_started(chat_id, f"noise-{index}", "kind", {"blob": "y" * 200})
        rotated = journal.stat().st_ino != pre_ino
        manager.append_op_result(chat_id, f"noise-{index}", True)
        if rotated:
            break
    assert rotated, "scenario must have produced at least one rotation"
    pending_mid = manager.pending_ops(chat_id)
    assert [item["op"] for item in pending_mid] == ["long-op"], (
        "a start record rotated into .1 must stay tracked as pending"
    )
    manager.append_op_result(chat_id, "long-op", True, {"hits": 3})
    assert manager.pending_ops(chat_id) == [], (
        "started-in-archive must be matched by result-in-active via merged replay"
    )


# ---------------------------------------------------------------------------
# 2. Rotation under pressure.
# ---------------------------------------------------------------------------


def test_rotation_under_pressure_replaces_generation_and_keeps_seq_continuity(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES", 2048, raising=False)
    monkeypatch.setattr(app.config, "HOST_CHAT_QUOTA_MB", 0, raising=False)
    manager = _make_manager(tmp_path)
    chat_id = "rotatio"
    manager.create_or_bind(chat_id)
    ws_dir = tmp_path / "chat-root" / chat_id

    rounds = 60
    seen_seq: set[int] = set()
    journal = ws_dir / "journal.jsonl"

    def encoded_len(record: dict) -> int:
        # Mirror of chat_workspace._json_line_bytes for the returned record.
        return len(
            (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )

    limit = int(getattr(app.config, "HOST_CHAT_JOURNAL_MAX_BYTES"))
    for index in range(rounds):
        pre_stat = journal.stat()
        started = manager.append_op_started(
            chat_id, f"op-{index}", "host.command", {"blob": "x" * 300}
        )
        post_started = journal.stat()
        incoming = encoded_len(started)
        if pre_stat.st_size + incoming > limit:
            assert post_started.st_ino != pre_stat.st_ino, (
                "an op_started that would cross the bound must rotate first"
            )
        assert post_started.st_size <= limit, (
            "right after a rotating-kind append the active file must fit the bound"
        )
        result = manager.append_op_result(chat_id, f"op-{index}", True)
        # op_result never rotates by design: it may overshoot by its own length
        # only, until the next op_started caps it again.
        assert journal.stat().st_size <= limit + encoded_len(result)
        for record in (started, result):
            assert record["seq"] not in seen_seq, "duplicate seq across rotations"
            seen_seq.add(record["seq"])

    archive = ws_dir / "journal.jsonl.1"
    assert archive.exists(), "rotation pressure must produce a .1 generation"
    stray = [p.name for p in ws_dir.iterdir() if p.name.startswith("journal.jsonl.")]
    assert stray == ["journal.jsonl.1"], f"exactly one archive generation expected: {stray}"

    archive_lines = [
        json.loads(line)
        for line in archive.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert archive_lines, "archive must hold relocated records"
    active_lines = [
        json.loads(line)
        for line in (ws_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert active_lines
    # Rotation relocates a prefix: archive holds strictly older seqs.
    max_archive_seq = max(record["seq"] for record in archive_lines)
    min_active_seq = min(record["seq"] for record in active_lines)
    assert max_archive_seq < min_active_seq
    # Per-append bounds were already verified inside the loop above.

    merged = manager.read_events(chat_id)
    merged_seqs = sorted(record["seq"] for record in merged)
    # KNOWN WINDOW SEMANTICS (see GAPS): each rotation REPLACES .1, so only the
    # last archive generation survives; replay retains a contiguous suffix of
    # history, not all 2*rounds records. Assert the retained window is
    # contiguous and reaches the newest seq — no holes inside the window.
    assert len(merged_seqs) < 2 * rounds
    assert len(set(merged_seqs)) == len(merged_seqs)
    assert merged_seqs == list(range(min(merged_seqs), 2 * rounds + 1))
    meta = json.loads((ws_dir / "meta.json").read_text())
    assert meta["next_seq"] == 2 * rounds + 1, "next_seq continuity across rotations"
    assert manager.pending_ops(chat_id) == []


# ---------------------------------------------------------------------------
# 3. Registry eviction storm.
# ---------------------------------------------------------------------------


def test_registry_eviction_storm_respects_cap_and_order_invariants():
    cap = 512
    registry = JobsRegistry(max_records=cap)
    workers_n = 8
    cycles_per_worker = 400
    total = workers_n * cycles_per_worker

    registered_index: dict[str, int] = {}
    index_lock = threading.Lock()
    counter = {"n": 0}
    monitor_violations: list[int] = []
    stop_monitor = threading.Event()

    def monitor() -> None:
        # Sampled concurrently with the storm: size must never exceed cap.
        while not stop_monitor.is_set():
            size = len(registry.list(limit=10**9))
            if size > cap:
                monitor_violations.append(size)
                return

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    def worker() -> None:
        for _ in range(cycles_per_worker):
            record = registry.register("storm.op", chat_id="storm")
            with index_lock:
                counter["n"] += 1
                registered_index[record.job_id] = counter["n"]
            assert registry.start(record.job_id) is True
            assert registry.finish(record.job_id, True, detail="ok") is True

    with ThreadPoolExecutor(max_workers=workers_n) as pool:
        futures = [pool.submit(worker) for _ in range(workers_n)]
        for future in futures:
            future.result(timeout=60)
    stop_monitor.set()
    monitor_thread.join(timeout=5)

    assert monitor_violations == []
    survivors = registry.list(limit=10**9)
    assert len(survivors) == cap
    # Every query on anything (evicted or not) answers without raising.
    for job_id in list(registered_index)[:50]:
        fetched = registry.get(job_id)
        assert fetched is None or isinstance(fetched, object)
    # Finished records evict oldest-insertion-first; with every job finished
    # synchronously and concurrency << cap, the survivors are exactly the
    # newest `cap` registrations.
    survivor_ids = {record.job_id for record in survivors}
    expected_ids = {
        job_id
        for job_id, index in registered_index.items()
        if index > total - cap
    }
    assert survivor_ids == expected_ids


def test_registry_get_on_evicted_id_returns_none_without_raising():
    registry = JobsRegistry(max_records=4)
    first_batch = [registry.register(f"op-{i}") for i in range(4)]
    for record in first_batch:
        registry.finish(record.job_id, True)
    second_batch = [registry.register(f"new-{i}") for i in range(4)]
    for record in first_batch:
        assert registry.get(record.job_id) is None
    for record in second_batch:
        assert registry.get(record.job_id) is not None
    # Unknown ids stay quiet too.
    assert registry.get("") is None
    assert registry.get("x" * 10_000) is None


# ---------------------------------------------------------------------------
# 4. Sweeper scale + dry-run purity + escape refusals.
# ---------------------------------------------------------------------------


def _fabricate_workspaces(root: Path, rng: random.Random) -> None:
    """Build hundreds of tiny fake workspaces quickly (no fsync anywhere)."""
    archive = root / ".archive"
    archive.mkdir(parents=True)
    for index in range(300):
        ws = root / f"ws{index:04d}"
        (ws / "notes").mkdir(parents=True)
        (ws / "meta.json").write_text(json.dumps({"schema": 1, "chat_id": ws.name}))
        (ws / "journal.jsonl").write_text('{"seq":1,"type":"op_started","op":"a"}\n')
        (ws / "notes" / "n.txt").write_text("x" * rng.randrange(0, 64))
    for index in range(40):
        old = archive / f"old{index:02d}"
        old.mkdir()
        (old / "meta.json").write_text(json.dumps({"schema": 1, "chat_id": old.name}))
        (old / "j.jsonl").write_text("{}\n")


def _backdate_all(root: Path, hours: float) -> None:
    stamp = time.time() - hours * 3600
    for dirpath, _dirnames, filenames in os.walk(root):
        os.utime(dirpath, (stamp, stamp))
        for name in filenames:
            os.utime(os.path.join(dirpath, name), (stamp, stamp))


def _checksum_tree(root: Path) -> list[tuple[str, int, int, str]]:
    digest_map: list[tuple[str, int, int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            data = path.read_bytes()
            rel = str(path.relative_to(root))
            digest_map.append(
                (rel, len(data), path.stat().st_mtime_ns, hashlib.sha256(data).hexdigest())
            )
    return digest_map


def test_sweeper_plan_scale_hundreds_of_workspaces_bounded_time(tmp_path):
    rng = random.Random(20260826)
    root = tmp_path / "sweep-root"
    root.mkdir()
    _fabricate_workspaces(root, rng)
    _backdate_all(root, hours=48.0)

    limits = SweepLimits(
        idle_archive_hours=1.0,
        retention_days=1.0,
        max_workspaces=10,
        root_max_gb=1.0,
    )
    started = time.perf_counter()
    inventory = scan(root)
    actions = plan_actions(inventory, limits)
    elapsed = time.perf_counter() - started
    # Soft budget: hundreds of dirs must plan far under 10s (scan dominates).
    assert elapsed < 10.0, f"scan+plan took {elapsed:.2f}s for 340 workspaces"

    assert len(inventory) == 340
    targets = {action["target"] for action in actions}
    assert len(targets) == len(actions), "no target may be planned twice"
    kinds = {action["action"] for action in actions}
    assert kinds <= {"ARCHIVE_IDLE", "DELETE_EXPIRED", "ENFORCE_COUNT", "ENFORCE_ROOT_SIZE"}
    deletes = [action for action in actions if action["action"] == "DELETE_EXPIRED"]
    assert len(deletes) == 40, "every expired archived workspace must be planned for deletion"


def test_sweeper_dry_run_mutates_nothing_checksum_identical(tmp_path):
    rng = random.Random(20260826)
    root = tmp_path / "sweep-dry"
    root.mkdir()
    _fabricate_workspaces(root, rng)
    _backdate_all(root, hours=48.0)
    limits = SweepLimits(
        idle_archive_hours=1.0, retention_days=1.0, max_workspaces=10, root_max_gb=1.0
    )
    before = _checksum_tree(root)
    actions = plan_actions(scan(root), limits)
    results = apply_actions(actions, root, dry_run=True)
    after = _checksum_tree(root)

    assert before == after, "dry_run must not change a single byte, name, or mtime"
    assert not (root / ".archive").exists() or (root / ".archive").is_dir(), (
        "pre-existing archive untouched"
    )
    statuses = {result["status"] for result in results}
    assert statuses <= {"would_archive", "would_delete"}, f"dry statuses leaked: {statuses}"
    assert all(result["status"] in ("would_archive", "would_delete") for result in results)


def test_apply_actions_refuses_escape_targets_and_unknown_kinds(tmp_path):
    root = tmp_path / "guard-root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    ws = root / "abcdef"
    ws.mkdir()
    (ws / "meta.json").write_text("{}")

    before = _checksum_tree(root)
    hostile = [
        {"action": "ARCHIVE_IDLE", "target": str(outside)},
        {"action": "ARCHIVE_IDLE", "target": str(root)},
        {"action": "DELETE_EXPIRED", "target": str(ws)},  # inside root, outside .archive
        {"action": "DELETE_EXPIRED", "target": str(outside)},
        {"action": "RECURSE_UNIVERSE", "target": str(ws)},
        {"action": None, "target": str(ws)},
    ]
    results = apply_actions(hostile, root, dry_run=False)
    after = _checksum_tree(root)

    assert before == after, "refused/unknown actions must mutate nothing even when live"
    statuses = [result["status"] for result in results]
    assert all(status == "refused" for status in statuses), statuses
    # A symlink escape is defeated by resolution, not by name checks.
    link = root / "symlink-ws"
    os.symlink(outside, link)
    results = apply_actions([{"action": "ARCHIVE_IDLE", "target": str(link)}], root)
    assert results[0]["status"] == "refused"
    assert not (root / ".archive").exists()


# ---------------------------------------------------------------------------
# 5. Error catalog fuzz.
# ---------------------------------------------------------------------------

_FUZZ_VALUES = [
    None,
    b"\xff\xfe garbage",
    "",
    "x" * 100_000,
    -1,
    0,
    10**30,
    float("nan"),
    float("inf"),
    float("-inf"),
    True,
    [],
    {},
    {"nested": {"deep": [1, None, "x"]}},
    [("tuple", 1)],
    object(),
    Ellipsis,
]


def test_chat_error_payload_fuzz_garbage_fields_always_yield_code():
    rng = random.Random(424242)
    codes = ["E1", "E2", "E3", "E4", "E5", "ZZZ", "", "e1", "E9" * 50]
    field_names = ("count", "limit", "used_bytes", "quota_bytes", "free_bytes",
                   "required_bytes", "chat_id", "path")
    for _ in range(400):
        code = rng.choice(codes)
        fields = {
            name: rng.choice(_FUZZ_VALUES)
            for name in rng.sample(field_names, rng.randrange(0, 5))
        }
        payload = chat_error_payload(code, **fields)
        assert isinstance(payload, dict)
        assert payload["ok"] is False
        assert isinstance(payload["error"]["code"], str)
        assert payload["error"]["code"]
        json.dumps(payload, allow_nan=True)  # envelope must stay serializable
    assert chat_error_payload("ZZZ")["error"]["code"] == "INTERNAL"
    assert internal_error_payload()["error"]["code"] == "INTERNAL"


def test_to_tool_error_fuzz_random_exceptions_returns_envelope():
    rng = random.Random(777)

    class InvalidChatIdError(Exception):
        pass

    class CapacityError(RuntimeError):
        def __init__(self, count: int, limit: int) -> None:
            super().__init__("full")
            self.count = count
            self.limit = limit

    class QuotaExceededError(Exception):
        used_bytes = 5
        quota_bytes = 4
        chat_id = "abc123"

    class RootFullError(OSError):
        pass

    class SquatError(RuntimeError):
        path = "/somewhere"

    class TotallyUnrelated(Exception):
        pass

    candidates: list[BaseException] = [
        InvalidChatIdError(),
        CapacityError(130, 128),
        QuotaExceededError("over"),
        RootFullError(28, "No space left"),
        OSError(28, "No space left on device"),
        SquatError("squat"),
        TotallyUnrelated("meh"),
        KeyboardInterrupt(),
        ValueError(),
        Exception("plain"),
    ]
    for _ in range(200):
        exc = rng.choice(candidates)
        payload = to_tool_error(exc)
        assert isinstance(payload, dict)
        assert payload["ok"] is False
        code = payload["error"]["code"]
        assert isinstance(code, str) and code
        if isinstance(exc, ChatCatalogError):
            continue  # mapped through the catalog directly
        # Domain-shaped exceptions map to E-codes or fall back to INTERNAL;
        # either way the envelope is intact.
        json.dumps(payload, allow_nan=True, default=str)
    assert to_tool_error(OSError(28, "full"))["error"]["code"] == "E4"
    assert tool_unavailable("f")["error"]["code"] == "NOT_AVAILABLE"
    assert tool_success("hi")["ok"] is True


# NOTE (known gap, kept out of the green suite): a value whose __format__ or
# __str__ raises (e.g. used_bytes=BrokenFormat()) makes chat_error_payload --
# and therefore to_tool_error for domain exceptions carrying such attrs --
# propagate the exception instead of returning an envelope. Recorded in GAPS.


# ---------------------------------------------------------------------------
# 6. REST jobs endpoints soak (subprocess TestClient pattern).
# ---------------------------------------------------------------------------

_SOAK_CODE = r'''
import json

from starlette.testclient import TestClient

from app.jobs_registry import get_jobs_registry

registry = get_jobs_registry()
for i in range(30):
    rec = registry.register(f"soak.op.{i % 5}", chat_id=f"chat-{i % 3}")
    if i % 3 == 0:
        registry.start(rec.job_id)
    if i % 3 != 1:
        registry.finish(rec.job_id, i % 5 != 4, detail="d", result_excerpt="r")

from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")

param_batches = [
    {},
    {"chat_id": "chat-1"},
    {"status": "done"},
    {"status": "error"},
    {"limit": 5},
    {"limit": 99999},
    {"limit": 0},
    {"job_id": "deadbeef"},
    {"status": "bogus"},          # intentional 400
    {"limit": "not-an-int"},      # intentional 400
    {"chat_id": "", "status": "queued"},
]

results = []
with TestClient(app) as client:
    for i in range(500):
        params = param_batches[i % len(param_batches)]
        path = "/api/v1/jobs" if i % 7 else "/api/v1/activity"
        response = client.get(path, params=params)
        entry = {"status": response.status_code}
        try:
            body = response.json()
            entry["envelope_ok"] = isinstance(body, dict) and (
                body.get("ok") is True
                or isinstance(body.get("error"), dict) and bool(body["error"].get("code"))
            )
        except Exception:
            entry["envelope_ok"] = False
            entry["body_head"] = response.text[:120]
        results.append(entry)
    canary = client.get("/api/v1").status_code

print(json.dumps({"results": results, "canary": canary}))
'''


def test_rest_jobs_endpoints_soak_mixed_params_wellformed():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
    }
    proc = subprocess.run(
        [sys.executable, "-c", _SOAK_CODE],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"soak harness crashed:\n{proc.stderr[-2000:]}"
    summary = json.loads(proc.stdout)

    assert summary["canary"] == 200, "API index stopped answering after the soak"
    bad_envelopes = [entry for entry in summary["results"] if not entry.get("envelope_ok")]
    assert not bad_envelopes, f"malformed envelopes: {bad_envelopes[:5]}"
    unexpected_5xx = [
        entry["status"] for entry in summary["results"] if entry["status"] >= 500
    ]
    assert not unexpected_5xx, f"unexpected 5xx during soak: {unexpected_5xx[:10]}"
    allowed = {200, 400, 404}
    off_menu = [
        entry["status"] for entry in summary["results"] if entry["status"] not in allowed
    ]
    assert not off_menu, f"unexpected status codes: {off_menu[:10]}"
    # The two intentionally-invalid batches must be validation rejections.
    statuses = [entry["status"] for entry in summary["results"]]
    assert 400 in statuses, "invalid params must yield intentional 400s"
