-- =====================================================================================
--  Migration 0017 — Chỉ số vận hành hằng ngày cho admin (S4-T01, US-18)
--  Bảng mart.system_daily và hàm mart.refresh_system_daily() đã có từ 0001, pg_cron làm mới
--  mỗi 15 phút. Migration này bổ sung phần S4-T01 còn thiếu và sửa cách tính ngày:
--    1. Ngày theo giờ Việt Nam (Asia/Ho_Chi_Minh). Trước đây mọi mốc dùng current_date và
--       ::date theo múi giờ của DB (UTC), nên "một ngày" lệch 7 giờ so với giờ Việt Nam.
--       Các dòng đã có trước migration này vẫn là ngày UTC, không tính lại.
--    2. mart.system_daily.jobs_new_24h: tin chuẩn mới trong 24 giờ tính tới lúc làm mới
--       (ngày đã qua: 24 giờ cuối của ngày đó). jobs_new giữ nghĩa cũ: mới trong ngày.
--    3. mart.system_daily_source: tin đang mở và tin mới 24h theo từng nguồn (ops.sources).
--       Một tin chuẩn gắn nhiều nguồn được đếm ở mỗi nguồn, nên tổng theo nguồn có thể lớn
--       hơn mart.system_daily.jobs_open.
--    4. crawl_success_pct = null khi ngày đó không có lượt crawl nào (trước đây ghi 100).
--    5. pg_cron: 'refresh-system-daily' gọi hàm theo ngày Việt Nam; thêm
--       'refresh-system-daily-yesterday' lúc 00:02 giờ Việt Nam để chốt số của ngày hôm trước.
--
--  Lưu ý: jobs_open, users_* và tin mở theo nguồn là ảnh chụp tại lúc làm mới, không tính lại
--  được cho quá khứ. Gọi hàm cho một ngày đã qua sẽ ghi đè các cột này bằng số hiện tại.
--  Đối chiếu với đếm tay: db/tests/system_daily_check.sql.
--  Chạy lại nhiều lần được. Cần 0001, 0011.
-- =====================================================================================

-- 1. Cột mới của mart.system_daily ----------------------------------------------------------
alter table mart.system_daily add column if not exists jobs_new_24h integer;
alter table mart.system_daily add column if not exists refreshed_at timestamptz;

comment on table mart.system_daily is
  'Chỉ số vận hành theo ngày (giờ Việt Nam từ migration 0017), làm mới bằng mart.refresh_system_daily().';
comment on column mart.system_daily.jobs_open is
  'Tin chuẩn đang mở tại lúc làm mới, cùng điều kiện với api.v_open_jobs.';
comment on column mart.system_daily.jobs_new is
  'Tin chuẩn có first_seen_at trong ngày (giờ Việt Nam).';
comment on column mart.system_daily.jobs_new_24h is
  'Tin chuẩn có first_seen_at trong 24 giờ tính tới lúc làm mới (ngày đã qua: 24 giờ cuối ngày).';
comment on column mart.system_daily.matches is
  'Số lượt matching (app.match_requests) trong ngày.';
comment on column mart.system_daily.crawl_success_pct is
  '% lượt crawl success trong ngày; null khi ngày đó không có lượt crawl nào.';
comment on column mart.system_daily.refreshed_at is 'Lần làm mới gần nhất.';

-- 2. Bảng theo nguồn ----------------------------------------------------------------------
create table if not exists mart.system_daily_source (
  day          date     not null,
  source_id    smallint not null references ops.sources,
  jobs_open    integer  not null,
  jobs_new_24h integer  not null,
  refreshed_at timestamptz not null default now(),
  primary key (day, source_id)
);

comment on table mart.system_daily_source is
  'Tin theo nguồn mỗi ngày (giờ Việt Nam), làm mới cùng mart.refresh_system_daily().';
comment on column mart.system_daily_source.jobs_open is
  'Tin chuẩn đang mở có nguồn này còn đang đăng (core.job_sources.is_active).';
comment on column mart.system_daily_source.jobs_new_24h is
  'Tin nguồn (core.job_sources) nguồn này thấy lần đầu trong 24 giờ tính tới lúc làm mới, '
  'kể cả tin được gắn vào tin chuẩn có sẵn.';

alter table mart.system_daily_source enable row level security;
drop policy if exists admin_read on mart.system_daily_source;
create policy admin_read on mart.system_daily_source for select to authenticated
  using ((select app.is_active_user()) and (select app.jwt_role()) = 'admin');
grant select on mart.system_daily_source to authenticated;
revoke all on mart.system_daily_source from anon;

-- 3. Hàm làm mới ----------------------------------------------------------------------------
-- Đổi giá trị mặc định của tham số cần drop trước (create or replace không cho đổi default).
-- Giữ tên và kiểu tham số để lời gọi cũ mart.refresh_system_daily(<date>) vẫn chạy.
drop function if exists mart.refresh_system_daily(date);

create function mart.refresh_system_daily(
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
    (select (percentile_cont(0.95) within group (order by latency_ms))::int
       from app.match_requests
      where created_at >= v_from and created_at < v_to and latency_ms is not null),
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

-- 4. pg_cron (chỉ khi extension đã bật; cùng tên thì pg_cron cập nhật lịch cũ) ---------------
do $$ begin
  if exists (select 1 from pg_namespace where nspname = 'cron') then
    perform cron.schedule('refresh-system-daily', '*/15 * * * *',
      $cron$ select mart.refresh_system_daily() $cron$);
    -- 17:02 UTC = 00:02 giờ Việt Nam: chốt số của ngày vừa qua
    perform cron.schedule('refresh-system-daily-yesterday', '2 17 * * *',
      $cron$ select mart.refresh_system_daily((now() at time zone 'Asia/Ho_Chi_Minh')::date - 1) $cron$);
  end if;
end $$;

-- 5. Điền ngay số của hôm nay ----------------------------------------------------------------
select mart.refresh_system_daily();
