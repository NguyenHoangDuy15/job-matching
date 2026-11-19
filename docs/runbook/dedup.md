# Runbook: khử trùng tin tuyển dụng

S3-T10 · US-14 · Người viết: Tùng · Cập nhật 19/11/2026 theo `main` tại #676

Tài liệu cho người vận hành: kiểm tra khử trùng có chạy đúng không, chạy tay khi cần, duyệt hàng
chờ admin, sửa khi gộp nhầm. Sơ đồ toàn luồng nạp tin: [`docs/architecture/ingestion.md`](../architecture/ingestion.md).
Lý do chọn ngưỡng: [`reports/s3_t05_khu_trung.md`](../../reports/s3_t05_khu_trung.md).

> **Dùng DB production cẩn thận.** Mọi lệnh `--apply` và mọi câu `update` / `select core.merge_jobs`
> dưới đây ghi thẳng vào Supabase dùng chung. Luôn chạy bản thử (không `--apply`) hoặc câu `select`
> trước, đọc kết quả, rồi mới ghi. Báo nhóm trước khi ghi tay.

## 1. Khử trùng hoạt động thế nào

Có 2 lớp. Cả hai đều **không xóa tin**: tin bị gộp có `status = 'closed'`,
`close_reason = 'duplicate'`, `duplicate_of` = id tin giữ lại. Mọi `core.job_sources` và
`app.saved_jobs` của tin bị gộp chuyển sang tin giữ lại (`core.merge_jobs`, migration 0011). Link
cũ của tin bị gộp tự chuyển sang tin giữ lại (`api.job_redirect`, migration 0015).

| Lớp | Khi nào chạy | Luật | Code |
| --- | --- | --- | --- |
| **Trùng chính xác** (S3-T03) | Mỗi lần ghi một tin, ở **mọi** đường nạp (crawl, TopCV sync, JSONL) | Tin nguồn mới khớp tin chuẩn theo thứ tự: cùng (nguồn, mã tin) → cùng URL chuẩn hóa (`url_norm`) → cùng dedup hash với tin chuẩn **đang mở**. Khớp thì chỉ gắn thêm nguồn | `PgStore.save` trong `src/ingestion/store.py`, `src/ingestion/dedup.py` |
| **Gần trùng** (S3-T04, ngưỡng S3-T05) | Sau mỗi lượt `scripts/crawl.py run` (workflow `crawl-daily`), so **mọi** tin đang mở | Chỉ so tin cùng công ty, có chung tỉnh. Độ giống = Jaccard cụm 3 từ của chức danh + mô tả. Chức danh trùng hẳn, cả hai ≥ 30 từ, giống ≥ 0,45 → **gộp tự động**. Còn lại mà giống ≥ 0,70 → **hàng chờ admin** `core.dedup_candidates` | `src/ingestion/near_dedup.py`, `src/ingestion/dedup_pg.py` |

**Dedup hash** = SHA-256 của chức danh + công ty (`name_norm`) + tỉnh + mô tả, tất cả đã chuẩn hóa
(chữ thường, bỏ dấu, bỏ dấu câu). Không tính hash (null, không gộp theo hash) khi mô tả sau chuẩn
hóa ngắn hơn 200 ký tự hoặc thiếu công ty. Phiên bản cách tính: `DEDUP_HASH_VERSION` trong
`src/ingestion/dedup.py`.

**Tin giữ lại:** trùng URL thì ưu tiên tin đang mở, rồi id nhỏ nhất. Trùng hash và gần trùng thì
giữ id nhỏ nhất.

**Lưu ý:** TopCV sync (`topcv-self-hosted`) và `scripts/load_jsonl.py` chỉ có lớp trùng chính
xác. Tin TopCV gần trùng nhau chỉ được gộp ở lượt `crawl.py run` kế tiếp. Muốn gộp ngay sau một
lượt nạp TopCV lớn thì chạy `scripts/dedup_near.py` (mục 3).

### Tham số

| Hằng | Giá trị | File |
| --- | --- | --- |
| `MIN_DESCRIPTION_CHARS` | 200 | `src/ingestion/dedup.py` |
| `DEDUP_HASH_VERSION` | `dedup-1` | `src/ingestion/dedup.py` |
| `MERGE_THRESHOLD` | 0,45 (chỉ khi chức danh trùng hẳn) | `src/ingestion/near_dedup.py` |
| `REVIEW_THRESHOLD` | 0,70 | `src/ingestion/near_dedup.py` |
| `TITLE_MERGE_THRESHOLD` | 1,0 (trùng hẳn sau chuẩn hóa) | `src/ingestion/near_dedup.py` |
| `MIN_TOKENS_TO_MERGE` | 30 từ | `src/ingestion/near_dedup.py` |
| `SHINGLE_WORDS`, `NUM_PERM` | 3 từ, 128 | `src/ingestion/near_dedup.py` |

