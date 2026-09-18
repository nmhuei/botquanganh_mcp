# Đề án nâng cấp BotQuangAnh MCP

Ngày cập nhật: 10/09/2026. Trạng thái: đề xuất để xem xét; hai tool mới chưa được triển khai trong công việc này.

## 1. Quyết định đề xuất

Thực hiện ba giai đoạn: ổn định UI/MCP hiện có, bổ sung `ctf_transform`, sau đó bổ sung `host_workspace_status`. Phát hành từng tool riêng để dễ xác minh hiệu quả và quay lui khi có lỗi.

Mục tiêu là giảm thao tác shell lặp lại, giúp GPT hiểu trạng thái workspace khi tiếp tục công việc, đồng thời giữ UI và kết nối MCP vận hành nhất quán.

Tài liệu này tổng hợp phạm vi và tiêu chí quyết định. [Thiết kế kỹ thuật](2026-09-08-two-tool-upgrade-design.md) quy định schema, giới hạn, quyền truy cập và các file dự kiến thay đổi. [Bộ đánh giá GPT](../evals/2026-09-08-two-tool-selection.md) quy định 20 tình huống nghiệm thu.

## 2. Đánh giá nền tảng và tình trạng bằng chứng

Kiến trúc có các phần đủ rõ để mở rộng: `app/main.py` đăng ký tool tường minh; `app/tools/` cung cấp MCP adapter; engine biến đổi byte nằm tại `app/ctf/transforms.py`; workspace có metadata, journal và STATE; desktop Qt dùng status và luồng activity để hiển thị.

Điểm mạnh là có thể bổ sung wrapper cho engine đã tồn tại. Điểm cần cải thiện là thông tin tool xuất hiện ở nhiều nơi, trạng thái runtime có thể bị nhầm giữa các checkout, và status workspace cần quy định rõ quyền cùng độ đầy đủ của dữ liệu.

Trong đợt kiểm tra ngày 08/09 đã xác nhận tranh cổng giữa hai supervisor, lỗi mất environment override khi mở UI, lỗi chữ ký hàm ghi audit làm fetch thành công bị báo thất bại, và dependency Qt thiếu ở checkout chính. Một số bản sửa và kiểm tra hồi quy đã được thực hiện. Việc ổn định runtime cuối cùng bị gián đoạn; không coi các kết quả này là xác nhận hệ thống hiện tại đã hoàn tất nghiệm thu.

Ngày 10/09 repository có thêm thay đổi UI đang làm dở. Khi bắt đầu triển khai cần ghi lại revision, diff và runtime thực tế; bảo toàn thay đổi đang có. Mốc catalog 17 tool là baseline trước đây. Chỉ dùng lộ trình 17 → 18 → 19 nếu kiểm tra lại xác nhận baseline vẫn là 17; nếu catalog đã thay đổi thì dùng N → N+1 → N+2.

## 3. Giai đoạn 0: ổn định UI và MCP

Đây là điều kiện triển khai, không phải một phần việc có thể bỏ qua để thêm tool trước.

| Hạng mục | Kết quả phải chứng minh |
|---|---|
| Runtime chuẩn | CLI, UI và MCP cùng chỉ đến checkout/cấu hình đã xác định; không còn supervisor tranh cùng địa chỉ/cổng |
| Start/Restart | Không sinh server trùng, không dừng server của checkout khác; xử lý PID file thiếu hoặc cũ đúng; restart giữ URL khi tunnel còn hoạt động |
| Desktop | Mở được cửa sổ thật, chuyển trang và refresh được; language/workspace override đúng; trạng thái SSE phản ánh kết nối thực |
| MCP | `initialize`, `tools/list`, `health_check`, `get_capabilities` qua localhost và endpoint đang dùng trả kết quả hợp lệ |
| Adapter | Fetch thành công đi qua wrapper và audit vẫn thành công; kiểm tra bằng transport giả hoặc fixture cục bộ |
| Dependency | Môi trường chạy UI có Qt và dependency khớp lock; không tự xóa các package bổ sung của người dùng |
| Theo dõi sau sửa | Theo dõi 10 phút, lấy health mẫu mỗi 30 giây; không có restart ngoài dự kiến, bind error hoặc sai lệch PID giữa UI và listener |

