# Plan: Autonomous Agent + WebSocket Control Plane — v2 (Detailed)

## Overview

This plan unifies two previously separate tracks:

- **WebSocket channel** for real-time event streaming, approval gates, and artifact delivery between ChatGPT web and the MCP server.
- **Autonomous agent runtime** that goes beyond the current single-step `agent_step`, while preserving budget enforcement, safety guardrails, audit trails, and the trusted-operator model.

**This is not a black-box full-auto system.** The design intent is:

- ChatGPT web remains the reasoning brain.
- MCP becomes the control plane + execution gateway.
- Autonomous mode is **bounded autonomy**: looping within a defined scope, with hard budget limits, explicit pause points, and mandatory approval gates for risky actions.

---

## 1. Current State

### What exists

- `agent_goal_create`, `agent_step`, `agent_status`, `agent_cancel`, `agent_report`
- State store at `logs/agent_goals/<goal_id>/`
- Safe action chains for `pwn`, `web`, `crypto`, `forensics`, `reverse`
- `ctf_harness_instructions` + local-first harness workflow
- Manager script and capabilities report

### What is missing

- No continuous execution loop
- No real-time session bus
- No event subscription for ChatGPT web
- No real-time approval channel
- No scheduler, watchdog, or resume policy
- No event cursor/replay for reconnect
- No loop-detection fingerprint mechanism

---

## 2. Target Architecture

```
ChatGPT web
    │
    ├─ HTTP/MCP tools ──────────► Goal control API
    │                              (create, start, pause, resume, cancel, approve)
    │
    └─ WebSocket ───────────────► Event/approval channel
                                   (stream events, receive approvals, heartbeat)

MCP Server
    │
    ├─ Goal state store  ───────► logs/agent_goals/<goal_id>/
    │
    └─ Agent runtime loop ──────► plan → act → observe → persist → evaluate
```

**Core principles:**

- HTTP/MCP tools = control API (imperative commands)
- WebSocket = event channel (reactive stream)
- Goal state = source of truth (persisted to disk)
- Artifacts/logs = audit evidence

---

## 3. Design Principles

- **Host-first by default.** Single-step mode remains the default. Full autonomous loop is opt-in via `mode="bounded_auto"`.
- **Every goal has a budget.** `max_steps`, `max_seconds`, `max_cost_hint` are required fields with enforced defaults.
- **Every goal has a scope.** `allowed_paths`, `allowed_hosts`, `category`, `risk_policy` constrain what the agent can touch.
- **Every action is logged.** Events include `trace_id`, `timestamp`, artifact refs, and action metadata.
- **No persistent global memory.** Agent state lives only in goal state files. No cross-goal memory leakage.
- **Approval is mandatory for risky actions.** See Section 10 for the full list.

---

## 4. v1 Scope

v1 is not an infinite autonomous agent. The target is **long-lived assisted autonomy**:

- WebSocket channel streams events in real time.
- Agent can run multiple steps consecutively within one session.
- Agent pauses on approval gates and decision points.
- One call to `agent_goal_start` = many actions until a stop condition is hit.

Before v1: one `agent_step` call = one action.
After v1: one `agent_goal_start` call = N actions until budget, approval gate, or completion.

---

## 5. Tool/API Surface

### 5.1 Goal lifecycle

```python
agent_goal_create(
    objective: str,
    cwd: str = "",
    scope: dict = {},    # allowed_paths, allowed_hosts, category, risk_policy
    budget: dict = {}    # max_steps, max_seconds, max_cost_hint
) -> goal_id

agent_goal_update(
    goal_id: str,
    objective_patch: str = "",
    scope_patch: dict = {},
    budget_patch: dict = {}
) -> ok

agent_goal_start(
    goal_id: str,
    mode: str = "bounded_auto"   # "single_step" | "bounded_auto" | "detached"
) -> session_id

agent_goal_pause(goal_id: str, reason: str = "") -> ok
agent_goal_resume(goal_id: str) -> ok
agent_goal_cancel(goal_id: str) -> ok
agent_status(goal_id: str) -> GoalStatus
agent_report(goal_id: str) -> ReportMarkdown
```

