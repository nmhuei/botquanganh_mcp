# UCS Desktop i18n and Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make English the official default language for `bqa ui`, add a persisted English/Vietnamese selector, and finish the UCS-branded black/green desktop layout.

**Architecture:** A desktop-only translation catalog owns the two supported languages and English fallback. `BQA_UI_LANGUAGE` is stored through the existing atomic `.env` update path; the dashboard replaces its translator and asks every existing view to redraw labels without restarting the bridge or discarding cached data. The supplied UCS logo is a small header emblem, while the theme owns the black/green tab rail.

**Tech Stack:** Python 3.10+, Tkinter/ttk, `python-dotenv`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-ucs-desktop-i18n-and-branding-design.md`

## Global Constraints

- `BQA_UI_LANGUAGE` accepts only `en` and `vi`; default to `en`.
- Translate desktop `bqa ui` controls, labels, messages, and dialogs only. CLI, MCP/API, journal fields, and command data remain English/stable.
- Refuse to persist through the selector when the same key is exported in the process environment.
- Language changes apply immediately while preserving bridge state, stream, cached rows, filters, and selection.
- Tab backgrounds remain `#070b0b`; tab labels are green, with brighter green selected text.
- Reuse `resources/ucs-secretagent.png` only as a 48–52 px header emblem; never add a data-obscuring watermark.
- Preserve existing dirty-worktree changes; stage only task files.

---

## File structure

| File | Responsibility |
| --- | --- |
| `app/cli/config_view.py` | Official language default, validation, and atomic persistence. |
| `app/cli/desktop_views/i18n.py` | Catalog, fallback translator, and reusable live widget bindings. |
| `app/cli/desktop_views/theme.py` | Black/green notebook and language selector styles. |
| `app/cli/desktop_views/{runtime,activity,workspace_logs}.py` | Translator-aware labels, notices, and inspector captions. |
| `app/cli/desktop_ui.py` | UCS header zones, Language selector, persistence, and translator propagation. |
| `.env.example`, `README.md`, `docs/CLI_UI.md` | Official setting and operational documentation. |
| `tests/test_workspace_config.py`, `tests/test_desktop_i18n.py` | Config persistence and catalog tests. |
| Existing desktop test files | View state, theme, and dashboard regressions. |

### Task 1: Make the language setting official

**Files:**
- Modify: `app/cli/config_view.py:15-185,233-340`
- Modify: `.env.example`, `README.md`, `docs/CLI_UI.md`
- Test: `tests/test_workspace_config.py`, `tests/test_operations_workflow.py`, `tests/test_config_env_parity.py`

**Interfaces:**
- `DEFAULT_UI_LANGUAGE: str = "en"`
- `SUPPORTED_UI_LANGUAGES: tuple[str, str] = ("en", "vi")`
- `normalize_desktop_ui_language(value: object) -> str`
- `set_desktop_ui_language(repo_root: Path, raw_language: str) -> dict[str, str]`

- [ ] **Step 1: Write failing tests**

```python
from app.cli.config_view import DEFAULTS, set_desktop_ui_language, validate_config


def test_set_desktop_ui_language_persists_the_official_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("BQA_UI_LANGUAGE", raising=False)
    (tmp_path / ".env").write_text("REQUIRE_AUTH=false\n", encoding="utf-8")
    assert set_desktop_ui_language(tmp_path, "vi") == {"BQA_UI_LANGUAGE": "vi"}
    assert "BQA_UI_LANGUAGE=\"vi\"" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_language_config_rejects_invalid_value_and_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BQA_UI_LANGUAGE", "en")
    with pytest.raises(ValueError, match="current environment"):
        set_desktop_ui_language(tmp_path, "vi")
    monkeypatch.delenv("BQA_UI_LANGUAGE")
    with pytest.raises(ValueError, match="en or vi"):
        set_desktop_ui_language(tmp_path, "fr")
    checks = {item["name"]: item for item in validate_config(tmp_path, {**DEFAULTS, "BQA_UI_LANGUAGE": "fr"})}
    assert checks["config_bqa_ui_language"]["status"] == "fail"
    assert checks["config_bqa_ui_language"]["message"] == "fr; expected en or vi"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_workspace_config.py -q`

Expected: FAIL because `set_desktop_ui_language` does not exist.

- [ ] **Step 3: Implement atomic setting persistence**

Add the default to `DEFAULTS` and implement:

