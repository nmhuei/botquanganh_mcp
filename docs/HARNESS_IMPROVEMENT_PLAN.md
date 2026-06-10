# CTF Harness Improvement Plan

Mục tiêu: nâng cấp `ctfharness` từ một CLI/MCP wrapper chạy lệnh thành một
harness CTF có workspace, trace, evidence, policy, replay và proof rõ ràng, đủ
ổn định để ChatGPT dùng qua MCP mà không bị loop, không claim flag thiếu chứng
cứ, và dễ debug khi workflow fail.

Plan này dựa trên code hiện tại của repo và các pattern từ những agent/harness
lớn: OpenHands, SWE-agent, LangGraph, OpenAI Agents SDK, Claude Code hooks,
Google ADK, cùng các ghi chú archive trước đó.

## Current State

Đang có:

```text
app/tools/ctf_harness.py
  MCP wrapper cho ctfharness.cli

ctfharness/
  cli.py             init/check/local/solve/remote/verify/workspace/report/pack
  config.py          load/normalize ctf.yaml
  flag.py            detect flag candidates and verifier command
  logging_utils.py   command logs, sha256, JSONL append
  scope.py           authorized remote target parser/checker

GPT.md
  operating instructions returned by ctf_harness_instructions

templates/
skills/
docs/archive/harnes_ctf.md
```

Điểm tốt:

- Có local-first gate trước remote.
- Có `ctf.yaml` làm source of truth cho challenge.
- Có workspace theo challenge.
- Có command transcript/hash.
- Có verifier phân biệt `candidate` và `verified`.
- Có MCP tool surface tương đối gọn.

Vấn đề còn lại:

- Workspace chưa có registry/list/resume mạnh.
- `timeline.jsonl` còn thô, thiếu event schema thống nhất.
- `ctf_harness_check` chưa phải doctor/preflight đầy đủ.
- Triage/recon còn do agent tự nghĩ, chưa có tool structured.
- Proof bundle chưa đủ replayable theo chuẩn "người khác chạy lại được".
- Policy nằm rải rác giữa `.env`, `ctf.yaml`, `app.security`, `scope.py`.
- Tool output vẫn thiên về stdout/stderr text, chưa đủ machine-readable.
- Chưa có loop/dead-end accounting ở harness level.
- Chưa có benchmark/eval mini để đo harness có thật sự cải thiện không.

## Research Findings

### OpenHands

Pattern nên học:

- Tách agent decision khỏi sandbox/runtime.
- Có sandbox provider rõ: Docker, process, remote.
- Workspace là nơi agent chạy lệnh, sửa file, start server.
- Runtime/sandbox choice là config, không trộn vào tool logic.

Áp dụng:

- Định nghĩa `execution_profile`: `host`, `docker`, `remote`.
- `ctf_harness_doctor` phải nói rõ profile nào dùng được.
- Mọi command execution trả về profile, cwd, run_id, transcript path.

### SWE-agent

Pattern nên học:

- Environment lifecycle có hooks.
- Trajectory tách khỏi history; trajectory dùng để replay/debug.
- Mỗi step lưu action/observation, save sau từng bước.
- Environment reset/resume/new-attempt là primitive rõ ràng.

Áp dụng:

- Thêm `trace_id` và `run_id` cho mọi harness command.
- Chuẩn hóa `timeline.jsonl` thành trajectory event stream.
- Thêm hook points: `pre_run`, `post_run`, `post_verify`, `on_fail`.
- Thêm `attempt_id` để phân biệt các lần thử exploit.

### LangGraph

Pattern nên học:

- Checkpoint sau từng node/step.
- Resume, human-in-the-loop, time travel/debug.
- State schema rõ hơn log tự do.

Áp dụng:

- `state.json` không chỉ có phase; nó phải là checkpoint:
  - current phase
  - hypotheses
  - attempts
  - last successful evidence
  - blocked reason
  - next suggested action
- Thêm `ctf_harness_state` và `ctf_harness_resume`.

### OpenAI Agents SDK

Pattern nên học:

- Tool calls, handoffs, guardrails, and custom events đều đi vào tracing.
- Guardrails là first-class, không chỉ text hướng dẫn.

Áp dụng:

