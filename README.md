# SecureEdu

**Bảo mật hồ sơ sinh viên với mã hóa xác thực và nhật ký audit có khóa**

Hệ thống quản lý hồ sơ sinh viên có mã hóa và kiểm chứng toàn vẹn, xây dựng bằng Python, Flask và SQLite.

![Python 3.12](https://img.shields.io/badge/Python-3.12-2563EB) ![Tests](https://img.shields.io/badge/tests-116%20passed-16A34A) ![Coverage](https://img.shields.io/badge/coverage-90.81%25-16A34A) ![UI](https://img.shields.io/badge/UI-responsive-1E3A5F)

> **Trạng thái:** proof-of-concept phục vụ nghiên cứu. Mỗi block có HMAC từ khóa audit tách miền và head mới nhất được checkpoint ngoài SQLite. Hệ thống **không phải mạng blockchain phân tán**; checkpoint phải được đặt trên miền lưu trữ mà DB writer không thể sửa. Hệ thống chưa có KMS/HSM và chưa phù hợp để triển khai với dữ liệu sinh viên thật.

Phiên bản trên nhánh `main` là bản sửa đổi cho **REV-ECIT 2026**. Phiên bản đã nộp FAIR 2026 được đóng băng tại tag `fair-2026-submission` để bảo toàn khả năng tái lập.

## Tổng quan

Mỗi thao tác tạo, cập nhật hoặc xóa logic một hồ sơ sẽ:

1. kiểm tra và chuẩn hóa dữ liệu;
2. tạo phiên bản hồ sơ mới;
3. mã hóa JSON bằng AES-256-GCM với nonce 12 byte mới;
4. gắn `actor_id`/vai trò vào AAD và tính SHA-256 cho phong bì mã hóa;
5. nối một khối kiểm toán với khối trước và xác thực block bằng HMAC;
6. ghi phiên bản, khối và con trỏ phiên bản trong **cùng một giao dịch SQLite**.

Sau khi SQLite commit, tệp checkpoint ngoài database được thay thế nguyên tử bằng head mới nhất. Bộ xác minh yêu cầu HMAC của từng block hợp lệ và checkpoint khớp chính xác với head, nhờ đó DB writer không thể che giấu việc sửa rồi rehash hoặc cắt lịch sử chỉ bằng cách sửa SQLite. Hai bước commit SQLite và thay checkpoint không tạo thành một giao dịch nguyên tử xuyên hai tài nguyên.

Mã sinh viên không được lưu ở dạng rõ. Hệ thống dẫn xuất một khóa tra cứu riêng và lưu HMAC-SHA-256 để hỗ trợ tìm kiếm chính xác.

## Trạng thái rà soát

| Hạng mục | Kết quả cập nhật ngày 27/09/2026 |
|---|---|
| Kiểm thử tự động | 116/116 đạt |
| Độ bao phủ mã nguồn | 90,81%; ngưỡng bắt buộc ≥ 90% |
| Kiểm tra cú pháp Python | Đạt |
| Cài đặt từ `requirements-lock.txt` | Đạt trên Python 3.12 |
| Thử can thiệp, 13 kịch bản × 30 lần | Từ chối 390/390 trạng thái bị sửa; gồm 210 lần thử DB writer thích nghi |
| Benchmark FAIR đã lưu | Dùng làm mốc tham chiếu; cần chạy lại sau schema v4 |
| Đăng nhập, khóa tạm và RBAC | Đã triển khai |
| `actor_id` trong AAD, phiên bản và block | Đã triển khai; tương thích schema v1 |
| HMAC block / checkpoint ngoài SQLite | Đã triển khai; checkpoint phải được bảo vệ độc lập với quyền ghi DB |

## Giao diện SecureEdu

Giao diện được thiết kế lại theo hướng dashboard bảo mật doanh nghiệp: responsive, điều hướng bàn phím, focus rõ, icon SVG thống nhất, trạng thái không chỉ dựa vào màu và hỗ trợ `prefers-reduced-motion`. Chế độ sáng/tối tự nhận thiết lập hệ thống ở lần đầu, cho phép chuyển nhanh trên thanh điều hướng và ghi nhớ lựa chọn ngay trong trình duyệt.

![Dashboard SecureEdu Audit Ledger](docs/screenshots/dashboard-desktop.png)

**Chế độ tối trên dashboard và cổng đăng nhập**

![Dashboard SecureEdu Audit Ledger - chế độ tối](docs/screenshots/dashboard-dark.png)

![Đăng nhập SecureEdu Audit Ledger - chế độ tối](docs/screenshots/login-dark.png)

Kết luận: đề tài **đã đạt mức proof-of-concept nghiên cứu có kiểm soát truy cập**, nhưng vẫn cần quản lý khóa, HTTPS, vận hành an toàn và một điểm neo độc lập trước khi có thể xem là hệ thống thực tế. Xem báo cáo rà soát chi tiết tại [`docs/RA_SOAT_VA_CHINH_SUA.md`](docs/RA_SOAT_VA_CHINH_SUA.md).

## Kiến trúc hiện thực

Sơ đồ dưới đây mô tả đúng mã nguồn hiện tại, không bao gồm các hạng mục mới chỉ có trong kiến trúc đề xuất.

```mermaid
flowchart TB
    U["Người dùng trên máy cục bộ"] --> A0["Đăng nhập + session<br/>web/auth.py"]
    A0 --> A1["AuthenticationService<br/>scrypt + khóa tạm"]
    A1 --> DB
    A0 -->|"RBAC"| W["Flask Web<br/>routes.py + templates"]
    W -->|"CSRF + kiểm tra biểu mẫu"| S["RecordService<br/>điều phối nghiệp vụ"]

    S --> D["domain/student.py<br/>chuẩn hóa và kiểm tra"]
    S --> A["encryption/aes_cipher.py<br/>AES-256-GCM"]
    S --> L["integrity/lookup.py<br/>HMAC-SHA-256"]
    S --> H["integrity/hashing.py + audit.py<br/>SHA-256 + HMAC audit"]
    S --> R["database/repository.py<br/>phiên bản mã hóa"]
    S --> C["blockchain/chain.py<br/>khối liên kết băm"]
    S --> V["verification/verifier.py<br/>xác minh nhiều lớp"]

    R --> T["Giao dịch BEGIN IMMEDIATE"]
    C --> T
    T --> DB[("SQLite/WAL<br/>records + record_versions + audit_blocks")]
    V --> DB
    S --> P["Checkpoint head có HMAC<br/>ngoài SQLite"]
    V --> P

    N["Chưa triển khai:<br/>KMS/HSM, atomic commit DB-checkpoint,<br/>HTTPS production, nhiều nút"] -.-> W
```

Tài liệu kiến trúc đầy đủ gồm luồng ghi, luồng xác minh và lược đồ dữ liệu: [`docs/KIEN_TRUC_HE_THONG.md`](docs/KIEN_TRUC_HE_THONG.md).

## Các lớp bảo vệ

| Mục tiêu | Cơ chế hiện có | Phạm vi |
|---|---|---|
| Bảo mật nội dung | AES-256-GCM | Họ tên, mã sinh viên, ngày sinh, chương trình và điểm chỉ xuất hiện trong ciphertext |
| Tìm kiếm kín | HMAC-SHA-256 với khóa dẫn xuất | Tra mã sinh viên mà không lưu mã rõ |
| Xác thực ngữ cảnh | AAD gồm `record_id`, `version`, `operation`, `schema_version` | Ngăn tráo bản mã giữa hồ sơ hoặc phiên bản |
| Toàn vẹn phong bì | SHA-256 có phân tách miền | Phát hiện thay đổi nonce, ciphertext hoặc metadata |
| Xác thực lịch sử | HMAC-SHA-256 trên từng `block_hash` bằng khóa audit dẫn xuất riêng | Chặn DB writer tính lại chuỗi sau khi sửa dữ liệu nếu không có khóa |
| Độ mới của lịch sử | Checkpoint head có HMAC nằm ngoài SQLite | Phát hiện rollback hoặc cắt suffix khi checkpoint không thuộc quyền sửa của DB writer |
| Nhất quán dữ liệu | `BEGIN IMMEDIATE`, COMMIT/ROLLBACK | Phiên bản và khối được ghi nguyên tử |
| An toàn biểu mẫu | CSRF token, giới hạn nội dung, security headers | Giảm rủi ro trên giao diện web cục bộ |
| Chống ghi đè | `expected_version` | Phát hiện cập nhật trên phiên bản đã cũ |
| Xác thực | Password hash `scrypt`, session ký, khóa tạm | Không lưu mật khẩu rõ; khóa sau nhiều lần đăng nhập sai |
| Phân quyền | `admin`, `registrar`, `auditor` | Chỉ admin/cán bộ học vụ được thay đổi hồ sơ |
| Truy vết chủ thể | `actor_id` và role trong AAD, version, block hash | Phát hiện thay đổi hoặc tráo danh tính người thao tác |

Lưu ý: `cryptography.hazmat.primitives.ciphers.aead.AESGCM` trả về ciphertext đã nối thẻ xác thực 16 byte; cơ sở dữ liệu không có cột `tag` riêng.

## Chức năng

- Thêm, xem, sửa và xóa logic hồ sơ sinh viên.
- Quản lý học phần, điểm và GPA.
- Lưu toàn bộ lịch sử phiên bản đã mã hóa.
- Xem các khối kiểm toán sau khi khởi động lại ứng dụng.
- Xác minh toàn hệ thống hoặc một hồ sơ cụ thể.
- Sinh dữ liệu mô phỏng 100, 1.000 và 10.000 hồ sơ.
- So sánh ba cấu hình: SQLite; SQLite + AES-GCM; SQLite + AES-GCM + sổ kiểm toán.
- Xuất dữ liệu thô, thống kê, metadata môi trường và biểu đồ.
- Thử thay đổi trái phép trên cơ sở dữ liệu tạm.

## Yêu cầu

- Windows 10/11.
- Python 3.11 trở lên; môi trường khóa phiên bản đã được kiểm tra với Python 3.12.
- Git và PowerShell.

## Cài đặt nhanh

```powershell
git clone https://github.com/hv6z/secureedu-authenticated-student-records.git
cd secureedu-authenticated-student-records

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
```

Nếu không cần tái lập đúng phiên bản thư viện đã đo, có thể dùng:

```powershell
python -m pip install -r requirements-dev.txt
```

## Cấu hình và khởi chạy

Tạo khóa AES 256 bit và khóa phiên Flask:

```powershell
python scripts/generate_key.py
```

Lệnh tạo tệp `.env` cục bộ. Tệp này đã nằm trong `.gitignore`.

> Không dùng `--force` khi đã có dữ liệu cần giữ. Thay AES key sẽ làm các phiên bản cũ không thể giải mã.

Khởi tạo cơ sở dữ liệu, thêm dữ liệu minh họa và chạy ứng dụng:

```powershell
python scripts/init_db.py
python scripts/manage_user.py create --username admin --role admin
python scripts/seed_demo.py
python run.py
```

Mở [http://127.0.0.1:5000](http://127.0.0.1:5000).

Mật khẩu được nhập ẩn hai lần và không xuất hiện trong lịch sử lệnh. Quản lý thêm tài khoản bằng:

```powershell
python scripts/manage_user.py list
python scripts/manage_user.py create --username hocvu --role registrar
python scripts/manage_user.py create --username kiemtoan --role auditor
python scripts/manage_user.py password hocvu
python scripts/manage_user.py disable hocvu
```

### Biến môi trường

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---:|---|---|
| `AES_KEY` | Có | Không có | Khóa AES 32 byte, mã hóa Base64 |
| `FLASK_SECRET_KEY` | Có | Không có | Ký phiên và CSRF token |
| `DATABASE_PATH` | Không | `instance/student_records.db` | Đường dẫn SQLite |
| `AUDIT_ANCHOR_PATH` | Không | `<DATABASE_PATH>.audit-anchor.json` | Checkpoint head; khi triển khai phải đặt trên miền lưu trữ tách quyền ghi SQLite |
| `KEY_ID` | Không | `key-v1` | Nhãn nhận dạng khóa, không phải khóa bí mật |
| `SESSION_LIFETIME_MINUTES` | Không | `30` | Thời gian tồn tại của phiên đăng nhập |
| `LOGIN_MAX_ATTEMPTS` | Không | `5` | Số lần sai trước khi khóa tạm |
| `LOGIN_LOCKOUT_MINUTES` | Không | `15` | Thời gian khóa tài khoản |
| `SESSION_COOKIE_SECURE` | Không | `false` | Đặt `true` khi chạy sau HTTPS |

## Kiểm thử

```powershell
python -m pytest -q
```

`pytest.ini` đã cấu hình thư mục tạm trong workspace, báo cáo coverage và ngưỡng `--cov-fail-under=90`; lệnh trên sẽ thất bại nếu độ phủ giảm dưới yêu cầu.

## Thực nghiệm

Quy trình đầy đủ, tiêu chí kiểm tra dữ liệu và cách công bố kết quả được mô tả tại [`docs/THUC_NGHIEM_TAI_LAP.md`](docs/THUC_NGHIEM_TAI_LAP.md).

Sinh dữ liệu mô phỏng:

```powershell
python experiments/generate_dataset.py --size 100
python experiments/generate_dataset.py --size 1000
python experiments/generate_dataset.py --size 10000
```

Chạy thử nhanh trước khi đo chính thức:

```powershell
python experiments/run_experiment.py --sizes 100 --repeats 1
```

Chạy cấu hình dùng cho báo cáo:

```powershell
python experiments/run_experiment.py --sizes 100 1000 10000 --repeats 30
python experiments/make_figures.py
```

Mỗi cấu hình ghi một hồ sơ bằng một giao dịch SQLite và dùng WAL. Thứ tự cấu hình được xáo trộn có thể tái lập theo từng lần lặp. Ba phép `verify` không tương đương về chức năng: SQLite chỉ kiểm tra khả năng đọc/JSON, AES xác thực từng bản mã, còn cấu hình đầy đủ kiểm tra cả AES và chuỗi liên kết băm.

Các tệp `raw_*.csv`, `summary_*.csv` và `metadata_*.json` được lưu trong `experiments/results`. Không chỉnh số liệu thô bằng tay.

Thử can thiệp trên cơ sở dữ liệu tạm:

```powershell
python experiments/tamper_test.py --trials 30
```

Chương trình tách hai nhóm rõ ràng: sáu mutation không sửa trạng thái phụ thuộc và bảy chiến lược DB writer thích nghi gồm modify-and-rehash, sửa timestamp rồi rehash, xóa hồ sơ rồi nối lại chuỗi, cắt suffix và sửa head, ghép lịch sử hợp lệ, reorder/reindex và rollback riêng một hồ sơ.

## Cấu trúc dự án

```text
secureedu-authenticated-student-records/
├── src/
│   ├── domain/          chuẩn hóa và kiểm tra hồ sơ
│   ├── auth/            tài khoản, password hashing và khóa đăng nhập
│   ├── encryption/      JSON chuẩn và AES-GCM
│   ├── integrity/       HMAC tra cứu, HMAC audit, checkpoint và SHA-256
│   ├── database/        kết nối, schema và repository
│   ├── blockchain/      cấu trúc khối và chuỗi liên kết băm
│   ├── verification/    xác minh chuỗi, phong bì và AES-GCM
│   ├── services/        điều phối nghiệp vụ trong transaction
│   └── web/             ứng dụng Flask và giao diện
├── tests/               kiểm thử tự động
├── scripts/             tạo khóa, khởi tạo DB và dữ liệu demo
├── experiments/         dữ liệu, đo lường, tamper test và biểu đồ
└── docs/                kiến trúc, rà soát và nội dung báo cáo
```

## Mô hình tin cậy và giới hạn

- Đây là **sổ nhật ký kiểm toán liên kết băm một nút**, không phải blockchain permissioned nhiều nút.
- DB writer có quyền sửa SQLite nhưng không có khóa audit và không có quyền sửa checkpoint sẽ bị phát hiện khi rehash, xóa chọn lọc, reorder hoặc rollback.
- Người chiếm đồng thời SQLite, khóa gốc và checkpoint vẫn có thể dựng lại lịch sử hợp lệ; HMAC không thay thế KMS/HSM hoặc chữ ký bằng khóa ký tách biệt.
- Commit SQLite và cập nhật checkpoint là hai thao tác liên tiếp, không phải một giao dịch nguyên tử xuyên hai tài nguyên. Sự cố giữa hai bước làm hệ thống fail-closed và cần quy trình khôi phục có kiểm soát.
- Đăng nhập/RBAC giảm truy cập trái phép ở tầng ứng dụng nhưng không bảo vệ khi máy chủ, database và khóa đều bị chiếm quyền.
- Xóa là xóa logic; các phiên bản cũ vẫn tồn tại ở dạng mã hóa để bảo toàn lịch sử kiểm toán.
- Chưa có KMS/HSM, xoay khóa, sao lưu khóa có kiểm soát hoặc chữ ký số bằng khóa bất đối xứng.
- Chỉ nên dùng dữ liệu mô phỏng cho đến khi có cơ chế truy cập phù hợp và phê duyệt xử lý dữ liệu cá nhân.

## Tài liệu

- [Kiến trúc hệ thống và các sơ đồ](docs/KIEN_TRUC_HE_THONG.md)
- [Kế hoạch code và luồng nghiệp vụ](docs/ke_hoach_code.md)
- [Kết quả rà soát và việc còn lại](docs/RA_SOAT_VA_CHINH_SUA.md)
- [Bản nháp nội dung báo cáo](docs/report/du_thao_noi_dung.md)

## Hướng phát triển ưu tiên

1. Bổ sung KMS/HSM, phiên bản khóa và quy trình xoay/chuyển đổi dữ liệu.
2. Đưa khóa audit vào KMS/HSM và đặt checkpoint trên kho độc lập có kiểm soát phiên bản/WORM.
3. Bổ sung CI, dependency audit, backup/restore test và triển khai HTTPS.
4. Thêm giao diện quản trị tài khoản có bước xác nhận lại mật khẩu và nhật ký sự kiện đăng nhập.
5. Nếu cần tính bất biến mạnh, chuyển sổ kiểm toán sang mạng permissioned nhiều tổ chức.
