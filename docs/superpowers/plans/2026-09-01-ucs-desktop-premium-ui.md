# UCS Desktop Premium UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a clean premium security-console redesign of the native UCS-SecretAgent desktop UI, including a confirmation-protected Stop action, without changing any backend or MCP capability.

**Architecture:** Keep `DesktopDashboard` as the Tk lifecycle coordinator and retain Runtime, Workspace Logs, and GPT Activity as the existing notebook-owned views. Build the new visual shell, rail, footer, semantic theme, and Runtime action surface entirely in the desktop UI modules; existing lifecycle callbacks, status snapshots, SSE data, activity cache, and inspectors remain their sole sources of truth.

**Tech Stack:** Python 3, Tkinter/ttk, pytest, existing fake-widget unit tests; no additional dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-ucs-desktop-premium-ui-design.md`

## Global Constraints

- Change only desktop UI Python modules, desktop UI tests, and desktop UI documentation; do not change `app/host`, MCP tools, API/REST/SSE schemas, lifecycle scripts, journal schema, CLI grammar, or `app/cli/dashboard.py`.
- Preserve and keep loading `resources/ucs-secretagent.png` unchanged; display it only as the compact UCS header emblem.
- Preserve all Runtime, Workspace Logs, and GPT Activity data and interaction contracts: refresh, SSE stream, cached rows, filters, selection, splitters, inspectors, keyboard shortcuts, and scroll retention.
- Reuse existing `app.cli.lifecycle.stop`; do not alter lifecycle implementation. Stop must require an explicit translated native confirmation and must reuse the UI worker/busy/refresh flow.
- Keep English and Vietnamese desktop copy complete. Text plus colour must communicate all runtime/semantic states.
- Do not add dependencies, external icon packs, analytics, persisted UI preferences, backend history graphs, glassmorphism, Matrix effects, visual glitches, or neon-overload styling.
- Run each test with `./.venv/bin/python -m pytest` from the repository root. Preserve unrelated dirty-worktree changes.

## File Structure

| File | Responsibility during this work |
| --- | --- |
| `app/cli/desktop_views/theme.py` | Defines the premium near-black/graphite/lime token set and all shared ttk/Tk styles, including rail, action, card, table, inspector, and footer styles. |
| `app/cli/desktop_views/i18n.py` | Adds EN/VI captions and confirmation/error copy used by new presentation controls. |
| `app/cli/desktop_views/runtime.py` | Replaces the property-grid presentation with the status overview, factual service cards, endpoint/workspace surfaces, and registered control buttons. |
| `app/cli/desktop_views/workspace_logs.py` | Applies the new hierarchy and shared styles without changing the log stream/filter/selection model. |
| `app/cli/desktop_views/activity.py` | Applies the new hierarchy and shared styles without changing session/activity/splitter/inspector behaviour. |
| `app/cli/desktop_ui.py` | Owns the header/rail/footer shell, rail-to-notebook adapter, Stop confirmation/action injection, and existing coordinator wiring. |
| `tests/test_desktop_theme.py` | Locks design tokens and shared premium styles without fragile pixel assertions. |
| `tests/test_desktop_i18n.py` | Locks all new EN/VI copy and fallback behaviour. |
| `tests/test_desktop_runtime_view.py` | Locks Runtime composition and busy registration with fake ttk widgets. |
| `tests/test_desktop_workspace_logs_view.py` | Guards Workspace Log data behaviour while its presentation changes. |
| `tests/test_desktop_activity_view.py` | Guards Activity data/splitter/inspector behaviour while its presentation changes. |
| `tests/test_cli_desktop_ui.py` | Locks shell navigation, footer coordination, original-logo retention, and Stop safety/wiring. |
| `docs/CLI_UI.md` | Describes the finished desktop layout and clarifies Stop's managed-runtime scope. |

---

### Task 1: Establish the UCS premium design tokens and shared ttk styles

**Files:**
- Modify: `app/cli/desktop_views/theme.py:8-159`
- Modify: `tests/test_desktop_theme.py:4-50`

**Interfaces:**
- Consumes: the existing `PALETTE` mapping and `apply_desktop_theme(style, root)` entry point.
- Produces: compatible `PALETTE` keys used by existing views plus `Shell.TFrame`, `Rail.TFrame`, `Rail.TButton`, `RailActive.TButton`, `Primary.TButton`, `Secondary.TButton`, `Danger.TButton`, `RuntimeCard.TLabelframe`, `Footer.TLabel`, and existing table/inspector style names.

- [ ] **Step 1: Write failing semantic-style tests**

  Extend `test_desktop_theme_configures_shared_semantic_widget_styles` so it proves the new shell and action styles exist, the active rail uses the logo-derived lime token, and the destructive style uses the existing semantic danger token.

  ```python
  assert {"Shell.TFrame", "Rail.TFrame", "Rail.TButton", "RailActive.TButton",
          "Primary.TButton", "Secondary.TButton", "Danger.TButton",
          "RuntimeCard.TLabelframe", "Footer.TLabel"} <= set(style.configured)
  assert style.configured["RailActive.TButton"]["foreground"] == PALETTE["lime"]
  assert style.configured["Danger.TButton"]["foreground"] == PALETTE["danger"]
  assert style.configured["App.TNotebook.Tab"]["padding"] == (0, 0)
  ```

  Add a `layout()` recorder to the fake `Style`, then assert the custom notebook tab layout is empty so its content views are selected by the new rail rather than a duplicate top tab strip.

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_theme.py::test_desktop_theme_configures_shared_semantic_widget_styles -q`

  Expected: FAIL because the premium styles, lime token, and notebook-tab layout have not yet been configured.

