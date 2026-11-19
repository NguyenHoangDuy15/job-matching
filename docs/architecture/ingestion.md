# Luồng ingestion tin tuyển dụng (cập nhật Sprint 3)

S3-T10 · US-14 · Người viết: Tùng · Cập nhật 19/11/2026 theo `main` tại #676

Sơ đồ cũ trong README chỉ có crawl → kỹ năng (Sprint 2). Từ Sprint 3 tin vào DB bằng 3 đường, có
thêm khử trùng (S3-T03/T04/T05), vector hóa (S3-D07) và workflow lưới an toàn `post-ingest`.
Cách vận hành khử trùng: [`docs/runbook/dedup.md`](../runbook/dedup.md).

## 1. Sơ đồ

```mermaid
flowchart TD
    subgraph SRC["Nguồn (chỉ nguồn đã phép trong config/sources.yaml)"]
        ITV["ITviec · VietnamWorks<br/>JSON-LD, 1 request / 5 giây"]
        TCV["TopCV<br/>trình duyệt thật, 1 request / 30 giây"]
        FILE["File JSONL có sẵn"]
    end

    subgraph RUN["Chạy ở đâu"]
        GHA["GitHub Actions <b>crawl-daily</b><br/>02:00 VN (cron 0 19 * * * UTC)<br/>scripts/crawl.py run"]
        SH["Runner self-hosted Windows <b>topcv-self-hosted</b><br/>phút 17 mỗi 2 giờ, chỉ khi bật<br/>vars.TOPCV_SCHEDULE_ENABLED<br/>scripts/run_topcv_automation.py"]
        MAN["Chạy tay<br/>scripts/load_jsonl.py"]
    end

    ITV --> GHA
    TCV --> SH
    FILE --> MAN

    GHA --> FX["① Tỷ giá (ingestion.fx)"] --> SAVE
    SH --> CK["Checkpoint SQLite + JSONL trên máy<br/>(ingestion.topcv_sync)"] --> SAVE
    MAN --> SAVE

    subgraph SAVE["② PgStore.save — mọi đường nạp đều qua đây"]
        direction TB
        NORM["Chuẩn hóa: 34 tỉnh, lương VND, cấp bậc,<br/>hình thức làm việc, 4 section JD"]
        RAW["raw.job_snapshots (bản gốc)"]
        EX{"Khử trùng chính xác (S3-T03)<br/>1. cùng (nguồn, mã tin)<br/>2. cùng url_norm<br/>3. cùng dedup hash với tin chuẩn đang mở"}
        NORM --> RAW --> EX
        EX -- "khớp" --> ATT["Chỉ gắn thêm core.job_sources<br/>vào tin chuẩn có sẵn (kết quả duplicate)"]
        EX -- "không khớp" --> NEW["Tạo / cập nhật core.jobs<br/>+ job_sources + job_locations"]
    end

    SAVE --> CLOSE["Đóng tin: 404/410, vắng 3 lượt, hết hạn<br/>(chỉ crawl.py) · ghi ops.crawl_runs"]
    CLOSE --> NEAR

    NEAR["Gần trùng MinHash/LSH (S3-T04/T05)<br/>trên MỌI tin đang mở<br/><b>chỉ chạy trong crawl.py</b>"]
    NEAR -- "chức danh trùng hẳn, ≥ 30 từ, giống ≥ 0,45" --> MERGE["core.merge_jobs:<br/>giữ tin id nhỏ, đóng tin kia<br/>close_reason = duplicate, duplicate_of"]
    NEAR -- "còn lại, giống ≥ 0,70" --> Q[("core.dedup_candidates<br/>pending")]
    Q -- "admin: merged / distinct" --> RES["api.admin_resolve_dedup<br/>(chưa có màn admin, xem runbook)"]
    RES --> MERGE

    NEAR --> SK["③ Gắn kỹ năng + mức (skillkit.levels)<br/>core.job_skills"]
    SAVE -. "topcv_sync, load_jsonl:<br/>không chạy gần trùng" .-> SK
    SK --> EMB["④ Vector hóa theo đoạn ≤ 300 token<br/>bge-m3 (Cloudflare Workers AI)<br/>core.job_chunks"]

    PI["GitHub Actions <b>post-ingest</b><br/>phút 40 mỗi 3 giờ + khi đổi từ điển<br/>scripts/postprocess.py"] --> SK

    EMB --> DB[("Supabase<br/>core.jobs đang mở")]
    MERGE --> DB
    DB --> WEB["Web: api.v_open_jobs, chi tiết tin<br/>api.job_redirect cho link tin đã gộp (S3-H05)"]
    DB --> API["API /match/jobs (S4)"]
```

## 2. Điểm cần nhớ

| Điểm | Chi tiết | Ở đâu |
| --- | --- | --- |
| Khử trùng chính xác chạy ở **mọi** đường nạp | Nằm trong `PgStore.save`, tin trùng chỉ được gắn thêm nguồn, không tạo tin chuẩn mới | `src/ingestion/store.py`, `src/ingestion/dedup.py` |
| Gần trùng chỉ chạy sau `crawl.py run` | TopCV sync và nạp JSONL **không** gọi bước này. Tin TopCV gần trùng nhau chỉ được gộp ở lượt `crawl.py` kế tiếp (bước này so mọi tin đang mở, không riêng nguồn vừa crawl) | `src/ingestion/crawl.py` (`near_dedup_after_crawl`) |
| Gộp không xóa tin | Tin bị gộp: `status = closed`, `close_reason = duplicate`, `duplicate_of` = tin giữ lại. Nguồn và tin đã lưu chuyển sang tin giữ lại | `db/migrations/0011_exact_dedup.sql` (`core.merge_jobs`) |
| Link cũ vẫn dùng được | Web gọi `api.job_redirect` rồi chuyển sang tin giữ lại | `db/migrations/0015_cv_primary_redirect.sql` |
| ③ và ④ có lưới an toàn | `post-ingest` gắn kỹ năng và vector hóa mọi tin đang mở còn thiếu, bất kể tin vào từ đường nào | `.github/workflows/post-ingest.yml` |
| Thứ tự trong `crawl.py` | gần trùng chạy **trước** ③, để không gắn kỹ năng cho tin vừa bị gộp | `src/ingestion/crawl.py` |

## 3. So với sơ đồ Sprint 2

- Thêm đường TopCV (runner self-hosted) và nạp JSONL. Cả hai ghi qua cùng `PgStore.save`.
- Thêm khử trùng chính xác trong `PgStore.save`, gần trùng sau crawl, hàng chờ admin.
- Thêm ④ vector hóa và workflow `post-ingest`.
- Tin đã gộp có link chuyển hướng (`api.job_redirect`).
