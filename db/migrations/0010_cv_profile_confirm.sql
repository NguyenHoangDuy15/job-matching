-- =====================================================================================
--  Migration 0010 — Màn xác nhận kỹ năng và lưu hồ sơ CV (S3-H02, S3-H03, US-12)
--  Web chỉ đọc được schema api, nên mọi thứ dưới đây đều nằm ở api:
--    1. api.v_my_cv_skills:    kỹ năng của CV của chính mình (tên lấy từ ref.skills)
--    2. api.v_skills:          từ điển kỹ năng đang dùng + alias, cho ô gợi ý khi tự thêm
--    3. api.v_my_cvs:          thêm years_exp, target_title, parse_error, original_name,
--                              profile_confirmed_at (thêm cột ở CUỐI view, cột cũ giữ nguyên)
--    4. api.confirm_cv_profile: lưu danh sách kỹ năng CUỐI CÙNG + số năm + chức danh
--    5. Tối đa 5 CV / người tìm việc: chặn ở DB (trigger), không chỉ ở giao diện
--    6. Tên tệp gốc: app.cvs.original_name, api.register_cv nhận thêm p_original_name
--    7. api.save_cv_profile (0009): đọc lại CV không ghi đè số năm / chức danh đã xác nhận
--
--  Mã lỗi api.confirm_cv_profile (web dịch sang tiếng Việt theo errcode):
--    42501  chưa đăng nhập
--    P0002  không thấy CV (hoặc CV của người khác, RLS ẩn)
--    55000  CV chưa đọc xong (parse_status khác 'parsed'), ví dụ đang đọc lại
--    22023  dữ liệu gửi lên sai: số năm ngoài 0–60, p_skills không phải mảng,
--           skill_id không phải số, kỹ năng không có trong từ điển, quá 100 kỹ năng
--  Mã lỗi mới của api.register_cv:
--    53400  đã có đủ 5 CV
--
--  Chạy lại nhiều lần được. Cần 0009.
-- =====================================================================================

-- 0. Cột mới trên app.cvs ---------------------------------------------------------------
alter table app.cvs
  add column if not exists original_name        text,
  add column if not exists profile_confirmed_at timestamptz;

do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'cvs_original_name_len' and conrelid = 'app.cvs'::regclass
  ) then
    alter table app.cvs add constraint cvs_original_name_len
      check (original_name is null or char_length(original_name) between 1 and 255);
  end if;
end $$;

comment on column app.cvs.original_name is
  'Tên tệp người dùng chọn khi tải lên, chỉ để hiển thị. Có thể chứa họ tên: không đưa vào text_redacted hay prompt LLM.';
comment on column app.cvs.profile_confirmed_at is
  'Lần cuối người dùng bấm Lưu hồ sơ (api.confirm_cv_profile). null = chưa xác nhận.';

-- 1. Kỹ năng của CV ---------------------------------------------------------------------
-- Lọc thêm owner_user_id = auth.uid(): RLS cv_child cho HR đọc CV ứng viên của công ty,
-- nhưng view này chỉ phục vụ hồ sơ của chính người tìm việc.
create or replace view api.v_my_cv_skills
with (security_invoker = true) as
select s.cv_id, s.skill_id, r.slug, r.name, s.evidence_level, s.evidence, s.years, s.confirmed
from app.cv_skills s
join app.cvs c on c.id = s.cv_id
join ref.skills r on r.id = s.skill_id
where c.owner_user_id = auth.uid();

grant select on api.v_my_cv_skills to authenticated;

-- 2. Từ điển kỹ năng cho ô gợi ý -----------------------------------------------------------
-- aliases: alias_norm đã NFC + chữ thường, GIỮ dấu (xem 0003). Web so khớp chữ người gõ
-- đã hạ chữ thường với name hoặc từng alias, ví dụ gõ "reactjs" ra React.
create or replace view api.v_skills
with (security_invoker = true) as
select r.id, r.slug, r.name, r.kind, c.name as category,
       coalesce(array_agg(a.alias_norm order by a.alias_norm) filter (where a.alias_norm is not null),
                '{}'::text[]) as aliases
from ref.skills r
join ref.skill_categories c on c.id = r.category_id
left join ref.skill_aliases a on a.skill_id = r.id
where r.is_active
group by r.id, r.slug, r.name, r.kind, c.name;

grant select on api.v_skills to authenticated;