- [ ] **Step 3: Implement the minimal shared theme**

  Replace one-off visual colours with an expanded compatible palette. Keep existing keys consumed by `activity.py`, `runtime.py`, and `workspace_logs.py`; add semantic keys rather than hard-coding new colours in views.

  ```python
  PALETTE = {
      "app_background": "#090d0c", "surface": "#121918",
      "surface_muted": "#192321", "border": "#2a3632",
      "text": "#f2f5f2", "text_muted": "#a9b5af", "text_subtle": "#81908a",
      "lime": "#b8f23d", "accent": "#b8f23d", "success": "#42d5ad",
      "warning": "#f4b942", "danger": "#ff6b61", "running": "#42d5ad",
      "tab_background": "#090d0c", "tab_green": "#8fbd30", "tab_green_active": "#b8f23d",
  }
  ```

  Configure the named shell/rail/action/card/footer styles with a consistent
  8-point spacing rhythm. Map focus, active, disabled, selected, pressed, and
  tree/inspector states. Use `style.layout("App.TNotebook.Tab", [])` in a
  guarded `try` block so the existing notebook retains selection/lifetime but
  does not render a second navigation row.

- [ ] **Step 4: Run the theme suite to verify it passes**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_theme.py -q`

  Expected: PASS, including existing inspector content/scroll/copy tests.

- [ ] **Step 5: Commit the theme foundation**

  ```bash
  git add app/cli/desktop_views/theme.py tests/test_desktop_theme.py
  git commit -m "style: add UCS premium desktop theme"
  ```

### Task 2: Add the complete localized presentation and Stop-confirmation copy

**Files:**
- Modify: `app/cli/desktop_views/i18n.py:10-307`
- Modify: `tests/test_desktop_i18n.py:1-40`

**Interfaces:**
- Consumes: `DesktopTranslator.text(key, **values)` and `TranslationBindings`.
- Produces: the keys `nav.runtime`, `nav.workspace_logs`, `nav.gpt_activity`,
  `runtime.overview`, `runtime.controls`, `runtime.service_detail`,
  `action.stop`, `dialog.stop_title`, and `dialog.stop_body` in both catalogs.

- [ ] **Step 1: Write failing catalog assertions**

  ```python
  def test_premium_shell_and_stop_copy_is_complete_in_both_languages():
      english = DesktopTranslator("en")
      vietnamese = DesktopTranslator("vi")
      assert english.text("nav.workspace_logs") == "Workspace Logs"
      assert vietnamese.text("nav.workspace_logs") == "Nhật ký Workspace"
      assert english.text("action.stop") == "Stop"
      assert vietnamese.text("action.stop") == "Dừng"
      assert "Cloudflare" in english.text("dialog.stop_body")
      assert "Cloudflare" in vietnamese.text("dialog.stop_body")
  ```

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_i18n.py::test_premium_shell_and_stop_copy_is_complete_in_both_languages -q`

  Expected: FAIL because the new keys are missing and the fallback returns key names.

