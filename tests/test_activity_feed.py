import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

_STAMP_BASE = datetime(2026, 8, 26, tzinfo=timezone.utc)


def _stamp(offset_seconds: int) -> str:
    return (_STAMP_BASE + timedelta(seconds=offset_seconds)).isoformat()


def _journal_record(
    seq: int,
    offset_seconds: int,
    event_type: str,
    op: str,
    **overrides: Any,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "seq": seq,
        "ts": _stamp(offset_seconds),
        "type": event_type,
        "op": op,
        "kind": "command",
    }
    record.update(overrides)
    return record


def _write_journal(
    root: Path,
    chat_id: str,
    records: list[dict[str, Any]],
    *,
    archived: bool = False,
    previous_generation: bool = False,
) -> None:
    ws_dir = root / ".archive" / chat_id if archived else root / chat_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    name = "journal.jsonl.1" if previous_generation else "journal.jsonl"
    lines = "".join(json.dumps(record) + "\n" for record in records)
    (ws_dir / name).write_text(lines)


def _run_probe(code: str, extra_env: dict[str, str]) -> dict[str, Any]:
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
        # The operator's real .env may enable chat workspaces; legacy-shape
        # probes must pin the flag off instead of inheriting it.
        "HOST_CHAT_WORKSPACES": "false",
        **extra_env,
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )
    return json.loads(proc.stdout)


_PROBE_PREAMBLE = r'''
import json

from starlette.testclient import TestClient

from app.jobs_registry import get_jobs_registry

registry = get_jobs_registry()

from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")
'''

# Shared body between the flag-off and flag-on probes; each seeds its own
# registry jobs and issues its probes into ``result`` before printing JSON.


def test_activity_without_flag_matches_legacy_shape(tmp_path: Path) -> None:
    # Journals exist on disk, but the feature flag stays off: the endpoint
    # must ignore them entirely and keep today's registry-only contract.
    _write_journal(
        tmp_path,
        "chat-z",
        [_journal_record(1, 0, "op_started", "host.command")],
    )
    code = (
        _PROBE_PREAMBLE
        + r'''

with TestClient(app) as client:
    done_job = registry.register("host.search", chat_id="chat-a")
    registry.start(done_job.job_id)
    registry.finish(done_job.job_id, True, detail="exit 0")
    queued_job = registry.register("host.command", chat_id="chat-b")

    result = {
        "seeded": [done_job.job_id, queued_job.job_id],
        "default": client.get("/api/v1/activity").json(),
        "by_chat": client.get("/api/v1/activity", params={"chat_id": "chat-a"}).json(),
        "jobs_only": client.get(
            "/api/v1/activity", params={"include": "jobs"}
        ).json(),
        "journals_only": client.get(
            "/api/v1/activity", params={"include": "journals"}
        ).json(),
    }
    bad_include = client.get("/api/v1/activity", params={"include": "bogus"})
    result["bad_include"] = [bad_include.status_code, bad_include.json()]

print(json.dumps(result))
'''
    )
    result = _run_probe(code, {"HOST_CHAT_ROOT": str(tmp_path)})

    default = result["default"]
    assert default["ok"] is True
    assert default["source"] == "jobs_registry"
    assert default["count"] == 2
    assert [rec["job_id"] for rec in default["activity"]] == [
        result["seeded"][1],
        result["seeded"][0],
    ]
    assert all("source" not in rec for rec in default["activity"])

    by_chat = result["by_chat"]
    assert by_chat["count"] == 1
    assert by_chat["activity"][0]["chat_id"] == "chat-a"

    assert result["jobs_only"]["source"] == "jobs_registry"
    assert result["jobs_only"]["count"] == 2

    # Feature off means no journal contribution anywhere; an explicit
    # journals-only ask yields an honest empty feed, not fabricated jobs.
    assert result["journals_only"]["source"] == "journal"
    assert result["journals_only"]["count"] == 0

    assert result["bad_include"][0] == 400
    assert result["bad_include"][1]["error"]["code"] == "INVALID_ARGUMENT"