### 5.2 Session management

```python
agent_session_open(goal_id: str) -> session_id + ws_url
agent_session_status(session_id: str) -> SessionStatus
agent_session_close(session_id: str) -> ok
agent_session_send(
    session_id: str,
    message_type: str,
    payload: dict = {}
) -> ok
```

### 5.3 Approval

```python
agent_approve(
    goal_id: str,
    action_id: str,
    decision: Literal["approve", "reject"],
    note: str = ""
) -> ok

agent_pending_approvals(goal_id: str) -> list[PendingApproval]
```

### 5.4 Event access (fallback for missed events)

```python
agent_event_tail(goal_id: str, limit: int = 100) -> list[Event]
agent_event_get(trace_id: str) -> Event
```

---

## 6. WebSocket Protocol

### Endpoint

```
GET /ws/agent/{session_id}
```

Connection requires a short-lived session token bound to the `goal_id`. Localhost-only in v1 unless an explicit tunnel is configured.

### Server → Client message types

| Type | When emitted |
|---|---|
| `session.started` | WebSocket connection accepted |
| `goal.updated` | Goal state changed |
| `agent.planning` | Planner is choosing next action |
| `agent.action.started` | Action execution begins |
| `agent.action.completed` | Action execution ends (success or fail) |
| `agent.observation` | Observation persisted after action |
| `agent.artifact.created` | New artifact written to disk |
| `agent.needs_approval` | Risky action awaiting approval |
| `agent.paused` | Loop paused (approval gate, decision point, or explicit pause) |
| `agent.completed` | Goal reached terminal success state |
| `agent.failed` | Loop hit unrecoverable error |
| `heartbeat` | Periodic keepalive |

### Client → Server message types

| Type | Payload |
|---|---|
| `approve` | `{action_id, note}` |
| `reject` | `{action_id, note}` |
| `pause` | `{}` |
| `resume` | `{}` |
| `cancel` | `{}` |
| `update_objective` | `{objective_patch}` |
| `ping` | `{}` |

### Message schema (all messages)

```json
{
  "session_id": "sess_abc123",
  "goal_id": "goal_xyz789",
  "trace_id": "tr_001",
  "timestamp": "2025-01-01T00:00:00Z",
  "type": "agent.action.started",
  "payload": {}
}
```

**Size constraints:**
- Payload is always small (metadata only).
- Large artifacts are referenced by path + SHA256 hash + preview snippet, never inlined.
- Full stdout/stderr is written to artifact file; only first 200 chars appear in event payload.
- Secrets are redacted before any event is emitted.

---

## 7. WebSocket Reconnect and Event Replay

### Reconnect behavior

When a client reconnects (after drop or refresh), it sends its last known event cursor:

```json
{ "type": "reconnect", "last_event_seq": 42 }
```

The server replays **all events from `seq=0`** (i.e., from the beginning of the goal). This is simpler than cursor-based partial replay and avoids state reconstruction bugs. The full event log is small enough (bounded by `max_steps`) that full replay is acceptable in v1.

### Event log as replay source

All events are persisted to `logs/agent_goals/<goal_id>/timeline.jsonl` with a monotonic `seq` field. On reconnect, the server streams all lines from `timeline.jsonl` before resuming live events. The client deduplicates by `trace_id` if needed.

### Initial connection

On first connect (no cursor), server sends:
1. A `goal.updated` snapshot (full current goal state)
2. Full replay of all events so far
3. Live events from that point forward

---

## 8. Goal and Session State Model

### Directory layout

```
logs/agent_goals/<goal_id>/
  goal.json           # current goal state (status, scope, budget, objective)
  timeline.jsonl      # append-only event log (seq, trace_id, type, payload)
  approvals.jsonl     # approval decisions log
  sessions/
    <session_id>.json # session metadata and WS status
  artifacts/
    <trace_id>/       # per-action artifacts
      stdout.txt
      stderr.txt
      files/
  report.md           # generated summary
```