- Tách policy guardrails thành module `ctfharness/policy.py`.
- Mọi block trả về structured:
  - `blocked=true`
  - `policy`
  - `reason`
  - `suggested_fix`
  - `safe_alternative`
- `ctf_harness_capabilities` phải expose guardrails active.

### Claude Code Hooks

Pattern nên học:

- Hooks chạy ở các lifecycle point: pre tool, post tool, stop, failure.
- Hook input/output là JSON, có thể allow/block/augment context.

Áp dụng:

- `ctf.yaml` có section `hooks`.
- Hook chạy deterministically, không cần LLM:
  - after `solve`: run formatter/linter/sanity checker
  - before `remote`: assert local evidence exists
  - after `verify`: copy evidence into proof bundle

### Google ADK

Pattern nên học:

- Session, event, artifact là core concepts.
- Code execution là tool capability, artifact management là riêng.

Áp dụng:

- Tách `runs/`, `artifacts/`, `findings/`, `deliverables/`.
- Thêm artifact index: path, sha256, mime/type, source event.
- `ctf_harness_pack` dùng artifact index thay vì zip thô.

## Target Architecture

Giữ `ctfharness` là deterministic harness, không biến nó thành autonomous LLM
agent. ChatGPT vẫn là planner/reasoner; harness là execution/control plane.

```text
app/tools/ctf_harness.py
  MCP adapter, validation, output truncation

ctfharness/
  cli.py              CLI entrypoint only
  config.py           ctf.yaml schema and migration
  workspace.py        registry, create/import/list/resume/archive
  state.py            state.json checkpoints
  events.py           timeline event schema and append/query
  policy.py           local/remote/scope/command guardrails
  doctor.py           profile/toolchain checks
  triage.py           file inventory and category candidates
  recon.py            category-safe recon runners
  runner.py           command execution and transcript metadata
  evidence.py         findings, flags, primitives, dead ends
  proof.py            replayable proof bundle
  report.py           writeup seed/report generation
  hooks.py            deterministic lifecycle hooks
```

Workspace target:

```text
workspaces/<challenge>/
  workspace.json
  ctf.yaml
  state.json
  input/
    original/
    normalized/
    MANIFEST.json
  work/
    notes.md
    exploit/
      solve.py
      attempts/
  runs/
    <run_id>.json
    <run_id>.stdout
    <run_id>.stderr
    <run_id>.combined.log
  traces/
    <trace_id>.jsonl
  artifacts/
    index.jsonl
    extracted/
    captures/
  findings/
    flags.jsonl
    primitives.jsonl
    dead_ends.jsonl
  deliverables/
    proof_bundle.json
    replay.sh
    writeup.md
```

## Proposed MCP Tool Surface

Keep current tools, add these in phases:

```text
ctf_harness_doctor(category="", profile="auto")
ctf_harness_state(cwd="", config="ctf.yaml")
ctf_harness_list_workspaces(limit=50)
ctf_harness_import(src_path, cwd="", mode="copy")
ctf_harness_triage(cwd="", config="ctf.yaml", max_files=300)
ctf_harness_recon(cwd="", config="ctf.yaml", category="", safe=true)
ctf_harness_record_finding(cwd="", kind, title, evidence_path="", confidence="")
ctf_harness_trace(cwd="", trace_id="", tail=100)
ctf_harness_proof_bundle(cwd="", config="ctf.yaml")
ctf_harness_resume(cwd="", config="ctf.yaml")
```

Do not remove existing tools until new tools cover them:

```text
ctf_harness_init
ctf_harness_check
ctf_harness_local
ctf_harness_solve
ctf_harness_verify
ctf_harness_report
ctf_harness_pack
```

## Event Schema

Every event in `timeline.jsonl` or `traces/<trace_id>.jsonl` should follow:

```json
{
  "schema_version": 1,
  "ts": "2026-06-08T00:00:00Z",
  "workspace_id": "baby-web",
  "trace_id": "tr_...",
  "run_id": "run_...",
  "phase": "recon",
  "kind": "command.finished",
  "actor": "harness",
  "category": "web",
  "summary": "curl /health returned 200",
  "inputs": {},
  "outputs": {},
  "artifacts": [],
  "policy": {
    "profile": "host",
    "remote_allowed": true
  }
}
```

Event kinds:

