# Hướng dẫn tái lập thực nghiệm

Tài liệu này mô tả cách tạo lại các kết quả hiệu năng và kiểm tra phát hiện can thiệp cho bản sửa REV-ECIT 2026. Toàn bộ dữ liệu đầu vào là dữ liệu mô phỏng, không chứa hồ sơ sinh viên thật. Kết quả hiệu năng FAIR thuộc thiết kế hash-chain không khóa và không được tái sử dụng như kết quả của thiết kế mới.

## 1. Phiên bản mã nguồn

Trước khi chạy, ghi lại commit đang sử dụng:

```powershell
git rev-parse HEAD
git status --short
```

Kết quả chỉ có thể đối chiếu chính xác khi commit và trạng thái tệp làm việc được lưu cùng bộ dữ liệu.

## 2. Chuẩn bị môi trường

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python -m pytest --basetemp=.pytest-tmp-fair2026
```

Nếu Windows báo lỗi truy cập thư mục tạm, chọn một tên `--basetemp` mới thay vì kết luận kiểm thử mã nguồn thất bại.

## 3. Tạo dữ liệu mô phỏng

```powershell
python experiments/generate_dataset.py --size 100
python experiments/generate_dataset.py --size 1000
python experiments/generate_dataset.py --size 10000
```

Các tệp JSON được lưu trong `experiments/datasets/`. Không thay thế chúng bằng dữ liệu sinh viên thật.

## 4. Chạy thực nghiệm hiệu năng

Chạy thử nhanh trước:

```powershell
python experiments/run_experiment.py --sizes 100 --repeats 1 --seed 2026
```

Chạy cấu hình dùng cho bài báo:

```powershell
python experiments/run_experiment.py --sizes 100 1000 10000 --repeats 30 --seed 2026 --output-dir experiments/results
```

Một lần chạy hợp lệ phải tạo:

- `raw_*.csv`: 270 dòng dữ liệu, tương ứng 3 cấu hình × 3 kích thước × 30 lần lặp;
- `summary_*.csv`: thống kê mô tả của từng chỉ số;
- `metadata_*.json`: hệ điều hành, CPU, bộ nhớ, Python, SQLite và phiên bản thư viện.

Không chỉnh sửa số liệu thô bằng tay. Nếu cần loại bỏ một lần chạy, phải ghi rõ lý do và chạy lại toàn bộ cấu hình.

## 5. Chạy thử nghiệm can thiệp

```powershell
python experiments/tamper_test.py --trials 30 --output-dir experiments/results
```

Kết quả gồm 13 kiểu can thiệp, mỗi kiểu 30 lần: sáu mutation không sửa trạng thái phụ thuộc và bảy chiến lược DB writer thích nghi. Tệp `tamper_raw_*.csv`, `tamper_summary_*.csv` và `tamper_metadata_*.json` phải được lưu cùng nhau. Metadata phải có `source_dirty` và `source_tree_sha256`; chỉ ghi commit là chưa đủ khi phép đo chạy trên working tree chưa commit.

## 6. Kiểm tra trước khi dùng trong bài báo

- Xác nhận `116/116` kiểm thử vượt qua và độ bao phủ không dưới 90%.
- Xác nhận mỗi cặp cấu hình/kích thước có đúng 30 lần lặp.
- Đối chiếu trực tiếp các giá trị trong bảng bài báo với `summary_*.csv`.
- Ghi rõ commit, môi trường máy chạy, thời điểm chạy và seed.
- Không diễn giải chênh lệch giữa ba cấu hình là chi phí riêng của AES, vì khối lượng công việc xác minh của chúng không giống nhau.
- Không suy rộng kết quả một máy thành hiệu năng trên hệ thống phân tán hoặc môi trường sản xuất.

## 7. Công bố trên GitHub

Repository: https://github.com/hv6z/secureedu-authenticated-student-records

Khi cập nhật kết quả, commit đồng thời script, dữ liệu thô, thống kê, metadata và tài liệu này. Không công bố khóa AES, mật khẩu, tệp `.env`, cơ sở dữ liệu thật hoặc dữ liệu nhận dạng cá nhân.

## 8. Bộ kết quả can thiệp của thiết kế REV ECIT

| Phạm vi | Dữ liệu thô | Thống kê | Metadata | Số phép thử |
|---|---|---|---|---:|
| 6 mutation không nhất quán và 7 tấn công thích nghi | `tamper_raw_20260925T065010Z.csv` | `tamper_summary_20260925T065010Z.csv` | `tamper_metadata_20260925T065010Z.json` | 390 |

Tất cả 390 trạng thái bị sửa đều bị verifier từ chối. Đây là kết quả quyết định trên các kịch bản đã định nghĩa, không phải xác suất phát hiện mọi tấn công. Metadata ghi `source_dirty=true` và SHA-256 của cây source vì phép đo được chạy trước khi tạo commit mới.

## 9. Bộ kết quả FAIR chỉ để lưu trữ

Để tránh mất toàn bộ dữ liệu khi phép đo 10.000 hồ sơ kéo dài, bộ 30 lần lặp được chạy thành hai chặng liên tiếp trên cùng máy, cùng phiên bản phần mềm và cùng seed:

| Phạm vi | Dữ liệu thô | Thống kê | Metadata | Số phép đo |
|---|---|---|---|---:|
| 100 và 1.000 hồ sơ | `raw_20260809T111011Z.csv` | `summary_20260809T111011Z.csv` | `metadata_20260809T111011Z.json` | 180 |
| 10.000 hồ sơ | `raw_20260809T120022Z.csv` | `summary_20260809T120022Z.csv` | `metadata_20260809T120022Z.json` | 90 |
| Sáu kiểu can thiệp | `tamper_raw_20260809T120109Z.csv` | `tamper_summary_20260809T120109Z.csv` | `tamper_metadata_20260809T120109Z.json` | 180 |

Hai chặng hiệu năng cùng dùng Windows 11, Intel Core i5-10300H, 7,84 GiB RAM, Python 3.12.13, SQLite 3.50.4, Flask 3.1.3, cryptography 49.0.0 và commit `18d5f84297a4f7d24173362d2234a0a15eeafb2d`. Tổng cộng có 270 phép đo hiệu năng; mỗi cặp cấu hình/kích thước có đúng 30 lần lặp.

Toàn bộ tệp hiệu năng và can thiệp FAIR, kể cả timestamp `20260712` và `20260809`, là dữ liệu lưu trữ từ thiết kế cũ và không được dùng cho bảng kết quả của bản REV-ECIT.
