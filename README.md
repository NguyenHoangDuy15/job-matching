# JobMatch – Team 5

Hệ thống gợi ý việc làm IT hai chiều cho thị trường Việt Nam:

- **Người tìm việc** tìm và lọc tin tuyển dụng thật, xem kỹ năng **bắt buộc / ưu tiên** của từng tin, nhận K việc hợp với CV.
- **HR** lọc N CV hợp với một JD.
- Kết quả giải thích được và có benchmark đánh giá (nDCG@10).

| Thành viên        | Vai trò                         |
| ----------------- | ------------------------------- |
| Nguyễn Hoàng Duy  | Tech lead, Ranking, Backend API |
| Đào Việt Tùng     | Data, Retrieval                 |
| Nguyễn Xuân Thịnh | Đánh giá, UI, QA, DevOps        |

Kế hoạch 8 sprint: issue trên GitHub theo milestone S1–S8 (story `US-xx`, task `Sx-Tyy/Dyy/Hyy`); file backlog gốc nằm ở ổ chung của nhóm.

## Kiến trúc

```
Cloud Run Job (02:00)                          Supabase (Postgres 16 + pgvector + Auth)
┌────────────────────────────────────┐        ┌──────────────────────────────────────┐
│ ① tỷ giá  ingestion.fx             │──────▶ │ ref     từ điển: 34 tỉnh, kỹ năng,    │
│ ② crawl   ingestion.crawl (JSON-LD)│        │         tỷ giá                         │
│   chuẩn hóa: 34 tỉnh, lương VND,   │──────▶ │ raw     bản gốc từng lượt crawl        │
│   tách section, kỹ năng + mức      │        │ core    jobs, job_locations, job_skills│
└────────────────────────────────────┘        │ app     người dùng, CV, HR (RLS)       │
                                               │ api     view + RPC cho web             │
Next.js trên Cloudflare (apps/web) ──────────▶ │ ops / mart / eval                      │
                                               └──────────────────────────────────────┘
```

Chi tiết stack và lý do chọn: `docs/adr/003-stack.md` và `docs/architecture/`.

## Đang chạy được (Sprint 2)

| Phần | Ở đâu | Ghi chú |
|---|---|---|
| Schema DB v2.0, RLS, Auth hook | `db/migrations/0001–0003` | Chạy theo thứ tự số |
| Đăng ký / đăng nhập / 3 vai trò | `apps/web` | Xem `apps/web/README.md` |
| Crawler VietnamWorks, ITviec + nạp JSONL | `src/ingestion/crawl.py`, `jsonl_import.py` | Ghi `raw.job_snapshots`, `core.jobs`, `core.job_sources` |
| Chuẩn hóa địa điểm về 34 tỉnh, gắn Remote/Hybrid | `src/ingestion/location.py` | Bảng tra trong `ref.provinces`, `ref.province_legacy` |
| Chuẩn hóa lương về VND/tháng | `src/ingestion/salary.py`, `fx.py` | Tỷ giá lấy mới mỗi lượt crawl; tin ngoại tệ tự tính lại khi tỷ giá đổi |
| Tách 4 section JD | `src/skillkit/sections.py` | Mô tả / Yêu cầu / Ưu tiên / Quyền lợi, heading Việt–Anh |
| Từ điển 379 kỹ năng + từ nhập nhằng | `config/skills.yaml`, `src/skillkit/matcher.py` | Go, R, C, .NET, Java/JS, AI... |
| Mức kỹ năng bắt buộc / ưu tiên / chỉ nhắc | `src/skillkit/levels/` | Từ điển + luật + Tầng 2 JEV-local; chạy lô bằng `label_skills.py` (gắn vào crawl ở S2-D05) |

## Bắt đầu

Cần **Python 3.11**, **uv**, **Docker** (cho DB thử), **Node 20+** (chỉ khi làm web).

```bash
uv sync
cp .env.example .env          # điền DATABASE_URL; KHÔNG commit .env
uv run pytest                 # unit test; test cần DB tự bỏ qua
```

Giao diện web: `cd apps/web && npm install && npm run dev` (chi tiết trong `apps/web/README.md`).

### Dựng DB thử ở máy