- [ ] **Step 3: Add exact English and Vietnamese desktop-only copy**

  Add every listed key to both `MESSAGES["en"]` and `MESSAGES["vi"]`. Use
  the exact confirmation semantics below so Stop never conceals scope:

  ```python
  "dialog.stop_title": "Stop managed runtime?",
  "dialog.stop_body": "This stops the managed supervisor, MCP server, and Cloudflare tunnel.",
  # Vietnamese
  "dialog.stop_title": "Dừng runtime được quản lý?",
  "dialog.stop_body": "Thao tác này dừng supervisor được quản lý, MCP server và Cloudflare tunnel.",
  ```

  Keep raw journal values and CLI/MCP copy untouched; only desktop labels and
  messages use these strings.

- [ ] **Step 4: Run the i18n suite to verify it passes**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_i18n.py -q`

  Expected: PASS, including English fallback and live binding coverage.

- [ ] **Step 5: Commit localized copy**

  ```bash
  git add app/cli/desktop_views/i18n.py tests/test_desktop_i18n.py
  git commit -m "feat: localize premium desktop controls"
  ```

### Task 3: Rebuild the Runtime surface as a factual control centre

**Files:**
- Modify: `app/cli/desktop_views/runtime.py:15-183`
- Modify: `tests/test_desktop_runtime_view.py:1-135`

**Interfaces:**
- Consumes: the unchanged `runtime_presentation(data, translator)` status model and narrow callbacks supplied by the dashboard.
- Produces: `RuntimeView.build(..., on_start, on_stop, on_restart, on_refresh)` and `RuntimeView.action_buttons` containing every lifecycle/configuration button that must disable during a UI worker action.

- [ ] **Step 1: Write failing Runtime layout/registration tests**

  Extend the fake ttk widget fixture to record `style`, `textvariable`, and
  `command`. Add a test proving the view builds the three factual cards and
  registers Start, Stop, Restart, Refresh, and Apply for `set_busy()`.

  ```python
  view.build(
      ttk=ttk, parent=Widget(), workspace_var=Variable(),
      on_copy_endpoint=lambda: None, on_choose_workspace=lambda: None,
      on_apply_workspace=lambda: None, on_start=lambda: None,
      on_stop=lambda: None, on_restart=lambda: None, on_refresh=lambda: None,
  )
  assert {"Primary.TButton", "Danger.TButton", "Secondary.TButton"} <= set(ttk.button_styles)
  view.set_busy(True)
  assert len(view.action_buttons) == 5
  assert all(button.state_calls[-1] == ["disabled"] for button in view.action_buttons)
  ```

- [ ] **Step 2: Run the focused Runtime tests to verify they fail**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_runtime_view.py -q`

  Expected: FAIL because `RuntimeView.build()` does not accept lifecycle callbacks or create the new card/control hierarchy.