def test_activity_includes_chat_journal_with_rotation_generation(
    tmp_path: Path,
) -> None:
    _write_journal(
        tmp_path,
        "chat-a",
        [_journal_record(10, 0, "op_started", "host.old-op")],
        previous_generation=True,
    )
    _write_journal(
        tmp_path,
        "chat-a",
        [
            _journal_record(11, 10, "op_result", "host.old-op"),
            _journal_record(12, 20, "op_started", "host.live-op"),
            _journal_record(13, 30, "op_result", "host.live-op"),
        ],
    )
    # Another chat whose journal must never leak into chat-a's feed.
    _write_journal(
        tmp_path,
        "chat-b",
        [_journal_record(20, 15, "op_started", "host.other-chat")],
    )
    code = (
        _PROBE_PREAMBLE
        + r'''

with TestClient(app) as client:
    done_job = registry.register("host.command", chat_id="chat-a")
    registry.start(done_job.job_id)
    registry.finish(done_job.job_id, True, detail="exit 0")

    result = {
        "job_id": done_job.job_id,
        "journals_only": client.get(
            "/api/v1/activity",
            params={"chat_id": "chat-a", "include": "journals"},
        ).json(),
        "merged_default": client.get(
            "/api/v1/activity",
            params={"chat_id": "chat-a"},
        ).json(),
        "jobs_only": client.get(
            "/api/v1/activity",
            params={"chat_id": "chat-a", "include": "jobs"},
        ).json(),
        "other_chat": client.get(
            "/api/v1/activity",
            params={"chat_id": "chat-b", "include": "journals"},
        ).json(),
    }

print(json.dumps(result))
'''
    )
    result = _run_probe(
        code,
        {
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ROOT": str(tmp_path),
        },
    )

    journals = result["journals_only"]
    assert journals["ok"] is True
    assert journals["source"] == "journal"
    assert journals["count"] == 4
    # Rotation archive (journal.jsonl.1) feeds oldest-first ahead of the
    # active journal: seq 10 predates 11..13 despite living in the older file.
    assert [record["seq"] for record in journals["activity"]] == [10, 11, 12, 13]
    assert all(record["source"] == "journal" for record in journals["activity"])
    assert all(record["chat_id"] == "chat-a" for record in journals["activity"])
    assert journals["activity"][0]["type"] == "op_started"
    assert journals["activity"][0]["op"] == "host.old-op"

    merged = result["merged_default"]
    assert merged["source"] == "jobs_registry+journal"
    assert merged["count"] == 5
    # Journal records carry ts so they sort ahead; the job record has no
    # ts/seq and keeps its registry position in the stable tail block.
    assert merged["activity"][0]["seq"] == 10
    assert merged["activity"][3]["seq"] == 13
    assert merged["activity"][4]["job_id"] == result["job_id"]

    jobs_only = result["jobs_only"]
    assert jobs_only["source"] == "jobs_registry"
    assert jobs_only["count"] == 1
    assert all(record.get("source") != "journal" for record in jobs_only["activity"])

    other_chat = result["other_chat"]
    assert other_chat["count"] == 1
    assert other_chat["activity"][0]["op"] == "host.other-chat"


def test_activity_skips_corrupt_lines_and_garbage_timestamps(
    tmp_path: Path,
) -> None:
    _write_journal(tmp_path, "chat-a", [])
    journal = tmp_path / "chat-a" / "journal.jsonl"
    payload = "".join(
        line + "\n"
        for line in [
            json.dumps(_journal_record(1, 0, "op_started", "op.ok-first")),
            "{not json at all",
            "",
            '{"seq":2,"ts":"2026-08-26T00:00:20+00:00","type":"op_result","op":',
            json.dumps(
                _journal_record(
                    3, 40, "op_started", "op.garbage-string-ts", ts="not-a-timestamp"
                )
            ),
            json.dumps({**_journal_record(4, 50, "op_result", "op.numeric-ts"), "ts": 12345}),
        ]
    )
    journal.write_text(payload)
    code = (
        _PROBE_PREAMBLE
        + r'''

with TestClient(app) as client:
    result = {"feed": client.get(
        "/api/v1/activity",
        params={"chat_id": "chat-a", "include": "journals"},
    ).json()}

print(json.dumps(result))
'''
    )
    result = _run_probe(
        code,
        {
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ROOT": str(tmp_path),
        },
    )

    feed = result["feed"]
    assert feed["ok"] is True
    assert feed["count"] == 3
    activity = feed["activity"]
    # Corrupt, torn, and blank lines vanish silently; only valid JSON objects
    # survive -- including the one whose payload was otherwise fine.
    by_op = {record["op"]: record for record in activity}
    assert set(by_op) == {"op.ok-first", "op.garbage-string-ts", "op.numeric-ts"}
    assert len(activity) == len(by_op)
    assert by_op["op.ok-first"]["seq"] == 1
    # Timestamps pass through verbatim -- even garbage ones.
    assert by_op["op.garbage-string-ts"]["ts"] == "not-a-timestamp"
    assert by_op["op.numeric-ts"]["ts"] == 12345
    # Comparable ISO stamps stay ordered; uncomparable junk sorts as plain
    # strings ("2026..." < "not-a-timestamp"), while non-string ts values are
    # treated as missing and fall into the stable tail bucket.
    assert [record["op"] for record in activity] == [
        "op.ok-first",
        "op.garbage-string-ts",
        "op.numeric-ts",
    ]


