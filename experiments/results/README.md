# Danh mục kết quả thực nghiệm

Thư mục này lưu dữ liệu thô, thống kê và metadata để tái lập các bảng trong bài FAIR 2026. Dữ liệu đầu vào là dữ liệu mô phỏng, không chứa hồ sơ sinh viên thật.

## Bộ dữ liệu hiện hành

| Phạm vi | Raw | Summary | Metadata | Trạng thái |
|---|---|---|---|---|
| 100 và 1.000 hồ sơ, 30 lần/cấu hình/kích thước | `raw_20260809T111011Z.csv` | `summary_20260809T111011Z.csv` | `metadata_20260809T111011Z.json` | Dùng trong bài |
| 10.000 hồ sơ, 30 lần/cấu hình | `raw_20260809T120022Z.csv` | `summary_20260809T120022Z.csv` | `metadata_20260809T120022Z.json` | Dùng trong bài |
| 6 kiểu can thiệp, 30 lần/kiểu | `tamper_raw_20260809T120109Z.csv` | `tamper_summary_20260809T120109Z.csv` | `tamper_metadata_20260809T120109Z.json` | Dùng trong bài |

Tổng số phép đo hiệu năng là 270. Bộ can thiệp gồm 180 phép thử và phát hiện 30/30 ở cả sáu lớp.

## Dữ liệu lưu trữ

Các tệp có timestamp `20260712` được tạo trước schema actor-aware hiện tại. Chúng được giữ để truy vết lịch sử nhưng không được dùng cho bảng và biểu đồ FAIR 2026 mới.

## Nguyên tắc sử dụng

- Không chỉnh sửa tệp raw bằng tay.
- Luôn lưu raw, summary và metadata thành một bộ.
- Đối chiếu timestamp và commit trước khi trích số liệu.
- Không commit khóa mã hóa, `.env`, mật khẩu hoặc dữ liệu sinh viên thật.
- Xem quy trình đầy đủ tại `docs/THUC_NGHIEM_TAI_LAP.md`.
