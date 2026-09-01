# UCS desktop premium security-console UI design

## Status

Approved direction in chat on 2026-09-01. This document defines a visual and
interaction overhaul of the native desktop interface only. It supersedes the
appearance decisions in earlier desktop UI specs where they conflict, while
retaining their behavioural contracts.

## Goal

Turn `bqa ui` / **UCS-SecretAgent** into a clean, premium security-operations
desktop application. The visual system takes its cues from the existing UCS
logo—near-black contrast, graphite surfaces, a controlled lime-green signal,
and sharp but restrained edges—without repeating the logo's Matrix/hacker
imagery across the interface.

The result must make runtime state, lifecycle controls, log filtering, and
GPT activity easier to scan while preserving every current desktop feature.

## Scope and non-goals

### In scope

- Native Tkinter visual hierarchy, layout, spacing, typography, theme styles,
  status treatments, empty/error states, and responsive minimum geometry.
- A premium dark application shell with a left navigation rail for the
  existing Runtime, Workspace Logs, and GPT Activity surfaces.
- A Runtime overview composed from the existing lifecycle status response.
- A user-visible Stop control with a native confirmation dialog, reusing the
  existing UI lifecycle action and worker/refresh mechanism.
- English and Vietnamese labels/messages for newly visible UI text.
- UI-specific unit/widget-adapter tests and documentation updates.

### Explicitly out of scope

- Changes to `app/host`, MCP tools, MCP/REST/SSE endpoints, request and
  response schemas, journal records, lifecycle shell scripts, or CLI grammar.
- Changes to the UCS logo asset, desktop launcher identity, or `bqa` command.
- New dependencies, browser UI, external icon libraries, analytics, stored UI
  preferences, or backend-derived metrics/history graphs.
- Changes to the terminal dashboard (`app/cli/dashboard.py`).

## Brand and visual system

`resources/ucs-secretagent.png` remains the only logo asset. The application
loads and retains it exactly as it does today; it is displayed as a small
header emblem (about 32–40 logical pixels) beside the established
`UCS // SECRET AGENT` wordmark. It is never stretched, recoloured, replaced,
or used as a content watermark.

The theme introduces semantic tokens rather than one-off widget colours:

| Token family | Intent |
| --- | --- |
| Ink / canvas | Near-black background with a very subtle cool-green cast. |
| Surface | Layered graphite cards and panels, separated by quiet hairline borders. |
| Text | Warm-white primary text, cool grey supporting text, high readable contrast. |
| Lime signal | Only active navigation, keyboard focus, selected tab, and "running" indicator accents. |
| Semantic states | Teal success, amber warning, coral/red destructive/error, each paired with textual state. |
| Geometry | Consistent 8-point spacing scale, compact 8–12px radii, no glow, glass, gradients, or decorative scan effects. |

The UI feels security-oriented through contrast, hierarchy, icon scale, and
controlled lime signals—not terminal code, Matrix rain, skulls, glitches, or
neon text walls. All states continue to use text as well as colour.

## Application shell and navigation

The root uses a three-zone shell:

1. **Header** — UCS emblem and product identity at left; concise runtime
   summary in the middle; language selector and passive window utilities at
   right. It is a compact identity bar, not a crowded command toolbar.
2. **Navigation rail** — a fixed, narrow left rail selects the three existing
   notebook views: Runtime, Workspace Logs, and GPT Activity. Selection has a
   lime leading indicator and readable label. Keyboard navigation and the
   logical tab order remain available through the existing notebook mechanism.
3. **Content canvas and footer** — the selected view fills the remaining
   graphite canvas. A calm footer owns backend/SSE/workspace/last-refresh
   meta-status and the most recent short message.

The current `ttk.Notebook` remains the owner of tab selection and view
lifetime; the rail is a presentation/control layer which selects that notebook
rather than a second set of view state. This prevents duplicate refresh,
selection, or stream lifecycles.

```text
UCS header + logo
    |
navigation rail -- selects --> existing Runtime / Workspace Logs / GPT Activity notebook
                                    |                 |                   |
                              status cards       SSE/filter/detail   sessions/activity/inspectors
                                    \                 |                   /
                                     existing desktop coordinator + footer status
```

## Runtime view

Runtime becomes the clear command centre, without inventing new backend data.
It receives the same `status_data()` response and renders:

- one concise overall health banner derived from the existing `ok`, bridge,
  server, and tunnel fields;
- three compact factual cards for MCP Bridge, Server, and Cloudflare Tunnel;
- an Endpoint card retaining its copy behaviour;
- a dedicated **Controls** row: Start, Restart, Refresh, and Stop.

