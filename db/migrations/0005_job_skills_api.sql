-- =====================================================================================
--  Migration 0005 — Thẻ kỹ năng cho web (S2-D05, US-10; dùng ở S2-H04 Trang chi tiết)
--  1. api.v_job_skills: kỹ năng bắt buộc / ưu tiên của từng tin (không có `mentioned`).
--  2. api.search_jobs: lọc theo kỹ năng chỉ tính bắt buộc / ưu tiên.
--  Cần 0004. Chạy lại nhiều lần được.
-- =====================================================================================

-- 1. Thẻ kỹ năng ------------------------------------------------------------------------
-- security_invoker: RLS của core.jobs / core.job_skills vẫn áp dụng (anon chỉ thấy tin mở).
create or replace view api.v_job_skills
with (security_invoker = true) as
select
  j.public_id      as job_public_id,
  s.slug           as skill_slug,
  s.name           as skill_name,
  c.name           as category,
  js.level,
  js.extractor,
  js.confidence,
  js.evidence,
  js.section,
  js.mention_count
from core.job_skills js
join core.jobs j            on j.id = js.job_id
join ref.skills s           on s.id = js.skill_id
join ref.skill_categories c on c.id = s.category_id
where js.level in ('required', 'preferred');

comment on view api.v_job_skills is
  'Thẻ kỹ năng của tin (S2-H04): lọc theo job_public_id, sắp theo level rồi confidence. '
  'Kỹ năng chỉ được nhắc trong mô tả (level = mentioned) không hiện.';

grant select on api.v_job_skills to anon, authenticated;

-- 2. Tìm việc: lọc kỹ năng bỏ qua `mentioned` -------------------------------------------
-- Giữ nguyên chữ ký và nội dung của 0001, chỉ thêm điều kiện level.
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
                                   where s.job_id = j.id and s.skill_id = any (skills)
                                     and s.level in ('required', 'preferred')))
  order by rank desc, j.last_seen_at desc
  limit least(page_size, 50) offset (greatest(page, 1) - 1) * least(page_size, 50)
$$;
