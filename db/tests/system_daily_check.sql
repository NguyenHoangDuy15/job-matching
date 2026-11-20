-- =====================================================================================
--  Đối chiếu mart.system_daily / mart.system_daily_source với đếm tay (S4-T01, US-18)
--  Dán cả file vào Supabase → SQL Editor rồi Run. Kết quả: mỗi chỉ số một dòng,
--  cột khop = true là số trong mart bằng số đếm tay.
--
--  Đếm tay viết theo cách khác hàm làm mới (đổi cột thời gian sang giờ Việt Nam rồi so ngày,
--  group by thay cho subquery) để không lặp lại cùng một lỗi.
--  Bước 1 làm mới số của hôm nay (chỉ ghi vào mart). Muốn chỉ đọc thì xóa dòng đó; khi ấy dữ
--  liệu có thể đã đổi sau lần cron chạy gần nhất (≤ 15 phút) nên vài dòng có thể lệch nhẹ.
-- =====================================================================================

select mart.refresh_system_daily();

with
  d as (select (now() at time zone 'Asia/Ho_Chi_Minh')::date as day),
  m as (select s.* from mart.system_daily s, d where s.day = d.day),
  jobs as (
    select j.*,
           (j.first_seen_at at time zone 'Asia/Ho_Chi_Minh')::date as seen_vn,
           (j.closed_at     at time zone 'Asia/Ho_Chi_Minh')::date as closed_vn
      from core.jobs j where j.origin = 'crawled'),
  roles as (
    select role, status, count(*) as n from app.profiles group by role, status),
  tay as (
    select 'jobs_open' as chi_so, count(*) filter (
             where status = 'open' and (valid_through is null or valid_through >= (select day from d))) as n
      from jobs
    union all
    select 'jobs_new', count(*) filter (where seen_vn = (select day from d)) from jobs
    union all
    select 'jobs_new_24h', count(*) filter (
             where first_seen_at >  (select refreshed_at from m) - interval '24 hours'
               and first_seen_at <= (select refreshed_at from m))
      from jobs
    union all
    select 'jobs_closed', count(*) filter (where closed_vn = (select day from d)) from jobs
    union all
    select 'users_seeker', coalesce(sum(n) filter (where role = 'seeker' and status <> 'locked'), 0) from roles
    union all
    select 'users_hr', coalesce(sum(n) filter (where role = 'hr' and status = 'active'), 0) from roles
    union all
    select 'users_admin', coalesce(sum(n) filter (where role = 'admin' and status = 'active'), 0) from roles
    union all
    select 'logins_today', count(*) from app.audit_log
     where action = 'login' and (at at time zone 'Asia/Ho_Chi_Minh')::date = (select day from d)
    union all
    select 'matches', count(*) from app.match_requests
     where (created_at at time zone 'Asia/Ho_Chi_Minh')::date = (select day from d)
  )
select 'system_daily' as bang, t.chi_so,
       case t.chi_so
         when 'jobs_open'    then m.jobs_open
         when 'jobs_new'     then m.jobs_new
         when 'jobs_new_24h' then m.jobs_new_24h
         when 'jobs_closed'  then m.jobs_closed
         when 'users_seeker' then m.users_seeker
         when 'users_hr'     then m.users_hr
         when 'users_admin'  then m.users_admin
         when 'logins_today' then m.logins_today
         when 'matches'      then m.matches
       end as mart,
       t.n as dem_tay,
       case t.chi_so
         when 'jobs_open'    then m.jobs_open
         when 'jobs_new'     then m.jobs_new
         when 'jobs_new_24h' then m.jobs_new_24h
         when 'jobs_closed'  then m.jobs_closed
         when 'users_seeker' then m.users_seeker
         when 'users_hr'     then m.users_hr
         when 'users_admin'  then m.users_admin
         when 'logins_today' then m.logins_today
         when 'matches'      then m.matches
       end = t.n as khop
  from tay t cross join m

union all

-- Theo nguồn: tin đang mở mà nguồn còn đăng, và tin nguồn thấy lần đầu trong 24 giờ
select 'system_daily_source', o.code || '.jobs_open',
       ms.jobs_open,
       (select count(*) from (
          select distinct s.job_id
            from core.job_sources s join core.jobs j on j.id = s.job_id
           where s.source_id = o.id and s.is_active and j.origin = 'crawled' and j.status = 'open'
             and (j.valid_through is null or j.valid_through >= (select day from d))) x),
       ms.jobs_open = (select count(*) from (
          select distinct s.job_id
            from core.job_sources s join core.jobs j on j.id = s.job_id
           where s.source_id = o.id and s.is_active and j.origin = 'crawled' and j.status = 'open'
             and (j.valid_through is null or j.valid_through >= (select day from d))) x)
  from ops.sources o
  join mart.system_daily_source ms on ms.source_id = o.id and ms.day = (select day from d)

union all

select 'system_daily_source', o.code || '.jobs_new_24h',
       ms.jobs_new_24h,
       (select count(*) from core.job_sources s
         where s.source_id = o.id
           and s.first_seen_at > ms.refreshed_at - interval '24 hours'
           and s.first_seen_at <= ms.refreshed_at),
       ms.jobs_new_24h = (select count(*) from core.job_sources s
         where s.source_id = o.id
           and s.first_seen_at > ms.refreshed_at - interval '24 hours'
           and s.first_seen_at <= ms.refreshed_at)
  from ops.sources o
  join mart.system_daily_source ms on ms.source_id = o.id and ms.day = (select day from d)
order by 1, 2;