```text
workspace.created
workspace.imported
phase.changed
doctor.checked
triage.completed
recon.completed
command.started
command.finished
command.failed
finding.recorded
flag.candidate
flag.verified
policy.blocked
hook.started
hook.finished
proof.built
report.built
dead_end.recorded
```

## Phase Roadmap

### Phase 0: Baseline And Tests

Goal: freeze current behavior before refactor.

Tasks:

- Add snapshot tests for existing `ctf_harness_*` MCP tools.
- Add CLI fixture challenge:
  - local echo flag
  - fake decoy flag
  - remote-gated config
- Add tests for:
  - `init -> check -> local --solve -> verify -> report -> pack`
  - local-only candidate does not become verified
  - remote solve without local evidence is blocked

Acceptance:

- Current command still passes:

```bash
DISABLE_SECURITY_POLICIES=false ALLOWED_TCP_TARGETS=1.1.1.1:80 .venv/bin/python -m pytest tests -q
```

### Phase 1: Workspace Registry And State

Goal: make resume/list/debug first-class.

Implement:

- `ctfharness/workspace.py`
- `ctfharness/state.py`
- `workspace.json`
- `state.json` migration from current simple format
- `ctf_harness_state`
- `ctf_harness_list_workspaces`
- `ctf_harness_resume`

Acceptance:

- Re-running `ctf_harness_init` with same name gives clear existing workspace
  response.
- `ctf_harness_state` returns current phase, last run, last evidence, and next
  suggested action.
- Workspace can be resumed after process restart.

### Phase 2: Doctor And Capability Truth

Goal: stop failures caused by missing tools or wrong profile.

Implement:

- `ctfharness/doctor.py`
- `ctf_harness_doctor(category="", profile="auto")`
- Tool checks per category:
  - web: `curl`, `jq`, Python `requests`, optional `ffuf`
  - pwn: `file`, `readelf`, `checksec`, `gdb`, `python -c import pwn`
  - reverse: `file`, `strings`, `objdump`, optional `rizin`, `ghidra`
  - crypto: Python `Crypto`, `sympy`, optional `sage`
  - forensics: `binwalk`, `exiftool`, `tshark`, optional `volatility`

Acceptance:

- Missing tools return `ok=false` with install suggestion, not a stack trace.
- `ctf_harness_capabilities` includes doctor summary and active policy profile.

### Phase 3: Triage And Structured Recon

Goal: reduce agent wandering by giving it reliable first-pass observations.

Implement:

- `ctfharness/triage.py`
- `ctfharness/recon.py`
- `ctf_harness_import`
- `ctf_harness_triage`
- `ctf_harness_recon`

Triage output:

```json
{
  "category_candidates": [
    {"category": "web", "confidence": 0.82, "reason": "Dockerfile + app.py + routes"}
  ],
  "interesting_files": [],
  "extracted_targets": [],
  "suggested_next_tools": []
}
```

Acceptance:

- Triage never executes untrusted challenge code.
- Recon commands are category-safe and logged.
- Every output links to artifact/run IDs.

### Phase 4: Trace, Findings, And Dead Ends

Goal: make loops visible and recoverable.

Implement:

- `ctfharness/events.py`
- `ctfharness/evidence.py`
- `ctf_harness_trace`
- `ctf_harness_record_finding`
- structured `dead_ends.jsonl`

Rules:

- Same failed command/hypothesis repeated 3 times records a dead end.
- `ctf_harness_state` surfaces repeated dead ends to the caller.
- Findings require source artifact/run ID.

Acceptance:

- A repeated failing exploit attempt is visible as a dead end.
- Agent can ask for `ctf_harness_trace(tail=...)` and get compact structured
  context.

### Phase 5: Policy And Hooks

Goal: move safety from prose into deterministic checks.

Implement:

- `ctfharness/policy.py`
- `ctfharness/hooks.py`
- `hooks` section in `ctf.yaml`

Example config:

```yaml
hooks:
  before_remote:
    - python3 scripts/check_local_evidence.py
  after_solve:
    - python3 scripts/extract_flag_candidates.py
```

Policy output:

```json
{
  "ok": false,
  "blocked": true,
  "policy": "remote_requires_local_evidence",
  "reason": "No local proof file found",
  "suggested_fix": "Run ctf_harness_local(solve=true) then ctf_harness_verify(mode='local')"
}
```

