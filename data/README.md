# data/

Không lên git (trừ file này). Dữ liệu dùng chung qua MinIO hoặc ổ nhóm.
CV thật chỉ dùng khi có form đồng ý và không chia sẻ ra ngoài nhóm.

## TopCV 2026 (Kaggle)

Dataset: `baocgb/vietnam-it-jobs-raw-data-from-topcv-2026`. Tải về `data/raw/topcv_2026/`, không commit.

1. Tạo token tại https://www.kaggle.com/settings/api rồi đặt ngoài repo, một trong hai cách:
   - Token mới: lưu chuỗi token vào `~/.kaggle/access_token`.
   - Legacy API key: lưu file vào `~/.kaggle/kaggle.json`.
   - Trên Windows, `~` là `%USERPROFILE%`.
2. Tải dữ liệu từ thư mục gốc của repo:

```
uv run --with kaggle --with six kaggle datasets download -d baocgb/vietnam-it-jobs-raw-data-from-topcv-2026 -p data/raw/topcv_2026 --unzip
```

## Snapshot 200 JD (TASK-U005)

Tạo `data/snapshot_200.jsonl` từ CSV. Tham số lấy mẫu nằm trong `config/column_map.yaml`, cùng CSV và cùng tham số thì cho cùng sha256.

```
uv run python -m scripts.make_snapshot --input data/raw/topcv_2026/topcv_jobs.csv --stats
```

CSV không có mô tả công việc nên `description` để trống cho tới khi bổ sung. Cách bổ sung, làm được nhiều đợt:

1. Chạy `uv run python -m scripts.import_saved_pages` để tạo `data/raw/topcv_2026/checklist.html`, chia link cho 3 người.
2. Mở từng link bằng trình duyệt với tốc độ đọc bình thường, bấm Ctrl+S, chọn "Webpage, HTML Only", lưu vào `data/raw/topcv_2026/pages/`. Gặp trang xác minh chống bot thì dừng lại, không tìm cách vượt qua và không dùng script để tải trang.
3. Chạy lại lệnh ở bước 1 để lấy mô tả. Email và số điện thoại trong mô tả được che.
4. Tạo lại snapshot. 200 tin được chọn không đổi, chỉ `description` và sha256 đổi nên phải gửi lại file và sha256 mới cho nhóm.

```
uv run python -m scripts.make_snapshot --input data/raw/topcv_2026/topcv_jobs.csv --descriptions data/raw/topcv_2026/descriptions.jsonl --stats
```
