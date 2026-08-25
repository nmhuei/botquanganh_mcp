import io
import pytest

from app.cli.output import OutputMode
from app.cli.progress import ProgressReporter


@pytest.fixture(autouse=True)
def _ensure_tty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("BQA_NO_PROGRESS", raising=False)


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_prepare_reporter_uses_uv_root_spinner_and_request_rows():
    stream = TTYBuffer()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        message="Starting runtime...",
        total=4,
        stream=stream,
        render_delay=0,
    )
    progress.start()
    progress.set_items(["server", "tunnel", "bridge", "endpoint"])
    progress.complete_item("server")
    progress.finish("Started runtime")
    rendered = stream.getvalue()
    assert "Starting runtime... (0/4)" in rendered
    assert "server" in rendered
    assert "------------------------------" in rendered
    assert "0/1" in rendered
    assert "Starting runtime... (1/4)" in rendered
    assert "Started runtime in " in rendered
    assert "█" not in rendered
    assert "░" not in rendered
    assert "%" not in rendered
    assert "\x1b[2K" in rendered


def test_binary_request_row_matches_uv_download_shape():
    stream = TTYBuffer()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        message="Preparing packages...",
        total=1,
        stream=stream,
        render_delay=0,
    )
    progress.start()
    progress.start_item(
        "torch",
        total=int(502.22 * 1024 * 1024),
        current=int(1.43 * 1024 * 1024),
        binary_bytes=True,
    )
    rendered = stream.getvalue()
    assert "Preparing packages... (0/1)" in rendered
    assert "torch" in rendered
    assert "------------------------------" in rendered
    assert "1.43 MiB" in rendered
    assert "502.22 MiB" in rendered


def test_unknown_size_row_uses_uv_four_dot_form():
    stream = TTYBuffer()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        message="Working...",
        stream=stream,
        render_delay=0,
    )
    progress.start()
    progress.start_item("workspace", total=None)
    assert "workspace ...." in stream.getvalue()


def test_non_tty_keeps_summary_without_live_control_sequences():
    stream = io.StringIO()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        message="Reading health...",
        stream=stream,
    )
    progress.start()
    progress.finish("Checked service health")
    rendered = stream.getvalue()
    assert "Checked service health in " in rendered
    assert "\r" not in rendered
    assert "\x1b[2K" not in rendered


def test_quiet_and_json_progress_are_silent():
    for mode in (OutputMode.QUIET, OutputMode.JSON):
        stream = TTYBuffer()
        progress = ProgressReporter(
            color_mode="never",
            output_mode=mode,
            message="Working...",
            total=2,
            stream=stream,
            render_delay=0,
        )
        progress.start()
        progress.advance("Done")
        progress.finish("Completed")
        assert stream.getvalue() == ""


def test_no_progress_disables_animation_but_keeps_summary():
    stream = TTYBuffer()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        no_progress=True,
        message="Working...",
        total=2,
        stream=stream,
        render_delay=0,
    )
    progress.start()
    progress.advance("Done")
    progress.finish("Completed")
    rendered = stream.getvalue()
    assert "Completed in " in rendered
    assert "(1/2)" not in rendered
    assert "\r" not in rendered


def test_verbose_hides_live_progress_like_uv_printer():
    stream = TTYBuffer()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        verbose=True,
        message="Working...",
        total=2,
        stream=stream,
        render_delay=0,
    )
    progress.start()
    progress.set_items(["one", "two"])
    progress.finish("Completed")
    assert "------------------------------" not in stream.getvalue()
    assert "Completed in " in stream.getvalue()


def test_non_tty_summary_can_be_suppressed_for_passthrough_commands():
    stream = io.StringIO()
    progress = ProgressReporter(
        color_mode="never",
        output_mode=OutputMode.HUMAN,
        summary_non_tty=False,
        message="Running command...",
        stream=stream,
    )
    progress.start()
    progress.finish("Command completed")
    assert stream.getvalue() == ""


# --- Diff rendering / elapsed suffix / single-summary regression coverage ---

import time  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import app.cli.progress as progress_module  # noqa: E402


