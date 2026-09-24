use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;
use base64::prelude::*;
use sha2::{Digest, Sha256};

use crate::backend::ctf_harness::{
    promote_script_to_solver, scaffold_ctf_harness, scaffold_ctf_harness_into, HarnessConfig,
};
use crate::backend::paths::AppPaths;
use crate::db::{CommandItem, Database};

pub async fn handle_auto_download_ctf_challenge(
    paths: &Arc<AppPaths>,
    db: &Arc<Database>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let name = args.get("name").and_then(|v| v.as_str()).unwrap_or("chal");
    let category = args.get("category").and_then(|v| v.as_str()).unwrap_or("pwn");
    let url_opt = args.get("url").and_then(|v| v.as_str());
    let target = args.get("target").and_then(|v| v.as_str());
    let description = args.get("description").and_then(|v| v.as_str());

    let (host, port) = if let Some(t) = target {
        if let Some((h, p)) = t.split_once(':') {
            (Some(h.trim().to_string()), p.trim().parse::<i32>().ok())
        } else {
            (Some(t.to_string()), None)
        }
    } else {
        (None, None)
    };

    let cfg = HarnessConfig {
        name: name.to_string(),
        category: category.to_string(),
        target_host: host,
        target_port: port,
        target_url: target.map(|s| s.to_string()),
        description: description.map(|s| s.to_string()),
    };

    let session_dir = scaffold_ctf_harness(paths, Some(db), &cfg)
        .map_err(|e| format!("Lỗi khởi tạo CTF harness: {}", e))?;

    let mut downloaded_files = Vec::new();

    // If URL is provided, download artifact
    if let Some(download_url) = url_opt {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .map_err(|e| format!("Lỗi khởi tạo HTTP client: {}", e))?;

        let res = client
            .get(download_url)
            .send()
            .await
            .map_err(|e| format!("Lỗi tải tệp tin từ URL: {}", e))?;

        if !res.status().is_success() {
            return Err(format!("Máy chủ trả về mã lỗi HTTP: {}", res.status()));
        }

        let bytes = res
            .bytes()
            .await
            .map_err(|e| format!("Lỗi đọc nội dung tải về: {}", e))?;

        let clean_path = download_url.split('?').next().unwrap_or("");
        let fname = clean_path.split('/').next_back().unwrap_or("artifact.bin");
        let fname = if fname.is_empty() { "artifact.bin" } else { fname };

        let chal_dir = session_dir.join("challenge");
        let target_file = chal_dir.join(fname);
        fs::write(&target_file, &bytes)
            .map_err(|e| format!("Lỗi ghi tệp challenge: {}", e))?;
        downloaded_files.push(fname.to_string());

        // Unpack if zip or tarball
        if fname.ends_with(".zip") {
            let _ = std::process::Command::new("unzip")
                .arg("-q")
                .arg(&target_file)
                .arg("-d")
                .arg(&chal_dir)
                .status();
        } else if fname.ends_with(".tar.gz") || fname.ends_with(".tgz") {
            let _ = std::process::Command::new("tar")
                .arg("-xzf")
                .arg(&target_file)
                .arg("-C")
                .arg(&chal_dir)
                .status();
        }
    }

    Ok(serde_json::json!({
        "ok": true,
        "challenge_name": name,
        "category": category,
        "workspace_dir": session_dir.to_string_lossy().to_string(),
        "downloaded_files": downloaded_files,
        "solver_path": session_dir.join("solver/solve.py").to_string_lossy().to_string(),
        "harness_structure": {
            "challenge": "Read-only original challenge artifacts and NOTE.md",
            "script": "Probes, scratch harnesses, and living analysis.md",
            "solver": "Standalone, deterministic final solve.py"
        }
    }))
}

pub fn handle_ctf_transform(args: &serde_json::Value) -> Result<serde_json::Value, String> {
    let text = args.get("text").and_then(|v| v.as_str()).unwrap_or("");
    let op = args.get("operation").and_then(|v| v.as_str()).unwrap_or("b64decode");
    let key = args.get("key").and_then(|v| v.as_str()).unwrap_or("");

    match op.to_lowercase().as_str() {
        "b64encode" => {
            let enc = BASE64_STANDARD.encode(text.as_bytes());
            Ok(serde_json::json!({ "ok": true, "operation": op, "result": enc }))
        }
        "b64decode" => {
            let clean = text.trim();
            let bytes = BASE64_STANDARD
                .decode(clean.as_bytes())
                .map_err(|e| format!("Lỗi giải mã Base64: {}", e))?;
            let res_str = String::from_utf8_lossy(&bytes).to_string();
            let hex_rep = bytes.iter().map(|b| format!("{:02x}", b)).collect::<String>();
            Ok(serde_json::json!({ "ok": true, "operation": op, "result": res_str, "hex": hex_rep }))
        }
        "hexencode" => {
            let hex_str = text.as_bytes().iter().map(|b| format!("{:02x}", b)).collect::<String>();
            Ok(serde_json::json!({ "ok": true, "operation": op, "result": hex_str }))
        }
        "hexdecode" => {
            let clean = text.trim().replace("0x", "").replace(' ', "");
            if clean.len() % 2 != 0 {
                return Err("Độ dài chuỗi hex không hợp lệ (phải là bội số của 2)".to_string());
            }
            let mut bytes = Vec::new();
            for i in (0..clean.len()).step_by(2) {
                let byte = u8::from_str_radix(&clean[i..i + 2], 16)
                    .map_err(|e| format!("Ký tự hex không hợp lệ: {}", e))?;
                bytes.push(byte);
            }
            let res_str = String::from_utf8_lossy(&bytes).to_string();
            Ok(serde_json::json!({ "ok": true, "operation": op, "result": res_str }))
        }
        "rot13" => {
            let rotated: String = text
                .chars()
                .map(|c| match c {
                    'a'..='z' => (((c as u8 - b'a' + 13) % 26) + b'a') as char,
                    'A'..='Z' => (((c as u8 - b'A' + 13) % 26) + b'A') as char,
                    _ => c,
                })
                .collect();
            Ok(serde_json::json!({ "ok": true, "operation": op, "result": rotated }))
        }
        "xor" => {
            if key.is_empty() {
                return Err("Thao tác XOR yêu cầu tham số 'key'".to_string());
            }
            let key_bytes = key.as_bytes();
            let out_bytes: Vec<u8> = text
                .as_bytes()
                .iter()
                .enumerate()
                .map(|(i, b)| b ^ key_bytes[i % key_bytes.len()])
                .collect();
            let res_str = String::from_utf8_lossy(&out_bytes).to_string();
            let hex_rep = out_bytes.iter().map(|b| format!("{:02x}", b)).collect::<String>();
            Ok(serde_json::json!({ "ok": true, "operation": op, "result": res_str, "hex": hex_rep }))
        }
        _ => Err(format!("Thao tác không được hỗ trợ: {}", op)),
    }
}