- [ ] **Step 3: Implement the Runtime composition without new data**

  Retain `RuntimePresentation` and all existing `StringVar` updates. Replace
  the property-grid frame with these visual sections, each bound to existing
  variables: overall-health banner; MCP Bridge card; Server card; Cloudflare
  Tunnel card; controls row; Endpoint copy row; workspace choose/apply row.

  Use a tiny local builder so card styles remain consistent:

  ```python
  def _service_card(self, ttk: Any, parent: Any, *, title_key: str,
                    state_var: Any, detail_key: str, detail_var: Any) -> Any:
      card = ttk.LabelFrame(parent, style="RuntimeCard.TLabelframe", padding=16)
      self.bindings.bind(card, title_key)
      ttk.Label(card, textvariable=state_var, style="RuntimeState.TLabel").grid(...)
      detail = ttk.Label(card, style="FieldName.TLabel")
      self.bindings.bind(detail, detail_key)
      ttk.Label(card, textvariable=detail_var, style="CardValue.TLabel").grid(...)
      return card
  ```

  Register lifecycle buttons in `action_buttons`; Start uses `Primary.TButton`,
  Stop uses `Danger.TButton`, and Restart/Refresh use `Secondary.TButton`.
  Do not create graph data, mutate `status_data`, or call any backend function.

- [ ] **Step 4: Run the Runtime suite to verify it passes**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_runtime_view.py -q`

  Expected: PASS, including existing localization and busy-state tests.

- [ ] **Step 5: Commit the Runtime view**

  ```bash
  git add app/cli/desktop_views/runtime.py tests/test_desktop_runtime_view.py
  git commit -m "feat: redesign desktop runtime control centre"
  ```

### Task 4: Build the premium shell, navigation rail, and footer around the existing notebook

**Files:**
- Modify: `app/cli/desktop_ui.py:200-430`
- Modify: `tests/test_cli_desktop_ui.py:87-291`

**Interfaces:**
- Consumes: `self.notebook`, `self.notebook_tabs`, `self.header_bindings`, `self.runtime_view`, and the unchanged three view constructors.
- Produces: `_select_view(key: str) -> None`, `_set_navigation_active(key: str) -> None`, `_sync_navigation(_event: Any = None) -> None`, `self.navigation_buttons: dict[str, Any]`, and `self.footer_bindings` that survive live language changes.

- [ ] **Step 1: Write failing shell-controller tests**

  Use a fake notebook with `select()`, `tab()`, and `bind()` recording calls.
  Construct a dashboard through `object.__new__`, assign the existing tab map,
  and assert the public UI-private helpers select a named tab and style only
  that rail button as active.

  ```python
  dashboard._select_view("workspace_logs")
  assert notebook.selected == "workspace-tab"
  assert dashboard.navigation_buttons["workspace_logs"].configured["style"] == "RailActive.TButton"
  assert dashboard.navigation_buttons["runtime"].configured["style"] == "Rail.TButton"
  ```

  Add a footer assertion that existing `backend_var`, `workspace_var`,
  `refresh_var`, `sse_var`, and `message_var` are displayed from variables,
  not copied into a second source of state.

- [ ] **Step 2: Run the focused shell tests to verify they fail**

  Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'navigation or footer' -q`

  Expected: FAIL because the navigation helpers and premium footer do not exist.

- [ ] **Step 3: Implement the shell without rebuilding views**

  In `_DesktopDashboard._build`, keep the same root lifecycle and `ttk.Notebook`
  instance. Replace the top action toolbar with a compact identity/header area;
  create a left `Rail.TFrame` with three buttons, put the hidden-tab notebook
  in the adjacent canvas column, and place the status variables in `Footer.TLabel`
  widgets in the bottom row. Bind notebook selection to `_sync_navigation`.

  ```python
  def _set_navigation_active(self, key: str) -> None:
      for name, button in self.navigation_buttons.items():
          button.configure(style="RailActive.TButton" if name == key else "Rail.TButton")

  def _select_view(self, key: str) -> None:
      tab = self.notebook_tabs[key]
      if str(self.notebook.select()) != str(tab):
          self.notebook.select(tab)
      self._set_navigation_active(key)

  def _sync_navigation(self, _event: Any = None) -> None:
      selected = str(self.notebook.select())
      for key, tab in self.notebook_tabs.items():
          if str(tab) == selected:
              self._set_navigation_active(key)
              return
  ```

  Bind rail labels through a dedicated
  `TranslationBindings` object and refresh it in `change_language`. Retain the
  original logo load/reference path, root title, boot flow, refresh interval,
  and all three existing view construction calls.

