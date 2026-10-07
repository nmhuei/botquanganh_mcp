# BQA MCP Audit Handoff — 2026-10-06

## Scope

This handoff records the interrupted `workspace_search` payload-cap audit and reconciliation state.

Repository:
- `/home/light/GitHub/botquanganh_mcp`

BQA audit session IDs:
- `cw-20261005-audit-workspace_search-py-57418f69` (workspace_search payload audit/reconciliation)
- Additional four BQA audit session IDs were not present in the recovered handoff sources searched during this reconciliation; do not infer or fabricate identifiers.


## Confirmed Audit Finding

Component:
- `app/tools/workspace_search.py`
- Regression coverage: `tests/test_workspace_search.py`

Finding:
- The implementation detected oversized serialized matches but did not reduce the returned payload to fit `_MAX_PAYLOAD_BYTES`.
- Regression fixture generated 100 matching lines of approximately 8 KB each.

Observed evidence:
- `_MAX_PAYLOAD_BYTES`: `512000` bytes
- Serialized matches payload: `832692` bytes

Test command:
```bash
/home/light/GitHub/botquanganh_mcp/.venv/bin/pytest tests/test_workspace_search.py::test_workspace_search_python_fallback_payload_budget_truncates
```

Result:
```text
FAILED tests/test_workspace_search.py::test_workspace_search_python_fallback_payload_budget_truncates
```

Failure:
```text
assert 832692 <= 512000
```

## Previous Audit Findings

### High

- Payload budget was measured but not enforced.

### Medium

- Path-mode truncation reporting may not accurately describe capped results.
- Ripgrep subprocess lifecycle lacked timeout protection.

### Lower

- Invalid regex input should have a stable validation error contract.
- Hidden-file and ignored-directory behavior needed more regression coverage.

## Regression Test Intent

`test_workspace_search_python_fallback_payload_budget_truncates`:

- Forces Python fallback.
- Creates oversized matching content.
- Requires truncation reporting.
- Requires serialized match payload to stay within `_MAX_PAYLOAD_BYTES`.

## Resolution Verification — 2026-10-07

Status:
- Resolved.

Implementation:
- `_bound_response_payload()` removes excess matches until the serialized response fits the payload ceiling.
- The tool records truncation when this reduction occurs.

Verification commands:
```bash
.venv/bin/python -m pytest -q tests/test_workspace_search*.py
.venv/bin/python -m pytest -q
```

Verification result:
```text
71 passed
774 passed
```

The previous failed result remains as historical audit evidence. It does not describe the current source state.

## Test Evidence

Relevant test files:
- `tests/test_workspace_search.py`
- `tests/test_workspace_search_config.py`
- `tests/test_workspace_search_concurrency.py`
- `tests/test_workspace_search_engines.py`
- `tests/test_workspace_search_limits.py`
- `tests/test_workspace_search_payload.py`
- `tests/test_workspace_search_review.py`
- `tests/test_workspace_search_safety_corrective.py`
- `tests/test_workspace_search_settings.py`

Covered behaviors include:
- attribution enforcement
- content search
- regex search
- case handling
- match limits
- ripgrep parsing
- exact counting
- Python fallback behavior

## Open Work

No open work remains from this payload-cap audit.

## Artifacts and Research References

Raw research JSON reference:
- `docs/research/tool_call_duplication_research_20261006.json`
- Source copied from: `/home/light/Downloads/bqa-trash/tool_call_duplication_research_20261006.json`
- This artifact contains the duplicate tool-call research record and related findings.

Related artifact areas:
- `GitHub/botquanganh_mcp/artifacts/live-forensics/`
- `GitHub/botquanganh_mcp/logs/`

## Operational Notes

- BR tools only were used.
- `container.exec` was not used.
- No server restart was performed.
- No tunnel restart was performed.
- Existing edits are preserved.
