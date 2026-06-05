# Hướng Dẫn Cấu Hình Workspace và Thiết Lập Server MCP

Tài liệu này cung cấp hướng dẫn chi tiết về cách thiết lập thư mục làm việc (Workspace), cấu hình tham số bảo mật và vận hành hệ thống **Fallback Runner MCP**.

---

## 1. Cấu Hình Workspace (`RUNS_DIR`)

Workspace là thư mục lưu trữ toàn bộ mã nguồn solver gửi lên, kết quả đầu ra (stdout, stderr), transcript thực thi, và lịch sử chạy của container.

### Cách thiết lập:
Mở file `.env` và cấu hình biến `RUNS_DIR` trỏ về thư mục mong muốn:
```env
RUNS_DIR=/home/youruser/Workspace/agy/mcp_workspace
```
*(Nếu sử dụng đường dẫn tương đối, hệ thống sẽ tự động phân giải nó dựa trên thư mục gốc của dự án).*

### Cơ chế hoạt động & Bảo mật:
* **Tự khởi tạo**: Server tự động tạo thư mục này lúc khởi động qua hàm khởi dựng ở `app/config.py`.
* **Chống thoát vùng chạy (Path Traversal Protection)**:
  * Tất cả các file solver gửi lên được kiểm tra qua hàm `validate_relative_path` để đảm bảo chúng không dùng đường dẫn tuyệt đối hoặc chứa ký tự `..`.
  * Hàm `write_files` trong `app/file_package.py` kiểm tra đường dẫn tuyệt đối sau khi giải quyết để chắc chắn toàn bộ file chỉ nằm trong thư mục con `mcp_workspace/run_xxxx`.

---

## 2. Các Thiết Lập Quan Trọng Của Server (Trong `.env`)

Hệ thống điều khiển toàn bộ hành vi thông qua file cấu hình môi trường `.env`.

### 2.1 Cấu Hình Mạng và Địa Chỉ Kết Nối
* **`MCP_BIND_HOST`**: Địa chỉ IP mà server MCP lắng nghe (Mặc định: `0.0.0.0` để nhận kết nối từ ngoài container/tunnel).
* **`MCP_PORT`**: Cổng dịch vụ chạy local (Mặc định: `8000`).

### 2.2 Cấu Hình Mục Tiêu Cho Phép (`ALLOWED_TCP_TARGETS`)
Bảo vệ server khỏi việc bị lợi dụng để tấn công DDoS hoặc quét mạng tùy tiện.
* **Cho phép mọi mục tiêu (Wildcard)**:
  ```env
  ALLOWED_TCP_TARGETS=*
  ```
* **Chỉ cho phép các mục tiêu cụ thể (Danh sách phân tách bằng dấu phẩy)**:
  ```env
  ALLOWED_TCP_TARGETS=13.238.150.105:36970,74.113.234.79:2222,localhost:31337
  ```

### 2.3 Chặn Địa Chỉ Nội Bộ (`BLOCK_PRIVATE_IPS`)
* Ngăn chặn container kết nối tới các IP riêng tư hoặc loopback (`127.0.0.1`, `localhost`, `192.168.x.x`...) để tránh rò rỉ thông tin hạ tầng local.
* Thiết lập: `BLOCK_PRIVATE_IPS=true` (khuyên dùng).
* *Lưu ý: Nếu một mục tiêu local được ghi cụ thể trong `ALLOWED_TCP_TARGETS` (ví dụ `localhost:31337`), nó sẽ bỏ qua bộ lọc chặn này.*

### 2.4 Cài Đặt Xác Thực (Token)
* **Tắt xác thực (Hiện tại)**: Để trống hoặc bỏ qua biến `GATEWAY_TOKEN` trong `.env`. Các tool MCP của server hiện đã được lược bỏ tham số `token` để giảm thiểu sự rườm rà.
* **Bật xác thực**: Thiết lập `GATEWAY_TOKEN=your-random-token-here`.

