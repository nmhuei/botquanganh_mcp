# Desktop boot animation design

## Status

Approved in chat on 2026-08-30. This design adds a short UCS-SecretAgent
startup sequence; it does not alter session-activity behavior.

## Goal

Give the native desktop app a compact, terminal-inspired boot moment before
the existing dashboard first appears. The visual language may take inspiration
from a Parrot OS boot animation, but uses only UCS-SecretAgent copy and
procedural Tk drawing--no Parrot assets, logos, or branding.

## Behavior

- `run_desktop_ui()` creates the Tk root hidden, builds the existing dashboard
  behind it, and presents a borderless 680 x 360 splash window.
- The splash advances through exactly four phases: `INITIALIZING INTERFACE`,
  `LOADING WORKSPACES`, `CONNECTING ACTIVITY STREAM`, and `READY`.
- Each phase is shown for 750 ms; `READY` remains visible for 750 ms. The
  sequence therefore lasts about 3 seconds and uses Tk's `after()` queue,
  never a blocking sleep or worker thread.
- The visual is a dark terminal panel with a UCS monogram, thin green scan
  lines, phase text, and a four-cell progress indicator. It is drawn with
  `tk.Canvas`, so no new runtime dependency or bitmap asset is needed.
- On normal completion the splash is destroyed and the root dashboard is
  deiconified. No call to `focus`, `focus_force`, `lift`, or a topmost window
  attribute is made.
- Cancelling the sequence cancels its outstanding Tk timer. The dashboard
  keeps its existing close lifecycle and activity stream behavior.

## Boundaries

`desktop_views/boot.py` owns timing and the splash rendering. Its pure-ish
`BootSequence` controller accepts scheduler and cancellation callables, which
makes phase ordering and cancellation testable without a display. The desktop
launcher only creates, starts, and retains the splash long enough for the
event loop.

## Acceptance criteria

- Starting `bqa ui` first presents the UCS boot sequence, then the existing
  dashboard without freezing the Tk event loop.
- Every phase is emitted once and in the stated order; the ready callback runs
  once after the final short delay.
- Cancelling before the ready delay prevents the ready callback.
- Opening, activity refreshes, SSE events, and sessions do not focus or raise
  the dashboard.
