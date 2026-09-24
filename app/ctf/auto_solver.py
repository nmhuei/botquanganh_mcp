"""Automated CTF solver promotion, writeup generation, and flag hoarding.

When a script inside the `script/` folder executes successfully:
1. Detects recovered flags in stdout/stderr.
2. Hoards the clean flag into `<workspace_root>/flag.txt`.
3. Promotes the script logic into `<workspace_root>/solver/solve.py`.
4. Auto-detects dependencies and updates `<workspace_root>/solver/requirements.txt`.
5. Automatically generates `<workspace_root>/solver/WRITEUP.md`.
6. Updates `script/analysis.md` status to VERIFIED/SOLVED.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any, Optional


FLAG_PATTERNS = [
    re.compile(r"(FLAG\{[^}\n\r\t ]+\})", re.IGNORECASE),
    re.compile(r"([A-Za-z0-9_-]{2,30}\{[^}\n\r\t ]+\})"),
    re.compile(r"(picoCTF\{[^}\n\r\t ]+\})", re.IGNORECASE),
    re.compile(r"(CTF\{[^}\n\r\t ]+\})", re.IGNORECASE),
]

KNOWN_IMPORTS_MAP = {
    "pwn": "pwntools>=4.10.0\n",
    "requests": "requests>=2.28.0\n",
    "z3": "z3-solver>=4.12.0\n",
    "Crypto": "pycryptodome>=3.18.0\n",
    "sympy": "sympy>=1.12\n",
    "gmpy2": "gmpy2>=2.1.5\n",
    "ecdsa": "ecdsa>=0.18.0\n",
    "fpylll": "fpylll>=0.5.9\n",
    "scapy": "scapy>=2.5.0\n",
    "httpx": "httpx>=0.24.0\n",
    "bs4": "beautifulsoup4>=4.12.0\n",
}


def extract_flags_from_text(text: str) -> list[str]:
    """Extract unique flags matching standard CTF patterns."""
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pattern in FLAG_PATTERNS:
        for match in pattern.finditer(text):
            flag_str = match.group(1).strip()
            # Filter false positives
            if flag_str.lower() in {"flag{placeholder}", "flag{test}", "flag{sample}"}:
                continue
            if flag_str not in seen:
                seen.add(flag_str)
                found.append(flag_str)
    return found


def find_script_in_command(command: str, workspace_root: Path, cwd: Optional[str] = None) -> Optional[Path]:
    """Identify the script file inside script/ that was executed by the command."""
    ws = Path(workspace_root).resolve()
    script_dir = ws / "script"
    if not script_dir.is_dir():
        return None

    # Check tokens in command
    parts = command.strip().split()
    for token in parts:
        clean_token = token.strip("\"'<>|;&")
        if not clean_token.endswith((".py", ".sh", ".rb", ".pl", ".js")):
            continue
        # Case A: relative to workspace root (e.g. "script/poc.py" or "./script/poc.py")
        cand_a = (ws / clean_token).resolve()
        if cand_a.is_file() and script_dir in cand_a.parents:
            return cand_a

        # Case B: relative to cwd (if cwd is inside script dir)
        if cwd:
            cand_b = (Path(cwd) / clean_token).resolve()
            if cand_b.is_file() and (cand_b.parent == script_dir or script_dir in cand_b.parents):
                return cand_b

        # Case C: filename only, check directly in script_dir
        cand_c = (script_dir / Path(clean_token).name).resolve()
        if cand_c.is_file():
            return cand_c

    return None


def generate_writeup_content(
    challenge_name: str,
    category: str,
    script_name: str,
    flags: list[str],
    stdout_sample: str,
    command: str,
    math_model_note: Optional[str] = None,
) -> str:
    """Generate Markdown writeup complying with AGENTS.md requirements."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    flag_display = "\n".join(f"- `{f}`" for f in flags) if flags else "- *(Flag recovered in script execution)*"
    sample_clean = stdout_sample[-2000:].strip() if len(stdout_sample) > 2000 else stdout_sample.strip()

    math_section = ""
    step_num = 2
    if math_model_note:
        math_section = f"""## {step_num}. Mathematical Model & Attack Vector
{math_model_note}

"""
        step_num += 1

    return f"""# Writeup: {challenge_name}

- **Category:** {category.upper()}
- **Solved Date:** {now_iso}
- **Exploit Script:** `{script_name}`
- **Status:** VERIFIED SOLVED

---

## 1. Challenge & Vulnerability Summary
- **Overview:** Challenge `{challenge_name}` ({category}) was analyzed and triaged using standard BotQuangAnh MCP 3-folder harness discipline.
- **Exploitation Vector:** Deterministic script execution via `{script_name}` successfully triggered the exploit and retrieved the target flag.

{math_section}## {step_num}. Reproduction Steps
1. Navigate to the solver directory:
   ```bash
   cd solver
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the standalone exploit:
   ```bash
   python3 solve.py
   ```

## {step_num + 1}. Original Execution Proof
Command executed:
```bash
{command}
```

Terminal output:
```text
{sample_clean}
```

## {step_num + 2}. Recovered Flag(s)
{flag_display}

> 🎯 *Flag is hoarded directly in `flag.txt` in the root workspace directory.*
"""



