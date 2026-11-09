-- =====================================================================
--  S2-D02 — Lương VND lưu sẵn, tính lại khi tỷ giá đổi (phương án 5)
--  Cần gộp vào schema.sql v2.0 (Tùng). Chạy sau khi đã có schema ref, core.
--
--  Luồng mỗi ngày (Cloud Run Job 02:00):
--    ① job tỷ giá ghi ref.fx_rates → nếu có ngoại tệ đổi giá: select ref.refresh_job_salaries_vnd();
--    ② crawl: tin mới tính salary_*_vnd bằng ref.fx_latest (cùng tỷ giá vừa cập nhật).
--  Công thức phải khớp ingestion.salary.to_vnd().
-- =====================================================================

create table if not exists ref.fx_rates (
  currency    char(3)        not null,
  rate_date   date           not null,
  rate_vnd    numeric(16, 4) not null check (rate_vnd > 0),
  source      text           not null,           -- vietcombank | open_er_api
  fetched_at  timestamptz    not null default now(),
  primary key (currency, rate_date, source)
);

-- Tỷ giá mới nhất mỗi ngoại tệ. Cùng ngày có 2 nguồn thì lấy bản ghi sau cùng.
create or replace view ref.fx_latest as
select distinct on (currency) currency, rate_vnd, rate_date, source
from ref.fx_rates
order by currency, rate_date desc, fetched_at desc;

alter table core.jobs
  add column if not exists salary_raw         text,
  add column if not exists salary_amount_min  numeric(16, 2),   -- số gốc theo tháng
  add column if not exists salary_amount_max  numeric(16, 2),
  add column if not exists salary_currency    char(3),
  add column if not exists salary_pay_type    text not null default 'unknown'
    check (salary_pay_type in ('gross', 'net', 'unknown')),
  add column if not exists salary_status      text not null default 'missing'
    check (salary_status in ('parsed', 'negotiable', 'missing', 'unparsed')),
  add column if not exists salary_min_vnd     bigint,           -- VND/tháng, dùng để lọc/sắp xếp
  add column if not exists salary_max_vnd     bigint,
  add column if not exists salary_fx_date     date;             -- null với tin VND

create index if not exists jobs_salary_min_vnd_idx on core.jobs (salary_min_vnd)
  where salary_min_vnd is not null;
create index if not exists jobs_salary_max_vnd_idx on core.jobs (salary_max_vnd)
  where salary_max_vnd is not null;

-- Khoảng lương VND/tháng hợp lệ: mọi đầu có giá trị đều nằm trong 1–500 triệu.
-- Một đầu ra ngoài khoảng thì bỏ cả hai (giống to_vnd() → note "out_of_range").
create or replace function ref.salary_vnd_ok(min_vnd numeric, max_vnd numeric)
returns boolean language sql immutable as $$
  select coalesce(min_vnd, max_vnd) is not null
     and (min_vnd is null or round(min_vnd) between 1000000 and 500000000)
     and (max_vnd is null or round(max_vnd) between 1000000 and 500000000)
$$;

-- Tính lại lương VND cho mọi tin ngoại tệ có tỷ giá mới, trong một câu UPDATE.
-- Tin VND và tin đã dùng đúng ngày tỷ giá mới nhất không bị đụng tới. Trả số dòng đã sửa.
create or replace function ref.refresh_job_salaries_vnd()
returns integer language sql as $$
  with updated as (
    update core.jobs j
       set salary_min_vnd = case
             when ref.salary_vnd_ok(j.salary_amount_min * r.rate_vnd, j.salary_amount_max * r.rate_vnd)
             then round(j.salary_amount_min * r.rate_vnd)::bigint end,
           salary_max_vnd = case
             when ref.salary_vnd_ok(j.salary_amount_min * r.rate_vnd, j.salary_amount_max * r.rate_vnd)
             then round(j.salary_amount_max * r.rate_vnd)::bigint end,
           salary_fx_date = r.rate_date
      from ref.fx_latest r
     where j.salary_currency = r.currency
       and j.salary_currency <> 'VND'
       and j.salary_status = 'parsed'
       and j.salary_fx_date is distinct from r.rate_date
    returning 1
  )
  select count(*)::integer from updated
$$;
