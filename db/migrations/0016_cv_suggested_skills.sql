-- =====================================================================================
--  Migration 0016 — Lưu kỹ năng gợi ý của CV (tiếp #678)
--  Kỹ năng CV có nhắc nhưng chưa đủ bằng chứng ("Câu lạc bộ tiếng Nhật", ngoại ngữ không ghi
--  trình độ) trước đây chỉ có trong phản hồi /cv/parse; trang Xác nhận đọc từ DB nên mất gợi ý
--  khi chuyển trang / F5 / vào lại từ "Hồ sơ của tôi".
--    1. app.cvs.suggested_skills jsonb: gợi ý của lần đọc CV gần nhất (mảng, mặc định [])
--    2. api.save_cv_profile nhận thêm p_suggested_skills (default null → []): API ghi lúc đọc CV
--    3. api.v_my_cvs thêm cột suggested_skills ở CUỐI (cột cũ giữ nguyên thứ tự)
--
--  Gợi ý KHÔNG tính điểm, không nằm trong app.cv_skills. Người dùng tick → confirm_cv_profile
--  lưu user_added như kỹ năng tự thêm; web tự ẩn gợi ý đã có trong cv_skills.
--  Mỗi phần tử: {"skill_id": "<slug>", "name": "...", "reason": "org_name|language_no_proficiency",
--                "evidence": "...", "highlight": [s, e], "section": "..."}
--  DB lọc lại: chỉ slug có trong ref.skills (đang dùng), reason hợp lệ, tối đa 50 phần tử,
--  câu trích ≤ 400 ký tự; name lấy từ ref.skills.
--  Chạy lại nhiều lần được. Cần 0010, 0015.
-- =====================================================================================

-- 1. Cột lưu gợi ý -------------------------------------------------------------------------
alter table app.cvs
  add column if not exists suggested_skills jsonb not null default '[]'::jsonb;

do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'cvs_suggested_skills_array'
                    and conrelid = 'app.cvs'::regclass) then
    alter table app.cvs add constraint cvs_suggested_skills_array
      check (jsonb_typeof(suggested_skills) = 'array');
  end if;
end $$;

comment on column app.cvs.suggested_skills is
  'Kỹ năng gợi ý của lần đọc CV gần nhất (chưa đủ bằng chứng, không tính điểm). Ghi bởi api.save_cv_profile.';

-- 2. api.save_cv_profile nhận thêm p_suggested_skills ---------------------------------------
-- Bỏ bản 7 tham số: để cả hai cùng tồn tại thì lời gọi 7 tham số bị mơ hồ. p_suggested_skills
-- có default null nên API bản cũ (chưa gửi gợi ý) vẫn gọi được, gợi ý khi đó là [].
drop function if exists api.save_cv_profile(uuid, text, jsonb, numeric, text, jsonb, text);

create or replace function api.save_cv_profile(
  p_cv_id            uuid,
  p_text_redacted    text,
  p_sections         jsonb,
  p_years_exp        numeric,
  p_target_title     text,
  p_skills           jsonb,
  p_parser_version   text,
  p_suggested_skills jsonb default null
) returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  v_rows      integer;
  v_suggested jsonb;
begin
  select coalesce(jsonb_agg(jsonb_build_object(
           'skill_id', r.slug,
           'name', r.name,
           'reason', e.item ->> 'reason',
           'evidence', left(e.item ->> 'evidence', 400),
           'highlight', case when jsonb_typeof(e.item -> 'highlight') = 'array'
                             then e.item -> 'highlight' end,
           'section', left(e.item ->> 'section', 40))
           order by e.ord), '[]'::jsonb)
    into v_suggested
    from jsonb_array_elements(
           case when jsonb_typeof(p_suggested_skills) = 'array'
                then p_suggested_skills else '[]'::jsonb end
         ) with ordinality as e(item, ord)
    join ref.skills r on r.slug = e.item ->> 'skill_id' and r.is_active
   where e.item ->> 'reason' in ('org_name', 'language_no_proficiency')
     and e.ord <= 50;

  update app.cvs c
     set text_redacted    = p_text_redacted,
         parsed_sections  = p_sections,
         years_exp        = case when c.profile_confirmed_at is null
                                 then round(p_years_exp, 1) else c.years_exp end,
         target_title     = case when c.profile_confirmed_at is null
                                 then left(p_target_title, 200) else c.target_title end,
         suggested_skills = v_suggested,
         parse_status     = 'parsed',
         parse_error      = null,
         parser_version   = p_parser_version
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

revoke execute on function api.save_cv_profile(uuid, text, jsonb, numeric, text, jsonb, text, jsonb)
  from public, anon;
grant execute on function api.save_cv_profile(uuid, text, jsonb, numeric, text, jsonb, text, jsonb)
  to authenticated;

-- 3. api.v_my_cvs thêm suggested_skills ở cuối ----------------------------------------------
create or replace view api.v_my_cvs
with (security_invoker = true) as
select c.id, c.storage_path, c.mime, c.size_bytes, c.parse_status, c.is_primary,
       c.consent_version, c.consent_at, c.created_at,
       c.years_exp, c.target_title, c.parse_error, c.original_name, c.profile_confirmed_at,
       c.delete_after, c.suggested_skills
from app.cvs c
where c.owner_user_id = auth.uid();

grant select on api.v_my_cvs to authenticated;

notify pgrst, 'reload schema';
