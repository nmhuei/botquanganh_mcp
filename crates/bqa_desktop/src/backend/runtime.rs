use std::fs;
use std::path::Path;
use std::process::Command;
use crate::backend::paths::AppPaths;

pub fn read_runtime_status(paths: &AppPaths) -> serde_json::Value {
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
    let mcp_path = if mcp_path.starts_with('/') {
        mcp_path.to_string()
    } else {
        format!("/{}", mcp_path)
    };
    let port: u16 = env_map
        .get("MCP_PORT")
        .and_then(|p| p.parse().ok())
        .unwrap_or(18427);

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

    let ws_dir = env_map
        .get("HOST_WORKSPACE_DIR")
        .cloned()
        .unwrap_or_else(|| "/home/undertaker".to_string());
    let default_dir = env_map.get("HOST_DEFAULT_DIR").cloned().unwrap_or_default();
    let chat_root = env_map.get("HOST_CHAT_ROOT").cloned().unwrap_or_default();
    let policy = env_map
        .get("HOST_COMMAND_POLICY")
        .cloned()
        .unwrap_or_else(|| "prompt".to_string());
    let default_timeout = env_map
        .get("DEFAULT_TIMEOUT_SECONDS")
        .cloned()
        .unwrap_or_else(|| "30".to_string());
    let max_timeout = env_map
        .get("MAX_TIMEOUT_SECONDS")
        .cloned()
        .unwrap_or_else(|| "300".to_string());
    let max_output = env_map
        .get("MAX_OUTPUT_BYTES")
        .cloned()
        .unwrap_or_else(|| "1048576".to_string());
    let token = env_map.get("GATEWAY_TOKEN").cloned().unwrap_or_default();
    let require_auth = env_map
        .get("REQUIRE_AUTH")
        .map(|v| v == "true" || v == "1")
        .unwrap_or(false);
    let attribution = env_map
        .get("ATTRIBUTION_MODE")
        .cloned()
        .unwrap_or_else(|| "full".to_string());

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

pub fn execute_lifecycle_action(paths: &AppPaths, act: &str) -> (bool, &'static str) {
    match act {
        "start" => {
            let ok = Command::new("bqa")
                .arg("start")
                .current_dir(&paths.repo_root)
                .status()
                .map(|s| s.success())
                .unwrap_or(false);
            (
                ok,
                if ok {
                    "Đã khởi chạy FastMCP server"
                } else {
                    "Không thể khởi chạy FastMCP server"
                },
            )
        }
        "stop" => {
            let ok = Command::new("bqa")
                .arg("stop")
                .current_dir(&paths.repo_root)
                .status()
                .map(|s| s.success())
                .unwrap_or(false);
            (
                ok,
                if ok {
                    "Đã dừng FastMCP server"
                } else {
                    "Không thể dừng FastMCP server"
                },
            )
        }
        "restart" => {
            let ok = Command::new("bqa")
                .arg("restart")
                .current_dir(&paths.repo_root)
                .status()
                .map(|s| s.success())
                .unwrap_or(false);
            (
                ok,
                if ok {
                    "Đã khởi động lại FastMCP server"
                } else {
                    "Không thể khởi động lại FastMCP server"
                },
            )
        }
        _ => (false, "Thao tác không xác định"),
    }
}
