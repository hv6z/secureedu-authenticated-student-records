# Rà soát đề tài và danh sách hoàn thiện

Ngày rà soát gần nhất: **20/07/2026**.

## Kết luận ngắn

Đề tài đã đạt mức **proof-of-concept nghiên cứu có thể tái lập**:

- luồng quản lý hồ sơ hoạt động;
- dữ liệu nghiệp vụ được mã hóa bằng AES-256-GCM;
- mã sinh viên được tra cứu bằng HMAC thay vì lưu rõ;
- mọi thay đổi tạo phiên bản mới và một khối kiểm toán;
- phiên bản và khối được ghi trong cùng transaction;
- quy trình xác minh phát hiện thay đổi ở bản mã, nonce, tag, hash và chuỗi;
- có dữ liệu mô phỏng, thực nghiệm ba cấu hình, metadata và biểu đồ.
- có đăng nhập, password hashing `scrypt`, khóa tài khoản tạm thời và RBAC;
- có `actor_id`/vai trò được bảo vệ trong AAD, phiên bản mã hóa và block.

Hệ thống **chưa đạt mức triển khai với dữ liệu thật** vì chưa có quản lý vòng đời khóa, chữ ký/điểm neo độc lập, HTTPS và quy trình vận hành an toàn.

## Phạm vi đã đối chiếu

- Mã nguồn trong workspace.
- Repository công khai `hv6z/secure_student_record_blockchain`, nhánh mặc định `main`.
- `filegoc.docx`.
- `Kien_truc_xu_ly_AES_GCM_Blockchain_huong_dan_tai_lap_1.docx`.
- Bộ kiểm thử, bộ dữ liệu và kết quả thực nghiệm đang có.

## Kết quả kỹ thuật

| Kiểm tra | Kết quả |
|---|---|
| Cài `requirements-lock.txt` trong môi trường mới | Đạt |
| `pip check` | Không có phụ thuộc hỏng |
| Biên dịch toàn bộ tệp Python | Đạt |
| Kiểm thử tự động | 79/79 đạt |
| Độ bao phủ | 88% tổng thể |
| Thực nghiệm nhanh, 100 hồ sơ, 3 cấu hình | Đạt; xuất CSV + JSON metadata |
| Tamper test sau nâng cấp, 6 kiểu × 1 lần | 6/6 phát hiện |
| Tương thích database schema v1 | Đạt; dữ liệu cũ vẫn giải mã và xác minh được |
| Bộ kết quả báo cáo có sẵn | 3 quy mô × 3 cấu hình × 30 lần lặp |
| Bộ thử can thiệp có sẵn | 6 kiểu × 30 lần = 180 lần |

Lần chạy pytest đầu tiên gặp lỗi quyền truy cập thư mục tạm mặc định của Windows. Đây là lỗi môi trường; chạy với `--basetemp` trong workspace cho kết quả đầy đủ đạt.

## Điểm phù hợp với tài liệu gốc

- Có Python, Flask, SQLite, AES-256-GCM và SHA-256.
- Dữ liệu nghiệp vụ được lưu ngoài “chuỗi” ở dạng mã hóa.
- Có lịch sử CREATE/UPDATE/DELETE theo phiên bản.
- Có giao diện dashboard, quản lý hồ sơ, xem khối và xác minh.
- Có quy mô 100, 1.000 và 10.000 hồ sơ.
- Có thời gian thêm, đọc, xác minh, dung lượng và tỷ lệ phát hiện.
- Có giới hạn nghiên cứu và không tuyên bố sổ một nút là blockchain phân tán hoàn chỉnh.

## Khoảng cách so với kiến trúc đề xuất

### Đã xử lý trong đợt bổ sung ngày 20/07/2026

1. **Đăng nhập và RBAC:** ba vai trò `admin`, `registrar`, `auditor`; route ghi chỉ dành cho admin/cán bộ học vụ.
2. **Bảo vệ mật khẩu:** password hash `scrypt`, khóa tạm sau số lần sai cấu hình được, vô hiệu hóa và đặt lại mật khẩu bằng CLI.
3. **Danh tính người thao tác:** schema v2 gắn `actor_id`/role vào AAD, envelope hash, phiên bản và block hash.
4. **Tương thích dữ liệu cũ:** schema v1 được tự bổ sung cột và vẫn dùng quy tắc AAD/hash v1 khi xác minh.

### Mức cao - còn cần xử lý trước dữ liệu thật

1. **Khóa AES vẫn nằm trong `.env`.** Phù hợp demo nhưng chưa có KMS/HSM, xoay khóa, thu hồi, backup có kiểm soát hoặc quy trình khôi phục.
2. **Chưa triển khai HTTPS production.** `SESSION_COOKIE_SECURE` đã cấu hình được nhưng chỉ nên bật sau HTTPS.

