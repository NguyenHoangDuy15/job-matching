# ADR-003: Chốt stack, bỏ công cụ chưa cần

- Trạng thái: đã chấp nhận (có hiệu lực khi PR được merge với 2 approve)
- Ngày: 05/11/2026
- Người viết / người duyệt: Duy / Tùng, Thịnh

## Bối cảnh

Nhóm có 3 người. Thiết kế ban đầu có Airflow, dbt và MinIO, nên repo vẫn còn thư mục `dags/`, `dbt/` trống. Hệ thống hiện chạy bằng một `compose.yaml` gồm db, api, ui. Dữ liệu TopCV 2026 có 1.550 dòng (`reports/profiling_topcv.md`).

Mỗi công cụ thêm vào là thêm một thứ phải học, cài trên 3 máy và giữ cho CI chạy được. ADR này chốt những gì chưa dùng, để nhóm không mất thời gian vào chúng. Các ngưỡng trong "Điều kiện xem lại" là ước lượng ban đầu, chưa đo trên hệ thống thật.

## Quyết định

### 1. Bỏ Airflow, dùng Makefile và scripts

- **Lý do:** Các bước xử lý hiện chạy tay được bằng script (ví dụ `scripts/profile_dataset.py`). Airflow cần thêm scheduler, webserver và DB riêng, quá nặng so với nhu cầu.
- **Phương án thay thế:** Airflow; cron.
- **Điều kiện xem lại:** Cần chạy pipeline theo lịch cố định và tự chạy lại khi lỗi.

### 2. Bỏ dbt, transform bằng Python và SQL

- **Lý do:** Số bước transform còn ít, viết bằng Python và SQL thì cả nhóm đã biết. Thư mục `dbt/` chưa có model nào.
- **Phương án thay thế:** dbt-core.
- **Điều kiện xem lại:** Có nhiều bước SQL phụ thuộc nhau và cần theo dõi nguồn gốc dữ liệu.

### 3. Bỏ MinIO, lưu file local qua `src/common/storage.py`

- **Lý do:** Hệ thống chạy trên một máy nên chưa cần object storage. Mọi truy cập file đi qua `storage.py`, nên sau này đổi nơi lưu không phải sửa nơi gọi.
- **Phương án thay thế:** MinIO; S3.
- **Điều kiện xem lại:** Triển khai nhiều máy cần dùng chung file.

### 4. Lưu nhãn relevance bằng JSONL

- **Lý do:** File text xem được diff và review được qua PR, không cần công cụ gán nhãn hay bảng DB riêng.
- **Phương án thay thế:** Bảng Postgres; Label Studio.
- **Điều kiện xem lại:** Nhiều người gán cùng lúc thường xuyên bị xung đột.

### 5. Hoãn index HNSW, quét chính xác bằng pgvector

- **Lý do:** Với quy mô hiện tại, quét chính xác nhiều khả năng đủ nhanh (chưa đo). Kết quả không bị sai số do index xấp xỉ nên benchmark dễ so sánh.
- **Phương án thay thế:** HNSW; IVFFlat.
- **Điều kiện xem lại:** Vượt 50.000 JD, hoặc p95 truy vấn top-K vượt 200 ms.

### 6. Dùng torch bản CPU

- **Lý do:** Bản CPU nhẹ hơn nhiều so với bản CUDA, nên image và CI nhanh hơn, chạy giống nhau trên cả 3 máy.
- **Phương án thay thế:** torch bản CUDA; ONNX Runtime; API embedding bên ngoài (phải gửi nội dung CV ra ngoài, không phù hợp với quy định về PII).
- **Điều kiện xem lại:** Embed toàn bộ dữ liệu mất hơn 1 giờ.

## Hệ quả

- Không cần học hay chạy Airflow, dbt, MinIO trong giai đoạn này.
- Dữ liệu trong `data/` không lên git và dùng chung qua ổ nhóm.
- Khi thêm torch phải cấu hình nguồn cài bản CPU trong `pyproject.toml`.
- Task sau cần viết `src/common/storage.py`, vì file này chưa có.
- Cần dọn ở một PR riêng các chỗ còn nhắc công cụ đã bỏ: `README.md`, `.gitignore`, `data/README.md`, docstring của `src/common/__init__.py`, thư mục `dags/` và `dbt/`.
- Còn để ngỏ: `compose.yaml` đang dùng `pgvector/pgvector:pg16`, chưa ghim phiên bản cụ thể như `docs/learning/docker-pgvector.md` đã gợi ý.