```python
DEFAULT_UI_LANGUAGE = "en"
SUPPORTED_UI_LANGUAGES = ("en", "vi")


def normalize_desktop_ui_language(value: object) -> str:
    language = str(value or DEFAULT_UI_LANGUAGE).strip().lower()
    if language not in SUPPORTED_UI_LANGUAGES:
        raise ValueError("BQA_UI_LANGUAGE must be en or vi.")
    return language
```

Extract the existing `.env` read/replace/`mkstemp`/`fsync`/`replace` code from
`set_workspace_config` into `_persist_env_updates(repo_root, updates)`. It must
preserve unrelated lines and existing file permissions. Use it from both
workspace persistence and:

```python
def set_desktop_ui_language(repo_root: Path, raw_language: str) -> dict[str, str]:
    if "BQA_UI_LANGUAGE" in os.environ:
        raise ValueError("BQA_UI_LANGUAGE is set in the current environment; unset it before changing language through the UI.")
    updates = {"BQA_UI_LANGUAGE": normalize_desktop_ui_language(raw_language)}
    return _persist_env_updates(repo_root, updates)
```

Add `config_bqa_ui_language` to `validate_config`: pass message is `en` or
`vi`; failure message is `<raw>; expected en or vi`. Add
`BQA_UI_LANGUAGE=en` to `.env.example`, and document English default,
desktop-only scope, persistence, and environment override behavior.

- [ ] **Step 4: Run configuration regressions**

Run: `./.venv/bin/python -m pytest tests/test_workspace_config.py tests/test_operations_workflow.py tests/test_config_env_parity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cli/config_view.py .env.example README.md docs/CLI_UI.md tests/test_workspace_config.py tests/test_operations_workflow.py tests/test_config_env_parity.py
git commit -m "feat: add official desktop language setting"
```

### Task 2: Add the desktop translation catalog

**Files:**
- Create: `app/cli/desktop_views/i18n.py`
- Create: `tests/test_desktop_i18n.py`

**Interfaces:**
- `DesktopTranslator(language: str = "en")`
- `DesktopTranslator.text(key: str, **values: object) -> str`
- `DesktopTranslator.with_language(language: str) -> DesktopTranslator`
- `TranslationBindings(translator: DesktopTranslator)` with `bind(widget, key, option="text", **values)` and `set_translator(translator)`.

- [ ] **Step 1: Write failing catalog and binding tests**

```python
from app.cli.desktop_views.i18n import DesktopTranslator, TranslationBindings


def test_translator_defaults_to_english_and_formats_values():
    assert DesktopTranslator().text("tab.runtime") == "Runtime"
    assert DesktopTranslator("vi").text("activity.count", count=2) == "2 lệnh"


def test_translator_uses_english_fallback_for_missing_key_or_value():
    translator = DesktopTranslator("vi")
    assert translator.text("missing.key") == "missing.key"
    assert translator.text("activity.count") == "{count} commands"


def test_translation_bindings_update_existing_widget():
    class Widget:
        def __init__(self): self.values = []
        def configure(self, **values): self.values.append(values)
    widget = Widget()
    bindings = TranslationBindings(DesktopTranslator("en"))
    bindings.bind(widget, "action.refresh")
    bindings.set_translator(DesktopTranslator("vi"))
    assert widget.values == [{"text": "Refresh"}, {"text": "Làm mới"}]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_desktop_i18n.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement catalog and safe fallback**

Create `MESSAGES` with complete `en` and `vi` mappings for header identity,
three tab labels, actions, Language labels/options, Runtime fields/statuses,
Workspace Logs filters/notices/inspector labels, GPT Activity controls/states,
and toasts/dialogs. Stable keys include `tab.runtime`, `tab.workspace_logs`,
`tab.gpt_activity`, `action.start`, `action.restart`, `action.refresh`,
`action.close`, `action.copy`, `action.clear`, `label.language`,
`status.ready`, `status.needs_attention`, `status.stopped`,
`activity.running`, `activity.succeeded`, `activity.failed`, and
`activity.timed_out`.

`DesktopTranslator.text` must choose the selected catalog, fall back to English,
fall back to `key`, then return the English template unformatted on an
interpolation exception. `TranslationBindings` must immediately configure a
bound widget and retain `(widget, key, option, values)` for later switching.

- [ ] **Step 4: Run catalog tests**

Run: `./.venv/bin/python -m pytest tests/test_desktop_i18n.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cli/desktop_views/i18n.py tests/test_desktop_i18n.py
git commit -m "feat: add desktop translation catalog"
```

### Task 3: Localize existing desktop views without state loss

**Files:**
- Modify: `app/cli/desktop_views/runtime.py`
- Modify: `app/cli/desktop_views/activity.py`
- Modify: `app/cli/desktop_views/workspace_logs.py`
- Modify: `app/cli/desktop_views/theme.py`
- Test: `tests/test_desktop_runtime_view.py`
- Test: `tests/test_desktop_activity_view.py`
- Test: `tests/test_desktop_workspace_logs_view.py`

**Interfaces:**
- Every view constructor accepts `translator: DesktopTranslator | None = None`.
- Every view implements `set_translator(translator: DesktopTranslator) -> None`.
- `InspectorTabs.set_tab_label(key: str, label: str) -> None` relabels an existing notebook tab.

- [ ] **Step 1: Write failing live-language-change tests**

```python
def test_runtime_presentation_uses_selected_language_without_changing_data():
    data = {"ok": True, "server": {"running": True}, "tunnel": {"running": True}}
    assert runtime_presentation(data, DesktopTranslator("en")).status == "Ready"
    assert runtime_presentation(data, DesktopTranslator("vi")).status == "Sẵn sàng"


