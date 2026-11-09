-- =====================================================================
--  Intelligent Job Matching — Supabase / PostgreSQL 16 Schema (v2.0 Production)
--  Layers:  ref (từ điển) · ops (vận hành) · raw (Bronze) · core (Silver)
--           app (Auth/RBAC, người dùng, CV, matching, HR) · mart (Gold) · eval (đánh giá)
--  Web/App gọi qua schema `api` (view security_invoker + RPC) và RLS bảo vệ đa tầng.
--  Authentication & Authorization (Login / Logout / Register / 3-Role RBAC):
--    - Đồng bộ tự động từ `auth.users` sang `app.profiles` + `app.audit_log`
--      khi Đăng ký (INSERT) và Đăng nhập (UPDATE last_sign_in_at).
--    - Custom Access Token Hook nhúng `user_role`, `account_status`, `org_id` vào JWT.
--    - Mọi RLS policy ghi/đọc nhạy cảm đều kiểm tra `app.is_active_user()`
--      để chặn tức thì tài khoản bị khóa (`status = 'locked'`).
--    - Hỗ trợ Đăng xuất (`api.logout_user`) xóa phiên локально hoặc toàn thiết bị
--      (`auth.sessions`) và ghi nhận lịch sử đăng nhập/đăng xuất cho Admin.
--  Worker (crawler, JEV, embedding, matching) kết nối bằng service_role qua
--  Supavisor transaction mode (port 6543; asyncpg statement_cache_size=0).
-- =====================================================================

-- 0. Extensions (Supabase: bật vector, pg_trgm, unaccent, citext, pg_cron, pgmq)
create extension if not exists vector   with schema extensions;  -- @pgvector
create extension if not exists pg_trgm  with schema extensions;
create extension if not exists unaccent with schema extensions;
create extension if not exists citext   with schema extensions;

create schema if not exists ref;
create schema if not exists ops;
create schema if not exists raw;
create schema if not exists core;
create schema if not exists app;
create schema if not exists mart;
create schema if not exists eval;
create schema if not exists api;

-- Tìm kiếm tiếng Việt: cấu hình `simple` + unaccent (không stemming, bỏ dấu)
do $$ begin
  if not exists (select 1 from pg_ts_config where cfgname = 'vn_simple') then
    create text search configuration public.vn_simple (copy = pg_catalog.simple);
    alter text search configuration public.vn_simple
      alter mapping for hword, hword_part, word with extensions.unaccent, simple;
  end if;
end $$;

-- 1. Enum ---------------------------------------------------------------
create type app.app_role         as enum ('seeker','hr','admin');
create type app.account_status   as enum ('active','pending_hr','locked');
create type app.evidence_level   as enum ('strong','listed','user_added');
create type app.match_kind       as enum ('seeker_topn','seeker_single','hr_rank');
create type app.candidate_status as enum ('new','shortlist','rejected');
create type core.job_status      as enum ('open','closed','expired');
create type core.job_origin      as enum ('crawled','hr','user_paste');
create type core.work_mode       as enum ('onsite','hybrid','remote','unknown');
create type core.seniority       as enum ('intern','fresher','junior','middle','senior','lead','manager','unknown');
create type core.req_level       as enum ('required','preferred','mentioned');
create type core.extractor       as enum ('dict','jev','llm','human');
create type ops.run_status       as enum ('running','success','partial','failed');

-- 2. REF — từ điển dùng chung --------------------------------------------
create table ref.provinces (
  code          smallint primary key,                 -- 34 đơn vị hành chính từ 01/07/2025
  name          text not null unique,
  name_unaccent text not null,
  kind          text not null check (kind in ('tinh','thanh_pho')),
  region        text
);

create table ref.province_legacy (                     -- ánh xạ 63 → 34 + biến thể viết
  alias_norm    text primary key,                     -- "binh duong", "hcm", "sai gon"
  province_code smallint not null references ref.provinces
);

create table ref.job_families (
  id   smallint primary key,                          -- 0 = tất cả
  name text not null unique                           -- Backend, Frontend, Data/AI, DevOps, Mobile, QA...
);

create table ref.skill_categories (
  id   smallint primary key,
  name text not null unique
);