### 2.5 Giới Hạn Tài Nguyên Docker (Docker Resource Caps)
Đảm bảo các script solver CTF chạy độc lập và không thể làm treo hoặc ngốn tài nguyên máy chủ:
* **`DOCKER_MEMORY=512m`**: Giới hạn tối đa 512MB RAM cho mỗi container chạy.
* **`DOCKER_CPUS=1`**: Giới hạn tối đa sử dụng 1 CPU Core.
* **`DOCKER_PIDS_LIMIT=128`**: Chặn đứng việc tạo quá nhiều tiến trình con (chống Fork Bomb).

---

## 3. Quản Lý Tiến Trình và Tự Động Hóa

### 3.1 Khởi động Hệ thống
Install cơ bản chỉ cài `.venv`, Python dependencies và `.env`; đủ để MCP server chạy với các tool nhẹ:
```bash
./scripts/install_basic.sh
```

Sử dụng script tích hợp tự động hóa để bật server và Cloudflare Tunnel:
```bash
./scripts/start_tunnel_server.sh
```
* **Basic mode**: Script sẽ tự động đảm bảo `.env`, `.venv` và các thư viện Python cơ bản đã có. Nó không tự build Docker runner images.
* **Advanced mode**: Muốn dùng các tool Docker runner như `run_solver_fallback`, `probe_target_from_runner`, `run_command`, chạy:
```bash
./scripts/install_advanced_tools.sh
```
Script này build các image `ctf-python-runner`, `ctf-pwn-runner`, `ctf-sage-runner`, `ctf-forensics-runner` và bật `ENABLE_ADVANCED_TOOLS=true` trong `.env`. Sau đó restart server.
* **Tunnel**: Đồng thời mở Cloudflare Tunnel và cung cấp đường dẫn endpoint `/mcp` công khai để điền trực tiếp vào ChatGPT.

### 3.2 Kiểm Tra Trạng Thái
Để xem các tiến trình đang chạy ngầm trên máy:
```bash
ps aux | grep -E 'fastmcp|cloudflared'
```

### 3.3 Chạy Bộ Test Unit
Để kiểm tra tính toàn vẹn của mã nguồn:
```bash
./scripts/test.sh
```

---

## 4. Liên Kết Với ChatGPT (Connector Settings)

1. Truy cập ChatGPT -> **Explore GPTs** -> **Develop GPTs** -> **Create a GPT** (hoặc edit Custom GPT hiện có).
2. Cuộn xuống phần **Capabilities** -> chọn **Add MCP Connector**.
3. Chọn giao thức kết nối: **Server-Sent Events (SSE)**.
4. Điền URL lấy được từ script `start_tunnel_server.sh` (ví dụ: `https://xxxx.trycloudflare.com/mcp`).
5. Hoàn tất kết nối. Ở basic mode, ChatGPT sẽ nhận các tool nhẹ như `health_check`, `get_capabilities`, workspace tools và run log tools. Sau khi bật advanced mode, các tool như `run_solver_fallback`, `probe_target_from_runner` và `run_command` sẽ xuất hiện thêm.

---

## 5. Sử Dụng CloakBrowser Cho Web Exploitation / Automation

Sau khi chạy `./scripts/install_advanced_tools.sh`, hệ thống có **CloakBrowser** (phiên bản Chromium tuỳ chỉnh chống phát hiện bot mức mã nguồn C++) cùng toàn bộ các thư viện hệ thống cần thiết (qua Playwright) trong các Docker runner images (`ctf-python-runner`, `ctf-pwn-runner`).

### Cách sử dụng trong file solver:
Khi viết script giải bài liên quan đến Web/Browser automation, hãy truyền tham số `--no-sandbox` khi khởi động browser do môi trường Docker chạy mặc định không có sandbox namespace:

```python
import cloakbrowser

# Khởi chạy trình duyệt ở chế độ headless với tham số --no-sandbox
browser = cloakbrowser.launch(
    headless=True,
    args=["--no-sandbox"]
)

page = browser.new_page()
page.goto("https://httpbin.org/ip")
print(page.content())

browser.close()
```
