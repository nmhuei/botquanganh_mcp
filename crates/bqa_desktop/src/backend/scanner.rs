use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use crate::backend::paths::AppPaths;
use crate::backend::sanitizer::sanitize_honeypot_text;
use crate::db::{CommandItem, Database, LogItem, SessionItem};

pub fn read_last_lines(path: &Path, max_lines: usize) -> Vec<String> {
    use std::io::{BufRead, BufReader, Seek, SeekFrom};
    let file = match fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return Vec::new(),
    };
    let mut reader = BufReader::new(file);
    let file_len = match reader.seek(SeekFrom::End(0)) {
        Ok(len) => len,
        Err(_) => return Vec::new(),
    };

    let chunk_size: u64 = 8 * 1024 * 1024;
    let start_pos = file_len.saturating_sub(chunk_size);
    let _ = reader.seek(SeekFrom::Start(start_pos));

    let mut lines = Vec::new();
    let mut line_iter = reader.lines().map_while(Result::ok);
    if start_pos > 0 {
        let _ = line_iter.next();
    }
    for line in line_iter {
        let trimmed = line.trim().to_string();
        if !trimmed.is_empty() {
            lines.push(trimmed);
        }
    }

    if lines.len() > max_lines {
        lines.split_off(lines.len() - max_lines)
    } else {
        lines
    }
}

