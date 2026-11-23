-- =====================================================================================
--  Migration 0019 — Ghi độ trễ API vào ops.api_metrics, p95 theo ngày lấy từ đây (S4-T04, US-18)
--  Bảng ops.api_metrics đã có từ 0001 (chỉ admin đọc) nhưng chưa ai ghi. Migration này:
--    1. Role Postgres `api_metrics_writer`: middleware của API (FastAPI) ghi mỗi request một dòng
--       (endpoint, latency_ms, status, user_role). Chỉ được INSERT vào ops.api_metrics, không đọc
--       được gì khác.
--    2. mart.refresh_system_daily(): p95_ms tính từ ops.api_metrics (mọi request API trong ngày
--       giờ Việt Nam). Ngày chưa có dòng nào trong ops.api_metrics thì dùng cách cũ
--       (app.match_requests.latency_ms) để các ngày trước khi bật middleware vẫn có số.
--
--  KHÔNG có mật khẩu trong file này. Sau khi chạy migration, đặt mật khẩu một lần trong SQL Editor:
--      alter role api_metrics_writer with password '<mật khẩu mạnh>';
--  rồi đưa chuỗi kết nối (qua pooler Supavisor, user `api_metrics_writer.<project-ref>`) vào biến
--  môi trường METRICS_DATABASE_URL của API, không commit. Để trống thì API không ghi số đo.
--  Chạy lại nhiều lần được. Cần 0001, 0017.
-- =====================================================================================

-- 1. Role chỉ ghi số đo --------------------------------------------------------------------
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'api_metrics_writer') then
    create role api_metrics_writer with login noinherit nocreatedb nocreaterole connection limit 5;
  end if;
end $$;

-- Một lần ghi chỉ là insert vài dòng; quá 5 giây thì hủy để không giữ kết nối
alter role api_metrics_writer set statement_timeout = '5s';

comment on role api_metrics_writer is
  'API (S4-T04): chỉ insert vào ops.api_metrics. Mật khẩu đặt tay, không nằm trong git.';

grant usage on schema ops to api_metrics_writer;
grant insert on ops.api_metrics to api_metrics_writer;

drop policy if exists metrics_insert on ops.api_metrics;
create policy metrics_insert on ops.api_metrics for insert to api_metrics_writer
  with check (true);

comment on table ops.api_metrics is
  'Mỗi request API một dòng (middleware FastAPI, role api_metrics_writer). Admin đọc.';
comment on column ops.api_metrics.endpoint is
  'Phương thức + mẫu đường dẫn, ví dụ "POST /match" (không chứa id cụ thể).';

-- 2. p95 theo ngày từ ops.api_metrics ------------------------------------------------------
-- Giữ nguyên tên, tham số và giá trị mặc định của 0017 nên create or replace là đủ.
create or replace function mart.refresh_system_daily(
  p_day date default (now() at time zone 'Asia/Ho_Chi_Minh')::date
) returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_from     timestamptz := p_day::timestamp at time zone 'Asia/Ho_Chi_Minh';  -- 00:00 giờ VN
  v_to       timestamptz := (p_day + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh';
  v_end      timestamptz := least(now(), (p_day + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh');
  v_24h_from timestamptz := least(now(), (p_day + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh')
                            - interval '24 hours';
begin
  insert into mart.system_daily (
    day, jobs_open, jobs_new, jobs_new_24h, jobs_closed,
    users_seeker, users_hr, users_admin, logins_today,
    matches, p95_ms, crawl_success_pct, llm_cost_usd, refreshed_at
  )
  select
    p_day,
    (select count(*)::int from core.jobs
      where origin = 'crawled' and status = 'open'
        and (valid_through is null or valid_through >= p_day)),
    (select count(*)::int from core.jobs
      where origin = 'crawled' and first_seen_at >= v_from and first_seen_at < v_to),
    (select count(*)::int from core.jobs
      where origin = 'crawled' and first_seen_at > v_24h_from and first_seen_at <= v_end),
    (select count(*)::int from core.jobs
      where origin = 'crawled' and closed_at >= v_from and closed_at < v_to),
    (select count(*)::int from app.profiles where role = 'seeker' and status <> 'locked'),
    (select count(*)::int from app.profiles where role = 'hr' and status = 'active'),
    (select count(*)::int from app.profiles where role = 'admin' and status = 'active'),
    (select count(*)::int from app.audit_log
      where action = 'login' and at >= v_from and at < v_to),
    (select count(*)::int from app.match_requests
      where created_at >= v_from and created_at < v_to),
    coalesce(
      (select (percentile_cont(0.95) within group (order by latency_ms))::int
         from ops.api_metrics
        where at >= v_from and at < v_to),
      (select (percentile_cont(0.95) within group (order by latency_ms))::int
         from app.match_requests
        where created_at >= v_from and created_at < v_to and latency_ms is not null)
    ),
    (select case when count(*) > 0
                 then round(count(*) filter (where status = 'success')::numeric * 100.0 / count(*), 2)
            end
       from ops.crawl_runs where started_at >= v_from and started_at < v_to),
    (select coalesce(sum(cost_usd), 0)::numeric(10,4) from ops.llm_usage
      where at >= v_from and at < v_to),
    now()
  on conflict (day) do update set
    jobs_open         = excluded.jobs_open,
    jobs_new          = excluded.jobs_new,
    jobs_new_24h      = excluded.jobs_new_24h,
    jobs_closed       = excluded.jobs_closed,
    users_seeker      = excluded.users_seeker,
    users_hr          = excluded.users_hr,
    users_admin       = excluded.users_admin,
    logins_today      = excluded.logins_today,
    matches           = excluded.matches,
    p95_ms            = excluded.p95_ms,
    crawl_success_pct = excluded.crawl_success_pct,
    llm_cost_usd      = excluded.llm_cost_usd,
    refreshed_at      = excluded.refreshed_at;

  -- Mỗi nguồn trong ops.sources một dòng, kể cả nguồn chưa có tin (0)
  insert into mart.system_daily_source (day, source_id, jobs_open, jobs_new_24h, refreshed_at)
  select p_day, o.id,
         (select count(distinct j.id)::int
            from core.job_sources s
            join core.jobs j on j.id = s.job_id
           where s.source_id = o.id and s.is_active
             and j.origin = 'crawled' and j.status = 'open'
             and (j.valid_through is null or j.valid_through >= p_day)),
         (select count(*)::int
            from core.job_sources s
           where s.source_id = o.id
             and s.first_seen_at > v_24h_from and s.first_seen_at <= v_end),
         now()
    from ops.sources o
  on conflict (day, source_id) do update set
    jobs_open    = excluded.jobs_open,
    jobs_new_24h = excluded.jobs_new_24h,
    refreshed_at = excluded.refreshed_at;
end $$;

comment on function mart.refresh_system_daily(date) is
  'Làm mới mart.system_daily và mart.system_daily_source cho một ngày (mặc định: hôm nay giờ Việt Nam).';
revoke execute on function mart.refresh_system_daily(date) from public, anon, authenticated;

comment on column mart.system_daily.p95_ms is
  'p95 độ trễ (ms) mọi request API trong ngày (ops.api_metrics); ngày chưa có số đo API thì lấy '
  'p95 latency_ms của app.match_requests.';

notify pgrst, 'reload schema';

-- 3. Tính lại số của hôm nay ------------------------------------------------------------------
select mart.refresh_system_daily();
