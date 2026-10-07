import pytest
from pathlib import Path
from app.tools.workspace_search import workspace_search
from app.chat_workspace import WorkspaceManager


def test_workspace_search_enforce_mode_requires_chat_id(monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    res = workspace_search(query="hello", chat_id=None)
    assert res["ok"] is False
    assert res["error"]["code"] == "E6"
    assert "workspace_context(action=\"bind\")" in res["error"]["message"]
    assert "workspace_context(action=\"bind\")" in res["error"]["suggestion"]


def test_workspace_search_content_and_path(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")

    chat_id = "test-chat-search"
    mgr = WorkspaceManager(tmp_path)
    bind_res = mgr.create_or_bind(chat_id)
    ws = bind_res.path

    (ws / "file1.txt").write_text("The quick brown fox\njumps over the lazy dog\n", encoding="utf-8")
    (ws / "sub").mkdir()
    (ws / "sub" / "file2.py").write_text("def find_secret():\n    return 'secret_value'\n", encoding="utf-8")

    # 1. Content search (literal)
    search_res = workspace_search(
        query="brown fox",
        path=str(ws),
        mode="content",
        chat_id=chat_id,
    )
    assert search_res["ok"] is True
    assert search_res["mode"] == "content"
    assert search_res["total_matches_found"] == 1
    assert "brown fox" in search_res["matches"][0]["text"]

    # 2. Content search (regex)
    regex_res = workspace_search(
        query=r"secret_\w+",
        path=str(ws),
        mode="content",
        regex=True,
        chat_id=chat_id,
    )
    assert regex_res["ok"] is True
    assert regex_res["total_matches_found"] == 1
    assert "secret_value" in regex_res["matches"][0]["text"]

    # 3. Path glob search
    path_res = workspace_search(
        path=str(ws),
        mode="path",
        path_glob="*.py",
        chat_id=chat_id,
    )
    assert path_res["ok"] is True
    assert path_res["mode"] == "path"
    assert len(path_res["matches"]) == 1
    assert "file2.py" in path_res["matches"][0]



def test_workspace_search_regression_fixture_case_insensitive_and_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.config.HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_READ_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)

    chat_id = f"ws-ci-{tmp_path.name[-16:]}"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)
    fixture = tmp_path / "workspace_search_regression" / "search_case"
    fixture.mkdir(parents=True)
    (fixture / "case.txt").write_text("alpha needle\nBETA NEEDLE\n", encoding="utf-8")

    res = workspace_search(
        query="needle",
        path=str(fixture),
        mode="content",
        max_matches=1,
        chat_id=chat_id,
    )

    assert res["ok"] is True
    assert res["mode"] == "content"
    assert res["total_matches_found"] == 2
    assert len(res["matches"]) == 1
    assert "needle" in res["matches"][0]["text"].lower()


def test_workspace_search_regression_fixture_case_sensitive(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.config.HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_READ_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)

    chat_id = f"ws-cs-{tmp_path.name[-16:]}"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)
    fixture = tmp_path / "workspace_search_regression" / "search_case"
    fixture.mkdir(parents=True)
    (fixture / "case.txt").write_text("alpha needle\nalpha Needle\n", encoding="utf-8")

    res = workspace_search(
        query="needle",
        path=str(fixture),
        mode="content",
        case_sensitive=True,
        chat_id=chat_id,
    )

    assert res["ok"] is True
    assert res["total_matches_found"] == 1
    assert res["matches"][0]["text"] == "alpha needle"



def test_workspace_search_regression_respects_match_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.config.HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_READ_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)

    chat_id = "test-chat-search-regression-limit-hermetic"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    fixture = tmp_path / "workspace_search_regression_fixed" / "limit_case"
    fixture.mkdir(parents=True)
    (fixture / "hits.txt").write_text(
        "hit one\nhit two\nhit three\nhit four\nhit five\nhit six\n",
        encoding="utf-8",
    )
    res = workspace_search(
        query="hit",
        path=str(fixture),
        mode="content",
        max_matches=2,
        chat_id=chat_id,
    )

    assert res["ok"] is True
    assert res["total_matches_found"] == 3
    assert res["returned_matches"] == 2
    assert res["count_complete"] is False
    assert len(res["matches"]) == 2
    assert res["truncated"] is True