pub fn handle_ctf_pattern(args: &serde_json::Value) -> Result<serde_json::Value, String> {
    let length = args.get("length").and_then(|v| v.as_u64()).unwrap_or(128) as usize;
    let search = args.get("search").and_then(|v| v.as_str());

    // Generate cyclic 4-byte pattern (aaaa, baaa, caaa ...)
    let charset = b"abcdefghijklmnopqrstuvwxyz";
    let mut pattern = String::new();
    'outer: for l in charset {
        for k in charset {
            for j in charset {
                for i in charset {
                    pattern.push(*i as char);
                    pattern.push(*j as char);
                    pattern.push(*k as char);
                    pattern.push(*l as char);
                    if pattern.len() >= length.max(4096) {
                        break 'outer;
                    }
                }
            }
        }
    }

    if let Some(query) = search {
        let clean_q = query.trim().trim_start_matches("0x");
        let needle = if clean_q.len() == 8 && clean_q.chars().all(|c| c.is_ascii_hexdigit()) {
            // Little endian hex unpack
            let mut bytes = Vec::new();
            for i in (0..clean_q.len()).step_by(2) {
                if let Ok(b) = u8::from_str_radix(&clean_q[i..i + 2], 16) {
                    bytes.push(b);
                }
            }
            bytes.reverse();
            String::from_utf8_lossy(&bytes).to_string()
        } else {
            query.to_string()
        };

        if let Some(pos) = pattern.find(&needle) {
            Ok(serde_json::json!({
                "ok": true,
                "search": query,
                "interpreted_query": needle,
                "offset": pos,
                "found": true
            }))
        } else {
            Ok(serde_json::json!({
                "ok": false,
                "search": query,
                "found": false,
                "message": "Không tìm thấy mẫu chuỗi trong pattern."
            }))
        }
    } else {
        let truncated = &pattern[..length.min(pattern.len())];
        Ok(serde_json::json!({
            "ok": true,
            "length": truncated.len(),
            "pattern": truncated
        }))
    }
}

pub fn handle_ctf_hash_tool(args: &serde_json::Value) -> Result<serde_json::Value, String> {
    let text = args.get("text").and_then(|v| v.as_str());
    let identify = args.get("identify").and_then(|v| v.as_str());

    if let Some(hash_val) = identify {
        let clean = hash_val.trim();
        let len = clean.len();
        let candidates = match len {
            32 => vec!["MD5", "NTLM", "MD4"],
            40 => vec!["SHA-1", "RIPEMD-160"],
            56 => vec!["SHA-224"],
            64 => vec!["SHA-256", "SM3", "BLAKE2s"],
            96 => vec!["SHA-384"],
            128 => vec!["SHA-512", "BLAKE2b", "Whirlpool"],
            _ => {
                if clean.starts_with("$2a$") || clean.starts_with("$2b$") {
                    vec!["bcrypt"]
                } else if clean.starts_with("$argon2") {
                    vec!["Argon2"]
                } else {
                    vec!["Không xác định"]
                }
            }
        };
        Ok(serde_json::json!({
            "ok": true,
            "hash": hash_val,
            "length": len,
            "candidates": candidates
        }))
    } else if let Some(input) = text {
        let mut hasher = Sha256::new();
        hasher.update(input.as_bytes());
        let res = hasher.finalize();
        let sha256_hex = format!("{:x}", res);
        Ok(serde_json::json!({
            "ok": true,
            "input": input,
            "sha256": sha256_hex
        }))
    } else {
        Err("Vui lòng cung cấp 'text' để băm hoặc 'identify' để nhận diện chữ ký hash.".to_string())
    }
}

