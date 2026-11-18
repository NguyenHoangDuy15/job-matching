-- =====================================================================================
--  Migration 0015 — CV chính, hạn lưu CV, chuyển hướng link tin đã gộp (S3-H04, S3-H05)
--    1. Người tìm việc có CV thì luôn có đúng 1 CV chính:
--       - api.register_cv: chưa có CV chính → CV vừa tải thành CV chính
--       - api.set_primary_cv(p_cv_id): nút "Đặt làm CV chính"
--       - xóa CV chính (api.delete_cv hay bất kỳ đường xóa nào) → CV mới nhất còn lại thành
--         CV chính (trigger, nên cả đường xóa không qua api.delete_cv cũng giữ được)
--       - dữ liệu cũ: ai có CV mà chưa có CV chính → CV mới nhất thành CV chính
--    2. Hạn lưu: api.register_cv ghi delete_after = current_date + 30; api.v_my_cvs thêm cột
--       delete_after (ở CUỐI view) cho cột "Tự xóa sau".
--       CHƯA tự xóa CV người tìm việc: chưa có bước xóa file trong Storage, xóa dòng thì file
--       mồ côi. app.purge_expired_cvs chỉ xóa CV ứng viên do HR tải, như trước.
--    3. api.job_redirect(p_public_id): public_id của tin được giữ lại nếu tin này đã bị gộp
--       (core.merge_jobs, S3-T03/T04/T05), để link cũ chuyển hướng thay vì báo 404.
--
--  Mã lỗi api.set_primary_cv (web dịch sang tiếng Việt theo errcode):
--    42501  chưa đăng nhập
--    P0002  không thấy CV (hoặc CV của người khác, RLS ẩn)
--
--  Chạy lại nhiều lần được. Cần 0010 (api.register_cv 7 tham số), 0011 (core.jobs.duplicate_of).
-- =====================================================================================

-- Cùng khóa advisory với app.cvs_limit_guard (0010): mọi thay đổi CV của một người chạy lần lượt,
-- để hai thao tác song song không cùng đặt CV chính (vướng cvs_one_primary_idx) hay cùng bỏ trống.
create or replace function app.lock_user_cvs(p_user_id uuid) returns void
language sql set search_path = '' as $$
  select pg_advisory_xact_lock(hashtextextended('app.cvs:' || p_user_id::text, 0))
$$;

revoke execute on function app.lock_user_cvs(uuid) from public, anon;
grant execute on function app.lock_user_cvs(uuid) to authenticated;

-- 1a. Dữ liệu cũ: CV mới nhất của người chưa có CV chính thành CV chính -----------------------
update app.cvs c
   set is_primary = true
 where c.id in (
         select distinct on (x.owner_user_id) x.id
         from app.cvs x
         where x.owner_user_id is not null
         order by x.owner_user_id, x.created_at desc, x.id desc)
   and not exists (
         select 1 from app.cvs p where p.owner_user_id = c.owner_user_id and p.is_primary);

-- 1b. Xóa CV chính → CV mới nhất còn lại thành CV chính ---------------------------------------
-- security definer: chạy được cả khi xóa bằng app.purge_expired_cvs hay service_role.
create or replace function app.cvs_primary_after_delete() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if old.is_primary and old.owner_user_id is not null then
    perform app.lock_user_cvs(old.owner_user_id);
    update app.cvs c
       set is_primary = true
     where c.id = (select n.id from app.cvs n
                   where n.owner_user_id = old.owner_user_id
                   order by n.created_at desc, n.id desc
                   limit 1)
       and not exists (select 1 from app.cvs p
                       where p.owner_user_id = old.owner_user_id and p.is_primary);
  end if;
  return old;
end $$;

revoke execute on function app.cvs_primary_after_delete() from public, anon, authenticated;

drop trigger if exists cvs_primary_after_delete on app.cvs;
create trigger cvs_primary_after_delete
  after delete on app.cvs
  for each row execute function app.cvs_primary_after_delete();

