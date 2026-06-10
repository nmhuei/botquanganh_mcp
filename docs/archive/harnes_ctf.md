# Harnes CTF cho botquanganh_mcp

Tham chieu:

- `openclaw/openclaw.git`: control plane, transport discipline, structured logs, policy boundary.
- `KeygraphHQ/shannon.git`: workspace/resume model, proof-by-exploitation pipeline, CLI/worker split, preflight, deliverables.
- `ljagiello/ctf-skills`: taxonomy CTF, category-specific prerequisites, first-pass triage, pivot rules.

Muc tieu cua harnes nay: bien MCP thanh lop chay tool CTF muot cho ChatGPT web. ChatGPT web giu context, chien luoc, suy luan va quyet dinh buoc tiep. MCP chi can nhan tool call ro rang, thuc thi on dinh, log day du, va tra observation ngan gon.

## 1. Khong phai agent runtime

Non-goal:

- Khong tao planner loop.
- Khong tao memory store dai han.
- Khong tu solve challenge neu ChatGPT khong goi tool.
- Khong nhung skill text dai vao moi request.
- Khong bien MCP thanh mot agent doc lap giong Shannon/OpenClaw day du.

State duoc phep giu:

- `harness_id`
- `workspace_id`
- `run_id`
- `trace_id`
- `artifact_id`
- file path, sha256, command transcript

Tat ca state tren la state ky thuat de replay/debug, khong phai task memory.

## 2. Bai hoc lay tu OpenClaw

OpenClaw dang hoc o muc infrastructure:

- Co control plane ro: tool registry, capability discovery, profile, diagnostics.
- Tach transport/runtime khoi tool logic.
- Log co cau truc de debug loi thuc thi thay vi chi tra string.
- Security boundary phai document ro, khong de policy block mo ho.
- Co doctor/onboard de biet moi truong dang thieu gi.

Ap dung vao harnes CTF:

- `get_ctf_harness_capabilities()` phai noi ro tool nao co, image nao san sang, category nao supported.
- `doctor_ctf_harness()` kiem tra Docker, Python venv, pwntools, sage, gdb, ghidra/rizin, tshark, binwalk, volatility, ffuf, curl, jq.
- Moi tool call co `trace_id`, `profile`, `category`, `workspace_id`.
- Loi block phai tra `blocked_reason`, `matched_fragment`, `suggested_tool`.
- Log JSONL de ChatGPT co the goi `get_trace()` doc lai.

## 3. Bai hoc lay tu Shannon

Shannon dang hoc o muc harness pipeline:

- Moi run tao workspace rieng.
- Target repo/source mounted read-only khi can isolation.
- Workspace co log, prompts, artifacts, deliverables.
- Co preflight truoc khi chay workflow nang.
- Co resume bang workspace name.
- Bao cao chi lay finding co proof thuc thi.
- Config gom scope, auth, rules of engagement, rate/concurrency.

Ap dung vao CTF:

- Moi challenge tao workspace rieng trong `~/Workspace/CTF/_harness/<slug>/`.
- Challenge input giu read-only trong `input/`.
- Scripts/exploits do ChatGPT tao nam trong `work/`.
- Output nam trong `artifacts/`.
- Transcript command/network nam trong `runs/`.
- Flag candidates nam trong `findings/flags.jsonl`.
- Writeup/proof bundle nam trong `deliverables/`.
- Resume bang `workspace_id`, nhung khong resume reasoning.

## 4. Bai hoc lay tu ctf-skills

ctf-skills dang hoc o muc category taxonomy:

- Co dispatcher `solve-challenge` de triage truoc.
- Co category skills: web, pwn, crypto, reverse, forensics, osint, malware, misc, ai-ml.
- Moi category co prerequisites rieng.
- Co pivot rules khi category ban dau sai.
- Co quick commands va flag validation rule.

Ap dung vao harnes:

- Harness co `category_profile`, khong load ca kho skill vao context.
- Tool `ctf_triage()` chi tra category candidates + suggested next tools.
- Tool `ctf_prepare_env(category)` cai/verify dung tool group.
- Tool `ctf_quick_recon(category, workspace_id)` chay recon an toan theo category.
- Tool `ctf_record_flag_candidate()` luu flag-like strings kem source va confidence.
- Tool `ctf_build_proof_bundle()` gom replay script, transcript, hashes, flag source.