pub fn scan_workspaces(root: &Path, db: Option<&Database>) -> Vec<SessionItem> {
    let mut last_session_id: Option<String> = None;
    let pointer_path = root.join(".last_session");
    if let Ok(content) = fs::read_to_string(&pointer_path) {
        if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(c) = val.get("chat_id").and_then(|v| v.as_str()) {
                if root.join(c).is_dir() || root.join(".archive").join(c).is_dir() {
                    last_session_id = Some(c.to_string());
                }
            }
        }
    }

    struct Scanned {
        item: SessionItem,
        created_ts: u64,
        mtime: u64,
        category: Option<String>,
        target_host: Option<String>,
        target_port: Option<i32>,
    }
    let mut scanned_list = Vec::new();

    let scan_dirs = [
        (root.to_path_buf(), false),
        (root.join(".archive"), true),
    ];

    for (dir, _is_archived) in scan_dirs {
        if !dir.is_dir() {
            continue;
        }
        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let name = path
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    let is_ctf_prefix = [
                        "pwn_", "crypto_", "web_", "reverse_", "forensics_", "misc_", "ai-ml_", "osint_"
                    ].iter().any(|p| name.starts_with(p));

                    if !name.starts_with('.')
                        && (name.starts_with("cw-")
                            || is_ctf_prefix
                            || path.join("meta.json").exists()
                            || path.join("metadata.json").exists()
                            || path.join("journal.jsonl").exists()
                            || path.join("challenge").is_dir()
                            || path.join("solver").is_dir())
                    {
                        let mut ops = 0;
                        let mut label = if name.starts_with("cw-") {
                            name.replace("cw-", "")
                        } else {
                            name.clone()
                        };
                        let mut created_at = String::new();
                        let mut category = None;
                        let mut target_host = None;
                        let mut target_port = None;

                        let meta_path = path.join("meta.json");
                        let metadata_path = path.join("metadata.json");

                        if let Ok(content) = fs::read_to_string(&meta_path) {
                            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                                if let Some(l) = val.get("label").and_then(|v| v.as_str()) {
                                    if !l.trim().is_empty() {
                                        label = l.to_string();
                                    }
                                }
                                if let Some(c) = val.get("created_at").and_then(|v| v.as_str()) {
                                    created_at = c.to_string();
                                }
                                category = val.get("category").and_then(|v| v.as_str()).map(String::from);
                                target_host = val.get("target_host").and_then(|v| v.as_str()).map(String::from);
                                target_port = val.get("target_port").and_then(|v| v.as_i64()).map(|p| p as i32);
                            }
                        } else if let Ok(content) = fs::read_to_string(&metadata_path) {
                            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                                if let Some(n) = val.get("name").and_then(|v| v.as_str()) {
                                    if !n.trim().is_empty() {
                                        label = n.to_string();
                                    }
                                }
                                if let Some(c) = val.get("created_at").and_then(|v| v.as_str()) {
                                    created_at = c.to_string();
                                }
                                category = val.get("category").and_then(|v| v.as_str()).map(String::from);
                                target_host = val.get("target_host").and_then(|v| v.as_str()).map(String::from);
                                target_port = val.get("target_port").and_then(|v| v.as_i64()).map(|p| p as i32);
                            }
                        }

                        if category.is_none() {
                            for cat in &["pwn", "crypto", "web", "reverse", "forensics", "misc", "ai-ml", "osint"] {
                                if name.starts_with(&format!("{}_", cat)) {
                                    category = Some(cat.to_string());
                                    if label == name {
                                        label = name[cat.len() + 1..].to_string();
                                    }
                                    break;
                                }
                            }
                        }

                        let journal_path = path.join("journal.jsonl");
                        let mut mtime = entry
                            .metadata()
                            .and_then(|m| m.modified())
                            .ok()
                            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                            .map(|d| d.as_secs())
                            .unwrap_or(0);

                        if let Ok(meta) = fs::metadata(&journal_path) {
                            let lines = read_last_lines(&journal_path, 300);
                            ops = lines.len();
                            if meta.len() > 100_000 && ops == 300 {
                                ops = (meta.len() / 300) as usize;
                            }
                            if let Ok(j_mod) = meta.modified() {
                                if let Ok(j_dur) = j_mod.duration_since(std::time::UNIX_EPOCH) {
                                    mtime = mtime.max(j_dur.as_secs());
                                }
                            }
                        }

                        // Determine creation timestamp (created_ts)
                        let mut created_ts = 0u64;
                        if !created_at.is_empty() {
                            if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(&created_at) {
                                created_ts = dt.timestamp().max(0) as u64;
                            }
                        }
                        if created_ts == 0 {
                            if let Ok(meta) = entry.metadata() {
                                if let Ok(created) = meta.created() {
                                    if let Ok(dur) = created.duration_since(std::time::UNIX_EPOCH) {
                                        created_ts = dur.as_secs();
                                    }
                                }
                            }
                        }
                        if created_ts == 0 {
                            let digits: String = name.chars().filter(|c| c.is_ascii_digit()).collect();
                            if digits.len() >= 8 {
                                if let (Ok(year), Ok(month), Ok(day)) = (
                                    digits[0..4].parse::<i32>(),
                                    digits[4..6].parse::<u32>(),
                                    digits[6..8].parse::<u32>(),
                                ) {
                                    if let Some(date) =
                                        chrono::NaiveDate::from_ymd_opt(year, month, day)
                                    {
                                        let hour = if digits.len() >= 10 {
                                            digits[8..10].parse::<u32>().unwrap_or(0)
                                        } else {
                                            0
                                        };
                                        let min = if digits.len() >= 12 {
                                            digits[10..12].parse::<u32>().unwrap_or(0)
                                        } else {
                                            0
                                        };
                                        let sec = if digits.len() >= 14 {
                                            digits[12..14].parse::<u32>().unwrap_or(0)
                                        } else {
                                            0
                                        };
                                        if let Some(dt) = date.and_hms_opt(hour, min, sec) {
                                            created_ts = dt.and_utc().timestamp().max(0) as u64;
                                        }
                                    }
                                }
                            }
                        }
                        if created_ts == 0 {
                            created_ts = mtime;
                        }

                        scanned_list.push(Scanned {
                            item: SessionItem {
                                id: name.clone(),
                                chat_id: name,
                                label,
                                ops,
                                ops_count: ops,
                                created_at,
                                created_ts,
                                active: false,
                            },
                            created_ts,
                            mtime,
                            category,
                            target_host,
                            target_port,
                        });
                    }
                }
            }
        }
    }

    // Sort strictly by creation time descending (newest created workspace first)
    scanned_list.sort_by(|a, b| {
        b.created_ts
            .cmp(&a.created_ts)
            .then_with(|| b.mtime.cmp(&a.mtime))
            .then_with(|| a.item.chat_id.cmp(&b.item.chat_id))
    });

    let mut sessions = Vec::with_capacity(scanned_list.len());
    for (idx, mut sc) in scanned_list.into_iter().enumerate() {
        if let Some(ref active_id) = last_session_id {
            sc.item.active = sc.item.chat_id == *active_id;
        } else if idx == 0 {
            sc.item.active = true;
        }

        // Persist to SQLite Database if provided
        if let Some(database) = db {
            let _ = database.upsert_session(
                &sc.item,
                sc.category.as_deref(),
                sc.target_host.as_deref(),
                sc.target_port,
            );
        }

        sessions.push(sc.item);
    }
    sessions
}

