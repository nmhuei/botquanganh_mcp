from app.tools.health import get_capabilities, health_check


def test_health_reports_host_profile():
    result = health_check()
    assert result["ok"] is True
    assert result["profile"] == "host"
    assert result["service"] == "botquanganh-host-mcp"


def test_capabilities_expose_only_host_features():
    result = get_capabilities()
    assert result["ok"] is True
    assert result["profile"] == "host"
    assert result["features"] == {
        "host_filesystem": True,
        "host_command_execution": True,
        "host_knowledge": True,
        "installed_tool_inventory": True,
    }
    assert result["host"]["caller_approval_parameter"] is False