create table ref.skills (
  id          integer generated always as identity primary key,
  slug        text not null unique,                   -- "react", "postgresql"
  name        text not null,                          -- tên hiển thị chuẩn (canonical_name)
  category_id smallint not null references ref.skill_categories,
  kind        text not null default 'hard'
              check (kind in ('hard','tool','language','framework','cloud','soft','domain')),
  source      text,                                   -- onet / stackoverflow / kaggle_github / manual
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

create table ref.skill_aliases (
  alias_norm    text primary key,                     -- chữ thường, bỏ dấu: "reactjs", "react.js"
  skill_id      integer not null references ref.skills on delete cascade,
  needs_context boolean not null default false,       -- "go", "r", "c", "java": cần biên từ / ngữ cảnh
  context_rule  jsonb
);
create index skill_aliases_skill_idx on ref.skill_aliases (skill_id);

-- 3. APP (Auth, Organizations & Profiles — cần trước core) ---------------
create table app.organizations (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  website      text,
  email_domain extensions.citext,
  created_by   uuid references auth.users on delete set null,
  created_at   timestamptz not null default now()
);

create table app.profiles (
  user_id              uuid primary key references auth.users on delete cascade,
  email                extensions.citext,
  full_name            text,
  avatar_url           text,
  role                 app.app_role not null default 'seeker',
  status               app.account_status not null default 'active',
  org_id               uuid references app.organizations on delete set null,
  data_consent_version text,
  data_consent_at      timestamptz,
  llm_consent_at       timestamptz,                   -- đồng ý gửi CV (đã ẩn danh PII) tới LLM
  last_login_at        timestamptz,
  last_logout_at       timestamptz,
  login_count          integer not null default 0,
  locked_reason        text,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  constraint hr_has_org check (role <> 'hr' or org_id is not null)
);
create index profiles_org_idx   on app.profiles (org_id) where org_id is not null;
create index profiles_email_idx on app.profiles (email);
create index profiles_role_idx  on app.profiles (role, status);

-- 4. OPS — vận hành -------------------------------------------------------
create table ops.sources (
  id                smallint primary key,
  code              text not null unique,              -- vietnamworks, itviec, careerviet, topcv, jobsgo, joboko
  name              text not null,
  base_url          text not null,
  method            text not null check (method in ('jsonld','api','html','dataset')),
  robots_checked_at date,
  tos_note          text,
  rate_limit_ms     integer not null default 2000,     -- 1 request / 2 giây
  is_enabled        boolean not null default false,
  hourly_enabled    boolean not null default false
);

create table ops.crawl_runs (
  id            bigint generated always as identity primary key,
  source_id     smallint not null references ops.sources,
  run_type      text not null check (run_type in ('daily','hourly','manual','backfill')),
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  status        ops.run_status not null default 'running',
  pages_fetched integer not null default 0,
  items_seen    integer not null default 0,
  items_new     integer not null default 0,
  items_updated integer not null default 0,
  items_closed  integer not null default 0,
  http_errors   integer not null default 0,
  error_sample  text
);
create index crawl_runs_source_time_idx on ops.crawl_runs (source_id, started_at desc);

create table ops.quality_reports (
  run_id              bigint primary key references ops.crawl_runs on delete cascade,
  completeness        numeric(5,4),
  validity            numeric(5,4),
  uniqueness          numeric(5,4),
  salary_parsed_pct   numeric(5,4),
  province_parsed_pct numeric(5,4),
  schema_errors       integer,
  freshness_hours     numeric(8,2),
  details             jsonb
);

create table ops.api_metrics (
  id         bigint generated always as identity primary key,
  at         timestamptz not null default now(),
  endpoint   text not null,
  latency_ms integer not null,
  status     smallint not null,
  user_role  app.app_role
);
create index api_metrics_at_brin on ops.api_metrics using brin (at);

create table ops.llm_usage (
  id            bigint generated always as identity primary key,
  at            timestamptz not null default now(),
  purpose       text not null check (purpose in ('jev_classify','jd_extract','cv_extract','explain')),
  model         text not null,
  input_tokens  integer not null default 0,
  output_tokens integer not null default 0,
  cost_usd      numeric(10,6) not null default 0,
  cache_hit     boolean not null default false
);
create index llm_usage_at_brin on ops.llm_usage using brin (at);

create table ops.llm_cache (                          -- cache kết quả LLM theo SHA-256 content_hash (EN-05)
  content_hash  bytea not null,
  purpose       text not null check (purpose in ('jev_classify','jd_extract','cv_extract','explain')),
  model         text not null,
  response_json jsonb not null,
  created_at    timestamptz not null default now(),
  primary key (content_hash, purpose, model)
);
alter table ops.llm_cache enable row level security;  -- chỉ service_role đọc/ghi


-- 5. RAW (Bronze) — bản gốc, không ghi đè, partition theo tháng ------------
create table raw.job_snapshots (
  id              bigint generated always as identity,
  source_id       smallint not null,
  source_job_id   text not null,
  url             text not null,
  run_id          bigint,
  fetched_at      timestamptz not null default now(),
  http_status     smallint not null,
  content_hash    bytea not null,                      -- sha256 nội dung đã chuẩn hóa
  payload         jsonb,                               -- JSON-LD / JSON API (nhỏ)
  html_object_key text,                                -- HTML gốc nằm ở Cloudflare R2 / GCS
  primary key (id, fetched_at)
) partition by range (fetched_at);

create table raw.job_snapshots_2026_11 partition of raw.job_snapshots for values from ('2026-11-01') to ('2026-12-01');
create table raw.job_snapshots_2026_12 partition of raw.job_snapshots for values from ('2026-12-01') to ('2027-01-01');
create table raw.job_snapshots_2027_01 partition of raw.job_snapshots for values from ('2027-01-01') to ('2027-02-01');
create index job_snapshots_lookup_idx on raw.job_snapshots (source_id, source_job_id, fetched_at desc);

-- 6. CORE (Silver) — dữ liệu sạch, matching đọc trực tiếp ------------------
create table core.companies (
  id         bigint generated always as identity primary key,
  name       text not null,
  name_norm  text not null unique,                    -- chữ thường, bỏ dấu, bỏ "công ty TNHH"...
  website    text,
  logo_url   text,
  created_at timestamptz not null default now()
);
create index companies_name_trgm on core.companies using gin (name_norm extensions.gin_trgm_ops);

create table core.jobs (
  id                   bigint generated always as identity primary key,
  public_id            uuid not null default gen_random_uuid() unique,  -- id dùng trên URL
  origin               core.job_origin not null default 'crawled',
  org_id               uuid references app.organizations on delete cascade,  -- JD của HR
  owner_user_id        uuid references auth.users on delete cascade,         -- JD người dùng dán
  title                text not null,
  title_norm           text not null,
  company_id           bigint references core.companies,
  job_family_id        smallint references ref.job_families,
  seniority            core.seniority not null default 'unknown',
  work_mode            core.work_mode not null default 'unknown',
  employment_type      text,
  years_exp_min        numeric(3,1),
  salary_raw           text,
  salary_min_vnd       bigint,
  salary_max_vnd       bigint,
  salary_is_negotiable boolean not null default false,
  description          text,
  requirements         text,
  preferred            text,
  benefits             text,
  posted_at            date,
  valid_through        date,                          -- hạn nộp hồ sơ
  first_seen_at        timestamptz not null default now(),
  last_seen_at         timestamptz not null default now(),
  closed_at            timestamptz,
  missed_runs          smallint not null default 0,   -- vắng 3 lần liên tiếp → closed
  status               core.job_status not null default 'open',
  is_draft             boolean not null default false, -- cho phép HR lưu nháp JD (US-23)
  apply_url            text,                          -- link tin gốc chính
  content_hash         bytea,
  search_tsv           tsvector,                      -- điền bằng trigger
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  constraint origin_owner check (
       (origin = 'crawled'    and org_id is null and owner_user_id is null)
    or (origin = 'hr'         and org_id is not null)
    or (origin = 'user_paste' and owner_user_id is not null)),
  constraint crawled_has_link check (origin <> 'crawled' or apply_url is not null),
  constraint salary_range check (salary_min_vnd is null or salary_max_vnd is null or salary_min_vnd <= salary_max_vnd)
);

-- Kho tìm kiếm & matching: chỉ tin crawl đang mở → partial index nhỏ, nhanh
create index jobs_open_recent_idx on core.jobs (last_seen_at desc) where origin = 'crawled' and status = 'open';
create index jobs_open_valid_idx  on core.jobs (valid_through)    where origin = 'crawled' and status = 'open';
create index jobs_open_tsv_idx    on core.jobs using gin (search_tsv) where origin = 'crawled' and status = 'open';
create index jobs_open_family_idx on core.jobs (job_family_id, seniority, work_mode) where origin = 'crawled' and status = 'open';
create index jobs_open_salary_idx on core.jobs (salary_max_vnd) where origin = 'crawled' and status = 'open' and salary_max_vnd is not null;
create index jobs_title_trgm      on core.jobs using gin (title_norm extensions.gin_trgm_ops) where origin = 'crawled';
create index jobs_org_idx         on core.jobs (org_id, status) where origin = 'hr';
create index jobs_owner_idx       on core.jobs (owner_user_id) where origin = 'user_paste';
create index jobs_company_idx     on core.jobs (company_id);
create index jobs_seen_idx        on core.jobs (first_seen_at, closed_at) where origin = 'crawled';

create table core.job_sources (                        -- provenance: tin nguồn → tin chuẩn
  source_id         smallint not null references ops.sources,
  source_job_id     text not null,
  job_id            bigint not null references core.jobs on delete cascade,
  url               text not null,
  first_seen_at     timestamptz not null default now(),
  last_seen_at      timestamptz not null default now(),
  last_snapshot_id  bigint,
  last_content_hash bytea,
  is_active         boolean not null default true,
  primary key (source_id, source_job_id)
);
create index job_sources_job_idx on core.job_sources (job_id);

create table core.job_locations (
  job_id        bigint not null references core.jobs on delete cascade,
  province_code smallint not null references ref.provinces,
  address_raw   text,
  primary key (job_id, province_code)
);
create index job_locations_prov_idx on core.job_locations (province_code, job_id);

create table core.job_skills (
  job_id     bigint not null references core.jobs on delete cascade,
  skill_id   integer not null references ref.skills,
  level      core.req_level not null,
  evidence   text,                                    -- đoạn văn chứa kỹ năng
  extractor  core.extractor not null default 'dict',
  confidence real,
  primary key (job_id, skill_id)
);
create index job_skills_skill_idx on core.job_skills (skill_id, job_id);

create table core.job_chunks (                         -- đoạn ≤ 300 token để embedding
  id        bigint generated always as identity primary key,
  job_id    bigint not null references core.jobs on delete cascade,
  section   text not null check (section in ('summary','responsibilities','requirements','preferred')),
  chunk_no  smallint not null,
  content   text not null,
  embedding extensions.halfvec(1024) not null,        -- @pgvector (2 byte/chiều)
  model     text not null,
  unique (job_id, section, chunk_no)
);
create index job_chunks_hnsw on core.job_chunks
  using hnsw (embedding extensions.halfvec_cosine_ops) with (m = 16, ef_construction = 64);  -- @pgvector

create table core.dedup_candidates (
  job_a       bigint not null references core.jobs on delete cascade,
  job_b       bigint not null references core.jobs on delete cascade,
  similarity  real not null,
  status      text not null default 'pending' check (status in ('pending','merged','distinct')),
  reviewed_by uuid references auth.users on delete set null,
  reviewed_at timestamptz,
  primary key (job_a, job_b),
  check (job_a < job_b)
);
create index dedup_pending_idx on core.dedup_candidates (similarity desc) where status = 'pending';

-- 7. APP — HR Requests, CV, Matching, Audit Log ---------------------------
create table app.hr_requests (
  id           bigint generated always as identity primary key,
  user_id      uuid not null references auth.users on delete cascade,
  company_name text not null,
  website      text,
  work_email   extensions.citext not null,
  position     text,
  status       text not null default 'pending' check (status in ('pending','approved','rejected')),
  reviewed_by  uuid references auth.users on delete set null,
  reviewed_at  timestamptz,
  note         text,
  created_at   timestamptz not null default now()
);
create index hr_requests_pending_idx on app.hr_requests (created_at) where status = 'pending';
create index hr_requests_user_idx    on app.hr_requests (user_id, created_at desc);

create table app.cvs (
  id              uuid primary key default gen_random_uuid(),
  owner_user_id   uuid references auth.users on delete cascade,       -- CV của người tìm việc
  org_id          uuid references app.organizations on delete cascade, -- CV ứng viên HR tải
  job_id          bigint references core.jobs on delete cascade,       -- JD mà HR tải CV cho
  uploaded_by     uuid not null references auth.users on delete cascade,
  candidate_label text,                                -- HR đặt nhãn, không bắt buộc tên thật
  storage_path    text not null unique,                -- u/{uid}/{id}.pdf | o/{org}/{job}/{id}.pdf
  file_sha256     bytea not null,
  mime            text not null check (mime in ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
  size_bytes      integer not null check (size_bytes <= 5 * 1024 * 1024),
  parse_status    text not null default 'queued' check (parse_status in ('queued','parsing','parsed','failed')),
  parse_error     text,
  text_redacted   text,                                -- văn bản đã che PII (họ tên, email, SĐT, địa chỉ)
  parsed_sections jsonb,                               -- học vấn, kinh nghiệm, dự án, kỹ năng
  target_title    text,
  years_exp       numeric(4,1),
  is_primary      boolean not null default false,
  keep            boolean not null default false,      -- HR giữ lại quá hạn
  delete_after    date,                                -- mặc định +30 ngày cho CV
  created_at      timestamptz not null default now(),
  constraint one_owner check ((owner_user_id is not null) <> (org_id is not null)),
  constraint hr_cv_has_job check (org_id is null or job_id is not null)
);
create unique index cvs_one_primary_idx on app.cvs (owner_user_id) where is_primary;
create index cvs_owner_idx      on app.cvs (owner_user_id, created_at desc) where owner_user_id is not null;
create index cvs_org_job_idx    on app.cvs (org_id, job_id) where org_id is not null;
create index cvs_purge_idx      on app.cvs (delete_after) where keep = false and delete_after is not null;
create unique index cvs_dedup_file_idx on app.cvs (coalesce(owner_user_id::text, job_id::text), file_sha256);

create table app.cv_skills (
  cv_id          uuid not null references app.cvs on delete cascade,
  skill_id       integer not null references ref.skills,
  evidence_level app.evidence_level not null,
  evidence       text,
  years          numeric(4,1),
  confirmed      boolean not null default false,
  primary key (cv_id, skill_id)
);
create index cv_skills_skill_idx on app.cv_skills (skill_id);

create table app.cv_chunks (                           -- so khớp CV ↔ ≤ 50 JD: quét trực tiếp
  id        bigint generated always as identity primary key,
  cv_id     uuid not null references app.cvs on delete cascade,
  section   text not null,
  chunk_no  smallint not null,
  content   text,
  embedding extensions.halfvec(1024) not null,        -- @pgvector
  model     text not null,
  unique (cv_id, section, chunk_no)
);

create table app.match_requests (
  id             bigint generated always as identity primary key,
  kind           app.match_kind not null,
  requester_id   uuid references auth.users on delete cascade,
  cv_id          uuid references app.cvs on delete cascade,
  job_id         bigint references core.jobs on delete cascade,
  top_n          smallint check (top_n between 1 and 200),
  filters        jsonb not null default '{}',
  weights        jsonb not null,                       -- {"K":0.25,"M":0.35,"E":0.30,"X":0.10}
  engine_version text not null,
  corpus_size    integer,                              -- số tin mở dùng tính phân vị
  latency_ms     integer,
  created_at     timestamptz not null default now()
);
create index match_requests_user_idx on app.match_requests (requester_id, created_at desc);
create index match_requests_job_idx  on app.match_requests (job_id) where kind = 'hr_rank';

create table app.match_results (
  request_id  bigint not null references app.match_requests on delete cascade,
  rank        smallint not null,
  job_id      bigint references core.jobs on delete cascade,
  cv_id       uuid references app.cvs on delete cascade,
  score_h     numeric(5,2) not null check (score_h between 0 and 100),
  k real, m real, e real, x real,                      -- null = thành phần không xác định
  gap         jsonb,                                   -- 3 nhóm kỹ năng + đoạn trích song song
  explanation text,                                    -- giải thích AI có kiểm duyệt (nếu có)
  primary key (request_id, rank)
);
create index match_results_pair_idx on app.match_results (cv_id, job_id);

create table app.explanations (                        -- cache giải thích LLM theo (cv_hash, jd_hash, model)
  cv_hash    bytea not null,
  jd_hash    bytea not null,
  model      text not null,
  body       text not null,
  created_at timestamptz not null default now(),
  primary key (cv_hash, jd_hash, model)
);

create table app.saved_jobs (
  user_id  uuid not null references auth.users on delete cascade,
  job_id   bigint not null references core.jobs on delete cascade,
  saved_at timestamptz not null default now(),
  primary key (user_id, job_id)
);

create table app.candidate_reviews (
  job_id     bigint not null references core.jobs on delete cascade,
  cv_id      uuid not null references app.cvs on delete cascade,
  status     app.candidate_status not null default 'new',
  note       text,
  updated_by uuid references auth.users on delete set null,
  updated_at timestamptz not null default now(),
  primary key (job_id, cv_id)
);

create table app.feedback (
  id         bigint generated always as identity primary key,
  user_id    uuid references auth.users on delete cascade,
  request_id bigint references app.match_requests on delete cascade,
  rank       smallint,
  kind       text not null check (kind in ('explanation_wrong','not_relevant','helpful')),
  comment    text,
  created_at timestamptz not null default now()
);

create table app.audit_log (
  id         bigint generated always as identity primary key,
  at         timestamptz not null default now(),
  actor_id   uuid references auth.users on delete set null,
  actor_role app.app_role,
  action     text not null,                            -- register, login, logout, logout_all, role_changed, status_changed, role_guard_block, hr_requested, hr_reviewed, source_toggled, dedup_resolved, cv_purged
  entity     text not null,                            -- auth, profile, hr_request, source, dedup, storage
  entity_id  text,
  ip_address inet,
  user_agent text,
  detail     jsonb
);
create index audit_log_at_brin    on app.audit_log using brin (at);
create index audit_log_action_idx on app.audit_log (action, at desc);
create index audit_log_actor_idx  on app.audit_log (actor_id, at desc) where actor_id is not null;

-- 8. EVAL -----------------------------------------------------------------
create table eval.labels (
  cv_id      uuid not null references app.cvs on delete cascade,
  job_id     bigint not null references core.jobs on delete cascade,
  labeler    text not null,
  label      smallint not null check (label between 0 and 3),
  split      text not null check (split in ('dev','test')),
  created_at timestamptz not null default now(),
  primary key (cv_id, job_id, labeler)
);

create table eval.experiments (
  id          bigint generated always as identity primary key,
  run_at      timestamptz not null default now(),
  method      text not null check (method in ('bm25','vector','hybrid')),
  split       text not null check (split in ('dev','test')),
  job_family  smallint not null default 0,
  weights     jsonb,
  ndcg_at_10  numeric(5,4) not null,
  p_at_10     numeric(5,4) not null,
  note        text
);

-- 9. MART (Gold) — bảng tổng hợp, làm mới bằng pg_cron ---------------------
create table mart.skill_weekly (
  week_start    date not null,
  job_family_id smallint not null,                     -- 0 = mọi nhóm nghề
  skill_id      integer not null references ref.skills,
  n_open        integer not null,                      -- N: tin mở trong tuần
  volume        integer not null,                      -- V: số tin mở yêu cầu kỹ năng
  share         numeric(6,4) not null,                 -- V/N
  delta_share   numeric(6,4),                          -- chênh lệch so với tuần liền trước
  ci_low        numeric(6,4) not null,                 -- Wilson 95% cận dưới
  ci_high       numeric(6,4) not null,                 -- Wilson 95% cận trên
  trend_label   text not null default 'insufficient'
                check (trend_label in ('up','down','stable','insufficient')),
  primary key (week_start, job_family_id, skill_id)
);

create table mart.skill_cooccurrence (
  period_start date not null,
  skill_a      integer not null references ref.skills,
  skill_b      integer not null references ref.skills,
  n_ab         integer not null,
  n_a          integer not null,
  n_b          integer not null,
  n_total      integer not null,
  lift         numeric(8,3) not null,
  primary key (period_start, skill_a, skill_b),
  check (skill_a < skill_b)
);

create table mart.region_salary (
  snapshot_date       date not null,
  province_code       smallint not null references ref.provinces,
  job_family_id       smallint not null,               -- 0 = mọi nhóm nghề
  n_open              integer not null,
  n_with_salary       integer not null,
  disclosure_rate_pct numeric(5,2) not null default 0,
  p25_vnd             bigint,
  p50_vnd             bigint,
  p75_vnd             bigint,                          -- null khi n_with_salary < 20
  primary key (snapshot_date, province_code, job_family_id)
);

create table mart.system_daily (
  day               date primary key,
  jobs_open         integer,
  jobs_new          integer,
  jobs_closed       integer,
  users_seeker      integer,
  users_hr          integer,
  users_admin       integer,
  logins_today      integer,
  matches           integer,
  p95_ms            integer,
  crawl_success_pct numeric(5,2),
  llm_cost_usd      numeric(10,4)
);

-- 10. Hàm, Trigger & Hệ thống Auth/RBAC (Login / Logout / Phân quyền) ------
create or replace function core.jobs_before_write() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  new.search_tsv :=
       setweight(to_tsvector('public.vn_simple', coalesce(new.title, '')), 'A')
    || setweight(to_tsvector('public.vn_simple', coalesce(new.requirements, '') || ' ' || coalesce(new.preferred, '')), 'B')
    || setweight(to_tsvector('public.vn_simple', coalesce(new.description, '')), 'C');
  if new.status <> 'open' and new.closed_at is null then
    new.closed_at := now();
  end if;
  return new;
end $$;

create trigger jobs_before_write before insert or update of title, description, requirements, preferred, status
  on core.jobs for each row execute function core.jobs_before_write();

-- Đọc vai trò, trạng thái tài khoản & công ty từ JWT (không truy vấn bảng → policy cực nhanh)
create or replace function app.jwt_role() returns app.app_role
language sql stable as $$
  select coalesce(nullif(auth.jwt() ->> 'user_role', ''), 'seeker')::app.app_role
$$;

create or replace function app.jwt_status() returns app.account_status
language sql stable as $$
  select coalesce(nullif(auth.jwt() ->> 'account_status', ''), 'active')::app.account_status
$$;

create or replace function app.jwt_org() returns uuid
language sql stable as $$
  select nullif(auth.jwt() ->> 'org_id', '')::uuid
$$;

-- Kiểm tra tài khoản đã đăng nhập và KHÔNG bị khóa (status <> 'locked')
-- Kiểm tra kép: cả claim trong JWT lẫn trạng thái thực trong bảng app.profiles (để khóa tài khoản có hiệu lực tức thì dù JWT chưa hết hạn)
create or replace function app.is_active_user() returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null
     and coalesce(nullif(auth.jwt() ->> 'account_status', ''), 'active') <> 'locked'
     and exists (
       select 1 from app.profiles p
       where p.user_id = auth.uid() and p.status <> 'locked'
     )
$$;

-- Trigger 1: Tự động tạo profile + ghi audit log khi người dùng Đăng ký (INSERT vào auth.users)
-- Nếu đăng ký kèm metadata requested_role = 'hr' và company_name thì tự động tạo yêu cầu duyệt HR
create or replace function app.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_req_role text := coalesce(new.raw_user_meta_data ->> 'requested_role', 'seeker');
  v_company  text := nullif(trim(coalesce(new.raw_user_meta_data ->> 'company_name', '')), '');
  v_status   app.account_status := 'active';
begin
  if v_req_role = 'hr' and v_company is not null then
    v_status := 'pending_hr';
  end if;

  insert into app.profiles (user_id, email, full_name, avatar_url, role, status)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
    new.raw_user_meta_data ->> 'avatar_url',
    'seeker',
    v_status
  )
  on conflict (user_id) do update
    set email      = excluded.email,
        full_name  = coalesce(excluded.full_name, app.profiles.full_name),
        updated_at = now();

  if v_status = 'pending_hr' then
    insert into app.hr_requests (user_id, company_name, website, work_email, position)
    values (
      new.id,
      v_company,
      new.raw_user_meta_data ->> 'website',
      coalesce(new.raw_user_meta_data ->> 'work_email', new.email),
      new.raw_user_meta_data ->> 'position'
    );
  end if;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (
    new.id,
    'seeker',
    'register',
    'auth',
    new.id::text,
    jsonb_build_object('email', new.email, 'requested_role', v_req_role, 'status', v_status)
  );
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function app.handle_new_user();

-- Trigger 2: Tự động đồng bộ khi người dùng Đăng nhập (Supabase Auth cập nhật last_sign_in_at trên auth.users)
create or replace function app.handle_user_login() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_role app.app_role;
begin
  if new.last_sign_in_at is distinct from old.last_sign_in_at and new.last_sign_in_at is not null then
    update app.profiles
       set last_login_at = new.last_sign_in_at,
           login_count   = login_count + 1,
           email         = coalesce(new.email, email),
           updated_at    = now()
     where user_id = new.id
     returning role into v_role;

    insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
    values (
      new.id,
      coalesce(v_role, 'seeker'),
      'login',
      'auth',
      new.id::text,
      jsonb_build_object('last_sign_in_at', new.last_sign_in_at)
    );
  elsif new.email is distinct from old.email then
    update app.profiles set email = new.email, updated_at = now() where user_id = new.id;
  end if;
  return new;
end $$;

do $$ begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'auth' and table_name = 'users' and column_name = 'last_sign_in_at'
  ) then
    execute 'create trigger on_auth_user_login after update of last_sign_in_at, email on auth.users for each row execute function app.handle_user_login()';
  end if;
