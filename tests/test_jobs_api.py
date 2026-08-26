import json
import os
import subprocess
import sys
import threading

import pytest

from app.jobs_registry import JobsRegistry, get_jobs_registry


def test_register_start_finish_lifecycle():
    registry = JobsRegistry()
    record = registry.register("host.command", chat_id="chat-1")
    assert record.status == "queued"
    assert record.started_at is None
    assert record.finished_at is None
    assert registry.get(record.job_id) is record
    assert record.op == "host.command"
    assert record.chat_id == "chat-1"

    assert registry.start(record.job_id) is True
    assert record.status == "running"
    assert record.started_at is not None

    assert (
        registry.finish(
            record.job_id, True, detail="exit 0", result_excerpt="alpha"
        )
        is True
    )
    assert record.status == "done"
    assert record.finished_at is not None
    assert record.detail == "exit 0"
    assert record.result_excerpt == "alpha"


def test_finish_error_marks_error_status_and_excerpt_optional():
    registry = JobsRegistry()
    record = registry.register("host.write_file")
    registry.start(record.job_id)
    assert registry.finish(record.job_id, False, detail="denied") is True
    assert record.status == "error"
    assert record.finished_at is not None
    assert record.result_excerpt is None


def test_unknown_job_ids_are_tolerated():
    registry = JobsRegistry()
    assert registry.get("missing") is None
    assert registry.start("missing") is False
    assert registry.finish("missing", True) is False


def test_eviction_prefers_oldest_finished_then_oldest_overall():
    registry = JobsRegistry(max_records=3)
    first_done = registry.register("op1")
    second_done = registry.register("op2")
    runner = registry.register("op3")
    registry.finish(first_done.job_id, True)
    registry.finish(second_done.job_id, False)

    fourth = registry.register("op4")
    assert registry.get(first_done.job_id) is None
    for kept in (second_done, runner, fourth):
        assert registry.get(kept.job_id) is not None

    fifth = registry.register("op5")
    assert registry.get(second_done.job_id) is None
    for kept in (runner, fourth, fifth):
        assert registry.get(kept.job_id) is not None

    sixth = registry.register("op6")
    assert registry.get(runner.job_id) is None
    for kept in (fourth, fifth, sixth):
        assert registry.get(kept.job_id) is not None


def test_list_filters_newest_first_and_limit():
    registry = JobsRegistry()
    alpha = registry.register("op-alpha", chat_id="chat-1")
    beta = registry.register("op-beta", chat_id="chat-2")
    gamma = registry.register("op-gamma", chat_id="chat-1")
    registry.finish(beta.job_id, False, detail="boom")

    assert [r.job_id for r in registry.list()] == [
        gamma.job_id,
        beta.job_id,
        alpha.job_id,
    ]
    assert [r.job_id for r in registry.list(chat_id="chat-1")] == [
        gamma.job_id,
        alpha.job_id,
    ]
    assert [r.job_id for r in registry.list(status="error")] == [beta.job_id]
    assert [r.job_id for r in registry.list(status="queued")] == [
        gamma.job_id,
        alpha.job_id,
    ]
    assert registry.list(chat_id="chat-1", status="error") == []
    assert [r.job_id for r in registry.list(limit=2)] == [
        gamma.job_id,
        beta.job_id,
    ]


def test_list_rejects_unknown_status():
    registry = JobsRegistry()
    registry.register("op")
    with pytest.raises(ValueError):
        registry.list(status="bogus")


def test_concurrent_registration_respects_cap():
    registry = JobsRegistry(max_records=32)
    failures: list[Exception] = []

    def worker(worker_index: int) -> None:
        try:
            for offset in range(20):
                registry.register(f"op-{worker_index}-{offset}")
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    records = registry.list(limit=100000)
    assert len(records) == 32
    # Nothing ever finished, so eviction must have dropped overall-oldest only.
    assert all(record.status == "queued" for record in records)


def test_get_jobs_registry_is_lazy_singleton():
    first = get_jobs_registry()
    second = get_jobs_registry()
    assert first is second
    assert isinstance(first, JobsRegistry)


