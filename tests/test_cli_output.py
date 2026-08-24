import io
import json

from app.cli.output import (
    Renderer,
    emit_json,
    human_duration,
    pad_to_width,
    redact_data,
    strip_ansi,
    truncate_visible,
    visible_width,
    wrap_visible,
)


def test_redaction_hides_nested_secrets(capsys):
    payload = {
        "GATEWAY_TOKEN": "secret",  # pragma: allowlist secret
        "nested": {"api_key": "value", "safe": "ok"},  # pragma: allowlist secret
    }
    emit_json(payload)
    result = json.loads(capsys.readouterr().out)
    assert result["GATEWAY_TOKEN"] == "<redacted>"
    assert result["nested"]["api_key"] == "<redacted>"
    assert result["nested"]["safe"] == "ok"


def test_human_duration():
    assert human_duration(0) == "0s"
    assert human_duration(61) == "1m 1s"
    assert human_duration(90061) == "1d 1h 1m 1s"


def test_redact_data_preserves_empty_secret():
    assert redact_data({"token": ""}) == {"token": ""}


def test_ansi_and_unicode_visible_width():
    assert strip_ansi("\x1b[31mLỗi\x1b[0m") == "Lỗi"
    assert visible_width("Tiếng Việt") == 10
    assert visible_width("工具") == 4
    assert visible_width("\x1b[31m● healthy\x1b[0m") == 9


def test_visible_truncation_and_padding():
    assert truncate_visible("đường-dẫn-rất-dài", 10).endswith("…")
    assert visible_width(truncate_visible("工具工具工具", 5)) <= 5
    assert visible_width(pad_to_width("工具", 8)) == 8


def test_wrap_visible_preserves_width():
    lines = wrap_visible("Nội dung dài cần xuống dòng chính xác", 12)
    assert all(visible_width(line) <= 12 for line in lines)
    assert " ".join(lines) == "Nội dung dài cần xuống dòng chính xác"


def test_renderer_width_matrix_has_no_overflow_or_trailing_spaces():
    for width in (50, 60, 70, 80, 100, 120, 160):
        stream = io.StringIO()
        renderer = Renderer(color_mode="never", stream=stream, width=width)
        renderer.header("Trạng thái hệ thống", "Host MCP bridge")
        renderer.blank()
        renderer.status("healthy")
        renderer.blank()
        renderer.facts(
            [
                ("Endpoint", "https://example.test/a/very/long/mcp/path"),
                ("Workspace", "/home/light/GitHub/botquanganh_mcp"),
            ]
        )
        renderer.blank()
        renderer.table(
            ["PORT", "ROLE", "STATE", "DESCRIPTION"],
            [[40001, "primary", "healthy", "Vietnamese: kết nối ổn định"]],
            numeric_columns=[0],
        )
        for line in stream.getvalue().splitlines():
            assert line == line.rstrip()
            assert visible_width(line) <= width


def test_renderer_uses_linear_borderless_layout():
    stream = io.StringIO()
    renderer = Renderer(color_mode="never", stream=stream, width=100)
    renderer.table(["NAME", "STATE"], [["server", "healthy"]])
    output = stream.getvalue()
    assert "┌" not in output
    assert "│" not in output
    assert "---" not in output


def test_color_policy_matrix(monkeypatch):
    from app.cli.output import color_enabled

    stream = io.StringIO()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert color_enabled("never", stream) is False
    assert color_enabled("always", stream) is True
    assert color_enabled("auto", stream) is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert color_enabled("auto", stream) is False


def test_colored_renderer_still_respects_visible_width():
    stream = io.StringIO()
    renderer = Renderer(color_mode="always", stream=stream, width=60)
    renderer.header("Trạng thái", "Unicode và ANSI")
    renderer.blank()
    renderer.status("healthy")
    renderer.blank()
    renderer.checks([{"status": "pass", "name": "kết_nối", "message": "ổn định"}])
    for line in stream.getvalue().splitlines():
        assert visible_width(line) <= 60


def test_copyable_value_never_inserts_hard_wraps():
    url = "https://actions-beneath-created-syndication.trycloudflare.com/mcp"
    stream = io.StringIO()
    renderer = Renderer(color_mode="never", stream=stream, width=20)

    renderer.copyable_value("Endpoint", url)

    assert stream.getvalue().splitlines() == ["  Endpoint", url]


def test_error_renderer_uses_compact_uv_style_tree():
    stream = io.StringIO()
    renderer = Renderer(color_mode="never", stream=stream, width=80)
    renderer.error(
        "Could not complete `start`",
        "Connector URL is unavailable.",
        "bqa doctor",
    )
    rendered = stream.getvalue()
    assert "× Could not complete `start`" in rendered
    assert "╰─▶ Connector URL is unavailable." in rendered
    assert "hint: bqa doctor" in rendered
    assert "Operation failed" not in rendered