## 5. Kien truc muc tieu

De xuat module:

```text
app/
  ctf_harness/
    __init__.py
    capabilities.py
    profiles.py
    workspace.py
    policy.py
    observations.py
    events.py
    triage.py
    env.py
    recon.py
    evidence.py
    replay.py
    proof.py
```

Nguyen tac:

- `ctf_harness` khong goi LLM.
- `ctf_harness` khong doc/ghi memory.
- Moi function co input/output schema ro.
- Moi output uu tien machine-readable, kem `summary` ngan cho ChatGPT.

## 6. Workspace layout

```text
~/Workspace/CTF/_harness/<workspace_id>/
  workspace.json
  scope.yaml
  input/
    original/
    normalized/
  work/
    notes.md
    solve.py
    exploit.py
    scratch/
  runs/
    <run_id>.json
    <run_id>.stdout
    <run_id>.stderr
    <run_id>.transcript
  artifacts/
    extracted/
    captures/
    binaries/
    screenshots/
  findings/
    flags.jsonl
    primitives.jsonl
    dead_ends.jsonl
  deliverables/
    proof_bundle.json
    replay.sh
    writeup_seed.md
```

`workspace.json` toi thieu:

```json
{
  "workspace_id": "gpn24-food-poisoning",
  "created_at": "2026-06-07T00:00:00Z",
  "category": "misc",
  "input_sha256": {},
  "scope": {
    "local_only": false,
    "allowed_hosts": [],
    "allowed_ports": [],
    "max_rps": 5
  }
}
```

## 7. Tool API de xuat

### 7.1 Capabilities va doctor

```text
ctf_harness_capabilities()
doctor_ctf_harness(category="")
ctf_verify_toolchain(category)
```

Tra ve:

- category supported
- tool installed/missing
- docker image available/missing
- writable dirs
- network policy
- recommended fix command

### 7.2 Workspace

```text
ctf_create_workspace(name, category="", source_path="", remote="")
ctf_import_challenge(workspace_id, src_path, mode="copy")
ctf_list_workspaces(limit=50)
ctf_get_workspace(workspace_id)
ctf_archive_workspace(workspace_id)
```

Rules:

- Import source vao `input/original`.
- Neu source la repo lon, cho phep symlink/bind read-only o host mode.
- Docker/VPS mode uu tien copy hoac mount read-only.

### 7.3 Triage

```text
ctf_triage(workspace_id, max_files=200)
ctf_detect_category(workspace_id)
ctf_suggest_next_tools(workspace_id, category="")
```

Triage nen chay:

- `file`
- `find`
- size/hash
- `strings` ngan
- archive detection
- pcap/image/audio/binary heuristics
- URL/host/port extraction

Output:

```json
{
  "ok": true,
  "category_candidates": [
    {"category": "pwn", "confidence": 0.74, "reason": "ELF + remote port"}
  ],
  "suggested_tools": ["ctf_prepare_env", "ctf_quick_recon"],
  "artifacts": []
}
```

### 7.4 Environment

```text
ctf_prepare_env(category, install=false)
ctf_install_tools(category, dry_run=true)
ctf_runner_image_status(category)
ctf_build_runner_image(category)
```

Category mapping tu ctf-skills:

- `web`: curl, jq, ffuf, sqlmap, flask-unsign, browser/proxy optional.
- `pwn`: pwntools, gdb, checksec, ROPgadget, ropper, one_gadget, seccomp-tools.
- `crypto`: pycryptodome, sage, z3, sympy, gmpy2, fpylll.
- `reverse`: gdb, rizin/radare2, ghidra optional, angr, frida, qiling, unicorn.
- `forensics`: binwalk, foremost, exiftool, tshark, volatility3, sleuthkit, steghide, ffmpeg.
- `osint`: curl, whois, dnsutils, shodan optional.
- `malware`: yara, pefile, volatility3, strings, capa optional.
- `misc`: z3, pwntools, nc, jq, python libs, encoders/decoders.
- `ai-ml`: numpy, torch optional, pillow, sklearn optional.

### 7.5 Execution

