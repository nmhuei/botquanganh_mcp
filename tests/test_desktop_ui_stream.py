from types import SimpleNamespace

from app.cli.desktop_ui import (
    STREAM_CHIP_KEYS,
    STREAM_DEFAULT_CHIP,
    STREAM_EMPTY_MESSAGE,
    STREAM_JOBS_LIMIT,
    STREAM_JOBS_PATH,
    STREAM_STATUS_GLYPHS,
    StreamRow,
    clip_text,
    filter_stream_rows,
    format_stream_details,
    format_stream_time,
    make_stream_jobs_reader,
    normalize_stream_chip,
    reduce_stream_view,
    shifted_selection,
    stream_copy_line,
    stream_row_from_mapping,
    stream_rows_from_payload,
    stream_error_message,
    stream_status_glyph,
)


def jobs_envelope(*jobs):
    return {"ok": True, "count": len(jobs), "jobs": list(jobs)}


def test_stream_rows_from_payload_builds_models():
    payload = jobs_envelope(
        {
            "job_id": "job-1",
            "op": "host_run_command",
            "chat_id": "chat-77",
            "status": "running",
            "created_at": 1735689600.5,
            "detail": "uptime",
            "result_excerpt": None,
        },
        {
            "job_id": "job-2",
            "op": "read_file",
            "status": "done",
            "created_at": 1735689660,
            "detail": "notes.txt",
            "result_excerpt": "hello",
        },
    )

    rows = stream_rows_from_payload(payload)

    assert rows == [
        StreamRow(
            job_id="job-1",
            op="host_run_command",
            status="running",
            chat_id="chat-77",
            created_at=1735689600.5,
            detail="uptime",
            result_excerpt="",
        ),
        StreamRow(
            job_id="job-2",
            op="read_file",
            status="done",
            chat_id="",
            created_at=1735689660.0,
            detail="notes.txt",
            result_excerpt="hello",
        ),
    ]


def test_stream_rows_tolerate_missing_keys():
    row = stream_row_from_mapping({"job_id": "job-3", "created_at": "not-a-number"})
    assert row is not None
    assert row.op == ""
    assert row.status == ""
    assert row.chat_id == ""
    assert row.created_at is None
    assert row.detail == ""
    assert row.result_excerpt == ""

    empty = stream_row_from_mapping({})
    assert empty == StreamRow(job_id="")

    upper = stream_row_from_mapping({"job_id": "j", "status": "DONE"})
    assert upper is not None
    assert upper.status == "done"


def test_stream_rows_defensive_on_garbage_payloads():
    garbage_payloads = [
        None,
        "junk",
        42,
        [],
        {"ok": True},
        {"jobs": "nope"},
        {"jobs": None},
    ]
    for payload in garbage_payloads:
        assert stream_rows_from_payload(payload) == []

    mixed = stream_rows_from_payload(
        {"jobs": [None, 7, "x", {"job_id": "a"}, {"job_id": "b"}]}
    )
    assert [row.job_id for row in mixed] == ["a", "b"]


def test_stream_filter_unknown_status_under_all_vs_specific_chips():
    rows = [
        StreamRow(job_id="r", op="op", status="running"),
        StreamRow(job_id="d", op="op", status="done"),
        StreamRow(job_id="w", op="op", status="exploded"),
    ]

    assert [row.job_id for row in filter_stream_rows(rows, "all")] == ["r", "d", "w"]
    assert [row.job_id for row in filter_stream_rows(rows, "running")] == ["r"]
    assert [row.job_id for row in filter_stream_rows(rows, "done")] == ["d"]
    assert filter_stream_rows(rows, "error") == []
    # Unknown-status rows never leak into a specific chip's view.


def test_normalize_stream_chip_accepts_only_known_keys():
    assert normalize_stream_chip("ALL") == "all"
    assert normalize_stream_chip("running") == "running"
    assert normalize_stream_chip(" Error ") == "error"
    assert normalize_stream_chip("queued") is None
    assert normalize_stream_chip("bogus") is None
    assert normalize_stream_chip(None) is None
    assert tuple(STREAM_CHIP_KEYS) == ("all", "running", "done", "error")


def test_chip_selection_is_session_local():
    # No settings-persistence convention exists in desktop_ui.py, so the chip
    # lives only in memory: default -> click -> replace, nothing hits disk.
    chip = STREAM_DEFAULT_CHIP
    assert chip == "all"

    chip = normalize_stream_chip("ERROR") or chip
    assert chip == "error"

    chip = normalize_stream_chip("bogus") or chip
    assert chip == "error"


def test_format_stream_time_boundaries():
    assert format_stream_time(None) == "—"
    assert format_stream_time("abc") == "—"
    assert format_stream_time(float("nan")) == "—"
    assert format_stream_time(float("inf")) == "—"
    assert format_stream_time(1e30) == "—"
    assert format_stream_time(0) == "1970-01-01 00:00:00"
    assert format_stream_time(1735689600.9) == "2025-01-01 00:00:00"
    assert format_stream_time("1735689660") == "2025-01-01 00:01:00"