def test_activity_caps_single_chat_at_100_newest(tmp_path: Path) -> None:
    _write_journal(
        tmp_path,
        "chat-a",
        [_journal_record(seq, seq, "op_started", f"op-{seq}") for seq in range(1, 151)],
    )
    code = (
        _PROBE_PREAMBLE
        + r'''

with TestClient(app) as client:
    result = {"feed": client.get(
        "/api/v1/activity",
        params={"chat_id": "chat-a", "include": "journals"},
    ).json()}

print(json.dumps(result))
'''
    )
    result = _run_probe(
        code,
        {
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ROOT": str(tmp_path),
        },
    )

    feed = result["feed"]
    assert feed["ok"] is True
    assert feed["count"] == 100
    # Only the most recent 100 valid records survive, oldest-last preserved.
    assert [record["seq"] for record in feed["activity"]] == list(range(51, 151))


def test_activity_aggregates_workspaces_capped_at_200_incl_archives(
    tmp_path: Path,
) -> None:
    # 240 total records across three workspaces (one archived): the global
    # newest-200 cut must drop chat-a's earliest 40 and keep the rest.
    _write_journal(
        tmp_path,
        "chat-a",
        [_journal_record(seq, seq, "op_started", f"a-{seq}") for seq in range(1, 81)],
    )
    _write_journal(
        tmp_path,
        "chat-b",
        [
            _journal_record(seq, 1000 + seq, "op_started", f"b-{seq}")
            for seq in range(1, 81)
        ],
    )
    _write_journal(
        tmp_path,
        "chat-old",
        [
            _journal_record(seq, 5000 + seq, "op_started", f"old-{seq}")
            for seq in range(1, 81)
        ],
        archived=True,
    )
    code = (
        _PROBE_PREAMBLE
        + r'''

with TestClient(app) as client:
    result = {"feed": client.get(
        "/api/v1/activity",
        params={"include": "journals"},
    ).json()}

print(json.dumps(result))
'''
    )
    result = _run_probe(
        code,
        {
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ROOT": str(tmp_path),
        },
    )

    feed = result["feed"]
    assert feed["ok"] is True
    assert feed["source"] == "journal"
    assert feed["count"] == 200
    activity = feed["activity"]
    chat_ids = {record["chat_id"] for record in activity}
    assert chat_ids == {"chat-a", "chat-b", "chat-old"}
    assert all(record["source"] == "journal" for record in activity)
    # Newest-200 window: chat-a seq 1..40 fell off the front, everything
    # else survived; the archived workspace's newest record closes the feed.
    assert (activity[0]["chat_id"], activity[0]["seq"]) == ("chat-a", 41)
    assert (activity[-1]["chat_id"], activity[-1]["seq"]) == ("chat-old", 80)
    assert [record["seq"] for record in activity if record["chat_id"] == "chat-a"] == list(
        range(41, 81)
    )
    assert [record["seq"] for record in activity if record["chat_id"] == "chat-b"] == list(
        range(1, 81)
    )


