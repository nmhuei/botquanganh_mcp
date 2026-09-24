use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

use crate::backend::paths::AppPaths;
use crate::db::Database;
use crate::mcp::tools::*;

pub fn get_tools_manifest() -> serde_json::Value {
    serde_json::json!({
        "tools": [
            {
                "name": "auto_download_ctf_challenge",
                "description": "Tự động tải challenge, giải nén an toàn và thiết lập cấu trúc 3 thư mục chuẩn (challenge/, script/, solver/) kèm template mã giải theo category.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": { "type": "string", "description": "Tên bài CTF (vd: ret2win, rsa_easy)" },
                        "category": { "type": "string", "enum": ["pwn", "reverse", "crypto", "web", "forensics", "misc"], "description": "Phân loại CTF" },
                        "url": { "type": "string", "description": "URL tải tệp tin bài thi (zip, tar.gz, binary)" },
                        "target": { "type": "string", "description": "Host:Port hoặc Web URL của server challenge" },
                        "description": { "type": "string", "description": "Mô tả bài toán" }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "ctf_transform",
                "description": "Bộ biến đổi dữ liệu đa năng: Base64, Hex, URL, XOR lặp khóa, ROT13.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": { "type": "string", "description": "Chuỗi đầu vào cần biến đổi" },
                        "operation": { "type": "string", "enum": ["b64encode", "b64decode", "hexencode", "hexdecode", "urlencode", "urldecode", "rot13", "xor"], "description": "Thao tác" },
                        "key": { "type": "string", "description": "Khóa giải mã nếu dùng thao tác xor" }
                    },
                    "required": ["text", "operation"]
                }
            },
            {
                "name": "ctf_pattern",
                "description": "Tạo chuỗi De Bruijn cyclic sequence hoặc tìm offset tràn bộ nhớ (tương thích pwntools cyclic).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "length": { "type": "integer", "description": "Độ dài pattern cần sinh (mặc định: 128)" },
                        "search": { "type": "string", "description": "Giá trị hex hoặc 4 ký tự cần tìm offset (vd: 0x61616164 hoặc 'daaa')" }
                    }
                }
            },
            {
                "name": "ctf_hash_tool",
                "description": "Băm offline (SHA-256) hoặc nhận diện chữ ký hash (MD5, SHA1, SHA256, NTLM, bcrypt, Argon2).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": { "type": "string", "description": "Chuỗi cần tính mã băm" },
                        "identify": { "type": "string", "description": "Chuỗi mã băm cần nhận diện chữ ký thuật toán" }
                    }
                }
            },
            {
                "name": "ctf_crypto_playbook",
                "description": "Tra cứu cẩm nang mật mã BQA Extreme Crypto Playbook và bảng ma trận vector tấn công (Attack Router Matrix). Dùng cho RSA, ECC, Lattices, PRNG, AES, Hashes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": { "type": "string", "description": "Từ khóa tìm kiếm vector (vd: wiener, biased nonce, small roots, lcg, gcm)" },
                        "section": { "type": "string", "enum": ["phases", "matrix", "rsa", "ecc", "lattice", "audit"], "description": "Tên phần cẩm nang cần đọc" }
                    }
                }
            },
            {
                "name": "host_workspace_bind",
                "description": "Khởi tạo hoặc liên kết không gian làm việc (workspace/session). Nếu label chứa 'ctf', tự động dựng harness 3 thư mục.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "label": { "type": "string", "description": "Nhãn workspace (vd: ctf_pwn_bof)" },
                        "chat_id": { "type": "string", "description": "ID phiên làm việc cụ thể nếu muốn liên kết lại" }
                    }
                }
            },
            {
                "name": "host_workspace_status",
                "description": "Tra cứu trạng thái workspace, danh sách file và 5 lệnh thực thi gần nhất từ SQLite database.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chat_id": { "type": "string", "description": "ID không gian làm việc cần tra cứu" }
                    }
                }
            },
            {
                "name": "host_run_command",
                "description": "Thực thi lệnh shell trong môi trường kiểm soát, ghi nhận kết quả và lưu vết kiểm toán vào SQLite.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": { "type": "string", "description": "Lệnh bash cần chạy" },
                        "cwd": { "type": "string", "description": "Thư mục làm việc hiện hành" },
                        "timeout_seconds": { "type": "integer", "description": "Thời gian timeout tối đa (mặc định: 30s)" }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "host_read_file",
                "description": "Đọc nội dung tệp tin an toàn kèm giới hạn dòng.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": { "type": "string", "description": "Đường dẫn tệp tin" },
                        "start_line": { "type": "integer", "description": "Dòng bắt đầu (1-indexed)" },
                        "end_line": { "type": "integer", "description": "Dòng kết thúc" }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "host_write_file",
                "description": "Ghi nội dung vào tệp tin.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": { "type": "string", "description": "Đường dẫn tệp tin" },
                        "content": { "type": "string", "description": "Nội dung cần ghi" }
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "host_save_note",
                "description": "Ghi chú thích có gắn nhãn thời gian vào notes/log.txt của workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": { "type": "string", "description": "Nội dung ghi chú" },
                        "chat_id": { "type": "string", "description": "ID workspace" }
                    },
                    "required": ["content"]
                }
            },
            {
                "name": "health_check",
                "description": "Kiểm tra trạng thái vận hành của BotQuangAnh Rust Native MCP server và SQLite database.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    })
}

