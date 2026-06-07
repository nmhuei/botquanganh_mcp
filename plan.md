# Ke hoach cai tien botquanganh_mcp

Tham chieu chinh: `openclaw/openclaw.git` tai `https://github.com/openclaw/openclaw.git`.

Muc tieu cua plan nay la bien repo MCP hien tai thanh mot tool executor muot hon cho ChatGPT web: mac dinh host-first, co che do VPS/Docker ro rang, it false positive hon, log/bang chung tot hon, va tra observation gon, ro, de ChatGPT web lam nao dieu phoi.

## 1. Bai hoc nen muon tu OpenClaw

OpenClaw lon hon repo nay rat nhieu, nhung co may pattern dang ap dung:

- `Gateway la control plane`: OpenClaw xem gateway la lop dieu phoi tools, logs, nodes va events. Repo MCP nay nen coi FastMCP server la execution gateway cho runner, host ops, workspace va proof logs; ChatGPT web giu phan suy luan/context.
- `Host-first, sandbox khi can`: OpenClaw security model mac dinh la host cho trusted operator, sandbox cho non-main/untrusted sessions. Repo nay nen giu mac dinh host mode, chi bat workspace/Docker khi cau hinh VPS.
- `Doctor/onboard`: OpenClaw co onboarding va `doctor` de kiem tra config, service, auth, logs. Repo nay nen co `doctor_mcp` va script setup tuong tu de giam loi cau hinh.
- `Tool chuyen dung thay vi shell generic`: OpenClaw co tool/capability rieng theo nhom. Repo nay nen tiep tuc tach GitHub, SSL, file ops, workspace import, proof bundle ra tool rieng.
- `Logs co cau truc`: OpenClaw dung JSONL, rotation, redaction, CLI tail. Repo nay dang co audit log, nen nang thanh JSONL co trace id, rotation va tool tail tot hon.
- `Workflow test theo vung thay doi`: OpenClaw co docs chi ro check/test/build gate theo module. Repo nay nen co matrix test nho: basic, advanced, Docker, tunnel, policy, live network.
- `Security model viet ro`: OpenClaw noi thang ve trusted-operator model va false-positive pattern. Repo nay can document ro: day la MCP trusted local operator, khong phai multi-tenant sandbox.

## 1.1 Nguyen tac thiet ke: ChatGPT web la nao

Repo nay khong can tro thanh agent runtime doc lap. Context, ke hoach, reasoning va quyet dinh buoc tiep theo se nam trong ChatGPT web.

MCP chi nen lam cac viec sau:

- expose tool chuyen dung, de ChatGPT web goi dung viec;
- thuc thi command/file/network/GitHub/runner mot cach on dinh;
- kiem tra policy truoc khi lam viec nhay cam;
- ghi log, hashes, transcript, proof;
- tra ve observation ngan gon, co cau truc, de ChatGPT web doc tiep;
- khong luu memory dai han, khong tu lap plan, khong tu chay loop agent.

Non-goal ro rang:

- Khong them `agent_run_task`, `agent_step`, planner loop, memory store, hay autonomous executor.
- Neu can state, chi giu state ky thuat toi thieu nhu `run_id`, `workspace_id`, `trace_id`, `artifact_id`.

## 2. Trang thai hien tai cua repo

Nhung diem da tot:

- Co 2 lop tool: core/basic va advanced.
- Co `run_basic_python_solver`, `run_solver_fallback`, runner Docker, workspace, logs, transcript, SHA256.
- Co `agent_*` host tools va dang tien toi host-first mode.
- Da co policy allowlist target, private IP block, egress firewall tuy chon.
- Da co proof primitives: run id, stdout/stderr/transcript hash.

Nhung diem can lam muot:

- Tool registry va docs chua dong bo voi code moi.
- Chua co `doctor` de noi config nao dang sai.
- Logs con la string audit event trong file log, chua phai JSONL sach de tail/filter.
- `run_command`, workspace, agent, fallback va GitHub tools con nam rai rac, chua co layer policy chung.
- Workspace/Docker mode can ro rang hon: mac dinh host, Docker chi khi `ENABLE_WORKSPACE_TOOLS=true` hoac VPS profile.
- Chua co setup/onboarding script hoi nguoi dung chon profile: local, CTF host, VPS runner.
- Chua co regression test cho tunnel/public connector.