pub fn handle_host_workspace_bind(
    paths: &Arc<AppPaths>,
    db: &Arc<Database>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let raw_lbl = args.get("label").and_then(|v| v.as_str()).unwrap_or("session").trim();
    let chat_id = args.get("chat_id").and_then(|v| v.as_str());
    let _is_new = args.get("new").and_then(|v| v.as_bool()).unwrap_or(false);
    let explicit_cat = args.get("category").and_then(|v| v.as_str());

    // Detect category from explicit arg or label
    let lower_lbl = raw_lbl.to_lowercase();
    let cats = ["pwn", "crypto", "web", "reverse", "forensics", "misc", "ai-ml", "osint"];
    let mut detected_cat = explicit_cat.map(|c| c.to_lowercase()).unwrap_or_else(|| "misc".to_string());
    if detected_cat == "misc" {
        for cat in &cats {
            if lower_lbl.starts_with(&format!("{}_", cat)) || lower_lbl.starts_with(&format!("{}-", cat)) || lower_lbl == *cat {
                detected_cat = cat.to_string();
                break;
            }
        }
    }
    if detected_cat == "misc" {
        for cat in &cats {
            if lower_lbl.contains(cat) {
                detected_cat = cat.to_string();
                break;
            }
        }
    }

    let mut clean_name = raw_lbl
        .replace("ctf_", "")
        .replace("ctf-", "")
        .replace("ctf", "");
    for cat in &cats {
        if clean_name.to_lowercase().starts_with(&format!("{}_", cat)) {
            clean_name = clean_name[cat.len() + 1..].to_string();
            break;
        } else if clean_name.to_lowercase().starts_with(&format!("{}-", cat)) {
            clean_name = clean_name[cat.len() + 1..].to_string();
            break;
        }
    }
    clean_name = clean_name
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect::<String>()
        .trim_matches('_')
        .trim_matches('-')
        .to_string();
    let clean_name = if clean_name.is_empty() { "chal".to_string() } else { clean_name };

    let session_id = if let Some(cid) = chat_id {
        cid.to_string()
    } else {
        format!("{}_{}", detected_cat, clean_name)
    };

    let ws_dir = paths.workspace_root.join(&session_id);
    fs::create_dir_all(&ws_dir).map_err(|e| format!("Failed to create workspace directory: {}", e))?;

    let cfg = HarnessConfig {
        name: clean_name,
        category: detected_cat,
        target_host: args.get("target_host").and_then(|v| v.as_str()).map(|s| s.to_string()),
        target_port: args.get("target_port").and_then(|v| v.as_i64()).map(|p| p as i32),
        target_url: args.get("target_url").and_then(|v| v.as_str()).map(|s| s.to_string()),
        description: args.get("description").and_then(|v| v.as_str()).map(|s| s.to_string()),
    };

    // ALWAYS enforce 3-folder CTF harness (idempotent, won't overwrite existing notes/solvers)
    if let Err(e) = scaffold_ctf_harness_into(&ws_dir, &session_id, paths, Some(db), &cfg) {
        return Err(format!("Failed to enforce harness layout: {}", e));
    }

    let pointer = serde_json::json!({ "chat_id": session_id });
    let _ = fs::write(paths.workspace_root.join(".last_session"), pointer.to_string());

    let chal_dir = ws_dir.join("challenge");
    let script_dir = ws_dir.join("script");
    let solver_dir = ws_dir.join("solver");
    let math_model_path = ws_dir.join("notes").join("math_model.md");

    let mut harness_map = serde_json::json!({
        "challenge_dir": chal_dir.to_string_lossy().to_string(),
        "script_dir": script_dir.to_string_lossy().to_string(),
        "solver_dir": solver_dir.to_string_lossy().to_string(),
        "note_file": chal_dir.join("NOTE.md").to_string_lossy().to_string(),
        "analysis_file": script_dir.join("analysis.md").to_string_lossy().to_string(),
        "solver_file": solver_dir.join("solve.py").to_string_lossy().to_string(),
    });
    if math_model_path.is_file() {
        if let Some(obj) = harness_map.as_object_mut() {
            obj.insert(
                "math_model_file".to_string(),
                serde_json::json!(math_model_path.to_string_lossy().to_string()),
            );
        }
    }

    let instructions = if cfg.category == "crypto" || math_model_path.is_file() {
        format!(
            "Workspace '{session_id}' is active (Category: CRYPTO). Include chat_id='{session_id}' in subsequent tool calls. \
            CRITICAL BQA CRYPTO PROTOCOL: You MUST adhere to the BQA Extreme Crypto Playbook (app/ctf/playbooks/crypto_playbook.md). \
            1. Parameter Triage: Inspect challenge files and identify public values (n, e, c, curve, PRNG state). \
            2. Mathematical Modeling: Document algebraic structures, unknowns, bounds, and equations in notes/math_model.md. \
            3. Vector Selection: Call tool 'ctf_crypto_playbook' to pick a deterministic attack vector matching observed preconditions. \
            4. Local Verification: Write solver in script/ implementing parse_data(), derive_secret(), and verify_solution(). \
            5. Verification & Promotion: Run via host_run_command. Successful exit code 0 auto-promotes to solver/solve.py, creates WRITEUP.md, and hoards the flag. \
            DO NOT guess or run brute-force attacks without proven small bounds!"
        )
    } else {
        format!("Workspace '{session_id}' is active. Include chat_id='{session_id}' in subsequent tool calls.")
    };

    Ok(serde_json::json!({
        "ok": true,
        "chat_id": session_id,
        "session_id": session_id,
        "workspace": ws_dir.to_string_lossy().to_string(),
        "workspace_dir": ws_dir.to_string_lossy().to_string(),
        "harness_enforced": true,
        "harness": harness_map,
        "instructions": instructions,
        "message": format!("Workspace ready with enforced CTF harness at {}", ws_dir.display()),
    }))
}

