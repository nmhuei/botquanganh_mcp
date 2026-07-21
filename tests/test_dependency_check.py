import json

from app.dependency_check import PROJECT_ROOTS, check_project_dependencies, main


def test_project_dependency_closure_is_consistent():
    result = check_project_dependencies()
    assert result["ok"] is True, result["errors"]
    assert result["errors"] == []
    assert set(PROJECT_ROOTS) <= set(result["roots"])
    assert result["closure_count"] >= len(PROJECT_ROOTS)
    assert "fastmcp" in result["closure"]
    assert "python-dotenv" in result["closure"]


def test_dependency_check_json_contract(capsys):
    assert main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["strict_foreign"] is False
    assert isinstance(payload["foreign_packages"], list)
    assert payload["foreign_package_count"] == len(payload["foreign_packages"])
