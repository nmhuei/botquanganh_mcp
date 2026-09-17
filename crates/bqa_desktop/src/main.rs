use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;

use notify::{Config, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use tao::{
    dpi::LogicalSize,
    event::{Event, StartCause, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    platform::unix::WindowExtUnix,
    window::WindowBuilder,
};
use wry::{WebViewBuilder, WebViewBuilderExtUnix};

#[derive(Debug, Clone)]
enum UserEvent {
    EvalScript(String),
}

#[derive(Debug, Serialize, Deserialize)]
struct IpcMessage {
    action: String,
    payload: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SessionItem {
    id: String,
    chat_id: String,
    label: String,
    ops: usize,
    ops_count: usize,
    created_at: String,
    #[serde(default)]
    created_ts: u64,
    active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CommandItem {
    id: String,
    tool: String,
    cmd: String,
    intent: Option<String>,
    exit_code: i32,
    duration: String,
    timestamp: String,
    time_short: String,
    status: String,
    is_latest: bool,
    output: String,
    stderr: String,
    cwd: String,
    raw_json: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LogItem {
    id: String,
    severity: String,
    cat: String,
    action: String,
    time: String,
    timestamp: String,
    msg: String,
    session: String,
    json: String,
}

#[derive(Debug, Clone)]
struct AppPaths {
    workspace_root: PathBuf,
    repo_root: PathBuf,
    dotenv_path: PathBuf,
    gateway_log: PathBuf,
    server_log: PathBuf,
}

static SAVE_ENV_SEQ: AtomicU64 = AtomicU64::new(0);

impl AppPaths {
    fn new() -> Self {
        let repo_root = std::env::var("BQA_REPO_ROOT")
            .map(PathBuf::from)
            .ok()
            .or_else(|| {
                if let Ok(cur) = std::env::current_dir() {
                    let mut probe = cur;
                    loop {
                        if probe.join("logs/mcp_command_activity.jsonl").exists() || probe.join("crates/bqa_desktop").exists() {
                            return Some(probe);
                        }
                        if !probe.pop() { break; }
                    }
                }
                None
            })
            .or_else(|| {
                if let Ok(exe) = std::env::current_exe() {
                    let mut probe = exe;
                    loop {
                        if probe.join("logs/mcp_command_activity.jsonl").exists() || probe.join("crates/bqa_desktop").exists() {
                            return Some(probe);
                        }
                        if !probe.pop() { break; }
                    }
                }
                None
            })
            .unwrap_or_else(|| {
                let default_path = PathBuf::from("/home/light/GitHub/botquanganh_mcp");
                if default_path.exists() {
                    default_path
                } else {
                    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
                }
            });
        let home_dir = std::env::var("HOME").unwrap_or_else(|_| "/home/light".to_string());
        let dotenv = repo_root.join(".env");
        let gateway_log = repo_root.join("logs/gateway.log");
        let server_log = repo_root.join("logs/server.log");

        let mut ws_root = PathBuf::from(&home_dir).join("Downloads/bqa-workspaces");

        // 1. Read HOST_CHAT_ROOT from .env if present
        if let Ok(content) = fs::read_to_string(&dotenv) {
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    continue;
                }
                if let Some((k, v)) = trimmed.split_once('=') {
                    if k.trim() == "HOST_CHAT_ROOT" {
                        let clean_v = v.trim().trim_matches('"').trim_matches('\'');
                        if !clean_v.is_empty() {
                            ws_root = if let Some(stripped) = clean_v.strip_prefix("~/") {
                                PathBuf::from(&home_dir).join(stripped)
                            } else {
                                PathBuf::from(clean_v)
                            };
                        }
                    }
                }
            }
        }

        // 2. Override from environment variables if set
        if let Ok(env_root) = std::env::var("HOST_CHAT_ROOT").or_else(|_| std::env::var("BQA_CHAT_WORKSPACES_DIR")) {
            let clean_v = env_root.trim();
            if !clean_v.is_empty() {
                ws_root = if let Some(stripped) = clean_v.strip_prefix("~/") {
                    PathBuf::from(&home_dir).join(stripped)
                } else {
                    PathBuf::from(clean_v)
                };
            }
        }

        Self {
            workspace_root: ws_root,
            repo_root,
            dotenv_path: dotenv,
            gateway_log,
            server_log,
        }
    }

    fn read_dotenv(&self) -> HashMap<String, String> {
        let mut map = HashMap::new();
        if let Ok(content) = fs::read_to_string(&self.dotenv_path) {
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    continue;
                }
                if let Some((k, v)) = trimmed.split_once('=') {
                    let clean_v = v.trim().trim_matches('"').trim_matches('\'');
                    map.insert(k.trim().to_string(), clean_v.to_string());
                }
            }
        }
        map
    }

    fn write_dotenv(&self, updates: &HashMap<String, String>) -> Result<(), std::io::Error> {
        let mut current = self.read_dotenv();
        for (k, v) in updates {
            if k.contains('\n') || k.contains('\r') || v.contains('\n') || v.contains('\r') {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "Newline not allowed in dotenv key or value",
                ));
            }
            current.insert(k.clone(), v.clone());
        }

        let mut lines = Vec::new();
        lines.push("# === BQA BRIDGE CONFIGURATION (MANAGED BY RUST NATIVE STUDIO) ===".to_string());
        for (k, v) in &current {
            let escaped_v = v.replace('\\', "\\\\").replace('"', "\\\"");
            lines.push(format!("{}=\"{}\"", k, escaped_v));
        }

        if let Some(parent) = self.dotenv_path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        let seq = SAVE_ENV_SEQ.fetch_add(1, Ordering::Relaxed);
        let tmp_path = self.dotenv_path.with_extension(format!("tmp.{}.{}", std::process::id(), seq));
        let content = lines.join("\n") + "\n";
        fs::write(&tmp_path, content)?;
        fs::rename(&tmp_path, &self.dotenv_path)?;
        Ok(())
    }
}