end $$;

-- Custom Access Token Hook: đưa user_role, account_status, org_id vào JWT của Supabase Auth
create or replace function public.custom_access_token_hook(event jsonb) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  claims jsonb := coalesce(event -> 'claims', '{}'::jsonb);
  p      record;
begin
  select role, status, org_id into p
    from app.profiles
   where user_id = (event ->> 'user_id')::uuid;

  claims := jsonb_set(claims, '{user_role}',      to_jsonb(coalesce(p.role::text, 'seeker')));
  claims := jsonb_set(claims, '{account_status}', to_jsonb(coalesce(p.status::text, 'active')));
  if p.org_id is not null then
    claims := jsonb_set(claims, '{org_id}', to_jsonb(p.org_id::text));
  else
    claims := claims - 'org_id';
  end if;
  return jsonb_set(event, '{claims}', claims);
end $$;

do $$ begin
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    execute 'grant usage on schema app to supabase_auth_admin';
    execute 'grant select on app.profiles to supabase_auth_admin';
    execute 'grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin';
  end if;
end $$;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

-- Kiểm tra quyền đọc một JD / CV (security definer: tránh RLS lồng nhau, có index)
create or replace function core.can_read_job(p_job_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from core.jobs j
    where j.id = p_job_id
      and (   j.origin = 'crawled'
           or (j.origin = 'hr' and j.org_id = app.jwt_org() and app.jwt_role() = 'hr' and app.is_active_user())
           or (j.origin = 'user_paste' and j.owner_user_id = auth.uid() and app.is_active_user())
           or (app.jwt_role() = 'admin' and app.is_active_user())))
