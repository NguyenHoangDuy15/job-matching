# Luồng ingestion tin tuyển dụng (Sprint 3)

S3-T10 · US-14 · Người viết: Tùng · Đối chiếu mã nguồn ngày 19/11/2026

Mọi nguồn chỉ được chạy khi đã được cho phép trong `config/sources.yaml`. Ba đường nạp production
đều chuẩn hóa và lưu bằng `PgStore.save`; khác nhau ở cách thu thập, checkpoint và các bước bảo trì
sau crawl. Cách vận hành khử trùng: [`docs/runbook/dedup.md`](../runbook/dedup.md).

## 1. Sơ đồ

```mermaid
flowchart TD
    subgraph SRC["Nguồn đã được phép trong config/sources.yaml"]
        ITV["ITviec<br/>JSON-LD · tối thiểu 5 giây/request"]
        VNW["VietnamWorks<br/>JSON-LD · tối thiểu 5 giây/request"]
        TCV["TopCV<br/>trình duyệt thật · tối thiểu 30 giây/request"]
        FILE["File JSONL có sẵn"]
    end

    subgraph RUN["Nơi chạy"]
        DAILY["GitHub Actions crawl-daily<br/>02:00 VN · cron 0 19 * * * UTC<br/>lịch tự động hiện chỉ chạy ITviec"]
        MANCRAWL["crawl-daily chạy thủ công<br/>có thể chọn VietnamWorks"]
        SH["Runner Windows topcv-self-hosted<br/>phút 17 mỗi 2 giờ<br/>chỉ chạy lịch khi TOPCV_SCHEDULE_ENABLED=true"]
        LOAD["Chạy tay<br/>scripts/load_jsonl.py"]
    end

    ITV --> DAILY
    VNW --> MANCRAWL
    TCV --> SH
    FILE --> LOAD

    DAILY --> CRAWL["scripts/crawl.py run<br/>đồng bộ tỷ giá"]
    MANCRAWL --> CRAWL
    SH --> TCVC["src/ingestion/topcv.py"]
    TCVC --> CK["Checkpoint cục bộ<br/>SQLite + JSONL"]
    CK --> SYNC["src/ingestion/topcv_sync.py"]

    CRAWL --> SAVE
    SYNC --> SAVE
    LOAD --> SAVE

    subgraph SAVE["PgStore.save — mọi đường nạp production đều qua đây"]
        direction TB
        NORM["Chuẩn hóa tỉnh, lương VND, seniority/cấp bậc,<br/>hình thức làm việc và các section JD"]
        RAW["Ghi raw.job_snapshots — bản gốc không ghi đè"]
        SRCID{"Đã có cùng<br/>source + source_job_id?"}
        URL{"Có cùng url_norm<br/>ở tin chuẩn chưa bị gộp?"}
        HASH{"Có cùng dedup_hash<br/>ở tin chuẩn đang mở?"}
        UPSERT["Không đổi hoặc cập nhật tin chuẩn<br/>và gắn/cập nhật core.job_sources"]
        ATTACH["Giữ nguyên tin chuẩn<br/>chỉ gắn core.job_sources · duplicate"]
        NEW["Tạo core.jobs mới<br/>+ job_sources + job_locations"]

        NORM --> RAW --> SRCID
        SRCID -- "có" --> UPSERT
        SRCID -- "không" --> URL
        URL -- "có" --> UPSERT
        URL -- "không" --> HASH
        HASH -- "có" --> ATTACH
        HASH -- "không" --> NEW
    end

    SAVE --> RUNLOG["Ghi ops.crawl_runs<br/>crawl.py · topcv_sync · load_jsonl"]

    CRAWL -. "bảo trì riêng của crawl.py" .-> CLOSE["Kiểm tra và đóng tin<br/>404/410 · vắng 3 lượt quét đủ · hết hạn"]
    CLOSE --> NEAR["Gần trùng MinHash/LSH trên mọi tin đang mở<br/>cùng công ty và tỉnh tương thích"]
    NEAR -- "Jaccard ≥ 0,45<br/>title chuẩn hóa trùng hẳn · ≥ 30 token" --> MERGE["core.merge_jobs<br/>giữ ID nhỏ · đóng ID còn lại<br/>close_reason=duplicate · duplicate_of"]
    NEAR -- "Jaccard ≥ 0,70 nhưng chưa đủ chắc" --> QUEUE[("core.dedup_candidates<br/>pending")]
    QUEUE -- "admin: merged / distinct" --> RESOLVE["api.admin_resolve_dedup<br/>hiện xử lý theo runbook"]
    RESOLVE --> MERGE

    NEAR --> SKILL
    SYNC -. "không chạy gần trùng" .-> SKILL
    LOAD -. "không chạy gần trùng" .-> SKILL
    SKILL["Gắn kỹ năng + mức<br/>core.job_skills"] --> EMB["Vector hóa đoạn ≤ 300 token<br/>bge-m3 · core.job_chunks"]

    POST["GitHub Actions post-ingest<br/>phút 40 mỗi 3 giờ và khi đổi code/từ điển liên quan<br/>scripts/postprocess.py"] --> SKILL

    EMB --> DB[("Supabase<br/>core.jobs đang mở")]
    MERGE --> DB
    DB --> WEB["Web/API hiện có<br/>api.v_open_jobs · api.v_job_detail<br/>api.job_redirect cho link tin đã gộp"]
    DB -. "S4: có code, chưa bật trên Render" .-> MATCH["API /match/jobs"]
```