- [ ] **Step 4: Run shell and existing coordinator regressions**

  Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -q`

  Expected: PASS, including detached launcher, activity focus, language, and lifecycle-worker tests.

- [ ] **Step 5: Commit the application shell**

  ```bash
  git add app/cli/desktop_ui.py tests/test_cli_desktop_ui.py
  git commit -m "feat: add premium desktop navigation shell"
  ```

### Task 5: Wire the confirmation-protected Stop action through the existing UI lifecycle path

**Files:**
- Modify: `app/cli/desktop_ui.py:15-40, 200-230, 610-640, 695-715`
- Modify: `tests/test_cli_desktop_ui.py:292-371`

**Interfaces:**
- Consumes: existing `app.cli.lifecycle.stop(repo_root) -> dict[str, Any]`, `_run_action(label, action)`, and `RuntimeView.build(..., on_stop=...)` from Task 3.
- Produces: `StopConfirmation = Callable[[Any, DesktopTranslator], bool]`, `confirm_stop(root, translator) -> bool`, `stop_service() -> None`, injectable `stop_action` and `stop_confirmation` arguments with safe defaults in `run_desktop_ui()` and `_DesktopDashboard`.

- [ ] **Step 1: Write failing Stop safety tests**

  Add tests that instantiate a minimal dashboard via `object.__new__`, inject
  a `stop_action` spy and `stop_confirmation` returning each boolean, and
  replace `_run_action` with a recorder.

  ```python
  dashboard.stop_confirmation = lambda _root, _translator: False
  dashboard.stop_service()
  assert calls == []

  dashboard.stop_confirmation = lambda _root, _translator: True
  dashboard.stop_service()
  assert calls[0][0] == DesktopTranslator().text("action.stop")
  assert calls[0][1]() == {"ok": True}
  ```

  Also assert the default confirmation calls `messagebox.askyesno` with the
  translated title/body, `parent=root`, `icon="warning"`, and `default="no"`.

- [ ] **Step 2: Run the focused Stop tests to verify they fail**

  Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k stop -q`

  Expected: FAIL because no dashboard Stop method or confirmation injection exists.

- [ ] **Step 3: Implement UI-only Stop wiring**

  Import `stop` alongside `start` and `restart`; do not modify
  `app/cli/lifecycle.py`. Define the confirmation helper and default injected
  parameters, then call the existing worker path only after confirmation:

  ```python
  def confirm_stop(root: Any, translator: DesktopTranslator) -> bool:
      from tkinter import messagebox
      return bool(messagebox.askyesno(
          translator.text("dialog.stop_title"),
          translator.text("dialog.stop_body"),
          parent=root, icon="warning", default="no",
      ))

  def stop_service(self) -> None:
      if not self.stop_confirmation(self.root, self.translator):
          return
      self._run_action(
          self.translator.text("action.stop"),
          lambda: self.stop_action(self.ctx.repo_root),
      )
  ```

  Pass `self.start_service`, `self.stop_service`, `self.restart_bridge`, and
  `self.refresh` to `RuntimeView.build`. Remove Start/Restart/Refresh from the
  header; leave language and Close there. Ensure all Runtime actions are in
  `RuntimeView.action_buttons`, so the existing busy-state machinery locks
  them and post-action `refresh()` runs unchanged.