DB thật là Supabase. Trên Postgres thường cần giả lập phần `auth`, `storage` và các role của Supabase trước bằng `db/tests/supabase_ci_bootstrap.sql` (PR #620). Thứ tự chạy:

```bash
docker compose up -d db
psql "$DATABASE_URL" -f db/tests/supabase_ci_bootstrap.sql   # chỉ khi không phải Supabase
psql "$DATABASE_URL" -f db/migrations/0001_schema_v2.sql
psql "$DATABASE_URL" -f db/seed/seed_reference_data.sql      # 34 tỉnh, nhóm nghề, nguồn
psql "$DATABASE_URL" -f db/migrations/0002_fx_rates.sql
psql "$DATABASE_URL" -f db/migrations/0003_skill_tree_sections.sql
psql "$DATABASE_URL" -f db/seed/seed_skills.sql              # từ điển kỹ năng (sinh từ YAML)
psql "$DATABASE_URL" -f db/migrations/0004_job_skill_levels.sql
```

Migration và seed đều chạy lại được nhiều lần. Nếu `DATABASE_URL` có dạng `postgresql+psycopg://…` thì bỏ `+psycopg` khi dùng với `psql`.

Chạy cả test cần DB (luôn dùng DB thử, **không** dùng Supabase production):

```bash
TEST_DATABASE_URL=postgresql://app:change_me@localhost:5432/jobs uv run pytest
```

## Luồng dữ liệu tin tuyển dụng

```bash
# Crawl: tự cập nhật tỷ giá trước, rồi crawl, chuẩn hóa và ghi DB
uv run python scripts/crawl.py run --source itviec --max-jobs 50
uv run python scripts/crawl.py run --source itviec --dry-run       # không ghi DB, ghi data/raw/crawl
uv run python scripts/crawl.py probe --source vietnamworks         # kiểm cấu hình nguồn

# Nạp file JSONL có sẵn
uv run python scripts/load_jsonl.py <file.jsonl> --source topcv

# Bảo trì
uv run python scripts/update_fx.py [--dry-run]       # cập nhật tỷ giá + tính lại lương tin ngoại tệ
uv run python scripts/split_sections.py [--apply]    # tách lại 4 section từ core.jobs.jd_text
uv run python scripts/label_skills.py [--apply]      # gắn kỹ năng + mức, ghi core.job_skills
```

Chỉ crawl các nguồn đã được phép trong `config/sources.yaml`, tuân thủ `docs/data_sources.md`. Gặp 403, 429 hoặc trang chống bot thì dừng, không tìm cách vượt.

## Từ điển kỹ năng

`config/skills.yaml` là **nguồn duy nhất**. Sau khi sửa file này:

```bash
PYTHONPATH=src uv run python scripts/build_skill_seed.py   # sinh lại db/seed/seed_skills.sql
uv run pytest tests/unit/test_skill_seed.py                # CI báo đỏ nếu SQL lệch YAML
```

- **Cấu trúc:** level 1 là nhóm, khớp `ref.skill_categories`. Level 2 là kỹ năng. Level 3 là framework/công cụ con, ghi vào `ref.skills.parent_id`.
- **So khớp giữ dấu tiếng Việt**, để "gõ" không thành "go".
- **Từ nhập nhằng** ("Go", "R", "C", "AI", "React"...) khai báo `ambiguous`, `context` và `rule` ngay trong YAML. Ví dụ: chỉ nhận "Go" viết hoa khi có ngữ cảnh lập trình; loại "go live", "R&D", "hạng C"; "lương Net" không ra .NET.

## Mức kỹ năng: bắt buộc / ưu tiên (S2-D04)

Mỗi lần kỹ năng xuất hiện trong JD đi qua các bước sau:

1. **Từ điển** (`SkillMatcher`) tìm kỹ năng.
2. **Luật** (`config/skill_levels.yaml`) xét section theo heading gốc và cue trong câu: "ưu tiên", "là lợi thế", "a plus", "không bắt buộc", "tối thiểu", "must"... Câu trộn hai mức được xét theo từng vế: "Thành thạo Java, ưu tiên biết Kotlin".
3. **Tầng 2 "JEV-local"** (TF-IDF n-gram ký tự + Logistic Regression) chỉ quyết các ca luật không chắc.
4. **Gộp:** mỗi (tin, kỹ năng) giữ một dòng trong `core.job_skills`.

Kỹ năng chỉ được nhắc trong Mô tả công việc, không có cue, ghi là `mentioned`. Kỹ năng trong Quyền lợi bị bỏ.

```bash
uv run python scripts/make_silver.py                # nhãn yếu từ VietJobs, trừ 50 JD gold
uv run python scripts/train_tier2.py                # train → models/jev_local_v1.joblib
uv run python scripts/evaluate_levels.py template   # file gán tay data/eval/gold_mentions_TEMPLATE.csv
uv run python scripts/evaluate_levels.py score      # chấm trên data/eval/gold_mentions.csv
```

- **Model** không lên git. Train lại cho ra cùng model, vì seed cố định và `uv.lock` ghim scikit-learn. Chưa có file model thì pipeline chỉ dùng luật.
- **Thêm cue:** sửa `config/skill_levels.yaml` rồi thêm ca vào `tests/unit/test_levels_rules.py`.
- **`extractor`:** `dict` là luật quyết, `jev` là Tầng 2 quyết, `human` là sửa tay. Chạy lại pipeline không ghi đè và không xóa dòng `human`.
- **`source_detail`:** cho biết luật nào đã quyết, gồm `rule_neg`, `rule_section`, `rule_cue`, `rule_mixed`, `rule_desc`, `model`, `fallback`.

## Script đo chất lượng

| Lệnh (thêm `PYTHONPATH=src` nếu script yêu cầu) | Đo gì |
|---|---|
| `scripts/location_report.py --input <csv>` | % tin có tỉnh chuẩn hoặc Remote (US-09/AC3, mục tiêu ≥ 95%) |
| `scripts/salary_report.py --input <csv>` | % lương đọc được, phân bố tiền tệ, chuỗi chưa đọc được |
| `scripts/build_jd_gold.py` → `scripts/section_report.py` | Tách section trên 50 JD gán tay (mục tiêu ≥ 90%) |
| `scripts/skill_coverage.py` | Độ phủ từ điển trên danh sách kỹ năng thật |
| `scripts/profile_dataset.py`, `make_snapshot.py` | Hồ sơ dữ liệu TopCV, snapshot 200 JD |

Bộ 50 JD gán tay chứa nội dung tin thật nên **không lên git**. Repo chỉ giữ nhãn (`tests/fixtures/jd_gold/labels.yaml`); ai có `data/interim/vietjobs_it.csv` chạy `build_jd_gold.py` sẽ ra lại đúng bộ đó.

## Cấu trúc repo

| Thư mục | Nội dung |
|---|---|
| `src/ingestion/` | Crawler, chuẩn hóa tỉnh / lương / tỷ giá, ghi DB |
| `src/skillkit/` | Taxonomy kỹ năng, so khớp, tách section JD |
| `src/api/` | FastAPI (matching, giải thích — các sprint sau) |
| `src/{retrieval,ranking,screening,cvparser,explain,eval,batch,common}/` | Module các sprint sau; module chỉ gọi nhau qua hàm công khai trong `__init__.py` |
| `apps/web/` | Next.js 16 + Supabase Auth, deploy Cloudflare |
| `db/migrations/`, `db/seed/` | Schema và dữ liệu tham chiếu, chạy theo thứ tự số |
| `config/` | `skills.yaml`, `jd_headings.yaml`, `sources.yaml`, `salary.yaml`, `column_map.yaml` |
| `scripts/` | Lệnh chạy tay (crawl, nạp, đo, sinh seed) |
| `tests/` | `unit/` (CI), `integration/` (cần `TEST_DATABASE_URL`), `fixtures/` |
| `docs/` | `adr/` quyết định kiến trúc, `data_sources.md` quyền dùng nguồn, `labeling/`, `learning/`, `notes/`, `ui/` |
| `ui/` | Streamlit demo cũ (S1) |
| `data/` | Dữ liệu, **không lên git** (xem `data/README.md`) |

`dags/` và `dbt/` đang để trống: ADR-003 tạm bỏ Airflow và dbt.

## CI

Mỗi PR và mỗi lần push lên `main` chạy các job sau:

| Job | Nội dung |
|---|---|
| `lint` | `uv sync --locked`, `ruff check`, `ruff format --check` |
| `test` | `uv run pytest -q` |
| `gitleaks` | Quét secret |
| `web` | `npm ci`, lint và kiểm kiểu cho `apps/web` |

## Quy ước

- `main` được bảo vệ: PR cần 1 approve của code owner và CI xanh. PR nên dưới 400 dòng.
- Mỗi task một nhánh theo mã task, ví dụ `feat/S2-D02-normalize-salary`. Commit và PR ghi mã task; dùng `Closes #<issue>` để tự đóng issue khi merge.
- Không commit `.env`, `kaggle.json`, API key, CV thật. Không log nội dung CV. Không gửi PII cho LLM.
- Trọng số, ngưỡng, nguồn, từ điển nằm trong `config/*.yaml`, không viết cứng trong code.
- Đổi schema thì thêm migration mới (`db/migrations/000N_*.sql`), không sửa migration đã merge.
