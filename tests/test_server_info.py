import pytest
from app import config
from app.tools.server_info import server_info


def test_server_info_bootstrap():
    res = server_info()
    assert res["ok"] is True
    assert res["version"] == config.VERSION
    assert "sandbox_trash_dir" in res
    assert "bqa-trash" in res["sandbox_trash_dir"]
    assert "limits" in res
    assert len(res["super_tools"]) == 8
    tool_names = {t["name"] for t in res["super_tools"]}
    assert tool_names == {
        "workspace_explore",
        "workspace_edit",
        "workspace_search",
        "terminal_execute",
        "task",
        "web_intelligence",
        "server_info",
        "workspace_context",
    }



def test_server_info_reports_configured_limits_without_sensitive_values():
    res = server_info()

    limits = res["limits"]
    assert limits["max_single_file_bytes"] == 30_000_000
    assert limits["max_output_bytes"] == 5_000_000
    assert limits["default_timeout_seconds"] == 60
    assert limits["max_timeout_seconds"] == 300
    assert limits["max_concurrent_commands"] == 100

    assert "secret" not in str(res).lower()
    assert "token" not in str(res).lower()


def test_server_info_status_output_is_stable_and_descriptive():
    res = server_info()

    assert res["service"] == "botquanganh-host-mcp"
    assert res["attribution_mode"] == "enforce"
    assert isinstance(res["server_time"], str)
    assert res["runtime_metrics"]["error_count"] >= 0
    assert res["runtime_metrics"]["client_error_count"] >= 0
    assert res["runtime_metrics"]["rate_limit_hits"] >= 0