pub async fn run_stdio_server(paths: Arc<AppPaths>, db: Arc<Database>) -> Result<(), Box<dyn std::error::Error>> {
    let stdin = tokio::io::stdin();
    let mut reader = BufReader::new(stdin).lines();
    let mut stdout = tokio::io::stdout();

    eprintln!("[+] BotQuangAnh Native Rust MCP Server listening on STDIO...");

    while let Ok(Some(line)) = reader.next_line().await {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let parsed: serde_json::Value = match serde_json::from_str(trimmed) {
            Ok(v) => v,
            Err(_) => continue,
        };

        let id = parsed.get("id").cloned();
        let method = parsed.get("method").and_then(|v| v.as_str()).unwrap_or("");
        let params = parsed.get("params").cloned().unwrap_or(serde_json::Value::Null);

        // Notifications without an ID need no response
        if id.is_none() {
            continue;
        }
        let req_id = id.unwrap();

        match method {
            "initialize" => {
                let resp = serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "botquanganh-mcp-rust",
                            "version": "1.0.0"
                        },
                        "instructions": "BotQuangAnh Native Rust CTF Engine with Clean Architecture, SQLite Database, and 3-folder Scaffolding."
                    }
                });
                let out = serde_json::to_string(&resp)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
            }
            "ping" => {
                let resp = serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {}
                });
                let out = serde_json::to_string(&resp)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
            }
            "tools/list" => {
                let manifest = get_tools_manifest();
                let resp = serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": manifest
                });
                let out = serde_json::to_string(&resp)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
            }
            "tools/call" => {
                let tool_name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let arguments = params.get("arguments").cloned().unwrap_or(serde_json::json!({}));

                let tool_res = match tool_name {
                    "auto_download_ctf_challenge" => {
                        handle_auto_download_ctf_challenge(&paths, &db, &arguments).await
                    }
                    "ctf_transform" => handle_ctf_transform(&arguments),
                    "ctf_pattern" => handle_ctf_pattern(&arguments),
                    "ctf_hash_tool" => handle_ctf_hash_tool(&arguments),
                    "ctf_crypto_playbook" => handle_ctf_crypto_playbook(&arguments),
                    "host_workspace_bind" => handle_host_workspace_bind(&paths, &db, &arguments),
                    "host_workspace_status" => handle_host_workspace_status(&paths, &db, &arguments),
                    "host_run_command" => handle_host_run_command(&paths, &db, &arguments).await,
                    "host_read_file" => handle_host_read_file(&paths, &arguments),
                    "host_write_file" => handle_host_write_file(&paths, &arguments),
                    "host_save_note" => handle_host_save_note(&paths, &arguments),
                    "health_check" => handle_health_check(&paths, &db),
                    _ => Err(format!("Công cụ không tồn tại: {}", tool_name)),
                };

                let resp = match tool_res {
                    Ok(val) => serde_json::json!({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": serde_json::to_string_pretty(&val).unwrap_or_default()
                                }
                            ],
                            "isError": false
                        }
                    }),
                    Err(err_msg) => serde_json::json!({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": err_msg
                                }
                            ],
                            "isError": true
                        }
                    }),
                };

                let out = serde_json::to_string(&resp)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
            }
            _ => {
                let resp = serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": format!("Method not found: {}", method)
                    }
                });
                let out = serde_json::to_string(&resp)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
            }
        }
    }

    Ok(())
}