$$;

create or replace function app.can_read_cv(p_cv_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select app.is_active_user() and exists (
    select 1 from app.cvs c
    where c.id = p_cv_id
      and (   c.owner_user_id = auth.uid()
           or (c.org_id = app.jwt_org() and app.jwt_role() = 'hr')))
$$;

-- =====================================================================
-- 10B. RPCs cho Login / Logout / Phân quyền / Quản trị trong schema `api`
-- =====================================================================

-- 1) Lấy thông tin hồ sơ & quyền của phiên đăng nhập hiện tại
create or replace function api.get_my_profile()
returns table (
  user_id              uuid,
  email                text,
  full_name            text,
  avatar_url           text,
  role                 app.app_role,
  status               app.account_status,
  org_id               uuid,
  org_name             text,
  data_consent_version text,
  data_consent_at      timestamptz,
  llm_consent_at       timestamptz,
  last_login_at        timestamptz,
  last_logout_at       timestamptz,
  login_count          integer
)
language sql stable security definer set search_path = '' as $$
  select p.user_id, p.email::text, p.full_name, p.avatar_url, p.role, p.status,
         p.org_id, o.name as org_name,
         p.data_consent_version, p.data_consent_at, p.llm_consent_at,
         p.last_login_at, p.last_logout_at, p.login_count
    from app.profiles p
    left join app.organizations o on o.id = p.org_id
   where p.user_id = auth.uid();
$$;

