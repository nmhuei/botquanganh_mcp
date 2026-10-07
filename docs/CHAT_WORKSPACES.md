# Chat Workspaces

Each chat can use an isolated workspace below `HOST_CHAT_ROOT`. The default
root is `~/Downloads/bqa-workspaces`. Workspace state supports session resume,
operation journaling and safe lifecycle cleanup.

## Start or resume work

1. Call `workspace_context(action="list")` to inspect prior workspaces.
2. Call `workspace_context(action="bind")` for a new workspace.
3. Call `workspace_context(action="bind", resume_id="latest")` to resume.
4. Reuse the returned `chat_id` for workspace operations.

When `ATTRIBUTION_MODE=enforce`, prior to binding only `server_info`,
`workspace_context(action="bind")` and `workspace_context(action="list")`
are permitted. All other operations (including `workspace_context` note,
state, hypotheses, resume, and all operational tools) require an
active bound workspace session.

`workspace_search` accepts `path` as the search root. It returns bounded
partial results with `truncated`, `limit_reason`, `scanned_files`,
`scanned_bytes`, and `count_complete` fields. Tune budgets in Desktop
Settings under Search Limits; saves persist atomically to `.env`.

## Configuration

| Key | Default | Purpose |
| --- | --- | --- |
| `ATTRIBUTION_MODE` | `enforce` | Require attributable workspace operations. |
| `HOST_CHAT_WORKSPACES` | `true` | Enable chat workspaces. |
| `HOST_CHAT_ROOT` | `~/Downloads/bqa-workspaces` | Workspace root. |
| `HOST_CHAT_IDLE_ARCHIVE_HOURS` | `72` | Archive idle workspaces after this period. |
| `HOST_CHAT_RETENTION_DAYS` | `30` | Retain archived workspaces for this period. |
| `HOST_CHAT_MAX_WORKSPACES` | `128` | Maximum workspace count. |
| `HOST_CHAT_QUOTA_MB` | `2048` | Maximum size of one workspace. |
| `HOST_CHAT_ROOT_MAX_GB` | `24` | Maximum size of the complete workspace root. |
| `HOST_CHAT_JOURNAL_MAX_BYTES` | `8388608` | Maximum journal size. |

## Layout

```text
<chat_id>/
├── CURRENT.json
├── STATE.md
├── journal.jsonl
├── meta.json
└── notes/
```

`journal.jsonl` is the durable operation ledger. `STATE.md` is a readable
resume summary. `workspace_context` manages notes, state updates and the
hypotheses matrix.

## Operation records

Each workspace operation records an `op_started` event and an `op_result`
event. The reader correlates them with the operation identifier.

| Field | Meaning |
| --- | --- |
| `event_dataset` | Stable value `bqa.workspace`. |
| `event_action` | Active tool or task action, such as `workspace_edit` or `terminal_execute`. |
| `event_category` | `file`, `process`, `session`, `host`, `configuration` or `api`. |
| `event_outcome` | `success`, `failure` or `unknown`. |
| `operation_phase` | `started` or `result`. |
| `interaction_id` | Identifier that links start and result events. |

Commands and secret-looking values are redacted before persistence or display.

## Lifecycle

- Idle workspaces move to `.archive` after `HOST_CHAT_IDLE_ARCHIVE_HOURS`.
- Archived workspaces are removed after `HOST_CHAT_RETENTION_DAYS`.
- The sweeper stays dry-run unless `HOST_CHAT_SWEEP_APPLY=true`.
- Capacity eviction protects active and bound workspaces.

Use `bqa chats list`, `bqa chats show`, `bqa chats logs`, `bqa chats archive`,
`bqa chats restore`, `bqa chats delete` and `bqa chats prune` for local
workspace administration.

## Errors

| Code | Meaning |
| --- | --- |
| `E1` | Missing or invalid chat identifier. |
| `E2` | Workspace capacity limit reached. |
| `E3` | Workspace or journal quota reached. |
| `E4` | Workspace root capacity reached. |
| `E5` | Existing workspace directory has invalid metadata. |
| `E6` | Bind with `workspace_context(action="bind")` before retrying. |