### `goal.status` values

| Status | Meaning |
|---|---|
| `active` | Created, not yet started |
| `running` | Loop executing |
| `paused` | Explicitly paused by operator |
| `needs_approval` | Blocked on pending approval |
| `completed` | Terminal success |
| `cancelled` | Explicitly cancelled |
| `blocked` | Loop cannot find a valid next action |
| `failed` | Unrecoverable runtime error |

### `session.status` values

| Status | Meaning |
|---|---|
| `open` | WS connection active |
| `streaming` | Events actively being emitted |
| `idle` | Connected but loop is paused |
| `closed` | Client disconnected cleanly |
| `dropped` | Connection lost unexpectedly |

---

## 9. Agent Runtime Loop

### Module location

`app/agent_runtime/loop.py`

### Loop pseudocode

```python
def run_loop(goal_id: str):
    goal = load_goal(goal_id)
    
    while True:
        # 1. Pre-flight checks
        if budget_exhausted(goal):
            emit("agent.paused", reason="budget_exhausted")
            break
        if scope_violated(goal):
            emit("agent.failed", reason="scope_violation")
            break

        # 2. Plan next action
        emit("agent.planning")
        action = _plan_next_action(goal, context=load_context(goal))
        
        if action is None:
            emit("agent.paused", reason="no_valid_action")
            break

        # 3. Fingerprint check (loop detection)
        if is_duplicate_action(goal, action):
            emit("agent.paused", reason="loop_detected")
            break

        # 4. Risk check → approval gate
        if requires_approval(action, goal.risk_policy):
            emit("agent.needs_approval", action_id=action.id)
            decision = wait_for_approval(action.id, timeout=goal.approval_timeout)
            log_approval(goal_id, action.id, decision)
            if decision == "reject" or decision == "timeout":
                emit("agent.paused", reason=f"approval_{decision}")
                break

        # 5. Execute
        emit("agent.action.started", action=action)
        result = _execute_action(goal, action)
        persist_artifacts(goal, action, result)
        emit("agent.action.completed", action=action, result=result)

        # 6. Observe
        observation = _observe(result)
        persist_observation(goal, observation)
        emit("agent.observation", observation=observation)

        # 7. Evaluate continuation
        status = _should_continue(goal, action, result)
        
        if status == "complete":
            emit("agent.completed")
            break
        elif status == "decision_point":
            emit("agent.paused", reason="decision_point")
            break
        elif status == "blocked":
            emit("agent.paused", reason="blocked")
            break
        # else: continue to next iteration
        
        goal = reload_goal(goal_id)  # pick up any patches from operator
```

### Stop conditions

The loop stops when any of the following are true:

- `max_steps` reached
- `max_seconds` elapsed
- Approval gate: action rejected or timed out
- Loop detection: fingerprint collision
- No valid next action found
- Goal objective assessed as complete
- Decision point reached (milestone requiring human judgment)
- Session dropped and mode is not `detached`

---

## 10. Planner Design — Hybrid Rule + LLM

### Architecture

```
_plan_next_action(goal, context)
    │
    ├─ Rule filter layer (fast, deterministic)
    │   ├─ Check scope constraints
    │   ├─ Check budget remaining
    │   ├─ Check fingerprint history (reject already-seen actions)
    │   ├─ Check risk policy (flag for approval if needed)
    │   └─ Produce candidate action list
    │
    └─ LLM decision layer (reasoning over candidates)
        ├─ Input: goal objective, current context, candidate actions, observation history
        ├─ Output: selected action + rationale
        └─ Fallback: if LLM fails or returns invalid action → rule-based fallback action
```

### Rule filter responsibilities

