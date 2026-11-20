# Runbook khử trùng tin tuyển dụng

Tài liệu này mô tả đúng hành vi hiện tại của `PgStore.save` và bước gần trùng chạy sau
`scripts/crawl.py run`.

## 1. Khử trùng chính xác

`PgStore.save` luôn ghi `raw.job_snapshots` trước, sau đó xét theo thứ tự:

1. Cùng `(source_id, source_job_id)`: giữ cùng tin chuẩn; trả về `unchanged` nếu nội dung không đổi,
   hoặc `updated` nếu nội dung đổi.
2. Không trùng mã nguồn nhưng cùng `url_norm` với tin chuẩn chưa bị gộp (`duplicate_of is null`): gắn nguồn và có thể cập nhật tin
   chuẩn từ nội dung mới.
3. Không trùng URL nhưng cùng `dedup_hash` với tin chuẩn đang mở: giữ nguyên nội dung tin chuẩn, chỉ
   gắn thêm `core.job_sources`; kết quả là `duplicate`.
4. Không khớp: tạo `core.jobs`, `core.job_sources` và `core.job_locations` mới.

Không xóa trực tiếp snapshot hoặc tin chuẩn để xử lý trùng.

## 2. Gần trùng

Bước gần trùng xét mọi tin đang mở, không chỉ nguồn vừa crawl. Một cặp chỉ được so sánh khi cùng công
ty và tỉnh tương thích. Điểm là Jaccard trên shingles ba từ:

- Tự động gộp khi điểm `>= 0.45`, title sau chuẩn hóa trùng hoàn toàn và mỗi JD có ít nhất 30 token
  (ngưỡng chọn ở S3-T05, `reports/s3_t05_khu_trung.md`; trước đó là `0.85`).
- Đưa vào `core.dedup_candidates` khi điểm `>= 0.70` nhưng chưa đủ điều kiện tự gộp.
- Dưới `0.70`: không tạo ứng viên.

Khi gộp, `core.merge_jobs` giữ ID nhỏ hơn, chuyển nguồn/saved jobs sang tin giữ lại, rồi đóng tin còn
lại bằng `close_reason = 'duplicate'` và `duplicate_of = <id tin giữ>`.

## 3. Kiểm tra vận hành

Kiểm tra số ứng viên theo trạng thái trong Supabase SQL Editor:

```sql
select status, count(*)
from core.dedup_candidates
group by status
order by status;
```

Kiểm tra các tin đã gộp:

```sql
select id, duplicate_of, closed_at
from core.jobs
where close_reason = 'duplicate'
order by closed_at desc
limit 50;
```

Nếu điểm hoặc điều kiện gộp có vẻ bất thường, dừng việc xử lý hàng chờ và kiểm tra mẫu trong
`src/ingestion/near_dedup.py` cùng `src/ingestion/dedup_pg.py`. Không sửa trực tiếp `duplicate_of`
hoặc xóa `core.jobs`; dùng hàm/API xử lý dedup để giữ quan hệ nguồn nhất quán.
