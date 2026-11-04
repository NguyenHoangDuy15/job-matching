# Báo cáo profiling TopCV 2026

Nguồn: [Vietnam IT Jobs Raw Data from TopCV 2026](https://www.kaggle.com/datasets/baocgb/vietnam-it-jobs-raw-data-from-topcv-2026), tác giả `baocgb`, giấy phép CC BY 4.0.

## 1. Quy mô và cột

- Số dòng: 1550
- Số cột: 7
- Các cột: `title`, `company`, `location`, `experience`, `salary`, `date_posted`, `url`
- Trường `raw_job` chưa có trong dữ liệu: `description`, `deadline`

## 2. Dữ liệu thiếu

| Cột | % ô trống |
|---|---:|
| `title` | 0.00 |
| `company` | 0.00 |
| `location` | 0.00 |
| `experience` | 12.00 |
| `salary` | 0.00 |
| `date_posted` | 0.00 |
| `url` | 0.00 |

## 3. Trùng lặp

- Trùng exact trên mọi cột: 0.00%
- Trùng khi bỏ cột URL: 0.19%

## 4. Ngày đăng

- Sớm nhất: 2025-12-16
- Muộn nhất: 2026-01-15
- Có giá trị nhưng không đọc được: 0.00%

## 5. URL tin gốc

- Có URL bắt đầu bằng `http`: 100.00%

## 6. Nhóm nghề

Gán theo từ khóa trong tiêu đề, xem `config/column_map.yaml`. Kết quả chưa được đối chiếu với mẫu gán nhãn.

| Nhóm | Số tin | % |
|---|---:|---:|
| `qa_test` | 127 | 8.19 |
| `ba_pm` | 247 | 15.94 |
| `it_sales` | 109 | 7.03 |
| `data_ai` | 41 | 2.65 |
| `infra_support` | 168 | 10.84 |
| `software_dev` | 581 | 37.48 |
| `other` | 277 | 17.87 |

**Kết luận:** Có, cần lấy thêm nội dung mô tả công việc bằng crawl hoặc nguồn khác, vì bộ dữ liệu không có trường `description` nên chưa đủ cho semantic search CV ↔ JD; cần kiểm tra điều khoản và `robots.txt` của nguồn trước khi crawl.