```text
ctf_run_command(workspace_id, command, cwd="work", timeout=60, category="")
ctf_run_python(workspace_id, code_or_file, args=[], timeout=60)
ctf_run_sage(workspace_id, file, timeout=300)
ctf_run_binary(workspace_id, binary, args=[], stdin="", timeout=10)
ctf_connect_tcp(workspace_id, host, port, send_lines=[], ssl=false, timeout=10)
ctf_http_request(workspace_id, method, url, headers={}, body="", timeout=20)
```

Execution rules:

- Moi run sinh `run_id`.
- Save stdout/stderr/transcript.
- Hash input/output quan trong.
- Tra observation ngan, khong dump output qua dai.
- Neu output dai, tra `artifact_id` va preview.

### 7.6 Evidence va proof

```text
ctf_record_primitive(workspace_id, type, description, source_run_id, confidence)
ctf_record_flag_candidate(workspace_id, value, source, run_id="", confidence="candidate")
ctf_validate_flag_candidate(workspace_id, value, regex="")
ctf_build_proof_bundle(workspace_id, include_artifacts=true)
ctf_generate_replay_script(workspace_id, run_ids=[])
```

Flag validation:

- Check regex flag format.
- Check uniqueness trong workspace.
- Link toi file/run/source tao ra flag.
- Neu co remote submit tool thi tach rieng, khong auto submit mac dinh.

## 8. Profiles

### `ctf-host`

Default cho may local:

- Chay host command.
- Doc/ghi trong `~/Workspace/CTF`.
- Docker optional.
- Network enabled theo request.

### `ctf-docker`

Dung khi can reproducible runner:

- Mount input read-only.
- Mount work/artifacts writable.
- Network mode configurable.
- Image theo category.

### `ctf-vps`

Dung khi deploy tren VPS:

- Workspace-only write.
- Runner Docker bat.
- Egress allowlist bat neu can.
- Khong mac dinh access ca home.

### `ctf-locked`

Dung de test connector:

- Chi capabilities, doctor, triage read-only.
- Khong run exploit/network.

## 9. Policy va scope

Scope per workspace:

```yaml
category: pwn
local_only: false
allowed_hosts:
  - chal.example.ctf
allowed_ports:
  - 31337
allowed_paths:
  - ~/Workspace/CTF
max_runtime_seconds: 300
max_output_bytes: 200000
```

Policy khong nen chan oan command CTF hop le. Thay vi heuristic mo ho:

- Neu `nc host port` bi nghi risky, route sang `ctf_connect_tcp`.
- Neu `curl` toi host allowlist thi cho phep.
- Neu `gdb`, `strace`, `ltrace`, `qemu` trong workspace thi cho phep.
- Neu command destructive ngoai workspace thi block.
- Neu network toi private IP khi policy cam thi block ro ly do.

Moi block tra:

```json
{
  "ok": false,
  "error": "POLICY_BLOCKED",
  "blocked_reason": "network_host_not_in_scope",
  "matched_fragment": "10.0.0.1",
  "suggested_tool": "ctf_update_scope"
}
```

## 10. Observation format

Tat ca tool nen tra format gan nhau:

```json
{
  "ok": true,
  "summary": "ELF x86_64, NX enabled, no PIE, likely pwn.",
  "workspace_id": "demo-pwn",
  "run_id": "run_123",
  "trace_id": "trace_abc",
  "artifacts": [
    {"artifact_id": "stdout", "path": "runs/run_123.stdout", "sha256": "..."}
  ],
  "next_suggestions": [
    "Run checksec",
    "Find offset with cyclic pattern"
  ]
}
```

`next_suggestions` chi la mechanical hint, khong phai planner. ChatGPT van la noi quyet dinh.

## 11. Flow mau theo category

### 11.1 Unknown challenge

```text
ctf_create_workspace(name, source_path)
ctf_triage(workspace_id)
ctf_prepare_env(category, install=false)
ctf_quick_recon(workspace_id, category)
```

ChatGPT doc observation, chon huong tiep.

### 11.2 Pwn

```text
ctf_prepare_env("pwn")
ctf_run_command(..., "file ./chall && checksec --file=./chall")
ctf_run_command(..., "python3 - <<'PY'\nfrom pwn import *\nprint(cyclic(200))\nPY")
ctf_connect_tcp(..., host, port)
ctf_record_primitive(..., "offset/leak/write primitive")
ctf_build_proof_bundle(...)
```