pub fn delete_workspace_folder(workspace_root: &Path, chat_id: &str) -> (bool, String) {
    let clean_id = chat_id.trim();
    if clean_id.is_empty() {
        return (false, "Tên workspace không được để trống".to_string());
    }
    if clean_id.contains('/')
        || clean_id.contains('\\')
        || clean_id.contains("..")
        || clean_id.starts_with('.')
    {
        return (false, "Tên workspace không hợp lệ".to_string());
    }

    let ws_dir = workspace_root.join(clean_id);
    let archive_dir = workspace_root.join(".archive").join(clean_id);
    let mut deleted_any = false;
    let mut err_msg = String::new();

    if ws_dir.is_dir() {
        match fs::remove_dir_all(&ws_dir) {
            Ok(_) => {
                deleted_any = true;
            }
            Err(e) => {
                err_msg = format!("Lỗi khi xóa thư mục {}: {}", ws_dir.display(), e);
            }
        }
    }
    if archive_dir.is_dir() {
        match fs::remove_dir_all(&archive_dir) {
            Ok(_) => {
                deleted_any = true;
            }
            Err(e) => {
                if err_msg.is_empty() {
                    err_msg = format!("Lỗi khi xóa archive {}: {}", archive_dir.display(), e);
                }
            }
        }
    }

    if deleted_any {
        let pointer_path = workspace_root.join(".last_session");
        if let Ok(content) = fs::read_to_string(&pointer_path) {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                if val.get("chat_id").and_then(|v| v.as_str()) == Some(clean_id) {
                    let _ = fs::remove_file(&pointer_path);
                }
            }
        }
        (
            true,
            "Đã xóa vĩnh viễn không gian làm việc thành công".to_string(),
        )
    } else if err_msg.is_empty() {
        (
            true,
            "Không tìm thấy thư mục workspace trên ổ đĩa".to_string(),
        )
    } else {
        (false, err_msg)
    }
}

