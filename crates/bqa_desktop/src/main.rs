pub mod backend;
pub mod db;
pub mod frontend;
pub mod mcp;

use std::sync::Arc;
use crate::backend::paths::AppPaths;
use crate::db::Database;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let paths = Arc::new(AppPaths::new());
    let db = Arc::new(Database::open(&paths.db_path)?);

    if args.iter().any(|a| a == "--mcp" || a == "mcp") {
        let rt = tokio::runtime::Runtime::new()?;
        return rt.block_on(async {
            mcp::run_stdio_server(paths, db).await
        });
    }

    frontend::run_app(paths, db)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use crate::backend::ctf_harness::{scaffold_ctf_harness, HarnessConfig};
    use crate::backend::scanner::{delete_workspace_folder, read_session_commands, scan_workspaces};

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

        let cmds = read_session_commands(&paths, ws_name, None);
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

        let scanned = scan_workspaces(&temp_dir, None);
        assert_eq!(scanned.len(), 2);
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

        let pointer_path = temp_dir.join(".last_session");
        fs::write(&pointer_path, format!("{{\"chat_id\":\"{}\"}}", ws_name)).unwrap();

        let scanned = scan_workspaces(&temp_dir, None);
        assert!(scanned.iter().any(|s| s.chat_id == ws_name));

        let (ok, msg) = delete_workspace_folder(&temp_dir, ws_name);
        assert!(ok, "Delete should succeed: {}", msg);
        assert!(!target_ws.exists(), "Directory should be physically deleted");
        assert!(!pointer_path.exists(), ".last_session should be removed");

        let rescanned = scan_workspaces(&temp_dir, None);
        assert!(!rescanned.iter().any(|s| s.chat_id == ws_name));

        let (fail_ok, _) = delete_workspace_folder(&temp_dir, "../sneaky");
        assert!(!fail_ok);
        let (fail_empty, _) = delete_workspace_folder(&temp_dir, "");
        assert!(!fail_empty);

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_sqlite_database_and_ctf_harness() {
        let temp_dir = std::env::temp_dir().join(format!("bqa_test_sqlite_harness_{}", std::process::id()));
        let _ = fs::create_dir_all(&temp_dir);

        let db_file = temp_dir.join("test_studio.db");
        let db = Database::open(&db_file).expect("Failed to initialize SQLite test database");

        let mut paths = AppPaths::new();
        paths.repo_root = temp_dir.clone();
        paths.workspace_root = temp_dir.join("workspaces");
        let _ = fs::create_dir_all(&paths.workspace_root);

        // Test CTF Harness scaffolding
        let cfg = HarnessConfig {
            name: "ret2win".to_string(),
            category: "pwn".to_string(),
            target_host: Some("127.0.0.1".to_string()),
            target_port: Some(1337),
            target_url: None,
            description: Some("Simple buffer overflow challenge".to_string()),
        };

        let chal_path = scaffold_ctf_harness(&paths, Some(&db), &cfg).expect("Scaffolding should succeed");
        assert!(chal_path.is_dir());
        assert!(chal_path.join("challenge").join("NOTE.md").is_file());
        assert!(chal_path.join("script").join("analysis.md").is_file());
        assert!(chal_path.join("solver").join("solve.py").is_file());
        assert!(chal_path.join("meta.json").is_file());

        let solve_py = fs::read_to_string(chal_path.join("solver").join("solve.py")).unwrap();
        assert!(solve_py.contains("HOST = \"127.0.0.1\""));
        assert!(solve_py.contains("PORT = 1337"));

        // Verify SQLite persisted session
        let sessions = db.get_sessions().expect("Failed to query sessions from DB");
        assert_eq!(sessions.len(), 1);
        assert!(sessions[0].label.contains("ctf_pwn_ret2win"));

        // Test SQLite flags storage
        db.save_flag(&sessions[0].chat_id, "FLAG{sqlite_rust_persistence_vjp}", Some("pwn"), true, Some("verified locally"))
            .expect("Failed to save flag");

        let flags = db.get_flags(None).expect("Failed to query flags");
        assert_eq!(flags.len(), 1);
        assert_eq!(flags[0].flag, "FLAG{sqlite_rust_persistence_vjp}");
        assert!(flags[0].verified);

        let _ = fs::remove_dir_all(&temp_dir);
    }
}