## 3. Kien truc muc tieu

### 3.1 Execution gateway

Tao mot lop `app/executor_core/` hoac `app/core/` gom:

- `capabilities.py`: mo ta toan bo tool surface theo config.
- `policy.py`: policy decision chung cho command, path, network, workspace.
- `diagnostics.py`: doctor checks va health snapshots.
- `events.py`: structured events/log schema.
- `profiles.py`: local/ctf/vps profile resolver.
- `observations.py`: format ket qua tool ngan gon, co `ok`, `summary`, `details`, `artifacts`.

Tieu chi xong:

- `health_check` va `get_capabilities` lay du lieu tu mot source of truth.
- Them tool moi khong can sua nhieu file roi de docs/capabilities bi lech.
- Tool tra ve ket qua vua du cho ChatGPT web tiep tuc, khong phai doc log dai moi hieu.

### 3.2 Tool surface theo profile

Profile de xuat:

- `local`: mac dinh, host-first, agent tools bat, workspace Docker tat.
- `ctf`: host-first, network allowlist linh hoat, basic solver bat, proof bundle bat.
- `vps`: workspace Docker bat, runner images bat, egress firewall co the bat.
- `locked`: chi health/capabilities/smoke/probe, dung de test connector.

Bien moi de xet:

```env
MCP_PROFILE=local
ENABLE_ADVANCED_TOOLS=true
ENABLE_AGENT_TOOLS=true
ENABLE_WORKSPACE_TOOLS=false
```

Tieu chi xong:

- `MCP_PROFILE=local` khong expose workspace Docker tools.
- `MCP_PROFILE=vps` expose workspace tools va doctor canh bao neu Docker image thieu.

## 4. Roadmap uu tien

### Phase 1: Doctor va onboarding

Them:

- `doctor_mcp()`: tool tra ve config health, missing deps, port, tunnel, Docker, gh auth, cloudflared, writable dirs.
- `scripts/doctor.sh`: chay local khong can MCP client.
- `scripts/onboard.sh`: hoi profile local/ctf/vps, tao `.env`, chay install tuong ung.

Doctor checks:

- Python/venv/fastmcp import duoc.
- `.env` parse duoc va path resolve dung.
- `AGENT_WORKSPACE_DIR` ton tai, writable.
- `RUNS_DIR`, `ARTIFACTS_DIR`, `WORKSPACES_DIR`, `LOG_FILE` writable.
- `cloudflared` co trong PATH neu dung tunnel.
- `gh auth status` neu GitHub tools bat.
- Docker daemon va runner images neu `ENABLE_WORKSPACE_TOOLS=true`.
- `ALLOWED_TCP_TARGETS=*` canh bao ro.
- `BLOCK_PRIVATE_IPS=false` canh bao ro.

Test:

```bash
./.venv/bin/python -m pytest tests/test_doctor.py -q
./scripts/doctor.sh
```

### Phase 2: Structured logging va trace

Nang logging theo huong OpenClaw:

- Chuyen audit event sang JSONL thuan, mot event moi dong.
- Them `trace_id`, `tool_name`, `run_id`, `workspace_id`, `request_id` neu co.
- Them rotation theo size/ngay.
- Redact theo key pattern hien co, nhung test ky hon.
- Them tools:
  - `tail_gateway_log(lines=100, follow_hint=false)`
  - `search_gateway_log(query, event_type="", limit=100)`
  - `get_trace(trace_id)`

Tieu chi xong:

- Moi tool quan trong log start/end/fail.
- Loi `POLICY_BLOCKED` co `blocked_reason`, `matched_fragment`, `suggested_tool`.
- Co the debug 502 bang log gan nhat theo trace/request.

### Phase 3: Policy engine giam false positive

Tao mot policy decision object chung:

```json
{
  "allowed": true,
  "risk": "low|medium|high",
  "rule": "string",
  "matched_fragment": "string",
  "suggested_tool": "string",
  "scope": {
    "cwd": "...",
    "target": "...",
    "repo": "..."
  }
}
```