pub fn handle_ctf_crypto_playbook(args: &serde_json::Value) -> Result<serde_json::Value, String> {
    let query_opt = args.get("query").and_then(|v| v.as_str());
    let section_opt = args.get("section").and_then(|v| v.as_str());

    let candidate_paths = [
        PathBuf::from("/home/undertaker/Downloads/bqa/botquanganh_mcp/app/ctf/playbooks/crypto_playbook.md"),
        PathBuf::from("app/ctf/playbooks/crypto_playbook.md"),
        PathBuf::from("../app/ctf/playbooks/crypto_playbook.md"),
    ];

    let mut content_opt: Option<String> = None;
    for cand in &candidate_paths {
        if let Ok(c) = fs::read_to_string(cand) {
            content_opt = Some(c);
            break;
        }
    }

    if query_opt.is_none() && section_opt.is_none() {
        return Ok(serde_json::json!({
            "ok": true,
            "discipline": "BQA Extreme Crypto Playbook (Deterministic Cryptanalysis Engine)",
            "protocol": [
                "Phase 1: Parameter & Scheme Triage (extract n, e, c, curve, PRNG state, cipher mode)",
                "Phase 2: Mathematical Modeling (write algebraic relations & bounds in notes/math_model.md)",
                "Phase 3: Attack Vector Selection (query ctf_crypto_playbook or Attack Router Matrix)",
                "Phase 4: Deterministic Local Verification (script/ with parse_data, derive_secret, verify_solution)",
                "Phase 5: Solution Promotion & Hoarding (auto-promote to solver/solve.py, WRITEUP.md, flag.txt)"
            ],
            "attack_categories": [
                { "category": "RSA", "vectors": ["Integer e-th Root", "Common Modulus", "Batch/Shared GCD", "Fermat", "Pollard p-1", "Wiener", "Boneh-Durfee", "Franklin-Reiter", "Coppersmith Small Roots", "Partial Key Exposure"] },
                { "category": "Elliptic Curves (ECC)", "vectors": ["Repeated Nonce", "Biased Nonce / HNP", "Pohlig-Hellman", "Smart's Attack (Anomalous)", "Singular Curves"] },
                { "category": "Discrete Logarithm (DLP)", "vectors": ["Baby-step Giant-step (BSGS)", "Pollard's Rho", "Pohlig-Hellman"] },
                { "category": "Lattices", "vectors": ["CVP / Babai Nearest Plane", "LLL / BKZ Reduction", "Subset Sum / Knapsack (CLOS)", "Noisy Modular Equations"] },
                { "category": "PRNG", "vectors": ["LCG Inversion", "Truncated LCG (Lattice)", "Mersenne Twister Untemper", "Truncated MT19937 (Z3 SMT)", "LFSR Berlekamp-Massey"] },
                { "category": "Symmetric & Hashes", "vectors": ["AES-CBC Padding Oracle", "CBC Bit-Flipping", "Byte-at-a-time ECB", "AES-GCM Nonce Reuse GHASH", "Hash Length Extension", "OTP / Keystream Reuse"] }
            ],
            "guidance": "Pass 'query' (e.g. 'wiener', 'ecc', 'coppersmith', 'lattice', 'gcm') to inspect specific attack parameters and preconditions."
        }));
    }

    let content = match content_opt {
        Some(c) => c,
        None => return Err("Crypto playbook markdown file not found on disk.".to_string()),
    };

    if let Some(sec) = section_opt {
        let sec_lower = sec.to_lowercase();
        let header = match sec_lower.as_str() {
            "phases" => "## 1. Quy trình 5 Giai đoạn",
            "matrix" | "router" => "## 2. Attack Router Matrix",
            "rsa" => "### 3.1. RSA Deep-Dive",
            "ecc" => "### 3.2. Elliptic Curves Deep-Dive",
            "lattice" => "### 3.3. Lattice Discipline",
            "audit" => "## 4. Checklist Kỷ luật",
            _ => "## 2. Attack Router Matrix",
        };
        if let Some(pos) = content.find(header) {
            let rest = &content[pos..];
            let end_pos = rest[header.len()..]
                .find("\n## ")
                .map(|p| p + header.len())
                .unwrap_or(rest.len());
            return Ok(serde_json::json!({
                "ok": true,
                "section": sec,
                "content": rest[..end_pos].trim()
            }));
        }
    }

    if let Some(query) = query_opt {
        let q_lower = query.to_lowercase();
        let terms: Vec<&str> = q_lower.split_whitespace().collect();
        let mut matched_rows = Vec::new();

        let mut in_table = false;
        for line in content.lines() {
            let line_clean = line.trim();
            if line_clean.contains("## 2. Attack Router Matrix") {
                in_table = true;
                continue;
            }
            if in_table && line_clean.starts_with("## ") {
                break;
            }
            if in_table
                && line_clean.starts_with('|')
                && !line_clean.starts_with("|---")
                && !line_clean.contains("Dấu hiệu")
            {
                let parts: Vec<&str> = line_clean
                    .split('|')
                    .map(|s| s.trim())
                    .filter(|s| !s.is_empty())
                    .collect();
                if parts.len() >= 3 {
                    let combined = format!("{} {} {}", parts[0], parts[1], parts[2]).to_lowercase();
                    if terms.iter().any(|&term| combined.contains(term)) {
                        matched_rows.push(serde_json::json!({
                            "observation": parts[0],
                            "prerequisite": parts[1],
                            "vector": parts[2]
                        }));
                    }
                }
            }
        }

        return Ok(serde_json::json!({
            "ok": true,
            "query": query,
            "matched_vectors_count": matched_rows.len(),
            "matched_vectors": matched_rows,
            "guidance": "Verify the prerequisite checks before writing exploit code. Document parameters in notes/math_model.md."
        }));
    }

    Err("Không tìm thấy kết quả phù hợp trong playbook.".to_string())
}

pub fn handle_host_workspace_status(
    paths: &Arc<AppPaths>,
    db: &Arc<Database>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let chat_id = args.get("chat_id").and_then(|v| v.as_str()).unwrap_or("");
    let ws_dir = if !chat_id.is_empty() {
        paths.workspace_root.join(chat_id)
    } else {
        paths.workspace_root.clone()
    };

    let mut files = Vec::new();
    if ws_dir.is_dir() {
        if let Ok(entries) = fs::read_dir(&ws_dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if !name.starts_with('.') {
                    files.push(name);
                }
            }
        }
    }

    let recent_cmds = if !chat_id.is_empty() {
        db.get_session_commands(chat_id).unwrap_or_default()
    } else {
        Vec::new()
    };

    Ok(serde_json::json!({
        "ok": true,
        "workspace": ws_dir.to_string_lossy().to_string(),
        "files": files,
        "recent_commands_count": recent_cmds.len(),
        "recent_commands": recent_cmds.into_iter().take(5).collect::<Vec<_>>(),
    }))
}