def test_activity_classification_filters_use_correlated_workspace_taxonomy(tmp_path: Path) -> None:
    _write_journal(
        tmp_path,
        "chat-filter",
        [
            _journal_record(1, 0, "op_started", "op-file", kind="host_read_file"),
            _journal_record(2, 1, "op_result", "op-file", kind=None, ok=True),
            _journal_record(3, 2, "op_started", "op-cmd", kind="host_run_command"),
            _journal_record(4, 4, "op_result", "op-cmd", kind=None, ok=False),
        ],
    )
    code = (
        _PROBE_PREAMBLE
        + r'''

with TestClient(app) as client:
    job = registry.register("host.command", chat_id="chat-filter")
    registry.start(job.job_id)
    registry.finish(job.job_id, True)
    result = {
        "errors": client.get(
            "/api/v1/activity",
            params={"chat_id": "chat-filter", "severity": "error"},
        ).json(),
        "file_results": client.get(
            "/api/v1/activity",
            params={
                "chat_id": "chat-filter",
                "category": "file",
                "phase": "result",
            },
        ).json(),
    }
    bad = client.get("/api/v1/activity", params={"severity": "fatal-ish"})
    result["bad"] = [bad.status_code, bad.json()]

print(json.dumps(result))
'''
    )
    result = _run_probe(
        code,
        {
            "HOST_CHAT_WORKSPACES": "true",
            "HOST_CHAT_ROOT": str(tmp_path),
        },
    )

    errors = result["errors"]
    assert errors["source"] == "journal"
    assert errors["count"] == 1
    assert errors["filters"]["severity"] == "ERROR"
    assert errors["activity"][0]["event_action"] == "host_run_command"
    assert errors["activity"][0]["event_category"] == "process"
    assert errors["activity"][0]["event_outcome"] == "failure"
    assert errors["activity"][0]["event_duration_ms"] == 2000.0

    file_results = result["file_results"]
    assert file_results["count"] == 1
    assert file_results["activity"][0]["event_action"] == "host_read_file"
    assert file_results["activity"][0]["event_category"] == "file"
    assert file_results["activity"][0]["event_duration_ms"] == 1000.0

    assert result["bad"][0] == 400
    assert result["bad"][1]["error"]["code"] == "INVALID_ARGUMENT"


# ---------------------------------------------------------------------------
# Live workspace activity SSE.
# ---------------------------------------------------------------------------


def test_activity_sse_event_id_and_frame_are_stable_and_opaque():
    import app.rest_api as rest

    record = {
        "chat_id": "chat-a",
        "seq": 7,
        "ts": "2026-08-26T18:00:00+00:00",
        "interaction_id": "op-7",
        "operation_phase": "result",
        "payload": {"path": "secret/path.txt"},
    }
    event_id = rest._activity_event_id(record)
    assert len(event_id) == 24
    assert "chat-a" not in event_id
    assert "secret" not in event_id
    assert rest._activity_event_id(dict(record)) == event_id
    frame = rest._sse_workspace_log(record)
    assert frame.startswith(f"id: {event_id}\nevent: workspace_log\ndata: ")
    assert frame.endswith("\n\n")


def test_activity_sse_generator_replays_and_resumes(monkeypatch):
    import anyio

    import app.rest_api as rest

    records = [
        {
            "chat_id": "chat-a",
            "seq": seq,
            "ts": f"2026-08-26T18:00:0{seq}+00:00",
            "interaction_id": f"op-{seq}",
            "operation_phase": "result",
            "severity_text": "INFO",
        }
        for seq in (1, 2)
    ]

    async def snapshot(*, chat_id, filters):
        assert chat_id == "chat-a"
        assert filters == {"category": "process"}
        return records

    monkeypatch.setattr(rest, "_activity_stream_snapshot", snapshot)

    class FakeRequest:
        def __init__(self, last_event_id=""):
            self.headers = {"last-event-id": last_event_id} if last_event_id else {}

        async def is_disconnected(self):
            return True

    async def first_replay():
        chunks = []
        generator = rest._activity_sse_generator(
            FakeRequest(),
            chat_id="chat-a",
            filters={"category": "process"},
            replay=1,
        )
        async for chunk in generator:
            chunks.append(chunk)
            if len(chunks) == 2:
                break
        await generator.aclose()
        return chunks

    replayed = anyio.run(first_replay)
    assert replayed[0] == f"retry: {rest._ACTIVITY_STREAM_RETRY_MS}\n\n"
    assert '"seq":2' in replayed[1]
    assert '"seq":1' not in replayed[1]

    first_id = rest._activity_event_id(records[0])

    async def resume_after_first():
        chunks = []
        generator = rest._activity_sse_generator(
            FakeRequest(first_id),
            chat_id="chat-a",
            filters={"category": "process"},
            replay=0,
        )
        async for chunk in generator:
            chunks.append(chunk)
            if len(chunks) == 2:
                break
        await generator.aclose()
        return chunks

    resumed = anyio.run(resume_after_first)
    assert '"seq":2' in resumed[1]
    assert '"seq":1' not in resumed[1]


