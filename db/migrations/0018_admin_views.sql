-- =====================================================================================
--  Migration 0018 — View cho trang Admin (S4-T02, S4-T03, US-18)
--  Web chỉ đọc qua schema api. Ba view dưới đây mở cho trang /admin và /admin/crawl-runs:
--    1. api.v_admin_system_daily        : mart.system_daily (thẻ số, biểu đồ crawl 7 ngày).
--    2. api.v_admin_system_daily_source : mart.system_daily_source kèm mã/tên nguồn.
--    3. api.v_admin_crawl_runs          : ops.crawl_runs kèm nguồn, thời lượng và báo cáo
--                                         chất lượng (ops.quality_reports) để xem lỗi từng lần chạy.
--  security_invoker = true: RLS của bảng gốc (admin_read) quyết định ai đọc được, nên chỉ
--  admin đang hoạt động thấy dữ liệu; vai trò khác nhận 0 dòng, anon bị chặn hẳn.
--  Chạy lại nhiều lần được. Cần 0001, 0017.
-- =====================================================================================

-- 1. Chỉ số theo ngày ----------------------------------------------------------------------
create or replace view api.v_admin_system_daily with (security_invoker = true) as
select d.day, d.jobs_open, d.jobs_new, d.jobs_new_24h, d.jobs_closed,
       d.users_seeker, d.users_hr, d.users_admin, d.logins_today,
       d.matches, d.p95_ms, d.crawl_success_pct, d.llm_cost_usd, d.refreshed_at
  from mart.system_daily d;

comment on view api.v_admin_system_daily is
  'Chỉ số vận hành theo ngày (giờ Việt Nam) cho trang Admin. Chỉ admin đọc được.';
grant select on api.v_admin_system_daily to authenticated;
revoke all on api.v_admin_system_daily from anon;

-- 2. Tin theo nguồn mỗi ngày -----------------------------------------------------------------
create or replace view api.v_admin_system_daily_source with (security_invoker = true) as
select d.day, d.source_id, s.code as source_code, s.name as source_name, s.is_enabled,
       d.jobs_open, d.jobs_new_24h, d.refreshed_at
  from mart.system_daily_source d
  join ops.sources s on s.id = d.source_id;

comment on view api.v_admin_system_daily_source is
  'Tin đang mở và tin mới 24h theo nguồn mỗi ngày cho trang Admin. Chỉ admin đọc được.';
grant select on api.v_admin_system_daily_source to authenticated;
revoke all on api.v_admin_system_daily_source from anon;

-- 3. Lịch sử crawl kèm chi tiết lỗi -----------------------------------------------------------
create or replace view api.v_admin_crawl_runs with (security_invoker = true) as
select r.id, r.source_id, s.code as source_code, s.name as source_name,
       r.run_type, r.status, r.started_at, r.finished_at,
       extract(epoch from (r.finished_at - r.started_at))::numeric(12,1) as duration_s,
       r.pages_fetched, r.items_seen, r.items_new, r.items_updated, r.items_closed,
       r.http_errors, r.error_sample,
       q.completeness, q.validity, q.uniqueness, q.salary_parsed_pct, q.province_parsed_pct,
       q.schema_errors, q.freshness_hours, q.details as quality_details
  from ops.crawl_runs r
  join ops.sources s on s.id = r.source_id
  left join ops.quality_reports q on q.run_id = r.id;

comment on view api.v_admin_crawl_runs is
  'Lịch sử crawl: mỗi lần chạy kèm nguồn, thời lượng (giây, null khi đang chạy), lỗi HTTP, '
  'mẫu lỗi và báo cáo chất lượng. Chỉ admin đọc được.';
grant select on api.v_admin_crawl_runs to authenticated;
revoke all on api.v_admin_crawl_runs from anon;
