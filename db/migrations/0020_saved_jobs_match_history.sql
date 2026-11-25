-- =====================================================================================
--  Migration 0020 — Việc đã lưu + lịch sử gợi ý của người tìm việc (S4-H05)
--  Web chỉ đọc/ghi qua schema api:
--    1. api.v_my_saved_jobs     : việc đã lưu của mình, kèm cờ tin còn mở hay đã đóng.
--    2. api.save_job(p_job_id)  : lưu một tin (gọi lại nhiều lần vẫn chỉ một dòng).
--       api.unsave_job(p_job_id): bỏ lưu.
--       p_job_id là public_id (uuid) của tin, cùng id web dùng trên URL /viec-lam/[public_id]
--       và có sẵn trong kết quả /match/jobs.
--    3. api.v_my_match_history  : 10 lượt Top N gần nhất của mình, mỗi dòng một lượt,
--                                 kết quả từng lượt nằm trong cột results (jsonb, theo rank).
--  Tất cả là security invoker: RLS saved_own, match_req_read, match_res_read, jobs_read
--  của bảng gốc vẫn áp dụng, tài khoản bị khóa nhận 0 dòng, anon bị chặn hẳn.
--
--  Mã lỗi save_job / unsave_job (web dịch sang tiếng Việt theo errcode):
--    42501  chưa đăng nhập / tài khoản bị khóa
--    P0002  không thấy tin (không tồn tại hoặc không phải tin crawl)
--  Chạy lại nhiều lần được. Cần 0001, 0011 (core.jobs.duplicate_of, close_reason).
-- =====================================================================================

-- 1. Việc đã lưu -------------------------------------------------------------------------
-- is_open dùng đúng điều kiện "đang mở" của api.v_open_jobs: status open và chưa quá hạn nộp.
create or replace view api.v_my_saved_jobs
with (security_invoker = true) as
select
  j.public_id,
  j.title,
  c.name     as company_name,
  c.logo_url as company_logo_url,
  j.valid_through,
  (j.status = 'open' and (j.valid_through is null or j.valid_through >= current_date)) as is_open,
  j.status,
  j.closed_at,
  s.saved_at
from app.saved_jobs s
join core.jobs j on j.id = s.job_id
left join core.companies c on c.id = j.company_id
where s.user_id = auth.uid();

comment on view api.v_my_saved_jobs is
  'Việc đã lưu của người đang đăng nhập (S4-H05). is_open = tin còn mở và chưa quá hạn nộp. '
  'Web sắp theo saved_at desc.';
grant select on api.v_my_saved_jobs to authenticated;
revoke all on api.v_my_saved_jobs from anon;

-- 2. Lưu / bỏ lưu ----------------------------------------------------------------------------
-- Tin đã bị gộp (core.merge_jobs) thì lưu tin được giữ lại, giống cách merge_jobs chuyển
-- app.saved_jobs. Trả true khi vừa lưu, false khi đã lưu từ trước.
create or replace function api.save_job(p_job_id uuid)
returns boolean
language plpgsql security invoker set search_path = '' as $$
declare
  v_job  bigint;
  v_rows integer;
begin
  if auth.uid() is null or not app.is_active_user() then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  select coalesce(j.duplicate_of, j.id) into v_job
    from core.jobs j
   where j.public_id = p_job_id and j.origin = 'crawled';
  if v_job is null then
    raise exception 'Không tìm thấy tin' using errcode = 'P0002';
  end if;
  insert into app.saved_jobs (user_id, job_id) values (auth.uid(), v_job)
  on conflict (user_id, job_id) do nothing;
  get diagnostics v_rows = row_count;
  return v_rows > 0;
end $$;

-- Trả true khi đã bỏ lưu, false khi tin chưa được lưu.
create or replace function api.unsave_job(p_job_id uuid)
returns boolean
language plpgsql security invoker set search_path = '' as $$
declare
  v_job  bigint;
  v_rows integer;
begin
  if auth.uid() is null or not app.is_active_user() then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  select coalesce(j.duplicate_of, j.id) into v_job
    from core.jobs j
   where j.public_id = p_job_id and j.origin = 'crawled';
  if v_job is null then
    raise exception 'Không tìm thấy tin' using errcode = 'P0002';
  end if;
  delete from app.saved_jobs s where s.user_id = auth.uid() and s.job_id = v_job;
  get diagnostics v_rows = row_count;
  return v_rows > 0;
end $$;

revoke execute on function api.save_job(uuid)   from public, anon;
revoke execute on function api.unsave_job(uuid) from public, anon;
grant execute on function api.save_job(uuid)   to authenticated;
grant execute on function api.unsave_job(uuid) to authenticated;

-- 3. Lịch sử gợi ý ---------------------------------------------------------------------------
-- 10 lượt seeker_topn gần nhất của chính mình (dùng index match_requests_user_idx).
-- results: [{"rank", "public_id", "title", "company_name", "score_h", "k", "m", "e", "x"}]
-- theo rank; k/m/e/x null = thành phần không xác định (giữ nguyên như app.match_results).
create or replace view api.v_my_match_history
with (security_invoker = true) as
select
  r.id,
  r.cv_id,
  cv.target_title as cv_target_title,
  r.top_n,
  r.filters,
  r.created_at,
  coalesce(res.result_count, 0) as result_count,
  coalesce(res.results, '[]'::jsonb) as results
from (
  select mr.*
    from app.match_requests mr
   where mr.requester_id = auth.uid() and mr.kind = 'seeker_topn'
   order by mr.created_at desc, mr.id desc
   limit 10
) r
left join app.cvs cv on cv.id = r.cv_id
left join lateral (
  select count(*)::int as result_count,
         jsonb_agg(jsonb_build_object(
                     'rank', m.rank,
                     'public_id', j.public_id,
                     'title', j.title,
                     'company_name', c.name,
                     'score_h', m.score_h,
                     'k', m.k, 'm', m.m, 'e', m.e, 'x', m.x)
                   order by m.rank) as results
    from app.match_results m
    left join core.jobs j on j.id = m.job_id
    left join core.companies c on c.id = j.company_id
   where m.request_id = r.id
) res on true;

comment on view api.v_my_match_history is
  '10 lượt gợi ý Top N gần nhất của người đang đăng nhập (S4-H05), mới nhất trước. '
  'results: kết quả từng lượt theo rank (public_id, title, company_name, score_h, k, m, e, x).';
grant select on api.v_my_match_history to authenticated;
revoke all on api.v_my_match_history from anon;

-- PostgREST (Supabase) đọc lại schema để thấy view / hàm mới ngay
notify pgrst, 'reload schema';
