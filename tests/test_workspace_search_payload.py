"""Linear payload fitting tests (Task 4, RED)."""

from __future__ import annotations

import json


def test_fitter_keeps_utf8_prefix_with_one_final_serialization(monkeypatch):
    from app import tools_common

    matches = [
        {"file": f"f{i}.txt", "line": i, "text": "héllo " + ("ü" * 2000)}
        for i in range(500)
    ]
    envelope = {
        "ok": True,
        "mode": "content",
        "matches": matches,
        "truncated": False,
        "returned_matches": len(matches),
    }
    calls = {"count": 0}
    orig_dumps = json.dumps

    def tracking_dumps(*args, **kwargs):
        calls["count"] += 1
        return orig_dumps(*args, **kwargs)

    monkeypatch.setattr(tools_common.json, "dumps", tracking_dumps)
    result = tools_common.fit_json_list_response(envelope, "matches", 512_000)
    final_bytes = len(orig_dumps(result, ensure_ascii=False).encode("utf-8"))
    assert final_bytes <= 512_000
    assert result["truncated"] is True
    # Linear: one serialization per item plus one final assertion.
    assert calls["count"] <= len(matches) + 5


def test_fitter_marks_result_cap_payload_reason():
    from app.tools_common import fit_json_list_response

    envelope = {
        "ok": True,
        "matches": [{"a": "x" * 100} for _ in range(50)],
        "truncated": False,
    }
    result = fit_json_list_response(envelope, "matches", 500)
    assert result["truncated"] is True
    assert result["limit_reason"] == "payload"
    assert len(result["matches"]) < 50


def test_fitter_preserves_order_and_empty_prefix():
    from app.tools_common import fit_json_list_response

    envelope = {"ok": True, "matches": [{"n": 1}], "truncated": False}
    result = fit_json_list_response(envelope, "matches", 10)
    assert result["matches"] == []
    assert result["truncated"] is True


def test_fitter_exact_counterexample_stays_within_budget():
    import json as json_module

    from app.tools_common import fit_json_list_response

    envelope = {
        "ok": True,
        "matches": [{"a": "x"}] * 5,
        "truncated": False,
        "returned_matches": 5,
    }
    result = fit_json_list_response(dict(envelope), "matches", 117)
    final_bytes = len(json_module.dumps(result, ensure_ascii=False).encode("utf-8"))
    assert final_bytes <= 117
    assert result["truncated"] is True
    assert result["returned_matches"] == len(result["matches"])
    assert result["matches"] == [{"a": "x"}] * len(result["matches"])


def test_fitter_never_exceeds_across_budgets_with_unicode():
    import json as json_module

    from app.tools_common import fit_json_list_response

    matches = [
        {"file": f"f{i}.txt", "line": i, "text": "héllo " + ("ü" * 50)}
        for i in range(20)
    ]
    envelope = {
        "ok": True,
        "mode": "content",
        "matches": matches,
        "truncated": False,
        "returned_matches": len(matches),
    }
    for budget in (117, 200, 500, 2000, 20000):
        result = fit_json_list_response(dict(envelope), "matches", budget)
        final_bytes = len(
            json_module.dumps(result, ensure_ascii=False).encode("utf-8")
        )
        base = {
            "ok": True,
            "matches": [],
            "truncated": True,
            "limit_reason": "payload",
            "returned_matches": 0,
        }
        base_bytes = len(json_module.dumps(base, ensure_ascii=False).encode("utf-8"))
        if base_bytes <= budget:
            assert final_bytes <= budget
        assert result["matches"] == matches[: len(result["matches"])]