pub async fn handle_host_run_command(
    paths: &Arc<AppPaths>,
    db: &Arc<Database>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let cmd = args.get("command").and_then(|v| v.as_str()).unwrap_or("");
    let cwd_arg = args.get("cwd").and_then(|v| v.as_str());
    let chat_id_arg = args.get("chat_id").and_then(|v| v.as_str());
    let timeout = args.get("timeout_seconds").and_then(|v| v.as_u64()).unwrap_or(30);

    let cwd = cwd_arg
        .map(PathBuf::from)
        .or_else(|| {
            chat_id_arg.map(|cid| {
                let candidate = paths.workspace_root.join(cid);
                if candidate.is_dir() {
                    candidate
                } else {
                    paths.workspace_root.clone()
                }
            })
        })
        .unwrap_or_else(|| paths.workspace_root.clone());

    let start_t = Instant::now();
    let child = tokio::process::Command::new("bash")
        .arg("--noprofile")
        .arg("--norc")
        .arg("-c")
        .arg(cmd)
        .current_dir(&cwd)
        .output();

    let output = match tokio::time::timeout(std::time::Duration::from_secs(timeout), child).await {
        Ok(Ok(out)) => out,
        Ok(Err(e)) => return Err(format!("Lỗi khi khởi chạy tiến trình: {}", e)),
        Err(_) => return Err(format!("Lệnh vượt quá thời gian tối đa {}s", timeout)),
    };

    let duration_ms = start_t.elapsed().as_millis() as f64;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let exit_code = output.status.code().unwrap_or(if output.status.success() { 0 } else { 1 });

    let op_id = format!("op-{}", &format!("{:x}", Sha256::digest(cmd.as_bytes()))[..8]);
    let cmd_item = CommandItem {
        id: op_id.clone(),
        tool: "host_run_command".to_string(),
        cmd: cmd.to_string(),
        intent: None,
        exit_code,
        duration: format!("{:.0}ms", duration_ms),
        timestamp: chrono::Utc::now().to_rfc3339(),
        time_short: chrono::Utc::now().format("%m-%d %H:%M").to_string(),
        status: if exit_code == 0 { "success".to_string() } else { "failure".to_string() },
        is_latest: true,
        output: stdout.clone(),
        stderr: stderr.clone(),
        cwd: cwd.to_string_lossy().to_string(),
        raw_json: serde_json::json!({ "command": cmd, "exit_code": exit_code }).to_string(),
    };

    let _ = db.upsert_command("current", &cmd_item);

    let mut promotion_res = None;
    if exit_code == 0 {
        let ws_dir = if cwd.starts_with(&paths.workspace_root) {
            cwd.clone()
        } else {
            paths.workspace_root.clone()
        };
        promotion_res = promote_script_to_solver(&ws_dir, cmd, &stdout, &stderr, exit_code, Some(db), None);
    }

    Ok(serde_json::json!({
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "operation_id": op_id,
        "harness_promotion": promotion_res
    }))
}

fn resolve_scoped_path(
    paths: &Arc<AppPaths>,
    path_str: &str,
    chat_id: Option<&str>,
    is_write: bool,
) -> Result<PathBuf, String> {
    let p = Path::new(path_str);
    let root = &paths.workspace_root;

    let target_path = if let Some(cid) = chat_id {
        let ws_dir = root.join(cid);
        if p.is_absolute() {
            let abs_p = p.to_path_buf();
            if abs_p.starts_with(root) && !abs_p.starts_with(&ws_dir) {
                if let Ok(rel) = abs_p.strip_prefix(root) {
                    let first_comp = rel.components().next().map(|c| c.as_os_str().to_string_lossy());
                    if let Some(comp) = first_comp {
                        if comp == "script" || comp == "challenge" || comp == "solver" {
                            ws_dir.join(rel)
                        } else {
                            abs_p
                        }
                    } else {
                        abs_p
                    }
                } else {
                    abs_p
                }
            } else {
                abs_p
            }
        } else {
            ws_dir.join(p)
        }
    } else {
        if p.is_absolute() {
            p.to_path_buf()
        } else {
            root.join(p)
        }
    };

    if is_write {
        for reserved in &["script", "challenge", "solver"] {
            let reserved_dir = root.join(reserved);
            if target_path == reserved_dir || target_path.starts_with(&reserved_dir) {
                return Err(format!(
                    "Policy BQA: Cấm tạo file/thư mục ('{}') trực tiếp tại thư mục gốc '{:?}'. Mọi tệp phải nằm bên trong thư mục workspace của challenge cụ thể.",
                    reserved, root
                ));
            }
        }
    }

    Ok(target_path)
}

pub fn handle_host_read_file(
    paths: &Arc<AppPaths>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let path_str = args.get("path").and_then(|v| v.as_str()).unwrap_or("");
    let chat_id = args.get("chat_id").and_then(|v| v.as_str());
    let start_line = args.get("start_line").and_then(|v| v.as_i64()).unwrap_or(1).max(1) as usize;
    let end_line = args.get("end_line").and_then(|v| v.as_i64()).unwrap_or(200).max(start_line as i64) as usize;

    let target_path = resolve_scoped_path(paths, path_str, chat_id, false)?;

    if !target_path.is_file() {
        return Err(format!("Tệp không tồn tại: {}", target_path.display()));
    }

    let content = fs::read_to_string(&target_path)
        .map_err(|e| format!("Lỗi khi đọc tệp tin: {}", e))?;
    let lines: Vec<&str> = content.lines().collect();
    let slice_end = end_line.min(lines.len());
    let slice_start = (start_line - 1).min(slice_end);
    let output = lines[slice_start..slice_end].join("\n");

    Ok(serde_json::json!({
        "ok": true,
        "path": target_path.to_string_lossy().to_string(),
        "start_line": start_line,
        "end_line": slice_end,
        "total_lines": lines.len(),
        "content": output
    }))
}

