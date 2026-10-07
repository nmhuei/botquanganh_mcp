# UCS desktop i18n and branding design

## Goal

Make English the official default language of the native `bqa ui` desktop
application, while allowing an operator to switch the complete desktop surface
between English and Vietnamese. Preserve the UCS identity with a restrained
header emblem, a black tab strip, and green tab labels. Correct visible header
and toolbar alignment at the same time.

## Scope

The setting affects only the native desktop interface: Runtime, Workspace
Logs, GPT Activity, button labels, filters, status text, toast messages, and
desktop dialogs. CLI output, MCP tool/API contracts, journal record values,
and persisted command data remain English/stable and are not translated.

## Official configuration

`BQA_UI_LANGUAGE` is an official `.env` setting with these values:

| Value | Meaning |
| --- | --- |
| `en` | English desktop UI (default) |
| `vi` | Vietnamese desktop UI |

The key appears in `DEFAULTS`, `.env.example`, and `bqa config validate`.
Invalid values produce a failing config check with the permitted values in the
message. `set_desktop_ui_language()` updates only this key in `.env`, using the
same atomic write and permission-preserving approach as workspace persistence.
It refuses to write when `BQA_UI_LANGUAGE` is exported in the active process,
because environment values override `.env` at launch.

## Translation architecture

A small desktop-only i18n module owns the supported language set, English and
Vietnamese message catalogs, value validation, and a `translate(key, **values)`
function. English is the fallback for an unavailable language/key or malformed
formatting arguments. Callers supply stable message keys rather than branching
on language. Dynamic values remain data and are interpolated after translating
the text template.

Each desktop view receives the current language/translator from the dashboard
and exposes a refresh method for language changes. Switching language rebuilds
only presentation labels or rerenders existing in-memory rows; it never
restarts the bridge, rereads activity logs, clears filters, changes selection,
or replays a stream.

## Interaction design

The header is split into stable visual zones:

1. UCS emblem (the supplied UCS logo) and product identity at the left.
2. Runtime status badge beside the identity area.
3. A right-aligned Language combobox followed by Start, Restart, Refresh, and
   Close actions, all vertically centered in one header action row.

The supplied logo is shown as a 48–52 px emblem only. It is not used as a large
watermark, so it cannot reduce table or inspector readability.

The notebook's tab rail uses near-black surfaces. Runtime, Workspace Logs, and
GPT Activity labels use green; the selected tab uses a brighter green and a
visible accent treatment. The graphite content surface from the existing theme
remains unchanged. Workspace Logs and GPT Activity toolbars retain their data
model but use aligned label/filter/action groups and consistent padding.

## Error handling

An unsupported stored language falls back to English at startup and causes the
config validator to report the invalid source value. A failed persistence
attempt leaves the active language unchanged and displays a localized error
message. An environment override is never silently replaced by the desktop
selector.

## Verification

Tests cover the official key/default, validation, atomic persistence and
override refusal, catalog fallback, English and Vietnamese key rendering, and
headless desktop layout construction. Existing desktop activity, runtime,
workspace-log, and theme tests remain green. Manual visual verification is
performed when a graphical display is available.