def test_activity_language_change_preserves_record_and_running_session(tmp_path):
    view = ActivityView(root=None, tk=None, ttk=None, parent=None, workspace_root=lambda: tmp_path, on_message=lambda *_: None, on_refresh=lambda: None, translator=DesktopTranslator("en"))
    session = WorkspaceSession("chat-a", tmp_path / "chat-a", 1.0)
    view.refresh([session], [{"event_id": "evt", "chat_id": "chat-a", "operation_id": "act", "phase": "started", "status": "running"}])
    view.set_translator(DesktopTranslator("vi"))
    assert view.records[0]["event_id"] == "evt"
    assert view.running_session_ids == {"chat-a"}


def test_workspace_log_language_change_preserves_filter_and_selection():
    view = WorkspaceLogView(on_new_activity=lambda _chat: None, translator=DesktopTranslator("en"))
    view.chip, view.selected_id = "error", "evt-1"
    view.set_translator(DesktopTranslator("vi"))
    assert (view.chip, view.selected_id) == ("error", "evt-1")
```

- [ ] **Step 2: Run the view tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py -q`

Expected: FAIL because constructors and `set_translator` do not implement the new interface.

- [ ] **Step 3: Implement localized rendering**

Store a local translator and `TranslationBindings` in RuntimeView, ActivityView,
and WorkspaceLogView. Bind static labels, headings, controls, and frames at
build time. `set_translator` updates bindings and rerenders only existing
rows/notices. Preserve activity records, `running_session_ids`, session and
command filters, log chip/outcome filters, and selected IDs.

Change `runtime_presentation(data, translator=None)` to translate only display
status/summary/fallback endpoint text. Keep colors, URLs, raw state values,
category, severity, journal payload, stdout, and stderr unchanged. Let activity
human output and workspace-log summary accept an optional translator and
translate prose labels only. Retain `frame_by_key` in `InspectorTabs`, and use
`self.notebook.tab(frame, text=label)` in `set_tab_label` so content and scroll
position remain in place.

- [ ] **Step 4: Run view regressions**

Run: `./.venv/bin/python -m pytest tests/test_desktop_i18n.py tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cli/desktop_views/runtime.py app/cli/desktop_views/activity.py app/cli/desktop_views/workspace_logs.py app/cli/desktop_views/theme.py tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py
git commit -m "feat: localize desktop views"
```

### Task 4: Add UCS header, Language selector, and black/green tabs

**Files:**
- Modify: `app/cli/desktop_ui.py:200-520`
- Modify: `app/cli/desktop_views/theme.py:20-150`
- Test: `tests/test_cli_desktop_ui.py`
- Test: `tests/test_desktop_theme.py`

**Interfaces:**
- `_DesktopDashboard` owns `translator`, `language_var`, `language_selector`, `notebook`, and `notebook_tabs`.
- `_DesktopDashboard.change_language(_event: Any = None) -> None` persists first, then propagates a new translator; it restores the prior selector value on `ValueError`.

- [ ] **Step 1: Write failing selector and tab-theme tests**