- [ ] **Step 4: Run focused and coordinator lifecycle tests to verify they pass**

  Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py -k 'stop or lifecycle_worker' -q`

  Expected: PASS. A cancelled Stop has no lifecycle call; a confirmed Stop
  uses the injected action and the worker contract remains on the Tk main loop.

- [ ] **Step 5: Commit safe Stop support**

  ```bash
  git add app/cli/desktop_ui.py tests/test_cli_desktop_ui.py
  git commit -m "feat: add confirmed desktop stop action"
  ```

### Task 6: Restyle Workspace Logs while preserving its stream and inspector contracts

**Files:**
- Modify: `app/cli/desktop_views/workspace_logs.py:342-448`
- Modify: `tests/test_desktop_workspace_logs_view.py`

**Interfaces:**
- Consumes: `WorkspaceLogView` public methods and existing `Table.Treeview`, `Inspector.TNotebook`, chip state, stream reader, and `TranslationBindings`.
- Produces: a presentationally upgraded toolbar/table/inspector using shared styles only; no changed data-model method signatures.

- [ ] **Step 1: Write a failing presentation-regression test around existing fake widgets**

  Extend the existing build fixture to record style names. Assert the view uses
  the shared `SectionHeader.TLabel`, `Filter.TEntry`, `Filter.TCombobox`,
  `Chip.TButton`/`ChipActive.TButton`, `Table.Treeview`, and
  `InspectorCard.TLabelframe` styles while retaining all filter control
  callbacks.

  ```python
  view = make_view_with_fake_widgets(...)
  assert "Filter.TEntry" in ttk.entry_styles
  assert "Filter.TCombobox" in ttk.combobox_styles
  assert "InspectorCard.TLabelframe" in ttk.label_frame_styles
  view.select_chip("error")
  assert view.chip == "error"
  ```

- [ ] **Step 2: Run Workspace Log tests to verify the new assertion fails**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_workspace_logs_view.py -q`

  Expected: FAIL because the premium presentation styles are not applied.

- [ ] **Step 3: Apply only layout/style changes**

  Add a section title and align chips as a labelled group; give the filter
  controls one consistent height; use the shared premium table and inspector
  styles; leave `select_chip`, `clear_filters`, `render`, `start_stream`,
  `close`, tree binding, keyboard selection, and cache/SSE state untouched.
  Existing calls to `_restyle_chips()` continue to choose only the two shared
  chip styles.

- [ ] **Step 4: Run Workspace Log tests to verify they pass**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_workspace_logs_view.py -q`

  Expected: PASS, including parsing, filtering, reconnecting, selection,
  detail-copy, stream reset, and close coverage.

- [ ] **Step 5: Commit the Workspace Logs presentation**

  ```bash
  git add app/cli/desktop_views/workspace_logs.py tests/test_desktop_workspace_logs_view.py
  git commit -m "style: refine workspace log console"
  ```

### Task 7: Restyle GPT Activity while preserving session, splitter, and inspector behaviour

**Files:**
- Modify: `app/cli/desktop_views/activity.py:718-925`
- Modify: `tests/test_desktop_activity_view.py`

**Interfaces:**
- Consumes: `ActivityView` refresh/session/filter/splitter/inspector public behaviour and shared styles from Task 1.
- Produces: the same tree/inspector/session mechanics rendered with `RailPanel.TLabelframe`, `SectionHeader.TLabel`, `Filter.TEntry`, `Secondary.TButton`, and existing table/inspector styles.

- [ ] **Step 1: Write a failing style-and-contract test**

  Reuse the existing fake view widgets to record named styles and assert the
  sessions panel, command toolbar, tables, and output inspector receive the
  intended shared styles. In the same test continue to prove the local filter
  and input/output collapse callbacks are still bound.

  ```python
  view = make_activity_view_with_fake_widgets(...)
  assert "RailPanel.TLabelframe" in ttk.label_frame_styles
  assert "Filter.TEntry" in ttk.entry_styles
  assert view.input_collapse_button is not None
  assert view.output_collapse_button is not None
  ```

- [ ] **Step 2: Run Activity tests to verify the new assertion fails**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_activity_view.py -q`

  Expected: FAIL because the old generic widget styles are still used.

