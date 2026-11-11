-- =====================================================================================
--  Migration 0007 — Chi tiết một tin cho web (S2-H04, US-06; trang /viec-lam/[public_id])
--  api.v_job_detail: một dòng một tin crawl đang mở, kèm 4 section JD, toàn văn,
--  tỉnh/thành và các link nguồn. Thẻ kỹ năng lấy riêng từ api.v_job_skills (0006).
--  Cần 0001, 0003 (cột jd_text). Chạy lại nhiều lần được.
-- =====================================================================================

-- security_invoker: RLS của core.jobs, core.job_locations, core.job_sources vẫn áp dụng.
-- Không đọc ops.sources (chỉ admin đọc được): web suy ra tên nguồn từ host của url.
create or replace view api.v_job_detail
with (security_invoker = true) as
select
  j.public_id,
  j.title,
  c.name     as company_name,
  c.logo_url as company_logo_url,
  c.website  as company_website,
  jf.name    as job_family_name,
  j.seniority,
  j.work_mode,
  j.employment_type,
  j.years_exp_min,
  j.salary_raw,
  j.salary_min_vnd,
  j.salary_max_vnd,
  j.salary_is_negotiable,
  j.description,
  j.requirements,
  j.preferred,
  j.benefits,
  j.jd_text,                -- toàn văn: web dùng khi chưa tách được 4 section
  j.posted_at,
  j.valid_through,
  (j.valid_through is not null and j.valid_through <= current_date + 3) as is_expiring_soon,
  j.first_seen_at,
  j.last_seen_at,
  j.apply_url,
  coalesce((
    select array_agg(p.name order by p.name)
    from core.job_locations l
    join ref.provinces p on p.code = l.province_code
    where l.job_id = j.id
  ), '{}'::text[]) as provinces,
  coalesce((
    select jsonb_agg(jsonb_build_object('url', s.url, 'last_seen_at', s.last_seen_at)
                     order by s.last_seen_at desc)
    from core.job_sources s
    where s.job_id = j.id and s.is_active
  ), '[]'::jsonb) as sources
from core.jobs j
left join core.companies c   on c.id = j.company_id
left join ref.job_families jf on jf.id = j.job_family_id
where j.origin = 'crawled'
  and j.status = 'open'
  and (j.valid_through is null or j.valid_through >= current_date);

comment on view api.v_job_detail is
  'Chi tiết tin crawl đang mở (S2-H04): lọc theo public_id. Cùng điều kiện "đang mở" với '
  'api.v_open_jobs; tin đã đóng/hết hạn không trả về, web hiện "Tin không còn tuyển".';

grant select on api.v_job_detail to anon, authenticated;