def test_workspace_search_regression_work_budget_stops_counting(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_SEARCH_MAX_WORK_MATCHES", "2")
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_WORK_MATCHES", 2)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.config.HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_READ_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)

    chat_id = "test-chat-search-regression-budget-hermetic"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)

    fixture = tmp_path / "workspace_search_regression_fixed" / "work_budget"
    fixture.mkdir(parents=True)
    (fixture / "budget.txt").write_text(
        "budget_hit one\nbudget_hit two\nbudget_hit three\nbudget_hit four\n",
        encoding="utf-8",
    )
    res = workspace_search(
        query="budget_hit",
        path=str(fixture),
        mode="content",
        max_matches=100,
        chat_id=chat_id,
    )

    assert res["ok"] is True
    assert res["total_matches_found"] == 2
    assert res["returned_matches"] == 2



def test_workspace_search_regression_reports_engine_and_bounds_results(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.config.HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_READ_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)

    chat_id = "test-chat-search-engine-regression"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)
    fixture = tmp_path / "workspace_search_regression" / "engine_case"
    fixture.mkdir(parents=True)
    (fixture / "needle.txt").write_text("needle\nsecond needle\n", encoding="utf-8")

    res = workspace_search(
        query="needle",
        path=str(fixture),
        mode="content",
        max_matches=1,
        chat_id=chat_id,
    )

    assert res["ok"] is True
    assert res["engine"] in {"ripgrep", "python"}
    assert res["returned_matches"] == 1
    assert res["total_matches_found"] == 2
    assert res["truncated"] is True


