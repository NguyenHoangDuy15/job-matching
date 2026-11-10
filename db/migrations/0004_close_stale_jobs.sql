-- =====================================================================
--  Migration 0004 — Tự động đóng tin hết hạn / bị gỡ (S2-T06, US-08)
--  Chạy SAU 0001..0003. Chạy lại nhiều lần không lỗi.
--
--  Ba đường đóng tin crawl, đều GIỮ dòng trong core.jobs (chỉ đổi status):
--    1. valid_through đã qua                      → status 'expired', close_reason 'expired'
--    2. trang chi tiết trả HTTP 404/410            → status 'closed',  close_reason 'gone'
--    3. vắng mặt 3 lượt quét đủ danh sách liên tiếp → status 'closed',  close_reason 'missing'
--  api.v_open_jobs và api.search_jobs chỉ lấy status = 'open' nên tin tự ẩn khỏi web.
--
--  Một tin có thể đến từ nhiều nguồn (core.job_sources). Đếm vắng mặt theo TỪNG nguồn;
--  tin chỉ đóng khi không còn nguồn nào đang theo dõi (is_active).
--  Tin gặp lại sau khi đóng vì 'gone'/'missing' được crawler mở lại (ingestion.store).
-- =====================================================================

-- 1. Cột mới -----------------------------------------------------------------
alter table core.jobs add column if not exists close_reason text;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'jobs_close_reason_check') then
    alter table core.jobs add constraint jobs_close_reason_check
      check (close_reason is null
             or close_reason in ('expired', 'gone', 'missing', 'duplicate', 'manual'));
  end if;
end $$;

comment on column core.jobs.close_reason is
  'Vì sao tin không còn mở: expired (quá hạn nộp), gone (nguồn trả 404/410), '
  'missing (vắng 3 lượt quét liên tiếp), duplicate (gộp trùng), manual. NULL khi đang mở.';

alter table core.job_sources add column if not exists missed_runs smallint not null default 0;

comment on column core.job_sources.missed_runs is
  'Số lượt quét đủ danh sách liên tiếp mà nguồn này không còn tin. Gặp lại thì về 0.';

comment on column core.jobs.missed_runs is
  'Số lượt vắng mặt nhỏ nhất trong các nguồn còn theo dõi của tin (đồng bộ từ core.job_sources).';

-- Tin đã mang status 'expired' từ trước (nạp khi đã quá hạn): ghi lý do cho thống nhất.
update core.jobs set close_reason = 'expired' where status = 'expired' and close_reason is null;

-- 2. Đóng các tin crawl không còn nguồn nào theo dõi ---------------------------------
create or replace function core.close_orphan_jobs(p_job_ids bigint[], p_reason text)
returns integer language plpgsql set search_path = '' as $$
declare
  v_closed integer;
begin
  update core.jobs j
     set status = 'closed', close_reason = p_reason
   where j.id = any (p_job_ids)
     and j.origin = 'crawled'
     and j.status = 'open'
     and exists (select 1 from core.job_sources s where s.job_id = j.id)
     and not exists (select 1 from core.job_sources s where s.job_id = j.id and s.is_active);
  get diagnostics v_closed = row_count;
  return v_closed;
end $$;

-- 3. Trang chi tiết trả 404/410: ngừng theo dõi nguồn đó ngay ------------------------
create or replace function core.mark_posting_gone(p_source_id smallint, p_source_job_id text)
returns integer language plpgsql set search_path = '' as $$
declare
  v_job_id bigint;
begin
  update core.job_sources
     set is_active = false
   where source_id = p_source_id and source_job_id = p_source_job_id and is_active
  returning job_id into v_job_id;
  if v_job_id is null then
    return 0;
  end if;
  return core.close_orphan_jobs(array[v_job_id], 'gone');
end $$;

-- 4. Sau một lượt quét ĐỦ danh sách của một nguồn: đếm vắng mặt ------------------------
--    p_run_started = ops.crawl_runs.started_at của lượt đó. Tin nguồn nào có last_seen_at
--    trước mốc này là không gặp trong lượt.
create or replace function core.mark_source_missing(
  p_source_id smallint,
  p_run_started timestamptz,
  p_threshold integer default 3
) returns integer language plpgsql set search_path = '' as $$
declare
  v_jobs bigint[];
  v_dropped bigint[];
begin
  with missed as (
    update core.job_sources
       set missed_runs = missed_runs + 1
     where source_id = p_source_id and is_active and last_seen_at < p_run_started
    returning job_id
  )
  select array_agg(distinct job_id) into v_jobs from missed;

  with dropped as (
    update core.job_sources
       set is_active = false
     where source_id = p_source_id and is_active and missed_runs >= p_threshold
    returning job_id
  )
  select array_agg(distinct job_id) into v_dropped from dropped;

  -- Đồng bộ bộ đếm cấp tin: số lượt vắng nhỏ nhất trong các nguồn còn theo dõi.
  update core.jobs j
     set missed_runs = coalesce(
           (select min(s.missed_runs) from core.job_sources s
             where s.job_id = j.id and s.is_active),
           p_threshold)
   where j.id = any (coalesce(v_jobs, '{}'));

  return core.close_orphan_jobs(coalesce(v_dropped, '{}'), 'missing');
end $$;

-- 5. Quét toàn bảng: hết hạn nộp + lưới an toàn cho tin mồ côi ---------------------------
--    Gọi sau mỗi lượt crawl và hằng ngày bằng pg_cron (tin hết hạn dù hôm đó không crawl).
create or replace function core.close_stale_jobs()
returns table (expired integer, closed integer)
language plpgsql set search_path = '' as $$
declare
  v_expired integer;
  v_closed integer;
begin
  update core.jobs
     set status = 'expired', close_reason = 'expired'
   where origin = 'crawled' and status = 'open'
     and valid_through is not null and valid_through < current_date;
  get diagnostics v_expired = row_count;

  select core.close_orphan_jobs(array_agg(j.id), 'missing') into v_closed
    from core.jobs j
   where j.origin = 'crawled' and j.status = 'open'
     and exists (select 1 from core.job_sources s where s.job_id = j.id)
     and not exists (select 1 from core.job_sources s where s.job_id = j.id and s.is_active);

  return query select v_expired, coalesce(v_closed, 0);
end $$;

-- Chỉ worker (postgres / service_role) và pg_cron gọi các hàm này.
revoke execute on function core.close_orphan_jobs(bigint[], text) from public, anon, authenticated;
revoke execute on function core.mark_posting_gone(smallint, text) from public, anon, authenticated;
revoke execute on function core.mark_source_missing(smallint, timestamptz, integer)
  from public, anon, authenticated;
revoke execute on function core.close_stale_jobs() from public, anon, authenticated;

-- 6. Lịch hằng ngày 00:05 giờ Việt Nam (17:05 UTC), chỉ khi có pg_cron -------------------
do $$ begin
  if exists (select 1 from pg_namespace where nspname = 'cron') then
    perform cron.schedule('close-stale-jobs', '5 17 * * *',
                          $cron$ select * from core.close_stale_jobs() $cron$);
  end if;
end $$;
