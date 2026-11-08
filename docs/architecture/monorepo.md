# Đề xuất cấu trúc monorepo

S1-H08 · Người viết: Thịnh · Trạng thái: **đề xuất, chốt ở Sprint Planning 09/11**

Kế hoạch v2 (Drive 07/11) đổi kiến trúc: web Next.js trên Cloudflare, API matching FastAPI trên Cloud Run, pipeline thu thập trên Cloud Run Jobs, dữ liệu trên Supabase. Repo hiện vẫn là một gói Python `src/` + Streamlit `ui/` + Docker Compose. Tài liệu này đề xuất cấu trúc mới và thứ tự chuyển để không làm gãy việc đang dở của ai.

## 1. Cấu trúc đích

```
apps/
  web/                 Next.js (App Router, TypeScript, Tailwind, shadcn/ui) → Cloudflare (OpenNext)
services/
  api/                 FastAPI: Top N, chấm 1 JD, đọc CV → Cloud Run
    src/api/
    tests/
    Dockerfile
pipelines/             crawl → chuẩn hóa → trích kỹ năng → embedding → Cloud Run Jobs
  src/pipelines/
  tests/
  Dockerfile
packages/              (đề xuất thêm) thư viện Python dùng chung cho api và pipelines
  skillkit/            taxonomy, normalize, extract_skills
db/
  migrations/          migration Supabase (tách từ schema.sql v2.0)
  seed/                seed_reference_data.sql
  tests/               rls_test.sql, supabase_ci_bootstrap.sql
config/                sources.yaml, column_map.yaml (dùng chung)
docs/
.github/
pyproject.toml         gốc workspace uv (ruff, pytest cấu hình chung)
uv.lock                một file khóa cho mọi gói Python
```

Vì sao có `packages/skillkit`: trích kỹ năng chạy ở **cả hai nơi**, pipeline (gắn thẻ kỹ năng cho tin) và API (đọc kỹ năng từ CV, JD người dùng dán). Kế hoạch yêu cầu "cùng một module trích kỹ năng và cùng công thức điểm cho cả ba loại JD", nên module phải nằm ở chỗ chung thay vì chép sang hai nơi.

## 2. Công cụ

| Phần | Công cụ | Ghi chú |
|---|---|---|
| Python | [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): `[tool.uv.workspace] members = ["services/api", "pipelines", "packages/*"]` | Một `uv.lock` ở gốc; gói dùng chung khai báo `skillkit = { workspace = true }` |
| Lint Python | ruff cấu hình ở `pyproject.toml` gốc | `uv run ruff check .` vẫn quét toàn repo như hiện tại |
| Web | npm trong `apps/web` | Chưa cần Turborepo/pnpm workspace khi chỉ có một app JS |
| DB | Supabase CLI: `supabase db push` | Thay Alembic; schema nằm trong `db/migrations` |

## 3. Chuyển từ cấu trúc hiện tại

| Hiện tại | Chuyển tới | Người quyết |
|---|---|---|
| `src/skillkit/` + `tests/unit` liên quan | `packages/skillkit/` | Duy |
| `src/api/`, `src/cvparser/`, `src/ranking/`, `src/retrieval/`, `src/explain/`, `src/eval/`, `src/screening/`, `src/batch/` | `services/api/src/api/…` (gói rỗng chỉ có `__init__.py` thì bỏ, tạo lại khi làm) | Duy |
| `src/ingestion/`, `scripts/*.py` | `pipelines/` | Tùng |
| `src/common/` | tách: phần dùng chung → `packages/`, phần riêng → gói dùng nó | Duy, Tùng |
| `migrations/`, `sql/` | `db/` (migration Supabase); `sql/practice.sql` → `docs/learning/` | Tùng |
| `ui/app.py` (Streamlit) | bỏ khỏi sản phẩm; Streamlit chỉ còn cho notebook phân tích nội bộ | Thịnh |
| `compose.yaml`, `Dockerfile` | mỗi service một `Dockerfile`; compose chỉ còn cho chạy thử cục bộ nếu nhóm muốn | Thịnh, Tùng |
| `dags/`, `dbt/` (chỉ có `.gitkeep`) | xóa: ADR-003 và kế hoạch v2 đã bỏ Airflow, dbt | cả nhóm |
| `sandbox/compose-demo/` | giữ làm tài liệu học, hoặc xóa | Thịnh |

## 4. Ảnh hưởng tới CI và review

- **`ci.yml`**: thêm job `web` (`npm ci`, lint, `next build` trong `apps/web`) và job `rls` (Postgres 16 + `supabase_ci_bootstrap.sql` + migration + `rls_test.sql`). Job `test` đổi `testpaths` sang thư mục `tests/` của từng gói. Kế hoạch v2 yêu cầu CI "lint, test, test RLS, build".
- **Required checks**: tên job mới (`web`, `rls`) phải được Duy thêm vào ruleset `main` sau khi chạy lần đầu.
- **`CODEOWNERS`**: đổi đường dẫn theo bảng mục 3 (`/apps/web/` Thịnh; `/services/api/`, `/packages/skillkit/` Duy; `/pipelines/`, `/db/` Tùng; mỗi khu vực vẫn hai owner).

## 5. Thứ tự chuyển (không làm gãy việc đang dở)

1. **Tạo mới, không di chuyển** (S2, thứ 2–3): `apps/web/` (S2-H01) và `db/` từ file trên Drive (S2-T01). Hai thư mục mới nên không xung đột với code cũ.
2. **Chờ các nhánh đang dở merge xong**, rồi một PR duy nhất `chore: chuyển sang monorepo` dùng `git mv` (giữ lịch sử file), làm lúc ít PR đang mở. Sau khi merge, mỗi người `git pull` rồi rebase nhánh của mình.
3. Cùng PR đó: sửa `ci.yml`, `CODEOWNERS`, `pyproject.toml` (workspace) và README; chạy đủ test trước khi merge.
4. Duy cập nhật required checks trong ruleset.

## 6. Cần nhóm chốt ở planning 09/11

1. Có thêm `packages/skillkit` không, hay để skillkit trong `services/api` và pipeline gọi API?
2. Bỏ hẳn Docker Compose, hay giữ cho chạy cục bộ (Supabase có `supabase start` chạy Postgres + Auth cục bộ)?
3. Bỏ Alembic, dùng migration của Supabase CLI?
4. Ai làm PR di chuyển ở bước 2, và vào ngày nào?
