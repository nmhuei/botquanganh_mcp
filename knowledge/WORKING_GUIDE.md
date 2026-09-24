# Working Guide

## Trình tự làm việc đề xuất

1. Khi sử dụng chat workspaces / `ATTRIBUTION_MODE=enforce`: Gọi `host_workspace_bind(chat_id="<id>")` để khởi tạo/khôi phục workspace trước khi gọi bất kỳ tool nào khác.
2. Gọi `host_knowledge(section="overview")` để đọc workspace, policy và danh sách tài liệu.
3. Gọi `host_knowledge(section="tools", query="<tool>")` trước khi giả định một command đã được cài.
4. Dùng `host_list_directory`, `host_read_file` và `host_search_text` để hiểu project trước khi sửa.
5. Dùng `host_check_command` cho command có tác động lớn hoặc khó đoán.
6. Sửa file bằng `host_write_file` hoặc `host_replace_in_file` khi có thể.
7. Chạy test/lint bằng `host_run_command` và báo lại bằng chứng thực tế.

## Quy tắc sửa code

- Không ghi đè thay đổi sẵn có nếu chưa kiểm tra `git status` và `git diff`.
- Ưu tiên thay đổi nhỏ, có test và có thể rollback.
- Không khẳng định đã sửa xong nếu chưa chạy kiểm tra phù hợp.
- Không ghi secret, token hoặc toàn bộ command nhạy cảm vào log/tài liệu.
- Dùng đường dẫn tương đối từ `HOST_WORKSPACE_DIR` khi có thể.

## Khi chạy command

- Đặt `cwd` đúng project.
- Dùng timeout phù hợp.
- Đọc `exit_code`, `stdout`, `stderr` và cờ `*_truncated`.
- Nếu command bị policy chặn, không cố bypass từ phía caller; thay đổi config phía server hoặc chọn cách an toàn hơn.

## Khi giải bài CTF (CTF Toolkit Playbook)

1. Tham khảo chi tiết trong `CTF_TOOLKIT_PLAYBOOK.md` (`host_knowledge(section="guide", query="CTF")`).
2. Luôn gọi `host_workspace_status` để kiểm tra tài nguyên và trạng thái phiên trước khi thao tác.
3. Luôn gọi `ctf_triage_artifact` đầu tiên để nhận diện binary/file thay vì chạy file/checksec/strings qua shell.
4. Dùng `ctf_transform` cho các phép biến đổi Base64, Hex, URL, ROT13, Gzip, Zlib, XOR lặp khóa.
5. Dùng `ctf_pattern` để tạo de Bruijn cyclic pattern và tìm offset EIP/RIP/saved frame pointer.
6. Dùng `ctf_hash_tool` để nhận diện cấu trúc hash hoặc tính toán mã băm cryptographic.
7. Tuân thủ nguyên tắc Evidence-First: Không đoán mò cờ, lưu cờ qua `host_save_note` và không bao giờ nộp cờ tự động lên scoreboard.