pub fn handle_host_write_file(
    paths: &Arc<AppPaths>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let path_str = args.get("path").and_then(|v| v.as_str()).unwrap_or("");
    let content = args.get("content").and_then(|v| v.as_str()).unwrap_or("");
    let chat_id = args.get("chat_id").and_then(|v| v.as_str());

    let target_path = resolve_scoped_path(paths, path_str, chat_id, true)?;

    if let Some(parent) = target_path.parent() {
        let _ = fs::create_dir_all(parent);
    }

    fs::write(&target_path, content)
        .map_err(|e| format!("Lỗi khi ghi tệp: {}", e))?;

    Ok(serde_json::json!({
        "ok": true,
        "path": target_path.to_string_lossy().to_string(),
        "size_bytes": content.len()
    }))
}

pub fn handle_host_save_note(
    paths: &Arc<AppPaths>,
    args: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let content = args.get("content").and_then(|v| v.as_str()).unwrap_or("");
    let chat_id = args.get("chat_id").and_then(|v| v.as_str());

    let ws_dir = if let Some(cid) = chat_id {
        paths.workspace_root.join(cid)
    } else {
        paths.workspace_root.clone()
    };

    let notes_dir = ws_dir.join("notes");
    let _ = fs::create_dir_all(&notes_dir);
    let log_file = notes_dir.join("log.txt");

    let now_str = chrono::Utc::now().to_rfc3339();
    let entry = format!("[{}] {}\n", now_str, content);

    use std::io::Write;
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_file)
        .map_err(|e| format!("Lỗi khi mở log.txt: {}", e))?;
    file.write_all(entry.as_bytes())
        .map_err(|e| format!("Lỗi khi ghi note: {}", e))?;

    Ok(serde_json::json!({
        "ok": true,
        "note_file": log_file.to_string_lossy().to_string(),
        "timestamp": now_str
    }))
}

