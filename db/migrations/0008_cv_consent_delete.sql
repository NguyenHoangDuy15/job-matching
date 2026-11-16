-- =====================================================================================
--  Migration 0008 — Consent khi tải CV và xóa CV sạch (S3-T02, US-11)
--  1. ref.cv_terms: các phiên bản Điều khoản xử lý CV; chỉ 1 phiên bản đang hiệu lực.
--  2. app.cvs.consent_version / consent_at: mỗi CV của người tìm việc phải kèm consent.
--     consent_at do DB ghi (client không tự đặt được) và không sửa được sau khi tạo.
--  3. Xóa CV: dòng app.cvs xóa thì các bảng con tự xóa theo FK (cv_skills, cv_chunks,
--     match_requests/results, candidate_reviews, eval.labels); trigger dọn thêm cache
--     app.explanations (không có FK) và ghi audit_log không kèm đường dẫn file.
--  4. API cho web (chỉ schema api được expose): api.v_cv_terms_current, api.v_my_cvs,
--     api.register_cv, api.delete_cv. api.delete_cv từ chối khi file còn trong Storage,
--     nên web buộc phải xóa file qua Storage API trước → không còn file mồ côi.
--  Cần 0001. Chạy lại nhiều lần được.
-- =====================================================================================

-- 1. Phiên bản điều khoản ------------------------------------------------------------
create table if not exists ref.cv_terms (
  version      text primary key,
  published_at date not null,
  retired_at   timestamptz,                 -- null = đang hiệu lực
  url          text not null,
  summary      text
);
create unique index if not exists cv_terms_one_current_idx on ref.cv_terms ((true)) where retired_at is null;

alter table ref.cv_terms enable row level security;
drop policy if exists ref_read on ref.cv_terms;
create policy ref_read on ref.cv_terms for select to anon, authenticated using (true);
grant select on ref.cv_terms to anon, authenticated;

insert into ref.cv_terms (version, published_at, url, summary) values
  ('cv-2026-11', date '2026-11-16', '/dieu-khoan#cv',
   'Cho phép lưu CV, trích kỹ năng và so khớp với tin tuyển dụng; xóa CV bất kỳ lúc nào.')
on conflict (version) do nothing;

-- 2. Consent trên từng CV ---------------------------------------------------------------
alter table app.cvs
  add column if not exists consent_version text references ref.cv_terms (version),
  add column if not exists consent_at      timestamptz;

-- NOT VALID: chỉ áp cho dòng mới, không chặn migration nếu đã có CV cũ chưa kèm consent.
-- CV ứng viên do HR tải (owner_user_id null) không thuộc phạm vi này.
do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'cvs_seeker_consent' and conrelid = 'app.cvs'::regclass
  ) then
    alter table app.cvs add constraint cvs_seeker_consent
      check (owner_user_id is null or (consent_version is not null and consent_at is not null)) not valid;
  end if;
end $$;

create or replace function app.cvs_consent_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.consent_version is not null then
      if not exists (
        select 1 from ref.cv_terms t
        where t.version = new.consent_version and t.retired_at is null
      ) then
        raise exception 'Điều khoản phiên bản % không còn hiệu lực, tải lại trang rồi đồng ý lại', new.consent_version
          using errcode = '23514';
      end if;
      new.consent_at := now();              -- thời điểm do DB ghi
    else
      new.consent_at := null;
    end if;
  else
    -- Consent là bằng chứng pháp lý: không ai sửa được sau khi tạo
    new.consent_version := old.consent_version;
    new.consent_at      := old.consent_at;
  end if;
  return new;
end $$;

drop trigger if exists cvs_consent_guard on app.cvs;
create trigger cvs_consent_guard
  before insert or update on app.cvs
  for each row execute function app.cvs_consent_guard();

-- 3. Dọn dữ liệu khi xóa CV ---------------------------------------------------------------
comment on column app.explanations.cv_hash is
  'Bằng app.cvs.file_sha256 của CV được giải thích. Trigger cvs_after_delete dựa vào quy ước này để xóa cache.';

create or replace function app.cvs_after_delete() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  -- Cache giải thích LLM không có FK tới app.cvs. Giữ lại nếu còn CV khác trùng file.
  delete from app.explanations e
   where e.cv_hash = old.file_sha256
     and not exists (select 1 from app.cvs c where c.file_sha256 = old.file_sha256);

  -- Chỉ ghi id CV, không ghi đường dẫn file hay nội dung CV
  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id)
  values (auth.uid(),
          case when auth.uid() is null then null else app.jwt_role() end,
          'cv_deleted', 'cv', old.id::text);
  return old;
end $$;

drop trigger if exists cvs_after_delete on app.cvs;
create trigger cvs_after_delete
  after delete on app.cvs
  for each row execute function app.cvs_after_delete();

-- 4. API cho web ------------------------------------------------------------------------
create or replace view api.v_cv_terms_current
with (security_invoker = true) as
select version, published_at, url, summary
from ref.cv_terms
where retired_at is null;

-- CV của chính mình (RLS cvs_owner vẫn áp dụng); dùng cho trang "Hồ sơ của tôi" và luồng xóa
create or replace view api.v_my_cvs
with (security_invoker = true) as
select c.id, c.storage_path, c.mime, c.size_bytes, c.parse_status, c.is_primary,
       c.consent_version, c.consent_at, c.created_at
from app.cvs c
where c.owner_user_id = auth.uid();

grant select on api.v_cv_terms_current to anon, authenticated;
grant select on api.v_my_cvs to authenticated;

-- Ghi CV sau khi web đã upload file lên Storage tại u/{uid}/{id}.{pdf|docx}.
-- security invoker: RLS cvs_owner quyết định quyền ghi.
create or replace function api.register_cv(
  p_id              uuid,
  p_storage_path    text,
  p_file_sha256     text,     -- hex 64 ký tự
  p_mime            text,
  p_size_bytes      integer,
  p_consent_version text
) returns uuid
language plpgsql security invoker set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
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

  insert into app.cvs (id, owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes, consent_version)
  values (p_id, v_uid, v_uid, p_storage_path, decode(p_file_sha256, 'hex'), p_mime, p_size_bytes, p_consent_version);
  return p_id;
end $$;

-- Xóa CV: gọi SAU khi đã xóa file qua Storage API. Còn file → từ chối, để không mất dấu file.
-- Trả false khi không có CV đó hoặc không có quyền (RLS lọc mất dòng).
create or replace function api.delete_cv(p_cv_id uuid) returns boolean
language plpgsql security invoker set search_path = '' as $$
declare
  v_path text;
  v_rows integer;
begin
  select c.storage_path into v_path from app.cvs c where c.id = p_cv_id;
  if v_path is null then
    return false;
  end if;
  if exists (select 1 from storage.objects o where o.bucket_id = 'cvs' and o.name = v_path) then
    raise exception 'File CV vẫn còn trong Storage, xóa file trước' using errcode = '55000';
  end if;

  delete from app.cvs c where c.id = p_cv_id;
  get diagnostics v_rows = row_count;
  return v_rows > 0;
end $$;

revoke execute on function api.register_cv(uuid, text, text, text, integer, text) from public, anon;
revoke execute on function api.delete_cv(uuid) from public, anon;
grant execute on function api.register_cv(uuid, text, text, text, integer, text) to authenticated;
grant execute on function api.delete_cv(uuid) to authenticated;
