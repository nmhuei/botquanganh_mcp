from __future__ import annotations

import argparse
import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from .config import challenge_dir, load_config, safe_name
from .constants import FLAG_REGEX_DEFAULT, SUPPORTED_CATEGORIES, WORKSPACE_ROOT
from .flag import detect_flags, write_evidence
from .logging_utils import append_jsonl, run_command, utc_now
from .scope import remote_target_allowed

ROOT = Path.cwd()
LAST_RUN = Path(".ctfh-last-run.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctfh", description="Local-first CTF harness")
    parser.add_argument("--config", default="ctf.yaml", help="Path to config YAML")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create ctf.yaml and starter solve.py")
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--category", default="misc", choices=SUPPORTED_CATEGORIES)
    p_init.add_argument("--host", default="", help="Remote host (optional)")
    p_init.add_argument("--port", default="", help="Remote port (optional)")
    p_init.add_argument("--force", action="store_true")

    sub.add_parser("check", help="Validate config and create workspace folders")

    p_local = sub.add_parser("local", help="Run local build/start/smoke; optionally solver")
    p_local.add_argument("--solve", action="store_true")
    p_local.add_argument("--keep-local", action="store_true", help="Do not run local.stop")
    p_local.add_argument("--timeout", type=int, default=None)

    p_solve = sub.add_parser("solve", help="Run solver only")
    p_solve.add_argument("--mode", choices=["local", "remote"], required=True)
    p_solve.add_argument("--timeout", type=int, default=None)
    p_solve.add_argument("--force-remote", action="store_true")

    p_remote = sub.add_parser("remote", help="Run remote solver after local evidence gate")
    p_remote.add_argument("--timeout", type=int, default=None)
    p_remote.add_argument("--force-remote", action="store_true")

    p_verify = sub.add_parser("verify", help="Parse artifacts/logs for flags and write evidence JSON")
    p_verify.add_argument("--mode", choices=["local", "remote"], required=True)

    sub.add_parser("workspace", help="Print workspace path")
    sub.add_parser("report", help="Generate Markdown report from logs and proofs")
    sub.add_parser("pack", help="Zip challenge artifacts")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)

    cfg = load_config(args.config)
    prepare_workspace(cfg)

    if args.cmd == "check":
        return cmd_check(cfg)
    if args.cmd == "local":
        return cmd_local(cfg, solve=args.solve, keep=args.keep_local, timeout=args.timeout)
    if args.cmd == "solve":
        return cmd_solve(cfg, args.mode, timeout=args.timeout, force_remote=args.force_remote)
    if args.cmd == "remote":
        return cmd_solve(cfg, "remote", timeout=args.timeout, force_remote=args.force_remote)
    if args.cmd == "verify":
        return cmd_verify(cfg, args.mode)
    if args.cmd == "workspace":
        print(challenge_dir(cfg).resolve())
        return 0
    if args.cmd == "report":
        return cmd_report(cfg)
    if args.cmd == "pack":
        return cmd_pack(cfg)
    return 2


def prepare_workspace(cfg: dict[str, Any]) -> None:
    base = challenge_dir(cfg)
    for subdir in [
        "logs", "proofs", "reports", "payloads", "transcripts", "tmp", "evidence",
        "artifacts", "exploit/attempts", "recon", "notes",
    ]:
        (base / subdir).mkdir(parents=True, exist_ok=True)


def event(cfg: dict[str, Any], kind: str, data: dict[str, Any]) -> None:
    append_jsonl(challenge_dir(cfg) / "timeline.jsonl", {"ts": utc_now(), "kind": kind, **data})


