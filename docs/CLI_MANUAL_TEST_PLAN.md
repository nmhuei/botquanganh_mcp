# CLI Manual Regression Plan

## Mục tiêu

Xác minh toàn bộ logic CLI `bqa` sau khi triển khai Phase 1–5, bao gồm parser, packaging, local/public REST, filesystem, command execution, knowledge, logs, config, doctor, completion và lifecycle.

## Quy tắc an toàn

- Không chạy `bqa restart --yes` hoặc `bqa stop` trên tunnel thật.
- Full lifecycle `start/stop/restart` được kiểm tra trong repo cô lập với process giả.
- Runtime thật chỉ chạy `bqa start` ở chế độ idempotent và `bqa server restart`.
- Trước/sau `bqa server restart` phải so sánh tunnel PID và URL.
- Test file được tạo trong thư mục tạm nằm dưới repo và được dọn sau khi kết thúc.
- Không in giá trị thật của `GATEWAY_TOKEN`.

## Ma trận kiểm thử

### A. Build và packaging

1. `compileall app/cli`.
2. `bash -n bin/bqa`.
3. `pip install -e . --no-deps`.
4. `./bin/bqa version`.
5. `.venv/bin/bqa version`.
6. `bqa --help` bao phủ command tree.

### B. Parser và output

1. Global options trước subcommand.
2. Global options sau subcommand.
3. `--json` tạo JSON hợp lệ.
4. Line ranges: `N`, `N:M`, `N:`, `:M`.
5. Secret trong config bị che.
6. Exit code lỗi usage bằng `2`.

### C. Runtime status và health

1. `bqa status`.
2. `bqa status --json`.
3. `bqa url`.
4. `bqa server status`.
5. Local `bqa health`.
6. Public `bqa --public health`.
7. Capabilities đầy đủ và các filter `--tools`, `--limits`, `--host`.

### D. Filesystem REST

1. `mkdir`.
2. `write --text`.
3. `write --from`.
4. `write --stdin`.
5. `cat` toàn file.
6. `cat --lines` với đủ bốn dạng range.
7. `append --text` và `append --stdin`.
8. `replace --old/--new`.
9. `replace --old-file/--new-file`.
10. `search`.
11. `ls`.
12. `--no-overwrite` trả conflict exit code `8`.

### E. Command REST

1. `cmd check` command hợp lệ.
2. `cmd check` command bị policy chặn, exit code `5`.
3. `cmd run` thành công.
4. `cmd run` với `--check-first`.
5. `cmd run` exit khác `0`, CLI giữ nguyên exit code.
6. `cmd run` timeout, CLI trả exit code `7`.
7. stdout và stderr được tách đúng.
8. JSON envelope hợp lệ.

### F. Knowledge

1. `overview`.
2. `guide`.
3. `tools`.
4. `tools --versions`.
5. `tools --all`.
6. `search`.
7. `all`.

### G. Logs, config và diagnostics

1. Bốn log targets.
2. `--lines`.
3. `--grep`.
4. `--since`.
5. JSON logs.
6. Follow mode khởi động được và bị dừng bằng external timeout.
7. `config show/get/path/validate`.
8. Token bị che.
9. `doctor` local/public/MCP.
10. Completion cho Bash, Zsh và Fish.

### H. Lifecycle cô lập

1. `start` tạo supervisor/server/tunnel giả.
2. `start` lần hai idempotent.
3. `status` đọc đúng PID, bridge và canonical URL.
4. `server restart` đổi server PID nhưng giữ tunnel PID/URL.
5. `stop` dừng supervisor trước và dọn process.
6. `restart --yes` chạy full lifecycle và cấp URL mới trong môi trường giả.
7. `restart` không có `--yes` bị từ chối ở non-interactive mode.

### I. Runtime thật

1. `bqa start` không đổi tunnel PID/URL khi supervisor đang chạy.
2. `bqa server restart` chỉ đổi server PID.
3. Tunnel PID và URL giữ nguyên.
4. Local health, public REST và MCP initialize vẫn pass sau restart bridge.

## Tiêu chí PASS

- Toàn bộ test tự động của pytest pass.
- Script manual regression kết thúc với `ALL_CLI_MANUAL_TESTS=PASS`.
- Runtime thật giữ nguyên tunnel PID và URL.
- Không có token xuất hiện trong artifacts/log test.
- `git diff --check`, `compileall` và `bash -n` pass.