pub fn handle_health_check(
    paths: &Arc<AppPaths>,
    db: &Arc<Database>,
) -> Result<serde_json::Value, String> {
    let session_count = db.get_sessions().map(|s| s.len()).unwrap_or(0);
    let flags_count = db.get_flags(None).map(|f| f.len()).unwrap_or(0);

    Ok(serde_json::json!({
        "ok": true,
        "status": "healthy",
        "service": "botquanganh-mcp-rust",
        "version": "1.0.0",
        "engine": "Rust (Native Clean Architecture)",
        "database": {
            "type": "SQLite (WAL mode)",
            "path": paths.db_path.to_string_lossy().to_string(),
            "sessions": session_count,
            "flags": flags_count
        },
        "workspace_root": paths.workspace_root.to_string_lossy().to_string()
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ctf_transform_all_operations() {
        // Base64
        let enc_res = handle_ctf_transform(&serde_json::json!({
            "text": "flag{rust_clean_mcp}",
            "operation": "b64encode"
        })).unwrap();
        assert_eq!(enc_res["result"], "ZmxhZ3tydXN0X2NsZWFuX21jcH0=");

        let dec_res = handle_ctf_transform(&serde_json::json!({
            "text": "ZmxhZ3tydXN0X2NsZWFuX21jcH0=",
            "operation": "b64decode"
        })).unwrap();
        assert_eq!(dec_res["result"], "flag{rust_clean_mcp}");

        // Hex
        let hex_enc = handle_ctf_transform(&serde_json::json!({
            "text": "hello",
            "operation": "hexencode"
        })).unwrap();
        assert_eq!(hex_enc["result"], "68656c6c6f");

        let hex_dec = handle_ctf_transform(&serde_json::json!({
            "text": "68656c6c6f",
            "operation": "hexdecode"
        })).unwrap();
        assert_eq!(hex_dec["result"], "hello");

        // ROT13
        let rot = handle_ctf_transform(&serde_json::json!({
            "text": "cvpbPGS{grfg}",
            "operation": "rot13"
        })).unwrap();
        assert_eq!(rot["result"], "picoCTF{test}");

        // XOR
        let xor_enc = handle_ctf_transform(&serde_json::json!({
            "text": "secret",
            "operation": "xor",
            "key": "K"
        })).unwrap();
        let xor_dec = handle_ctf_transform(&serde_json::json!({
            "text": xor_enc["result"],
            "operation": "xor",
            "key": "K"
        })).unwrap();
        assert_eq!(xor_dec["result"], "secret");
    }

    #[test]
    fn test_ctf_pattern_and_offset() {
        let pattern_res = handle_ctf_pattern(&serde_json::json!({
            "length": 64
        })).unwrap();
        assert_eq!(pattern_res["ok"], true);
        let pat_str = pattern_res["pattern"].as_str().unwrap();
        assert_eq!(pat_str.len(), 64);
        assert!(pat_str.starts_with("aaaa"));

        // Search
        let offset_res = handle_ctf_pattern(&serde_json::json!({
            "search": "baaa"
        })).unwrap();
        assert_eq!(offset_res["ok"], true);
        assert_eq!(offset_res["offset"], 4);
    }

    #[test]
    fn test_ctf_hash_tool() {
        let hash_res = handle_ctf_hash_tool(&serde_json::json!({
            "text": "antigravity"
        })).unwrap();
        assert_eq!(hash_res["ok"], true);
        assert_eq!(hash_res["sha256"].as_str().unwrap().len(), 64);

        // Identify length 32 -> MD5
        let id_res = handle_ctf_hash_tool(&serde_json::json!({
            "identify": "5d41402abc4b2a76b9719d911017c592"
        })).unwrap();
        assert_eq!(id_res["candidates"][0], "MD5");
    }

    #[tokio::test]
    async fn test_auto_download_harness_local() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_mcp_harness_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");
        paths.db_path = temp_dir.join("test.db");

        let db = Database::open(&paths.db_path).unwrap();

        let paths_arc = Arc::new(paths);
        let db_arc = Arc::new(db);

        let res = handle_auto_download_ctf_challenge(&paths_arc, &db_arc, &serde_json::json!({
            "name": "fmt_vuln",
            "category": "pwn",
            "target": "10.10.10.10:9999",
            "description": "Format string leak and overwrite"
        })).await.unwrap();

        assert_eq!(res["ok"], true);
        let ws_path = PathBuf::from(res["workspace_dir"].as_str().unwrap());
        assert!(ws_path.join("challenge").join("NOTE.md").is_file());
        assert!(ws_path.join("script").join("analysis.md").is_file());
        assert!(ws_path.join("solver").join("solve.py").is_file());

        let solve_content = fs::read_to_string(ws_path.join("solver").join("solve.py")).unwrap();
        assert!(solve_content.contains("HOST = \"10.10.10.10\""));
        assert!(solve_content.contains("PORT = 9999"));

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_host_workspace_bind_enforces_harness_unconditionally() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_bind_harness_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");
        paths.db_path = temp_dir.join("test.db");

        let db = Database::open(&paths.db_path).unwrap();
        let paths_arc = Arc::new(paths);
        let db_arc = Arc::new(db);

        // 1. First bind with custom non-CTF label
        let bind_res = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "my_incident_investigation"
        })).unwrap();

        assert_eq!(bind_res["ok"], true);
        assert_eq!(bind_res["harness_enforced"], true);
        let ws_path = PathBuf::from(bind_res["workspace"].as_str().unwrap());
        assert!(ws_path.join("challenge").join("NOTE.md").is_file());
        assert!(ws_path.join("script").join("analysis.md").is_file());
        assert!(ws_path.join("solver").join("solve.py").is_file());

        // 2. User writes custom work into solver/solve.py
        let custom_solver_code = "#!/usr/bin/env python3\nprint('USER_CUSTOM_SOLVER_PAYLOAD')";
        fs::write(ws_path.join("solver").join("solve.py"), custom_solver_code).unwrap();

        // 3. Re-bind / resume session with same chat_id
        let chat_id = bind_res["chat_id"].as_str().unwrap();
        let rebind_res = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "chat_id": chat_id,
            "label": "my_incident_investigation"
        })).unwrap();

        assert_eq!(rebind_res["ok"], true);
        // Verify custom code was NOT overwritten on resume
        let current_solver_content = fs::read_to_string(ws_path.join("solver").join("solve.py")).unwrap();
        assert_eq!(current_solver_content, custom_solver_code);

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_host_workspace_bind_category_naming_and_version_collision() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_naming_collision_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");
        paths.db_path = temp_dir.join("test.db");

        let db = Database::open(&paths.db_path).unwrap();
        let paths_arc = Arc::new(paths);
        let db_arc = Arc::new(db);

        // 1. Initial bind with category label -> pwn_babybof
        let res1 = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "pwn_babybof"
        })).unwrap();
        assert_eq!(res1["chat_id"], "pwn_babybof");
        let p1 = PathBuf::from(res1["workspace"].as_str().unwrap());
        assert_eq!(p1.file_name().unwrap().to_str().unwrap(), "pwn_babybof");

        // 2. Re-bind without new=true -> reuses pwn_babybof
        let res_resume = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "pwn_babybof"
        })).unwrap();
        assert_eq!(res_resume["chat_id"], "pwn_babybof");

        // 3. Bind with new=true still continues in canonical folder to avoid clutter
        let res2 = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "pwn_babybof",
            "new": true
        })).unwrap();
        assert_eq!(res2["chat_id"], "pwn_babybof");
        let p2 = PathBuf::from(res2["workspace"].as_str().unwrap());
        assert_eq!(p2.file_name().unwrap().to_str().unwrap(), "pwn_babybof");

        // 4. Crypto challenge detection
        let res3 = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "ez_rsa_factor",
            "category": "crypto"
        })).unwrap();
        assert_eq!(res3["chat_id"], "crypto_ez_rsa_factor");

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[tokio::test]
    async fn test_promote_script_to_solver_and_hoard_flag() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_promote_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");
        paths.db_path = temp_dir.join("test.db");

        let db = Database::open(&paths.db_path).unwrap();
        let paths_arc = Arc::new(paths);
        let db_arc = Arc::new(db);

        // 1. Bind session
        let bind_res = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "pwn_canary_leak"
        })).unwrap();

        let ws_path = PathBuf::from(bind_res["workspace"].as_str().unwrap());
        let script_file = ws_path.join("script").join("exploit.py");

        // 2. User writes exploratory exploit in script/
        let exploit_code = r#"#!/usr/bin/env python3