Artifacts quan trong:

- binary sha256
- libc/ld sha256 neu co
- checksec output
- exploit script
- local transcript
- remote transcript neu co

### 11.3 Web

```text
ctf_prepare_env("web")
ctf_http_request(..., "GET", url)
ctf_run_command(..., "ffuf ...")
ctf_record_primitive(..., "auth bypass/file read/sql injection")
ctf_record_flag_candidate(...)
```

Artifacts:

- raw request/response
- cookies/headers da redact
- exploit script
- screenshot neu co browser tool

### 11.4 Crypto

```text
ctf_prepare_env("crypto")
ctf_run_python(..., "parse params / sanity check")
ctf_run_sage(..., "solve.sage")
ctf_record_flag_candidate(...)
```

Artifacts:

- challenge params hash
- solver
- deterministic output
- math assumptions trong `findings/primitives.jsonl`

### 11.5 Reverse

```text
ctf_prepare_env("reverse")
ctf_run_command(..., "file; strings; readelf")
ctf_run_command(..., "rizin/radare2 batch")
ctf_run_python(..., "patch/extract/checker")
```

Artifacts:

- binary hash
- extracted constants
- patch diff
- final solver

### 11.6 Forensics

```text
ctf_prepare_env("forensics")
ctf_run_command(..., "file; binwalk; exiftool")
ctf_run_command(..., "tshark/volatility/foremost")
ctf_record_flag_candidate(...)
```

Artifacts:

- original evidence hash
- extraction tree manifest
- decoded files hash
- command transcript

## 12. Replay va proof bundle

`proof_bundle.json` nen gom:

```json
{
  "workspace_id": "demo",
  "category": "pwn",
  "flag": {
    "value": "flag{...}",
    "source": "runs/run_009.stdout",
    "confidence": "validated"
  },
  "inputs": [
    {"path": "input/original/chall", "sha256": "..."}
  ],
  "runs": [
    {"run_id": "run_009", "command": "python3 solve.py", "exit_code": 0}
  ],
  "artifacts": [],
  "replay": "deliverables/replay.sh"
}
```

`replay.sh`:

- Set `set -euo pipefail`.
- Assert required files exist.
- Print sha256.
- Run solver/exploit.
- Grep expected flag regex.

## 13. Test plan

Unit tests:

- workspace create/import/list
- category detection by fixture
- env verify with missing tools
- policy allow/block
- observation truncation
- proof bundle generation

Integration tests:

- toy crypto challenge
- toy pwn local binary
- toy web Flask app
- toy forensics zip/png
- TCP echo challenge

Commands:

```bash
./.venv/bin/python -m pytest tests/test_ctf_harness.py -q
./.venv/bin/python -m pytest tests/test_ctf_harness_integration.py -q
```

## 14. Roadmap implement

### Phase 1: Skeleton

- Add `app/ctf_harness/`.
- Add workspace model.
- Add `ctf_harness_capabilities`.
- Add `doctor_ctf_harness`.
- Add JSONL event writer.

### Phase 2: Triage va workspace

- Add `ctf_create_workspace`.
- Add `ctf_import_challenge`.
- Add `ctf_triage`.
- Add fixtures cho file/binary/pcap/archive.

### Phase 3: Category env

- Add category profiles tu ctf-skills.
- Add verify/install dry-run.
- Add runner image status.
- Add docs command install tools.

### Phase 4: Execution wrappers

- Add `ctf_run_command`.
- Add `ctf_run_python`.
- Add `ctf_connect_tcp`.
- Add `ctf_http_request`.
- Normalize observation.

### Phase 5: Evidence/proof

- Add flag candidate recorder.
- Add primitive recorder.
- Add proof bundle.
- Add replay script generator.

### Phase 6: Docker runner

- Add category images.
- Add read-only input mount.
- Add writable work/artifact mount.
- Add resource/time limits.

## 15. Definition of done

Harnes CTF coi la dung khi:

- ChatGPT web co the tao workspace, import challenge, triage, chay recon, chay solver, luu flag candidate, build proof bundle bang tool calls.
- MCP khong can nho context dai.
- Moi run co transcript va artifact path.
- Loi policy noi ro rule nao bi block.
- Co replay script de chung minh ket qua.
- Default van la host-first; Docker/VPS chi bat qua profile/config.