def test_jobs_and_activity_endpoints():
    env = {
        **os.environ,
        "REQUIRE_AUTH": "false",
        "MCP_JSON_RESPONSE": "true",
        "MCP_STATELESS_HTTP": "true",
    }
    code = r'''
import json

from starlette.testclient import TestClient

from app.jobs_registry import get_jobs_registry

registry = get_jobs_registry()
done_job = registry.register("host.command", chat_id="chat-a")
registry.start(done_job.job_id)
registry.finish(done_job.job_id, True, detail="exit 0", result_excerpt="alpha")
error_job = registry.register("host.write_file", chat_id="chat-b")
registry.finish(error_job.job_id, False, detail="denied")
queued_job = registry.register("host.search", chat_id="chat-a")

from app.mcp_server import mcp

app = mcp.http_app(path="/mcp", transport="streamable-http")

with TestClient(app) as client:
    listing = client.get("/api/v1/jobs").json()
    by_chat = client.get("/api/v1/jobs", params={"chat_id": "chat-a"}).json()
    by_status = client.get("/api/v1/jobs", params={"status": "error"}).json()
    limited = client.get("/api/v1/jobs", params={"limit": 2}).json()
    clamped = client.get("/api/v1/jobs", params={"limit": 9999}).json()
    bad_status = client.get("/api/v1/jobs", params={"status": "bogus"})
    bad_limit = client.get("/api/v1/jobs", params={"limit": "abc"})
    single = client.get("/api/v1/jobs", params={"job_id": done_job.job_id})
    missing = client.get("/api/v1/jobs", params={"job_id": "deadbeef"})
    activity_all = client.get("/api/v1/activity").json()
    activity_chat = client.get(
        "/api/v1/activity", params={"chat_id": "chat-b"}
    ).json()
    index = client.get("/api/v1").json()

result = {
    "seeded": {
        "done": done_job.job_id,
        "error": error_job.job_id,
        "queued": queued_job.job_id,
    },
    "listing": listing,
    "by_chat": by_chat,
    "by_status": by_status,
    "limited": limited,
    "clamped": clamped,
    "bad_status": [bad_status.status_code, bad_status.json()],
    "bad_limit": [bad_limit.status_code, bad_limit.json()],
    "single": [single.status_code, single.json()],
    "missing": [missing.status_code, missing.json()],
    "activity_all": activity_all,
    "activity_chat": activity_chat,
    "index_paths": [entry["path"] for entry in index["endpoints"]],
}
print(json.dumps(result))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=True,
    )
    result = json.loads(proc.stdout)

    listing = result["listing"]
    assert listing["ok"] is True
    assert listing["count"] == 3
    assert [job["op"] for job in listing["jobs"]] == [
        "host.search",
        "host.write_file",
        "host.command",
    ]

    assert result["by_chat"]["count"] == 2
    assert {job["chat_id"] for job in result["by_chat"]["jobs"]} == {"chat-a"}

    assert result["by_status"]["count"] == 1
    assert result["by_status"]["jobs"][0]["status"] == "error"

    assert [job["op"] for job in result["limited"]["jobs"]] == [
        "host.search",
        "host.write_file",
    ]
    assert result["clamped"]["count"] == 3

    assert result["bad_status"][0] == 400
    assert result["bad_status"][1]["error"]["code"] == "INVALID_ARGUMENT"
    assert result["bad_limit"][0] == 400
    assert result["bad_limit"][1]["error"]["code"] == "INVALID_ARGUMENT"

    single_status, single_body = result["single"]
    assert single_status == 200
    assert single_body["ok"] is True
    assert single_body["job"]["job_id"] == result["seeded"]["done"]
    assert single_body["job"]["status"] == "done"
    assert single_body["job"]["result_excerpt"] == "alpha"

    missing_status, missing_body = result["missing"]
    assert missing_status == 404
    assert missing_body["error"]["code"] == "FILE_NOT_FOUND"

    activity_all = result["activity_all"]
    assert activity_all["ok"] is True
    assert activity_all["source"] == "jobs_registry"
    assert activity_all["count"] == 3
    assert activity_all["activity"][0]["job_id"] == result["seeded"]["queued"]

    activity_chat = result["activity_chat"]
    assert activity_chat["count"] == 1
    assert activity_chat["activity"][0]["job_id"] == result["seeded"]["error"]
    assert activity_chat["activity"][0]["status"] == "error"

    assert "/api/v1/jobs" in result["index_paths"]
    assert "/api/v1/activity" in result["index_paths"]
