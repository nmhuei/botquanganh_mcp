from pathlib import Path
import shutil

from app.tools.ctf_harness import (
    ctf_harness_capabilities,
    ctf_harness_check,
    ctf_harness_init,
    ctf_harness_instructions,
)


def test_ctf_harness_capabilities_lists_templates_and_skills():
    res = ctf_harness_capabilities()

    assert res["ok"] is True
    assert "web" in res["template_categories"]
    assert "ctf-web" in res["skills"]
    assert res["bootstrap"]["required_first_tool"] == "ctf_harness_instructions"
    assert "ctf_harness_init" in res["usage"]["init"]


def test_ctf_harness_instructions_reads_gpt_md():
    res = ctf_harness_instructions()

    assert res["ok"] is True
    assert "TRIAGE" in res["content"]
    assert "Coding Guardrails" in res["content"]
    assert res["path"].endswith("GPT.md")


def test_ctf_harness_init_and_check():
    workspace = Path.home() / "Workspace" / ".ctfh_pytest_smoke"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True)

    try:
        res = ctf_harness_init("pytest-smoke", "misc", cwd=str(workspace), force=True)

        assert res["ok"] is True
        assert (workspace / "ctf.yaml").exists()
        assert (workspace / "workspaces" / "pytest-smoke" / "exploit" / "solve.py").exists()

        check = ctf_harness_check(cwd=str(workspace))

        assert check["ok"] is True
        assert "pytest-smoke" in check["stdout"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
