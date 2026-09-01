use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::sync::{Arc, Mutex};
use tao::{
    dpi::LogicalSize,
    event::{Event, StartCause, WindowEvent},
    event_loop::{ControlFlow, EventLoop},
    window::WindowBuilder,
};
use wry::WebViewBuilder;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
struct IpcMessage {
    action: String,
    payload: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SessionItem {
    id: String,
    label: String,
    ops: usize,
    active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CommandItem {
    tool: String,
    cmd: String,
    exit_code: i32,
    duration: String,
    timestamp: String,
    time_short: String,
    is_latest: bool,
    output: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LogItem {
    id: String,
    severity: String,
    cat: String,
    action: String,
    time: String,
    msg: String,
    session: String,
    json: String,
}

#[derive(Debug, Clone)]
struct AppState {
    workspace_root: PathBuf,
    dotenv_path: PathBuf,
    log_file_path: PathBuf,
    bridge_running: bool,
}

impl AppState {
    fn new() -> Self {
        let base_dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        let home_dir = std::env::var("HOME").unwrap_or_else(|_| "/home/light".to_string());
        let ws_root = PathBuf::from(&home_dir).join("Downloads/bqa-workspaces");
        let dotenv = base_dir.join(".env");
        let log_file = base_dir.join("logs/gateway.log");

        Self {
            workspace_root: ws_root,
            dotenv_path: dotenv,
            log_file_path: log_file,
            bridge_running: true,
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
                    map.insert(k.trim().to_string(), v.trim().to_string());
                }
            }
        }
        map
    }

    fn write_dotenv(&self, updates: &HashMap<String, String>) -> Result<(), std::io::Error> {
        let mut current = self.read_dotenv();
        for (k, v) in updates {
            current.insert(k.clone(), v.clone());
        }

        let mut lines = Vec::new();
        lines.push("# === BQA BRIDGE CONFIGURATION (MANAGED BY RUST NATIVE STUDIO) ===".to_string());
        for (k, v) in &current {
            lines.push(format!("{}={}", k, v));
        }

        if let Some(parent) = self.dotenv_path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        fs::write(&self.dotenv_path, lines.join("\n") + "\n")
    }

    fn scan_sessions(&self) -> Vec<SessionItem> {
        let mut sessions = Vec::new();
        if let Ok(entries) = fs::read_dir(&self.workspace_root) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let file_name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
                    if file_name.starts_with("cw-") {
                        let journal_path = path.join("journal.jsonl");
                        let mut ops = 0;
                        if let Ok(journal) = fs::read_to_string(journal_path) {
                            ops = journal.lines().filter(|l| !l.trim().is_empty()).count();
                        }
                        sessions.push(SessionItem {
                            id: file_name.clone(),
                            label: file_name.replace("cw-", ""),
                            ops,
                            active: sessions.is_empty(),
                        });
                    }
                }
            }
        }

        if sessions.is_empty() {
            sessions.push(SessionItem {
                id: "cw-research_mcp_tunnel".to_string(),
                label: "research_mcp_tunnel".to_string(),
                ops: 5,
                active: true,
            });
            sessions.push(SessionItem {
                id: "cw-analyze_botquanganh".to_string(),
                label: "analyze_botquang...".to_string(),
                ops: 14,
                active: false,
            });
            sessions.push(SessionItem {
                id: "cw-ui_overhaul_qml".to_string(),
                label: "ui_overhaul_qml".to_string(),
                ops: 8,
                active: false,
            });
        }
        sessions
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let state = Arc::new(Mutex::new(AppState::new()));
    let event_loop = EventLoop::new();

    let window = WindowBuilder::new()
        .with_title("BQA Bridge Center — Native Studio Console")
        .with_inner_size(LogicalSize::new(1280.0, 800.0))
        .with_min_inner_size(LogicalSize::new(920.0, 580.0))
        .build(&event_loop)?;

    let html_content = include_str!("../ui/index.html");

    let state_clone = Arc::clone(&state);
    let _webview = WebViewBuilder::new()
        .with_html(html_content)
        .with_ipc_handler(move |req: wry::http::Request<String>| {
            let msg = req.body();
            if let Ok(parsed) = serde_json::from_str::<IpcMessage>(msg) {
                match parsed.action.as_str() {
                    "save_env" => {
                        if let Some(payload) = parsed.payload {
                            if let Ok(map) = serde_json::from_value::<HashMap<String, String>>(payload) {
                                let st = state_clone.lock().unwrap();
                                let _ = st.write_dotenv(&map);
                            }
                        }
                    }
                    "bridge_restart" => {
                        let _ = Command::new("pkill")
                            .args(["-f", "app.main"])
                            .spawn();
                    }
                    "bridge_stop" => {
                        let _ = Command::new("pkill")
                            .args(["-f", "app.main"])
                            .spawn();
                    }
                    "bridge_start" => {
                        let _ = Command::new("nohup")
                            .args(["uv", "run", "python", "-m", "app.main"])
                            .spawn();
                    }
                    _ => {}
                }
            }
        })
        .build(&window)?;

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::NewEvents(StartCause::Init) => {
                println!("[+] BQA Rust Native Desktop App Initialized successfully");
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
