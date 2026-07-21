# Implementation Plan — Cycle 01

## Goal
Make command-chain parsing quote-aware without changing guarded-policy behavior.

## Scope
`app/host/policy.py` and regression tests.

## Non-goals
No shell execution semantics rewrite and no policy relaxation.

### TASK-001 — Quote-aware chain splitter
- Priority: High
- Objective: Split `&&`, `||`, `|`, `;`, and newlines only outside quotes.
- Files/modules: `app/host/policy.py`, `tests/test_host_tools.py`
- Acceptance criteria: quoted separators remain in one segment; true chains still produce multiple command names.
- Tests: focused parser tests plus full suite.
- Risks: escaped characters and unmatched quotes.
- Rollback: restore regex splitter.

## Verification matrix
| Requirement | Task | Test/Evidence | Expected result |
|---|---|---|---|
| Preserve quoted semicolon | TASK-001 | parser regression | `['python3']` |
| Split real chain | TASK-001 | chained command regression | `['printf','python3']` |
