-- =====================================================================================
--  Migration 0013 — API Top N việc phù hợp (S4-D04, US-16)
--  Hai RPC cho API so khớp, gọi bằng JWT NGƯỜI DÙNG (như api.save_cv_profile):
--    api.get_cv_for_match  — hồ sơ CV để so khớp: chức danh, số năm, các mục đã che PII, kỹ năng
--                            (CV đã xác nhận thì chỉ lấy kỹ năng người dùng giữ lại)
--    api.save_match        — ghi app.match_requests + app.match_results trong một giao dịch
--  Người dùng chỉ có quyền select trên hai bảng kết quả; ghi đi qua api.save_match (security
--  definer, tự kiểm CV thuộc người gọi, tin là tin crawl, số kết quả ≤ top_n).
--
--  Mã lỗi:
--    42501  chưa đăng nhập / tài khoản bị khóa
--    P0002  không thấy CV (hoặc CV của người khác)
--    22023  dữ liệu sai: top_n ngoài 1–200, kết quả không phải mảng hoặc nhiều hơn top_n,
--           thiếu engine_version, tin không tồn tại hoặc không phải tin crawl
--  Chạy lại nhiều lần được. Cần 0012.
-- =====================================================================================

-- 1. Hồ sơ CV để so khớp -------------------------------------------------------------------
create or replace function api.get_cv_for_match(p_cv_id uuid)
returns jsonb
language plpgsql stable security invoker set search_path = '' as $$
declare
  v jsonb;
begin
  if auth.uid() is null then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  select jsonb_build_object(
           'cv_id', c.id,
           'parse_status', c.parse_status,
           'target_title', c.target_title,
           'years_exp', c.years_exp,
           'profile_confirmed_at', c.profile_confirmed_at,
           'sections', coalesce(c.parsed_sections, '{}'::jsonb),
           'skills', coalesce((
             select jsonb_agg(jsonb_build_object('skill_id', r.slug, 'name', r.name,
                                                 'evidence_level', s.evidence_level)
                              order by r.slug)
               from app.cv_skills s
               join ref.skills r on r.id = s.skill_id
              where s.cv_id = c.id
                -- Đã xác nhận: chỉ kỹ năng người dùng giữ lại (bỏ gợi ý mới của lần đọc lại).
                and (c.profile_confirmed_at is null or s.confirmed)
           ), '[]'::jsonb))
    into v
    from app.cvs c
   where c.id = p_cv_id and c.owner_user_id = auth.uid();
  if v is null then
    raise exception 'Không tìm thấy CV' using errcode = 'P0002';
  end if;
  return v;
end $$;

-- 2. Ghi một lượt Top N ----------------------------------------------------------------------
-- p_results: [{"rank": 1, "job_id": 12, "score": 82.4, "k": 0.91, "m": 0.75, "e": 0.88,
--              "x": null, "gap": {...}, "explanation": "..."}, ...]
create or replace function api.save_match(
  p_cv_id          uuid,
  p_top_n          integer,
  p_filters        jsonb,
  p_weights        jsonb,
  p_engine_version text,
  p_corpus_size    integer,
  p_latency_ms     integer,
  p_results        jsonb
) returns bigint
language plpgsql security definer set search_path = '' as $$
declare
  v_id  bigint;
  v_bad text;
begin
  if auth.uid() is null or not app.is_active_user() then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  perform 1 from app.cvs c where c.id = p_cv_id and c.owner_user_id = auth.uid();
  if not found then
    raise exception 'Không tìm thấy CV' using errcode = 'P0002';
  end if;
  if p_top_n is null or p_top_n not between 1 and 200 then
    raise exception 'top_n phải từ 1 đến 200' using errcode = '22023';
  end if;
  if coalesce(btrim(p_engine_version), '') = '' then
    raise exception 'Thiếu engine_version' using errcode = '22023';
  end if;
  if p_results is null or jsonb_typeof(p_results) <> 'array'
     or jsonb_array_length(p_results) > p_top_n then
    raise exception 'Danh sách kết quả không hợp lệ' using errcode = '22023';
  end if;
  select coalesce(r ->> 'job_id', 'null') into v_bad
    from jsonb_array_elements(p_results) r
    left join core.jobs j on j.id = (r ->> 'job_id')::bigint
   where j.id is null or j.origin <> 'crawled'
   limit 1;
  if found then
    raise exception 'Tin % không hợp lệ', v_bad using errcode = '22023';
  end if;

  insert into app.match_requests (kind, requester_id, cv_id, top_n, filters, weights,
                                  engine_version, corpus_size, latency_ms)
  values ('seeker_topn', auth.uid(), p_cv_id, p_top_n, coalesce(p_filters, '{}'::jsonb),
          coalesce(p_weights, '{}'::jsonb), p_engine_version, p_corpus_size, p_latency_ms)
  returning id into v_id;

  insert into app.match_results (request_id, rank, job_id, cv_id, score_h, k, m, e, x, gap,
                                 explanation)
  select v_id, (r ->> 'rank')::smallint, (r ->> 'job_id')::bigint, p_cv_id,
         (r ->> 'score')::numeric, (r ->> 'k')::real, (r ->> 'm')::real, (r ->> 'e')::real,
         (r ->> 'x')::real, r -> 'gap', r ->> 'explanation'
    from jsonb_array_elements(p_results) r;
  return v_id;
end $$;

revoke execute on function api.get_cv_for_match(uuid) from public, anon;
revoke execute on function api.save_match(uuid, integer, jsonb, jsonb, text, integer, integer, jsonb)
  from public, anon;
grant execute on function api.get_cv_for_match(uuid) to authenticated;
grant execute on function api.save_match(uuid, integer, jsonb, jsonb, text, integer, integer, jsonb)
  to authenticated;

notify pgrst, 'reload schema';
