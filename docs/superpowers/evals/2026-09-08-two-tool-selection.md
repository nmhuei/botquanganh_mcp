# Bộ đánh giá GPT chọn tool cho đề án nâng cấp BotQuangAnh MCP

**Trạng thái:** Thiết kế bài đánh giá; chưa chạy.
**Spec:** [Đề án hai tool](../specs/2026-09-08-two-tool-upgrade-design.md).
**Mục đích:** Đo khả năng chọn tool, tham số và diễn giải kết quả từ câu hỏi tự nhiên; không thay thế test chức năng/policy.

## Cách chạy và fixture

Mỗi case chạy ba lần trong hội thoại sạch với cùng model/client, tool catalog và metadata revision. Gắn đúng kết nối MCP. Case T10–T15 và T20 dùng một workspace thử nghiệm được bind hợp lệ, có chat ID và credential được cấp riêng cho lượt chạy. Truyền credential qua ngữ cảnh tool result của binding; không đưa token thật vào tài liệu này hoặc bản ghi kết quả.

Fixture là workspace cục bộ do bộ kiểm thử quản lý: metadata hợp lệ, một journal nhỏ có operation bắt đầu chưa có terminal record, một operation đã hoàn tất và file text lành tính. Không đọc workspace của người dùng để tạo dữ liệu đánh giá. Case T14 dùng fixture quota đã biết; case T15 dùng fixture journal bị giới hạn đọc để tool công bố coverage thiếu. Chuẩn bị fixture trước lượt chấm, không tính bind/setup là call thừa.

Case T17 có chat ID nhưng không có credential và không có quyền tự tạo workspace thay thế. Case T20 đã nhận status gần đây, đầy đủ cho yêu cầu, và đã biết vị trí file README được phép đọc.

## Các tình huống

| ID | Yêu cầu tự nhiên | Hành vi kỳ vọng |
|---|---|---|
| T01 | “Giải mã Base64 `SGVsbG8=` giúp tôi.” | `ctf_transform`, `base64_decode`, input_text đúng; output Hello |
| T02 | “Chuỗi hex `48656c6c6f` này là nội dung gì?” | `ctf_transform`, `hex_decode`; không dựng Python shell |
| T03 | “Chuyển `Xin chào` thành Base64 UTF-8.” | `ctf_transform`, `base64_encode`; giữ Unicode chính xác |
| T04 | “Đổi `a b/?` sang dạng URL-encoded.” | `ctf_transform`, `url_encode` |
| T05 | “Đọc lại nội dung `a%20b%2F%3F`.” | `ctf_transform`, `url_decode`; output `a b/?` |
| T06 | “Giải ROT13: `Uryyb, Jbeyq!`.” | `ctf_transform`, `rot13`; output Hello, World! |
| T07 | “Dữ liệu nhị phân được gửi bằng Base64 `AP8=`; đổi các byte đó thành hex.” | `ctf_transform`, `hex_encode`, input_base64; output `00ff` |
| T08 | “Nén chuỗi `repeat me` thành gzip và trả dữ liệu bằng Base64.” | `ctf_transform`, `gzip_compress`; không ghi file |
| T09 | “XOR các byte được gửi bằng Base64 `AAH/` với khóa hex `0f10`.” | `ctf_transform`, `xor_hex`, key đúng; không thử thêm khóa |
| T10 | “Tôi quay lại rồi, kiểm tra workspace hiện tại trước khi tiếp tục.” | `host_workspace_status`, ID/token từ binding hợp lệ |
| T11 | “Workspace này đang dùng bao nhiêu dung lượng?” | `host_workspace_status`; báo logical usage và độ đầy đủ |
| T12 | “Trong nhật ký có thao tác nào chưa ghi kết quả cuối không?” | `host_workspace_status`; trình bày unresolved theo coverage |
| T13 | “Phiên trước bị gián đoạn; xem những việc cần kiểm tra lại.” | `host_workspace_status`; không coi pending là tiến trình chắc chắn còn chạy |
| T14 | “Còn đủ quota để thêm một file 1 MiB không?” | `host_workspace_status`; chỉ kết luận khi usage đầy đủ, quota xác định; không tự ghi file |
| T15 | “Hãy giải thích trạng thái workspace, kể cả phần nào chưa xác định được.” | `host_workspace_status`; nêu partial/consistency theo fixture, không bịa số chính xác |
| T16 | “Base64 khác mã hóa bảo mật ở điểm nào?” | Giải thích trực tiếp; không gọi hai tool mới |
| T17 | “Tôi chỉ còn chat ID, không còn token; xem nội dung và trạng thái workspace đó giúp tôi.” | Báo cần khôi phục credential; không gọi status với token đoán, không tạo workspace thay thế |
| T18 | “Quota workspace nghĩa là gì?” | Giải thích trực tiếp, không cần status |
| T19 | “Băm chuỗi hello bằng SHA-256.” | Không ép vào một operation transform không tồn tại; xử lý bằng khả năng khác phù hợp |
| T20 | “Với workspace vừa kiểm tra xong, đọc file README đã xác định.” | Dùng tool đọc file; không gọi status lặp lại vô ích |

Nhóm cần gọi gồm T01–T15 (15 case); nhóm không nên gọi hai tool mới hoặc không đủ điều kiện gồm T16–T20 (5 case). T15 đồng thời kiểm tra cách GPT diễn giải dữ liệu chưa đầy đủ.

## Thang điểm đề xuất

- Nhóm cần gọi: 45 lượt; ít nhất 43/45 chọn đúng tool và truyền arguments hợp lệ; không case nào sai cả ba lượt.
- Nhóm không nên gọi/không đủ quyền: 15/15 không gọi hai tool mới sai tình huống. T17 không được tạo credential hoặc workspace thay thế.
- T15 phải nêu dữ liệu thiếu ở cả ba lượt. T12/T13 không được khẳng định process đang chạy chỉ từ pending journal.
- T01–T09 không có shell call phụ để làm phép transform đã hỗ trợ.
- Không có credential/raw key bị ghi vào báo cáo eval; kết quả codec được đối chiếu bằng checker độc lập ở test chức năng.

## Bản ghi mỗi lượt

Ghi: `case_id`, `run_index`, model identifier/version nếu client công bố, loại client, ngày giờ, commit server, catalog hash, metadata revision, tool được chọn, tên operation, arguments-valid boolean, result-valid boolean, unnecessary-calls, outcome-explanation-valid và ghi chú lỗi đã redacted.

Không lưu toàn bộ arguments chứa credential. Không tính một tool call thất bại do server thiếu dependency là lỗi lựa chọn model; ghi riêng environment/tool-execution failure, sửa môi trường rồi chạy lại lượt đó. Không loại bỏ lượt chọn sai khỏi mẫu số.

Khi sửa metadata: thay một trường mỗi lần, refresh kết nối, mở hội thoại mới, chạy lại case ảnh hưởng cùng toàn bộ negative set. Sau bản sửa cuối, chạy đủ 60 lượt để có một kết quả release thống nhất.
