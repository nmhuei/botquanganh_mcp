use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct AppPaths {
    pub workspace_root: PathBuf,
    pub repo_root: PathBuf,
    pub dotenv_path: PathBuf,
    pub gateway_log: PathBuf,
    pub server_log: PathBuf,
    pub db_path: PathBuf,
}

impl AppPaths {
    pub fn new() -> Self {
        let repo_root = std::env::var("BQA_REPO_ROOT")
            .map(PathBuf::from)
            .ok()
            .or_else(|| {
                if let Ok(cur) = std::env::current_dir() {
                    let mut probe = cur;
                    loop {
                        if probe.join("logs/mcp_command_activity.jsonl").exists()
                            || probe.join("crates/bqa_desktop").exists()
                        {
                            return Some(probe);
                        }
                        if !probe.pop() {
                            break;
                        }
                    }
                }
                None
            })
            .or_else(|| {
                if let Ok(exe) = std::env::current_exe() {
                    let mut probe = exe;
                    loop {
                        if probe.join("logs/mcp_command_activity.jsonl").exists()
                            || probe.join("crates/bqa_desktop").exists()
                        {
                            return Some(probe);
                        }
                        if !probe.pop() {
                            break;
                        }
                    }
                }
                None
            })
            .unwrap_or_else(|| {
                let default_path = PathBuf::from("/home/undertaker/Downloads/bqa/botquanganh_mcp");
                if default_path.exists() {
                    default_path
                } else {
                    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
                }
            });

        let home_dir = std::env::var("HOME").unwrap_or_else(|_| "/home/undertaker".to_string());
        let dotenv = repo_root.join(".env");
        let gateway_log = repo_root.join("logs/gateway.log");
        let server_log = repo_root.join("logs/server.log");
        let db_path = repo_root.join("logs/bqa_studio.db");

        let mut ws_root = PathBuf::from(&home_dir).join("Documents/BQA");

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
        if let Ok(env_root) =
            std::env::var("HOST_CHAT_ROOT").or_else(|_| std::env::var("BQA_CHAT_WORKSPACES_DIR"))
        {
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
            db_path,
        }
    }

    pub fn read_dotenv(&self) -> HashMap<String, String> {
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

    pub fn write_dotenv(&self, updates: &HashMap<String, String>) -> Result<(), std::io::Error> {
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

        let tmp_path = self
            .dotenv_path
            .with_extension(format!("tmp.{}", std::process::id()));
        let content = lines.join("\n") + "\n";
        fs::write(&tmp_path, content)?;
        fs::rename(&tmp_path, &self.dotenv_path)?;
        Ok(())
    }
}