pub fn read_session_commands(paths: &AppPaths, chat_id: &str, db: Option<&Database>) -> Vec<CommandItem> {
    let mut mcp_by_op: HashMap<String, serde_json::Value> = HashMap::new();
    let mut mcp_fallback_records: Vec<serde_json::Value> = Vec::new();

    // 1. Read MCP command activity log
    let mcp_log_path = paths.repo_root.join("logs/mcp_command_activity.jsonl");
    if mcp_log_path.exists() {
        if let Ok(file) = fs::File::open(&mcp_log_path) {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(file);
            for line in reader.lines().map_while(Result::ok) {
                if !line.contains(chat_id) {
                    continue;
                }
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&line) {
                    let rec_chat_id = val.get("chat_id").and_then(|v| v.as_str()).unwrap_or("");
                    if rec_chat_id == chat_id {
                        if let Some(op_id) = val.get("operation_id").and_then(|v| v.as_str()) {
                            let phase = val.get("phase").and_then(|v| v.as_str()).unwrap_or("");
                            if phase == "completed" || !mcp_by_op.contains_key(op_id) {
                                mcp_by_op.insert(op_id.to_string(), val.clone());
                            }
                        }
                        if val.get("phase").and_then(|v| v.as_str()) == Some("completed") {
                            mcp_fallback_records.push(val);
                        }
                    }
                }
            }
        }
    }

    // 2. Read workspace journal
    let ws_dir = if paths.workspace_root.join(chat_id).is_dir() {
        paths.workspace_root.join(chat_id)
    } else {
        paths.workspace_root.join(".archive").join(chat_id)
    };
    let journal_archive = ws_dir.join("journal.jsonl.1");
    let journal_path = ws_dir.join("journal.jsonl");

    let mut op_order: Vec<String> = Vec::new();
    let mut started_ops: HashMap<String, serde_json::Value> = HashMap::new();
    let mut result_ops: HashMap<String, serde_json::Value> = HashMap::new();

    for fpath in &[journal_archive, journal_path] {
        if fpath.exists() {
            if let Ok(file) = fs::File::open(fpath) {
                use std::io::{BufRead, BufReader};
                let reader = BufReader::new(file);
                for line in reader.lines().map_while(Result::ok) {
                    let trimmed = line.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(trimmed) {
                        let op_id = val
                            .get("op")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        if op_id.is_empty() {
                            continue;
                        }
                        let event_type = val.get("type").and_then(|v| v.as_str()).unwrap_or("");
                        if event_type == "op_started" {
                            if !started_ops.contains_key(&op_id) {
                                op_order.push(op_id.clone());
                            }
                            started_ops.insert(op_id, val);
                        } else if event_type == "op_result" {
                            result_ops.insert(op_id, val);
                        }
                    }
                }
            }
        }
    }

    let mut commands: Vec<CommandItem> = Vec::new();

    // 3. Reconcile journal operations with MCP activity records
    for op_id in &op_order {
        let started = match started_ops.get(op_id) {
            Some(s) => s,
            None => continue,
        };
        let result = result_ops.get(op_id);
        let mcp = mcp_by_op.get(op_id);

        let kind = started
            .get("kind")
            .or_else(|| started.get("tool"))
            .and_then(|v| v.as_str())
            .unwrap_or("host_run_command");
        let payload = started.get("payload");

        let raw_intent = payload
            .and_then(|p| p.get("intent"))
            .and_then(|v| v.as_str())
            .map(|s| s.trim())
            .filter(|s| !s.is_empty());
        let intent_note = raw_intent.map(sanitize_honeypot_text);

        let cmd = if let Some(m) = mcp {
            let mcp_cmd = m.get("command").and_then(|v| v.as_str()).unwrap_or("");
            if !mcp_cmd.is_empty() && mcp_cmd != "<redacted>" {
                mcp_cmd.to_string()
            } else if let Some(p) = payload {
                let p_cmd = p.get("command").and_then(|v| v.as_str()).unwrap_or("");
                if !p_cmd.is_empty() && p_cmd != "<redacted>" {
                    p_cmd.to_string()
                } else if let Some(int) = raw_intent {
                    int.to_string()
                } else {
                    mcp_cmd.to_string()
                }
            } else if let Some(int) = raw_intent {
                int.to_string()
            } else {
                mcp_cmd.to_string()
            }
        } else if let Some(p) = payload {
            let p_cmd = p.get("command").and_then(|v| v.as_str()).unwrap_or("");
            let p_path = p.get("path").and_then(|v| v.as_str()).unwrap_or("");
            let p_query = p.get("query").and_then(|v| v.as_str()).unwrap_or("");

            if !p_cmd.is_empty() && p_cmd != "<redacted>" {
                p_cmd.to_string()
            } else if kind == "host_read_file" && !p_path.is_empty() {
                let start = p.get("start_line").and_then(|v| v.as_i64()).unwrap_or(1);
                let end = p.get("end_line").and_then(|v| v.as_i64()).unwrap_or(100);
                let rel_path = p_path.split('/').next_back().unwrap_or(p_path);
                format!("read {} (lines {}-{})", rel_path, start, end)
            } else if kind == "host_write_file" && !p_path.is_empty() {
                let rel_path = p_path.split('/').next_back().unwrap_or(p_path);
                format!("write {}", rel_path)
            } else if kind == "host_search_text" && !p_query.is_empty() {
                format!("search '{}'", p_query)
            } else if kind == "host_workspace_bind" {
                format!(
                    "bind {}",
                    p.get("label").and_then(|v| v.as_str()).unwrap_or(chat_id)
                )
            } else if kind == "host_knowledge" {
                format!(
                    "docs: {}",
                    p.get("section").and_then(|v| v.as_str()).unwrap_or("overview")
                )
            } else if let Some(int) = raw_intent {
                int.to_string()
            } else {
                p.get("summary")
                    .and_then(|v| v.as_str())
                    .unwrap_or(kind)
                    .to_string()
            }
        } else {
            kind.to_string()
        };

        let is_completed = result.is_some() || mcp.is_some();
        let is_ok = result
            .and_then(|r| r.get("ok"))
            .and_then(|v| v.as_bool())
            .or_else(|| mcp.and_then(|m| m.get("phase")).map(|p| p == "completed"))
            .unwrap_or(true);

        let exit_code = mcp
            .and_then(|m| m.get("exit_code"))
            .and_then(|v| v.as_i64())
            .or_else(|| {
                result
                    .and_then(|r| r.get("payload"))
                    .and_then(|p| p.get("exit_code"))
                    .and_then(|v| v.as_i64())
            })
            .unwrap_or(if is_ok { 0 } else { 1 }) as i32;

        let duration = mcp
            .and_then(|m| m.get("duration_ms"))
            .and_then(|v| v.as_f64())
            .map(|d| format!("{:.0}ms", d))
            .or_else(|| {
                started
                    .get("duration_ms")
                    .and_then(|v| v.as_f64())
                    .map(|d| format!("{:.0}ms", d))
            })
            .unwrap_or_else(|| "—".to_string());

        let timestamp = started
            .get("ts")
            .or_else(|| mcp.and_then(|m| m.get("timestamp")))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let time_short = if timestamp.len() >= 16 {
            timestamp[5..16].replace('T', " ")
        } else {
            "09-16 08:22".to_string()
        };

        let status = if !is_completed {
            "running".to_string()
        } else if is_ok && exit_code == 0 {
            "success".to_string()
        } else {
            "failure".to_string()
        };

        let mut cwd = mcp
            .and_then(|m| m.get("cwd"))
            .and_then(|v| v.as_str())
            .or_else(|| payload.and_then(|p| p.get("cwd")).and_then(|v| v.as_str()))
            .unwrap_or("")
            .to_string();
        if cwd.is_empty() {
            if let Some(p) = payload {
                if let Some(path_str) = p.get("path").and_then(|v| v.as_str()) {
                    cwd = path_str.to_string();
                }
            }
        }

        let mut output = mcp
            .and_then(|m| m.get("stdout"))
            .and_then(|v| v.as_str())
            .or_else(|| {
                result
                    .and_then(|r| r.get("payload"))
                    .and_then(|p| p.get("stdout"))
                    .and_then(|v| v.as_str())
            })
            .or_else(|| {
                result
                    .and_then(|r| r.get("payload"))
                    .and_then(|p| p.get("result"))
                    .and_then(|r| r.get("stdout"))
                    .and_then(|v| v.as_str())
            })
            .unwrap_or("")
            .to_string();

        let stderr = mcp
            .and_then(|m| m.get("stderr"))
            .and_then(|v| v.as_str())
            .or_else(|| {
                result
                    .and_then(|r| r.get("payload"))
                    .and_then(|p| p.get("stderr"))
                    .and_then(|v| v.as_str())
            })
            .or_else(|| {
                result
                    .and_then(|r| r.get("payload"))
                    .and_then(|p| p.get("result"))
                    .and_then(|r| r.get("stderr"))
                    .and_then(|v| v.as_str())
            })
            .unwrap_or("")
            .to_string();

        if output.is_empty() {
            if kind == "host_run_command" {
                if exit_code == 0 {
                    output = "[Lệnh thực thi thành công (Mã thoát: 0)]".to_string();
                } else {
                    output = format!("[Lệnh kết thúc với lỗi (Mã thoát: {})]", exit_code);
                }
            } else if kind == "host_read_file" {
                if let Some(p) = payload {
                    if let Some(path_str) = p.get("path").and_then(|v| v.as_str()) {
                        let candidate_paths = [
                            PathBuf::from(path_str),
                            PathBuf::from(&cwd).join(path_str),
                            paths.workspace_root.join(chat_id).join(path_str),
                            paths.repo_root.join(path_str),
                            paths
                                .workspace_root
                                .parent()
                                .unwrap_or(&paths.workspace_root)
                                .join(path_str),
                        ];
                        let mut found_content = None;
                        for cand in &candidate_paths {
                            if cand.exists() && cand.is_file() {
                                if let Ok(content) = fs::read_to_string(cand) {
                                    let start = p
                                        .get("start_line")
                                        .and_then(|v| v.as_i64())
                                        .unwrap_or(1)
                                        .max(1) as usize;
                                    let end = p
                                        .get("end_line")
                                        .and_then(|v| v.as_i64())
                                        .unwrap_or(200)
                                        .max(start as i64) as usize;
                                    let lines: Vec<&str> = content.lines().collect();
                                    let slice_end = end.min(lines.len());
                                    let slice_start = (start - 1).min(slice_end);
                                    if slice_start < slice_end {
                                        found_content =
                                            Some(lines[slice_start..slice_end].join("\n"));
                                    } else {
                                        found_content = Some(content);
                                    }
                                    break;
                                }
                            }
                        }
                        output = found_content.unwrap_or_else(|| {
                            format!(
                                "[Đọc tệp tin: {} (Dòng {}-{})]",
                                path_str,
                                p.get("start_line").and_then(|v| v.as_i64()).unwrap_or(1),
                                p.get("end_line").and_then(|v| v.as_i64()).unwrap_or(100)
                            )
                        });
                    }
                }
            } else if kind == "host_write_file" {
                if let Some(p) = payload {
                    let path_str = p.get("path").and_then(|v| v.as_str()).unwrap_or("");
                    let size = p.get("size_bytes").and_then(|v| v.as_i64()).unwrap_or(0);
                    let overwrite = p
                        .get("overwrite")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    output = format!(
                        "[Ghi tệp tin thành công]\nĐường dẫn: {}\nKích thước: {} bytes\nGhi đè: {}",
                        path_str, size, overwrite
                    );
                }
            } else if kind == "host_search_text" {
                if let Some(p) = payload {
                    let query = p.get("query").and_then(|v| v.as_str()).unwrap_or("");
                    let path_str = p.get("path").and_then(|v| v.as_str()).unwrap_or("");
                    output = format!(
                        "[Tìm kiếm văn bản trong '{}' với từ khóa '{}']",
                        path_str, query
                    );
                }
            } else if kind == "host_list_directory" {
                if let Some(p) = payload {
                    if let Some(path_str) = p.get("path").and_then(|v| v.as_str()) {
                        let path = Path::new(path_str);
                        if let Ok(entries) = fs::read_dir(path) {
                            let names: Vec<String> = entries
                                .filter_map(|e| {
                                    e.ok().and_then(|de| de.file_name().into_string().ok())
                                })
                                .take(150)
                                .collect();
                            if !names.is_empty() {
                                output = names.join("\n");
                            }
                        }
                        if output.is_empty() {
                            output = format!("[Liệt kê thư mục: {}]", path_str);
                        }
                    }
                }
            } else if kind == "host_workspace_bind" {
                output = format!("[Khởi tạo và kết nối không gian làm việc: {}]", chat_id);
            } else if kind == "host_knowledge" {
                if let Some(p) = payload {
                    let section = p.get("section").and_then(|v| v.as_str()).unwrap_or("");
                    output = format!("[Tra cứu tài liệu hệ thống: {}]", section);
                }
            } else if let Some(p) = payload {
                output = format!(
                    "[Thực thi {}]\n{}",
                    kind,
                    serde_json::to_string_pretty(p).unwrap_or_default()
                );
            }
        }

        let raw_json = if let Some(m) = mcp {
            serde_json::to_string_pretty(&m).unwrap_or_default()
        } else {
            let mut combo = serde_json::Map::new();
            combo.insert("started".to_string(), started.clone());
            if let Some(res) = result {
                combo.insert("result".to_string(), (*res).clone());
            }
            serde_json::to_string_pretty(&serde_json::Value::Object(combo)).unwrap_or_default()
        };

        let sanitized_cmd = sanitize_honeypot_text(&cmd);
        let final_intent = intent_note.filter(|int| int != &sanitized_cmd);

        let cmd_item = CommandItem {
            id: op_id.to_string(),
            tool: kind.to_string(),
            cmd: sanitized_cmd,
            intent: final_intent,
            exit_code,
            duration,
            timestamp,
            time_short,
            status,
            is_latest: false,
            output: sanitize_honeypot_text(&output),
            stderr: sanitize_honeypot_text(&stderr),
            cwd,
            raw_json,
        };

        // Persist command to SQLite if provided
        if let Some(database) = db {
            let _ = database.upsert_command(chat_id, &cmd_item);
        }

        commands.push(cmd_item);
    }

    // 4. MCP fallback records
    for m in mcp_fallback_records {
        let op_id = m.get("operation_id").and_then(|v| v.as_str()).unwrap_or("");
        if !op_id.is_empty() && started_ops.contains_key(op_id) {
            continue;
        }
        let item_id = if !op_id.is_empty() {
            op_id.to_string()
        } else {
            let ts = m.get("timestamp").and_then(|v| v.as_str()).unwrap_or("");
            let raw_c = m.get("command").and_then(|v| v.as_str()).unwrap_or("");
            format!("mcp_{}_{}", ts, raw_c)
        };
        let tool = m
            .get("tool")
            .and_then(|v| v.as_str())
            .unwrap_or("host_run_command")
            .to_string();
        let raw_cmd = m.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let cmd = sanitize_honeypot_text(&raw_cmd);
        let exit_code = m.get("exit_code").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
        let duration = m
            .get("duration_ms")
            .and_then(|v| v.as_f64())
            .map(|d| format!("{:.0}ms", d))
            .unwrap_or_else(|| "14ms".to_string());
        let timestamp = m.get("timestamp").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let time_short = if timestamp.len() >= 16 {
            timestamp[5..16].replace('T', " ")
        } else {
            "09-16 08:22".to_string()
        };
        let status = if exit_code == 0 {
            "success".to_string()
        } else {
            "failure".to_string()
        };
        let output = sanitize_honeypot_text(m.get("stdout").and_then(|v| v.as_str()).unwrap_or(""));
        let stderr = sanitize_honeypot_text(m.get("stderr").and_then(|v| v.as_str()).unwrap_or(""));
        let cwd = m.get("cwd").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let raw_json = serde_json::to_string_pretty(&m).unwrap_or_default();

        let cmd_item = CommandItem {
            id: item_id,
            tool,
            cmd,
            intent: None,
            exit_code,
            duration,
            timestamp,
            time_short,
            status,
            is_latest: false,
            output,
            stderr,
            cwd,
            raw_json,
        };

        if let Some(database) = db {
            let _ = database.upsert_command(chat_id, &cmd_item);
        }

        commands.push(cmd_item);
    }

    commands.reverse();
    if let Some(first) = commands.first_mut() {
        first.is_latest = true;
    }
    commands
}