## 2. Kiểm tra hằng ngày (chỉ đọc)

Chạy trong Supabase → SQL Editor, hoặc `psql "$DATABASE_URL"`. Các câu này chỉ `select`.

**a) Log lượt crawl.** Trong log GitHub Actions `crawl-daily`, bước "Crawl, upsert, …" phải có:

    == gần trùng ==
      so <N> tin mở · gộp <x> · vào hàng chờ <y> · admin đã bác <z> · dọn <w> cặp chờ đã đóng

Có dòng `✗ gộp tin gần trùng lỗi` thì xem mục 6. Có dòng `! DB chưa chạy 0011_exact_dedup.sql`
thì DB thiếu migration 0011.

**b) Bất biến, mọi câu phải ra 0:**

```sql
-- Trùng chính xác còn sót: cùng url_norm ở 2 tin chuẩn chưa gộp, hoặc cùng dedup hash ở 2 tin đang mở
select
  (select count(*) from (
     select 1 from core.job_sources s join core.jobs j on j.id = s.job_id
      where s.url_norm is not null and j.duplicate_of is null
      group by s.url_norm having count(distinct s.job_id) > 1) u)
+ (select count(*) from (
     select 1 from core.jobs
      where origin = 'crawled' and status = 'open' and duplicate_of is null and content_hash is not null
      group by content_hash having count(*) > 1) h) as trung_chinh_xac_con_lai;

-- Chuỗi gộp (tin trỏ về một tin cũng đã bị gộp)
select count(*) from core.jobs d join core.jobs k on k.id = d.duplicate_of
 where k.duplicate_of is not null;

-- Tin đã gộp mà chưa đóng, hoặc vẫn còn giữ nguồn
select count(*) from core.jobs d
 where d.duplicate_of is not null
   and (d.status <> 'closed' or exists (select 1 from core.job_sources s where s.job_id = d.id));

-- Nguồn chưa có url_norm
select count(*) from core.job_sources where url_norm is null;
```

**c) Xem gộp gần đây và hàng chờ:**

```sql
-- 20 lần gộp gần nhất
select d.id as tin_gop, d.duplicate_of as tin_giu, left(d.title, 60) as chuc_danh,
       d.closed_at at time zone 'Asia/Ho_Chi_Minh' as luc_gop
  from core.jobs d where d.close_reason = 'duplicate'
 order by d.closed_at desc limit 20;

-- Hàng chờ admin, giống nhất trước
select c.job_a, c.job_b, round(c.similarity::numeric, 2) as giong,
       a.title as chuc_danh_a, b.title as chuc_danh_b
  from core.dedup_candidates c
  join core.jobs a on a.id = c.job_a
  join core.jobs b on b.id = c.job_b
 where c.status = 'pending'
 order by c.similarity desc;
```

**Số liệu production lúc 19/11/2026 10:35** (để so khi kiểm sau):

| Chỉ số | Giá trị |
| --- | --- |
| Tin chuẩn đang mở (`origin = 'crawled'`) | 1.431 |
| Tin đã gộp (`close_reason = 'duplicate'`) | 10 (gộp lúc chạy S3-T05 `--apply`, 18/11) |
| Hàng chờ `pending` / `merged` / `distinct` | 17 / 1 / 0 |
| Trùng chính xác còn lại | 0 |
| Cặp gần trùng đủ điều kiện gộp tự động mà chưa gộp | 0 (tính lại bằng `find_near_duplicates`, chỉ đọc) |
| Các bất biến ở mục b | đều 0 |

## 3. Chạy tay

Hai script đều mặc định **chạy thử**: làm hết các bước trong một transaction rồi rollback, nên số
liệu in ra giống khi ghi thật. Chạy lại nhiều lần được. Cần `DATABASE_URL` (biến môi trường hoặc
`.env`).

```bash
uv run python scripts/dedup_exact.py              # chạy thử: in số tin sẽ gộp
uv run python scripts/dedup_exact.py --apply      # ghi thật
uv run python scripts/dedup_near.py               # chạy thử: in cặp gộp / vào hàng chờ
uv run python scripts/dedup_near.py --apply       # ghi thật
```