class WriteCapture:
    """TTY-like fake stream that records every write() call separately."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def write(self, text: str) -> int:
        self.chunks.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return True

    def getvalue(self) -> str:
        return "".join(self.chunks)


def _make_progress(stream: WriteCapture, **overrides: Any) -> ProgressReporter:
    options: dict[str, Any] = {
        "color_mode": "never",
        "output_mode": OutputMode.HUMAN,
        "message": "W",
        "total": None,
        "stream": stream,
        # Huge delay: public mutators skip their implicit _render() so tests
        # drive rendering manually and inspect byte-exact deltas.
        "render_delay": 1e9,
    }
    options.update(overrides)
    return ProgressReporter(**options)


def test_diff_render_rewrites_only_changed_lines():
    stream = WriteCapture()
    progress = _make_progress(stream)
    progress._started_at = time.monotonic()
    progress._render()  # first draw: plain full write, nothing to erase
    assert "\x1b[2K" not in stream.getvalue()

    mark = len(stream.chunks)
    progress._frame = 1  # only the spinner glyph changes
    expected = progress._root_line()
    progress._render()

    delta = "".join(stream.chunks[mark:])
    # Exactly one clear-cell sequence followed by the rewritten root line;
    # no cursor-up navigation and no full-block rewrite for a 1-line block.
    assert delta == "\r\x1b[2K" + expected
    assert delta.count("\x1b[2K") == 1
    assert progress._last_lines == [expected]


def test_diff_render_falls_back_on_row_count_change():
    stream = WriteCapture()
    progress = _make_progress(stream)
    progress._started_at = time.monotonic()
    progress.start_item("alpha")
    progress.start_item("beta")
    progress._render()
    assert progress._drawn_lines == 3

    mark = len(stream.chunks)
    progress.complete_item("alpha")  # block shrinks from 3 lines to 2
    progress._render()

    delta = "".join(stream.chunks[mark:])
    assert progress._drawn_lines == 2
    assert len(progress._last_lines) == 2
    # Fallback: navigate up over the old block and erase every drawn line...
    assert delta.startswith("\r\x1b[2A")
    assert delta.count("\x1b[2K") == 3
    assert "\x1b[1B\r" in delta
    # ...then rewrite the whole (now shorter) block instead of diffing.
    assert "\n".join(progress._last_lines) in delta


def test_close_resets_last_lines():
    stream = WriteCapture()
    progress = _make_progress(stream)
    progress._started_at = time.monotonic()
    progress._render()
    assert progress._last_lines
    progress.close(clear=True)
    assert progress._last_lines == []
    assert progress._drawn_lines == 0


def test_root_line_elapsed_suffix_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = WriteCapture()
    progress = _make_progress(stream)
    now = 10_000.0
    monkeypatch.setattr(
        progress_module, "time", SimpleNamespace(monotonic=lambda: now)
    )

    progress._started_at = now - 1.9  # below the 2s threshold
    assert "·" not in progress._root_line()

    progress._started_at = now - 5.0  # well past the threshold
    line = progress._root_line()
    assert "·" in line
    assert line.endswith(" · 5s")


def test_finish_prints_single_summary_without_extra_frame():
    stream = WriteCapture()
    progress = _make_progress(stream)
    progress._started_at = time.monotonic()
    progress._render()
    drawn = progress._drawn_lines
    mark = len(stream.chunks)

    progress.finish("Started runtime")

    delta = "".join(stream.chunks[mark:])
    assert stream.getvalue().count("Started runtime in ") == 1
    # Only the close(clear=True) erase bytes: no final frame was rendered
    # (a final frame would add another \x1b[2K + spinner content here).
    assert delta.count("\x1b[2K") == drawn
    assert not any(glyph in delta for glyph in progress_module._SPINNER)
    # Summary is the very last thing printed, terminated by one newline.
    assert stream.chunks[-1] == "\n"
    assert stream.chunks[-2].startswith("Started runtime in ")


def test_diff_render_writes_only_changed_rows_in_multi_row_block():
    stream = WriteCapture()
    progress = _make_progress(stream)
    progress._started_at = time.monotonic()
    progress.start_item("alpha")
    progress.start_item("beta")
    progress._render()
    mark = len(stream.chunks)

    progress.update_item("beta", 1)  # beta row content changes...
    progress._frame = 1  # ...and the root spinner ticks
    progress._render()

    delta = "".join(stream.chunks[mark:])
    # Same 3-line shape: only the 2 changed cells are cleared and rewritten.
    assert delta.count("\x1b[2K") == 2
    assert "alpha" not in delta  # unchanged row produced zero output bytes