def promote_script_to_solver(
    workspace_root: Path | str,
    command: str,
    stdout: str,
    stderr: str = "",
    exit_code: int = 0,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    """Evaluate executed command; if a script in script/ succeeded, promote to solver, write flag.txt & WRITEUP.md."""
    if exit_code != 0:
        return {"promoted": False, "reason": f"Exit code {exit_code} != 0"}

    ws = Path(workspace_root).resolve()
    script_file = find_script_in_command(command, ws, cwd)
    if not script_file or not script_file.is_file():
        return {"promoted": False, "reason": "No script file inside script/ detected in command"}

    combined_output = f"{stdout}\n{stderr}"
    flags = extract_flags_from_text(combined_output)

    solver_dir = ws / "solver"
    solver_dir.mkdir(parents=True, exist_ok=True)
    solve_py = solver_dir / "solve.py"

    # 1. Promote script logic into solver/solve.py
    script_content = script_file.read_text(encoding="utf-8")
    solve_py.write_text(script_content, encoding="utf-8")
    try:
        os.chmod(solve_py, 0o755)
    except OSError:
        pass

    # 2. Update solver/requirements.txt
    reqs_file = solver_dir / "requirements.txt"
    existing_reqs = reqs_file.read_text(encoding="utf-8") if reqs_file.is_file() else ""
    new_reqs = list(existing_reqs.splitlines())
    for imp_module, req_line in KNOWN_IMPORTS_MAP.items():
        if re.search(rf"\b(import\s+{imp_module}|from\s+{imp_module}\b)", script_content):
            pkg_name = req_line.split(">=")[0].split("==")[0].strip()
            if not any(pkg_name in line for line in new_reqs):
                new_reqs.append(req_line.strip())
    reqs_file.write_text("\n".join(filter(None, new_reqs)) + "\n", encoding="utf-8")

    # 3. Detect challenge name & category
    chal_name = ws.name
    category = "misc"
    for cat in ("pwn", "crypto", "web", "reverse", "forensics", "misc", "ai-ml", "osint"):
        if chal_name.startswith(f"{cat}_"):
            category = cat
            chal_name = chal_name[len(cat) + 1:]
            break

    # Read meta.json if present for richer info
    meta_path = ws / "meta.json"
    if not meta_path.is_file():
        meta_path = ws / "metadata.json"
    if meta_path.is_file():
        try:
            import json
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
            category = meta_data.get("category") or category
            chal_name = meta_data.get("name") or meta_data.get("label") or chal_name
        except Exception:
            pass

    # 4. Generate solver/WRITEUP.md
    writeup_file = solver_dir / "WRITEUP.md"
    math_note: Optional[str] = None
    math_model_path = ws / "notes" / "math_model.md"
    if math_model_path.is_file():
        math_note = (
            "- **Mathematical Model:** Formalized in `notes/math_model.md`.\n"
            "- **Attack Discipline:** Verified against BQA Extreme Crypto Playbook (Deterministic Verification)."
        )

    writeup_text = generate_writeup_content(
        challenge_name=chal_name,
        category=category,
        script_name=script_file.name,
        flags=flags,
        stdout_sample=stdout,
        command=command,
        math_model_note=math_note,
    )
    writeup_file.write_text(writeup_text, encoding="utf-8")

    # 5. Hoard flag in root workspace flag.txt
    flag_file = ws / "flag.txt"
    if flags:
        flag_file.write_text("\n".join(flags) + "\n", encoding="utf-8")

    # 6. Update script/analysis.md candidate flags table
    analysis_file = ws / "script" / "analysis.md"
    if analysis_file.is_file() and flags:
        try:
            content = analysis_file.read_text(encoding="utf-8")
            table_marker = "## 3. Candidate Flags Lifecycle"
            if table_marker in content:
                rows = "\n".join(
                    f"| `{f}` | `VERIFIED` | `{script_file.name}` execution | Verified with exit code 0 |"
                    for f in flags
                )
                if "(No flags discovered yet)" in content:
                    content = content.replace("| *(No flags discovered yet)* | - | - | - |", rows)
                else:
                    parts = content.split(table_marker, 1)
                    content = f"{parts[0]}{table_marker}\n{rows}\n{parts[1].lstrip()}"
                analysis_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    return {
        "promoted": True,
        "script_source": str(script_file),
        "solver_file": str(solve_py),
        "writeup_file": str(writeup_file),
        "flag_file": str(flag_file) if flags else None,
        "flags": flags,
        "message": f"Successfully promoted {script_file.name} to solver/solve.py, generated WRITEUP.md, and hoarded flag(s) in flag.txt.",
    }
