# Danh mục kết quả thực nghiệm

Thư mục này lưu dữ liệu mô phỏng, số đo thô, thống kê và metadata cho bản sửa REV-ECIT 2026. Không có hồ sơ sinh viên thật.

## Bộ kết quả REV-ECIT hiện hành

| Phạm vi | Raw | Summary | Metadata | Số phép đo |
|---|---|---|---|---:|
| SQLite, AES-GCM và SecureEdu; 100/1.000 hồ sơ; 10 lần | `raw_20260927T031609Z.csv` | `summary_20260927T031609Z.csv` | `metadata_20260927T031609Z.json` | 60 |
| SQLite, AES-GCM và SecureEdu; 10.000 hồ sơ; 3 lần | `raw_20260927T032752Z.csv` | `summary_20260927T032752Z.csv` | `metadata_20260927T032752Z.json` | 9 |
| SQLCipher 4.12; ba quy mô; 10 lần | `raw_20260927T033437Z.csv` | `summary_20260927T033437Z.csv` | `metadata_20260927T033437Z.json` | 30 |
| Bộ hiệu năng đã ghép để lập bảng/hình | `raw_rev_ecit_20260927.csv` | `summary_rev_ecit_20260927.csv` | `metadata_rev_ecit_20260927.json` | 99 |
| 13 kiểu can thiệp × 30 lần | `tamper_raw_20260925T065010Z.csv` | `tamper_summary_20260925T065010Z.csv` | `tamper_metadata_20260925T065010Z.json` | 390 |
| 1/2/4/8 luồng × 10 lần | `contention_raw_20260927T031003Z.csv` | `contention_summary_20260927T031003Z.csv` | `contention_metadata_20260927T031003Z.json` | 40 |

SQLCipher là baseline độc lập về mã hóa/xác thực ở tầng trang. SQLite và AES-GCM là ablation; SecureEdu có thêm phiên bản, block HMAC và checkpoint nên các phép xác minh không cùng ngữ nghĩa.

## Dữ liệu lưu trữ

Các tệp timestamp `20260712` và `20260809` thuộc thiết kế FAIR trước block HMAC/checkpoint. Chúng chỉ được giữ để truy vết và không được dùng cho bảng REV-ECIT.

## Nguyên tắc sử dụng

- Không chỉnh sửa raw bằng tay; khi ghép chỉ nối nguyên hàng và tính lại summary.
- Luôn lưu raw, summary và metadata thành một bộ.
- Đối chiếu số lần lặp: P1–P3 dùng 10 lần ở 100/1.000 và 3 lần ở 10.000; SQLCipher dùng 10 lần ở mọi quy mô.
- Không diễn giải tỷ lệ với SQLCipher là so sánh an toàn tương đương: SQLCipher không cung cấp lịch sử phiên bản có checkpoint.
- Không commit khóa, `.env`, mật khẩu hoặc dữ liệu thật.