def test_workspace_search_regression_ignores_non_match_ripgrep_events(tmp_path, monkeypatch):
    import app.search_engines as engines_module
    import app.tools.workspace_search as search_module

    class FakeStdout:
        def __iter__(self):
            return iter([
                '{"type":"begin"}\n',
                '{"type":"match","data":{"path":{"text":"hit.txt"},"line_number":1,"lines":{"text":"needle\\n"},"submatches":[]}}\n',
                '{"type":"end"}\n',
            ])

        def close(self):
            return None

        def fileno(self):
            raise OSError("no fileno in test")

    class FakeStderr:
        def read(self, *args, **kwargs):
            return ""

    class FakeProcess:
        stdout = FakeStdout()
        stderr = FakeStderr()
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(engines_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    matches, total = search_module._search_ripgrep(
        tmp_path,
        "needle",
        False,
        False,
        10,
        False,
        0,
    )

    assert total == 1
    assert matches[0]["file"] == "hit.txt"


def test_workspace_search_ripgrep_skips_json_after_match_cap(tmp_path, monkeypatch):
    import app.search_engines as engines_module
    import app.tools.workspace_search as search_module

    decoded = []

    class FakeStdout:
        def __iter__(self):
            for i in range(3):
                yield '{"type":"match","data":{"path":{"text":"%s.txt"},"line_number":1,"lines":{"text":"needle\\n"},"submatches":[]}}\n' % i

        def close(self):
            return None

        def fileno(self):
            raise OSError("no fileno in test")

    class FakeStderr:
        def read(self, *args, **kwargs):
            return ""

    original_json_loads = search_module.json.loads

    def tracking_loads(value):
        decoded.append(value)
        return original_json_loads(value)

    class FakeProcess:
        stdout = FakeStdout()
        stderr = FakeStderr()
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(engines_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(engines_module.json, "loads", tracking_loads)

    matches, total = search_module._search_ripgrep(
        tmp_path,
        "needle",
        False,
        False,
        1,
        False,
        0,
    )

    assert total == 2
    assert len(matches) == 1
    assert len(decoded) == 1


def test_workspace_search_ripgrep_adversarial_match_text_preserves_count(tmp_path, monkeypatch):
    import app.search_engines as engines_module
    import app.tools.workspace_search as search_module

    class FakeStdout:
        def __iter__(self):
            return iter([
                '{"type":"begin"}\n',
                '{"type": "match", "data":{"path":{"text":"a"},"line_number":2,"lines":{"text":"needle\\n"}}}\n',
                '{"type":"end"}\n',
            ])

        def close(self):
            return None

        def fileno(self):
            raise OSError("no fileno in test")

    class FakeStderr:
        def read(self, *args, **kwargs):
            return ""

    class FakeProcess:
        stdout = FakeStdout()
        stderr = FakeStderr()
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(engines_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    matches, total = search_module._search_ripgrep(
        tmp_path,
        "needle",
        False,
        False,
        10,
        False,
        0,
    )

    assert total == 1
    assert matches[0]["line"] == 2


def test_workspace_search_default_agent_fast_stops_after_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")
    (tmp_path / "hits.txt").write_text("needle\n" * 5, encoding="utf-8")

    res = workspace_search(query="needle", path=str(tmp_path), max_matches=2)

    assert res["ok"] is True
    assert res["returned_matches"] == 2
    assert res["count_complete"] is False
    assert res["total_matches_is_partial"] is True


def test_workspace_search_exact_count_preserves_total(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")
    (tmp_path / "hits.txt").write_text("needle\n" * 5, encoding="utf-8")

    res = workspace_search(query="needle", path=str(tmp_path), max_matches=2, exact_count=True)

    assert res["ok"] is True
    assert res["returned_matches"] == 2
    assert res["total_matches_found"] == 5
    assert res["count_complete"] is True
    assert res["total_matches_is_partial"] is False



def test_workspace_search_python_fallback_payload_budget_truncates(tmp_path, monkeypatch):
    import json
    import app.tools.workspace_search as search_module

    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "enforce")
    monkeypatch.setattr("app.config.HOST_READ_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE_SET", True)
    monkeypatch.setattr("app.config.HOST_READ_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_WRITE_SCOPE", tmp_path)
    monkeypatch.setattr("app.config.HOST_CHAT_WORKSPACES", True)
    monkeypatch.setattr("app.config.HOST_CHAT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.config.HOST_DEFAULT_DIR", tmp_path)
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)

    chat_id = "test-chat-search-payload-budget"
    WorkspaceManager(tmp_path).create_or_bind(chat_id)
    monkeypatch.setattr(search_module.shutil, "which", lambda _name: None)

    payload_line = "needle " + ("x" * 8190)
    (tmp_path / "large_hits.txt").write_text(
        "\n".join([payload_line] * 100),
        encoding="utf-8",
    )

    res = workspace_search(
        query="needle",
        path=str(tmp_path),
        mode="content",
        max_matches=500,
        chat_id=chat_id,
    )

    serialized = json.dumps(res["matches"], ensure_ascii=False).encode("utf-8")

    assert res["ok"] is True
    assert res["truncated"] is True
    assert res["returned_matches"] < 100
    from app.tools_common import bridge_payload_ceiling

    assert len(serialized) <= bridge_payload_ceiling()



def test_workspace_search_response_payload_cap_applies_to_complete_result(tmp_path, monkeypatch):
    import json
    import app.tools.workspace_search as search_module

    monkeypatch.setattr("app.config.ATTRIBUTION_MODE", "off")
    monkeypatch.setattr("app.config.HOST_WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr("app.config.WORKSPACE_SEARCH_MAX_LINE_CHARS", 20000)
    (tmp_path / "payload.txt").write_text(
        "\n".join(["needle " + ("x" * 7000)] * 120),
        encoding="utf-8",
    )

    result = workspace_search(
        query="needle",
        path=str(tmp_path),
        mode="content",
        max_matches=500,
    )

    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    assert result["ok"] is True
    assert result["truncated"] is True
    from app.tools_common import bridge_payload_ceiling

    assert len(encoded) <= bridge_payload_ceiling()