def cmd_init(args: argparse.Namespace) -> int:
    cfg_path = Path("ctf.yaml")
    if cfg_path.exists() and not args.force:
        print("[-] ctf.yaml already exists. Use --force to overwrite.")
        return 1

    name = args.name
    category = args.category
    template_category = {"rev": "reverse"}.get(category, category)
    host = args.host or ""
    port = args.port or ""
    ws_rel = f"{WORKSPACE_ROOT}/{safe_name(name)}"

    allowed_lines = ["    - localhost", "    - 127.0.0.1"]
    if host:
        allowed_lines.append(f"    - {host}")
    allowed_yaml = "\n".join(allowed_lines)
    remote_target = f"{host}:{port}" if host else "https://target.ctf.example"
    remote_url = f"http://{host}:{port}" if host and port else "https://target.ctf.example"
    extra_env = ""
    if host:
        extra_env += f"    HOST: '{host}'\n"
    if port:
        extra_env += f"    PORT: '{port}'\n"

    config_text = (
        f"challenge:\n"
        f"  name: {name}\n"
        f"  category: {category}\n"
        f"  workspace: {WORKSPACE_ROOT}\n"
        f"  flag_regex: '{FLAG_REGEX_DEFAULT}'\n\n"
        f"policy:\n"
        f"  local_first: true\n"
        f"  require_remote_evidence: true\n"
        f"  reject_decoy_words: [fake, dummy, test, local, example, placeholder]\n"
        f"  authorized_remote_domains:\n{allowed_yaml}\n\n"
        f"local:\n"
        f"  build: []\n"
        f"  start: []\n"
        f"  smoke: []\n"
        f"  stop: []\n\n"
        f"solver:\n"
        f"  local: 'python3 {ws_rel}/exploit/solve.py'\n"
        f"  remote: 'REMOTE_URL=\"$REMOTE_URL\" HOST=\"$HOST\" PORT=\"$PORT\" python3 {ws_rel}/exploit/solve.py REMOTE'\n\n"
        f"remote:\n"
        f"  target: '{remote_target}'\n"
        f"  env:\n"
        f"    REMOTE_URL: '{remote_url}'\n{extra_env}"
        f"\nproof:\n"
        f"  # Replace with real checker/CTFd submitter to upgrade candidate -> verified.\n"
        f"  command: ''\n"
    )
    cfg_path.write_text(config_text, encoding="utf-8")

    ws_path = Path(ws_rel)
    for subdir in ["artifacts", "exploit/attempts", "recon", "notes", "evidence", "payloads", "transcripts", "tmp", "logs", "proofs", "reports"]:
        (ws_path / subdir).mkdir(parents=True, exist_ok=True)

    template_dir = Path(__file__).resolve().parents[1] / "templates" / template_category
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[1] / "templates" / "misc"
    dst = ws_path / "exploit" / "solve.py"
    if not dst.exists() or args.force:
        src_text = (template_dir / "solve.py").read_text(encoding="utf-8")
        src_text = src_text.replace("__CHALLENGE__", name)
        src_text = src_text.replace("__HOST__", host or "TARGET_HOST")
        src_text = src_text.replace("__PORT__", port or "TARGET_PORT")
        dst.write_text(src_text, encoding="utf-8")
        dst.chmod(0o755)

    notes = ws_path / "notes" / "NOTES.md"
    if not notes.exists() or args.force:
        notes.write_text(f"# {name} — {category}\n\n## Description\n\n## Recon\n\n## Hypotheses\n\n## Attempts\n\n## Solution\n\n## Flag\n\n", encoding="utf-8")

    state = ws_path / "state.json"
    if not state.exists() or args.force:
        state.write_text(json.dumps({
            "challenge": name,
            "category": category,
            "remote": {"host": host, "port": port},
            "phase": "triage",
            "hypotheses": [],
            "confirmed_primitives": [],
            "attempts": 0,
            "flag": None,
            "flag_verified": False,
            "created_at": utc_now(),
        }, indent=2), encoding="utf-8")

    link = Path("solve.py")
    if not link.exists() or args.force:
        try:
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(dst.resolve())
        except Exception:
            shutil.copy(dst, link)

    print(f"[+] initialized: {name} ({category})")
    print(f"[+] workspace:   {ws_path}/")
    print(f"[+] solve.py:    {dst}")
    print(f"[+] config:      ctf.yaml")
    print(f"[+] next:        copy challenge files to {ws_path}/artifacts/")
    return 0