- [ ] **Step 3: Apply the shared hierarchy without model changes**

  Recompose only the `_build()` geometry/padding/style assignments: keep the
  existing workplaces rail, compact the session action grid, align the command
  filter and collapse controls, and give input/output panels matching section
  headers. Retain all `Panedwindow.add` weights, tree columns, tags, bindings,
  `toggle_*`, `refresh`, sorting, session reopening, and `InspectorTabs`
  construction signatures.

- [ ] **Step 4: Run Activity tests to verify they pass**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_activity_view.py -q`

  Expected: PASS, including lifecycle projection, live session rail, local
  filters, scroll retention, nested splitter, collapse, selection, copy, and
  keyboard shortcut coverage.

- [ ] **Step 5: Commit the Activity presentation**

  ```bash
  git add app/cli/desktop_views/activity.py tests/test_desktop_activity_view.py
  git commit -m "style: refine GPT activity console"
  ```

### Task 8: Document the completed UI and perform end-to-end verification

**Files:**
- Modify: `docs/CLI_UI.md:199-233`
- Verify: `tests/test_desktop_theme.py`, `tests/test_desktop_i18n.py`, `tests/test_desktop_runtime_view.py`, `tests/test_desktop_workspace_logs_view.py`, `tests/test_desktop_activity_view.py`, `tests/test_desktop_boot.py`, `tests/test_cli_desktop_ui.py`

**Interfaces:**
- Consumes: the finished desktop-only implementation from Tasks 1–7.
- Produces: operator documentation and captured automated/manual verification evidence.

- [ ] **Step 1: Write documentation assertions into the existing desktop-layout section**

  Replace the obsolete “thin header contains Start, Restart, and Refresh”
  paragraph with concise documentation of the UCS emblem, navigation rail,
  three preserved views, Runtime control centre, managed runtime Stop scope,
  and confirmation requirement. State explicitly that Stop affects the managed
  supervisor, MCP server, and Cloudflare tunnel and that it does not alter MCP
  tools/API contracts.

- [ ] **Step 2: Run the full focused desktop suite**

  Run: `./.venv/bin/python -m pytest tests/test_desktop_theme.py tests/test_desktop_i18n.py tests/test_desktop_runtime_view.py tests/test_desktop_workspace_logs_view.py tests/test_desktop_activity_view.py tests/test_desktop_boot.py tests/test_cli_desktop_ui.py -q`

  Expected: PASS with no skipped failure or Tk traceback.

- [ ] **Step 3: Run non-mutating quality checks**

  Run: `git diff --check`

  Expected: no output and exit code 0.

  Run: `./.venv/bin/python -m compileall -q app/cli/desktop_ui.py app/cli/desktop_views`

  Expected: exit code 0.

- [ ] **Step 4: Perform manual graphical smoke verification when a display is available**

  Run: `./.venv/bin/bqa ui --inline`

  Verify: the unmodified UCS logo appears as a compact header emblem; rail
  selection changes Runtime/Workspace Logs/GPT Activity without duplication;
  EN/VI relabels live; filters, splitters, collapse controls, and inspectors
  retain state; Start/Restart/Refresh work; cancelled Stop does nothing;
  confirmed Stop shows completion/error feedback and refreshes state; resizing
  does not overlap controls; close leaves no Tk traceback in
  `logs/desktop-ui.log`.

  If no graphical display is available, record that limitation and rely on the
  complete fake-widget suite; do not alter runtime configuration merely to run
  a visual check.

- [ ] **Step 5: Commit documentation and verification-ready change set**

  ```bash
  git add docs/CLI_UI.md
  git commit -m "docs: describe premium UCS desktop UI"
  ```
