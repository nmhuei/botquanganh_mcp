# BQA Center Qt Quick/QML UI

BQA Center is the operator control center for BotQuangAnh Host MCP. It is not a GUI wrapper around every CLI/MCP primitive. The QML frontend surfaces the workflows an operator needs to operate, observe, investigate, manage workspaces, diagnose, and configure the host. The legacy Tkinter frontend remains available with bqa ui --classic.

## Product information architecture

The desktop GUI is intentionally a monitoring workbench rather than an admin dashboard. Primary navigation is limited to three persistent views:

1. **Monitor** — aggregate health, Server / Connector / Event stream state, actionable attention items, public endpoint context, and active/recent work.
2. **Activity** — session/workspace context, command operations, search/sort, live updates, operation detail, stdout/stderr/metadata, and operation-to-log correlation.
3. **Logs** — two evidence modes in one surface:
   - **Events**: structured chat/workspace journal events correlated by stable operation_id.
   - **Runtime**: bounded snapshots of server, tunnel, launcher, audit, and desktop logs.

Less-frequent management is progressively disclosed through the global overflow menu instead of occupying permanent navigation:

- **Manage workspaces…** — active/archived inventory plus archive/restore/delete/prune lifecycle.
- **Diagnostics…** — Doctor, security posture, configuration validation, and health metrics.
- **Preferences…** — UI language/theme/density/font scale plus the curated host-workspace workflow.

This split keeps the default workflow focused on **Status -> Activity -> Evidence** while preserving the existing management and recovery capabilities.

## Architecture

~~~text
Host/runtime/workspace services
  status_data
  health_check / get_capabilities
  activity journal + workspace SSE
  chat_sweeper lifecycle
  config validation
  bqa doctor primitives
  runtime log files
           |
           v
app.cli.center.services
  workspace inventory/lifecycle
  health aggregation
  attention items
  security posture
  doctor snapshot
  runtime log snapshot
           |
           v
CenterQmlBackend
           |
           +--> keyed QAbstractListModels
           |
           v
Main.qml
  Monitor / Activity / Logs
  overflow -> Workspaces / Diagnostics / Preferences
~~~

app.cli.center.services contains no Qt/Tk widgets. It is the presentation-domain boundary so state semantics can be unit-tested without launching a desktop environment.

## State semantics

The UI does not collapse the system into one LIVE boolean. The aggregate runtime can report:

- HEALTHY
- LOCAL ONLY
- STARTING
- DEGRADED
- OFFLINE
- MISCONFIGURED
- SECURITY WARNING
- STALE DATA

Connector URL freshness is independent:

- active — current URL is confirmed.
- stale — only a last-known URL exists; it is never presented as active.
- unavailable — no public URL is confirmed.

The activity stream state is also independent. Changing stream state recomputes health/attention without pretending the whole runtime is stopped.

## Attention and recovery

attentionModel converts raw subsystem state into actionable operator items. Examples include server offline, bridge not ready, tunnel offline, stale connector, unauthenticated public connector, stream degradation, server errors, authentication failures, rate-limit activity, and failed config validation.

~~~text
server offline       -> Start
bridge/config error  -> Diagnostics / Doctor
tunnel offline       -> Logs > Runtime services > Tunnel
auth/rate limits     -> Logs > Runtime services > Audit
stream problem       -> Logs > Runtime services > Desktop
public auth disabled -> Diagnostics / security posture
~~~

## Refresh and I/O policy

The Center deliberately has two refresh tiers.

### Fast refresh

The 1.4-second timer reads only volatile state:

- runtime process/connector state;
- health counters;
- chat/session discovery;
- bounded command activity.

It does not recursively scan workspace journals/configuration every cycle.

### Full refresh

Explicit Refresh and post-mutation refresh additionally update:

- capabilities;
- config validation;
- security posture;
- workspace inventory and journal summaries.

Doctor remains on-demand because it performs protocol/network/dependency checks. Runtime service logs are also fetched on-demand while their Logs mode is open.

## Metrics

Health exposes counters and percentile snapshots such as uptime, total requests, 5xx count, in-flight requests, p95 latency, and command capacity.

The backend does not currently expose timestamped historical metric samples. Therefore the UI intentionally does not draw fake latency/request charts. A future trend graph requires a real timestamped time-series sampler and bounded retention first.

## Workspace lifecycle safety

The secondary workspace manager uses the shared chat_sweeper path-boundary rules.

- Active workspaces can be archived under .archive.
- Archived workspaces can be restored.
- Permanent delete is available only for a target already inside HOST_CHAT_ROOT/.archive.
- Prune supports preview before apply.
- High-impact actions use confirmation dialogs.
- Safe fixture verification converts mutations into non-destructive feedback.

The global host workspace is a separate concept. Applying it updates HOST_WORKSPACE_DIR / HOST_DEFAULT_DIR and uses the existing server-restart invariant so the tunnel is not accidentally replaced.

## Lifecycle actions

Monitor exposes Start only when the server actually needs recovery. Restart connector and the secondary management surfaces live in the global overflow menu so normal healthy monitoring stays quiet.

- Start / adopt — contextual low-risk recovery action when the server is unavailable.
- Restart connector — guarded restart that verifies the tunnel invariant.

The QML API intentionally does not expose a Stop/tunnel-stop slot. Stopping the managed runtime invalidates the connector that Center itself depends on and is therefore kept as an explicit CLI operation (bqa stop), not a dashboard button. Verification asserts this safety boundary.

Verification runs with safe_actions=True, so mutation-capable UI actions cannot alter the real runtime.

## Activity and correlation

Activity preserves stable domain identifiers. Operations expose command, CWD, status, duration, exit status, stdout, stderr, metadata, and chat/workspace ID.

