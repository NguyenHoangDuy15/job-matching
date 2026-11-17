# S3-T05: Đo precision/recall khử trùng trên toàn kho, chỉnh ngưỡng

Ngày 17/11/2026 · Tùng · US-14 · Phụ thuộc S3-T03 (#658), S3-T04 (#659, #664)

> **Trạng thái:** đã đo, chỉnh ngưỡng và duyệt nhãn; chờ merge rồi chạy `--apply` trên production.
> Luật mới: **trùng hẳn chức danh + giống ≥ 0,45 → gộp** (trước: ≥ 0,85).
> Precision **1,000** (10/10 cặp gộp đều đúng) · recall phần gộp tự động **0,28 → 0,40** ·
> recall gộp + hàng chờ admin **0,88 → 0,96**. Đạt nghiệm thu precision ≥ 0,95.

## 1. Cách đo

| Bước               | Lệnh                                                                                                  | Ghi chú                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Lấy mẫu            | `uv run python scripts/eval_dedup.py sample --out reports/s3_t05/pairs.csv`                           | Chỉ đọc DB (`read_only`). Ra `pairs.csv` (điền nhãn) + `pairs.html` (hai tin cạnh nhau, chỗ khác tô màu; không commit) |
| Gán nhãn           | cột `nhan` trong `pairs.csv`                                                                          | `1` = cùng một tin tuyển dụng, `0` = hai tin khác nhau                                                                 |
| Chấm điểm          | `uv run python scripts/eval_dedup.py score reports/s3_t05/pairs.csv --report reports/s3_t05/score.md` | Không cần DB; thử 96 bộ ngưỡng                                                                                         |
| Khử trùng toàn kho | `scripts/dedup_exact.py`, `scripts/dedup_near.py` (chạy thử, rồi `--apply`)                           | Mục 4                                                                                                                  |

**Đơn vị đo là cặp tin** cùng công ty và có chung tỉnh, đúng phạm vi `ingestion.near_dedup`.
Cặp gồm cả tin đang mở và tin đã bị gộp, để đo luôn những gì luật cũ đã gộp. Mỗi cặp giữ lại 3
đặc trưng mà luật dùng (độ giống nội dung, độ giống chức danh, số từ), nhờ vậy thử ngưỡng khác
không cần quay lại DB.

**Lấy mẫu phân tầng theo độ giống.** Kho chỉ có 268 cặp ≥ 0,20 trong 1.446 tin, nên các tầng trên
được **lấy hết**: đây là số liệu thật của toàn kho, không phải ước lượng.

| Tầng        | Độ giống  | Số cặp trong kho | Lấy                         | Trùng thật (nhãn) |
| ----------- | --------- | ---------------- | --------------------------- | ----------------- |
| gop         | ≥ 0,85    | 19               | 19 (hết)                    | 17                |
| hang_cho    | 0,70–0,85 | 10               | 10 (hết)                    | 5                 |
| duoi_nguong | 0,40–0,70 | 47               | 47 (hết)                    | 3                 |
| thap        | 0,20–0,40 | 192              | 24 (ngẫu nhiên, trọng số 8) | 0                 |

Precision và recall được tính có trọng số (số cặp của tầng / số cặp có nhãn của tầng). Cặp
< 0,20 không lấy mẫu, nên recall ở đây là cận trên.

**Quy ước nhãn.** Hai tin là trùng khi cùng vị trí, cùng cấp bậc, cùng nơi làm việc, chỉ khác
cách viết, nguồn hoặc lần đăng. Khác cấp bậc (Lead / không Lead, Senior / không Senior), khác yêu
cầu kinh nghiệm kèm lương khác, hoặc khác mã tuyển dụng thì là hai tin. Nhãn đã duyệt ngày 17/11/2026. 17 cặp ranh giới vẫn giữ dấu `?` ở cột `ghi_chu` để lần chấm sau dễ xem lại.

## 2. Kết quả

| Luật       | Gộp khi                                        | Precision | Cận dưới 95% (Wilson) | Recall (gộp) | Recall (gộp + hàng chờ) | Cặp gộp |
| ---------- | ---------------------------------------------- | --------- | --------------------- | ------------ | ----------------------- | ------- |
| S3-T04     | chức danh trùng hẳn, ≥ 30 từ, giống ≥ 0,85     | 1,000     | 0,646                 | 0,280        | 0,880                   | 7       |
| **S3-T05** | chức danh trùng hẳn, ≥ 30 từ, giống **≥ 0,45** | **1,000** | 0,722                 | **0,400**    | **0,960**               | 10      |

Bảng đầy đủ 96 bộ ngưỡng: `reports/s3_t05/score.md`.

**Vì sao hạ ngưỡng gộp xuống 0,45.** Ba cặp trùng thật đang bị bỏ sót hoặc phải chờ admin, dù
chức danh trùng hẳn:

| Cặp                                                     | Độ giống | Nguồn                | Vì sao giống thấp                  |
| ------------------------------------------------------- | -------- | -------------------- | ---------------------------------- |
| FPT Software · Nutanix Software Engineer (#421 ~ #1066) | 0,629    | VietnamWorks ~ TopCV | VNW thêm đoạn "About FPT Software" |
| LG CNS · Senior Fullstack Java Developer (#409 ~ #820)  | 0,495    | VietnamWorks ~ TopCV | mỗi nguồn trình bày mô tả khác     |
| Thẩm mỹ OHIO · Chuyên Viên Thiết Kế (#1506 ~ #1580)     | 0,796    | TopCV ~ TopCV        | đăng lại, sửa vài câu              |

Hai cặp đầu là đúng loại trùng mà khử trùng giữa các nguồn cần bắt. Luật cũ bỏ sót cả hai, vì LSH
ở ngưỡng 0,70 không đưa chúng vào danh sách để so.

**Không gộp nhầm.** Kiểm toàn bộ (không lấy mẫu) mọi cặp cùng công ty, cùng tỉnh, trùng hẳn chức
danh trong kho: 12 cặp. 10 cặp giống ≥ 0,45 đều là trùng thật (0,495 → 1,000). 2 cặp còn lại là
hai tin khác nhau, chỉ giống 0,087 và 0,026 (#917 ~ #1571 NASANI, #908 ~ #1149 Alphaway BI Lead).
Ngưỡng 0,45 là ngưỡng cao nhất còn bắt được cặp 0,495. Mọi ngưỡng từ 0,20 tới 0,45 cho cùng kết
quả trên dữ liệu hiện có, nên chọn mức chặt nhất.

**Vẫn phải giữ điều kiện chức danh trùng hẳn.** Nới ra là precision tụt dưới 0,95 ngay:

| Gộp ≥ | Chức danh ≥ | Precision | Gộp nhầm                                                           |
| ----- | ----------- | --------- | ------------------------------------------------------------------ |
| 0,85  | 0,8         | 0,875     | Cơ Khí "Có KN" ~ "Không KN" (#1213 ~ #1216)                        |
| 0,85  | 0,5         | 0,846     | thêm Fullstack ~ Lead Fullstack (#1452 ~ #1954, mô tả giống 0,995) |
| 0,45  | 0,0         | 0,481     | 27 cặp                                                             |

Kết quả này khớp với sửa đổi #664.

**Giới hạn của số liệu.** Cả kho chỉ có 10 cặp đủ điều kiện gộp tự động. Precision 10/10 là số
thật, nhưng cận dưới khoảng tin cậy 95% chỉ là 0,72. Chưa đủ cặp để _chứng minh thống kê_ rằng
precision ≥ 0,95. Nên chấm lại bằng cùng lệnh khi kho lớn hơn, nhất là khi bật thêm nguồn
VietnamWorks và ITviec.

## 3. Thay đổi code

| File                                                                       | Thay đổi                                                                                                                                                                                                                               |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/ingestion/near_dedup.py`                                              | `MERGE_THRESHOLD` 0,85 → 0,45, chỉ áp dụng khi chức danh trùng hẳn và ≥ 30 từ. Thêm bước luôn so các cặp trùng hẳn chức danh, vì LSH ở ngưỡng 0,70 không thấy cặp 0,45–0,70. Hàng chờ admin giữ nguyên: khác chức danh mà giống ≥ 0,70 |
| `src/ingestion/dedup_eval.py`, `scripts/eval_dedup.py`                     | Mới: lấy mẫu phân tầng, xuất CSV + HTML để gán nhãn, tính precision/recall có trọng số, cận dưới Wilson, thử ngưỡng                                                                                                                    |
| `tests/unit/test_dedup_eval.py`, `tests/integration/test_eval_dedup_pg.py` | Mới. Test tích hợp kiểm `sample` không ghi gì vào DB                                                                                                                                                                                   |
| `tests/unit/test_near_dedup.py`, `tests/integration/test_near_dedup_pg.py` | Cập nhật theo luật mới. Thêm ca cùng tin ở hai nguồn giống 0,45–0,70 (được gộp) và ca trùng chức danh nhưng nội dung khác hẳn (không gộp)                                                                                              |

## 4. Khử trùng toàn kho (production, chạy thử 17/11/2026)

| Bước                      | Kết quả                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------ |
| `dedup_exact.py` (S3-T03) | 0 nhóm URL · 0 nhóm hash · **còn lại 0**: kho đã sạch trùng chính xác                                  |
| `dedup_near.py`, luật mới | 1.439 tin mở · **gộp 3** (đúng 3 cặp ở mục 2) · 18 cặp vào hoặc cập nhật hàng chờ · 0 cặp admin đã bác |
| Trước khi chạy            | 7 tin đã bị gộp (luật S3-T04) · 19 cặp đang chờ admin                                                  |

Còn lại: merge PR, rồi chạy `uv run python scripts/dedup_near.py --apply`. Lượt crawl 02:00 sau khi
merge cũng tự làm bước này.

## 5. Phát hiện ngoài phạm vi ngưỡng

- **Cùng tin nhưng tên công ty chuẩn hóa khác nhau.** Luật chỉ so trong cùng `company_id`, nên
  các cặp sau không bao giờ được so: "LOTTE Innovate Việt Nam" (VNW) ~ "LOTTE INNOVATE VIETNAM
  COMPANY LIMITED" (TopCV), giống 0,61; "CÔNG TY CỔ PHẦN CÔNG NGHỆ ALPHAWAY" ~ "Alphaway Technology",
  0,70; "CHI NHÁNH CÔNG TY TNHH THẨM MỸ OHIO" ~ "CÔNG TY CỔ PHẦN THẨM MỸ OHIO", 0,82. Cần gộp
  tên công ty (alias, tên tiếng Anh ↔ tiếng Việt, chi nhánh) ở bước chuẩn hóa thực thể. Nên tách
  thành task riêng.
- **Mô tả giống hệt nhưng là công ty khác** (ví dụ Graphic Designer của Sado, 5S Fashion và một
  công ty cùng nhóm, giống 0,96–0,98). Có thể là công ty con của cùng tập đoàn. Không gộp, vì là
  nhà tuyển dụng khác nhau.
- **NASANI** đăng nhiều tin "Tư vấn …" khác tiêu đề, khác lương, mô tả giống 0,57–0,74. Hiện gán
  là tin khác nhau (`?`). Nếu nhóm coi đó là cùng một tin thì recall giảm, precision không đổi.