-- 2) Đăng xuất (Logout) an toàn: cập nhật last_logout_at, ghi audit_log,
--    và nếu p_all_devices = true thì thu hồi toàn bộ phiên trong auth.sessions
create or replace function api.logout_user(p_all_devices boolean default false)
returns void language plpgsql security definer set search_path = '' as $$
declare
  v_uid  uuid := auth.uid();
  v_role app.app_role := app.jwt_role();
begin
  if v_uid is null then
    return;
  end if;

  update app.profiles
     set last_logout_at = now(),
         updated_at     = now()
   where user_id = v_uid;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (
    v_uid,
    v_role,
    case when p_all_devices then 'logout_all' else 'logout' end,
    'auth',
    v_uid::text,
    jsonb_build_object('all_devices', p_all_devices, 'logged_out_at', now())
  );

  if p_all_devices and exists (
    select 1 from information_schema.tables
    where table_schema = 'auth' and table_name = 'sessions'
  ) then
    execute 'delete from auth.sessions where user_id = $1' using v_uid;
  end if;
end $$;

-- 3) Ghi nhận sự kiện bảo mật / chặn truy cập trái quyền từ Middleware (ví dụ: seeker vào /admin)
create or replace function api.log_security_event(
  p_action    text,
  p_entity    text,
  p_entity_id text default null,
  p_detail    jsonb default '{}'::jsonb
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_action not in ('login', 'logout', 'role_guard_block', 'password_reset') then
    raise exception 'invalid security event action' using errcode = '22023';
  end if;

  if p_action = 'login' and auth.uid() is not null then
    update app.profiles
       set last_login_at = now(),
           login_count   = login_count + 1,
           updated_at    = now()
     where user_id = auth.uid();
  end if;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (auth.uid(), app.jwt_role(), p_action, p_entity, p_entity_id, p_detail);
end $$;

-- 4) Người dùng gửi yêu cầu nâng cấp tài khoản HR (US-22)
create or replace function api.request_hr_account(
  p_company_name text,
  p_website      text,
  p_work_email   text,
  p_position     text default null
) returns bigint language plpgsql security definer set search_path = '' as $$
declare
  v_uid    uuid := auth.uid();
  v_req_id bigint;
begin
  if not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  if nullif(trim(coalesce(p_company_name, '')), '') is null or nullif(trim(coalesce(p_work_email, '')), '') is null then
    raise exception 'company_name and work_email are required' using errcode = '22023';
  end if;

  insert into app.hr_requests (user_id, company_name, website, work_email, position, status)
  values (v_uid, trim(p_company_name), trim(p_website), trim(p_work_email), trim(p_position), 'pending')
  returning id into v_req_id;

  update app.profiles
     set status     = case when role = 'seeker' then 'pending_hr'::app.account_status else status end,
         updated_at = now()
   where user_id = v_uid;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (v_uid, app.jwt_role(), 'hr_requested', 'hr_request', v_req_id::text,
          jsonb_build_object('company_name', p_company_name, 'work_email', p_work_email));
  return v_req_id;
end $$;

-- 5) Admin duyệt / từ chối yêu cầu HR (tự động tạo công ty + cấp role = 'hr')
create or replace function api.admin_review_hr_request(
  p_request_id bigint,
  p_approve    boolean,
  p_note       text default null
) returns uuid language plpgsql security definer set search_path = '' as $$
declare
  v_req    record;
  v_org_id uuid;
  v_domain text;
begin
  if app.jwt_role() <> 'admin' or not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  select * into v_req from app.hr_requests where id = p_request_id for update;
  if not found then
    raise exception 'hr_request not found' using errcode = 'P0002';
  end if;

  if p_approve then
    v_domain := nullif(split_part(v_req.work_email::text, '@', 2), '');
    select id into v_org_id from app.organizations where lower(name) = lower(v_req.company_name) limit 1;
    if v_org_id is null then
      insert into app.organizations (name, website, email_domain, created_by)
      values (v_req.company_name, v_req.website, v_domain, v_req.user_id)
      returning id into v_org_id;
    end if;

    update app.hr_requests
       set status = 'approved', reviewed_by = auth.uid(), reviewed_at = now(), note = p_note
     where id = p_request_id;

    update app.profiles
       set role = 'hr', status = 'active', org_id = v_org_id, updated_at = now()
     where user_id = v_req.user_id;
  else
    update app.hr_requests
       set status = 'rejected', reviewed_by = auth.uid(), reviewed_at = now(), note = p_note
     where id = p_request_id;

    update app.profiles
       set status = 'active', updated_at = now()
     where user_id = v_req.user_id and status = 'pending_hr';
  end if;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (
    auth.uid(), 'admin', 'hr_reviewed', 'hr_request', p_request_id::text,
    jsonb_build_object('user_id', v_req.user_id, 'approved', p_approve, 'org_id', v_org_id, 'note', p_note)
  );
  return v_org_id;
end $$;

-- 6) Admin đổi vai trò (ghi nhật ký)
create or replace function api.admin_set_role(p_user uuid, p_role app.app_role, p_org uuid default null)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if app.jwt_role() <> 'admin' or not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  update app.profiles
     set role       = p_role,
         org_id     = case when p_role = 'hr' then coalesce(p_org, org_id) else coalesce(p_org, org_id) end,
         status     = case when status = 'pending_hr' and p_role = 'hr' then 'active'::app.account_status else status end,
         updated_at = now()
   where user_id = p_user;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (auth.uid(), 'admin', 'role_changed', 'profile', p_user::text,
          jsonb_build_object('role', p_role, 'org', p_org));
end $$;

-- 7) Admin khóa / mở khóa tài khoản (US-31): chặn tức thì qua RLS + thu hồi phiên auth.sessions
create or replace function api.admin_set_account_status(
  p_user   uuid,
  p_status app.account_status,
  p_reason text default null
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if app.jwt_role() <> 'admin' or not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  if p_user = auth.uid() and p_status = 'locked' then
    raise exception 'admin cannot lock own account' using errcode = '22023';
  end if;

  update app.profiles
     set status        = p_status,
         locked_reason = case when p_status = 'locked' then p_reason else null end,
         updated_at    = now()
   where user_id = p_user;

  if p_status = 'locked' and exists (
    select 1 from information_schema.tables
    where table_schema = 'auth' and table_name = 'sessions'
  ) then
    execute 'delete from auth.sessions where user_id = $1' using p_user;
  end if;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (auth.uid(), 'admin', 'status_changed', 'profile', p_user::text,
          jsonb_build_object('status', p_status, 'reason', p_reason));
end $$;

-- 8) Admin duyệt cặp tin nghi trùng 0.70–0.85 (US-32)
create or replace function api.admin_resolve_dedup(
  p_job_a    bigint,
  p_job_b    bigint,
  p_decision text
) returns void language plpgsql security definer set search_path = '' as $$
declare
  v_a bigint := least(p_job_a, p_job_b);
  v_b bigint := greatest(p_job_a, p_job_b);
begin
  if app.jwt_role() <> 'admin' or not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  if p_decision not in ('merged', 'distinct') then
    raise exception 'decision must be merged or distinct' using errcode = '22023';
  end if;

  update core.dedup_candidates
     set status = p_decision, reviewed_by = auth.uid(), reviewed_at = now()
   where job_a = v_a and job_b = v_b;

  if p_decision = 'merged' then
    update core.job_sources set job_id = v_a where job_id = v_b;
    update core.jobs set status = 'closed', closed_at = now(), updated_at = now() where id = v_b;
  end if;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (auth.uid(), 'admin', 'dedup_resolved', 'dedup', v_a || ':' || v_b,
          jsonb_build_object('job_a', v_a, 'job_b', v_b, 'decision', p_decision));
end $$;

-- 9) Admin bật/tắt nguồn thu thập (US-31)
create or replace function api.admin_toggle_source(
  p_source_id      smallint,
  p_is_enabled     boolean,
  p_hourly_enabled boolean default null
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if app.jwt_role() <> 'admin' or not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  update ops.sources
     set is_enabled     = p_is_enabled,
         hourly_enabled = coalesce(p_hourly_enabled, hourly_enabled)
   where id = p_source_id;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (auth.uid(), 'admin', 'source_toggled', 'source', p_source_id::text,
          jsonb_build_object('is_enabled', p_is_enabled, 'hourly_enabled', p_hourly_enabled));
end $$;

-- 10) View danh sách việc đang mở còn hạn (`api.v_open_jobs` — phục vụ S1-H04, S1-H05, US-03, US-14)
create or replace view api.v_open_jobs
with (security_invoker = true) as
select
  j.id,
  j.public_id,
  j.title,
  c.name as company_name,
  c.logo_url as company_logo_url,
  j.job_family_id,
  jf.name as job_family_name,
  j.seniority,
  j.work_mode,
  j.years_exp_min,
  j.salary_raw,
  j.salary_min_vnd,
  j.salary_max_vnd,
  j.salary_is_negotiable,
  j.posted_at,
  j.valid_through,
  (j.valid_through is not null and j.valid_through <= current_date + 3) as is_expiring_soon,
  j.first_seen_at,
  j.last_seen_at,
  j.apply_url,
  coalesce((
    select count(*)::int from core.job_sources js where js.job_id = j.id and js.is_active
  ), 1) as source_count
