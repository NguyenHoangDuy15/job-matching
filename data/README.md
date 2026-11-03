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