Mười phút là cửa sổ nghiệm thu đề xuất, không phải bảo đảm độ ổn định dài hạn. Lưu thời điểm, revision, kết quả kiểm tra và giới hạn còn lại. Chỉ chuyển bước khi lỗi liên quan các luồng trên đã được xử lý hoặc có quyết định phạm vi rõ ràng từ người dùng.

## 4. Tool ưu tiên thứ nhất: `ctf_transform`

Tool thực hiện một phép biến đổi xác định trên byte/text được cung cấp: Base64, hex, URL encoding, gzip, zlib, ROT13 và XOR với khóa đã biết; tổng cộng 12 operation của engine hiện có.

**Lý do nên thêm:**

1. Engine đã có, nên phần đầu tư chủ yếu là MCP wrapper, metadata, chuẩn hóa kết quả và kiểm tra tích hợp. Chi phí và phạm vi nhỏ hơn xây một hệ thống mới.
2. Các thao tác này thường phải dựng Python hoặc shell chỉ để xử lý một chuỗi. Tool chuyên dụng giảm lỗi quoting, chọn encoding và đọc stdout.
3. Byte nhị phân được giữ nguyên qua `output_base64`; chỉ kèm text khi UTF-8 hợp lệ. GPT có kết quả có cấu trúc để sử dụng tiếp.
4. Tính đúng có thể kiểm tra bằng codec tham chiếu và round-trip, cho tiêu chí nghiệm thu rõ ràng.

Input gồm `operation`, đúng một trong `input_text`/`input_base64`, `key_hex` khi XOR và attribution theo chế độ đang dùng. Giữ giới hạn engine: input 128 KiB, output 512 KiB. Tool chỉ tính toán trên dữ liệu đầu vào; không tự đọc file, gọi mạng, chạy chương trình, đoán encoding hay thử khóa.

Ví dụ: “Giải mã Base64 SGVsbG8=” phải dẫn đến một call với `operation=base64_decode`, trả text `Hello`.

**Đo hiệu quả:** số call và shell call phụ trên các tình huống transform; tỷ lệ kết quả đúng; byte đầu ra; độ trễ. Chưa có số liệu để cam kết mức giảm token hoặc tăng tốc cụ thể.

## 5. Tool ưu tiên thứ hai: `host_workspace_status`

Tool trả snapshot chỉ đọc của một workspace được phép truy cập: identity, dung lượng/quota, mức đầy đủ của journal, operation chưa có kết quả cuối và tình trạng STATE.

**Lý do nên thêm:**

1. Khi tiếp tục một phiên gián đoạn, GPT cần biết dữ liệu hiện có trước khi hành động. Hiện thông tin này phân tán ở nhiều file và lời gọi.
2. Một kết quả có cấu trúc giảm việc suy diễn từ vài dòng log hoặc nhầm thư mục làm việc.
3. Có thể phân biệt “chưa thấy kết quả cuối trong journal” với “tiến trình đang chạy”; hai điều này không tương đương.
4. Khi phép đo dung lượng chưa đầy đủ, tool trả `complete=false` và quota còn lại chưa xác định, giúp GPT tránh đưa kết luận sai.

Input gồm `chat_id` và credential từ binding hợp lệ. Xác thực ở từng call, chỉ đọc workspace đích, không tự tạo workspace khi thiếu quyền. Không cập nhật last-activity hoặc sửa journal chỉ vì người dùng hỏi trạng thái.

Giới hạn thiết kế: tối đa 10.000 entries khi đo usage, journal tối đa 1 MiB, output JSON tối đa 32 KiB. Ngân sách đọc 500 ms là cooperative deadline, không phải hard timeout cho filesystem bị treo. Mọi phần thiếu hoặc thiếu nhất quán phải được công bố trong kết quả.

**Đo hiệu quả:** số call để trả lời câu hỏi trạng thái, độ đầy đủ của snapshot, cách GPT diễn giải pending/quota và việc giữ nguyên dữ liệu workspace.

## 6. Làm thế nào để GPT biết gọi sau khi merge?