from core.jobs j
left join core.companies c on c.id = j.company_id
left join ref.job_families jf on jf.id = j.job_family_id
where j.origin = 'crawled'
  and j.status = 'open'
  and (j.valid_through is null or j.valid_through >= current_date);

-- 11) Tìm việc (web gọi qua PostgREST: /rpc/search_jobs)
create or replace function api.search_jobs(
  q text default null, provinces smallint[] default null, skills integer[] default null,
  salary_min bigint default null, modes core.work_mode[] default null,
  levels core.seniority[] default null, page integer default 1, page_size integer default 20)
returns table (public_id uuid, title text, company text, salary_min_vnd bigint, salary_max_vnd bigint,
               salary_raw text, work_mode core.work_mode, valid_through date, apply_url text,
               last_seen_at timestamptz, rank real)
language sql stable security invoker set search_path = '' as $$
  select j.public_id, j.title, c.name, j.salary_min_vnd, j.salary_max_vnd, j.salary_raw,
         j.work_mode, j.valid_through, j.apply_url, j.last_seen_at,
         case when q is null then 0
              else ts_rank_cd(j.search_tsv, websearch_to_tsquery('public.vn_simple', q)) end as rank
  from core.jobs j
  left join core.companies c on c.id = j.company_id
  where j.origin = 'crawled' and j.status = 'open'
    and (j.valid_through is null or j.valid_through >= current_date)
    and (q is null or j.search_tsv @@ websearch_to_tsquery('public.vn_simple', q))
    and (salary_min is null or j.salary_max_vnd >= salary_min)
    and (modes  is null or j.work_mode = any (modes))
    and (levels is null or j.seniority = any (levels))
    and (provinces is null or exists (select 1 from core.job_locations l
                                      where l.job_id = j.id and l.province_code = any (provinces)))
    and (skills is null or exists (select 1 from core.job_skills s
                                   where s.job_id = j.id and s.skill_id = any (skills)))
  order by rank desc, j.last_seen_at desc
  limit least(page_size, 50) offset (greatest(page, 1) - 1) * least(page_size, 50)
$$;

-- =====================================================================
-- 10C. Các hàm làm mới tầng MART (Gold) & Dọn dẹp định kỳ
-- =====================================================================

-- 1) Làm mới chỉ số kỹ năng theo tuần (tin MỞ trong tuần, kèm Wilson 95% CI, delta_share và trend_label)
create or replace function mart.refresh_skill_weekly(p_week date) returns void
language plpgsql security definer set search_path = '' as $$
declare
  w_end     date := p_week + 6;
  prev_week date := p_week - 7;
begin
  delete from mart.skill_weekly where week_start = p_week;

  with open_jobs as (
    select j.id, coalesce(j.job_family_id, 0) as fam
    from core.jobs j
    where j.origin = 'crawled'
      and j.first_seen_at::date <= w_end
      and (j.closed_at is null or j.closed_at::date >= p_week)
  ), fams as (
    select id, fam from open_jobs
    union all select id, 0 from open_jobs where fam <> 0
  ), n as (
    select fam, count(*)::int as n_open from fams group by fam
  ), v as (
    select f.fam, s.skill_id, count(distinct f.id)::int as volume
    from fams f join core.job_skills s on s.job_id = f.id
    group by f.fam, s.skill_id
  ), cur as (
    select
      p_week as week_start,
      v.fam as job_family_id,
      v.skill_id,
      n.n_open,
      v.volume,
      round(v.volume::numeric / n.n_open, 4) as share,
      round(greatest(0, (v.volume::numeric/n.n_open + 1.92/n.n_open
            - 1.96*sqrt((v.volume::numeric/n.n_open)*(1 - v.volume::numeric/n.n_open)/n.n_open + 0.9604/(n.n_open::numeric^2)))
            / (1 + 3.8416/n.n_open)), 4) as ci_low,
      round(least(1, (v.volume::numeric/n.n_open + 1.92/n.n_open
            + 1.96*sqrt((v.volume::numeric/n.n_open)*(1 - v.volume::numeric/n.n_open)/n.n_open + 0.9604/(n.n_open::numeric^2)))
            / (1 + 3.8416/n.n_open)), 4) as ci_high
    from v join n using (fam)
  )
  insert into mart.skill_weekly (
    week_start, job_family_id, skill_id, n_open, volume, share, delta_share, ci_low, ci_high, trend_label
  )
  select
    c.week_start,
    c.job_family_id,
    c.skill_id,
    c.n_open,
    c.volume,
    c.share,
    case when p.share is not null then c.share - p.share else null end as delta_share,
    c.ci_low,
    c.ci_high,
    case
      when c.volume < 10 or p.volume is null or p.volume < 10 then 'insufficient'
      when c.ci_low > p.ci_high then 'up'
      when c.ci_high < p.ci_low then 'down'
      else 'stable'
    end as trend_label
  from cur c
  left join mart.skill_weekly p
    on p.week_start = prev_week
   and p.job_family_id = c.job_family_id
   and p.skill_id = c.skill_id;
end $$;

-- 2) Làm mới bảng đồng xuất hiện kỹ năng (Lift cho cặp có ≥ 10 JD chung)
create or replace function mart.refresh_skill_cooccurrence(p_period_start date default current_date) returns void
language plpgsql security definer set search_path = '' as $$
begin
  delete from mart.skill_cooccurrence where period_start = p_period_start;

  with open_jobs as (
    select j.id
    from core.jobs j
    where j.origin = 'crawled' and j.status = 'open'
      and (j.valid_through is null or j.valid_through >= current_date)
  ), tot as (
    select count(*)::int as n_total from open_jobs
  ), js as (
    select distinct s.job_id, s.skill_id
    from core.job_skills s
    join open_jobs o on o.id = s.job_id
  ), counts as (
    select skill_id, count(*)::int as n_k from js group by skill_id
  ), pairs as (
    select a.skill_id as skill_a, b.skill_id as skill_b, count(*)::int as n_ab
    from js a
    join js b on a.job_id = b.job_id and a.skill_id < b.skill_id
    group by a.skill_id, b.skill_id
    having count(*) >= 10
  )
  insert into mart.skill_cooccurrence (period_start, skill_a, skill_b, n_ab, n_a, n_b, n_total, lift)
  select
    p_period_start,
    p.skill_a,
    p.skill_b,
    p.n_ab,
    ca.n_k,
    cb.n_k,
    t.n_total,
    round((p.n_ab::numeric * t.n_total) / nullif(ca.n_k::numeric * cb.n_k, 0), 3)
  from pairs p
  join counts ca on ca.skill_id = p.skill_a
  join counts cb on cb.skill_id = p.skill_b
  cross join tot t
  where t.n_total > 0;
end $$;