def test_stream_status_glyphs_match_contract():
    assert STREAM_STATUS_GLYPHS == {
        "running": "●",
        "done": "✓",
        "error": "✗",
        "queued": "◔",
    }
    assert stream_status_glyph("running") == "●"
    assert stream_status_glyph("RUNNING") == "●"
    assert stream_status_glyph("queued") == "◔"
    assert stream_status_glyph("weird") == "·"
    assert stream_status_glyph("") == "·"


def test_reduce_stream_view_error_clears_to_muted_line():
    rows = [
        StreamRow(job_id="r", op="op", status="running"),
        StreamRow(job_id="d", op="op", status="done"),
    ]

    visible, notice = reduce_stream_view(rows, chip="all")
    assert visible == rows
    assert notice == ""

    # Connection failure wins over any cached rows.
    visible, notice = reduce_stream_view(rows, chip="all", error_message="refused")
    assert visible == []
    assert notice == "refused"

    visible, notice = reduce_stream_view([], chip="all")
    assert visible == []
    assert notice == STREAM_EMPTY_MESSAGE

    visible, notice = reduce_stream_view(rows, chip="error")
    assert visible == []
    assert notice == STREAM_EMPTY_MESSAGE


def test_shifted_selection_moves_and_clamps():
    order = ["a", "b", "c"]
    assert shifted_selection(order, None, 1) == "a"
    assert shifted_selection(order, "a", 1) == "b"
    assert shifted_selection(order, "c", 1) == "c"
    assert shifted_selection(order, "c", -1) == "b"
    assert shifted_selection(order, "a", -1) == "a"
    assert shifted_selection(order, None, -1) == "c"
    assert shifted_selection(order, "missing", 1) == "a"
    assert shifted_selection([], "a", 1) is None


def test_clip_text_collapses_and_clips():
    assert clip_text("a  b\n\t c", 10) == "a b c"
    assert clip_text("abcdef", 6) == "abcdef"
    assert clip_text("abcdefg", 6) == "abcde…"
    assert len(clip_text("x" * 500, 80)) == 80


def test_stream_details_include_job_id_result_and_copy_line():
    row = StreamRow(
        job_id="job-9",
        op="host_run_command",
        status="error",
        chat_id="chat-5",
        created_at=1735689600,
        detail="ls -la /tmp",
        result_excerpt="permission denied",
    )
    details = format_stream_details(row)
    assert "Job: job-9" in details
    assert "✗ error" in details
    assert "permission denied" in details
    assert f"Copy: {stream_copy_line(row)}" in details
    assert stream_copy_line(row) == "host_run_command error job-9 chat-5"


def test_default_stream_reader_uses_cli_client_conventions(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, token=None, timeout=15.0):
            captured["base_url"] = base_url
            captured["token"] = token
            captured["timeout"] = timeout

        def get(self, path, *, query=None):
            captured["path"] = path
            captured["query"] = query
            return jobs_envelope({"job_id": "job-1", "op": "op", "status": "done"})

    monkeypatch.setattr("app.cli.desktop_ui.RESTClient", FakeClient)
    ctx = SimpleNamespace(
        base_url="http://127.0.0.1:19999/",
        token="tok",
        request_timeout=7.5,
        values={},
    )

    reader = make_stream_jobs_reader(ctx)
    payload = reader()

    assert captured == {
        "base_url": "http://127.0.0.1:19999",
        "token": "tok",
        "timeout": 7.5,
        "path": STREAM_JOBS_PATH,
        "query": {"limit": STREAM_JOBS_LIMIT},
    }
    assert [row.job_id for row in stream_rows_from_payload(payload)] == ["job-1"]


def test_default_stream_reader_falls_back_to_local_bind_values(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, base_url, token=None, timeout=15.0):
            captured["base_url"] = base_url
            captured["timeout"] = timeout

        def get(self, path, *, query=None):
            return {}

    monkeypatch.setattr("app.cli.desktop_ui.RESTClient", FakeClient)
    ctx = SimpleNamespace(
        token="",
        request_timeout=None,
        values={"MCP_CONNECT_HOST": "0.0.0.0", "MCP_PORT": "18488"},
    )

    make_stream_jobs_reader(ctx)

    assert captured["base_url"] == "http://127.0.0.1:18488"
    assert captured["timeout"] == 15.0


def test_fetch_error_path_reduces_cached_rows_to_muted_state(monkeypatch):
    # Simulates what refresh_stream does when the REST call blows up: the
    # worker converts the exception into an empty model plus a muted message.
    cached_rows = [StreamRow(job_id="stale", op="op", status="running")]

    def failing_reader():
        raise ConnectionError("connection refused")

    try:
        failing_reader()
        error = None
    except ConnectionError as exc:
        error = exc

    rows = [] if error is not None else cached_rows
    message = "" if error is None else stream_error_message(error)

    visible, notice = reduce_stream_view(cached_rows, chip="all", error_message=message)
    assert rows == []
    assert visible == []
    assert "Không đọc được luồng job" in notice
    assert "connection refused" in notice