Merge code là một bước. Để GPT sử dụng được, bản chạy phải đăng ký tool, client phải nhận metadata mới, và mô tả/schema phải giúp model chọn đúng tình huống. OpenAI khuyến nghị tên, description và parameter docs rõ ràng, cùng tập prompt trực tiếp, gián tiếp và không nên kích hoạt tool. [Nguồn: Optimize Metadata](https://developers.openai.com/plugins/guides/optimize-metadata).

Đề án yêu cầu:

1. Đăng ký wrapper trong `app/main.py`; đồng bộ `get_capabilities` và catalog test.
2. Description nêu khi dùng, khi không dùng, giới hạn và thông tin đầu vào bắt buộc.
3. Schema dùng enum cho operation, phân biệt text với byte carrier, giải thích nguồn credential.
4. Hướng dẫn server ưu tiên transform cho phép biến đổi đã hỗ trợ; dùng status khi cần tiếp tục hoặc kiểm tra workspace, không gọi lặp lại vô ích.
5. Sau cập nhật server, xác nhận `tools/list` mới. Với kết nối ChatGPT Developer mode, Refresh metadata và kiểm tra trong hội thoại mới. Plugin đã publish có quy trình cập nhật snapshot/version riêng. [Nguồn: Connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt#refresh-metadata).
6. Chạy bộ đánh giá bằng yêu cầu tự nhiên trên đúng client/model; không suy ra GPT chọn đúng từ việc Python tests pass.

Không cần huấn luyện lại model để đăng ký hai tool này. Tuy nhiên, không cam kết GPT luôn chọn đúng chỉ bằng description; kết quả lựa chọn phải được đo.

## 7. Lộ trình và tiêu chí nghiệm thu

| Giai đoạn | Deliverable | Điều kiện hoàn tất |
|---|---|---|
| 0 | Baseline UI/MCP ổn định | Toàn bộ tiêu chí vận hành ở mục 3 có bằng chứng mới |
| 1 | `ctf_transform` | Engine/wrapper/transport đúng; catalog tăng một tool; không mất byte hoặc phát sinh shell call phụ trong tập đánh giá |
| 2 | `host_workspace_status` | Quyền từng call đúng; dữ liệu không bị sửa; partial/quota/pending được diễn giải đúng |
| 3 | Tích hợp client và release | Metadata mới được nhìn thấy; eval đạt; rollback được mô tả và kiểm tra phù hợp |

Bộ eval gồm 20 tình huống × 3 lượt = 60 lượt. Mục tiêu đề xuất: ít nhất 43/45 lượt cần tool chọn đúng cùng tham số hợp lệ; 15/15 lượt không nên gọi hoặc thiếu quyền không gọi sai. Không tình huống cần tool nào được sai cả ba lượt. Đây là ngưỡng nghiệm thu, chưa phải kết quả đạt được.

Giữ tương thích các tool cũ. Mỗi giai đoạn có diff và bản phát hành riêng; nếu có regression thì quay lui phần đăng ký/wrapper/metadata của giai đoạn đó và cập nhật client tương ứng. Không xóa workspace hoặc journal để rollback.

## 8. Phạm vi và điều kiện quyết định

Chọn phương án adapter mỏng tái sử dụng engine/service hiện có. Chỉ thêm decorator sẽ thiếu contract và kiểm tra wrapper; refactor toàn hệ thống cùng lúc sẽ tăng phạm vi regression. Các thay đổi nền tảng rộng hơn được tách khỏi hai đợt tool.

Đợt này không thêm job runner, background execution, hệ thống tự thử nhiều phương án hoặc một UI mới cho từng tool. Các vấn đề quyền của tool cũ và tính bền vững journal cần được theo dõi riêng; status mới không chứng minh toàn hệ thống đã có isolation cho nhiều client không tin cậy.

Đề xuất chốt: ổn định UI/MCP trước, triển khai `ctf_transform` trước do engine đã có, sau đó `host_workspace_status` với quyền và snapshot rõ ràng. Mức tiết kiệm thao tác và chất lượng chọn tool được đo ở từng đợt; chỉ công bố kết quả đã kiểm chứng.