print("Stage 1: Leaking canary...")
print("Stage 2: Payload dispatch...")
print("Got shell! Output: FLAG{canary_master_leak_win_1337}")
"#;
        fs::write(&script_file, exploit_code).unwrap();

        // 3. User runs script via handle_host_run_command
        let cmd = format!("python3 script/exploit.py");
        let run_res = handle_host_run_command(&paths_arc, &db_arc, &serde_json::json!({
            "command": cmd,
            "cwd": ws_path.to_string_lossy().to_string()
        })).await.unwrap();

        assert_eq!(run_res["ok"], true);
        assert!(run_res["harness_promotion"]["promoted"].as_bool().unwrap());

        // 4. Verify solve.py promoted
        let solve_content = fs::read_to_string(ws_path.join("solver").join("solve.py")).unwrap();
        assert_eq!(solve_content, exploit_code);

        // 5. Verify flag.txt created in root workspace
        let flag_content = fs::read_to_string(ws_path.join("flag.txt")).unwrap();
        assert!(flag_content.contains("FLAG{canary_master_leak_win_1337}"));

        // 6. Verify solver/WRITEUP.md generated
        let writeup_content = fs::read_to_string(ws_path.join("solver").join("WRITEUP.md")).unwrap();
        assert!(writeup_content.contains("# Writeup:"));
        assert!(writeup_content.contains("VERIFIED SOLVED"));
        assert!(writeup_content.contains("FLAG{canary_master_leak_win_1337}"));

        // 7. Verify flag persisted in SQLite DB
        let flags = db_arc.get_flags(None).unwrap();
        assert!(!flags.is_empty());
        assert_eq!(flags[0].flag, "FLAG{canary_master_leak_win_1337}");
        assert!(flags[0].verified);

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_root_protection_and_scoped_path_resolution() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_scope_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.workspace_root = temp_dir.join("BQA");
        let _ = fs::create_dir_all(&paths.workspace_root);
        let paths_arc = Arc::new(paths);

        // 1. Ghi file với chat_id -> Tự động scope vào workspace của session
        let write_res = handle_host_write_file(&paths_arc, &serde_json::json!({
            "path": "script/ida_xrefs.py",
            "content": "# ida script",
            "chat_id": "rev_atarude"
        })).unwrap();

        assert_eq!(write_res["ok"], true);
        let expected_file = paths_arc.workspace_root.join("rev_atarude").join("script").join("ida_xrefs.py");
        assert!(expected_file.is_file());
        assert!(!paths_arc.workspace_root.join("script").exists(), "Thư mục script rác đã bị tạo ở root!");

        // 2. Đọc file với relative path và chat_id
        let read_res = handle_host_read_file(&paths_arc, &serde_json::json!({
            "path": "script/ida_xrefs.py",
            "chat_id": "rev_atarude"
        })).unwrap();
        assert_eq!(read_res["ok"], true);
        assert!(read_res["content"].as_str().unwrap().contains("# ida script"));

        // 3. Cố tình ghi vào root/script không có chat_id -> Bị Policy chặn
        let blocked = handle_host_write_file(&paths_arc, &serde_json::json!({
            "path": paths_arc.workspace_root.join("script").join("bad.py").to_string_lossy().to_string(),
            "content": "bad"
        }));
        assert!(blocked.is_err());
        assert!(blocked.unwrap_err().contains("Policy BQA"));

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_ctf_crypto_playbook_tool() {
        // 1. Overview
        let overview = handle_ctf_crypto_playbook(&serde_json::json!({})).unwrap();
        assert_eq!(overview["ok"], true);
        assert!(overview["discipline"].as_str().unwrap().contains("BQA Extreme Crypto Playbook"));
        assert_eq!(overview["protocol"].as_array().unwrap().len(), 5);

        // 2. Query search
        let rsa_query = handle_ctf_crypto_playbook(&serde_json::json!({ "query": "wiener" })).unwrap();
        assert_eq!(rsa_query["ok"], true);
        assert!(rsa_query["matched_vectors_count"].as_u64().unwrap() >= 1);
        let vectors = rsa_query["matched_vectors"].as_array().unwrap();
        assert!(vectors.iter().any(|v| v["vector"].as_str().unwrap().to_lowercase().contains("wiener")));

        // 3. Section lookup
        let sec_res = handle_ctf_crypto_playbook(&serde_json::json!({ "section": "phases" })).unwrap();
        assert_eq!(sec_res["ok"], true);
        assert!(sec_res["content"].as_str().unwrap().contains("Quy trình 5 Giai đoạn"));
    }

    #[test]
    fn test_crypto_workspace_bind_enforces_playbook_and_math_model() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_crypto_bind_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");
        paths.db_path = temp_dir.join("test.db");

        let db = Database::open(&paths.db_path).unwrap();
        let paths_arc = Arc::new(paths);
        let db_arc = Arc::new(db);

        let bind_res = handle_host_workspace_bind(&paths_arc, &db_arc, &serde_json::json!({
            "label": "crypto_rsa_oracle"
        })).unwrap();

        assert_eq!(bind_res["ok"], true);
        assert!(bind_res["instructions"].as_str().unwrap().contains("Category: CRYPTO"));
        assert!(bind_res["instructions"].as_str().unwrap().contains("BQA Extreme Crypto Playbook"));

        let ws_path = PathBuf::from(bind_res["workspace"].as_str().unwrap());
        let math_file = ws_path.join("notes").join("math_model.md");
        assert!(math_file.is_file());

        let math_text = fs::read_to_string(&math_file).unwrap();
        assert!(math_text.contains("# Mathematical Model: rsa_oracle"));
        assert!(math_text.contains("Algebraic Structure & Domains"));
        assert!(math_text.contains("Selected Attack Vector"));

        // Verify solve.py template has 3-phase structure
        let solve_path = ws_path.join("solver").join("solve.py");
        assert!(solve_path.is_file());
        let solve_text = fs::read_to_string(&solve_path).unwrap();
        assert!(solve_text.contains("def parse_data()"));
        assert!(solve_text.contains("def derive_secret(params"));
        assert!(solve_text.contains("def verify_solution(recovered"));
        assert!(solve_text.contains("verify_solution(secret, params)"));

        // Verify requirements.txt
        let reqs_path = ws_path.join("solver").join("requirements.txt");
        assert!(reqs_path.is_file());
        let reqs_text = fs::read_to_string(&reqs_path).unwrap();
        assert!(reqs_text.contains("pycryptodome"));
        assert!(reqs_text.contains("sympy"));
        assert!(reqs_text.contains("gmpy2"));

        let _ = fs::remove_dir_all(&temp_dir);
    }
}