Start is the primary safe action. Restart and Refresh are neutral secondary
actions. Stop is a distinct coral/red destructive control visually separated
from Start. Stop opens a native confirmation dialog whose translated copy says
that the managed supervisor, MCP server, and Cloudflare tunnel will be stopped.
Only confirmation launches the existing `lifecycle.stop` action; cancellation
has no effect. It reuses `_run_action`, busy disabling, completion feedback,
and scheduled refresh. No lifecycle implementation changes are made.

The existing workspace choose/apply controls stay available in the Runtime
view, but are visually grouped below operational status so configuration work
does not compete with daily lifecycle actions.

## Workspace Logs and GPT Activity

Both existing views retain their data, widgets, and interaction contracts:

- Workspace Logs retains its SSE worker, cached-row cap, category/outcome/chat
  filters, Clear action, row selection, Summary/Metadata/Payload inspector,
  and stream-reset handling.
- GPT Activity retains workplaces rail, reopened-session behaviour, local
  filtering, sortable command table, nested split panes, independent
  Input/Output collapse controls, inspector scroll preservation, copy
  behaviour, and keyboard shortcuts.

Their visual treatment becomes consistent with the shell: a clear section
title, aligned toolbars, one control height, semantic filter chips, quieter
table chrome, compact selected-row contrast, and intentional empty/loading/
error panels. The change is presentational; it does not issue new requests or
alter filtering, sorting, cached data, selection, or splitter behaviour.

## Component ownership

The existing view boundaries remain intact:

| Module | Premium UI responsibility |
| --- | --- |
| `desktop_views/theme.py` | Semantic palette/tokens and all shared ttk/Tk styles. |
| `desktop_views/i18n.py` | New EN/VI labels, confirmations, and status text. |
| `desktop_views/runtime.py` | Runtime banner/card/control layout and busy registration. |
| `desktop_views/workspace_logs.py` | Presentation-only toolbar/table/inspector state styling. |
| `desktop_views/activity.py` | Presentation-only session rail, command table, split-pane and inspector styling. |
| `desktop_ui.py` | Shell, navigation-to-notebook adapter, footer status layout, Stop action wiring, and cross-view coordination. |

`DesktopDashboard` stays the owner of refresh scheduling, lifecycle worker
actions, translation propagation, and shutdown. Views continue to receive
narrow callbacks rather than reaching into the dashboard or backend code.

## Error handling and accessibility

- A Stop confirmation cancellation is silent and leaves UI state unchanged.
- Lifecycle errors, existing status-reader errors, and stream errors retain
  their current message paths but use the shared semantic error treatment.
- During any lifecycle action, all registered actions—including Stop and
  navigation-affecting configuration actions—are disabled until the UI worker
  finishes on Tk's main loop.
- Focus rings, tab order, button labels, and textual runtime states remain
  visible. Colour is never the sole status indicator.
- UI remains usable at the current supported minimum window size; tables and
  inspectors shrink/scroll rather than overlap control areas.

## Test and verification strategy

Tests are UI-only and use existing fake-Tk/widget-adapter patterns where a
display is unavailable:

1. Theme tests assert semantic shared styles and selected/navigation status
   state rather than brittle pixel positions.
2. Runtime tests cover presentation of ready/degraded/stopped data, factual
   cards, busy-state registration, and unchanged endpoint/workspace callbacks.
3. Dashboard tests cover rail-to-notebook selection, footer refresh values,
   logo loading retention, Stop confirmation cancellation/confirmation,
   injected Stop action wiring, busy locking, and post-action refresh.
4. i18n tests require each new key in English and Vietnamese and verify live
   relabeling does not discard loaded state.
5. Existing Workspace Log and Activity regression suites must pass unchanged,
   proving stream, cache, filter, splitter, selection, scroll, and shortcut
   behaviour are preserved.
6. Run the focused desktop test suite, then the broader project test suite
   appropriate to the changed files. Perform a manual visual smoke test under
   a graphical session (or Xvfb when available): all three views, EN/VI
   switching, Start/Restart/Refresh, cancelled Stop, confirmed Stop, resize,
   and clean exit.

## Acceptance criteria

- The native desktop UI visibly follows the clean security-terminal premium
  direction while using the original UCS logo unchanged.
- Runtime, Workspace Logs, and GPT Activity remain available and preserve all
  pre-existing behavioural contracts.
- Stop is discoverable, confirmation-protected, localized, busy-safe, and
  operates only through the existing UI lifecycle action.
- No backend, MCP tool, API/SSE schema, lifecycle script, journal schema, or
  terminal UI file changes.
- The test/visual verification strategy succeeds with no Tk tracebacks.