pub fn read_system_logs(paths: &AppPaths, db: Option<&Database>) -> Vec<LogItem> {
    let mut logs = Vec::new();
    let log_path = if paths.gateway_log.exists() {
        &paths.gateway_log
    } else {
        &paths.server_log
    };
    let mut lines = read_last_lines(log_path, 800);
    lines.reverse();

    let mut healthz_count = 0;

    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let json_val = if let Some((_, json_str)) = trimmed.split_once("AUDIT_EVENT: ") {
            serde_json::from_str::<serde_json::Value>(json_str.trim()).ok()
        } else if trimmed.starts_with('{') && trimmed.ends_with('}') {
            serde_json::from_str::<serde_json::Value>(trimmed).ok()
        } else {
            None
        };

        if let Some(val) = json_val {
            let details = val.get("details");

            let tool_opt = details.and_then(|d| d.get("tool")).and_then(|v| v.as_str());
            let path_opt = details.and_then(|d| d.get("path")).and_then(|v| v.as_str());
            let method_opt = details.and_then(|d| d.get("method")).and_then(|v| v.as_str());
            let status_code = details
                .and_then(|d| d.get("status"))
                .and_then(|v| v.as_i64())
                .unwrap_or(200);
            let has_error = details
                .and_then(|d| d.get("error"))
                .and_then(|v| v.as_bool())
                .unwrap_or(false);

            let is_healthz = path_opt.map(|p| p.contains("healthz")).unwrap_or(false)
                || method_opt.map(|m| m.contains("healthz")).unwrap_or(false);

            if is_healthz {
                healthz_count += 1;
                if healthz_count > 10 {
                    continue;
                }
            }

            let id = val
                .get("event_id")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
                .unwrap_or_else(|| format!("evt-{}", i + 1));

            let event_type = val
                .get("event_type")
                .or_else(|| val.get("type"))
                .and_then(|v| v.as_str())
                .unwrap_or("AUDIT_EVENT");

            let (cat, action) = if let Some(tool) = tool_opt {
                if tool.contains("file") {
                    ("file".to_string(), tool.replace("host_", ""))
                } else if tool.contains("command") {
                    ("process".to_string(), "run_command".to_string())
                } else {
                    ("session".to_string(), tool.replace("host_", ""))
                }
            } else if event_type.starts_with("MCP_") {
                ("session".to_string(), method_opt.unwrap_or("mcp_message").to_string())
            } else if event_type.starts_with("HTTP_") {
                if is_healthz {
                    ("network".to_string(), "healthz".to_string())
                } else {
                    (
                        "network".to_string(),
                        format!("{} {}", method_opt.unwrap_or("HTTP"), path_opt.unwrap_or("")),
                    )
                }
            } else {
                ("runtime".to_string(), event_type.to_lowercase())
            };

            let severity = if has_error || status_code >= 500 {
                "ERROR".to_string()
            } else if status_code >= 400 {
                "WARN".to_string()
            } else {
                "INFO".to_string()
            };

            let raw_ts = val
                .get("timestamp")
                .or_else(|| val.get("ts"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            let time = if raw_ts.len() >= 19 {
                raw_ts[5..19].replace('T', " ")
            } else if !raw_ts.is_empty() {
                raw_ts.clone()
            } else {
                "09-16 19:50".to_string()
            };

            let session = details
                .and_then(|d| d.get("chat_id"))
                .or_else(|| val.get("chat_id"))
                .or_else(|| val.get("session_id"))
                .and_then(|v| v.as_str())
                .unwrap_or("system")
                .to_string();

            let msg = if let Some(tool) = tool_opt {
                let dur = details
                    .and_then(|d| d.get("duration_ms"))
                    .and_then(|v| v.as_f64())
                    .map(|d| format!(" ({:.1}ms)", d))
                    .unwrap_or_default();
                format!("{} {}{}", event_type, tool, dur)
            } else if let Some(path) = path_opt {
                let dur = details
                    .and_then(|d| d.get("duration_ms"))
                    .and_then(|v| v.as_f64())
                    .map(|d| format!(" ({:.1}ms)", d))
                    .unwrap_or_default();
                format!(
                    "{} {} -> {}{}",
                    method_opt.unwrap_or("GET"),
                    path,
                    status_code,
                    dur
                )
            } else if let Some(method) = method_opt {
                format!("{} {}", event_type, method)
            } else {
                event_type.to_string()
            };

            let log_item = LogItem {
                id,
                severity,
                cat,
                action,
                time,
                timestamp: raw_ts,
                msg,
                session,
                json: serde_json::to_string_pretty(&val).unwrap_or_default(),
            };

            if let Some(database) = db {
                let _ = database.insert_audit_log(&log_item);
            }

            logs.push(log_item);

            if logs.len() >= 150 {
                break;
            }
        }
    }

    logs
}