fn read_last_lines(path: &Path, max_lines: usize) -> Vec<String> {
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

fn scan_workspaces(root: &Path) -> Vec<SessionItem> {
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
                    let name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
                    if !name.starts_with('.') && (name.starts_with("cw-") || path.join("meta.json").exists() || path.join("journal.jsonl").exists()) {
                        let mut ops = 0;
                        let mut label = name.replace("cw-", "");
                        let mut created_at = String::new();

                        let meta_path = path.join("meta.json");
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
                            }
                        }

                        let journal_path = path.join("journal.jsonl");
                        let mut mtime = entry.metadata().and_then(|m| m.modified()).ok()
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
                                    if let Some(date) = chrono::NaiveDate::from_ymd_opt(year, month, day) {
                                        let hour = if digits.len() >= 10 { digits[8..10].parse::<u32>().unwrap_or(0) } else { 0 };
                                        let min = if digits.len() >= 12 { digits[10..12].parse::<u32>().unwrap_or(0) } else { 0 };
                                        let sec = if digits.len() >= 14 { digits[12..14].parse::<u32>().unwrap_or(0) } else { 0 };
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
                        });
                    }
                }
            }
        }
    }

    // Sort strictly by creation time descending (newest created workspace first)
    scanned_list.sort_by(|a, b| {
        b.created_ts.cmp(&a.created_ts)
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
        sessions.push(sc.item);
    }
    sessions
}

fn delete_workspace_folder(workspace_root: &Path, chat_id: &str) -> (bool, String) {
    let clean_id = chat_id.trim();
    if clean_id.is_empty() {
        return (false, "Tên workspace không được để trống".to_string());
    }
    if clean_id.contains('/') || clean_id.contains('\\') || clean_id.contains("..") || clean_id.starts_with('.') {
        return (false, "Tên workspace không hợp lệ".to_string());
    }

    let ws_dir = workspace_root.join(clean_id);
    let archive_dir = workspace_root.join(".archive").join(clean_id);
    let mut deleted_any = false;
    let mut err_msg = String::new();

    if ws_dir.is_dir() {
        match fs::remove_dir_all(&ws_dir) {
            Ok(_) => { deleted_any = true; }
            Err(e) => { err_msg = format!("Lỗi khi xóa thư mục {}: {}", ws_dir.display(), e); }
        }
    }
    if archive_dir.is_dir() {
        match fs::remove_dir_all(&archive_dir) {
            Ok(_) => { deleted_any = true; }
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
        (true, "Đã xóa vĩnh viễn không gian làm việc thành công".to_string())
    } else if err_msg.is_empty() {
        (true, "Không tìm thấy thư mục workspace trên ổ đĩa".to_string())
    } else {
        (false, err_msg)
    }
}

fn copy_to_system_clipboard(text: &str) {
    use std::io::Write;
    if let Ok(mut child) = Command::new("xclip")
        .args(["-selection", "clipboard"])
        .stdin(std::process::Stdio::piped())
        .spawn()
    {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
        return;
    }
    if let Ok(mut child) = Command::new("wl-copy")
        .stdin(std::process::Stdio::piped())
        .spawn()
    {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
        return;
    }
    if let Ok(mut child) = Command::new("xsel")
        .args(["--clipboard", "--input"])
        .stdin(std::process::Stdio::piped())
        .spawn()
    {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
    }
}

fn sanitize_honeypot_text(text: &str) -> String {
    let lower = text.to_lowercase();
    if !lower.contains("x-llm")
        && !lower.contains("honeypot")
        && !lower.contains("canary")
        && !lower.contains("honey-port")
        && !lower.contains("antigravity")
        && !lower.contains("agent:")
        && !lower.contains("agent=")
        && !lower.contains("model:")
        && !lower.contains("model=")
    {
        return text.to_string();
    }
    let mut out = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        let trimmed_lower = trimmed.to_lowercase();
        // Entire line is solely a honeypot/canary directive
        if trimmed_lower.starts_with("x-llm-")
            || trimmed_lower.starts_with("# x-llm-")
            || trimmed_lower.starts_with("// x-llm-")
            || trimmed_lower.starts_with("/* x-llm-")
            || trimmed_lower.starts_with("<!-- x-llm-")
            || trimmed_lower.starts_with("prompt-canary:")
            || trimmed_lower.starts_with("agent_name:")
        {
            continue;
        }

        // In-place inline comment / honeypot redaction
        let mut cleaned_line = line.to_string();

        // 1. Redact trailing inline comments
        for delimiter in &[" # x-llm-", " // x-llm-", " # canary", " // canary", " # honey-port", " // honey-port"] {
            if let Some(pos) = cleaned_line.to_lowercase().find(delimiter) {
                cleaned_line.truncate(pos);
            }
        }

        // 2. Redact standalone bracketed tags like [antigravity]
        if let Some(pos) = cleaned_line.to_lowercase().find("[antigravity]") {
            cleaned_line = format!("{}{}", &cleaned_line[..pos], &cleaned_line[pos + 13..]);
        }

        let final_line = cleaned_line.trim_end();
        if !final_line.is_empty() {
            out.push(final_line.to_string());
        }
    }
    out.join("\n")
}