- **Scope check:** reject any action touching paths or hosts outside `allowed_paths` / `allowed_hosts`.
- **Budget check:** reject if action would exceed remaining step or time budget.
- **Fingerprint check:** reject actions whose fingerprint appears in recent window (see Section 11).
- **Risk classification:** tag actions as `safe`, `low_risk`, `high_risk`, `requires_approval`.
- **Category constraints:** enforce CTF category-specific action allowlists.

### LLM decision layer

- Called with a structured prompt containing: objective, last N observations, candidate action list (post-filter), goal metadata.
- Must select one action from the candidate list (no free-form new actions).
- Returns: `{action_id, rationale, confidence}`.
- If response is malformed or selects an action not in the candidate list → fallback to rule-based highest-priority candidate.
- LLM call is **optional**: if no LLM is configured, rule layer selects highest-priority candidate deterministically.

---

## 11. Loop Detection — Action Fingerprint

### Fingerprint schema

Each action produces two fingerprints:

**Type A — structural fingerprint:**
```python
fp_structural = sha256(f"{action.type}:{sorted(action.args.items())}")
```

**Type B — content fingerprint:**
```python
fp_content = sha256(action.command_string)  # if applicable
```

Both fingerprints are stored in `goal.json` under `action_fingerprint_history`.

### Detection logic

```python
SLIDING_WINDOW = 10  # last N actions

def is_duplicate_action(goal, action):
    recent = goal.action_fingerprint_history[-SLIDING_WINDOW:]
    fp_s = compute_structural_fp(action)
    fp_c = compute_content_fp(action)
    
    # Structural match: same action type + args
    if fp_s in [r.fp_structural for r in recent]:
        return True
    
    # Content match: identical command string
    if fp_c and fp_c in [r.fp_content for r in recent]:
        return True
    
    return False
```

When a duplicate is detected, the loop emits `agent.paused` with `reason="loop_detected"` and writes a diagnostic entry to `timeline.jsonl`. The operator can inspect and either cancel, update the objective, or resume with a patch.

---

## 12. Approval System

### Approval timeout policy

Default timeout: **120 seconds** (configurable per goal via `budget.approval_timeout`).

On timeout: **auto-reject** (safe default). The loop pauses and emits:
```json
{
  "type": "agent.paused",
  "payload": {
    "reason": "approval_timeout",
    "action_id": "act_001",
    "action_type": "broad_scan",
    "timeout_seconds": 120
  }
}
```

The operator can resume after inspecting and calling `agent_approve` or adjusting the risk policy.

### Actions requiring mandatory approval

| Category | Action type |
|---|---|
| Package management | `install_package`, `pip_install`, `npm_install` |
| Container ops | `docker_build`, `docker_run` (new image) |
| Destructive ops | `rm -rf`, `overwrite`, `format`, `wipe` |
| Network scanning | `broad_scan`, `port_scan`, `service_enum` |
| Remote exploitation | `remote_exploit`, `send_payload_remote` |
| Unknown hosts | Any network action to a host not in `allowed_hosts` |
| Flag submission | `submit_flag` (CTF) |

### Approval queue persistence

All pending and resolved approvals are appended to `approvals.jsonl`:
```json
{
  "action_id": "act_001",
  "action_type": "broad_scan",
  "requested_at": "...",
  "decided_at": "...",
  "decision": "approve",
  "note": "safe to scan 10.0.0.0/24",
  "decided_by": "operator"
}
```

---

## 13. Safety Model

### Default budget values (enforced if not specified)

| Parameter | Default |
|---|---|
| `max_steps` | 20 |
| `max_seconds` | 900 |
| `max_consecutive_actions` | 5 |
| `approval_timeout` | 120s |
| `retry_budget` | 3 per action |

### Write scope

Agent can only write to:
- `AGENT_WORKSPACE_DIR` (configured at startup)
- `cwd` specified in goal (if within allowed prefix)
- Artifact directory under `logs/agent_goals/<goal_id>/`

Any write outside these paths raises a `scope_violation` and terminates the loop.

### Network scope

Agent respects the existing MCP network allowlist. No new hosts are contacted without explicit `allowed_hosts` in goal scope. Broad scans require approval regardless of scope.