-- 3. Hồ sơ trên danh sách CV của tôi (cột mới thêm ở cuối) ---------------------------------
create or replace view api.v_my_cvs
with (security_invoker = true) as
select c.id, c.storage_path, c.mime, c.size_bytes, c.parse_status, c.is_primary,
       c.consent_version, c.consent_at, c.created_at,
       c.years_exp, c.target_title, c.parse_error, c.original_name, c.profile_confirmed_at
from app.cvs c
where c.owner_user_id = auth.uid();

grant select on api.v_my_cvs to authenticated;

-- 4. Lưu hồ sơ đã xác nhận -------------------------------------------------------------------
-- p_skills: danh sách CUỐI CÙNG người dùng giữ lại, [{"skill_id": 12}, {"skill_id": 40}, ...]
--   (skill_id là ref.skills.id lấy từ api.v_my_cv_skills / api.v_skills).
--   - có dòng sẵn       → confirmed = true (giữ evidence_level, câu trích, số năm)
--   - chưa có dòng      → thêm evidence_level = 'user_added', confirmed = true
--   - dòng không còn trong danh sách → xóa
-- p_years_exp / p_target_title: null = giữ nguyên; chức danh chuỗi rỗng = xóa chức danh.
-- api.save_cv_profile (0009) giữ các dòng confirmed / user_added, nên đọc lại CV không làm mất
-- phần đã xác nhận; kỹ năng người dùng đã bỏ có thể được máy gợi ý lại (confirmed = false).
-- Trả số kỹ năng của CV sau khi lưu.
create or replace function api.confirm_cv_profile(
  p_cv_id        uuid,
  p_years_exp    numeric,
  p_target_title text,
  p_skills       jsonb
) returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  v_status text;
  v_ids    integer[];
  v_bad    text;
  v_rows   integer;
begin
  if auth.uid() is null then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;

  select c.parse_status into v_status
    from app.cvs c
   where c.id = p_cv_id and c.owner_user_id = auth.uid()
     for update;
  if not found then
    raise exception 'Không tìm thấy CV' using errcode = 'P0002';
  end if;
  if v_status <> 'parsed' then
    raise exception 'CV chưa đọc xong, hãy đợi rồi thử lại' using errcode = '55000';
  end if;

  if p_years_exp is not null and (p_years_exp < 0 or p_years_exp > 60) then
    raise exception 'Số năm kinh nghiệm phải từ 0 đến 60' using errcode = '22023';
  end if;
  if p_skills is null or jsonb_typeof(p_skills) <> 'array' then
    raise exception 'Danh sách kỹ năng không hợp lệ' using errcode = '22023';
  end if;
  if jsonb_array_length(p_skills) > 100 then
    raise exception 'Tối đa 100 kỹ năng' using errcode = '22023';
  end if;

  select x::text into v_bad
    from jsonb_array_elements(p_skills) x
   where jsonb_typeof(x) <> 'object'
      or coalesce(jsonb_typeof(x -> 'skill_id'), '') <> 'number'
      or coalesce(x ->> 'skill_id', '') !~ '^[0-9]{1,9}$'
   limit 1;
  if found then
    raise exception 'Mã kỹ năng không hợp lệ: %', v_bad using errcode = '22023';
  end if;

  select coalesce(array_agg(distinct (x ->> 'skill_id')::integer), '{}')
    into v_ids
    from jsonb_array_elements(p_skills) x;

  -- Kỹ năng mới phải có trong từ điển đang dùng; dòng đã có sẵn thì giữ được
  -- kể cả khi kỹ năng vừa bị ngưng dùng trong từ điển.
  select i::text into v_bad
    from unnest(v_ids) i
   where not exists (select 1 from ref.skills r where r.id = i and r.is_active)
     and not exists (select 1 from app.cv_skills s where s.cv_id = p_cv_id and s.skill_id = i)
   limit 1;
  if found then
    raise exception 'Kỹ năng % không có trong từ điển', v_bad using errcode = '22023';
  end if;

  delete from app.cv_skills s
   where s.cv_id = p_cv_id and s.skill_id <> all (v_ids);

  update app.cv_skills s
     set confirmed = true
   where s.cv_id = p_cv_id and not s.confirmed;

  insert into app.cv_skills (cv_id, skill_id, evidence_level, confirmed)
  select p_cv_id, i, 'user_added', true
    from unnest(v_ids) i
  on conflict (cv_id, skill_id) do nothing;

  update app.cvs c
     set years_exp            = coalesce(round(p_years_exp, 1), c.years_exp),
         target_title         = case
                                  when p_target_title is null then c.target_title
                                  else nullif(left(btrim(p_target_title), 200), '')
                                end,
         profile_confirmed_at = now()
   where c.id = p_cv_id;

  select count(*) into v_rows from app.cv_skills s where s.cv_id = p_cv_id;
  return v_rows;