fn read_session_commands(paths: &AppPaths, chat_id: &str) -> Vec<CommandItem> {
    let mut mcp_by_op: HashMap<String, serde_json::Value> = HashMap::new();
    let mut mcp_fallback_records: Vec<serde_json::Value> = Vec::new();

    // 1. Read MCP command activity log (real unredacted commands & real stdout/stderr)
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

    // 2. Read workspace journal (reading rotated journal.jsonl.1 first, then active journal.jsonl)
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
                    if trimmed.is_empty() { continue; }
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(trimmed) {
                        let op_id = val.get("op").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        if op_id.is_empty() { continue; }
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

        let kind = started.get("kind")
            .or_else(|| started.get("tool"))
            .and_then(|v| v.as_str())
            .unwrap_or("host_run_command");
        let payload = started.get("payload");

        // Extract intent note if present in payload
        let raw_intent = payload
            .and_then(|p| p.get("intent"))
            .and_then(|v| v.as_str())
            .map(|s| s.trim())
            .filter(|s| !s.is_empty());
        let intent_note = raw_intent.map(sanitize_honeypot_text);

        // Derive user-friendly command / action title
        // Prioritize actual unredacted shell/tool command over intent note
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
                format!("bind {}", p.get("label").and_then(|v| v.as_str()).unwrap_or(chat_id))
            } else if kind == "host_knowledge" {
                format!("docs: {}", p.get("section").and_then(|v| v.as_str()).unwrap_or("overview"))
            } else if let Some(int) = raw_intent {
                int.to_string()
            } else {
                p.get("summary").and_then(|v| v.as_str()).unwrap_or(kind).to_string()
            }
        } else {
            kind.to_string()
        };

        let is_completed = result.is_some() || mcp.is_some();
        let is_ok = result.and_then(|r| r.get("ok")).and_then(|v| v.as_bool())
            .or_else(|| mcp.and_then(|m| m.get("phase")).map(|p| p == "completed"))
            .unwrap_or(true);

        let exit_code = mcp.and_then(|m| m.get("exit_code")).and_then(|v| v.as_i64())
            .or_else(|| result.and_then(|r| r.get("payload")).and_then(|p| p.get("exit_code")).and_then(|v| v.as_i64()))
            .unwrap_or(if is_ok { 0 } else { 1 }) as i32;

        let duration = mcp.and_then(|m| m.get("duration_ms")).and_then(|v| v.as_f64())
            .map(|d| format!("{:.0}ms", d))
            .or_else(|| started.get("duration_ms").and_then(|v| v.as_f64()).map(|d| format!("{:.0}ms", d)))
            .unwrap_or_else(|| "—".to_string());

        let timestamp = started.get("ts")
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

        let mut cwd = mcp.and_then(|m| m.get("cwd")).and_then(|v| v.as_str())
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

        let mut output = mcp.and_then(|m| m.get("stdout")).and_then(|v| v.as_str())
            .or_else(|| result.and_then(|r| r.get("payload")).and_then(|p| p.get("stdout")).and_then(|v| v.as_str()))
            .or_else(|| result.and_then(|r| r.get("payload")).and_then(|p| p.get("result")).and_then(|r| r.get("stdout")).and_then(|v| v.as_str()))
            .unwrap_or("")
            .to_string();

        let stderr = mcp.and_then(|m| m.get("stderr")).and_then(|v| v.as_str())
            .or_else(|| result.and_then(|r| r.get("payload")).and_then(|p| p.get("stderr")).and_then(|v| v.as_str()))
            .or_else(|| result.and_then(|r| r.get("payload")).and_then(|p| p.get("result")).and_then(|r| r.get("stderr")).and_then(|v| v.as_str()))
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
                            paths.workspace_root.parent().unwrap_or(&paths.workspace_root).join(path_str),
                        ];
                        let mut found_content = None;
                        for cand in &candidate_paths {
                            if cand.exists() && cand.is_file() {
                                if let Ok(content) = fs::read_to_string(cand) {
                                    let start = p.get("start_line").and_then(|v| v.as_i64()).unwrap_or(1).max(1) as usize;
                                    let end = p.get("end_line").and_then(|v| v.as_i64()).unwrap_or(200).max(start as i64) as usize;
                                    let lines: Vec<&str> = content.lines().collect();
                                    let slice_end = end.min(lines.len());
                                    let slice_start = (start - 1).min(slice_end);
                                    if slice_start < slice_end {
                                        found_content = Some(lines[slice_start..slice_end].join("\n"));
                                    } else {
                                        found_content = Some(content);
                                    }
                                    break;
                                }
                            }
                        }
                        output = found_content.unwrap_or_else(|| {
                            format!("[Đọc tệp tin: {} (Dòng {}-{})]", path_str,
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
                    let overwrite = p.get("overwrite").and_then(|v| v.as_bool()).unwrap_or(false);
                    output = format!("[Ghi tệp tin thành công]\nĐường dẫn: {}\nKích thước: {} bytes\nGhi đè: {}", path_str, size, overwrite);
                }
            } else if kind == "host_search_text" {
                if let Some(p) = payload {
                    let query = p.get("query").and_then(|v| v.as_str()).unwrap_or("");
                    let path_str = p.get("path").and_then(|v| v.as_str()).unwrap_or("");
                    output = format!("[Tìm kiếm văn bản trong '{}' với từ khóa '{}']", path_str, query);
                }
            } else if kind == "host_list_directory" {
                if let Some(p) = payload {
                    if let Some(path_str) = p.get("path").and_then(|v| v.as_str()) {
                        let path = Path::new(path_str);
                        if let Ok(entries) = fs::read_dir(path) {
                            let names: Vec<String> = entries
                                .filter_map(|e| e.ok().and_then(|de| de.file_name().into_string().ok()))
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
                output = format!("[Thực thi {}]\n{}", kind, serde_json::to_string_pretty(p).unwrap_or_default());
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

        commands.push(CommandItem {
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
        });
    }

    // 4. If any completed MCP activity record was not in journal, include it
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
        let tool = m.get("tool").and_then(|v| v.as_str()).unwrap_or("host_run_command").to_string();
        let raw_cmd = m.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let cmd = sanitize_honeypot_text(&raw_cmd);
        let exit_code = m.get("exit_code").and_then(|v| v.as_i64()).unwrap_or(0) as i32;
        let duration = m.get("duration_ms").and_then(|v| v.as_f64()).map(|d| format!("{:.0}ms", d)).unwrap_or_else(|| "14ms".to_string());
        let timestamp = m.get("timestamp").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let time_short = if timestamp.len() >= 16 { timestamp[5..16].replace('T', " ") } else { "09-16 08:22".to_string() };
        let status = if exit_code == 0 { "success".to_string() } else { "failure".to_string() };
        let output = sanitize_honeypot_text(m.get("stdout").and_then(|v| v.as_str()).unwrap_or(""));
        let stderr = sanitize_honeypot_text(m.get("stderr").and_then(|v| v.as_str()).unwrap_or(""));
        let cwd = m.get("cwd").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let raw_json = serde_json::to_string_pretty(&m).unwrap_or_default();

        commands.push(CommandItem {
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
        });
    }

    commands.reverse();
    if let Some(first) = commands.first_mut() {
        first.is_latest = true;
    }
    commands
}

fn read_runtime_status(paths: &AppPaths) -> serde_json::Value {
    let mut server_running = false;
    let mut server_pid: Option<u32> = None;
    let mut tunnel_running = false;
    let mut tunnel_pid: Option<u32> = None;

    // 1. Check server PID from logs/server.pid
    let server_pid_path = paths.repo_root.join("logs/server.pid");
    if let Ok(content) = fs::read_to_string(&server_pid_path) {
        if let Ok(pid) = content.trim().parse::<u32>() {
            let proc_path = format!("/proc/{}", pid);
            if Path::new(&proc_path).exists() {
                server_running = true;
                server_pid = Some(pid);
            }
        }
    }
    if !server_running {
        if let Ok(output) = Command::new("pgrep").args(["-f", "fastmcp"]).output() {
            if output.status.success() {
                let pid_str = String::from_utf8_lossy(&output.stdout);
                if let Some(first_line) = pid_str.lines().next() {
                    if let Ok(pid) = first_line.trim().parse::<u32>() {
                        server_running = true;
                        server_pid = Some(pid);
                    }
                }
            }
        }
    }

    // 2. Check tunnel PID from logs/tunnel.pid
    let tunnel_pid_path = paths.repo_root.join("logs/tunnel.pid");
    if let Ok(content) = fs::read_to_string(&tunnel_pid_path) {
        if let Ok(pid) = content.trim().parse::<u32>() {
            let proc_path = format!("/proc/{}", pid);
            if Path::new(&proc_path).exists() {
                tunnel_running = true;
                tunnel_pid = Some(pid);
            }
        }
    }
    if !tunnel_running {
        if let Ok(output) = Command::new("pgrep").args(["-f", "cloudflared.*tunnel"]).output() {
            if output.status.success() {
                let pid_str = String::from_utf8_lossy(&output.stdout);
                if let Some(first_line) = pid_str.lines().next() {
                    if let Ok(pid) = first_line.trim().parse::<u32>() {
                        tunnel_running = true;
                        tunnel_pid = Some(pid);
                    }
                }
            }
        }
    }

    // 3. Read tunnel public URL from logs/tunnel_url.txt
    let env_map = paths.read_dotenv();
    let mcp_path = env_map.get("MCP_PATH").map(|s| s.as_str()).unwrap_or("/mcp");
    let mcp_path = if mcp_path.starts_with('/') { mcp_path.to_string() } else { format!("/{}", mcp_path) };
    let port: u16 = env_map.get("MCP_PORT").and_then(|p| p.parse().ok()).unwrap_or(18427);

    let mut raw_tunnel_base = String::new();
    let tunnel_url_path = paths.repo_root.join("logs/tunnel_url.txt");
    if let Ok(content) = fs::read_to_string(&tunnel_url_path) {
        if let Some(first_line) = content.lines().next() {
            let trimmed = first_line.trim().trim_end_matches('/');
            if trimmed.starts_with("https://") || trimmed.starts_with("http://") {
                raw_tunnel_base = trimmed.to_string();
            }
        }
    }

    let tunnel_url = if !raw_tunnel_base.is_empty() {
        format!("{}{}", raw_tunnel_base, mcp_path)
    } else {
        format!("http://127.0.0.1:{}{}", port, mcp_path)
    };

    let ws_dir = env_map.get("HOST_WORKSPACE_DIR").cloned().unwrap_or_else(|| "/home/light".to_string());
    let default_dir = env_map.get("HOST_DEFAULT_DIR").cloned().unwrap_or_default();
    let chat_root = env_map.get("HOST_CHAT_ROOT").cloned().unwrap_or_default();
    let policy = env_map.get("HOST_COMMAND_POLICY").cloned().unwrap_or_else(|| "prompt".to_string());
    let default_timeout = env_map.get("DEFAULT_TIMEOUT_SECONDS").cloned().unwrap_or_else(|| "30".to_string());
    let max_timeout = env_map.get("MAX_TIMEOUT_SECONDS").cloned().unwrap_or_else(|| "300".to_string());
    let max_output = env_map.get("MAX_OUTPUT_BYTES").cloned().unwrap_or_else(|| "1048576".to_string());
    let token = env_map.get("GATEWAY_TOKEN").cloned().unwrap_or_default();
    let require_auth = env_map.get("REQUIRE_AUTH").map(|v| v == "true" || v == "1").unwrap_or(false);
    let attribution = env_map.get("ATTRIBUTION_MODE").cloned().unwrap_or_else(|| "full".to_string());

    serde_json::json!({
        "ok": server_running,
        "fastmcp_running": server_running,
        "fastmcp_pid": server_pid,
        "fastmcp_port": port,
        "tunnel_running": tunnel_running,
        "tunnel_pid": tunnel_pid,
        "tunnel_url": tunnel_url,
        "raw_tunnel_base": raw_tunnel_base,
        "url": tunnel_url,
        "last_known_url": tunnel_url,
        "bridge": if server_running { "ready" } else { "stopped" },
        "server": {
            "running": server_running,
            "pid": server_pid,
            "port": port,
            "endpoint": format!("http://127.0.0.1:{}{}", port, mcp_path)
        },
        "tunnel": {
            "running": tunnel_running,
            "pid": tunnel_pid,
            "url": tunnel_url,
            "status": if tunnel_running { "active" } else { "stopped" }
        },
        "workspace_root": ws_dir,
        "default_dir": default_dir,
        "chat_root": chat_root,
        "policy": policy,
        "default_timeout": default_timeout,
        "max_timeout": max_timeout,
        "max_output_bytes": max_output,
        "gateway_token": token,
        "require_auth": require_auth,
        "attribution_mode": attribution,
        "env": env_map
    })
}

fn read_system_logs(paths: &AppPaths) -> Vec<LogItem> {
    let mut logs = Vec::new();
    let log_path = if paths.gateway_log.exists() {
        &paths.gateway_log
    } else {
        &paths.server_log
    };
    let mut lines = read_last_lines(log_path, 800);
    // Examine newest lines first
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
            let status_code = details.and_then(|d| d.get("status")).and_then(|v| v.as_i64()).unwrap_or(200);
            let has_error = details.and_then(|d| d.get("error")).and_then(|v| v.as_bool()).unwrap_or(false);

            let is_healthz = path_opt.map(|p| p.contains("healthz")).unwrap_or(false)
                || method_opt.map(|m| m.contains("healthz")).unwrap_or(false);

            if is_healthz {
                healthz_count += 1;
                if healthz_count > 10 {
                    continue;
                }
            }

            let id = val.get("event_id")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
                .unwrap_or_else(|| format!("evt-{}", i + 1));

            let event_type = val.get("event_type")
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
                    ("network".to_string(), format!("{} {}", method_opt.unwrap_or("HTTP"), path_opt.unwrap_or("")))
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

            let raw_ts = val.get("timestamp")
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

            let session = details.and_then(|d| d.get("chat_id"))
                .or_else(|| val.get("chat_id"))
                .or_else(|| val.get("session_id"))
                .and_then(|v| v.as_str())
                .unwrap_or("system")
                .to_string();

            let msg = if let Some(tool) = tool_opt {
                let dur = details.and_then(|d| d.get("duration_ms")).and_then(|v| v.as_f64())
                    .map(|d| format!(" ({:.1}ms)", d)).unwrap_or_default();
                format!("{} {}{}", event_type, tool, dur)
            } else if let Some(path) = path_opt {
                let dur = details.and_then(|d| d.get("duration_ms")).and_then(|v| v.as_f64())
                    .map(|d| format!(" ({:.1}ms)", d)).unwrap_or_default();
                format!("{} {} -> {}{}", method_opt.unwrap_or("GET"), path, status_code, dur)
            } else if let Some(method) = method_opt {
                format!("{} {}", event_type, method)
            } else {
                event_type.to_string()
            };

            logs.push(LogItem {
                id,
                severity,
                cat,
                action,
                time,
                timestamp: raw_ts,
                msg,
                session,
                json: serde_json::to_string_pretty(&val).unwrap_or_default(),
            });

            if logs.len() >= 150 {
                break;
            }
        }
    }

    logs
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(unix)]
    unsafe {
        libc::signal(libc::SIGHUP, libc::SIG_IGN);
    }

    let paths = Arc::new(AppPaths::new());
    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    // Background inotify watcher for instant live stream updates
    let proxy_watcher = proxy.clone();
    let paths_watcher = Arc::clone(&paths);
    thread::spawn(move || {
        let (tx, rx) = std::sync::mpsc::channel();
        let mut watcher = match RecommendedWatcher::new(tx, Config::default()) {
            Ok(w) => w,
            Err(_) => return,
        };

        let logs_dir = paths_watcher.repo_root.join("logs");
        let ws_dir = paths_watcher.workspace_root.clone();

        if logs_dir.exists() {
            let _ = watcher.watch(&logs_dir, RecursiveMode::NonRecursive);
        }
        if ws_dir.exists() {
            let _ = watcher.watch(&ws_dir, RecursiveMode::Recursive);
        }

        let mut last_trigger = std::time::Instant::now();
        for event in rx.into_iter().flatten() {
            if (event.kind.is_modify() || event.kind.is_create())
                && last_trigger.elapsed() >= std::time::Duration::from_millis(150)
            {
                last_trigger = std::time::Instant::now();
                let js = "if (window.__triggerFastPoll) window.__triggerFastPoll();".to_string();
                let _ = proxy_watcher.send_event(UserEvent::EvalScript(js));
            }
        }
    });

    let window = WindowBuilder::new()
        .with_title("BQA Bridge Center — Native Studio Console")
        .with_inner_size(LogicalSize::new(1280.0, 800.0))
        .with_min_inner_size(LogicalSize::new(960.0, 600.0))
        .build(&event_loop)?;

    let html_content = include_str!("../ui/index.html");

    let paths_clone = Arc::clone(&paths);
    let proxy_clone = proxy.clone();

    let enable_devtools = std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) || cfg!(debug_assertions);
    let builder = WebViewBuilder::new()
        .with_devtools(enable_devtools)
        .with_html(html_content)
        .with_ipc_handler(move |req: wry::http::Request<String>| {
            let msg = req.body();
            if let Ok(parsed) = serde_json::from_str::<IpcMessage>(msg) {
                let p = Arc::clone(&paths_clone);
                let pr = proxy_clone.clone();

                thread::spawn(move || {
                    match parsed.action.as_str() {
                        "console_log" => {
                            if let Some(msg) = parsed.payload.as_ref().and_then(|p| p.get("msg")).and_then(|m| m.as_str()) {
                                if std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) {
                                    println!("[WEBVIEW LOG] {}", msg);
                                }
                            }
                        }
                        "console_error" => {
                            if let Some(msg) = parsed.payload.as_ref().and_then(|p| p.get("msg")).and_then(|m| m.as_str()) {
                                if std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) {
                                    eprintln!("[WEBVIEW ERROR] {}", msg);
                                }
                            }
                        }
                        "get_workspaces" => {
                            let sessions = scan_workspaces(&p.workspace_root);
                            if let Ok(json) = serde_json::to_string(&sessions) {
                                let js = format!("if (window.__onWorkspacesLoaded) window.__onWorkspacesLoaded({});", json);
                                let _ = pr.send_event(UserEvent::EvalScript(js));
                            }
                        }
                        "get_session_details" => {
                            let chat_id = parsed.payload
                                .as_ref()
                                .and_then(|v| v.get("chat_id"))
                                .and_then(|v| v.as_str())
                                .unwrap_or("");
                            if !chat_id.is_empty() {
                                let commands = read_session_commands(&p, chat_id);
                                let payload = serde_json::json!({
                                    "chat_id": chat_id,
                                    "commands": commands,
                                });
                                if let Ok(json) = serde_json::to_string(&payload) {
                                    let js = format!("if (window.__onJournalLoaded) window.__onJournalLoaded({});", json);
                                    let _ = pr.send_event(UserEvent::EvalScript(js));
                                }
                            }
                        }
                        "get_runtime_status" => {
                            let status = read_runtime_status(&p);
                            if let Ok(json) = serde_json::to_string(&status) {
                                let js = format!("if (window.__onRuntimeStatusLoaded) window.__onRuntimeStatusLoaded({});", json);
                                let _ = pr.send_event(UserEvent::EvalScript(js));
                            }
                        }
                        "get_logs" => {
                            let logs = read_system_logs(&p);
                            if let Ok(json) = serde_json::to_string(&logs) {
                                let js = format!("if (window.__onLogsLoaded) window.__onLogsLoaded({});", json);
                                let _ = pr.send_event(UserEvent::EvalScript(js));
                            }
                        }
                        "lifecycle_action" => {
                            let act = parsed.payload
                                .as_ref()
                                .and_then(|v| v.get("action"))
                                .and_then(|v| v.as_str())
                                .unwrap_or("");
                            let (success, msg) = match act {
                                "start" => {
                                    let ok = Command::new("bqa")
                                        .arg("start")
                                        .current_dir(&p.repo_root)
                                        .status()
                                        .map(|s| s.success())
                                        .unwrap_or(false);
                                    (ok, if ok { "Đã khởi chạy FastMCP server" } else { "Không thể khởi chạy FastMCP server" })
                                }
                                "stop" => {
                                    let ok = Command::new("bqa")
                                        .arg("stop")
                                        .current_dir(&p.repo_root)
                                        .status()
                                        .map(|s| s.success())
                                        .unwrap_or(false);
                                    (ok, if ok { "Đã dừng FastMCP server" } else { "Không thể dừng FastMCP server" })
                                }
                                "restart" => {
                                    let ok = Command::new("bqa")
                                        .arg("restart")
                                        .current_dir(&p.repo_root)
                                        .status()
                                        .map(|s| s.success())
                                        .unwrap_or(false);
                                    (ok, if ok { "Đã khởi động lại FastMCP server" } else { "Không thể khởi động lại FastMCP server" })
                                }
                                _ => (false, "Thao tác không xác định"),
                            };
                            let js = format!(
                                "if (window.__onLifecycleActionFinished) window.__onLifecycleActionFinished('{}', {}, '{}');",
                                act, success, msg
                            );
                            let _ = pr.send_event(UserEvent::EvalScript(js));
                        }
                        "copy_to_clipboard" => {
                            let text = parsed.payload
                                .as_ref()
                                .and_then(|v| v.get("text"))
                                .and_then(|v| v.as_str())
                                .unwrap_or("");
                            if !text.is_empty() {
                                copy_to_system_clipboard(text);
                            }
                        }
                        "save_env" => {
                            if let Some(payload) = parsed.payload {
                                if let Ok(map) = serde_json::from_value::<HashMap<String, String>>(payload) {
                                    let res = p.write_dotenv(&map);
                                    let (ok, msg) = match res {
                                        Ok(_) => (true, "Đã cập nhật .env thành công (khởi động lại server để áp dụng)".to_string()),
                                        Err(err) => (false, format!("Lỗi khi lưu .env: {}", err)),
                                    };
                                    let js = format!("if (window.__onEnvSaved) window.__onEnvSaved({}, '{}');", ok, msg.replace('\'', "\\'"));
                                    let _ = pr.send_event(UserEvent::EvalScript(js));
                                }
                            }
                        }
                        "delete_workspace" => {
                            let chat_id = parsed.payload
                                .as_ref()
                                .and_then(|v| v.get("chat_id"))
                                .and_then(|v| v.as_str())
                                .unwrap_or("");
                            let (ok, msg) = delete_workspace_folder(&p.workspace_root, chat_id);
                            let js_res = format!(
                                "if (window.__onWorkspaceDeleted) window.__onWorkspaceDeleted({}, '{}', '{}');",
                                ok,
                                chat_id.replace('\'', "\\'"),
                                msg.replace('\'', "\\'")
                            );
                            let _ = pr.send_event(UserEvent::EvalScript(js_res));

                            let sessions = scan_workspaces(&p.workspace_root);
                            if let Ok(json) = serde_json::to_string(&sessions) {
                                let js = format!("if (window.__onWorkspacesLoaded) window.__onWorkspacesLoaded({});", json);
                                let _ = pr.send_event(UserEvent::EvalScript(js));
                            }
                        }
                        _ => {}
                    }
                });
            }
        });

    let vbox = window.default_vbox().expect("Failed to get default vbox container on Linux GTK");
    let webview = builder.build_gtk(vbox)?;

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::NewEvents(StartCause::Init) => {
                if std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) {
                    println!("[+] BQA Rust Native Desktop App Initialized successfully");
                }
            }
            Event::UserEvent(UserEvent::EvalScript(script)) => {
                let _ = webview.evaluate_script(&script);
            }
            Event::WindowEvent {
                event: WindowEvent::CloseRequested,
                ..
            } => {
                *control_flow = ControlFlow::Exit;
            }
            _ => (),
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_session_commands_and_intent() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_read_cmds_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let ws_name = "cw-20260917-test-session";
        let target_ws = temp_dir.join("workspaces").join(ws_name);
        fs::create_dir_all(&target_ws).unwrap();

        let journal_data = r#"{"op":"op-67782c99","type":"op_started","tool":"host_run_command","payload":{"command":"for u in supervisor; do echo $u; done","intent":"Test the enumerated usernames"}}
{"op":"op-67782c99","type":"op_result","ok":true,"payload":{"exit_code":0,"stdout":"supervisor\n"}}
"#;
        fs::write(target_ws.join("journal.jsonl"), journal_data).unwrap();

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");

        let cmds = read_session_commands(&paths, ws_name);
        assert_eq!(cmds.len(), 1);
        let item = &cmds[0];
        assert_eq!(item.id, "op-67782c99");
        assert!(item.cmd.contains("for u in supervisor"));
        assert_eq!(item.intent.as_deref(), Some("Test the enumerated usernames"));
        assert_eq!(item.exit_code, 0);
        assert_eq!(item.status, "success");

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_workspace_creation_time_sorting() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_ws_sort_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let ws_old = temp_dir.join("cw-20260915-older-ws");
        let ws_new = temp_dir.join("cw-20260917-newer-ws");
        fs::create_dir_all(&ws_old).unwrap();
        fs::create_dir_all(&ws_new).unwrap();

        fs::write(ws_old.join("meta.json"), r#"{"created_at": "2026-09-15T10:00:00+00:00"}"#).unwrap();
        fs::write(ws_new.join("meta.json"), r#"{"created_at": "2026-09-17T12:00:00+00:00"}"#).unwrap();

        let scanned = scan_workspaces(&temp_dir);
        assert_eq!(scanned.len(), 2);
        // Newest created workspace should be first
        assert_eq!(scanned[0].chat_id, "cw-20260917-newer-ws");
        assert_eq!(scanned[1].chat_id, "cw-20260915-older-ws");
        assert!(scanned[0].created_ts > scanned[1].created_ts);

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_delete_workspace_folder() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_ws_del_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let ws_name = "cw-20260917-test-delete-subsystem";
        let target_ws = temp_dir.join(ws_name);
        fs::create_dir_all(&target_ws).unwrap();
        fs::write(target_ws.join("journal.jsonl"), "{\"op\":\"op-1\"}\n").unwrap();

        // Also test .last_session cleanup
        let pointer_path = temp_dir.join(".last_session");
        fs::write(&pointer_path, format!("{{\"chat_id\":\"{}\"}}", ws_name)).unwrap();

        let scanned = scan_workspaces(&temp_dir);
        assert!(scanned.iter().any(|s| s.chat_id == ws_name));

        let (ok, msg) = delete_workspace_folder(&temp_dir, ws_name);
        assert!(ok, "Delete should succeed: {}", msg);
        assert!(!target_ws.exists(), "Directory should be physically deleted");
        assert!(!pointer_path.exists(), ".last_session should be removed");

        let rescanned = scan_workspaces(&temp_dir);
        assert!(!rescanned.iter().any(|s| s.chat_id == ws_name));

        // Test invalid/empty/traversal
        let (fail_ok, _) = delete_workspace_folder(&temp_dir, "../sneaky");
        assert!(!fail_ok);
        let (fail_empty, _) = delete_workspace_folder(&temp_dir, "");
        assert!(!fail_empty);

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_concurrent_write_dotenv() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_dotenv_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let mut paths = AppPaths::new();
        paths.dotenv_path = temp_dir.join(".env");

        let mut handles = Vec::new();
        for i in 0..10 {
            let p = paths.clone();
            handles.push(thread::spawn(move || {
                let mut updates = HashMap::new();
                updates.insert("TEST_KEY".to_string(), format!("value_{}", i));
                updates.insert(format!("THREAD_{}", i), "1".to_string());
                p.write_dotenv(&updates)
            }));
        }

        for h in handles {
            let res = h.join().unwrap();
            assert!(res.is_ok(), "Concurrent write_dotenv failed: {:?}", res);
        }

        assert!(paths.dotenv_path.exists());
        let content = fs::read_to_string(&paths.dotenv_path).unwrap();
        assert!(content.contains("TEST_KEY="));

        let _ = fs::remove_dir_all(&temp_dir);
    }
}