def cmd_check(cfg: dict[str, Any]) -> int:
    base = challenge_dir(cfg)
    print(f"[+] challenge : {cfg['challenge']['name']} ({cfg['challenge']['category']})")
    print(f"[+] workspace : {base.resolve()}")
    print(f"[+] flag_regex: {cfg['challenge']['flag_regex'][:80]}...")
    target = cfg.get("remote", {}).get("target", "")
    allowed, reason = remote_target_allowed(target, cfg["policy"].get("authorized_remote_domains", []))
    print(f"[+] remote scope: {'OK' if allowed else 'WARN'} - {reason}")
    print(f"[+] solver.local : {cfg.get('solver', {}).get('local', '') or '(empty)'}")
    print(f"[+] solver.remote: {cfg.get('solver', {}).get('remote', '') or '(empty)'}")
    solve_py = base / "exploit" / "solve.py"
    if not solve_py.exists():
        print(f"[!] missing workspace solver: {solve_py}")
    event(cfg, "check", {"remote_scope": reason, "remote_scope_allowed": allowed})
    return 0


def run_steps(cfg: dict[str, Any], section: str, timeout: int | None = None) -> list[dict[str, Any]]:
    results = []
    log_dir = challenge_dir(cfg) / "logs"
    env = cfg.get("remote", {}).get("env", {}) or {}
    for idx, cmd in enumerate(cfg.get("local", {}).get(section, []) or [], 1):
        print(f"[+] {section}[{idx}]: {cmd}")
        res = run_command(cmd, log_dir, f"{section}-{idx}", env=env, cwd=ROOT, timeout=timeout, check=False)
        print(f"    exit={res.exit_code} log={res.combined_path} sha256={res.combined_sha256[:12]}...")
        event(cfg, "command", {"section": section, **res.__dict__})
        results.append(res.__dict__)
    return results


def cmd_local(cfg: dict[str, Any], solve: bool, keep: bool, timeout: int | None = None) -> int:
    rc = 0
    try:
        run_steps(cfg, "build", timeout=timeout)
        run_steps(cfg, "start", timeout=timeout)
        run_steps(cfg, "smoke", timeout=timeout)
        if solve:
            rc = cmd_solve(cfg, "local", timeout=timeout, force_remote=False)
    finally:
        if not keep:
            run_steps(cfg, "stop", timeout=timeout)
    return rc