### Additional safeguards

- `dry_run_first=true`: new command patterns are dry-run before execution.
- `policy_check`: every action passes through the rule filter before execution.
- `action fingerprint`: duplicate detection via sliding window (see Section 11).
- `retry_budget`: separate from `max_steps`; limits retries on infra errors without burning step budget.

---

## 14. CTF-Specific Behavior

Agent autonomous mode for CTF follows `GPT.md` and the harness:

- Load `ctf_harness_instructions` before first action.
- Local-first: run local exploit/solver before attempting remote.
- Proof required: `proof.json` must exist before claiming solved.
- Remote only after local exploit/solver has a working foundation.
- Save `proof.json`, transcript, and hashes as artifacts.

### Per-category behavior

**pwn:** triage binary → local recon → gadget/libc identification → local exploit template → pause (approval before remote)

**web:** triage → target map → safe recon plan → pause (approval before any active scan)

**crypto:** classify cipher/protocol → file/math recon → solver scaffold → pause

**forensics:** metadata extraction → carving/stego triage → pause

**reverse:** static triage → decompiler plan → local patch/solver scaffold → pause

---

## 15. Refactor Strategy (from `agent_step`)

No rewrite from scratch. Preserve existing infrastructure:

- Keep `goal.json`, `timeline.jsonl`, `artifacts/`
- Keep `_run_next_safe_action()` logic as the basis for the rule filter layer
- Keep harness tools untouched

### Refactor targets

| Before | After |
|---|---|
| `_run_next_safe_action(goal)` | Split into `_plan_next_action(goal, context)` + `_execute_action(goal, action)` |
| `agent_step()` | Becomes a thin wrapper: calls one loop iteration and returns |
| New: `agent_goal_start()` | Calls the loop for N iterations until stop condition |
| New: `_should_continue(goal, action_result)` | Evaluates continuation logic |
| New: `_observe(result)` | Extracts structured observation from action result |

`agent_step()` remains fully functional and is the fallback for single-step mode.

---

## 16. Phase Roadmap

### Phase 1 — Session and event foundation

**Goal:** Stream single-step events over WebSocket.

Deliverables:
- WebSocket endpoint `GET /ws/agent/{session_id}`
- Session store (`sessions/<session_id>.json`)
- Event schema + emitter (all types from Section 6)
- `agent_session_open`, `agent_session_status`, `agent_session_close` tools
- Event persistence to `timeline.jsonl` with monotonic `seq`
- Full replay on reconnect

**Done when:** Create goal → open WS → call `agent_step` → receive events in real time → disconnect → reconnect → receive full replay.

---

### Phase 2 — Multi-step bounded loop

**Goal:** Run N consecutive actions in one `agent_goal_start` call.

Deliverables:
- `agent_goal_start(mode="bounded_auto")`
- Runtime loop (`app/agent_runtime/loop.py`)
- Budget enforcement (steps, seconds, consecutive actions)
- Loop detection (action fingerprint, both types)
- Pause on `needs_approval` and `decision_point`
- `agent_goal_pause`, `agent_goal_resume` tools
- Hybrid planner (rule filter + optional LLM layer)

**Done when:** One session runs 3–10 actions consecutively, pauses correctly on budget/gate, and resumes on operator command.

---

### Phase 3 — Approval bus

**Goal:** Full real-time approval flow.

Deliverables:
- Approval queue in `approvals.jsonl`
- `agent.needs_approval` event with full action metadata
- `approve`/`reject` client → server messages
- Timeout auto-reject (120s default)
- `agent_approve`, `agent_pending_approvals` tools
- Loop resumes immediately on approval

**Done when:** Risky action triggers `needs_approval` → operator approves via WS → loop continues; or timeout → auto-reject → loop pauses cleanly.

---

### Phase 4 — Detached run and watchdog

**Goal:** Goal survives session disconnection.

