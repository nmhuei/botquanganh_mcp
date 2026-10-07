import httpx
import pytest
from app.tools.web_intelligence import web_intelligence, _parse_html_intelligence, _extract_flags
from app.chat_workspace import WorkspaceManager


def test_web_intelligence_enforce_mode_requires_chat_id(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    res = web_intelligence(url="http://example.com", chat_id=None)
    assert res["ok"] is False
    assert res["error"]["code"] == "E6"


def test_html_intelligence_parser():
    sample_html = """
    <html>
      <head>
        <meta name="author" content="BotQuangAnh">
      </head>
      <body>
        <!-- SECRET_LEAK: admin_password_123 -->
        <h1>Welcome</h1>
        <form>
          <input type="hidden" name="csrf_token" value="super_secret_token_abc">
          <input type="text" name="user">
        </form>
        <p>The flag is flag{sample_ctf_flag_winner} here!</p>
      </body>
    </html>
    """
    text, intel = _parse_html_intelligence(sample_html)
    assert "Welcome" in text
    assert any("SECRET_LEAK" in c for c in intel["comments"])
    assert any(h["name"] == "csrf_token" and h["value"] == "super_secret_token_abc" for h in intel["hidden_inputs"])
    assert intel["meta"].get("author") == "BotQuangAnh"

    flags = _extract_flags(sample_html)
    assert "flag{sample_ctf_flag_winner}" in flags


def test_web_intelligence_mocked_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-web"
    mgr = WorkspaceManager(tmp_path)
    mgr.create_or_bind(chat_id)

    def mock_send(self, request, **kwargs):
        content = b"<html><!-- comment1 --><body>flag{mock_flag_123}</body></html>"
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "text/html", "Server": "nginx/1.24"},
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "send", mock_send)

    res = web_intelligence(url="http://127.0.0.1:8080/test", chat_id=chat_id)
    assert res["ok"] is True
    assert res["status_code"] == 200
    assert "flag{mock_flag_123}" in res["intelligence"]["flags"]
    assert "comment1" in res["intelligence"]["comments"]
    assert res["intelligence"]["headers"].get("server") == "nginx/1.24"
    assert "widget_uri" in res



def test_web_intelligence_mocked_post_method_and_plain_text(monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-web-post"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    seen = {}

    def mock_send(self, request, **kwargs):
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            content=b"plain mocked response",
            headers={"Content-Type": "text/plain"},
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "send", mock_send)

    res = web_intelligence(
        url="http://127.0.0.1:8080/plain",
        method="POST",
        chat_id=chat_id,
    )

    assert res["ok"] is True
    assert seen["method"] == "POST"
    assert res["body"] == "plain mocked response"
    assert res["intelligence"]["flags"] == []


def test_web_intelligence_rejects_invalid_url_without_network(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")

    def fail_request(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(httpx.Client, "request", fail_request)

    res = web_intelligence(url="ftp://example.com/resource")

    assert res["ok"] is False
    assert res["error"]["code"] == "INVALID_URL"