def test_activity_stream_is_advertised_in_routes_and_openapi():
    import app.rest_api as rest

    paths = {route.path for route in rest.rest_routes()}
    assert "/api/v1/activity/stream" in paths
    document = rest.openapi_document()
    stream = document["paths"]["/api/v1/activity/stream"]["get"]
    assert stream["responses"]["200"]["content"]["text/event-stream"]


def test_activity_stream_http_contract_and_replay_validation():
    import anyio

    import app.rest_api as rest

    class FakeRequest:
        def __init__(self, params):
            self.query_params = params
            self.headers = {}

        async def is_disconnected(self):
            return True

    response = anyio.run(
        rest.api_activity_stream,
        FakeRequest({"chat_id": "chat-a", "category": "file", "replay": "1"}),
    )
    invalid = anyio.run(
        rest.api_activity_stream,
        FakeRequest({"replay": str(rest._ACTIVITY_STREAM_REPLAY_MAX + 1)}),
    )

    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert invalid.status_code == 400
    assert json.loads(invalid.body)["error"]["code"] == "INVALID_ARGUMENT"


def test_activity_sse_generator_marks_missing_resume_cursor_as_reset(monkeypatch):
    import anyio

    import app.rest_api as rest

    records = [
        {
            "chat_id": "chat-a",
            "seq": 9,
            "ts": "2026-08-26T18:00:09+00:00",
            "interaction_id": "op-9",
            "operation_phase": "result",
            "severity_text": "INFO",
        }
    ]

    async def snapshot(*, chat_id, filters):
        return records

    monkeypatch.setattr(rest, "_activity_stream_snapshot", snapshot)

    class FakeRequest:
        headers = {"last-event-id": "expired-cursor"}

        async def is_disconnected(self):
            return True

    async def collect():
        chunks = []
        generator = rest._activity_sse_generator(
            FakeRequest(), chat_id="chat-a", filters={}, replay=1
        )
        async for chunk in generator:
            chunks.append(chunk)
            if len(chunks) == 3:
                break
        await generator.aclose()
        return chunks

    chunks = anyio.run(collect)
    assert chunks[0] == f"retry: {rest._ACTIVITY_STREAM_RETRY_MS}\n\n"
    assert "event: stream_reset" in chunks[1]
    reset = json.loads(chunks[1].split("data: ", 1)[1])
    assert reset == {
        "reason": "cursor_not_found",
        "requested_last_event_id": "expired-cursor",
        "replay": 1,
    }
    assert '"seq":9' in chunks[2]


def test_live_stream_snapshot_uses_larger_window_than_snapshot_endpoint(monkeypatch, tmp_path):
    import anyio

    import app.config
    import app.rest_api as rest

    records = [
        _journal_record(seq, seq, "op_result", f"op-{seq}", ok=True)
        for seq in range(1, 251)
    ]
    _write_journal(tmp_path, "chat-burst", records)
    monkeypatch.setattr(app.config, "HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr(app.config, "HOST_CHAT_ROOT", tmp_path)

    snapshot_rows = rest._journal_activity_records(chat_id="chat-burst")
    assert len(snapshot_rows) == rest._JOURNAL_SINGLE_CHAT_LIMIT == 100

    async def read_stream_snapshot():
        return await rest._activity_stream_snapshot(chat_id="chat-burst", filters={})

    stream_rows = anyio.run(read_stream_snapshot)
    assert len(stream_rows) == 250
    assert [item["seq"] for item in stream_rows] == list(range(1, 251))