Deliverables:
- `mode="detached"` option in `agent_goal_start`
- Watchdog process that restarts loop on interrupt
- Stale lock handling (detect crashed loop, recover state)
- Session reconnect picks up in-progress goal

**Done when:** Kill WS session mid-run → goal keeps running → reconnect → receive full event replay → goal state is consistent.

---

### Phase 5 — VPS/workspace profile

**Goal:** Same session model works on VPS with docker/workspace context.

Deliverables:
- `profile="vps"` enables docker/workspace mode
- WS streams runner/workspace status events
- Import/sync path into workspace on demand

**Done when:** Local host and VPS workspace share the same session model, differing only in policy/profile config.

---

## 17. Test Plan

### Unit tests

- Goal/session lifecycle state machine
- WS message schema validation
- Approval queue: enqueue, approve, reject, timeout
- Budget exhaustion (steps, seconds, consecutive)
- Pause/resume/cancel state transitions
- Event persistence and seq ordering
- Action fingerprint: structural match, content match, sliding window eviction
- Loop detection trigger and diagnostic log

### Integration tests

- Create goal → open WS → start session → receive ordered events
- Risky action → `needs_approval` → approve → loop continues
- Risky action → `needs_approval` → timeout 120s → auto-reject → loop pauses
- Loop detection → `agent.paused(reason="loop_detected")` → operator patches objective → resume
- CTF harness init/check → event stream in correct order
- WS disconnect mid-run → reconnect → full event replay → state consistent

### Regression tests

- All existing `agent_step` tests pass unchanged
- All existing `ctf_harness_*` tests pass unchanged
- All existing `get_capabilities` tests pass unchanged

---

## 18. WebSocket Security

- **Session token:** short-lived, bound to `goal_id`, single-use for connection upgrade.
- **Scope binding:** session cannot send messages for a different `goal_id`.
- **Localhost-only in v1:** no public exposure unless explicit tunnel is configured.
- **Max message size:** 64KB inbound, enforced at WS layer.
- **Heartbeat timeout:** 30s; server closes connection if no `ping` received.
- **Secret redaction:** stdout/stderr are scrubbed for common secret patterns (API keys, tokens, passwords) before any event payload is emitted.
- **Artifact size policy:** artifacts > 10MB are referenced by path + hash only; no content inline.
- **Concurrency (v1):** single active session per goal; second connection attempt returns error. Multi-session support is out of scope for v1.

---

## 19. Non-Goals

These are explicitly out of scope and should not be added without a new plan:

- No persistent global memory across goals.
- Agent cannot self-expand its scope; all scope changes require operator `agent_goal_update`.
- No removal of approval gates or budget limits for "speed."
- No full ChatGPT context streamed into MCP.
- MCP is not a reasoning engine; ChatGPT web remains the brain.
- No multi-session concurrency support in v1.

---

## 20. Definition of Done (v1)

v1 is considered complete when:

- WebSocket session channel is operational (Phase 1).
- Agent runs bounded multi-step loop (Phase 2).
- Approval bus is live with timeout auto-reject (Phase 3).
- Existing `agent_step` and harness tools are fully regression-tested.
- Trusted-operator safety model is preserved end-to-end.
- All events are persisted and replayable on reconnect.
- Loop detection prevents infinite spin on stuck planner.

---

## 21. Suggested Implementation Order

1. Event schema + WebSocket endpoint (Phase 1 foundation)
2. Session persistence (`sessions/<session_id>.json`, `timeline.jsonl` with seq)
3. Reconnect/replay logic (full replay from seq=0)
4. Refactor `agent_step` → `_plan_next_action` + `_execute_action` + `_should_continue`
5. Action fingerprint (both types, sliding window)
6. `agent_goal_start` + runtime loop with budget enforcement
7. `agent_goal_pause` / `agent_goal_resume`
8. Approval bus (queue, timeout, WS messages)
9. Hybrid planner (LLM layer on top of rule filter)
10. Detached run + watchdog (Phase 4)
11. VPS/workspace profile (Phase 5)