end $$;

revoke execute on function api.confirm_cv_profile(uuid, numeric, text, jsonb) from public, anon;
grant execute on function api.confirm_cv_profile(uuid, numeric, text, jsonb) to authenticated;

-- 4b. Đọc lại CV không ghi đè số năm / chức danh người dùng đã xác nhận ---------------------
-- Giống 0009, chỉ khác: CV đã có profile_confirmed_at thì giữ years_exp, target_title.
-- Kỹ năng vẫn xử lý như cũ (giữ dòng confirmed / user_added).
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
         years_exp       = case when c.profile_confirmed_at is null
                                then round(p_years_exp, 1) else c.years_exp end,
         target_title    = case when c.profile_confirmed_at is null
                                then left(p_target_title, 200) else c.target_title end,
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

-- 5. Tối đa 5 CV cho mỗi người tìm việc --------------------------------------------------------
-- Trigger thay vì kiểm trong api.register_cv: chặn cả đường ghi thẳng vào app.cvs.
-- Khóa advisory theo user để hai lần tải song song không cùng lọt qua khi đang có 4 CV.
-- security definer: đếm đủ CV của chủ sở hữu, không phụ thuộc RLS của người đang ghi.
create or replace function app.cvs_limit_guard() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.owner_user_id is not null then
    perform pg_advisory_xact_lock(hashtextextended('app.cvs:' || new.owner_user_id::text, 0));
    if (select count(*) from app.cvs c where c.owner_user_id = new.owner_user_id) >= 5 then
      raise exception 'Bạn đã có 5 CV. Hãy xóa bớt một CV rồi tải lại' using errcode = '53400';
    end if;
  end if;
  return new;
end $$;

revoke execute on function app.cvs_limit_guard() from public, anon, authenticated;

drop trigger if exists cvs_limit_guard on app.cvs;
create trigger cvs_limit_guard
  before insert on app.cvs
  for each row execute function app.cvs_limit_guard();

-- 6. api.register_cv nhận thêm tên tệp gốc ----------------------------------------------------
-- Bỏ bản 6 tham số: để cả hai bản cùng tồn tại thì lời gọi 6 tham số bị mơ hồ.
-- p_original_name có default null nên web đang gọi 6 tham số vẫn chạy.
drop function if exists api.register_cv(uuid, text, text, text, integer, text);

create or replace function api.register_cv(
  p_id              uuid,
  p_storage_path    text,
  p_file_sha256     text,     -- hex 64 ký tự
  p_mime            text,
  p_size_bytes      integer,
  p_consent_version text,
  p_original_name   text default null
) returns uuid
language plpgsql security invoker set search_path = '' as $$
declare
  v_uid  uuid := auth.uid();
  v_name text;
begin
  if v_uid is null then
    raise exception 'Cần đăng nhập để tải CV' using errcode = '42501';
  end if;
  if p_consent_version is null or p_consent_version = '' then
    raise exception 'Cần đồng ý Điều khoản xử lý CV trước khi tải lên' using errcode = '23514';
  end if;
  if p_storage_path is null
     or p_storage_path !~ ('^u/' || v_uid::text || '/' || p_id::text || '\.(pdf|docx)$') then
    raise exception 'Đường dẫn file CV không hợp lệ' using errcode = '22023';
  end if;
  if p_file_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'Mã băm file không hợp lệ' using errcode = '22023';
  end if;

  -- Chỉ giữ phần tên sau dấu / hoặc \ cuối cùng, bỏ ký tự điều khiển, cắt 255 ký tự
  v_name := regexp_replace(coalesce(p_original_name, ''), '^.*[/\\]', '');
  v_name := btrim(regexp_replace(v_name, '[[:cntrl:]]', '', 'g'));
  v_name := nullif(left(v_name, 255), '');

  insert into app.cvs (id, owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes,
                       consent_version, original_name)
  values (p_id, v_uid, v_uid, p_storage_path, decode(p_file_sha256, 'hex'), p_mime, p_size_bytes,
          p_consent_version, v_name);
  return p_id;
end $$;

revoke execute on function api.register_cv(uuid, text, text, text, integer, text, text) from public, anon;
grant execute on function api.register_cv(uuid, text, text, text, integer, text, text) to authenticated;

-- PostgREST (Supabase) đọc lại schema để thấy view / hàm mới ngay
notify pgrst, 'reload schema';
