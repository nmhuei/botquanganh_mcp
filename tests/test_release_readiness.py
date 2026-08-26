import re
from pathlib import Path


def test_github_quality_workflow_uses_pinned_actions_and_least_privilege():
    repo = Path(__file__).resolve().parents[1]
    workflow = (repo / ".github" / "workflows" / "quality.yml").read_text(
        encoding="utf-8"
    )
    action_refs = re.findall(r"uses:\s*([^\s]+)", workflow)
    assert action_refs
    for reference in action_refs:
        owner_repo, revision = reference.rsplit("@", 1)
        assert re.fullmatch(r"[0-9a-f]{40}", revision), reference
        assert owner_repo in {
            "actions/checkout",
            "actions/setup-python",
            "astral-sh/setup-uv",
        }
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "./scripts/quality_gate.sh" in workflow


def test_dependabot_covers_python_and_github_actions():
    repo = Path(__file__).resolve().parents[1]
    config = (repo / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: pip" in config
    assert "package-ecosystem: github-actions" in config
    assert config.count("interval: weekly") == 2


def test_release_and_security_documentation_exists_and_is_linked():
    repo = Path(__file__).resolve().parents[1]
    for relative in (
        "SECURITY.md",
        "docs/ARCHITECTURE.md",
        "docs/OPERATIONS_RUNBOOK.md",
        "docs/RELEASE_CHECKLIST.md",
    ):
        assert (repo / relative).is_file(), relative
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "docs/RELEASE_CHECKLIST.md" in readme
    architecture = (repo / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "SERVICE_BUSY" in architecture
    assert "--noprofile --norc" in architecture
    security = (repo / "SECURITY.md").read_text(encoding="utf-8")
    assert "GATEWAY_TOKEN" in security
    assert "MAX_CONCURRENT_COMMANDS" in security


def test_manual_workspace_and_diagnostics_are_ignored():
    repo = Path(__file__).resolve().parents[1]
    ignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "manual_test_workspace_*/" in ignore
    assert "artifacts/*-diagnostics/" in ignore