> TopDev và crawler trình duyệt mới trong working tree hiện là đường local/manual, chưa có workflow
> production. Chỉ thêm chúng vào nhánh production của sơ đồ sau khi migration, lịch chạy và quy trình
> đồng bộ đã được merge và triển khai.

## 2. Điểm cần nhớ

| Điểm | Chi tiết | Ở đâu |
| --- | --- | --- |
| Lịch `crawl-daily` | Lịch 02:00 VN hiện chỉ chạy ITviec; VietnamWorks được chọn khi chạy thủ công | `.github/workflows/crawl-daily.yml` |
| Checkpoint TopCV | `topcv.py` ghi SQLite/JSONL; `topcv_sync.py` chỉ đồng bộ phần chưa đẩy lên PostgreSQL | `src/ingestion/topcv.py`, `src/ingestion/topcv_sync.py` |
| Khử trùng chính xác | Cùng mã nguồn hoặc URL có thể cập nhật tin chuẩn; chỉ nhánh trùng `dedup_hash` khác nguồn mới chỉ gắn thêm nguồn với kết quả `duplicate` | `src/ingestion/store.py` |
| Gần trùng | Tự gộp từ `0,45` khi title chuẩn hóa trùng hoàn toàn và JD đủ 30 token (S3-T05, trước là `0,85`); từ `0,70` đưa vào hàng chờ nếu chưa đủ chắc | `src/ingestion/near_dedup.py`, `src/ingestion/dedup_pg.py` |
| Gần trùng chỉ chạy trong `crawl.py` | TopCV sync và nạp JSONL chạy thẳng sang hậu xử lý; chúng được xét gần trùng ở lượt `crawl.py` sau | `src/ingestion/crawl.py` |
| `ops.crawl_runs` | Cả `crawl.py`, `topcv_sync.py` và `load_jsonl` đều ghi run khi có lượt nạp | `src/ingestion/store.py`, `src/ingestion/topcv_sync.py`, `src/ingestion/jsonl_import.py` |
| Gộp không xóa tin | Tin bị gộp được đóng, đặt `close_reason=duplicate`, `duplicate_of` trỏ tới tin giữ lại; nguồn và saved jobs được chuyển sang tin giữ | `db/migrations/0011_exact_dedup.sql` |
| Link cũ của tin đã gộp | Web gọi `api.job_redirect` rồi chuyển sang tin giữ lại (S3-H05) | `db/migrations/0015_cv_primary_redirect.sql` |
| Lưới an toàn hậu xử lý | `post-ingest` bổ sung kỹ năng/vector còn thiếu cho tin đang mở, bất kể đường nạp | `.github/workflows/post-ingest.yml` |

## 3. So với sơ đồ Sprint 2

- Có đường TopCV qua runner self-hosted và đường nạp JSONL; cả hai dùng cùng `PgStore.save`.
- Khử trùng chính xác nằm trong `PgStore.save`; gần trùng chạy sau `crawl.py` và có hàng chờ admin.
- Có vector hóa theo đoạn và workflow `post-ingest` để bắt phần hậu xử lý còn thiếu.
- Link cũ của tin đã gộp chuyển sang tin giữ lại (`api.job_redirect`, S3-H05).
- `/match/jobs` đã có code (S4-D04) nhưng chưa bật trên Render, chưa phải chức năng production.
