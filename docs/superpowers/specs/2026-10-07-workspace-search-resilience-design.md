# Workspace Search Resilience Design

## Goal

Keep `workspace_search` responsive under broad, dense, and hostile searches.
Return bounded partial results. Do not leave search processes running.

## Scope

Change the `workspace_search` tool and its shared payload, configuration,
Desktop Settings, telemetry, tests, and current documentation.

Do not build a persistent content index. Do not change the Cloudflare tunnel.

## Current evidence

| Case | Measurement | Finding |
| --- | --- | --- |
| Default root, sparse query | 90.6 ms | Ripgrep is fast for normal work. |
| Default root, dense query | 40.4 ms | The result cap stops normal searches early. |
| Exact count | 148.9 ms | Full scans are required for exact totals. |
| 500 long matches | 1,429.8 ms | Repeated JSON serialization is the main local cost. |

The current payload loops serialize the complete list for each discarded item.
The current ripgrep timeout starts only after stdout iteration ends.

## Required behaviour

1. Return a valid result when a budget ends a search.
2. Set `truncated=true` and `limit_reason` on that result.
3. Preserve result order and existing content fields.
4. Do not claim an exact total after a work budget ends.
5. Return a typed error only for invalid input, policy denial, or execution failure.
6. Do not leave an `rg` process or child process after return.
7. Do not read symlinks, special files, oversized files, denied descendants, or binary files.
8. Do not store raw queries or matched text in telemetry.

Use a typed `SearchLimitReason` enum. Define these values:

| Value | Meaning |
| --- | --- |
| `deadline` | The wall-clock deadline ended the search. |
| `work_matches` | The match-work budget ended the search. |
| `scanned_files` | The scanned-file budget ended the search. |
| `scanned_bytes` | The scanned-byte budget ended the search. |
| `payload` | The response byte budget omitted matches. |
| `result_cap` | The caller result cap omitted matches. |
| `queue` | Search capacity was unavailable before queue timeout. |

`ok` remains true for a partial result. `count_complete` remains false when a
work budget, deadline, or result cap prevents a full count.

## Resource controls

Use configuration values as the only operational source. Validate each value.
Expose each value in Desktop Settings. Persist updates through the existing
atomic `.env` writer.

| Configuration | Purpose |
| --- | --- |
| `SEARCH_TEXT_DEADLINE_SECONDS` | One wall-clock deadline for both search engines. |
| `MAX_SINGLE_FILE_BYTES` | Maximum file size for search. |
| `WORKSPACE_SEARCH_MAX_WORK_MATCHES` | Maximum examined matching lines. Must be finite. |
| `WORKSPACE_SEARCH_MAX_SCANNED_FILES` | Maximum regular files examined by Python fallback. |
| `WORKSPACE_SEARCH_MAX_SCANNED_BYTES` | Maximum bytes examined by Python fallback. |
| `WORKSPACE_SEARCH_MAX_CONCURRENT` | Global running-search capacity. |
| `WORKSPACE_SEARCH_MAX_PER_CHAT` | Running-search capacity for one chat. |
| `WORKSPACE_SEARCH_QUEUE_TIMEOUT_SECONDS` | Maximum wait to acquire capacity. |
| `WORKSPACE_SEARCH_DEFAULT_MAX_MATCHES` | Default returned-match cap. |
| `WORKSPACE_SEARCH_MAX_RETURNED_MATCHES` | Maximum caller-requested returned-match cap. |
| `WORKSPACE_SEARCH_MAX_LINE_CHARS` | Returned line preview cap. |
| `MCP_MAX_PAYLOAD_BYTES` | Canonical complete MCP response ceiling. |
| `MCP_TOOL_RESULT_OVERHEAD_BYTES` | Reserved MCP envelope capacity. |

Define default values only in `app.config` and `.env.example`. Do not define
operational numeric literals in business modules.

## Engine design

### Ripgrep

Run `rg` in a new process group. Use an argv list. Pass `--no-config`.
Pass `--binary-files=without-match`. Pass configured `--max-filesize`.

Consume stdout with a deadline-aware reader. Check the deadline while reading.
Terminate the process group when the deadline, match-work budget, or result
cap ends work. Reap the process in `finally`.

Capture bounded stderr. Map an invalid regex or abnormal exit to a typed error.
Treat exit code 1 as a normal no-match result.

Apply `HOST_READ_DENY_GLOBS` to ripgrep exclusion rules. Deny rules always win
over `include_hidden`.

### Python fallback

Use the secure traversal patterns in `app.host.files.search_text`.
Use `lstat`, regular-file checks, no-follow opens, size checks, and deadline
checks. Do not follow directory or file symlinks. Skip binary files.

Track scanned file and byte budgets. Compile regex once. Precompute lowercase
literal input once.

## Payload design

Add a shared list-fitting helper in `app.tools_common`.

1. Serialize a candidate match once.
2. Track list commas, brackets, and reserved envelope bytes.
3. Keep the longest input-order prefix within the search response budget.
4. Serialize the final response once for an assertion.
5. Keep the bridge middleware as a hostile-output fallback only.

Apply this helper to content and path modes. Keep the current public fields.
Set accurate path-mode truncation when the path cap omits data.

## Concurrency design

Add a thread-safe search-capacity manager. It has global and per-chat limits.
Acquire capacity before engine work. Release capacity in `finally`.

If capacity is unavailable before the queue deadline, return a typed overload
result with `limit_reason="queue"`. Do not block the MCP server indefinitely.

## Telemetry design

Record these safe fields in search journal and completion audit events:

- engine
- mode
- duration_ms
- engine_duration_ms
- payload_duration_ms
- scanned_files
- scanned_bytes
- candidate_matches
- returned_matches
- response_bytes
- truncation flag
- limit_reason
- error class

Record query length and a keyed digest only. Never record raw query or match
text in these telemetry fields.

## Verification

Add tests for:

1. Deadline during an active ripgrep stream.
2. Termination and reaping after every limit path.
3. Exact count under and over work budget.
4. Result cap and path cap truncation semantics.
5. Long UTF-8 matches and one-byte payload boundaries.
6. Linear serialization behaviour with 500 near-limit matches.
7. Full FastMCP result size below the configured wire ceiling.
8. Global and per-chat concurrency limits.
9. Symlinks, FIFO, socket, device, binary, oversized, and denied files.
10. Ripgrep and fallback response parity.
11. Settings validation, UI round-trip, and atomic `.env` persistence.
12. Regression suite and a bounded stress test.

## Non-goals

Do not add a persistent full-text index in this change. Measure the new
telemetry before considering an index or cache.