-- 3) Làm mới thống kê địa phương & lương (34 tỉnh/thành, ẩn số lương khi n_with_salary < 20)
create or replace function mart.refresh_region_salary(p_date date default current_date) returns void
language plpgsql security definer set search_path = '' as $$
begin
  delete from mart.region_salary where snapshot_date = p_date;

  with open_loc as (
    select l.province_code, coalesce(j.job_family_id, 0) as fam,
           j.id as job_id,
           case
             when j.salary_min_vnd is not null and j.salary_max_vnd is not null then (j.salary_min_vnd + j.salary_max_vnd) / 2
             else coalesce(j.salary_max_vnd, j.salary_min_vnd)
           end as sal_mid
    from core.jobs j
    join core.job_locations l on l.job_id = j.id
    where j.origin = 'crawled' and j.status = 'open'
      and (j.valid_through is null or j.valid_through >= current_date)
  ), expanded as (
    select province_code, fam, job_id, sal_mid from open_loc
    union all
    select province_code, 0 as fam, job_id, sal_mid from open_loc where fam <> 0
  ), agg as (
    select
      province_code,
      fam as job_family_id,
      count(distinct job_id)::int as n_open,
      count(distinct job_id) filter (where sal_mid is not null)::int as n_with_salary,
      percentile_cont(0.25) within group (order by sal_mid)::bigint as p25,
      percentile_cont(0.50) within group (order by sal_mid)::bigint as p50,
      percentile_cont(0.75) within group (order by sal_mid)::bigint as p75
    from expanded
    group by province_code, fam
  )
  insert into mart.region_salary (
    snapshot_date, province_code, job_family_id, n_open, n_with_salary, disclosure_rate_pct, p25_vnd, p50_vnd, p75_vnd
  )
  select
    p_date,
    province_code,
    job_family_id,
    n_open,
    n_with_salary,
    case when n_open > 0 then round(n_with_salary::numeric * 100.0 / n_open, 2) else 0 end,
    case when n_with_salary >= 20 then p25 else null end,
    case when n_with_salary >= 20 then p50 else null end,
    case when n_with_salary >= 20 then p75 else null end
  from agg;
end $$;

-- 4) Làm mới bảng chỉ số vận hành toàn hệ thống (`mart.refresh_system_daily`)
create or replace function mart.refresh_system_daily(p_day date default current_date) returns void
language plpgsql security definer set search_path = '' as $$
begin
  insert into mart.system_daily (
    day, jobs_open, jobs_new, jobs_closed,
    users_seeker, users_hr, users_admin, logins_today,
    matches, p95_ms, crawl_success_pct, llm_cost_usd
  )
  select
    p_day,
    (select count(*)::int from core.jobs where origin = 'crawled' and status = 'open' and (valid_through is null or valid_through >= p_day)),
    (select count(*)::int from core.jobs where origin = 'crawled' and first_seen_at::date = p_day),
    (select count(*)::int from core.jobs where origin = 'crawled' and closed_at::date = p_day),
    (select count(*)::int from app.profiles where role = 'seeker' and status <> 'locked'),
    (select count(*)::int from app.profiles where role = 'hr' and status = 'active'),
    (select count(*)::int from app.profiles where role = 'admin' and status = 'active'),
    (select count(*)::int from app.audit_log where action = 'login' and at::date = p_day),
    (select count(*)::int from app.match_requests where created_at::date = p_day),
    (select percentile_cont(0.95) within group (order by latency_ms)::int from app.match_requests where created_at::date = p_day and latency_ms is not null),
    (select case when count(*) > 0 then round(count(*) filter (where status = 'success')::numeric * 100.0 / count(*), 2) else 100.0 end
       from ops.crawl_runs where started_at::date = p_day),
    (select coalesce(sum(cost_usd), 0)::numeric(10,4) from ops.llm_usage where at::date = p_day)
  on conflict (day) do update set
    jobs_open         = excluded.jobs_open,
    jobs_new          = excluded.jobs_new,
    jobs_closed       = excluded.jobs_closed,
    users_seeker      = excluded.users_seeker,
    users_hr          = excluded.users_hr,
    users_admin       = excluded.users_admin,
    logins_today      = excluded.logins_today,
    matches           = excluded.matches,
    p95_ms            = excluded.p95_ms,
    crawl_success_pct = excluded.crawl_success_pct,
    llm_cost_usd      = excluded.llm_cost_usd;
end $$;

-- 5) Xóa CV quá hạn (TTL 30 ngày): xóa dòng DB, đẩy đường dẫn file vào audit_log để worker xóa qua Storage API
create or replace function app.purge_expired_cvs() returns integer
language plpgsql security definer set search_path = '' as $$
declare n integer;
begin
  with gone as (
    delete from app.cvs where keep = false and delete_after < current_date returning storage_path
  )
  insert into app.audit_log (action, entity, entity_id)
  select 'cv_purged', 'storage', storage_path from gone;
  get diagnostics n = row_count;
  return n;
end $$;

-- =====================================================================
-- 11. Row-Level Security (RLS) ----------------------------------------
-- =====================================================================
alter table app.profiles            enable row level security;
alter table app.organizations       enable row level security;
alter table app.hr_requests         enable row level security;
alter table app.cvs                 enable row level security;
alter table app.cv_skills           enable row level security;
alter table app.cv_chunks           enable row level security;
alter table app.match_requests      enable row level security;
alter table app.match_results       enable row level security;
alter table app.saved_jobs          enable row level security;
alter table app.candidate_reviews   enable row level security;
alter table app.feedback            enable row level security;
alter table app.audit_log           enable row level security;
alter table app.explanations        enable row level security;   -- chỉ service_role
alter table core.jobs               enable row level security;
alter table core.job_sources        enable row level security;
alter table core.job_locations      enable row level security;
alter table core.job_skills         enable row level security;
alter table core.job_chunks         enable row level security;   -- chỉ service_role
alter table core.companies          enable row level security;
alter table core.dedup_candidates   enable row level security;
alter table ops.sources             enable row level security;
alter table ops.crawl_runs          enable row level security;
alter table ops.quality_reports     enable row level security;
alter table ops.api_metrics         enable row level security;
alter table ops.llm_usage           enable row level security;
alter table mart.system_daily       enable row level security;
alter table mart.skill_weekly       enable row level security;
alter table mart.skill_cooccurrence enable row level security;
alter table mart.region_salary      enable row level security;
alter table eval.labels             enable row level security;
alter table eval.experiments        enable row level security;
alter table ref.skills              enable row level security;
alter table ref.skill_aliases       enable row level security;
alter table ref.skill_categories    enable row level security;
alter table ref.provinces           enable row level security;
alter table ref.province_legacy     enable row level security;
alter table ref.job_families        enable row level security;
-- raw.* không bật policy nào: chỉ service_role (worker) truy cập.

-- Từ điển & số liệu thị trường: công khai cho cả anon và authenticated
create policy ref_read  on ref.skills              for select to anon, authenticated using (true);
create policy ref_read  on ref.skill_aliases       for select to anon, authenticated using (true);
create policy ref_read  on ref.skill_categories    for select to anon, authenticated using (true);
create policy ref_read  on ref.provinces           for select to anon, authenticated using (true);
create policy ref_read  on ref.province_legacy     for select to anon, authenticated using (true);
create policy ref_read  on ref.job_families        for select to anon, authenticated using (true);
create policy mart_read on mart.skill_weekly       for select to anon, authenticated using (true);
create policy mart_read on mart.skill_cooccurrence for select to anon, authenticated using (true);
create policy mart_read on mart.region_salary      for select to anon, authenticated using (true);
create policy companies_read on core.companies     for select to anon, authenticated using (true);

-- Profile: tự xem mình; admin xem tất cả; sửa vai trò/trạng thái chỉ qua RPC của admin
create policy profiles_self on app.profiles for select to authenticated
  using (user_id = (select auth.uid()) or ((select app.jwt_role()) = 'admin' and (select app.is_active_user())));

create policy profiles_update_self on app.profiles for update to authenticated
  using (user_id = (select auth.uid()) and (select app.is_active_user()))
  with check (user_id = (select auth.uid()) and (select app.is_active_user()));

revoke update on app.profiles from authenticated;
grant update (full_name, avatar_url, data_consent_version, data_consent_at, llm_consent_at) on app.profiles to authenticated;

do $$ begin
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    execute 'create policy auth_admin_reads_profiles on app.profiles for select to supabase_auth_admin using (true)';
  end if;
end $$;

create policy org_member_read on app.organizations for select to authenticated
  using ((select app.is_active_user()) and (id = (select app.jwt_org()) or (select app.jwt_role()) = 'admin'));

-- HR Requests: người dùng chỉ xem và tạo yêu cầu pending của mình; chỉ admin mới được duyệt (update)
create policy hr_request_select on app.hr_requests for select to authenticated
  using ((select app.is_active_user()) and (user_id = (select auth.uid()) or (select app.jwt_role()) = 'admin'));

create policy hr_request_insert on app.hr_requests for insert to authenticated
  with check ((select app.is_active_user()) and user_id = (select auth.uid()) and status = 'pending' and reviewed_by is null);

create policy hr_request_admin_write on app.hr_requests for update to authenticated
  using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin')
  with check ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');

-- JD (core.jobs)
create policy jobs_read on core.jobs for select to anon, authenticated
  using (   origin = 'crawled'
         or ((select app.is_active_user()) and (
               (origin = 'hr' and org_id = (select app.jwt_org()) and (select app.jwt_role()) = 'hr')
            or (origin = 'user_paste' and owner_user_id = (select auth.uid()))
            or (select app.jwt_role()) = 'admin')));

