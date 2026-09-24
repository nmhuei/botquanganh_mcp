use std::collections::HashMap;
use std::sync::Arc;
use serde::{Deserialize, Serialize};
use tao::event_loop::EventLoopProxy;

use crate::backend::ctf_harness::{scaffold_ctf_harness, HarnessConfig};
use crate::backend::paths::AppPaths;
use crate::backend::runtime::{execute_lifecycle_action, read_runtime_status};
use crate::backend::sanitizer::copy_to_system_clipboard;
use crate::backend::scanner::{delete_workspace_folder, read_session_commands, read_system_logs, scan_workspaces};
use crate::db::Database;
use crate::frontend::UserEvent;

#[derive(Debug, Serialize, Deserialize)]
pub struct IpcMessage {
    pub action: String,
    pub payload: Option<serde_json::Value>,
}

pub fn handle_ipc_message(
    parsed: IpcMessage,
    paths: &Arc<AppPaths>,
    db: &Arc<Database>,
    proxy: &EventLoopProxy<UserEvent>,
) {
    let p = Arc::clone(paths);
    let database = Arc::clone(db);
    let pr = proxy.clone();

    match parsed.action.as_str() {
        "console_log" => {
            if let Some(msg) = parsed
                .payload
                .as_ref()
                .and_then(|p| p.get("msg"))
                .and_then(|m| m.as_str())
            {
                if std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) {
                    println!("[WEBVIEW LOG] {}", msg);
                }
            }
        }
        "console_error" => {
            if let Some(msg) = parsed
                .payload
                .as_ref()
                .and_then(|p| p.get("msg"))
                .and_then(|m| m.as_str())
            {
                if std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) {
                    eprintln!("[WEBVIEW ERROR] {}", msg);
                }
            }
        }
        "get_workspaces" => {
            let sessions = scan_workspaces(&p.workspace_root, Some(&database));
            if let Ok(json) = serde_json::to_string(&sessions) {
                let js = format!(
                    "if (window.__onWorkspacesLoaded) window.__onWorkspacesLoaded({});",
                    json
                );
                let _ = pr.send_event(UserEvent::EvalScript(js));
            }
        }
        "get_session_details" => {
            let chat_id = parsed
                .payload
                .as_ref()
                .and_then(|v| v.get("chat_id"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            if !chat_id.is_empty() {
                let commands = read_session_commands(&p, chat_id, Some(&database));
                let payload = serde_json::json!({
                    "chat_id": chat_id,
                    "commands": commands,
                });
                if let Ok(json) = serde_json::to_string(&payload) {
                    let js = format!(
                        "if (window.__onJournalLoaded) window.__onJournalLoaded({});",
                        json
                    );
                    let _ = pr.send_event(UserEvent::EvalScript(js));
                }
            }
        }
        "get_runtime_status" => {
            let status = read_runtime_status(&p);
            if let Ok(json) = serde_json::to_string(&status) {
                let js = format!(
                    "if (window.__onRuntimeStatusLoaded) window.__onRuntimeStatusLoaded({});",
                    json
                );
                let _ = pr.send_event(UserEvent::EvalScript(js));
            }
        }
        "get_logs" => {
            let logs = read_system_logs(&p, Some(&database));
            if let Ok(json) = serde_json::to_string(&logs) {
                let js = format!("if (window.__onLogsLoaded) window.__onLogsLoaded({});", json);
                let _ = pr.send_event(UserEvent::EvalScript(js));
            }
        }
        "lifecycle_action" => {
            let act = parsed
                .payload
                .as_ref()
                .and_then(|v| v.get("action"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let (success, msg) = execute_lifecycle_action(&p, act);
            let js = format!(
                "if (window.__onLifecycleActionFinished) window.__onLifecycleActionFinished('{}', {}, '{}');",
                act, success, msg
            );
            let _ = pr.send_event(UserEvent::EvalScript(js));
        }
        "copy_to_clipboard" => {
            let text = parsed
                .payload
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
                        Ok(_) => (
                            true,
                            "Đã cập nhật .env thành công (khởi động lại server để áp dụng)".to_string(),
                        ),
                        Err(err) => (false, format!("Lỗi khi lưu .env: {}", err)),
                    };
                    let js = format!(
                        "if (window.__onEnvSaved) window.__onEnvSaved({}, '{}');",
                        ok,
                        msg.replace('\'', "\\'")
                    );
                    let _ = pr.send_event(UserEvent::EvalScript(js));
                }
            }
        }
        "delete_workspace" => {
            let chat_id = parsed
                .payload
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

            let sessions = scan_workspaces(&p.workspace_root, Some(&database));
            if let Ok(json) = serde_json::to_string(&sessions) {
                let js = format!(
                    "if (window.__onWorkspacesLoaded) window.__onWorkspacesLoaded({});",
                    json
                );
                let _ = pr.send_event(UserEvent::EvalScript(js));
            }
        }
        "create_ctf_session" => {
            if let Some(payload) = parsed.payload {
                if let Ok(cfg) = serde_json::from_value::<HarnessConfig>(payload) {
                    match scaffold_ctf_harness(&p, Some(&database), &cfg) {
                        Ok(dir) => {
                            let js = format!(
                                "if (window.__onNotification) window.__onNotification('info', 'Đã khởi tạo CTF harness tại: {}');",
                                dir.display()
                            );
                            let _ = pr.send_event(UserEvent::EvalScript(js));

                            let sessions = scan_workspaces(&p.workspace_root, Some(&database));
                            if let Ok(json) = serde_json::to_string(&sessions) {
                                let js = format!(
                                    "if (window.__onWorkspacesLoaded) window.__onWorkspacesLoaded({});",
                                    json
                                );
                                let _ = pr.send_event(UserEvent::EvalScript(js));
                            }
                        }
                        Err(e) => {
                            let js = format!(
                                "if (window.__onNotification) window.__onNotification('error', 'Lỗi khởi tạo CTF harness: {}');",
                                e
                            );
                            let _ = pr.send_event(UserEvent::EvalScript(js));
                        }
                    }
                }
            }
        }
        "save_flag" => {
            if let Some(payload) = parsed.payload {
                let chat_id = payload.get("chat_id").and_then(|v| v.as_str()).unwrap_or("");
                let flag = payload.get("flag").and_then(|v| v.as_str()).unwrap_or("");
                let category = payload.get("category").and_then(|v| v.as_str());
                let verified = payload.get("verified").and_then(|v| v.as_bool()).unwrap_or(false);
                let notes = payload.get("notes").and_then(|v| v.as_str());

                if !flag.is_empty() {
                    let res = database.save_flag(chat_id, flag, category, verified, notes);
                    let (ok, msg) = match res {
                        Ok(_) => (true, "Đã lưu flag vào cơ sở dữ liệu SQLite thành công!"),
                        Err(_e) => (false, "Lỗi khi lưu flag vào database"),
                    };
                    let js = format!(
                        "if (window.__onNotification) window.__onNotification('{}', '{}');",
                        if ok { "info" } else { "error" },
                        msg
                    );
                    let _ = pr.send_event(UserEvent::EvalScript(js));
                }
            }
        }
        "get_flags" => {
            let chat_id = parsed
                .payload
                .as_ref()
                .and_then(|v| v.get("chat_id"))
                .and_then(|v| v.as_str());
            if let Ok(flags) = database.get_flags(chat_id) {
                if let Ok(json) = serde_json::to_string(&flags) {
                    let js = format!("if (window.__onFlagsLoaded) window.__onFlagsLoaded({});", json);
                    let _ = pr.send_event(UserEvent::EvalScript(js));
                }
            }
        }
        _ => {}
    }
}
