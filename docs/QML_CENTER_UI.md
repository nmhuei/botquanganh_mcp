# BQA Center QML UI

BQA Center is the Qt Quick operations interface for BQA MCP. It monitors the
runtime, workspaces, activity and logs. It does not expose a tunnel-stop action.

## Primary views

1. **Monitor** shows server, connector, health and attention items.
2. **Activity** shows workspace operations and their correlated log events.
3. **Logs** shows workspace events and bounded runtime log snapshots.

The overflow menu provides workspace management, diagnostics and preferences.

## Data flow

```text
Runtime and workspace services
  status_data
  server_info
  activity journal and workspace SSE
  chat_sweeper lifecycle
  configuration and doctor checks
        |
        v
app.cli.center.services
        |
        v
CenterQmlBackend
        |
        v
QAbstractListModels and QML views
```

`server_info` provides service status, operational limits and the active
eight-tool catalog. Workspace operations use the current super-tool names,
such as `workspace_explore`, `workspace_edit` and `terminal_execute`.

## Runtime safety

- Start is available only when runtime recovery is required.
- Server restart preserves the Cloudflare tunnel process and URL.
- Stop is an explicit CLI operation. QML does not expose it.
- Verification uses safe actions. Fixture UI checks do not mutate a real runtime.

## Workspace management

The UI lists active and archived workspaces. It supports archive, restore,
prune and guarded deletion. High-impact actions require confirmation.

`workspace_context` owns binding and resume state. The UI displays operation
records from `journal.jsonl` and uses `interaction_id` for correlation.

## Activity and logs

Activity rows show command state, duration, exit status and bounded output.
Examples of event actions are `workspace_edit`, `workspace_search` and
`terminal_execute`. Runtime logs remain separate from workspace journal events.

The workspace SSE stream supports bounded replay and filters by severity,
category, outcome, chat identifier, operation identifier and action.

## Preferences

Preferences contain language, theme, density and font scale. They are stored
outside `.env` in the user configuration directory. Changing preferences does
not restart the server or tunnel.

## Verification

Run the static QML check:

```bash
./.venv/bin/pyside6-qmllint app/qml_ui/qml/*.qml
```

Run interaction verification under Xvfb:

```bash
QT_QUICK_BACKEND=software xvfb-run -a \
  ./.venv/bin/python scripts/verify_qml_interactions.py
```

Run visual verification with temporary screenshots under `~/Downloads/bqa-trash/`.