Them:

- `policy_check_tool_call(tool, args)`
- `policy_check_command(command, cwd)`
- `policy_explain_last_block()`

Rules nen co:

- Path rule: workspace/home/root profile.
- Network rule: allowlist target, private IP, github/api.github.com, CTF host.
- Shell rule: chi chan destructive primitives that su nguy hiem.
- Tool alternative hints: `gh pr list` -> `github_list_prs`, `ncat --ssl` -> `tcp_connect_ssl`.

Tieu chi xong:

- Shell hop le nhu `gh pr list`, `gh api`, `ncat --ssl` khong bi chan vi heuristic mo ho, hoac duoc route sang tool chuyen dung.
- Moi block tra ve rule name va cach retry.

### Phase 4: File API va patch API chuan

Chuan hoa file tools:

- `read_file(path, start_line=None, end_line=None)`
- `write_file(path, content, create=true)`
- `replace_in_file(path, old, new, expected_count=1)`
- `apply_unified_diff(path_or_root, diff, dry_run=false)`
- `append_file(path, content)`
- `mkdir_p(path)`
- `delete_path(path, recursive=false)`
- `move_path(src, dst)`
- `copy_path(src, dst)`

Guardrail:

- Mac dinh chi trong `AGENT_WORKSPACE_DIR`.
- Profile `local` co the doc/ghi trong `~/Workspace`.
- Profile `vps` uu tien workspace managed.
- Log diff summary: file, line count, bytes before/after, sha256 before/after.

Tieu chi xong:

- Khong can nhung noi dung source code dai vao shell.
- `agent_edit_file` co the giu lai de tuong thich, nhung docs huong sang `replace_in_file`/`apply_unified_diff`.

### Phase 5: GitHub va network tools chuyen dung

GitHub tools:

- `github_clone_or_sync(repo, branch, dst_in_workspace)`
- `github_create_branch(repo, from_ref, new_branch)`
- `github_commit_files(repo, branch, files, message)`
- `github_open_pr(repo, head, base, title, body)`
- `github_list_prs(repo, state, limit)`
- `github_get_run_logs(repo, run_id)`
- `github_api_request(method, path, body=None)` co allowlist repo/path.

Network tools:

- `tcp_connect(host, port, send_lines=[], recv_bytes=4096)`
- `tcp_connect_ssl(host, port, send_lines=[], server_name=None)`
- `http_request(method, url, headers={}, body="")` voi allowlist.
- `probe_ssl_banner(host, port)`.

Tieu chi xong:

- Workflow GitHub PR khong can `gh ...` shell generic.
- CTF TLS service khong can viet socket boilerplate moi lan.
- Network policy van gate theo host/port/url.

### Phase 6: Workspace import va scoped allowlist theo request

Them:

- `import_path_to_workspace(src, dst)`
- `sync_git_repo_to_workspace(repo_url_or_local_path, dst, branch="")`
- `policy_check_scope(paths=[], repos=[], hosts=[])`
- `with_scope(tool_name, args, paths=[], repos=[], hosts=[])`

Y tuong:

- ChatGPT web truyen scope truc tiep trong tool call khi can.
- MCP khong can nho task context; no chi kiem tra scope cua request hien tai.
- Neu sau nay can cache scope ngan han, chi nen dung TTL rat ngan va tra ve `scope_id`, khong bien no thanh memory.

Tieu chi xong:

- Repo nam o `~/GitHub/...` co duong import chinh thuc vao `~/Workspace/...`.
- Mot request CTF/GitHub co the allow host + repo/path cu the ma khong mo het may.

### Phase 7: Proof bundle va writeup artifacts

Mo rong `build_ctf_proof_bundle`:

- solver file SHA256.
- stdout/stderr/transcript SHA256.
- target host/port.
- flag regex match.
- raw proof excerpt co cap length.
- environment summary.
- command transcript.
- timestamps.
- local validation evidence.

Them:

- `export_run_artifacts(run_id, dst_dir)`
- `generate_writeup_skeleton(run_id, language="vi")`

Tieu chi xong:

