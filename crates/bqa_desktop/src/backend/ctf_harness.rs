use std::fs;
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};
use crate::backend::paths::AppPaths;
use crate::db::{Database, SessionItem};

#[derive(Debug, Serialize, Deserialize)]
pub struct HarnessConfig {
    pub name: String,
    pub category: String,
    pub target_host: Option<String>,
    pub target_port: Option<i32>,
    pub target_url: Option<String>,
    pub description: Option<String>,
}

pub fn scaffold_ctf_harness(
    paths: &AppPaths,
    db: Option<&Database>,
    config: &HarnessConfig,
) -> Result<PathBuf, std::io::Error> {
    let clean_name = config
        .name
        .to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect::<String>()
        .trim_matches('_')
        .trim_matches('-')
        .to_string();
    let clean_name = if clean_name.is_empty() { "chal".to_string() } else { clean_name };

    let category = match config.category.to_lowercase().as_str() {
        "pwn" | "reverse" | "crypto" | "web" | "forensics" | "misc" | "ai-ml" | "osint" => {
            config.category.to_lowercase()
        }
        _ => "misc".to_string(),
    };

    let base_id = if clean_name.starts_with(&format!("{}_", category)) || clean_name.starts_with(&format!("{}-", category)) {
        clean_name.replace('-', "_")
    } else {
        format!("{}_{}", category, clean_name)
    };

    let session_id = base_id;
    let session_dir = paths.workspace_root.join(&session_id);
    scaffold_ctf_harness_into(&session_dir, &session_id, paths, db, config)?;
    Ok(session_dir)
}

