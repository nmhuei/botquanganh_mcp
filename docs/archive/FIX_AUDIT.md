# Fix Audit — v0.3.0

This audit records the fixes applied after review.

## Fixed

1. **Workspace path mismatch**
   - `config.py` default workspace changed from `artifacts` to `workspaces`.
   - `ctf.example.yaml`, `ctfh init`, and `scripts/new-challenge.sh` now agree on `workspaces/<challenge>`.

2. **Unsafe remote auto-verification**
   - `flag.py` no longer upgrades remote `candidate` to `verified` automatically.
   - `verified` now requires `proof.command` to exit 0.

3. **Flag regex drift**
   - Added `ctfharness/constants.py` as the single source of truth.
   - CLI and templates import/use `FLAG_REGEX_DEFAULT`.

4. **Solver path robustness**
   - `ctfh init` and `new-challenge.sh` write solver paths relative to harness root.
   - `ctfh workspace` added to print the active workspace.

5. **PWN template blocking risk**
   - PWN template now uses bounded `recvrepeat(timeout)` and saves transcript.

6. **Duplicate orchestrator skill**
   - Removed duplicate `skills/ctf-orchestrator`; kept canonical `skills/solve-challenge/SKILL.md`.

7. **CI coverage**
   - CI now compiles sources/templates, runs `ctfh check`, `ctfh local --solve`, `ctfh verify --mode local`, `ctfh report`, `ctfh pack`, and confirms remote candidates are not auto-verified.

8. **Forensics/OSINT templates**
   - Forensics template has file/strings/exiftool/zip/pcap-oriented triage.
   - OSINT template has domain/file metadata scanning and a manual recon guide.

9. **Examples**
   - Added `examples/mock-web` end-to-end smoke example.

10. **Verifier stub**
   - `submit_or_check_flag.py` now exits 2 by default, so it cannot accidentally mark arbitrary candidates as verified.

## Still not fully automated

- Real CTFd submit/verify is intentionally not enabled because it requires platform URL, challenge ID, and API token.
- Advanced category tools such as SageMath, Ghidra, Volatility, Burp, and cloud CLIs are documented but not installed by default.
- Remote verification remains `candidate` until you configure `proof.command`.

---

## v0.3.1

11. **Thread-safety bug in resolve_approval**
    - `fut.set_result()` được gọi từ sync thread pool (agent_approve) trên Future thuộc event loop khác.
    - Fix: dùng `fut.get_loop().call_soon_threadsafe(fut.set_result, approved)`.

12. **Approval flow phụ thuộc SSE subscriber**
    - agent_approve không hoạt động khi không có SSE client connect.
    - Fix: bỏ điều kiện `has_subscribers`, luôn register Future và await.

13. **logs/ vẫn bị track trong git**
    - `git rm -r --cached logs/` để untrack artifacts và log files.