- Sau mot run thanh cong, co the tao `proof.json`, `proof.txt`, `solve.py`, `commands.log`, `writeup.md`.
- Dung tot cho CTF workflow local-before-remote.
- ChatGPT web la noi viet narrative/writeup; MCP chi xuat artifact va proof co cau truc.

### Phase 8: Interactive/pseudo-TTY runner

Them runner stateful:

- `start_interactive_run(language, files, entrypoint, target=None)`
- `send_stdin(session_id, data)`
- `recv_until(session_id, pattern="", timeout_seconds=5)`
- `close_interactive_run(session_id)`

Backend:

- Ban dau dung local subprocess + pipes.
- Sau do Docker exec voi `pty` neu can.

Tieu chi xong:

- Pwn/ncat/debug flow khong phai viet script hoan chinh moi lan.
- Log van duoc ghi vao run folder.
- ChatGPT web doc observation tu `recv_until` va quyet dinh input tiep theo.

### Phase 9: Test gate va CI

Hoc tu OpenClaw: co check scripts theo module.

Them scripts:

- `scripts/check_basic.sh`
- `scripts/check_policy.sh`
- `scripts/check_advanced.sh`
- `scripts/check_docker_images.sh`
- `scripts/check_tunnel.sh`
- `scripts/check_all.sh`

Test matrix:

- Unit: schemas, security, file package, agent tools.
- Integration local: basic solver, run logs, proof bundle.
- Integration workspace: workspace lifecycle, Docker command, import path.
- Live optional: tunnel, GitHub auth, allowlisted target probe.

Tieu chi xong:

```bash
./scripts/check_basic.sh
./scripts/check_policy.sh
./.venv/bin/python -m pytest -q
```

### Phase 10: Docs va operator UX

Docs can co:

- `docs/security-model.md`: trusted operator, host-first, VPS/workspace mode, scope allowlist.
- `docs/profiles.md`: local/ctf/vps/locked.
- `docs/doctor.md`: cach doc output doctor.
- `docs/tools.md`: tool nao dung thay shell.
- `docs/ctf-workflow.md`: local-before-remote + proof bundle.
- `docs/github-workflow.md`: clone/branch/commit/PR/log.
- `docs/troubleshooting.md`: 502, policy block, tunnel, Docker, gh auth.

README nen rut gon:

- Quick start local.
- Quick start VPS.
- Connector setup.
- Safety defaults.
- Link docs chi tiet.

## 5. Thu tu lam ngay

Nen lam theo thu tu nay de co loi ich nhanh:

1. `doctor_mcp` + `scripts/doctor.sh`.
2. JSONL audit log + tail/search log tools.
3. Policy decision object + `policy_check_tool_call`.
4. File API day du + `apply_unified_diff`.
5. GitHub tools day du + SSL helper.
6. Workspace import/sync + scoped allowlist theo request.
7. Proof bundle/export writeup.
8. Interactive runner.
9. Check scripts + docs.

## 6. Non-goals

- Khong bien MCP nay thanh multi-tenant security boundary.
- Khong bien MCP nay thanh agent runtime tu dong; ChatGPT web la nao.
- Khong luu context/memory dai han trong MCP.
- Khong mo shell unrestricted theo mac dinh.
- Khong bat Docker/workspace mode tren laptop neu chua can.
- Khong thay FastMCP neu chua co ly do ro.
- Khong copy OpenClaw architecture nguyen khoi; chi muon pattern phu hop voi repo nho nay.

## 7. Definition of done cho ban "muot"

Repo duoc coi la muot hon khi:

- Cai dat moi co `onboard` hoac `doctor` noi ro can sua gi.
- ChatGPT connector co `run_safe_smoke_test` pass bang mot call.
- Loi policy block noi ro rule va tool thay the.
- GitHub/SSL/file patch workflow khong can shell generic.
- Host mode la mac dinh; workspace/Docker mode la profile rieng.
- Moi run co logs, hashes, transcript va proof bundle.
- Moi tool result co summary/observation ngan gon de ChatGPT web tiep tuc xu ly.
- Co check script nho de test nhanh truoc khi restart/push.