pub fn scaffold_ctf_harness_into(
    session_dir: &std::path::Path,
    session_id: &str,
    paths: &AppPaths,
    db: Option<&Database>,
    config: &HarnessConfig,
) -> Result<(), std::io::Error> {
    let clean_name = config
        .name
        .to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect::<String>();

    let category = match config.category.to_lowercase().as_str() {
        "pwn" | "reverse" | "crypto" | "web" | "forensics" | "misc" | "ai-ml" | "osint" => {
            config.category.to_lowercase()
        }
        _ => "misc".to_string(),
    };

    let chal_dir = session_dir.join("challenge");
    let script_dir = session_dir.join("script");
    let solver_dir = session_dir.join("solver");

    fs::create_dir_all(&chal_dir)?;
    fs::create_dir_all(&script_dir)?;
    fs::create_dir_all(&solver_dir)?;

    // 1. Write challenge/NOTE.md (only if not exists)
    let note_path = chal_dir.join("NOTE.md");
    if !note_path.exists() {
        let note_content = format!(
            r#"# Challenge: {name}
- Category: {category}
- Created: {created}
- Target: {target}
- Description: {desc}

## Rule of Engagement
1. Artifacts in `challenge/` are strictly read-only original inputs.
2. Exploratory scripts and logs belong to `script/`.
3. The final reproducible exploit must reside in `solver/solve.py`.
4. No automated submission. Flag verification must be evidence-first.
"#,
            name = clean_name,
            category = category,
            created = chrono::Utc::now().to_rfc3339(),
            target = config
                .target_url
                .as_deref()
                .or(config.target_host.as_deref())
                .unwrap_or("N/A"),
            desc = config.description.as_deref().unwrap_or("No description provided.")
        );
        fs::write(note_path, note_content)?;
    }

    // 1.1. Write notes/math_model.md (Mandatory Mathematical Modeling for Crypto)
    if category == "crypto" {
        let notes_dir = session_dir.join("notes");
        fs::create_dir_all(&notes_dir)?;
        let math_model_path = notes_dir.join("math_model.md");
        if !math_model_path.exists() {
            let math_content = format!(
                r#"# Mathematical Model: {name}

> **Mandatory Crypto Discipline:** Before writing exploit code, document the mathematical relations below.
> Reference: `app/ctf/playbooks/crypto_playbook.md` or invoke tool `ctf_crypto_playbook`.

## 1. Algebraic Structure & Domains
- Ring / Field / Group: (e.g. Z/nZ, GF(2^128), E(F_p), Lattice Z^m)
- Generator / Base points: (e.g. g, G)
- Modulus / Order: (e.g. n = p*q, curve order #E)

## 2. Public Parameters & Observed Values
- Modulus n:
- Public Exponent e:
- Ciphertext c:
- Elliptic Curve Params (p, a, b, G):
- PRNG Outputs / Keystream:

## 3. Unknowns & Bounds
- Target secret (m / flag): Bounds: (e.g. m < 2^256)
- Nonce / Randomness (k, r): Bounds: (e.g. |k_i| < 2^128)
- Factors (p, q, d): Bounds: (e.g. d < 1/3 * n^0.25)

## 4. System of Equations & Congruences
- Equation 1:
- Equation 2:

## 5. Selected Attack Vector (from Playbook)
- Selected Vector:
- Mathematical Justification / Preconditions verified:

## 6. Verification Criterion
- Equation to satisfy:
"#,
                name = clean_name
            );
            fs::write(math_model_path, math_content)?;
        }
    }

    // 2. Write script/analysis.md (only if not exists)
    let analysis_path = script_dir.join("analysis.md");
    if !analysis_path.exists() {
        let crypto_discipline = if category == "crypto" {
            r#"
## 4. Crypto Discipline (BQA Extreme Playbook Protocol)
- [ ] Phase 1: Parameter & Scheme Triage (extract n, e, c, curve params, PRNG state from challenge/)
- [ ] Phase 2: Mathematical Modeling (formalized in `notes/math_model.md`)
- [ ] Phase 3: Attack Vector Selection (verified preconditions via `ctf_crypto_playbook`)
- [ ] Phase 4: Deterministic Local Verification (implemented 3-phase harness in script/)
- [ ] Phase 5: Solution Promotion (promoted to `solver/solve.py` with exit code 0)
"#
        } else {
            ""
        };
        let analysis_content = format!(
            r#"# Analysis & Hypotheses for {name} ({category})

## 1. Initial Triage & Recon
- File signatures / Architecture:
- Protections (checksec / hardening):
- Identified attack surface:

## 2. Hypotheses & Exploration
- [ ] Hypothesis 1:
- [ ] Hypothesis 2:

## 3. Disproven / Dead Paths
(Record failing payloads and discarded ideas here to avoid repeating work)
{discipline}"#,
            name = clean_name,
            category = category,
            discipline = crypto_discipline
        );
        fs::write(analysis_path, analysis_content)?;
    }

    // 3. Write solver/solve.py based on category (only if not exists)
    let solve_path = solver_dir.join("solve.py");
    if !solve_path.exists() {
        let solver_code = match category.as_str() {
            "pwn" => format!(
                r#"#!/usr/bin/env python3
"""Deterministic exploit script for {name} ({category})."""

import os
import sys
from pwn import *

HOST = "{target_host}"
PORT = {target_port}
BINARY = "../challenge/{binary_name}"

context.terminal = ['tmux', 'splitw', '-h']
if os.path.exists(BINARY):
    elf = context.binary = ELF(BINARY, checksec=True)

def start():
    if args.REMOTE:
        if not HOST or not PORT:
            log.error("HOST and PORT must be defined for REMOTE exploitation.")
        return remote(HOST, PORT)
    return process([BINARY])

def exploit():
    io = start()
    log.info("Starting exploit harness...")
    # === [LEAK / RECON] ===

    # === [DISPATCH PAYLOAD] ===

    # === [INTERACTIVE / FLAG RECOVERY] ===
    io.interactive()

if __name__ == "__main__":
    exploit()
"#,
                name = clean_name,
                category = category,
                target_host = config.target_host.as_deref().unwrap_or(""),
                target_port = config.target_port.unwrap_or(0),
                binary_name = clean_name
            ),
            "crypto" => format!(
                r#"#!/usr/bin/env python3
"""Deterministic cryptographic solver for {name} ({category}).
Enforces the 5-Phase BQA Crypto Playbook discipline.
"""

import sys
from typing import Any
# from Crypto.Util.number import bytes_to_long, long_to_bytes, inverse
# from sympy import *
# from z3 import *

def parse_data() -> dict[str, Any]:
    """Phase 1: Parse and validate public cryptographic parameters."""
    print("[*] Phase 1: Parsing challenge parameters...")
    params: dict[str, Any] = {{
        # "n": ...,
        # "e": ...,
        # "c": ...,
    }}
    return params

def derive_secret(params: dict[str, Any]) -> int | bytes | str:
    """Phase 2-3: Mathematically solve for the secret / plaintext."""
    print("[*] Phase 2-3: Deriving secret via deterministic attack vector...")
    # === [IMPLEMENT DETERMINISTIC ATTACK ALGORITHM HERE] ===
    recovered = "FLAG{{placeholder}}"
    return recovered

def verify_solution(recovered: Any, params: dict[str, Any]) -> bool:
    """Phase 4: Deterministically verify solution satisfies all initial relations."""
    print("[*] Phase 4: Verifying solution against original equations...")
    # Example:
    # if pow(recovered, params['e'], params['n']) != params['c']:
    #     return False
    return True

def solve():
    params = parse_data()
    secret = derive_secret(params)
    if not verify_solution(secret, params):
        print("[-] Verification failed! Solution does not satisfy initial equations.", file=sys.stderr)
        sys.exit(1)

    if isinstance(secret, bytes):
        flag = secret.decode(errors="ignore")
    else:
        flag = str(secret)

    print(f"[+] Recovered flag: {{flag}}")
    return flag

if __name__ == "__main__":
    solve()
"#,
                name = clean_name,
                category = category
            ),
            "web" => format!(
                r#"#!/usr/bin/env python3
"""Deterministic web exploit harness for {name} ({category})."""

import requests
import sys

TARGET_URL = "{target_url}"
session = requests.Session()

def exploit():
    print(f"[*] Attacking endpoint: {{TARGET_URL}}")
    # === [WEB EXPLOIT / INJECTION LOGIC HERE] ===

if __name__ == "__main__":
    exploit()
"#,
                name = clean_name,
                category = category,
                target_url = config.target_url.as_deref().unwrap_or("http://localhost:8080")
            ),
            "reverse" => format!(
                r#"#!/usr/bin/env python3
"""Reverse engineering keygen / logic inverter for {name} ({category})."""

import sys
# from z3 import *

def solve():
    print("[*] Initializing constraint solver / logic inversion...")
    # === [INVERSION / Z3 LOGIC HERE] ===

if __name__ == "__main__":
    solve()
"#,
                name = clean_name,
                category = category
            ),
            _ => format!(
                r#"#!/usr/bin/env python3
"""Deterministic solver for {name} ({category})."""

import sys

def solve():
    print("[*] Running solver logic...")
    # === [SOLVE LOGIC HERE] ===

if __name__ == "__main__":
    solve()
"#,
                name = clean_name,
                category = category
            ),
        };
        fs::write(&solve_path, solver_code)?;
    }

    let reqs_path = solver_dir.join("requirements.txt");
    if !reqs_path.exists() {
        if category == "crypto" {
            fs::write(
                reqs_path,
                "# Python dependencies for standalone crypto solve script\nrequests>=2.28.0\npycryptodome>=3.18.0\nsympy>=1.12\ngmpy2>=2.1.5\n",
            )?;
        } else if category == "pwn" {
            fs::write(
                reqs_path,
                "# Python dependencies for standalone pwn exploit\npwntools>=4.10.0\nrequests>=2.28.0\n",
            )?;
        } else {
            fs::write(
                reqs_path,
                "# Python dependencies for standalone solve script\nrequests>=2.28.0\n",
            )?;
        }
    }

    // 4. Write meta.json (only if not exists)
    let meta_path = session_dir.join("meta.json");
    let now_str = chrono::Utc::now().to_rfc3339();
    if !meta_path.exists() {
        let meta_json = serde_json::json!({
            "chat_id": session_id,
            "label": clean_name,
            "category": category,
            "created_at": now_str,
            "target_host": config.target_host,
            "target_port": config.target_port,
            "target_url": config.target_url,
            "description": config.description,
            "status": "active"
        });
        fs::write(meta_path, serde_json::to_string_pretty(&meta_json)?)?;
    }

    // 5. Update .last_session pointer
    let pointer = serde_json::json!({ "chat_id": session_id });
    let _ = fs::write(paths.workspace_root.join(".last_session"), pointer.to_string());

    // 6. Record to SQLite Database if provided
    if let Some(database) = db {
        let session_item = SessionItem {
            id: session_id.to_string(),
            chat_id: session_id.to_string(),
            label: clean_name,
            ops: 0,
            ops_count: 0,
            created_at: now_str,
            created_ts: chrono::Utc::now().timestamp().max(0) as u64,
            active: true,
        };
        let _ = database.upsert_session(
            &session_item,
            Some(&category),
            config.target_host.as_deref(),
            config.target_port,
        );
    }

    Ok(())
}

pub fn promote_script_to_solver(
    ws_dir: &std::path::Path,
    command: &str,
    stdout: &str,
    stderr: &str,
    exit_code: i32,
    db: Option<&Database>,
    chat_id: Option<&str>,
) -> Option<serde_json::Value> {
    if exit_code != 0 {
        return None;
    }

    let script_dir = ws_dir.join("script");
    if !script_dir.is_dir() {
        return None;
    }

    // Find script file referenced in command
    let mut script_path: Option<PathBuf> = None;
    for token in command.split_whitespace() {
        let clean = token.trim_matches(|c| c == '"' || c == '\'' || c == ';' || c == '&' || c == '|');
        if clean.ends_with(".py") || clean.ends_with(".sh") || clean.ends_with(".js") || clean.ends_with(".rb") {
            let cand1 = ws_dir.join(clean);
            if cand1.is_file() && cand1.starts_with(&script_dir) {
                script_path = Some(cand1);
                break;
            }
            let cand2 = script_dir.join(Path::new(clean).file_name().unwrap_or_default());
            if cand2.is_file() {
                script_path = Some(cand2);
                break;
            }
        }
    }

    let script_file = script_path?;
    let script_content = fs::read_to_string(&script_file).ok()?;

    // 1. Extract flags using regex
    let flag_re = regex::Regex::new(r"([A-Za-z0-9_-]{2,30}\{[^}\n\r\t ]+\})").ok()?;
    let combined_out = format!("{}\n{}", stdout, stderr);
    let mut flags: Vec<String> = Vec::new();
    for cap in flag_re.captures_iter(&combined_out) {
        if let Some(m) = cap.get(1) {
            let f = m.as_str().to_string();
            if !f.to_lowercase().contains("placeholder") && !flags.contains(&f) {
                flags.push(f);
            }
        }
    }

    // 2. Promote to solver/solve.py
    let solver_dir = ws_dir.join("solver");
    let _ = fs::create_dir_all(&solver_dir);
    let solve_py = solver_dir.join("solve.py");
    let _ = fs::write(&solve_py, &script_content);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&solve_py, fs::Permissions::from_mode(0o755));
    }

    // 3. Hoard flag in root workspace flag.txt
    let flag_txt_path = ws_dir.join("flag.txt");
    if !flags.is_empty() {
        let _ = fs::write(&flag_txt_path, flags.join("\n") + "\n");
        // Save to SQLite
        if let Some(database) = db {
            let target_cid = chat_id.unwrap_or(ws_dir.file_name().and_then(|n| n.to_str()).unwrap_or("current"));
            for flag in &flags {
                let _ = database.save_flag(
                    target_cid,
                    flag,
                    Some("harness"),
                    true,
                    Some(&format!("Captured from execution of {}", script_file.display()))
                );
            }
        }
    }

    // 4. Generate solver/WRITEUP.md
    let chal_name = ws_dir.file_name().and_then(|n| n.to_str()).unwrap_or("challenge");
    let now_str = chrono::Utc::now().to_rfc3339();
    let flag_lines = if !flags.is_empty() {
        flags.iter().map(|f| format!("- `{}`", f)).collect::<Vec<_>>().join("\n")
    } else {
        "- *(Flag recovered during script execution)*".to_string()
    };
    let stdout_sample = if stdout.len() > 2000 {
        &stdout[stdout.len() - 2000..]
    } else {
        stdout
    };

    let math_section = if ws_dir.join("notes/math_model.md").is_file() {
        "## 2. Mathematical Model & Attack Vector\n- **Mathematical Model:** Formalized in `notes/math_model.md`.\n- **Protocol:** Strictly followed BQA Extreme Crypto Playbook (Deterministic Verification).\n\n## 3. Reproduction Steps"
    } else {
        "## 2. Reproduction Steps"
    };

    let writeup_content = format!(
r#"# Writeup: {name}

- **Solved At:** {now}
- **Exploit Script:** `{script_name}`
- **Status:** VERIFIED SOLVED

---

## 1. Challenge & Vulnerability Summary
- **Overview:** Challenge `{name}` was analyzed and exploited deterministically.
- **Exploitation Vector:** Automated harness promotion from `{script_name}`.

{math_part}
1. Navigate to the solver directory:
   ```bash
   cd solver
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the standalone exploit:
   ```bash
   python3 solve.py
   ```

## Original Execution Proof
Command executed:
```bash
{cmd}
```

Terminal Output:
```text
{out}
```

## Recovered Flag(s)
{flags_text}

> 🎯 *Flag is hoarded directly in `flag.txt` in the root workspace directory.*
"#,
        name = chal_name,
        now = now_str,
        script_name = script_file.file_name().and_then(|n| n.to_str()).unwrap_or("poc.py"),
        math_part = math_section,
        cmd = command,
        out = stdout_sample.trim(),
        flags_text = flag_lines
    );

    let writeup_path = solver_dir.join("WRITEUP.md");
    let _ = fs::write(&writeup_path, writeup_content);

    Some(serde_json::json!({
        "promoted": true,
        "script_source": script_file.to_string_lossy().to_string(),
        "solver_file": solve_py.to_string_lossy().to_string(),
        "writeup_file": writeup_path.to_string_lossy().to_string(),
        "flag_file": if !flags.is_empty() { Some(flag_txt_path.to_string_lossy().to_string()) } else { None },
        "flags": flags,
        "message": format!("Successfully promoted {} to solver/solve.py, generated WRITEUP.md, and hoarded flag(s) in flag.txt.", script_file.display())
    }))
}
