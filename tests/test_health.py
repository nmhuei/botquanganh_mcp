from app.tools.health import get_capabilities, health_check


def test_health_reports_host_profile():
    result = health_check()
    assert result["ok"] is True
    assert result["profile"] == "host"
    assert result["service"] == "botquanganh-host-mcp"


def test_capabilities_expose_host_and_optional_agent_runtime_features():
    result = get_capabilities()
    assert result["ok"] is True
    assert result["profile"] == "host"
    assert result["features"] == {
        "host_filesystem": True,
        "host_command_execution": True,
        "host_knowledge": True,
        "installed_tool_inventory": True,
        "agent_runtime_control_plane": True,
    }
    assert result["host"]["caller_approval_parameter"] is False
    assert result["agent_runtime"]["optional_dependency"] is True
    assert "agent_run_start" in result["agent_runtime"]["tools"]
    assert "agent_runtime_health" in result["tools"]
