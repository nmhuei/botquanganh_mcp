"""Behavioral tests for the scoped, single-target CTF request service."""

from __future__ import annotations

import importlib
import socket

import httpx
import pytest

from app.chat_workspace import WorkspaceManager
from app.ctf.case_scope import create_case


PUBLIC_ADDRESS = "93.184.216.34"
MAX_RESPONSE_BYTES = 200_000


def _target_request():
    """Import lazily so the initial TDD run reports missing implementation."""
    try:
        return importlib.import_module("app.ctf.target_request")
    except ModuleNotFoundError as exc:
        pytest.fail(f"scoped target request service is missing: {exc}")


@pytest.fixture()
def workspace_manager(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces", bind_wait_seconds=0.01)
    manager.create_or_bind("request001")
    return manager


def _resolver_for(address=PUBLIC_ADDRESS, events=None):
    def resolve(hostname, port, *, type):
        if events is not None:
            events.append(("dns", hostname, port))
        assert type == socket.SOCK_STREAM
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        socket_address = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address)]

    return resolve


def _create_local_case(workspace_manager, *origins):
    return create_case(
        workspace_manager,
        "request001",
        label="local web",
        authorized_origins=origins or ("http://localhost:8080",),
        network_mode="local_instance",
    )


def _create_public_case(workspace_manager, *origins):
    return create_case(
        workspace_manager,
        "request001",
        label="public web",
        authorized_origins=origins or ("https://challenge.example",),
        network_mode="public_https",
        resolver=_resolver_for(),
    )


def _request(
    service,
    workspace_manager,
    case,
    client,
    *,
    origin=None,
    resolver=None,
    **kwargs,
):
    return service.request_target(
        workspace_manager,
        "request001",
        case_id=case.case_id,
        origin=origin or case.authorized_origins[0],
        client=client,
        resolver=resolver or _resolver_for(),
        **kwargs,
    )


def test_get_uses_only_exact_case_origin_and_caller_path_query(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, headers={"Content-Type": "text/plain"}, text="flag form")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _request(
            service,
            workspace_manager,
            case,
            client,
            path="/login?next=%2Fflag",
            headers={"Accept": "text/plain", "X-Host-Hint": "allowed"},
        )

    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == "http://localhost:8080/login?next=%2Fflag"
    assert seen[0].headers["accept"] == "text/plain"
    assert seen[0].headers["x-host-hint"] == "allowed"
    assert result == {
        "ok": True,
        "method": "GET",
        "url": "http://localhost:8080/login?next=%2Fflag",
        "status_code": 200,
        "content_type": "text/plain",
        "body": "flag form",
        "body_bytes": 9,
        "body_truncated": False,
        "redirects": [],
    }


