-- =====================================================================================
--  Migration 0012 — Quyền cho API so khớp (S4-D01, S4-D02; trước S4-D04)
--  1. Role Postgres chỉ đọc `matcher_ro`: API so khớp nạp kho tin (BM25, ma trận vector) bằng
--     kết nối Postgres riêng. Chỉ thấy tin CRAWL (công khai); không thấy JD nội bộ của HR, JD
--     người dùng dán, CV hay bất kỳ bảng app.* nào. Mọi giao dịch mặc định read-only.
--  2. app.cv_chunks: thêm policy RLS (bảng đã bật RLS nhưng chưa có policy nên không ghi được)
--     + hai RPC cho API (bằng JWT người dùng, như api.save_cv_profile):
--       api.save_cv_chunks  — lưu vector các đoạn CV
--       api.get_cv_chunks   — đọc lại, để khởi động lại API không phải gọi model lần nữa
--
--  KHÔNG có mật khẩu trong file này. Sau khi chạy migration, đặt mật khẩu một lần trong SQL Editor:
--      alter role matcher_ro with password '<mật khẩu mạnh>';
--  rồi đưa chuỗi kết nối (qua pooler Supavisor, user `matcher_ro.<project-ref>`) vào biến môi
--  trường của API, không commit.
--
--  Mã lỗi api.save_cv_chunks / api.get_cv_chunks:
--    42501  chưa đăng nhập
--    P0002  không thấy CV (hoặc CV người khác, RLS ẩn)
--    22023  dữ liệu sai: không phải mảng, quá 50 đoạn, thiếu section/chunk_no, vector không đủ
--           1024 chiều, thiếu model
--  Chạy lại nhiều lần được. Cần 0011.
-- =====================================================================================

-- 1. Role chỉ đọc cho API so khớp ---------------------------------------------------------
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'matcher_ro') then
    create role matcher_ro with login noinherit nocreatedb nocreaterole connection limit 10;
  end if;
end $$;

-- Đặt mặc định khi đăng nhập: giao dịch chỉ đọc, câu lệnh quá 30 giây thì hủy
alter role matcher_ro set default_transaction_read_only = on;
alter role matcher_ro set statement_timeout = '30s';

comment on role matcher_ro is
  'API so khớp (S4): chỉ đọc tin crawl và từ điển. Mật khẩu đặt tay, không nằm trong git.';

grant usage on schema core, ref, extensions to matcher_ro;
grant select on core.jobs, core.job_skills, core.job_chunks, core.job_locations, core.companies
  to matcher_ro;
grant select on ref.skills, ref.skill_aliases, ref.skill_categories, ref.provinces, ref.job_families
  to matcher_ro;

-- RLS: chỉ tin crawl. JD của HR (origin hr) và JD người dùng dán (user_paste) là dữ liệu riêng.
drop policy if exists matcher_read on core.jobs;
create policy matcher_read on core.jobs for select to matcher_ro
  using (origin = 'crawled');

drop policy if exists matcher_read on core.job_skills;
create policy matcher_read on core.job_skills for select to matcher_ro
  using (exists (select 1 from core.jobs j where j.id = job_id and j.origin = 'crawled'));

drop policy if exists matcher_read on core.job_chunks;
create policy matcher_read on core.job_chunks for select to matcher_ro
  using (exists (select 1 from core.jobs j where j.id = job_id and j.origin = 'crawled'));

drop policy if exists matcher_read on core.job_locations;
create policy matcher_read on core.job_locations for select to matcher_ro
  using (exists (select 1 from core.jobs j where j.id = job_id and j.origin = 'crawled'));

drop policy if exists matcher_read on core.companies;
create policy matcher_read on core.companies for select to matcher_ro using (true);

drop policy if exists matcher_read on ref.skills;
create policy matcher_read on ref.skills for select to matcher_ro using (true);
drop policy if exists matcher_read on ref.skill_aliases;
create policy matcher_read on ref.skill_aliases for select to matcher_ro using (true);
drop policy if exists matcher_read on ref.skill_categories;
create policy matcher_read on ref.skill_categories for select to matcher_ro using (true);
drop policy if exists matcher_read on ref.provinces;
create policy matcher_read on ref.provinces for select to matcher_ro using (true);
drop policy if exists matcher_read on ref.job_families;
create policy matcher_read on ref.job_families for select to matcher_ro using (true);