-- 1c. Nút "Đặt làm CV chính" ------------------------------------------------------------------
-- security invoker: RLS cvs_owner chỉ cho thấy và sửa CV của chính mình.
create or replace function api.set_primary_cv(p_cv_id uuid) returns void
language plpgsql security invoker set search_path = '' as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception 'Cần đăng nhập để chọn CV chính' using errcode = '42501';
  end if;
  perform app.lock_user_cvs(v_uid);
  if not exists (select 1 from app.cvs c where c.id = p_cv_id and c.owner_user_id = v_uid) then
    raise exception 'Không tìm thấy CV' using errcode = 'P0002';
  end if;

  -- Bỏ CV chính cũ trước, rồi mới đặt CV mới (cvs_one_primary_idx kiểm từng dòng)
  update app.cvs c set is_primary = false
   where c.owner_user_id = v_uid and c.is_primary and c.id <> p_cv_id;
  update app.cvs c set is_primary = true
   where c.id = p_cv_id and not c.is_primary;
end $$;

revoke execute on function api.set_primary_cv(uuid) from public, anon;
grant execute on function api.set_primary_cv(uuid) to authenticated;

-- 1d + 2. api.register_cv: CV đầu tiên thành CV chính, ghi hạn lưu 30 ngày ---------------------
-- Giữ nguyên chữ ký 7 tham số của 0010 (create or replace giữ quyền đã cấp).
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
  v_uid     uuid := auth.uid();
  v_name    text;
  v_primary boolean;
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

  perform app.lock_user_cvs(v_uid);
  v_primary := not exists (select 1 from app.cvs c where c.owner_user_id = v_uid and c.is_primary);

  insert into app.cvs (id, owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes,
                       consent_version, original_name, is_primary, delete_after)
  values (p_id, v_uid, v_uid, p_storage_path, decode(p_file_sha256, 'hex'), p_mime, p_size_bytes,
          p_consent_version, v_name, v_primary, current_date + 30);
  return p_id;
end $$;

revoke execute on function api.register_cv(uuid, text, text, text, integer, text, text) from public, anon;
grant execute on function api.register_cv(uuid, text, text, text, integer, text, text) to authenticated;

-- 2b. Cột "Tự xóa sau" trên danh sách CV của tôi (thêm ở cuối, cột cũ giữ nguyên) ------------
create or replace view api.v_my_cvs
with (security_invoker = true) as
select c.id, c.storage_path, c.mime, c.size_bytes, c.parse_status, c.is_primary,
       c.consent_version, c.consent_at, c.created_at,
       c.years_exp, c.target_title, c.parse_error, c.original_name, c.profile_confirmed_at,
       c.delete_after
from app.cvs c
where c.owner_user_id = auth.uid();

grant select on api.v_my_cvs to authenticated;

-- 2c. Chưa xóa CV người tìm việc khi quá hạn (chưa có bước xóa file trong Storage) -------------
create or replace function app.purge_expired_cvs() returns integer
language plpgsql security definer set search_path = '' as $$
declare n integer;
begin
  with gone as (
    delete from app.cvs
     where keep = false and delete_after < current_date
       and owner_user_id is null            -- chỉ CV ứng viên do HR tải
    returning storage_path
  )
  insert into app.audit_log (action, entity, entity_id)
  select 'cv_purged', 'storage', storage_path from gone;
  get diagnostics n = row_count;
  return n;
end $$;

-- 3. Link cũ của tin đã gộp → tin được giữ lại -------------------------------------------------
-- core.merge_jobs luôn trỏ duplicate_of thẳng về tin giữ lại (không có chuỗi), nên một bước là đủ.
-- Trả null khi tin không bị gộp hoặc không tồn tại: web hiện trang "Tin không còn tuyển" như cũ.
-- security definer: tin bị gộp đã đóng; chỉ trả public_id của tin crawl (vốn công khai).
create or replace function api.job_redirect(p_public_id uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select k.public_id
  from core.jobs d
  join core.jobs k on k.id = d.duplicate_of
  where d.public_id = p_public_id
    and d.origin = 'crawled'
    and k.origin = 'crawled'
$$;

revoke execute on function api.job_redirect(uuid) from public;
grant execute on function api.job_redirect(uuid) to anon, authenticated;

-- PostgREST (Supabase) đọc lại schema để thấy hàm / cột mới ngay
notify pgrst, 'reload schema';