Acceptance:

- Remote execution block is structured and test-covered.
- Hooks can add artifacts/events.
- Hook failures are visible but do not corrupt state.

### Phase 6: Proof Bundle And Report

Goal: make solve artifacts replayable and shareable.

Implement:

- `ctfharness/proof.py`
- `ctfharness/report.py`
- upgrade `ctf_harness_pack` into `ctf_harness_proof_bundle`

Bundle includes:

```text
proof_bundle.json
replay.sh
writeup.md
ctf.yaml
state.json
artifact index
selected transcripts
solver files with sha256
verified flag evidence, if any
```

Acceptance:

- Bundle is enough for another operator to reproduce the solve path.
- Report clearly labels `candidate`, `candidate-local`, and `verified`.

### Phase 7: Harness Eval

Goal: know whether the harness improved instead of just growing.

Create mini benchmark under `tests/fixtures/ctf_harness_cases/`:

```text
web_echo_flag/
pwn_mock_service/
crypto_static_params/
forensics_zip_layer/
decoy_flag/
remote_requires_local_evidence/
```

Metrics:

- steps to verified evidence
- repeated dead-end count
- missing-tool clarity
- proof bundle completeness
- no false verified flags

Acceptance:

- `scripts/test_harness_eval.sh` runs all cases locally.
- Plan/regression is visible in CI or normal test command.

## Migration Strategy

Do not big-bang rewrite.

1. Add new modules behind existing CLI.
2. Keep old workspace layout readable.
3. Add migration function:

```text
ctfharness.state.migrate_workspace(base)
```

4. Existing `ctf_harness_*` tools call new internals when available.
5. Deprecate only after tests cover equivalent behavior.

## Priority Order

Highest ROI:

1. Phase 0 tests
2. Phase 1 state/resume
3. Phase 2 doctor
4. Phase 4 trace/dead-end visibility

Then:

5. Phase 3 triage/recon
6. Phase 5 policy/hooks
7. Phase 6 proof bundle
8. Phase 7 eval

## Non-Goals

- Do not build another autonomous agent loop inside `ctfharness`.
- Do not make harness call an LLM directly.
- Do not load every skill into every tool call.
- Do not expose host command execution as part of basic harness profile.
- Do not mark regex flag matches as verified without verifier/remote acceptance.

## File-Level Implementation Checklist

```text
ctfharness/workspace.py      new
ctfharness/state.py          new
ctfharness/events.py         new
ctfharness/doctor.py         new
ctfharness/triage.py         new
ctfharness/recon.py          new
ctfharness/policy.py         new
ctfharness/evidence.py       split/extend from flag.py
ctfharness/proof.py          new
ctfharness/report.py         split from cli.py
ctfharness/hooks.py          new
ctfharness/cli.py            thin orchestration only
app/tools/ctf_harness.py     add MCP wrappers for new functions
GPT.md                       keep instructions aligned with tool surface
README.md                    add operator docs when tools land
tests/test_ctf_harness.py    expand
tests/fixtures/              add harness eval cases
```

## First Concrete PR

Recommended first implementation PR:

```text
Title: Add CTF harness state, workspace registry, and doctor preflight

Includes:
  - ctfharness/state.py
  - ctfharness/workspace.py
  - ctfharness/doctor.py
  - ctf_harness_state MCP tool
  - ctf_harness_doctor MCP tool
  - tests for init/check/state/doctor

Excludes:
  - recon automation
  - hooks
  - proof bundle rewrite
```

This gives immediate operational value and creates the foundation for later
trace/recon/proof work.

## References

- OpenHands sandbox/runtime model: https://docs.openhands.dev/openhands/usage/runtimes/overview
- OpenHands remote agent server architecture: https://docs.openhands.dev/sdk/guides/agent-server/overview
- SWE-agent architecture/environment/trajectory docs: https://swe-agent.com/0.7/background/architecture/
- SWE-agent environment hooks reference: https://swe-agent.com/latest/reference/env/
- LangGraph persistence/checkpointing: https://docs.langchain.com/oss/python/langgraph/persistence
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Google ADK technical overview: https://google.github.io/adk-docs/get-started/about/