create policy jobs_hr_write on core.jobs for all to authenticated
  using ((select app.is_active_user()) and origin = 'hr' and org_id = (select app.jwt_org()) and (select app.jwt_role()) = 'hr')
  with check ((select app.is_active_user()) and origin = 'hr' and org_id = (select app.jwt_org()) and (select app.jwt_role()) = 'hr');

create policy jobs_paste_write on core.jobs for all to authenticated
  using ((select app.is_active_user()) and origin = 'user_paste' and owner_user_id = (select auth.uid()))
  with check ((select app.is_active_user()) and origin = 'user_paste' and owner_user_id = (select auth.uid()));

create policy job_child_read on core.job_skills    for select to anon, authenticated using ((select core.can_read_job(job_id)));
create policy job_child_read on core.job_locations for select to anon, authenticated using ((select core.can_read_job(job_id)));
create policy job_child_read on core.job_sources   for select to anon, authenticated using ((select core.can_read_job(job_id)));

create policy hr_job_skills_write on core.job_skills for all to authenticated
  using ((select app.is_active_user()) and (select core.can_read_job(job_id)) and (select app.jwt_role()) = 'hr')
  with check ((select app.is_active_user()) and (select core.can_read_job(job_id)) and (select app.jwt_role()) = 'hr');

-- CV: người tìm việc thấy CV của mình; HR thấy CV ứng viên công ty mình; Admin KHÔNG đọc CV; tài khoản bị khóa bị chặn hoàn toàn
create policy cvs_owner on app.cvs for all to authenticated
  using ((select app.is_active_user()) and owner_user_id = (select auth.uid()))
  with check ((select app.is_active_user()) and owner_user_id = (select auth.uid()) and uploaded_by = (select auth.uid()));

create policy cvs_hr on app.cvs for all to authenticated
  using ((select app.is_active_user()) and org_id = (select app.jwt_org()) and (select app.jwt_role()) = 'hr')
  with check ((select app.is_active_user()) and org_id = (select app.jwt_org()) and (select app.jwt_role()) = 'hr');

create policy cv_child on app.cv_skills for all to authenticated
  using ((select app.can_read_cv(cv_id)))
  with check ((select app.can_read_cv(cv_id)));

-- Kết quả matching, lưu việc, shortlist ứng viên, phản hồi
create policy match_req_read on app.match_requests for select to authenticated
  using ((select app.is_active_user()) and (
         requester_id = (select auth.uid())
         or (kind = 'hr_rank' and (select core.can_read_job(job_id)) and (select app.jwt_role()) = 'hr')));

create policy match_res_read on app.match_results for select to authenticated
  using ((select app.is_active_user()) and exists (select 1 from app.match_requests r where r.id = request_id));

create policy saved_own on app.saved_jobs for all to authenticated
  using ((select app.is_active_user()) and user_id = (select auth.uid()))
  with check ((select app.is_active_user()) and user_id = (select auth.uid()));

create policy review_hr on app.candidate_reviews for all to authenticated
  using ((select app.is_active_user()) and (select core.can_read_job(job_id)) and (select app.jwt_role()) = 'hr')
  with check ((select app.is_active_user()) and (select core.can_read_job(job_id)) and (select app.jwt_role()) = 'hr');

create policy feedback_own on app.feedback for insert to authenticated
  with check ((select app.is_active_user()) and user_id = (select auth.uid()));

-- Admin: số liệu vận hành, nhật ký bảo mật, khử trùng, đánh giá
create policy admin_read on ops.sources         for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
create policy admin_read on ops.crawl_runs      for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
create policy admin_read on ops.quality_reports for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
create policy admin_read on ops.api_metrics     for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
create policy admin_read on ops.llm_usage       for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
create policy admin_read on mart.system_daily   for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
create policy admin_read on app.audit_log       for select to authenticated using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');

create policy admin_all on core.dedup_candidates for all to authenticated
  using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin')
  with check ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');

create policy admin_upd on ops.sources for update to authenticated
  using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin')
  with check ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');

create policy admin_read on eval.labels for all to authenticated
  using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin')
  with check ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');

create policy admin_read on eval.experiments for all to authenticated
  using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin')
  with check ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');

-- 12. Storage: bucket private 'cvs' (tự động khởi tạo nếu có bảng storage.buckets) --
do $$ begin
  if exists (
    select 1 from information_schema.tables
    where table_schema = 'storage' and table_name = 'buckets'
  ) then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values (
      'cvs',
      'cvs',
      false,
      5242880,
      array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    )
    on conflict (id) do update set
      public             = excluded.public,
      file_size_limit    = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;
  end if;
end $$;
create policy cv_files_seeker on storage.objects for all to authenticated
  using ((select app.is_active_user())
         and bucket_id = 'cvs'
         and (storage.foldername(name))[1] = 'u'
         and (storage.foldername(name))[2] = (select auth.uid())::text)
  with check ((select app.is_active_user())
         and bucket_id = 'cvs'
         and (storage.foldername(name))[1] = 'u'
         and (storage.foldername(name))[2] = (select auth.uid())::text);

create policy cv_files_hr on storage.objects for all to authenticated
  using ((select app.is_active_user())
         and bucket_id = 'cvs'
         and (storage.foldername(name))[1] = 'o'
         and (storage.foldername(name))[2] = (select app.jwt_org())::text
         and (select app.jwt_role()) = 'hr')
  with check ((select app.is_active_user())
         and bucket_id = 'cvs'
         and (storage.foldername(name))[1] = 'o'
         and (storage.foldername(name))[2] = (select app.jwt_org())::text
         and (select app.jwt_role()) = 'hr');

-- 13. Quyền schema cho PostgREST (thêm `api` vào Exposed schemas) ------------
grant usage on schema api, ref, core, app, mart, ops, eval to anon, authenticated;

grant select on all tables in schema ref, mart to anon, authenticated;
grant select on api.v_open_jobs to anon, authenticated;
grant select on core.jobs, core.companies, core.job_skills, core.job_locations, core.job_sources to anon, authenticated;

grant insert, update, delete on core.jobs, core.job_skills to authenticated;
grant select, insert, update, delete on app.cvs, app.cv_skills, app.saved_jobs, app.candidate_reviews to authenticated;
grant select, insert, update on app.hr_requests to authenticated;
grant select on app.profiles, app.organizations, app.match_requests, app.match_results, app.audit_log to authenticated;
grant insert on app.feedback to authenticated;
grant select on ops.sources, ops.crawl_runs, ops.quality_reports, ops.api_metrics, ops.llm_usage to authenticated;
grant update (is_enabled, hourly_enabled) on ops.sources to authenticated;
grant select, update on core.dedup_candidates to authenticated;
grant select, insert, update on eval.labels, eval.experiments to authenticated;

grant execute on all functions in schema api to anon, authenticated;
revoke execute on function
  api.get_my_profile(),
  api.logout_user(boolean),
  api.log_security_event(text, text, text, jsonb),
  api.request_hr_account(text, text, text, text),
  api.admin_review_hr_request(bigint, boolean, text),
  api.admin_set_role(uuid, app.app_role, uuid),
  api.admin_set_account_status(uuid, app.account_status, text),
  api.admin_resolve_dedup(bigint, bigint, text),
  api.admin_toggle_source(smallint, boolean, boolean)
from anon;

-- 14. Lịch pg_cron (chỉ đăng ký khi extension pg_cron đã bật trên Supabase) --
do $$ begin
  if exists (select 1 from pg_namespace where nspname = 'cron') then
    perform cron.schedule('refresh-system-daily', '*/15 * * * *', $cron$ select mart.refresh_system_daily(current_date) $cron$);
    perform cron.schedule('refresh-skill-weekly', '0 3 * * *', $cron$ select mart.refresh_skill_weekly(date_trunc('week', now())::date) $cron$);
    perform cron.schedule('refresh-skill-cooccurrence', '10 3 * * *', $cron$ select mart.refresh_skill_cooccurrence(current_date) $cron$);
    perform cron.schedule('refresh-region-salary', '20 3 * * *', $cron$ select mart.refresh_region_salary(current_date) $cron$);
    perform cron.schedule('purge-expired-cvs', '30 3 * * *', $cron$ select app.purge_expired_cvs() $cron$);
  end if;
end $$;