-- 2. app.cv_chunks: chủ CV (và HR của công ty với CV ứng viên) đọc / ghi, giống cv_child của cv_skills
drop policy if exists cv_child on app.cv_chunks;
create policy cv_child on app.cv_chunks for all to authenticated
  using ((select app.can_read_cv(cv_id)))
  with check ((select app.can_read_cv(cv_id)));

grant select, insert, update, delete on app.cv_chunks to authenticated;

-- Lưu vector đoạn CV. Thay TOÀN BỘ đoạn cũ của CV (mọi model): bảng chỉ unique theo
-- (cv_id, section, chunk_no), và đoạn cũ không còn đúng khi CV đọc lại / hồ sơ đổi.
-- p_chunks: [{"section": "summary", "chunk_no": 0, "content": "...", "embedding": [1024 số]}, ...]
-- API biết đoạn đã lưu còn dùng được không bằng cách so `content` với đoạn vừa cắt từ CV hiện tại
-- (api.get_cv_chunks trả cả content): khác thì vector hóa lại rồi gọi hàm này.
-- Trả số đoạn đã lưu.
create or replace function api.save_cv_chunks(
  p_cv_id  uuid,
  p_model  text,
  p_chunks jsonb
) returns integer
language plpgsql security invoker set search_path = '' as $$
declare
  v_bad  text;
  v_rows integer;
begin
  if auth.uid() is null then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  perform 1 from app.cvs c where c.id = p_cv_id for update;
  if not found then
    raise exception 'Không tìm thấy CV' using errcode = 'P0002';
  end if;
  if coalesce(btrim(p_model), '') = '' then
    raise exception 'Thiếu tên model' using errcode = '22023';
  end if;
  if p_chunks is null or jsonb_typeof(p_chunks) <> 'array' then
    raise exception 'Danh sách đoạn không hợp lệ' using errcode = '22023';
  end if;
  if jsonb_array_length(p_chunks) > 50 then
    raise exception 'Tối đa 50 đoạn mỗi CV' using errcode = '22023';
  end if;

  select coalesce(x ->> 'section', '?') || '#' || coalesce(x ->> 'chunk_no', '?') into v_bad
    from jsonb_array_elements(p_chunks) x
   where jsonb_typeof(x) <> 'object'
      or coalesce(btrim(x ->> 'section'), '') = ''
      or coalesce(jsonb_typeof(x -> 'chunk_no'), '') <> 'number'
      or coalesce(jsonb_typeof(x -> 'embedding'), '') <> 'array'
      or jsonb_array_length(x -> 'embedding') <> 1024
   limit 1;
  if found then
    raise exception 'Đoạn % không hợp lệ (cần section, chunk_no, embedding 1024 chiều)', v_bad
      using errcode = '22023';
  end if;

  delete from app.cv_chunks ch where ch.cv_id = p_cv_id;

  insert into app.cv_chunks (cv_id, section, chunk_no, content, embedding, model)
  select p_cv_id, left(x ->> 'section', 50), (x ->> 'chunk_no')::smallint,
         left(x ->> 'content', 4000), (x -> 'embedding')::text::extensions.halfvec(1024),
         btrim(p_model)
    from jsonb_array_elements(p_chunks) x;
  get diagnostics v_rows = row_count;
  return v_rows;
end $$;

-- Đọc lại vector đoạn CV của một model. embedding trả dạng text "[0.1,0.2,...]" (json.loads được).
create or replace function api.get_cv_chunks(p_cv_id uuid, p_model text)
returns table (section text, chunk_no smallint, content text, embedding text)
language plpgsql stable security invoker set search_path = '' as $$
begin
  if auth.uid() is null then
    raise exception 'Cần đăng nhập' using errcode = '42501';
  end if;
  if not exists (select 1 from app.cvs c where c.id = p_cv_id) then
    raise exception 'Không tìm thấy CV' using errcode = 'P0002';
  end if;
  return query
    select ch.section, ch.chunk_no, ch.content, ch.embedding::text
      from app.cv_chunks ch
     where ch.cv_id = p_cv_id and ch.model = p_model
     order by ch.section, ch.chunk_no;
end $$;

revoke execute on function api.save_cv_chunks(uuid, text, jsonb) from public, anon;
revoke execute on function api.get_cv_chunks(uuid, text) from public, anon;
grant execute on function api.save_cv_chunks(uuid, text, jsonb) to authenticated;
grant execute on function api.get_cv_chunks(uuid, text) to authenticated;

notify pgrst, 'reload schema';