### Mức trung bình - giới hạn tính bất biến và vận hành

1. **Sổ kiểm toán và dữ liệu cùng nằm trong một SQLite.** Người có toàn quyền database và khóa có thể viết lại cả dữ liệu lẫn chuỗi.
2. **Chưa neo `block_hash` cuối ra vị trí độc lập hoặc ký số block.** Không phát hiện được rollback toàn bộ database về một snapshot cũ.
3. **Xóa là xóa logic.** Dữ liệu cũ vẫn tồn tại ở dạng mã hóa; cần đánh giá yêu cầu xóa dữ liệu cá nhân trước triển khai thật.
4. **Chưa có CI, dependency/security scan, backup/restore test và hướng dẫn HTTPS/deployment.**

### Mức thấp - đóng gói repository

1. Chưa có tệp `LICENSE`; cần chọn giấy phép trước khi công bố tái sử dụng.
2. Chưa có ảnh chụp giao diện thật trong README/báo cáo.
3. Metadata repository trên GitHub chưa có mô tả, chủ đề hoặc license.

## Trạng thái GitHub và workspace

Nhánh `main` công khai trên GitHub được đẩy gần nhất ngày 12/07/2026. Workspace đang rà soát chứa phiên bản mới hơn ở hầu hết tệp mã nguồn và tài liệu, nhưng thư mục dự án hiện không có `.git` riêng; Git đang nhận repository cha `D:/HUIT`.

Vì vậy, các cập nhật README/sơ đồ trong workspace **chưa tự xuất hiện trên GitHub**. Trước khi đẩy, cần đưa đúng thư mục này vào clone của repository hoặc khởi tạo/đặt lại Git đúng phạm vi, kiểm tra diff, rồi commit lên nhánh phù hợp. Không nên commit toàn bộ `D:/HUIT`.

## Nội dung đã cập nhật trong lần rà soát này

1. Viết lại `README.md` theo trạng thái thực tế, có hướng dẫn cài đặt, cấu hình, kiểm thử, thực nghiệm và mô hình tin cậy.
2. Thay sơ đồ tổng quan bằng kiến trúc as-built; tách rõ phần chưa triển khai.
3. Thêm `docs/KIEN_TRUC_HE_THONG.md` gồm sơ đồ phạm vi tin cậy, thành phần, sequence transaction, xác minh, ERD và lộ trình nâng cấp.
4. Sửa đường dẫn mô-đun sai trong `docs/ke_hoach_code.md`: `lookup.py`, `verifier.py` và trách nhiệm của từng tệp.
5. Ghi rõ tag AES-GCM được nối trong ciphertext theo API `AESGCM`, không phải cột riêng.
6. Bổ sung `users`, trang đăng nhập, session hết hạn, lockout và RBAC.
7. Bổ sung `scripts/manage_user.py` để tạo, liệt kê, đổi mật khẩu/vai trò và vô hiệu hóa tài khoản.
8. Nâng schema mật mã/block lên v2 để bảo vệ `actor_id`/role, kèm migration v1.

## Checklist trước khi nộp báo cáo

- [ ] Xác nhận tên tác giả, đơn vị, email và thứ tự tác giả.
- [ ] Xác nhận CPU, RAM và hệ điều hành của đúng máy tạo bộ số liệu ngày 12/07/2026.
- [ ] Đối chiếu từng tài liệu tham khảo với nguồn gốc; kiểm tra DOI, năm, trang và trùng lặp.
- [ ] Đưa nội dung vào đúng mẫu FAIR 2026 và kiểm tra giới hạn trang.
- [ ] Bổ sung ảnh giao diện thật với dữ liệu mô phỏng.
- [ ] Ghi rõ các phép `verify` của ba cấu hình không tương đương về chức năng.
- [ ] Dùng thuật ngữ “sổ nhật ký kiểm toán liên kết băm một nút” hoặc “private blockchain prototype”.
- [ ] Đồng bộ đúng phiên bản workspace lên GitHub.

## Checklist trước khi thử nghiệm với dữ liệu thật

- [x] Đăng nhập, password hashing, khóa tài khoản và hết hạn phiên.
- [x] RBAC ở mọi route web thay đổi dữ liệu.
- [x] `actor_id`/role trong AAD và block kiểm toán.
- [ ] KMS/HSM, xoay khóa, backup và diễn tập khôi phục.
- [ ] HTTPS, cấu hình cookie `Secure`, logging và giám sát.
- [ ] Chữ ký số hoặc neo hash cuối ra hệ thống độc lập.
- [ ] Đánh giá quyền riêng tư, thời hạn lưu và quy trình xóa dữ liệu.
- [ ] Pen-test, dependency audit và kiểm thử backup/restore.
