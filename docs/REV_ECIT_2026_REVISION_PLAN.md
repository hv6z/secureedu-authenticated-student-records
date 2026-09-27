# Kế hoạch sửa bài SecureEdu cho REV ECIT 2026

## Ràng buộc nộp bài đã xác minh

Trang chính thức của REV-ECIT 2026 công bố hạn nộp bài ngày 30/09/2026. Hướng dẫn nộp bài yêu cầu toàn bộ bài viết bằng tiếng Việt, theo định dạng IEEE trên giấy A4 và không quá 6 trang. Bài sai định dạng có thể không được gửi phản biện.

Nguồn:

- https://rev-ecit.vn/vi
- https://rev-ecit.vn/en/content/huong-dan-nop-bai

## Kết luận kỹ thuật từ phản biện FAIR

Phản biện đúng khi chỉ ra rằng hash chain SHA-256 không khóa không cung cấp tamper evidence trước `A_DB`, vì kẻ tấn công biết thuật toán có thể sửa dữ liệu và tính lại toàn bộ chuỗi. Kết quả mutation cũ chỉ chứng minh phát hiện lỗi không nhất quán, không chứng minh chống kẻ tấn công thích nghi.

Vì vậy, bản REV-ECIT không được chỉ sửa cách diễn đạt. Thiết kế, threat model và thực nghiệm đều phải thay đổi đồng thời.

## Ma trận hành động

| Góp ý FAIR | Thay đổi bắt buộc | Tiêu chí hoàn thành |
|---|---|---|
| DB writer có thể rehash | HMAC-SHA-256 trên từng block với khóa audit tách miền | Modify-and-rehash làm verifier từ chối vì block MAC sai |
| Rollback và suffix truncation | Checkpoint head có HMAC nằm ngoài SQLite | Database cũ hơn hoặc bị cắt không khớp checkpoint |
| Mutation 360/360 chưa có kẻ tấn công thích nghi | Tách mutation không nhất quán và adaptive DB writer | Có dữ liệu thô cho 13 trường hợp, gồm 7 chiến lược thích nghi |
| Không có baseline | Thêm baseline độc lập và ma trận định tính | Cùng workload, storage, môi trường và số lần lặp; nêu rõ chức năng không tương đương |
| tmpfs không thực tế | Chạy kết quả chính trên filesystem lưu trữ bền vững | tmpfs chỉ là sensitivity analysis, không phải số chính |
| Chưa có tải nhiều writer | Đo contention và tỷ lệ lỗi/throughput theo số writer | Ít nhất 1, 2, 4 và 8 writer; báo p50/p95 và retry/failure |
| Tính mới khoa học thấp | Định vị đóng góp ở threat-model-driven composition và attack-driven evaluation | Không tuyên bố primitive mới; so sánh trực tiếp với authenticated logging và transparency log |

## Thiết kế sửa đổi đã triển khai

1. `K_audit` được dẫn xuất từ khóa gốc bằng HKDF-SHA-256 với `info` riêng.
2. Mỗi block lưu `block_mac = HMAC(K_audit, domain || index || block_hash)`.
3. Head mới nhất được lưu trong checkpoint JSON ngoài SQLite; checkpoint có HMAC riêng.
4. Mọi thao tác ghi kiểm tra checkpoint trước khi mở rộng chuỗi.
5. Verifier kiểm tra hash, block HMAC, liên kết, quan hệ version-block, AES-GCM và checkpoint.
6. Cơ sở dữ liệu schema cũ chỉ được bootstrap tại thời điểm migration sau khi chuỗi hiện có vượt qua kiểm tra nhất quán. Việc này không chứng minh lịch sử trước migration chưa từng bị sửa.

## Giới hạn phải công bố

- Nếu kẻ tấn công chiếm cả khóa gốc và checkpoint, họ có thể dựng lại lịch sử hợp lệ.
- Khóa audit dẫn xuất từ khóa gốc chưa cung cấp forward security khi khóa gốc bị lộ.
- SQLite commit và cập nhật checkpoint không tạo thành một giao dịch nguyên tử xuyên hai tài nguyên. Crash giữa hai bước làm hệ thống fail-closed và cần recovery có kiểm soát.
- Checkpoint chỉ có ý nghĩa nếu miền lưu trữ của nó không thuộc quyền sửa của DB writer. Đặt cạnh file SQLite mà không tách quyền chỉ là cấu hình demo.
- Thiết kế là authenticated audit log một nút, không phải blockchain phân tán.

## Baseline và tài liệu liên quan

Baseline định lượng tối thiểu nên gồm SQLite thuần, AES-GCM theo bản ghi, và SecureEdu đầy đủ. SQLCipher chỉ được thêm khi có thể cài đặt và chạy cùng workload trên cùng máy; không được so số đo của dự án với số quảng cáo từ hệ thống khác.

So sánh định tính phải bao phủ:

- SQLCipher cho mã hóa toàn file và HMAC ở tầng trang;
- Certificate Transparency theo RFC 9162 cho Merkle inclusion và consistency proof;
- forward-secure logging và Crosby-Wallach history tree;
- SealFSv2 hoặc secure append-only filesystem;
- hệ thống hồ sơ giáo dục dùng blockchain, nhưng không để nhóm này lấn át authenticated logging.

Nguồn khởi đầu đã xác minh:

- https://github.com/sqlcipher/sqlcipher
- https://www.zetetic.net/sqlcipher/documentation/
- https://www.rfc-editor.org/rfc/rfc9162.html

## Thứ tự công việc

1. Hoàn tất mã nguồn HMAC/checkpoint, migration và kiểm thử hồi quy.
2. Chạy đủ adaptive tamper experiment và lưu metadata.
3. Thiết kế baseline công bằng và benchmark trên ổ lưu trữ bền vững.
4. Bổ sung contention benchmark nhiều writer.
5. Viết lại related work và contribution claims từ nguồn gốc.
6. Dàn bài tiếng Việt theo IEEE A4, tối đa 6 trang.
7. Render Word/PDF, kiểm tra từng trang và rà soát mọi con số với CSV gốc.
