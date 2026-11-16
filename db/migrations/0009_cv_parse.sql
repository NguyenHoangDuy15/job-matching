-- =====================================================================================
--  Migration 0009 — Đọc CV qua API (S3-D05, US-12)
--  API POST /cv/parse gọi 3 hàm dưới đây BẰNG JWT CỦA NGƯỜI DÙNG (security invoker):
--  RLS của app.cvs / app.cv_skills tự chặn mọi CV không phải của họ, API không giữ khóa bí mật.
--    1. api.claim_cv_parse:  queued/failed/parsed → parsing (chống hai request chạy song song)
--    2. api.save_cv_profile: ghi văn bản đã che PII, section, số năm, chức danh, kỹ năng
--    3. api.fail_cv_parse:   parsing → failed + mã lỗi để UI hiện lý do
--  Chạy lại nhiều lần được. Cần 0008.
-- =====================================================================================

alter table app.cvs
  add column if not exists parse_started_at timestamptz,
  add column if not exists parser_version   text;     -- "cvparser-1/pdf-2|pii-1|cv-sections-1|cv-profile-1"

-- 1. Nhận CV để đọc --------------------------------------------------------------------
-- Trả đường dẫn file để API tải từ Storage (cũng bằng JWT người dùng).
-- Lỗi: P0002 = không thấy CV (hoặc CV của người khác, RLS ẩn); 55P03 = đang được đọc.
-- Một lần đọc kẹt quá 2 phút (API chết giữa chừng) được nhận lại.
create or replace function api.claim_cv_parse(p_cv_id uuid)
returns table (storage_path text, mime text, size_bytes integer)
language plpgsql security invoker set search_path = '' as $$
declare
  v_status  text;
  v_started timestamptz;
begin
  if auth.uid() is null then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  select c.parse_status, c.parse_started_at into v_status, v_started
    from app.cvs c where c.id = p_cv_id
    for update;
  if not found then
    raise exception 'cv_not_found' using errcode = 'P0002';
  end if;
  if v_status = 'parsing' and v_started > now() - interval '2 minutes' then
    raise exception 'parse_in_progress' using errcode = '55P03';
  end if;
  return query
    update app.cvs c
       set parse_status = 'parsing', parse_error = null, parse_started_at = now()
     where c.id = p_cv_id
    returning c.storage_path, c.mime, c.size_bytes;
end $$;

-- 2. Lưu hồ sơ ---------------------------------------------------------------------------
-- p_skills: [{"skill_id": "<slug ref.skills>", "evidence_level": "strong|listed",
--             "evidence": "...", "years": 3.8}, ...]  (CvProfile.skills của cvparser.profile)
-- Thay các dòng kỹ năng do máy tạo; GIỮ dòng người dùng đã xác nhận hoặc tự thêm.
-- Trả số kỹ năng đã ghi.
create or replace function api.save_cv_profile(
  p_cv_id          uuid,
  p_text_redacted  text,
  p_sections       jsonb,
  p_years_exp      numeric,
  p_target_title   text,
  p_skills         jsonb,
  p_parser_version text
) returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  v_rows integer;
begin
  update app.cvs c
     set text_redacted   = p_text_redacted,
         parsed_sections = p_sections,
         years_exp       = round(p_years_exp, 1),
         target_title    = left(p_target_title, 200),
         parse_status    = 'parsed',
         parse_error     = null,
         parser_version  = p_parser_version
   where c.id = p_cv_id and c.parse_status = 'parsing';
  if not found then
    raise exception 'cv_not_claimed' using errcode = '55000';
  end if;

  delete from app.cv_skills s
   where s.cv_id = p_cv_id and not s.confirmed and s.evidence_level <> 'user_added';

  insert into app.cv_skills (cv_id, skill_id, evidence_level, evidence, years)
  select p_cv_id, r.id, (x ->> 'evidence_level')::app.evidence_level,
         left(x ->> 'evidence', 400), nullif(x ->> 'years', '')::numeric
    from jsonb_array_elements(coalesce(p_skills, '[]'::jsonb)) x
    join ref.skills r on r.slug = x ->> 'skill_id' and r.is_active
   where x ->> 'evidence_level' in ('strong', 'listed')
  on conflict (cv_id, skill_id) do nothing;   -- dòng đã xác nhận / tự thêm giữ nguyên
  get diagnostics v_rows = row_count;
  return v_rows;
end $$;

-- 3. Đánh dấu lỗi ------------------------------------------------------------------------
create or replace function api.fail_cv_parse(p_cv_id uuid, p_code text)
returns void
language plpgsql security invoker set search_path = '' as $$
begin
  update app.cvs c
     set parse_status = 'failed', parse_error = left(p_code, 100)
   where c.id = p_cv_id and c.parse_status = 'parsing';
end $$;

revoke execute on function api.claim_cv_parse(uuid) from public, anon;
revoke execute on function api.save_cv_profile(uuid, text, jsonb, numeric, text, jsonb, text)
  from public, anon;
revoke execute on function api.fail_cv_parse(uuid, text) from public, anon;
grant execute on function api.claim_cv_parse(uuid) to authenticated;
grant execute on function api.save_cv_profile(uuid, text, jsonb, numeric, text, jsonb, text)
  to authenticated;
grant execute on function api.fail_cv_parse(uuid, text) to authenticated;
