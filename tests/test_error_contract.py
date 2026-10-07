import json

import pytest

import app.config
from app.error_contract import (
    ERROR_SPECS,
    ServiceBusyError,
    format_error_code,
    format_exception_error,
    http_status_for_exception,
    http_status_for_result,
)
from app.rest_api import openapi_document


@pytest.mark.parametrize(
    ("exc", "code", "status"),
    [
        (ValueError("bad"), "INVALID_ARGUMENT", 400),
        (NotADirectoryError("bad dir"), "INVALID_ARGUMENT", 400),
        (PermissionError("blocked"), "POLICY_BLOCKED", 403),
        (FileNotFoundError("missing"), "FILE_NOT_FOUND", 404),
        (TimeoutError("late"), "TIMEOUT", 408),
        (FileExistsError("exists"), "FILE_EXISTS", 409),
        (ServiceBusyError("full"), "SERVICE_BUSY", 503),
        (RuntimeError("sensitive internal detail"), "INTERNAL_ERROR", 500),
    ],
)
def test_exception_taxonomy_is_consistent(exc, code, status):
    body = format_exception_error(exc)
    assert body["ok"] is False
    assert body["error"]["code"] == code
    assert http_status_for_exception(exc) == status
    if code == "INTERNAL_ERROR":
        assert body["error"]["message"] == "Internal server error."
        assert "sensitive" not in body["error"]["message"]


def test_public_error_message_redacts_known_paths(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app.config, "HOST_WORKSPACE_DIR", workspace)
    body = format_exception_error(FileNotFoundError(f"Path not found: {workspace}/a.txt"))
    assert str(workspace) not in body["error"]["message"]
    assert "<workspace>/a.txt" in body["error"]["message"]


def test_result_status_uses_shared_error_codes():
    for code, spec in ERROR_SPECS.items():
        result = {"ok": False, "error": {"code": code, "message": "x"}}
        assert http_status_for_result(result) == spec.http_status
    assert http_status_for_result({"ok": False, "exit_code": 9}) == 200
    assert http_status_for_result({"ok": True}) == 200


def test_rate_limit_error_shape():
    body = format_error_code(
        "RATE_LIMITED", message="Rate limit exceeded.", extra={"retry_after": 3}
    )
    assert body == {
        "ok": False,
        "error": {
            "code": "RATE_LIMITED",
            "message": "Rate limit exceeded.",
            "suggestion": ERROR_SPECS["RATE_LIMITED"].suggestion,
            "retry_after": 3,
        },
    }


def test_openapi_exposes_shared_error_contract():
    document = openapi_document()
    schema = document["components"]["schemas"]["ErrorResponse"]
    codes = schema["properties"]["error"]["properties"]["code"]["enum"]
    assert codes == sorted(ERROR_SPECS)
    responses = document["paths"]["/api/v1/files/content"]["get"]["responses"]
    for status in ("400", "401", "403", "404", "408", "409", "429", "500", "503"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }


def test_error_schema_is_json_serializable():
    json.dumps(openapi_document())


def test_domain_exceptions_not_masked():
    from app.chat_workspace import CapacityError, QuotaError, RootFullError, SquatError
    from app.chat_errors import ChatCatalogError

    # E2
    e2 = format_exception_error(CapacityError(count=5, limit=5))
    assert e2["ok"] is False
    assert e2["error"]["code"] == "E2"
    assert "5 of 5" in e2["error"]["message"]
    assert http_status_for_exception(CapacityError()) == 409

    # E3
    e3 = format_exception_error(QuotaError("over quota", chat_id="chat-1", used_bytes=100, quota_bytes=50))
    assert e3["ok"] is False
    assert e3["error"]["code"] == "E3"
    assert "100 of 50" in e3["error"]["message"]
    assert http_status_for_exception(QuotaError("x")) == 413

    # E4
    e4 = format_exception_error(RootFullError(free_bytes=500, required_bytes=1000))
    assert e4["ok"] is False
    assert e4["error"]["code"] == "E4"
    assert "500 free bytes" in e4["error"]["message"]
    assert http_status_for_exception(RootFullError()) == 507

    # E5
    e5 = format_exception_error(SquatError(path="/tmp/squat"))
    assert e5["ok"] is False
    assert e5["error"]["code"] == "E5"
    assert "/tmp/squat" in e5["error"]["message"]
    assert http_status_for_exception(SquatError()) == 409

    # E6
    e6 = format_exception_error(ChatCatalogError("E6", chat_id="chat-bound-1"))
    assert e6["ok"] is False
    assert e6["error"]["code"] == "E6"
    assert http_status_for_exception(ChatCatalogError("E6")) == 400

