use std::path::Path;
use std::sync::Mutex;
use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionItem {
    pub id: String,
    pub chat_id: String,
    pub label: String,
    pub ops: usize,
    pub ops_count: usize,
    pub created_at: String,
    #[serde(default)]
    pub created_ts: u64,
    pub active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandItem {
    pub id: String,
    pub tool: String,
    pub cmd: String,
    pub intent: Option<String>,
    pub exit_code: i32,
    pub duration: String,
    pub timestamp: String,
    pub time_short: String,
    pub status: String,
    pub is_latest: bool,
    pub output: String,
    pub stderr: String,
    pub cwd: String,
    pub raw_json: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogItem {
    pub id: String,
    pub severity: String,
    pub cat: String,
    pub action: String,
    pub time: String,
    pub timestamp: String,
    pub msg: String,
    pub session: String,
    pub json: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlagRecord {
    pub id: i64,
    pub chat_id: String,
    pub flag: String,
    pub category: String,
    pub verified: bool,
    pub submitted: bool,
    pub created_at: String,
    pub notes: String,
}

pub struct Database {
    conn: Mutex<Connection>,
}

impl Database {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self> {
        let p = path.as_ref();
        if let Some(parent) = p.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let conn = Connection::open(p)?;
        // Enable WAL mode for high concurrency between webview readers and daemon writers
        let _ = conn.execute_batch("PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;");
        let db = Self {
            conn: Mutex::new(conn),
        };
        db.init_tables()?;
        Ok(db)
    }

    pub fn init_tables(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                label TEXT,
                category TEXT,
                target_host TEXT,
                target_port INTEGER,
                status TEXT,
                ops_count INTEGER DEFAULT 0,
                created_at TEXT,
                created_ts INTEGER DEFAULT 0,
                updated_ts INTEGER DEFAULT 0,
                meta_json TEXT
            );

            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                tool TEXT NOT NULL,
                cmd TEXT NOT NULL,
                intent TEXT,
                exit_code INTEGER DEFAULT 0,
                duration TEXT,
                timestamp TEXT,
                time_short TEXT,
                status TEXT,
                output TEXT,
                stderr TEXT,
                cwd TEXT,
                raw_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_commands_chat_id ON commands(chat_id);

            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                flag TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT 'misc',
                verified INTEGER DEFAULT 0,
                submitted INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                notes TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_flags_chat_id ON flags(chat_id);

            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                severity TEXT NOT NULL,
                cat TEXT NOT NULL,
                action TEXT NOT NULL,
                time TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                msg TEXT NOT NULL,
                session TEXT NOT NULL,
                json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
            "#,
        )?;
        Ok(())
    }

    pub fn upsert_session(&self, item: &SessionItem, category: Option<&str>, target_host: Option<&str>, target_port: Option<i32>) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            r#"
            INSERT INTO sessions (id, chat_id, label, category, target_host, target_port, status, ops_count, created_at, created_ts, updated_ts)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, strftime('%s', 'now'))
            ON CONFLICT(id) DO UPDATE SET
                label = excluded.label,
                category = COALESCE(excluded.category, sessions.category),
                target_host = COALESCE(excluded.target_host, sessions.target_host),
                target_port = COALESCE(excluded.target_port, sessions.target_port),
                ops_count = excluded.ops_count,
                updated_ts = strftime('%s', 'now');
            "#,
            params![
                item.id,
                item.chat_id,
                item.label,
                category,
                target_host,
                target_port,
                if item.active { "active" } else { "idle" },
                item.ops_count,
                item.created_at,
                item.created_ts,
            ],
        )?;
        Ok(())
    }

    pub fn get_sessions(&self) -> Result<Vec<SessionItem>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, chat_id, label, ops_count, created_at, created_ts FROM sessions ORDER BY created_ts DESC"
        )?;
        let rows = stmt.query_map([], |row| {
            let id: String = row.get(0)?;
            let chat_id: String = row.get(1)?;
            let label: String = row.get(2)?;
            let ops_count: usize = row.get(3)?;
            let created_at: String = row.get(4)?;
            let created_ts: u64 = row.get(5)?;
            Ok(SessionItem {
                id,
                chat_id,
                label,
                ops: ops_count,
                ops_count,
                created_at,
                created_ts,
                active: false,
            })
        })?;

        let mut list = Vec::new();
        for r in rows {
            list.push(r?);
        }
        Ok(list)
    }

    pub fn upsert_command(&self, chat_id: &str, cmd: &CommandItem) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            r#"
            INSERT INTO commands (id, chat_id, tool, cmd, intent, exit_code, duration, timestamp, time_short, status, output, stderr, cwd, raw_json)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                exit_code = excluded.exit_code,
                output = excluded.output,
                stderr = excluded.stderr,
                raw_json = excluded.raw_json;
            "#,
            params![
                cmd.id,
                chat_id,
                cmd.tool,
                cmd.cmd,
                cmd.intent,
                cmd.exit_code,
                cmd.duration,
                cmd.timestamp,
                cmd.time_short,
                cmd.status,
                cmd.output,
                cmd.stderr,
                cmd.cwd,
                cmd.raw_json,
            ],
        )?;
        Ok(())
    }

    pub fn get_session_commands(&self, chat_id: &str) -> Result<Vec<CommandItem>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            r#"
            SELECT id, tool, cmd, intent, exit_code, duration, timestamp, time_short, status, output, stderr, cwd, raw_json
            FROM commands
            WHERE chat_id = ?1
            ORDER BY timestamp DESC
            "#
        )?;
        let rows = stmt.query_map(params![chat_id], |row| {
            Ok(CommandItem {
                id: row.get(0)?,
                tool: row.get(1)?,
                cmd: row.get(2)?,
                intent: row.get(3)?,
                exit_code: row.get(4)?,
                duration: row.get(5)?,
                timestamp: row.get(6)?,
                time_short: row.get(7)?,
                status: row.get(8)?,
                is_latest: false,
                output: row.get(9)?,
                stderr: row.get(10)?,
                cwd: row.get(11)?,
                raw_json: row.get(12)?,
            })
        })?;

        let mut list = Vec::new();
        for r in rows {
            list.push(r?);
        }
        if let Some(first) = list.first_mut() {
            first.is_latest = true;
        }
        Ok(list)
    }

    pub fn save_flag(&self, chat_id: &str, flag: &str, category: Option<&str>, verified: bool, notes: Option<&str>) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute(
            r#"
            INSERT INTO flags (chat_id, flag, category, verified, submitted, created_at, notes)
            VALUES (?1, ?2, ?3, ?4, 0, ?5, ?6)
            ON CONFLICT(flag) DO UPDATE SET
                verified = excluded.verified,
                notes = excluded.notes;
            "#,
            params![
                chat_id,
                flag,
                category.unwrap_or("misc"),
                if verified { 1 } else { 0 },
                now,
                notes.unwrap_or(""),
            ],
        )?;
        Ok(())
    }

    pub fn get_flags(&self, chat_id: Option<&str>) -> Result<Vec<FlagRecord>> {
        let conn = self.conn.lock().unwrap();
        let mut list = Vec::new();
        if let Some(cid) = chat_id {
            let mut stmt = conn.prepare(
                "SELECT id, chat_id, flag, category, verified, submitted, created_at, notes FROM flags WHERE chat_id = ?1 ORDER BY id DESC"
            )?;
            let rows = stmt.query_map(params![cid], |row| {
                Ok(FlagRecord {
                    id: row.get(0)?,
                    chat_id: row.get(1)?,
                    flag: row.get(2)?,
                    category: row.get(3)?,
                    verified: row.get::<_, i32>(4)? != 0,
                    submitted: row.get::<_, i32>(5)? != 0,
                    created_at: row.get(6)?,
                    notes: row.get(7)?,
                })
            })?;
            for r in rows {
                list.push(r?);
            }
        } else {
            let mut stmt = conn.prepare(
                "SELECT id, chat_id, flag, category, verified, submitted, created_at, notes FROM flags ORDER BY id DESC"
            )?;
            let rows = stmt.query_map([], |row| {
                Ok(FlagRecord {
                    id: row.get(0)?,
                    chat_id: row.get(1)?,
                    flag: row.get(2)?,
                    category: row.get(3)?,
                    verified: row.get::<_, i32>(4)? != 0,
                    submitted: row.get::<_, i32>(5)? != 0,
                    created_at: row.get(6)?,
                    notes: row.get(7)?,
                })
            })?;
            for r in rows {
                list.push(r?);
            }
        }
        Ok(list)
    }

    pub fn insert_audit_log(&self, item: &LogItem) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            r#"
            INSERT OR IGNORE INTO audit_logs (id, severity, cat, action, time, timestamp, msg, session, json)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
            "#,
            params![
                item.id,
                item.severity,
                item.cat,
                item.action,
                item.time,
                item.timestamp,
                item.msg,
                item.session,
                item.json,
            ],
        )?;
        Ok(())
    }

    pub fn get_audit_logs(&self, limit: usize) -> Result<Vec<LogItem>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, severity, cat, action, time, timestamp, msg, session, json FROM audit_logs ORDER BY timestamp DESC LIMIT ?1"
        )?;
        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(LogItem {
                id: row.get(0)?,
                severity: row.get(1)?,
                cat: row.get(2)?,
                action: row.get(3)?,
                time: row.get(4)?,
                timestamp: row.get(5)?,
                msg: row.get(6)?,
                session: row.get(7)?,
                json: row.get(8)?,
            })
        })?;
        let mut list = Vec::new();
        for r in rows {
            list.push(r?);
        }
        Ok(list)
    }
}
