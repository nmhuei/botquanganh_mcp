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