def test_head_and_post_are_supported_with_post_utf8_body(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    seen = []

    def handler(request):
        seen.append((request.method, request.content))
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        head_result = _request(
            service, workspace_manager, case, client, method="head", path="/health"
        )
        post_result = _request(
            service,
            workspace_manager,
            case,
            client,
            method="POST",
            path="/submit",
            body="xin chào 🌍",
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )

    assert seen == [("HEAD", b""), ("POST", "xin chào 🌍".encode())]
    assert head_result["method"] == "HEAD"
    assert head_result["body"] == ""
    assert post_result["method"] == "POST"


@pytest.mark.parametrize("method", ["PUT", "DELETE", "OPTIONS", "PATCH", "TRACE", ""])
def test_rejects_unsupported_methods_without_sending(workspace_manager, method):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    sent = []

    with httpx.Client(transport=httpx.MockTransport(lambda request: sent.append(request))) as client:
        with pytest.raises(ValueError, match="GET, HEAD, or POST"):
            _request(service, workspace_manager, case, client, method=method)

    assert sent == []


def test_rejects_body_for_get_or_head(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        for method in ("GET", "HEAD"):
            with pytest.raises(ValueError, match="POST"):
                _request(
                    service,
                    workspace_manager,
                    case,
                    client,
                    method=method,
                    body="even an explicit empty body" if method == "GET" else "",
                )


def test_requires_current_case_id_and_exact_selected_origin(workspace_manager):
    service = _target_request()
    first = _create_local_case(workspace_manager, "http://localhost:8080")
    active = _create_local_case(workspace_manager, "http://localhost:9090")
    sent = []

    with httpx.Client(transport=httpx.MockTransport(lambda request: sent.append(request))) as client:
        with pytest.raises(ValueError, match="case_id"):
            _request(service, workspace_manager, first, client)
        with pytest.raises(ValueError, match="authorized origin"):
            _request(
                service,
                workspace_manager,
                active,
                client,
                origin="http://LOCALHOST:9090",
            )

    assert sent == []


@pytest.mark.parametrize(
    "path",
    [
        "https://challenge.example/path",
        "//challenge.example/path",
        "//user:password@challenge.example/path",
        "/path#fragment",
        "/safe\\@evil.example/path",
        "/line\r\nX-Evil: true",
    ],
)
def test_rejects_path_authority_fragment_and_header_widening(
    workspace_manager, path
):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    sent = []

    with httpx.Client(transport=httpx.MockTransport(lambda request: sent.append(request))) as client:
        with pytest.raises(ValueError, match="path"):
            _request(service, workspace_manager, case, client, path=path)

    assert sent == []


@pytest.mark.parametrize(
    "header",
    ["Host", "host", "Content-Length", "CONNECTION", "Transfer-Encoding"],
)
def test_rejects_exact_forbidden_request_headers(workspace_manager, header):
    service = _target_request()
    case = _create_local_case(workspace_manager)

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        with pytest.raises(ValueError, match="header"):
            _request(
                service,
                workspace_manager,
                case,
                client,
                method="POST",
                headers={header: "caller-controlled"},
                body="x",
            )


@pytest.mark.parametrize(
    "headers",
    [
        {f"X-{index}": "x" for index in range(33)},
        {"X" * 129: "x"},
        {"X-Large": "x" * 4097},
        {"X-A": "x" * 4096, "X-B": "y" * 4096, "X-C": "z" * 4096, "X-D": "q" * 4096},
    ],
)
def test_rejects_request_headers_over_count_or_byte_bounds(workspace_manager, headers):
    service = _target_request()
    case = _create_local_case(workspace_manager)

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        with pytest.raises(ValueError, match="header"):
            _request(service, workspace_manager, case, client, headers=headers)


def test_rejects_non_text_and_oversized_utf8_body_before_sending(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    sent = []

    with httpx.Client(transport=httpx.MockTransport(lambda request: sent.append(request))) as client:
        with pytest.raises(ValueError, match="body"):
            _request(service, workspace_manager, case, client, method="POST", body=b"raw")
        with pytest.raises(ValueError, match="65,536"):
            _request(service, workspace_manager, case, client, method="POST", body="é" * 32_769)

    assert sent == []


def test_does_not_apply_client_default_headers_cookies_or_auth(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    seen_headers = []

    def handler(request):
        seen_headers.append(dict(request.headers))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/finish", "Set-Cookie": "server=secret"})
        return httpx.Response(200, text="done")

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"X-Ambient": "must-not-leak"},
        cookies={"ambient": "must-not-leak"},
        auth=("ambient", "must-not-leak"),
        follow_redirects=True,
    ) as client:
        result = _request(
            service,
            workspace_manager,
            case,
            client,
            path="/start",
            follow_redirects=True,
        )

    assert result["body"] == "done"
    assert len(seen_headers) == 2
    for headers in seen_headers:
        assert "x-ambient" not in headers
        assert "authorization" not in headers
        assert "cookie" not in headers


def test_uses_fixed_timeout_and_does_not_retry_transport_errors(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    seen = []

    def handler(request):
        seen.append(request)
        assert request.extensions["timeout"] == {
            "connect": 10.0,
            "read": 10.0,
            "write": 10.0,
            "pool": 10.0,
        }
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), timeout=999) as client:
        with pytest.raises(RuntimeError, match="HTTP GET failed"):
            _request(service, workspace_manager, case, client)

    assert len(seen) == 1


def test_bounds_response_bytes_and_reports_truncation(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)

    def handler(_request):
        return httpx.Response(200, content=b"a" * (MAX_RESPONSE_BYTES + 1))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _request(service, workspace_manager, case, client)

    assert result["body"] == "a" * MAX_RESPONSE_BYTES
    assert result["body_bytes"] == MAX_RESPONSE_BYTES
    assert result["body_truncated"] is True


def test_public_dns_rebinding_is_rejected_immediately_before_http(workspace_manager):
    service = _target_request()
    case = _create_public_case(workspace_manager)
    answers = iter((PUBLIC_ADDRESS, "127.0.0.1"))
    sent = []

    def rebinding_resolver(hostname, port, *, type):
        return _resolver_for(next(answers))(hostname, port, type=type)

    with httpx.Client(transport=httpx.MockTransport(lambda request: sent.append(request))) as client:
        with pytest.raises(ValueError, match="global"):
            _request(
                service,
                workspace_manager,
                case,
                client,
                resolver=rebinding_resolver,
            )

    assert sent == []


def test_local_loopback_stays_exact_and_never_uses_public_dns(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager, "http://127.0.0.2:8080")
    seen = []

    def no_dns(*_args, **_kwargs):
        raise AssertionError("local literal loopback must not use DNS")

    with httpx.Client(
        transport=httpx.MockTransport(lambda request: seen.append(str(request.url)) or httpx.Response(200))
    ) as client:
        result = _request(
            service,
            workspace_manager,
            case,
            client,
            resolver=no_dns,
            path="/only",
        )

    assert seen == ["http://127.0.0.2:8080/only"]
    assert result["status_code"] == 200


def test_redirects_are_manual_capped_and_dns_checked_before_each_send(workspace_manager):
    service = _target_request()
    case = _create_public_case(workspace_manager)
    events = []

    def handler(request):
        events.append(("http", str(request.url)))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/finish?ok=1"})
        return httpx.Response(200, text="done")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = _request(
            service,
            workspace_manager,
            case,
            client,
            resolver=_resolver_for(events=events),
            path="/start",
            follow_redirects=True,
        )

    http_indexes = [index for index, event in enumerate(events) if event[0] == "http"]
    assert len(http_indexes) == 2
    assert all(events[index - 1][0] == "dns" for index in http_indexes)
    assert result["url"] == "https://challenge.example/finish?ok=1"
    assert result["redirects"] == [
        {
            "status_code": 302,
            "from": "https://challenge.example/start",
            "to": "https://challenge.example/finish?ok=1",
        }
    ]


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/steal",
        "https://user:password@challenge.example/steal",
        "/finish#secret",
    ],
)
def test_rejects_redirects_outside_exact_case_authority(workspace_manager, location):
    service = _target_request()
    case = _create_public_case(workspace_manager)
    sent = []

    def handler(request):
        sent.append(str(request.url))
        return httpx.Response(302, headers={"Location": location})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="redirect|authorized origin|credentials|fragment"):
            _request(
                service,
                workspace_manager,
                case,
                client,
                resolver=_resolver_for(),
                follow_redirects=True,
            )

    assert sent == ["https://challenge.example/"]


