import socket

import httpx
import pytest

from app.tools.ctf_http import ctf_fetch_url, fetch_ctf_url


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )


def test_fetches_one_https_get_with_bounded_body(public_dns):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="challenge page")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    try:
        result = fetch_ctf_url("https://challenge.example/", client=client)
    finally:
        client.close()

    assert result["ok"] is True
    assert result["method"] == "GET"
    assert result["body"] == "challenge page"
    assert result["redirects"] == []
    assert [request.method for request in seen] == ["GET"]


def test_follows_only_validated_https_redirects(public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/challenge"})
        return httpx.Response(200, text="flag form")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    try:
        result = fetch_ctf_url("https://challenge.example/start", client=client)
    finally:
        client.close()

    assert result["url"] == "https://challenge.example/challenge"
    assert result["body"] == "flag form"
    assert result["redirects"] == [
        {
            "status_code": 302,
            "from": "https://challenge.example/start",
            "to": "https://challenge.example/challenge",
        }
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://challenge.example/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://user:password@challenge.example/",
    ],
)
def test_rejects_non_public_or_non_https_urls(url, public_dns):
    with pytest.raises(ValueError):
        fetch_ctf_url(url)


import app.config


@pytest.fixture(autouse=True)
def default_env(monkeypatch):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "off", raising=False)


def test_tool_returns_shared_error_for_invalid_url():
    result = ctf_fetch_url("http://challenge.example/")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"


def test_tool_gated_under_enforce(monkeypatch):
    monkeypatch.setattr(app.config, "ATTRIBUTION_MODE", "enforce", raising=False)
    result = ctf_fetch_url("https://challenge.example/")
    assert result["ok"] is False
    assert result["error"]["code"] == "E6"
