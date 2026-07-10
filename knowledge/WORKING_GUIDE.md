# Working Guide

## Trình tự làm việc đề xuất

1. Gọi `host_knowledge(section="overview")` để đọc workspace, policy và danh sách tài liệu.
2. Gọi `host_knowledge(section="tools", query="<tool>")` trước khi giả định một command đã được cài.
3. Dùng `host_list_directory`, `host_read_file` và `host_search_text` để hiểu project trước khi sửa.
4. Dùng `host_check_command` cho command có tác động lớn hoặc khó đoán.
5. Sửa file bằng `host_write_file` hoặc `host_replace_in_file` khi có thể.
6. Chạy test/lint bằng `host_run_command` và báo lại bằng chứng thực tế.

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
