# 📖 BQA CLI — Complete Usage, Architecture & Debugging Reference Manual

> **Mục đích tài liệu:** Hướng dẫn toàn diện cho lập trình viên và các AI Agents tiếp theo hiểu rõ toàn bộ tập lệnh CLI `bqa`, kiến trúc Desktop UI (Rust Native), cơ chế vận hành hệ thống, và các bước debug / troubleshooting nhanh khi gặp lỗi.

---

## 📑 Mục Lục
1. [Cấu Trúc Tổng Quan & Vị Trí File](#1-cấu-trúc-tổng-quan--vị-trí-file)
2. [Bảng Tra Cứu Toàn Bộ Lệnh CLI (`bqa`)](#2-bảng-tra-cứu-toàn-bộ-lệnh-cli-bqa)
3. [Chi Tiết Từng Nhóm Lệnh & Ví Dụ Thực Tế](#3-chi-tiết-từng-nhóm-lệnh--ví-dụ-thực-tế)
4. [Kiến Trúc Giao Diện Desktop (Rust Native Studio)](#4-kiến-trúc-giao-diện-desktop-rust-native-studio)
5. [Cơ Chế Hot-Reload Biến Môi Trường (.env)](#5-cơ-chế-hot-reload-biến-môi-trường-env)
6. [Sổ Tay Debug & Xử Lý Sự Cố (Troubleshooting Runbook)](#6-sổ-tay-debug--xử-lý-sự-cố-troubleshooting-runbook)

---

## 1. Cấu Trúc Tổng Quan & Vị Trí File

```text
botquanganh_mcp/
├── bin/
│   ├── bqa                             # Entry script chính của CLI (Python launcher)
│   └── bqa-desktop                     # Symlink trực tiếp đến Rust Native App
├── app/
│   ├── cli/
│   │   ├── main.py                     # Bộ điều phối lệnh trung tâm (CLI Dispatcher)
│   │   ├── parser.py                   # Định nghĩa tham số và cờ CLI (Argparse)
│   │   ├── lifecycle.py                # Quản lý tiến trình (start, stop, restart, pid)
│   │   ├── desktop_ui.py               # Tkinter launcher và tiến trình daemon nền
│   │   └── commands/                   # Các module xử lý từng lệnh (doctor, logs, config, etc.)
│   ├── config.py                       # Nạp và validate biến môi trường .env
│   ├── server.py / mcp_server.py       # Core FastMCP SSE Server
│   └── rest_api.py                     # REST API Endpoint nội bộ (:18427)
├── crates/
│   └── bqa_desktop/                    # Source code Rust Native Studio UI
│       ├── Cargo.toml                  # Tao (Windowing) + Wry (Webview engine)
│       ├── src/main.rs                 # Rust IPC Backend & Window Lifecycle
│       └── ui/index.html               # Frontend Studio (12 Themes, Resizable Splitters)
└── target/release/bqa-desktop          # File nhị phân Release Native Linux (1.6 MB)
```

---

## 2. Bảng Tra Cứu Toàn Bộ Lệnh CLI (`bqa`)

| Nhóm chức năng | Lệnh CLI | Mô tả chi tiết |
| :--- | :--- | :--- |
| **🖥️ Giao diện UI** | `bqa ui -f` / `bqa ui --foreground` | Mở ứng dụng Rust Native Studio **gắn trực tiếp với terminal** |
| | `bqa ui -d` / `bqa ui --detach` | Mở ứng dụng Rust Native Studio **chạy ngầm độc lập (detached)** |
| | `bqa ui --classic` | Mở giao diện Tkinter cũ (dự phòng) |
| | `bqa tui` | Mở giao diện bảng điều khiển tương tác trực tiếp trong Terminal (Rich TUI) |
| **⚡ Vận hành Daemon** | `bqa start` | Khởi chạy toàn bộ hệ thống (Supervisor + Server + Tunnel) |
| | `bqa stop` | Dừng an toàn toàn bộ tiến trình hệ thống |
| | `bqa restart` | Khởi động lại MCP Server (giữ nguyên Tunnel URL & PID) |
| | `bqa status` | Hiển thị bảng trạng thái hoạt động và các tiến trình PID |
| | `bqa url` | In ra đường dẫn kết nối MCP Cloudflare Tunnel công khai |
| | `bqa server restart` | Khởi động lại riêng Bridge Socket nội bộ |
| | `bqa server status` | Kiểm tra riêng trạng thái Bridge Socket (:18427) |
| **🔍 Giám sát & Logs** | `bqa logs audit` | Xem nhật ký bảo mật và thực thi lệnh gần nhất |
| | `bqa logs launcher -n 100` | Xem 100 dòng log gần nhất của bộ khởi chạy UI |
| | `bqa logs supervisor` | Xem log của tiến trình giám sát daemon |
| | `bqa health` | Kiểm tra độ trễ và sức khỏe của REST API |
| | `bqa capabilities` | Xem danh sách toàn bộ công cụ MCP đang kích hoạt |
| | `bqa doctor` | Chạy chẩn đoán toàn diện hệ thống (tự động phát hiện lỗi) |
| **📁 Phiên & File** | `bqa chats list` | Liệt kê toàn bộ các workspace phiên chat (`cw-...`) |
| | `bqa chats sweep` | Quét và dọn dẹp các workspace phiên chat hết hạn |
| | `bqa fs ls <path>` | Duyệt file qua REST API an toàn |
| | `bqa fs cat <path>` | Đọc nội dung file qua REST API an toàn |
| | `bqa cmd run <command>` | Chạy lệnh thử nghiệm dưới chính sách bảo mật MCP |
| **⚙️ Cấu hình & Tool** | `bqa config view` | Xem cấu hình active và các biến trong `.env` |
| | `bqa config check` | Kiểm tra tính hợp lệ của file `.env` |
| | `bqa completion bash` | Tạo script tự động gợi ý lệnh tab completion cho shell |
| | `bqa version` | In phiên bản CLI và dịch vụ |

---

## 3. Chi Tiết Từng Nhóm Lệnh & Ví Dụ Thực Tế

### 3.1. Khởi chạy Giao diện Desktop (`bqa ui`)
```bash
# 1. Chạy trực tiếp và xem log trực tiếp trên terminal (Khuyên dùng khi debug):
bqa ui -f

# 2. Mở chạy ngầm để tiếp tục dùng terminal làm việc khác:
bqa ui -d

# 3. Xuất trạng thái JSON cho automation:
bqa ui --json
```

### 3.2. Quản lý Vòng Đời Dịch Vụ (`start / stop / restart / status`)
```bash
# Kiểm tra trạng thái hệ thống:
bqa status

# Khởi động lại server mà không làm rớt Cloudflare Tunnel:
bqa restart

# Lấy URL kết nối của ChatGPT / Claude:
bqa url
```

### 3.3. Xem Logs & Điều Tra Pháp Y (`bqa logs`)
```bash
# Xem 50 sự kiện audit log gần nhất:
bqa logs audit -n 50

# Theo dõi log real-time liên tục (tương đương tail -f):
bqa logs audit --follow

# Lọc log trong vòng 15 phút vừa qua:
bqa logs audit --since 15m
```

### 3.4. Chẩn đoán Tự Động (`bqa doctor`)
```bash
# Kiểm tra kết nối mạng nội bộ, quyền ghi đĩa, biến .env, và Cloudflare Tunnel:
bqa doctor

# Chỉ kiểm tra cục bộ (không ping ra ngoài internet):
bqa doctor --local-only
```

---

## 4. Kiến Trúc Giao Diện Desktop (Rust Native Studio)

- **Ngôn ngữ & Framework:** Rust (`tao` 0.31 để tạo cửa sổ native OS + `wry` 0.47 Webview).
- **Kích thước nhị phân:** Chỉ **1.6 MB** (`target/release/bqa-desktop`).
- **Giao diện người dùng:** 
  - **12 Chủ đề (Themes):** Rose Pine Moon (mặc định), Linear Studio, GitHub Dimmed, Dracula, Nord, Tokyo Night, Gruvbox, Catppuccin, Monokai, Solarized, Vercel Mono, Clean Light.
  - **3 Tab:** `Tổng quan (Overview)`, `Hoạt động (Activity)`, `Nhật ký (Logs)`.
  - **Công thái học (Ergonomics):** Thanh trượt kéo thả chia cột linh hoạt (`resizer col-resize`), nút thu gọn inline trực tiếp trên cột (`«` và `» Sessions`), không bị nút toggle thừa che mất không gian.
  - **Settings Drawer:** Trượt ra từ cạnh phải, quản lý trực tiếp các thông số `.env`.

---

## 5. Cơ Chế Hot-Reload Biến Môi Trường (.env)

Hệ thống hỗ trợ nạp lại biến môi trường tức thì (Zero-Downtime Hot Reload) mà không cần ngắt kết nối WebSocket/SSE:

```text
┌───────────────────────────┬──────────────┬───────────────────────────────────────────┐
│ Tên Biến trong .env       │ Hot Reload?  │ Hành vi khi nạp lại                       │
├───────────────────────────┼──────────────┼───────────────────────────────────────────┤
│ HOST_WORKSPACE_DIR        │ ✅ CÓ        │ Cập nhật ngay gốc bảo mật file            │
│ HOST_DEFAULT_DIR          │ ✅ CÓ        │ Đổi thư mục fallback thực thi             │
│ HOST_CHAT_ROOT            │ ✅ CÓ        │ Cập nhật đường dẫn quét sessions          │
│ HOST_COMMAND_POLICY       │ ✅ CÓ        │ Đổi chính sách chặn lệnh (guarded)        │
│ DEFAULT_TIMEOUT_SECONDS   │ ✅ CÓ        │ Áp dụng timeout mới cho lệnh tiếp theo    │
│ GATEWAY_TOKEN             │ ✅ CÓ        │ Cập nhật token kiểm tra middleware        │
│ ATTRIBUTION_MODE          │ ✅ CÓ        │ Đổi chế độ gán nhãn chat session          │
│ MCP_PORT / MCP_BIND_HOST  │ ❌ CẦN RESTART│ Yêu cầu bind lại Socket OS cổng mạng      │
└───────────────────────────┴──────────────┴───────────────────────────────────────────┘
```

---

## 6. Sổ Tay Debug & Xử Lý Sự Cố (Troubleshooting Runbook)

### ❓ Tình huống 1: Gõ `bqa ui` không mở được cửa sổ
1. Kiểm tra biến môi trường hiển thị X11/Wayland:
   ```bash
   echo $DISPLAY $WAYLAND_DISPLAY
   ```
2. Chạy ở chế độ foreground để xem trực tiếp lỗi console:
   ```bash
   bqa ui -f
   ```
3. Re-compile lại binary Rust nếu bị thiếu:
   ```bash
   cargo build --release --manifest-path crates/bqa_desktop/Cargo.toml
   ```

### ❓ Tình huống 2: Bridge Server không phản hồi (:18427)
1. Kiểm tra xem port 18427 có đang bị chiếm dụng không:
   ```bash
   ss -tulpn | grep 18427
   ```
2. Ping trực tiếp vào endpoint REST Health:
   ```bash
   curl -s http://127.0.0.1:18427/health | jq .
   ```
3. Khởi động lại bridge:
   ```bash
   bqa server restart
   ```

### ❓ Tình huống 3: Chạy Unit Tests để xác nhận toàn bộ hệ thống
```bash
# Chạy toàn bộ test suite cốt lõi:
uv run pytest tests/test_config_env_parity.py tests/test_center_services.py

# Kết quả kỳ vọng: 37 passed in < 1s
```