Chạy `dedup_exact.py` **trước** `dedup_near.py`. `dedup_exact.py` thoát mã 1 khi
`trùng chính xác còn lại` khác 0.

| Khi nào | Chạy gì |
| --- | --- |
| Vừa chạy migration 0011 trên một DB mới | `dedup_exact.py --apply` một lần, rồi `dedup_near.py --apply` |
| Đổi cách chuẩn hóa trong `src/ingestion/dedup.py` (`normalize_key`, công ty, tỉnh…) | Tăng `DEDUP_HASH_VERSION`, merge, rồi `dedup_exact.py --apply` để tính lại hash cho tin cũ |
| Đổi ngưỡng trong `near_dedup.py` | Merge, rồi `dedup_near.py` (thử), xem kỹ các cặp `merge` in ra, rồi `--apply` |
| Vừa nạp lô TopCV / JSONL lớn, muốn gộp ngay không chờ 02:00 | `dedup_near.py` rồi `--apply` |
| Lượt crawl báo lỗi ở bước gần trùng | Sửa nguyên nhân (mục 6) rồi `dedup_near.py --apply` |

Thêm `--sample 50` để in nhiều cặp hơn khi kiểm tay.

## 4. Duyệt hàng chờ admin

Hàng chờ là `core.dedup_candidates` có `status = 'pending'`. Các cặp ở đây khác chức danh hoặc mô
tả ngắn, nên máy không tự gộp.

**Quy ước quyết định** (giống nhãn S3-T05): hai tin là **trùng** khi cùng vị trí, cùng cấp bậc,
cùng nơi làm việc, chỉ khác cách viết, nguồn hoặc lần đăng. **Khác cấp bậc** (Lead / không Lead,
Senior / không Senior), khác yêu cầu kinh nghiệm kèm lương khác, hoặc khác mã tuyển dụng thì là
**hai tin khác nhau**. Ví dụ cặp `1452 ~ 1954` "Fullstack Web Developer" ~ "Lead Fullstack
Developer" giống 0,99 nhưng là hai tin.

Mở hai tin cạnh nhau để so: `https://jobmatch-web.dtt-jobmatch.workers.dev/viec-lam/<public_id>`
(`select id, public_id from core.jobs where id in (<a>, <b>)`).

**Web chưa có màn duyệt** (`apps/web/src/app/admin/page.tsx` mới là trang giữ chỗ). Hàm
`api.admin_resolve_dedup` đòi JWT có vai trò admin nên **không gọi được từ SQL Editor**. Cho tới
khi có màn admin, duyệt bằng SQL Editor như sau. Thay `:a`, `:b` bằng số `job_a`, `job_b` của cặp
(`a < b`); SQL Editor không hiểu biến `:a`, chỉ `psql` mới hiểu.

```sql
-- Trùng → gộp. Giữ tin id nhỏ (a). core.merge_jobs tự đổi cặp này sang 'merged'.
begin;
select core.merge_jobs(:a, :b);
insert into app.audit_log (actor_role, action, entity, entity_id, detail)
values ('admin', 'dedup_resolved', 'dedup', :a || ':' || :b,
        jsonb_build_object('job_a', :a, 'job_b', :b, 'decision', 'merged', 'via', 'sql_editor'));
commit;

-- Khác nhau → đánh dấu distinct. Các lượt gần trùng sau sẽ bỏ qua cặp này.
begin;
update core.dedup_candidates
   set status = 'distinct', reviewed_at = now()
 where job_a = :a and job_b = :b and status = 'pending';
insert into app.audit_log (actor_role, action, entity, entity_id, detail)
values ('admin', 'dedup_resolved', 'dedup', :a || ':' || :b,
        jsonb_build_object('job_a', :a, 'job_b', :b, 'decision', 'distinct', 'via', 'sql_editor'));
commit;
```

Cặp `pending` có một tin đã đóng (hết hạn, bị gỡ, bị gộp) được lượt gần trùng sau tự xóa khỏi
hàng chờ, không cần duyệt.

## 5. Gộp nhầm: tách lại

Chưa có hàm tách. `core.merge_jobs` chuyển nguồn và tin đã lưu sang tin giữ lại, nên tách phải làm
tay. Ví dụ tin `:dup` bị gộp nhầm vào `:keep`:

```sql
-- 1. Xem nguồn đang nằm ở tin giữ lại; tìm nguồn vốn là của tin bị gộp
--    (so chức danh trong bản gốc raw.job_snapshots với core.jobs.title của từng tin)
select s.source_id, s.source_job_id, s.url, s.first_seen_at,
       (select r.payload ->> 'title' from raw.job_snapshots r
         where r.source_id = s.source_id and r.source_job_id = s.source_job_id
         order by r.fetched_at desc limit 1) as chuc_danh_goc
  from core.job_sources s where s.job_id = :keep;
select id, title from core.jobs where id in (:keep, :dup);

begin;
-- 2. Trả nguồn về tin bị gộp (lặp cho từng nguồn tìm được ở bước 1)
update core.job_sources set job_id = :dup
 where source_id = :source_id and source_job_id = :source_job_id;

-- 3. Mở lại tin bị gộp
update core.jobs
   set status = 'open', close_reason = null, closed_at = null, duplicate_of = null, updated_at = now()
 where id = :dup;

-- 4. Ghi cặp là distinct để lượt gần trùng sau không gộp lại
insert into core.dedup_candidates (job_a, job_b, similarity, status, reviewed_at)
values (least(:keep, :dup), greatest(:keep, :dup), 0, 'distinct', now())
on conflict (job_a, job_b) do update set status = 'distinct', reviewed_at = now();
commit;
```

Giới hạn của cách tách tay:

- Tin đã lưu (`app.saved_jobs`) đã chuyển sang tin giữ lại thì không biết người dùng lưu tin nào,
  nên để nguyên.
- `first_seen_at` / `last_seen_at` của tin giữ lại đã lấy theo cả hai tin, không trả lại.
- Đánh dấu `distinct` chỉ chặn **gần trùng**. Nếu hai tin có cùng dedup hash thì lần chạy
  `dedup_exact.py --apply` sau vẫn gộp lại. Khi đó phải sửa luật hash (mục 7), không tách tay.

Mở lại tin xong, gắn kỹ năng và vector cho tin đó sẽ được `post-ingest` tự làm (≤ 3 giờ), hoặc
chạy `uv run python scripts/postprocess.py`.

## 6. Sự cố thường gặp

| Dấu hiệu | Nguyên nhân hay gặp | Xử lý |
| --- | --- | --- |
| Log crawl có `✗ gộp tin gần trùng lỗi: …` và job đỏ | Lỗi SQL / timeout DB. Bước này đã rollback, dữ liệu crawl không mất | Đọc lỗi; sửa xong chạy `dedup_near.py --apply` |
| `! DB chưa chạy 0011_exact_dedup.sql` | DB thiếu cột `duplicate_of` / `url_norm` | Chạy `db/migrations/0011_exact_dedup.sql`, rồi `dedup_exact.py --apply` |
| Bất biến "trùng chính xác còn lại" khác 0 | Tin vào lúc DB chưa có 0011, hoặc vừa đổi cách chuẩn hóa | `dedup_exact.py` (thử) rồi `--apply` |
| Hàng chờ tăng nhanh sau một lượt nạp | Một công ty đăng nhiều tin cùng mẫu mô tả, khác cấp bậc | Bình thường. Duyệt `distinct` theo mục 4 |
| Người dùng báo hai tin giống hệt trên web | Khác công ty sau chuẩn hóa (tên viết khác), khác tỉnh, hoặc mô tả < 200 ký tự | Kiểm `core.companies.name_norm` và `core.job_locations` của hai tin. Gộp tay bằng `select core.merge_jobs(<id nhỏ>, <id lớn>)` |
| Link tin cũ báo "Không tìm thấy" | Tin hết hạn / bị gỡ (không phải gộp), hoặc tin giữ lại cũng đã đóng | `select api.job_redirect('<public_id>')` trả null nghĩa là tin không bị gộp |
| Hai tin khác nhau bị gộp | Luật sai với một mẫu mới | Tách theo mục 5, ghi lại cặp đó để thêm vào bộ chấm của S3-T05 |

## 7. Đổi ngưỡng hoặc luật

Không sửa ngưỡng theo cảm tính. Làm lại vòng đo của S3-T05:

```bash
uv run python scripts/eval_dedup.py sample --out reports/s3_t05/pairs.csv   # chỉ đọc DB
# gán nhãn cột `nhan` (1 = trùng, 0 = khác)
uv run python scripts/eval_dedup.py score reports/s3_t05/pairs.csv --report reports/s3_t05/score.md
```

Nghiệm thu: precision ≥ 0,95 cho phần gộp tự động. Ghi số trước / sau vào PR, rồi làm theo
mục 3. Nên đo lại khi kho lớn hơn hoặc khi bật thêm nguồn, vì lần đo 17/11 chỉ có 10 cặp đủ điều
kiện gộp tự động (cận dưới khoảng tin cậy 95% là 0,72).
