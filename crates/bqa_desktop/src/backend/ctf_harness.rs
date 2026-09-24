use std::fs;
use std::path::PathBuf;
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
        .collect::<String>();

    let category = match config.category.to_lowercase().as_str() {
        "pwn" | "reverse" | "crypto" | "web" | "forensics" | "misc" | "ai-ml" | "osint" => {
            config.category.to_lowercase()
        }
        _ => "misc".to_string(),
    };

    let session_id = format!("cw-{}-{}", chrono::Utc::now().format("%Y%m%d%H%M%S"), clean_name);
    let session_dir = paths.workspace_root.join(&session_id);

    let chal_dir = session_dir.join("challenge");
    let script_dir = session_dir.join("script");
    let solver_dir = session_dir.join("solver");

    fs::create_dir_all(&chal_dir)?;
    fs::create_dir_all(&script_dir)?;
    fs::create_dir_all(&solver_dir)?;

    // 1. Write challenge/NOTE.md
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
    fs::write(chal_dir.join("NOTE.md"), note_content)?;

    // 2. Write script/analysis.md
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
"#,
        name = clean_name,
        category = category
    );
    fs::write(script_dir.join("analysis.md"), analysis_content)?;

    // 3. Write solver/solve.py based on category
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
"""Deterministic cryptographic solver for {name} ({category})."""

import sys
# from Crypto.Util.number import *
# from sympy import *

def solve():
    print("[*] Loading cryptographic parameters...")
    # === [SOLVER LOGIC HERE] ===

    flag = "FLAG{{placeholder}}"
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
    fs::write(solver_dir.join("solve.py"), solver_code)?;
    fs::write(
        solver_dir.join("requirements.txt"),
        "# Python dependencies for standalone solve script\nrequests>=2.28.0\n",
    )?;

    // 4. Write meta.json
    let now_str = chrono::Utc::now().to_rfc3339();
    let meta_json = serde_json::json!({
        "chat_id": session_id,
        "label": format!("ctf_{}_{}", category, clean_name),
        "category": category,
        "created_at": now_str,
        "target_host": config.target_host,
        "target_port": config.target_port,
        "target_url": config.target_url,
        "description": config.description,
        "status": "active"
    });
    fs::write(session_dir.join("meta.json"), serde_json::to_string_pretty(&meta_json)?)?;

    // 5. Update .last_session pointer
    let pointer = serde_json::json!({ "chat_id": session_id });
    let _ = fs::write(paths.workspace_root.join(".last_session"), pointer.to_string());

    // 6. Record to SQLite Database if provided
    if let Some(database) = db {
        let session_item = SessionItem {
            id: session_id.clone(),
            chat_id: session_id.clone(),
            label: format!("ctf_{}_{}", category, clean_name),
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

    Ok(session_dir)
}