def test_rejects_unscoped_redirect_before_resolving_its_hostname(workspace_manager):
    service = _target_request()
    case = _create_public_case(workspace_manager)
    lookups = []

    def scoped_resolver(hostname, port, *, type):
        lookups.append(hostname)
        return _resolver_for()(hostname, port, type=type)

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                302, headers={"Location": "https://unscoped.example/steal"}
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="authorized origin"):
            _request(
                service,
                workspace_manager,
                case,
                client,
                resolver=scoped_resolver,
                follow_redirects=True,
            )

    assert "unscoped.example" not in lookups


def test_allows_redirect_to_another_exact_authorized_origin_and_strips_secrets(
    workspace_manager,
):
    service = _target_request()
    case = _create_public_case(
        workspace_manager,
        "https://challenge.example",
        "https://assets.example:8443",
    )
    seen = []

    def resolver(hostname, port, *, type):
        assert hostname in {"challenge.example", "assets.example"}
        return _resolver_for()(hostname, port, type=type)

    def handler(request):
        seen.append((str(request.url), dict(request.headers)))
        if request.url.host == "challenge.example":
            return httpx.Response(307, headers={"Location": "HTTPS://ASSETS.EXAMPLE:8443/next"})
        return httpx.Response(200, text="asset")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _request(
            service,
            workspace_manager,
            case,
            client,
            resolver=resolver,
            path="/start",
            headers={
                "Authorization": "Bearer explicit-secret",
                "Cookie": "explicit=secret",
                "X-Challenge": "kept",
            },
            follow_redirects=True,
        )

    assert len(seen) == 2
    assert seen[0][1]["authorization"] == "Bearer explicit-secret"
    assert seen[0][1]["cookie"] == "explicit=secret"
    assert "authorization" not in seen[1][1]
    assert "cookie" not in seen[1][1]
    assert seen[1][1]["x-challenge"] == "kept"
    assert result["url"] == "https://assets.example:8443/next"


def test_post_redirect_method_rules_are_bounded_and_explicit(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    seen = []

    def handler(request):
        seen.append((request.method, request.content))
        if request.url.path == "/submit":
            return httpx.Response(303, headers={"Location": "/result"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _request(
            service,
            workspace_manager,
            case,
            client,
            method="POST",
            path="/submit",
            body="answer=42",
            follow_redirects=True,
        )

    assert seen == [("POST", b"answer=42"), ("GET", b"")]


def test_redirect_limit_stops_after_four_total_requests(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)
    sent = []

    def handler(request):
        sent.append(str(request.url))
        return httpx.Response(302, headers={"Location": f"/hop/{len(sent)}"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Redirect limit"):
            _request(
                service,
                workspace_manager,
                case,
                client,
                path="/start",
                follow_redirects=True,
            )

    assert len(sent) == 4


def test_disabled_redirects_return_the_first_bounded_response(workspace_manager):
    service = _target_request()
    case = _create_local_case(workspace_manager)

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(302, headers={"Location": "https://evil.example/"}, text="move")
        ),
        follow_redirects=True,
    ) as client:
        result = _request(
            service,
            workspace_manager,
            case,
            client,
            follow_redirects=False,
        )

    assert result["status_code"] == 302
    assert result["body"] == "move"
    assert result["redirects"] == []