```python
def test_dashboard_language_change_persists_and_propagates(monkeypatch, tmp_path):
    dashboard = object.__new__(_DesktopDashboard)
    dashboard.ctx = type("Context", (), {"repo_root": tmp_path, "values": {"BQA_UI_LANGUAGE": "en"}})()
    dashboard.language_var = type("Var", (), {"get": lambda self: "vi", "set": lambda self, value: None})()
    for name in ("runtime_view", "activity_view", "workspace_log_view"):
        view = type("View", (), {"set_translator": lambda self, translator: setattr(self, "language", translator.language)})()
        setattr(dashboard, name, view)
    monkeypatch.setattr("app.cli.desktop_ui.set_desktop_ui_language", lambda *_args: {"BQA_UI_LANGUAGE": "vi"})
    dashboard.change_language()
    assert dashboard.ctx.values["BQA_UI_LANGUAGE"] == "vi"
    assert dashboard.workspace_log_view.language == "vi"


def test_desktop_theme_uses_green_text_on_black_tab_rail():
    style, root = Style(), Root()
    apply_desktop_theme(style, root)
    assert style.configured["App.TNotebook"]["background"] == "#070b0b"
    assert style.configured["App.TNotebook.Tab"]["foreground"] == PALETTE["tab_green"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py tests/test_desktop_theme.py -q`

Expected: FAIL because the dashboard has no language change handler and the required palette keys are absent.

- [ ] **Step 3: Implement aligned header and propagation**

Create the dashboard translator from `ctx.values["BQA_UI_LANGUAGE"]`. Replace
the current two-row header with a vertically centered brand frame, status badge,
expanding spacer, and right-aligned action frame. Render the UCS image with
`subsample(10, 10)` and add the `UCS // SECRET AGENT` identity. Place a readonly
Language combobox before Start, Restart, Refresh, and Close. Map localized
display text explicitly to `en`/`vi`, never by comparing translated text.

Keep a map from `runtime`, `workspace_logs`, and `gpt_activity` to their
notebook child frames. `change_language` calls `set_desktop_ui_language` before
changing in-memory state. On success update `ctx.values`, header controls,
notebook labels, and every view. On failure restore the prior selector display
and issue a localized error. Translate dashboard toasts, file-dialog title, and
action messages at emission time.

Add `tab_background="#070b0b"`, `tab_green`, and `tab_green_active` to
`PALETTE`. Configure/map `App.TNotebook` and `.Tab` so both normal and selected
backgrounds are black, normal text is green, and selected text is brighter
green. Add a `Language.TCombobox` style. Keep content panels graphite and never
set tab text black.

- [ ] **Step 4: Run desktop UI regressions**

Run: `./.venv/bin/python -m pytest tests/test_cli_desktop_ui.py tests/test_desktop_theme.py tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cli/desktop_ui.py app/cli/desktop_views/theme.py tests/test_cli_desktop_ui.py tests/test_desktop_theme.py
git commit -m "feat: add UCS desktop language selector"
```

### Task 5: Verify and hand off

**Files:**
- Verify: `.env.example`, `README.md`, `docs/CLI_UI.md`, and files from Tasks 1–4

- [ ] **Step 1: Verify documentation coverage**

Confirm the three docs state `BQA_UI_LANGUAGE=en|vi`, English default,
desktop-only scope, persistence through the selector, and environment override
refusal. Confirm `.env.example` contains exactly `BQA_UI_LANGUAGE=en`.

- [ ] **Step 2: Run focused verification**

Run:

```bash
env HOST_READ_SCOPE= HOST_WRITE_SCOPE= ./.venv/bin/python -m pytest tests/test_workspace_config.py tests/test_operations_workflow.py tests/test_config_env_parity.py tests/test_desktop_i18n.py tests/test_desktop_runtime_view.py tests/test_desktop_activity_view.py tests/test_desktop_workspace_logs_view.py tests/test_desktop_theme.py tests/test_cli_desktop_ui.py -q
./.venv/bin/python -m compileall -q app
git diff --check
```

Expected: every selected test passes, compile exits 0, and whitespace check has no output.

- [ ] **Step 3: Run manual desktop check when a display exists**

Run: `bqa ui --inline`

Check the 48–52 px UCS emblem, black/green tab labels, aligned header action
row, aligned Workspace Logs/GPT toolbars, English initial UI, immediate
Vietnamese switch, preserved tab/filter/selection, and English restored after
relaunch. If no graphical display exists, record that limitation and retain
headless verification output.

- [ ] **Step 4: Commit documentation-only changes if any remain**

```bash
git add README.md docs/CLI_UI.md .env.example tests/test_config_env_parity.py
git commit -m "docs: document desktop language preference"
```
