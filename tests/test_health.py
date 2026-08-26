from app.tools.health import get_capabilities, health_check


def test_health_reports_host_profile():
    result = health_check()
    assert result["ok"] is True
    assert result["profile"] == "host"
    assert result["service"] == "botquanganh-host-mcp"
    assert "mcp_http_requests_total" in result["metrics"]
    assert "mcp_tool_calls_total" in result["transport"]


def test_capabilities_expose_host_core_features_only():
    result = get_capabilities()
    assert result["ok"] is True
    assert result["profile"] == "host"
    assert result["features"] == {
        "host_filesystem": True,
        "host_command_execution": True,
        "host_knowledge": True,
        "ctf_fetch_result_ui": True,
        "installed_tool_inventory": True,
    }
    assert result["host"]["caller_approval_parameter"] is False
    assert len(result["tools"]) == 16
    assert all(not name.startswith("agent_") for name in result["tools"])