def local_gate_has_evidence(cfg: dict[str, Any]) -> bool:
    proofs = challenge_dir(cfg) / "proofs"
    for p in sorted(proofs.glob("local-*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("findings"):
            return True
    marker = proofs / "local-primitive.txt"
    return marker.exists() and marker.stat().st_size > 0


def cmd_solve(cfg: dict[str, Any], mode: str, timeout: int | None = None, force_remote: bool = False) -> int:
    base = challenge_dir(cfg)
    if mode == "remote":
        target = cfg.get("remote", {}).get("target", "")
        allowed, reason = remote_target_allowed(target, cfg["policy"].get("authorized_remote_domains", []))
        if not allowed and not force_remote:
            print(f"[-] remote target blocked by scope policy: {reason}")
            print("    Add the domain to policy.authorized_remote_domains or rerun with --force-remote if authorized.")
            return 3
        if cfg["policy"].get("local_first", True) and not local_gate_has_evidence(cfg) and not force_remote:
            print("[-] local-first gate blocked remote solve: no local evidence found.")
            print(f"    Run: ctfh local --solve && ctfh verify --mode local")
            print(f"    Or create: {base}/proofs/local-primitive.txt")
            return 4

    cmd = cfg.get("solver", {}).get(mode, "")
    if not cmd:
        print(f"[-] solver.{mode} is empty in config")
        return 2
    log_dir = base / "logs"
    env = cfg.get("remote", {}).get("env", {}) or {}
    print(f"[+] solver[{mode}]: {cmd}")
    res = run_command(cmd, log_dir, f"solver-{mode}", env=env, cwd=ROOT, timeout=timeout, check=False)
    print(f"[+] exit={res.exit_code} log={res.combined_path}")
    print(f"[+] sha256={res.combined_sha256}")
    event(cfg, "solver", {"mode": mode, **res.__dict__})
    LAST_RUN.write_text(json.dumps({"mode": mode, "result": res.__dict__}, indent=2), encoding="utf-8")
    return res.exit_code


def verify_scan_root(cfg: dict[str, Any], mode: str) -> Path:
    base = challenge_dir(cfg)
    # Keep mode verification focused so remote verification does not re-read old local-only logs.
    if mode == "remote":
        return base / "logs"
    return base


def cmd_verify(cfg: dict[str, Any], mode: str) -> int:
    base = challenge_dir(cfg)
    root = verify_scan_root(cfg, mode)
    findings = detect_flags(
        root=root,
        flag_regex=cfg["challenge"]["flag_regex"],
        mode=mode,
        reject_words=cfg["policy"].get("reject_decoy_words", []),
    )
    if mode == "remote":
        findings = [f for f in findings if "solver-remote" in Path(f.source_file).name or "verify-remote" in Path(f.source_file).name]
    verifier_command = (cfg.get("proof", {}) or {}).get("command") or ""
    target = cfg.get("remote", {}).get("target", "") if mode == "remote" else "local"
    out_path = base / "proofs" / f"{mode}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    evidence = write_evidence(
        out_path,
        findings,
        mode=mode,
        target=target,
        verifier_command=verifier_command or None,
        log_dir=base / "logs",
    )
    print(f"[+] evidence: {out_path}")
    print(f"[+] status: {evidence['status']}")
    if evidence["findings"]:
        best = evidence["findings"][0]
        print(f"[+] flag: {best['flag']}")
        print(f"[+] source: {best['source_file']}")
        print(f"[+] reason: {best['reason']}")
        if evidence["status"] == "candidate":
            print("[!] candidate only; set proof.command to a real checker to mark verified")
    else:
        print("[-] no flag-like token found")
    event(cfg, "verify", {"mode": mode, "evidence": str(out_path), "status": evidence["status"]})
    return 0 if evidence["findings"] else 1


def latest_json(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def cmd_report(cfg: dict[str, Any]) -> int:
    base = challenge_dir(cfg)
    report_dir = base / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "report.md"
    local_ev = latest_json(base / "proofs", "local-*.json")
    remote_ev = latest_json(base / "proofs", "remote-*.json")
    timeline = base / "timeline.jsonl"

    lines: list[str] = []
    lines.append(f"# CTF Report: {cfg['challenge']['name']}\n")
    lines.append(f"- **Category**: `{cfg['challenge']['category']}`")
    lines.append(f"- **Generated**: `{utc_now()}`")
    lines.append(f"- **Remote target**: `{cfg.get('remote', {}).get('target', '')}`")
    lines.append(f"- **Workspace**: `{base.resolve()}`\n")

    for title, ev_path in [("Local evidence", local_ev), ("Remote evidence", remote_ev)]:
        lines.append(f"## {title}\n")
        if not ev_path:
            lines.append("_No evidence file found._\n")
            continue
        data = json.loads(ev_path.read_text(encoding="utf-8"))
        lines.append(f"- **Evidence file**: `{ev_path}`")
        lines.append(f"- **Status**: `{data.get('status', 'unknown')}`")
        if data.get("findings"):
            finding = data["findings"][0]
            lines.append(f"- **Flag/candidate**: `{finding.get('flag')}`")
            lines.append(f"- **Source**: `{finding.get('source_file')}`")
            lines.append(f"- **SHA256**: `{finding.get('source_sha256')}`")
            lines.append(f"- **Reason**: {finding.get('reason')}")
        lines.append("")

    lines.append("## Command timeline\n")
    if timeline.exists():
        for raw in timeline.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if obj.get("kind") in {"command", "solver"}:
                lines.append(f"- `{obj.get('ts')}` **{obj.get('kind')}** exit=`{obj.get('exit_code')}` — `{obj.get('command')}`")
                if obj.get("combined_path"):
                    lines.append(f"  - log: `{obj.get('combined_path')}`")
                    lines.append(f"  - sha256: `{obj.get('combined_sha256')}`")
            elif obj.get("kind") == "verify":
                lines.append(f"- `{obj.get('ts')}` verify `{obj.get('mode')}` → `{obj.get('status')}`")
    else:
        lines.append("_No timeline found._")

    lines.append("\n## Reproduction\n")
    lines.append("```bash")
    lines.append("ctfh local --solve")
    lines.append("ctfh verify --mode local")
    lines.append("ctfh remote")
    lines.append("ctfh verify --mode remote")
    lines.append("ctfh report")
    lines.append("```")

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] report: {report}")
    return 0


def cmd_pack(cfg: dict[str, Any]) -> int:
    base = challenge_dir(cfg)
    zip_path = Path(f"{safe_name(cfg['challenge']['name'])}-artifacts.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in base.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(base.parent))
    print(f"[+] packed: {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