Activity -> Related logs filters Events by operation_id. Events -> Open operation returns to the correlated operation if it remains in the bounded local cache.

Correlation never depends on row index or timestamp guessing.

The session controls are presentation tracking controls:

- Track
- Mute
- Hide

They are intentionally named differently from real workspace lifecycle actions such as Archive/Restore/Delete.

## Logs

### Events

Structured local filters accept free text and key/value terms:

~~~text
severity:error
category:file
outcome:success
chat:auto-download
op:operation-id
action:host_run_command
~~~

### Runtime services

Sources:

~~~text
all
server
tunnel
launcher
audit
desktop
~~~

Reads are bounded and searchable. BQA Center does not expose an arbitrary terminal or full filesystem editor.

## Security posture

The Diagnostics security section summarizes operational policy without exposing secret values:

- authentication enabled/disabled;
- workspace restriction;
- command policy;
- attribution mode;
- chat workspaces;
- chat write isolation.

GATEWAY_TOKEN contents are never placed in a QML model.

## Presentation preferences

Presentation preferences are independent from server .env configuration and hot-apply immediately:

- language: English / Vietnamese;
- theme: Graphite (classic compatibility key) / Light / Dark;
- density: Compact / Comfortable;
- font scale: 85%–150%.

They are stored in the per-user XDG UI preference JSON. Window state uses the XDG state store and includes logical size, current destination, workspace selection, and Logs mode.

## Visual system

The QML frontend uses the **Nebula Workbench** visual direction: graphite/near-black surfaces, a restrained indigo-violet accent, compact desktop density, table-first information hierarchy, and semantic color reserved for operational state. The presentation intentionally avoids dashboard card grids, persistent sidebars, zebra-striping noise, heavy gradients, and decorative metrics.

The compatibility value classic now renders the default Graphite workstation appearance. Light and Dark remain hot-switchable. The visual hierarchy uses four practical layers: window, surface, raised surface, and overlay. Borders are low-contrast and primarily communicate focus, selection, input boundaries, or separation.

The permanent shell is deliberately small: product identity, aggregate health, **Monitor / Activity / Logs** tabs, and one overflow menu. There is no permanent sidebar or footer. Detail inspectors open only in context, while workspace management, diagnostics, and preferences are secondary surfaces.

Qt Quick Controls Basic is used for predictable cross-distro styling. Preferred fonts are Noto Sans and Noto Sans Mono, with Qt system-font fallback. scripts/install_ui_fonts.sh installs distro packages when available; no font binary is bundled in the repository.

Desktop layouts are verified at 960x650, 1180x760, 1366x768, and 1600x900 in both languages. Primary data views do not require page-level scrolling; Monitor and secondary management surfaces may scroll when content requires it.

## Keyboard and accessibility contract

- Ctrl+1 / Ctrl+2 / Ctrl+3: Monitor / Activity / Logs.
- Ctrl+R or platform Refresh: refresh current data.
- Ctrl+F or platform Find: focus the current searchable primary view.
- Ctrl+, opens Preferences; Ctrl+Shift+D opens Diagnostics.
- /: focus search when a text field is not already active.
- Esc: close the current drawer/popup first, otherwise clear the current local search/filter state.
- Tab/arrow keys: navigate controls and live lists.

Global navigation/find/refresh/escape shortcuts use application-level shortcut scope so a TextField on the previous or hidden page cannot retain ownership.

Status color is supplemental; important states are also written as text. Interactive rows expose Accessible roles, names, selectable state, and press actions.

## Performance

Keyed QAbstractListModel instances optimize common streaming prepend/update paths rather than resetting the entire view. Live ListView delegates use reuseItems and fixed row heights.

The Activity cache and Event cache are bounded. Runtime service-log snapshots are bounded to 500 lines per source request. The periodic refresh policy avoids recursive journal scans.

Model benchmark:

~~~bash
./.venv/bin/python scripts/benchmark_qml_models.py --rows 5000 --repetitions 30
~~~

## Verification

Static QML gate:

~~~bash
./.venv/bin/pyside6-qmllint app/qml_ui/qml/*.qml
~~~

Interaction verification launches a real QQuickWindow under Xvfb and tests the three primary views plus secondary overflow surfaces, mouse/keyboard navigation, search/sort, detail drawers, cross-navigation, runtime/event log modes, preferences hot-apply, transient toast behavior, and the absence of a tunnel-stop QML surface:

~~~bash
QT_QUICK_BACKEND=software xvfb-run -a \
  ./.venv/bin/python scripts/verify_qml_interactions.py
~~~

Full fixture visual matrix:

~~~bash
QT_QUICK_BACKEND=software xvfb-run -a \
  ./.venv/bin/python scripts/verify_qml_ui.py \
  --screenshots-dir ~/Downloads/bqa-qml-verification
~~~

The matrix captures seven view states, two languages, and four window sizes: 56 screenshots total. It audits unclamped Text geometry for overflow/clipping.

Read-only live verification:

~~~bash
QT_QUICK_BACKEND=software xvfb-run -a \
  ./.venv/bin/python scripts/verify_qml_ui.py \
  --live-readonly \
  --screenshots-dir ~/Downloads/bqa-qml-live-verification
~~~

The verifier uses temporary UI/state stores and safe_actions=True.

## Launch modes

~~~bash
bqa ui
bqa ui --inline
bqa ui --classic
bqa tui
~~~

If Qt cannot initialize, bqa ui falls back to the classic Tkinter frontend.

## Packaging

pyproject.toml includes app/qml_ui/qml/*.qml as package data. QML source, font installer, verification scripts, and PySide6 dependencies are part of the normal source/package consistency gates.
