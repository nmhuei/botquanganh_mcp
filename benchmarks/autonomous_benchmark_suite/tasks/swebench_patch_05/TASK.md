# SWEBENCH TASK 05: URI CORE BRACKET QUERY & IPV6 REGRESSION FIX

## Issue Description #482
Users reported two serious regression bugs in `uri_core.parser`:
1. **Bracket syntax collision**: If a query has mixed scalar and bracket keys (e.g. `tag=default&tag[]=new`), `parse_url` crashes with `ValueError: Malformed bracket expression for key: tag`. Expected behavior: It should smoothly convert scalar into a list, e.g. `{"tag": ["default", "new"]}`.
2. **IPv6 Host normalization**: When parsing URLs with IPv6 addresses like `http://[::1]:8080/metrics` or `http://[2001:db8::1]/`, `hostname` should be normalized without enclosing brackets (`::1` or `2001:db8::1`).
3. **Empty query values**: Handling `key=` without value should map to `""`.

## Objectives
1. Run existing unit tests (`PYTHONPATH=src pytest`).
2. Add regression tests in `tests/test_regression_482.py` testing:
   - Mixed scalar and array bracket parameters (`tag=old&tag[]=new`).
   - IPv6 hostname normalization (`[::1]`).
   - Empty query parameters (`flag=&test=1`).
3. Fix the bugs in `src/uri_core/parser.py` without breaking existing tests.
4. Export git patch diff into `patch.diff`.
5. Output `solution.json`:
```json
{
  "status": "solved",
  "fixed_files": ["src/uri_core/parser.py"],
  "test_count_passed": 5
}
```

## Definition of Done
- `PYTHONPATH=src pytest` passes 100% of all tests (baseline + regression).
- `patch.diff` exists in workspace.
