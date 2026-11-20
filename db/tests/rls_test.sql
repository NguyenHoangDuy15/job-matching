\set ON_ERROR_STOP 1

-- =====================================================================
--  Bộ Kiểm thử Tự động (Automated Verification Suite) cho:
--  1. Authentication (Đăng ký, Đăng nhập, Đăng xuất, Thu hồi phiên)
--  2. Authorization & RBAC 3 Vai trò (seeker, hr, admin) + RLS 2 lớp
--  3. Chống tự nâng quyền (Privilege Escalation) & Khóa tài khoản tức thì
--  4. Tìm kiếm Tiếng Việt không dấu, Khử trùng & Bảng tổng hợp Gold
--
--  CHỈ chạy trên DB dùng một lần (CI, máy cá nhân): file này tạo user và dữ liệu giả.
--  KHÔNG chạy trên Supabase cloud.
-- =====================================================================

-- 1. Seed danh mục tham chiếu & nguồn thu thập (idempotent: chạy độc lập hoặc sau seed_reference_data.sql đều an toàn)
insert into ref.provinces (code, name, name_unaccent, kind, region) values
  (1, 'Hà Nội', 'ha noi', 'thanh_pho', 'Bắc'),
  (79, 'TP. Hồ Chí Minh', 'tp ho chi minh', 'thanh_pho', 'Nam')
on conflict (code) do nothing;

insert into ref.province_legacy (alias_norm, province_code) values
  ('binh duong', 79), ('sai gon', 79), ('hn', 1)
on conflict (alias_norm) do nothing;

insert into ref.skill_categories (id, name) values
  (1, 'Language'), (2, 'Data & Cloud')
on conflict (id) do nothing;

insert into ref.skills (slug, name, category_id) values
  ('python', 'Python', 1),
  ('sql', 'SQL', 1),
  ('airflow', 'Airflow', 2)
on conflict (slug) do nothing;

insert into ref.job_families (id, name) values
  (0, 'Tất cả'), (1, 'Data/AI')
on conflict (id) do nothing;

insert into ops.sources (id, code, name, base_url, method, is_enabled) values
  (1, 'vnw', 'VietnamWorks', 'https://www.vietnamworks.com', 'jsonld', true)
on conflict (id) do nothing;

-- 2. Seed người dùng qua auth.users (Trigger on_auth_user_created tự sinh app.profiles & audit_log)
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-00000000000a', 'seeker@x.vn', '{"full_name":"Nguyễn Ứng Viên"}'::jsonb),
  ('00000000-0000-0000-0000-00000000000b', 'hra@x.vn',    '{"full_name":"Trần HR A"}'::jsonb),
  ('00000000-0000-0000-0000-00000000000c', 'hrb@x.vn',    '{"full_name":"Lê HR B"}'::jsonb),
  ('00000000-0000-0000-0000-00000000000d', 'admin@x.vn',  '{"full_name":"Phạm Admin"}'::jsonb),
  ('00000000-0000-0000-0000-00000000000e', 'hr_applicant@companyc.vn', '{"full_name":"Hoàng HR Mới","requested_role":"hr","company_name":"Công ty C","work_email":"hr_applicant@companyc.vn"}'::jsonb),
  ('00000000-0000-0000-0000-00000000000f', 'seeker2@x.vn', '{"full_name":"Đỗ Ứng Viên B"}'::jsonb);

insert into app.organizations (id, name) values
  ('10000000-0000-0000-0000-00000000000a', 'Công ty A'),
  ('10000000-0000-0000-0000-00000000000b', 'Công ty B');

update app.profiles set role = 'hr', org_id = '10000000-0000-0000-0000-00000000000a' where user_id = '00000000-0000-0000-0000-00000000000b';
update app.profiles set role = 'hr', org_id = '10000000-0000-0000-0000-00000000000b' where user_id = '00000000-0000-0000-0000-00000000000c';
update app.profiles set role = 'admin' where user_id = '00000000-0000-0000-0000-00000000000d';

-- 3. Seed dữ liệu công việc & hồ sơ CV
insert into core.companies (name, name_norm) values ('FPT Software', 'fpt software');
insert into core.jobs (title, title_norm, company_id, job_family_id, requirements, apply_url, valid_through, first_seen_at, salary_min_vnd, salary_max_vnd) values
  ('Lập trình viên Python (Data Engineer)', 'lap trinh vien python', 1, 1, 'Thành thạo Python, SQL, Airflow', 'https://www.vietnamworks.com/x-1-jd', current_date + 20, date_trunc('week', current_date) - interval '2 days', 25000000, 40000000),
  ('Java Backend Developer', 'java backend developer', 1, null, 'Java, Spring', 'https://www.vietnamworks.com/x-2-jd', current_date - 1, date_trunc('week', current_date) - interval '2 days', null, null);
insert into core.jobs (origin, org_id, title, title_norm) values
  ('hr', '10000000-0000-0000-0000-00000000000a', 'JD nội bộ A', 'jd noi bo a'),
  ('hr', '10000000-0000-0000-0000-00000000000b', 'JD nội bộ B', 'jd noi bo b');

insert into core.job_locations values (1, 1, null);
insert into core.job_skills (job_id, skill_id, level) values
  (1, (select id from ref.skills where slug = 'python'),  'required'),
  (1, (select id from ref.skills where slug = 'sql'),     'required'),
  (1, (select id from ref.skills where slug = 'airflow'), 'preferred'),
  (3, (select id from ref.skills where slug = 'python'),  'required'),
  (4, (select id from ref.skills where slug = 'sql'),     'required');

-- Phiên bản điều khoản đã hết hiệu lực (cv-2026-11 đang hiệu lực do migration 0008 tạo)
insert into ref.cv_terms (version, published_at, retired_at, url) values
  ('cv-2026-01', date '2026-01-01', now() - interval '1 day', '/dieu-khoan/cv-2026-01')
on conflict (version) do nothing;

insert into app.cvs (owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes, consent_version) values
  ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000a', 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf', '\x01', 'application/pdf', 1000, 'cv-2026-11'),
  ('00000000-0000-0000-0000-00000000000f', '00000000-0000-0000-0000-00000000000f', 'u/00000000-0000-0000-0000-00000000000f/cv-b.pdf', '\x03', 'application/pdf', 1000, 'cv-2026-11');
-- Kỹ năng trích từ CV của seeker A (để kiểm tra seeker B không đọc được app.cv_skills của A)
insert into app.cv_skills (cv_id, skill_id, evidence_level, evidence)
select c.id, (select id from ref.skills where slug = 'python'), 'strong', 'Dự án ETL bằng Python'
from app.cvs c where c.storage_path = 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf';
insert into app.cvs (org_id, job_id, uploaded_by, storage_path, file_sha256, mime, size_bytes, delete_after) values
  ('10000000-0000-0000-0000-00000000000a', 3, '00000000-0000-0000-0000-00000000000b', 'o/10000000-0000-0000-0000-00000000000a/3/c1.pdf', '\x02', 'application/pdf', 1000, current_date - 1);

insert into storage.objects (bucket_id, name) values
  ('cvs', 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf'),
  ('cvs', 'o/10000000-0000-0000-0000-00000000000a/3/c1.pdf'),
  ('cvs', 'u/00000000-0000-0000-0000-00000000000f/cv-b.pdf');

-- 4. Bảng lưu kết quả kiểm thử
create temp table results(test text, got text, expected text);
grant all on results to anon, authenticated;

-- Test nhóm 0: Bucket 'cvs' được migration tạo đúng cấu hình (S3-T01)
insert into results select 'bucket cvs: private, 5MB, pdf/docx only',
  (select (not public
           and file_size_limit = 5242880
           and allowed_mime_types @> array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document']
           and cardinality(allowed_mime_types) = 2)::text
   from storage.buckets where id = 'cvs'),
  'true';

-- Test nhóm 1: Đăng ký tự động, Trigger Login & Custom Access Token Hook
insert into results select 'trigger created 6 profiles on register', count(*)::text, '6' from app.profiles;
insert into results select 'hr applicant auto-created pending_hr request', count(*)::text, '1' from app.hr_requests where user_id = '00000000-0000-0000-0000-00000000000e' and status = 'pending';
insert into results select 'jwt hook injects hr role & org_id',
  (public.custom_access_token_hook('{"user_id":"00000000-0000-0000-0000-00000000000b","claims":{"sub":"00000000-0000-0000-0000-00000000000b"}}'::jsonb)->'claims'->>'user_role'),
  'hr';

-- Mô phỏng Supabase Auth cập nhật last_sign_in_at khi người dùng đăng nhập
update auth.users set last_sign_in_at = now() where id = '00000000-0000-0000-0000-00000000000a';
insert into results select 'on_auth_user_login trigger increments login_count',
  (select (login_count = 1 and last_login_at is not null)::text from app.profiles where user_id = '00000000-0000-0000-0000-00000000000a'),
  'true';

-- Test nhóm 2: Khách (anon)
set role anon; set request.jwt.claims = '{}';
insert into results select 'anon sees crawled jobs only', count(*)::text, '2' from core.jobs;
insert into results select 'v_open_jobs hides expired job', count(*)::text, '1' from api.v_open_jobs;
insert into results select 'search unaccent "lap trinh vien" + Hà Nội', count(*)::text, '1' from api.search_jobs(q=>'lap trinh vien', provinces=>array[1]::smallint[]);
insert into results select 'search hides expired java', count(*)::text, '0' from api.search_jobs(q=>'java');
insert into results select 'v_job_detail: open crawled only', count(*)::text, '1' from api.v_job_detail;
insert into results select 'v_job_detail: province name', coalesce((select provinces[1] from api.v_job_detail limit 1), 'null'), 'Hà Nội';
-- anon không được cấp SELECT trên app.cvs (schema chỉ grant cho authenticated) → bị từ chối ngay ở tầng quyền.
do $$
declare
  v_rows bigint;
begin
  select count(*) into v_rows from app.cvs;
  insert into results values ('anon cannot read cvs', v_rows::text || ' rows readable', 'denied');
exception when insufficient_privilege then
  insert into results values ('anon cannot read cvs', 'denied', 'denied');
end $$;
insert into results select 'anon sees skills of crawled jobs only', count(*)::text, '3' from core.job_skills;
reset role;

-- Test nhóm 3: Người tìm việc (seeker) — Login, xem hồ sơ, Logout, chống tự nâng quyền
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
insert into results select 'seeker sees own cv', count(*)::text, '1' from app.cvs;
insert into results select 'seeker sees 0 hr jobs', count(*)::text, '0' from core.jobs where origin='hr';
insert into results select 'seeker storage files', count(*)::text, '1' from storage.objects;
insert into results select 'seeker no ops', count(*)::text, '0' from ops.crawl_runs;
insert into results select 'seeker profiles visible', count(*)::text, '1' from app.profiles;

-- Kiểm tra Logout RPC & Audit log
select api.logout_user(true);
insert into results select 'seeker logout timestamp recorded via api.get_my_profile()',
  (select (last_logout_at is not null)::text from api.get_my_profile()),
  'true';

-- Kiểm tra chống tự nâng quyền (Privilege Escalation Block)
do $$
declare
  v_req_id bigint;
  v_rows   int;
begin
  begin
    update app.profiles set role = 'admin' where user_id = auth.uid();
    insert into results values ('seeker cannot self-promote column', 'UPDATED', 'denied');
  exception when insufficient_privilege then
    insert into results values ('seeker cannot self-promote column', 'denied', 'denied');
  end;
  begin
    perform api.admin_set_role(auth.uid(), 'admin');
    insert into results values ('seeker cannot call admin_set_role', 'ok', 'denied');
  exception when insufficient_privilege then
    insert into results values ('seeker cannot call admin_set_role', 'denied', 'denied');
  end;
  -- Seeker tạo yêu cầu HR và thử tự UPDATE status = 'approved' → RLS phải chặn (0 rows updated)
  v_req_id := api.request_hr_account('Công ty Tự Phong', 'https://tuphong.vn', 'seeker@tuphong.vn', 'HR');
  update app.hr_requests set status = 'approved' where id = v_req_id;
  get diagnostics v_rows = row_count;
  insert into results values ('seeker cannot self-approve own hr_request', v_rows::text, '0');
end $$;
reset role;

-- Test nhóm 3b (S3-T01, US-11): Seeker B không đọc / sửa / xóa / ghi đè được CV và file của seeker A
-- Giả định B đã biết cv_id của A (lộ qua URL/log) để thử ghi trực tiếp
select set_config('test.cv_a', id::text, false) from app.cvs where storage_path = 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf';
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
insert into results select 'seekerB sees only own cv', string_agg(storage_path, ','), 'u/00000000-0000-0000-0000-00000000000f/cv-b.pdf' from app.cvs;
insert into results select 'seekerB cannot read A cv_skills', count(*)::text, '0' from app.cv_skills;
insert into results select 'seekerB sees only own storage file', string_agg(name, ','), 'u/00000000-0000-0000-0000-00000000000f/cv-b.pdf' from storage.objects;
insert into results select 'seekerB cannot open A file by exact path', count(*)::text, '0'
  from storage.objects where bucket_id = 'cvs' and name = 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf';
do $$
declare
  v_rows int;
begin
  -- Sửa / xóa CV và file của A: RLS lọc hết dòng → 0 dòng bị ảnh hưởng
  update app.cvs set is_primary = true where owner_user_id = '00000000-0000-0000-0000-00000000000a';
  get diagnostics v_rows = row_count;
  insert into results values ('seekerB cannot update A cv row', v_rows::text, '0');

  delete from app.cvs where owner_user_id = '00000000-0000-0000-0000-00000000000a';
  get diagnostics v_rows = row_count;
  insert into results values ('seekerB cannot delete A cv row', v_rows::text, '0');

  delete from storage.objects where name = 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf';
  get diagnostics v_rows = row_count;
  insert into results values ('seekerB cannot delete A file', v_rows::text, '0');

  -- Tải file vào thư mục của A, hoặc ra ngoài thư mục u/{uid}/ → bị chặn bởi WITH CHECK
  begin
    insert into storage.objects (bucket_id, name) values ('cvs', 'u/00000000-0000-0000-0000-00000000000a/evil.pdf');
    insert into results values ('seekerB cannot upload into A folder', 'inserted', 'denied');
  exception when insufficient_privilege then
    insert into results values ('seekerB cannot upload into A folder', 'denied', 'denied');
  end;
  begin
    insert into storage.objects (bucket_id, name) values ('cvs', 'cv-root.pdf');
    insert into results values ('seekerB cannot upload outside u/{uid}/', 'inserted', 'denied');
  exception when insufficient_privilege then
    insert into results values ('seekerB cannot upload outside u/{uid}/', 'denied', 'denied');
  end;

  -- Tạo bản ghi CV đứng tên A → bị chặn
  begin
    insert into app.cvs (owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000f',
            'u/00000000-0000-0000-0000-00000000000a/fake.pdf', '\x04', 'application/pdf', 1000);
    insert into results values ('seekerB cannot insert cv owned by A', 'inserted', 'denied');
  exception when insufficient_privilege then
    insert into results values ('seekerB cannot insert cv owned by A', 'denied', 'denied');
  end;

  -- Biết (đoán) được cv_id của A rồi gắn thêm kỹ năng vào CV đó → bị chặn
  begin
    insert into app.cv_skills (cv_id, skill_id, evidence_level)
    values (current_setting('test.cv_a')::uuid, (select id from ref.skills where slug = 'sql'), 'user_added');
    insert into results values ('seekerB cannot add skill to A cv', 'inserted', 'denied');
  exception when insufficient_privilege then
    insert into results values ('seekerB cannot add skill to A cv', 'denied', 'denied');
  end;
end $$;
reset role;

-- Chạy với quyền superuser: dữ liệu của A vẫn nguyên vẹn sau các lần thử của B
insert into results select 'A cv + file + skills intact after B attempts',
  (select count(*) from app.cvs where owner_user_id = '00000000-0000-0000-0000-00000000000a' and not is_primary)::text || '/' ||
  (select count(*) from storage.objects where name like 'u/00000000-0000-0000-0000-00000000000a/%')::text || '/' ||
  (select count(*) from app.cv_skills s join app.cvs c on c.id = s.cv_id where c.owner_user_id = '00000000-0000-0000-0000-00000000000a')::text,
  '1/1/1';

-- Test nhóm 3c (S3-T02, US-11): Consent khi tải CV, xóa CV = xóa file + mọi dữ liệu liên quan
-- CV mới của seeker B: id b2…01, file u/{B}/b2…01.pdf, sha256 = 'ab' x 32
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
insert into storage.objects (bucket_id, name) values
  ('cvs', 'u/00000000-0000-0000-0000-00000000000f/b2000000-0000-0000-0000-000000000001.pdf');
select api.register_cv('b2000000-0000-0000-0000-000000000001',
                       'u/00000000-0000-0000-0000-00000000000f/b2000000-0000-0000-0000-000000000001.pdf',
                       repeat('ab', 32), 'application/pdf', 2000, 'cv-2026-11');
insert into results select 'register_cv stores consent version + DB time',
  (consent_version = 'cv-2026-11' and consent_at between now() - interval '1 minute' and now() + interval '1 minute')::text,
  'true'
  from api.v_my_cvs where id = 'b2000000-0000-0000-0000-000000000001';
insert into results select 'anyone can read current terms', string_agg(version, ','), 'cv-2026-11' from api.v_cv_terms_current;

do $$
declare
  v_ok boolean;
begin
  -- Thiếu consent / điều khoản hết hạn / phiên bản lạ / đường dẫn vào thư mục người khác
  begin
    perform api.register_cv('b2000000-0000-0000-0000-000000000002', 'u/00000000-0000-0000-0000-00000000000f/b2000000-0000-0000-0000-000000000002.pdf',
                            repeat('c2', 32), 'application/pdf', 1000, null);
    insert into results values ('register_cv rejects missing consent', 'accepted', 'rejected');
  exception when check_violation then
    insert into results values ('register_cv rejects missing consent', 'rejected', 'rejected');
  end;
  begin
    perform api.register_cv('b2000000-0000-0000-0000-000000000003', 'u/00000000-0000-0000-0000-00000000000f/b2000000-0000-0000-0000-000000000003.pdf',
                            repeat('c3', 32), 'application/pdf', 1000, 'cv-2026-01');
    insert into results values ('register_cv rejects retired terms version', 'accepted', 'rejected');
  exception when check_violation then
    insert into results values ('register_cv rejects retired terms version', 'rejected', 'rejected');
  end;
  begin
    perform api.register_cv('b2000000-0000-0000-0000-000000000004', 'u/00000000-0000-0000-0000-00000000000f/b2000000-0000-0000-0000-000000000004.pdf',
                            repeat('c4', 32), 'application/pdf', 1000, 'cv-9999');
    insert into results values ('register_cv rejects unknown terms version', 'accepted', 'rejected');
  exception when check_violation then
    insert into results values ('register_cv rejects unknown terms version', 'rejected', 'rejected');
  end;
  begin
    perform api.register_cv('b2000000-0000-0000-0000-000000000005', 'u/00000000-0000-0000-0000-00000000000a/b2000000-0000-0000-0000-000000000005.pdf',
                            repeat('c5', 32), 'application/pdf', 1000, 'cv-2026-11');
    insert into results values ('register_cv rejects path in another user folder', 'accepted', 'rejected');
  exception when invalid_parameter_value then
    insert into results values ('register_cv rejects path in another user folder', 'rejected', 'rejected');
  end;
  -- Ghi thẳng vào app.cvs (bỏ qua RPC) mà không có consent → constraint chặn
  begin
    insert into app.cvs (owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes)
    values (auth.uid(), auth.uid(), 'u/00000000-0000-0000-0000-00000000000f/raw.pdf', '\xc6', 'application/pdf', 1000);
    insert into results values ('direct insert without consent rejected', 'accepted', 'rejected');
  exception when check_violation then
    insert into results values ('direct insert without consent rejected', 'rejected', 'rejected');
  end;

  -- Consent không sửa được sau khi tạo (kể cả chủ CV)
  update app.cvs set consent_at = timestamptz '2020-01-01', consent_version = null
   where id = 'b2000000-0000-0000-0000-000000000001';
  select (consent_version = 'cv-2026-11' and consent_at > timestamptz '2026-01-01') into v_ok
    from app.cvs where id = 'b2000000-0000-0000-0000-000000000001';
  insert into results values ('consent is immutable after upload', v_ok::text, 'true');
end $$;
reset role;

-- Dữ liệu sinh ra từ CV b2…01 (worker chạy bằng service_role nên seed bằng superuser)
insert into app.cv_skills (cv_id, skill_id, evidence_level)
  values ('b2000000-0000-0000-0000-000000000001', (select id from ref.skills where slug = 'sql'), 'strong');
insert into app.cv_chunks (cv_id, section, chunk_no, content, embedding, model)
  values ('b2000000-0000-0000-0000-000000000001', 'experience', 0, 'đoạn đã che PII',
          ('[' || array_to_string(array_fill(0, array[1024]), ',') || ']')::extensions.halfvec, 'test');
insert into app.match_requests (kind, requester_id, cv_id, weights, engine_version)
  values ('seeker_topn', '00000000-0000-0000-0000-00000000000f', 'b2000000-0000-0000-0000-000000000001', '{}', 'test');
insert into app.explanations (cv_hash, jd_hash, model, body) values
  (decode(repeat('ab', 32), 'hex'), '\x01', 'test', 'giải thích cho CV b2…01'),
  ('\x01', '\x01', 'test', 'giải thích cho CV của A');      -- của CV khác, phải còn lại

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
do $$
declare
  v_deleted boolean;
  v_rows    int;
begin
  -- Xóa dòng trước khi xóa file → từ chối (không được để file mồ côi)
  begin
    perform api.delete_cv('b2000000-0000-0000-0000-000000000001');
    insert into results values ('delete_cv refuses while file still in Storage', 'deleted', 'refused');
  exception when object_not_in_prerequisite_state then
    insert into results values ('delete_cv refuses while file still in Storage', 'refused', 'refused');
  end;

  -- B không xóa được CV của A dù biết id
  insert into results values ('seekerB delete_cv on A cv returns false',
                              api.delete_cv(current_setting('test.cv_a')::uuid)::text, 'false');

  -- Luồng đúng: web xóa file qua Storage API rồi gọi api.delete_cv
  delete from storage.objects
   where bucket_id = 'cvs' and name = 'u/00000000-0000-0000-0000-00000000000f/b2000000-0000-0000-0000-000000000001.pdf';
  get diagnostics v_rows = row_count;
  v_deleted := api.delete_cv('b2000000-0000-0000-0000-000000000001');
  insert into results values ('seekerB deletes own file then cv', v_rows::text || '/' || v_deleted::text, '1/true');
end $$;
reset role;

-- Kiểm tra bằng superuser: không còn dòng nào gắn với CV đã xóa
insert into results select 'deleted cv leaves no rows or file',
  concat_ws('/',
    (select count(*) from app.cvs           where id    = 'b2000000-0000-0000-0000-000000000001'),
    (select count(*) from app.cv_skills     where cv_id = 'b2000000-0000-0000-0000-000000000001'),
    (select count(*) from app.cv_chunks     where cv_id = 'b2000000-0000-0000-0000-000000000001'),
    (select count(*) from app.match_requests where cv_id = 'b2000000-0000-0000-0000-000000000001'),
    (select count(*) from app.explanations  where cv_hash = decode(repeat('ab', 32), 'hex')),
    (select count(*) from storage.objects   where name like '%b2000000-0000-0000-0000-000000000001%')),
  '0/0/0/0/0/0';
insert into results select 'delete keeps cache of other cvs', count(*)::text, '1' from app.explanations where cv_hash = '\x01';
insert into results select 'audit cv_deleted: actor B, id only, no file path',
  (select (count(*) = 1 and bool_and(actor_id = '00000000-0000-0000-0000-00000000000f' and actor_role = 'seeker' and detail is null))::text
     from app.audit_log where action = 'cv_deleted' and entity = 'cv' and entity_id = 'b2000000-0000-0000-0000-000000000001')
  || '/' ||
  (select count(*) from app.audit_log where entity_id like 'u/%b2000000-0000-0000-0000-000000000001%')::text,
  'true/0';

-- Test nhóm 4: HR Công ty A & HR Công ty B (Cô lập dữ liệu đa tổ chức)
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000b","user_role":"hr","account_status":"active","org_id":"10000000-0000-0000-0000-00000000000a"}';
insert into results select 'hrA sees own hr job', count(*)::text, '1' from core.jobs where origin='hr';
insert into results select 'hrA sees own candidate cv', count(*)::text, '1' from app.cvs;
insert into results select 'hrA skills of B job hidden', count(*)::text, '0' from core.job_skills where job_id=4;
insert into results select 'hrA storage files', count(*)::text, '1' from storage.objects;
reset role;

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000c","user_role":"hr","account_status":"active","org_id":"10000000-0000-0000-0000-00000000000b"}';
insert into results select 'hrB cannot see A cv', count(*)::text, '0' from app.cvs;
reset role;

-- Test nhóm 5: Admin duyệt HR, khóa tài khoản, và kiểm chứng tài khoản bị khóa bị chặn tức thì
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000d","user_role":"admin","account_status":"active"}';
insert into results select 'admin sees all jobs', count(*)::text, '4' from core.jobs;
insert into results select 'admin cannot read CVs (least privilege)', count(*)::text, '0' from app.cvs;
insert into results select 'admin sees all 6 profiles', count(*)::text, '6' from app.profiles;

-- Admin duyệt yêu cầu HR của user E
select api.admin_review_hr_request(
  (select id from app.hr_requests where user_id = '00000000-0000-0000-0000-00000000000e' limit 1),
  true,
  'Đã xác minh email công ty C'
);
insert into results select 'admin approved HR request promotes user E to hr',
  (select role::text from app.profiles where user_id = '00000000-0000-0000-0000-00000000000e'),
  'hr';

-- Admin khóa tài khoản seeker A
select api.admin_set_account_status('00000000-0000-0000-0000-00000000000a', 'locked', 'Vi phạm điều khoản');
reset role;

-- Seeker A (dù vẫn cầm JWT cũ có account_status='active') thử đọc CV sau khi bị Admin khóa → RLS chặn tức thì!
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
insert into results select 'locked seeker blocked immediately from reading own CV', count(*)::text, '0' from app.cvs;
reset role;

-- Mở khóa lại cho Seeker A
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000d","user_role":"admin","account_status":"active"}';
select api.admin_set_account_status('00000000-0000-0000-0000-00000000000a', 'active', null);
reset role;

-- Test nhóm 5b (S3-D05, US-12): API đọc CV gọi RPC bằng JWT người dùng; RLS chặn CV người khác
select set_config('test.cv_a', id::text, false) from app.cvs where storage_path = 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf';
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
do $$
declare v_state text;
begin
  begin
    perform api.claim_cv_parse(current_setting('test.cv_a')::uuid);
    insert into results values ('seekerB cannot claim A cv for parsing', 'claimed', 'P0002');
  exception when others then
    get stacked diagnostics v_state = returned_sqlstate;
    insert into results values ('seekerB cannot claim A cv for parsing', v_state, 'P0002');
  end;
  begin
    perform api.save_cv_profile(current_setting('test.cv_a')::uuid, 'x', '{}', 1, 'x', '[]', 'v');
    insert into results values ('seekerB cannot save profile into A cv', 'saved', '55000');
  exception when others then
    get stacked diagnostics v_state = returned_sqlstate;
    insert into results values ('seekerB cannot save profile into A cv', v_state, '55000');
  end;
end $$;
reset role;

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
insert into results select 'seeker claims own cv for parsing', storage_path, 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf'
  from api.claim_cv_parse(current_setting('test.cv_a')::uuid);
do $$
declare v_state text;
begin
  perform api.claim_cv_parse(current_setting('test.cv_a')::uuid);
  insert into results values ('second claim while parsing is refused', 'claimed', '55P03');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('second claim while parsing is refused', v_state, '55P03');
end $$;
-- Lưu hồ sơ: python (đã có dòng máy tạo) + java; slug lạ bị bỏ
insert into results select 'seeker saves own cv profile (skills written)',
  api.save_cv_profile(current_setting('test.cv_a')::uuid, '[HỌ_TÊN] Backend', '{"skills":["Java"]}', 2.46, 'Backend Developer',
    '[{"skill_id":"python","evidence_level":"strong","evidence":"ETL bằng Python","years":2.0},
      {"skill_id":"java","evidence_level":"listed","evidence":"Java"},
      {"skill_id":"khong-co-slug-nay","evidence_level":"strong","evidence":"x"}]', 'test')::text,
  '2';
insert into results select 'saved cv is parsed with years and title',
  parse_status || '|' || years_exp::text || '|' || target_title, 'parsed|2.5|Backend Developer'
  from app.cvs where id = current_setting('test.cv_a')::uuid;
-- Người dùng tự thêm docker; đọc lại CV không được ghi đè dòng tự thêm
insert into app.cv_skills (cv_id, skill_id, evidence_level, confirmed)
  values (current_setting('test.cv_a')::uuid, (select id from ref.skills where slug = 'docker'), 'user_added', true);
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 1, 't',
  '[{"skill_id":"docker","evidence_level":"listed","evidence":"Docker"},
    {"skill_id":"python","evidence_level":"listed","evidence":"Python"}]', 'test');
insert into results select 're-parse keeps user_added skill', evidence_level::text, 'user_added'
  from app.cv_skills where cv_id = current_setting('test.cv_a')::uuid
   and skill_id = (select id from ref.skills where slug = 'docker');
-- java của lần đọc trước bị xóa, python ghi lại theo lần đọc mới
insert into results select 're-parse replaces machine skills', string_agg(r.slug || ':' || s.evidence_level, ','), 'python:listed'
  from app.cv_skills s join ref.skills r on r.id = s.skill_id
 where s.cv_id = current_setting('test.cv_a')::uuid and not s.confirmed;
-- File lỗi: parse_status = failed + mã lỗi
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
select api.fail_cv_parse(current_setting('test.cv_a')::uuid, 'ocr_required');
insert into results select 'failed parse records error code', parse_status || '|' || parse_error, 'failed|ocr_required'
  from app.cvs where id = current_setting('test.cv_a')::uuid;
reset role;

-- Test nhóm 5b (S3-H02, S3-H03, migration 0010): xác nhận kỹ năng, sửa số năm / chức danh
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
do $$
declare v_state text;
begin
  perform api.confirm_cv_profile(current_setting('test.cv_a')::uuid, 1, 'x', '[]');
  insert into results values ('confirm refused while cv is parsing', 'saved', '55000');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('confirm refused while cv is parsing', v_state, '55000');
end $$;
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 2, 'Backend Developer',
  '[{"skill_id":"python","evidence_level":"strong","evidence":"ETL bằng Python","years":2},
    {"skill_id":"sql","evidence_level":"listed","evidence":"SQL"}]', 'test');
insert into results select 'v_my_cv_skills lists own cv skills with names',
  string_agg(slug || ':' || name || ':' || evidence_level || ':' || confirmed, ',' order by slug),
  'docker:Docker:user_added:true,python:Python:strong:false,sql:SQL:listed:false'
  from api.v_my_cv_skills where cv_id = current_setting('test.cv_a')::uuid;
-- Giữ python + docker, tự thêm java, bỏ sql; số năm làm tròn 1 chữ số, chức danh bỏ khoảng trắng
insert into results select 'confirm returns skill count',
  api.confirm_cv_profile(current_setting('test.cv_a')::uuid, 3.25, '  Data Engineer  ',
    jsonb_build_array(
      jsonb_build_object('skill_id', (select id from ref.skills where slug = 'python')),
      jsonb_build_object('skill_id', (select id from ref.skills where slug = 'docker')),
      jsonb_build_object('skill_id', (select id from ref.skills where slug = 'java')),
      jsonb_build_object('skill_id', (select id from ref.skills where slug = 'java'))))::text,
  '3';
insert into results select 'confirm keeps, adds user_added, removes dropped',
  string_agg(slug || ':' || evidence_level || ':' || confirmed, ',' order by slug),
  'docker:user_added:true,java:user_added:true,python:strong:true'
  from api.v_my_cv_skills where cv_id = current_setting('test.cv_a')::uuid;
insert into results select 'confirm saves years, title, confirmed time',
  years_exp::text || '|' || target_title || '|' || (profile_confirmed_at is not null)::text, '3.3|Data Engineer|true'
  from api.v_my_cvs where id = current_setting('test.cv_a')::uuid;
-- null = giữ nguyên số năm và chức danh
select api.confirm_cv_profile(current_setting('test.cv_a')::uuid, null, null,
  (select jsonb_agg(jsonb_build_object('skill_id', skill_id)) from api.v_my_cv_skills
    where cv_id = current_setting('test.cv_a')::uuid));
insert into results select 'confirm with null years/title keeps them', years_exp::text || '|' || target_title, '3.3|Data Engineer'
  from api.v_my_cvs where id = current_setting('test.cv_a')::uuid;
-- Đọc lại CV: dòng đã xác nhận giữ nguyên, kỹ năng đã bỏ (sql) được máy gợi ý lại
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 2, 'Backend Developer',
  '[{"skill_id":"python","evidence_level":"listed","evidence":"Python"},
    {"skill_id":"sql","evidence_level":"listed","evidence":"SQL"}]', 'test');
insert into results select 're-parse keeps confirmed skills',
  string_agg(slug || ':' || evidence_level || ':' || confirmed, ',' order by slug),
  'docker:user_added:true,java:user_added:true,python:strong:true,sql:listed:false'
  from api.v_my_cv_skills where cv_id = current_setting('test.cv_a')::uuid;
insert into results select 're-parse keeps confirmed years/title', years_exp::text || '|' || target_title, '3.3|Data Engineer'
  from api.v_my_cvs where id = current_setting('test.cv_a')::uuid;
do $$
declare
  v_state text;
  v_case  record;
begin
  for v_case in
    select * from (values
      ('confirm rejects years > 60',      70::numeric, '[]'::jsonb),
      ('confirm rejects non-array skills', 1::numeric, '{"skill_id": 1}'::jsonb),
      ('confirm rejects slug as skill_id', 1::numeric, '[{"skill_id": "python"}]'::jsonb),
      ('confirm rejects missing skill_id', 1::numeric, '[{"id": 1}]'::jsonb),
      ('confirm rejects unknown skill',    1::numeric, '[{"skill_id": 999999999}]'::jsonb)
    ) t(name, years, skills)
  loop
    begin
      perform api.confirm_cv_profile(current_setting('test.cv_a')::uuid, v_case.years, null, v_case.skills);
      insert into results values (v_case.name, 'saved', '22023');
    exception when others then
      get stacked diagnostics v_state = returned_sqlstate;
      insert into results values (v_case.name, v_state, '22023');
    end;
  end loop;
end $$;
insert into results select 'rejected confirm changes nothing', count(*)::text || '|' || max(years_exp)::text, '4|3.3'
  from api.v_my_cv_skills s join api.v_my_cvs c on c.id = s.cv_id
 where s.cv_id = current_setting('test.cv_a')::uuid;
-- Từ điển cho ô gợi ý: gõ alias "reactjs" ra React; chỉ kỹ năng đang dùng
insert into results select 'v_skills finds React by alias reactjs', string_agg(name, ','), 'React'
  from api.v_skills where 'reactjs' = any (aliases);
insert into results select 'v_skills only active skills',
  ((select count(*) from api.v_skills) = (select count(*) from ref.skills where is_active))::text, 'true';
reset role;

-- Seeker B không xem / xác nhận được kỹ năng CV của A
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
insert into results select 'seekerB cannot read A cv skills via view', count(*)::text, '0'
  from api.v_my_cv_skills where cv_id = current_setting('test.cv_a')::uuid;
do $$
declare v_state text;
begin
  perform api.confirm_cv_profile(current_setting('test.cv_a')::uuid, 1, 'x', '[]');
  insert into results values ('seekerB cannot confirm A cv', 'saved', 'P0002');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('seekerB cannot confirm A cv', v_state, 'P0002');
end $$;
reset role;
insert into results select 'A skills intact after B confirm attempt', count(*)::text, '4'
  from app.cv_skills where cv_id = current_setting('test.cv_a')::uuid;

-- Tối đa 5 CV / người tìm việc; register_cv lưu tên tệp gốc (chỉ phần tên, bỏ thư mục)
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000010', 'seeker3@x.vn', '{"full_name":"Vũ Ứng Viên C"}'::jsonb);
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000010","user_role":"seeker","account_status":"active"}';
select api.register_cv('c3000000-0000-0000-0000-000000000001',
                       'u/00000000-0000-0000-0000-000000000010/c3000000-0000-0000-0000-000000000001.pdf',
                       repeat('d1', 32), 'application/pdf', 1000, 'cv-2026-11', E'C:\\Users\\vu\\CV Vũ C\t.pdf');
insert into results select 'register_cv stores original file name only', original_name, 'CV Vũ C.pdf'
  from api.v_my_cvs where id = 'c3000000-0000-0000-0000-000000000001';
select api.register_cv(('c3000000-0000-0000-0000-00000000000' || i)::uuid,
                       'u/00000000-0000-0000-0000-000000000010/c3000000-0000-0000-0000-00000000000' || i || '.pdf',
                       repeat('d' || i, 32), 'application/pdf', 1000, 'cv-2026-11')
  from generate_series(2, 5) i;
do $$
declare v_state text;
begin
  perform api.register_cv('c3000000-0000-0000-0000-000000000006',
                          'u/00000000-0000-0000-0000-000000000010/c3000000-0000-0000-0000-000000000006.pdf',
                          repeat('d6', 32), 'application/pdf', 1000, 'cv-2026-11');
  insert into results values ('register_cv rejects 6th cv', 'accepted', '53400');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('register_cv rejects 6th cv', v_state, '53400');
end $$;
insert into results select 'seeker keeps 5 cvs', count(*)::text, '5' from api.v_my_cvs;
reset role;

-- Test nhóm 5c (S4-D01/D02, migration 0012): role chỉ đọc matcher_ro cho API so khớp
-- Đoạn vector cho tin crawl #1 và JD nội bộ HR #3 (worker ghi bằng service_role → seed bằng superuser)
insert into core.job_chunks (job_id, section, chunk_no, content, embedding, model)
select j, 'summary', 0, 'đoạn thử',
       ('[' || array_to_string(array_fill(0.01::float4, array[1024]), ',') || ']')::extensions.halfvec,
       'test-model'
  from unnest(array[1, 3]) j
on conflict do nothing;
grant all on results to matcher_ro;  -- chỉ bảng tạm của bộ test
insert into results select 'matcher_ro logs in read-only',
  (select coalesce(array_to_string(rolconfig, ','), '') like '%default_transaction_read_only=on%'
     from pg_roles where rolname = 'matcher_ro')::text, 'true';
set role matcher_ro;
insert into results select 'matcher sees only crawled jobs',
  (select string_agg(distinct origin::text, ',') from core.jobs), 'crawled';
insert into results select 'matcher reads chunks of crawled jobs only',
  (select string_agg(job_id::text, ',' order by job_id) from core.job_chunks where model = 'test-model'), '1';
insert into results select 'matcher reads skills of crawled jobs only',
  (select count(*) from core.job_skills where job_id in (3, 4))::text, '0';
insert into results select 'matcher reads skill dictionary', ((select count(*) from ref.skills) > 0)::text, 'true';
do $$
declare
  v_state text;
  v_case  record;
begin
  for v_case in
    select * from (values
      ('matcher cannot read cvs',        'select count(*) from app.cvs'),
      ('matcher cannot read cv chunks',  'select count(*) from app.cv_chunks'),
      ('matcher cannot update jobs',     'update core.jobs set title = title where id = 1'),
      ('matcher cannot insert job skills',
       'insert into core.job_skills (job_id, skill_id, level) select 1, id, ''required'' from ref.skills limit 1')
    ) t(name, sql)
  loop
    begin
      execute v_case.sql;
      insert into results values (v_case.name, 'allowed', '42501');
    exception when others then
      get stacked diagnostics v_state = returned_sqlstate;
      insert into results values (v_case.name, v_state, '42501');
    end;
  end loop;
end $$;
reset role;

-- Test nhóm 5d (S4-D02, migration 0012): lưu / đọc vector đoạn CV bằng JWT người dùng
create temp table t_vec as
select jsonb_agg(0.25) as v1024, '[0.25, 0.5, 0.75]'::jsonb as v3 from generate_series(1, 1024);
grant select on t_vec to authenticated;
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
insert into results select 'save_cv_chunks stores chunks',
  api.save_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3',
    jsonb_build_array(
      jsonb_build_object('section', 'summary', 'chunk_no', 0, 'content', 'Data Engineer · Python', 'embedding', v1024),
      jsonb_build_object('section', 'experience', 'chunk_no', 0, 'content', 'ETL bằng Airflow', 'embedding', v1024)))::text,
  '2'
  from t_vec;
insert into results select 'get_cv_chunks returns 1024-dim vectors',
  count(*)::text || '|' || min(jsonb_array_length(embedding::jsonb))::text || '|' || min((embedding::jsonb ->> 0)::numeric)::text,
  '2|1024|0.25'
  from api.get_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3');
insert into results select 'get_cv_chunks filters by model', count(*)::text, '0'
  from api.get_cv_chunks(current_setting('test.cv_a')::uuid, 'other-model');
-- Lưu lại (CV đọc lại / hồ sơ đổi): thay toàn bộ đoạn cũ
select api.save_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3',
  jsonb_build_array(jsonb_build_object('section', 'summary', 'chunk_no', 0, 'content', 'Mới', 'embedding', v1024)))
  from t_vec;
insert into results select 'save_cv_chunks replaces old chunks', string_agg(section || ':' || content, ','), 'summary:Mới'
  from api.get_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3');
do $$
declare
  v_state text;
  v_case  record;
  v1024   jsonb := (select v1024 from t_vec);
  v3      jsonb := (select v3 from t_vec);
begin
  for v_case in
    select * from (values
      ('save_cv_chunks rejects 3-dim vector', 'm',
       jsonb_build_array(jsonb_build_object('section', 's', 'chunk_no', 0, 'embedding', v3))),
      ('save_cv_chunks rejects non-array', 'm', '{"section": "s"}'::jsonb),
      ('save_cv_chunks rejects missing section', 'm',
       jsonb_build_array(jsonb_build_object('chunk_no', 0, 'embedding', v1024))),
      ('save_cv_chunks rejects missing model', '',
       jsonb_build_array(jsonb_build_object('section', 's', 'chunk_no', 0, 'embedding', v1024)))
    ) t(name, model, chunks)
  loop
    begin
      perform api.save_cv_chunks(current_setting('test.cv_a')::uuid, v_case.model, v_case.chunks);
      insert into results values (v_case.name, 'saved', '22023');
    exception when others then
      get stacked diagnostics v_state = returned_sqlstate;
      insert into results values (v_case.name, v_state, '22023');
    end;
  end loop;
end $$;
insert into results select 'rejected saves keep old chunks', count(*)::text, '1'
  from api.get_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3');
reset role;

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
insert into results select 'seekerB cannot see A cv chunks', count(*)::text, '0'
  from app.cv_chunks where cv_id = current_setting('test.cv_a')::uuid;
do $$
declare
  v_state text;
begin
  begin
    perform * from api.get_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3');
    insert into results values ('seekerB cannot read A chunks via RPC', 'read', 'P0002');
  exception when others then
    get stacked diagnostics v_state = returned_sqlstate;
    insert into results values ('seekerB cannot read A chunks via RPC', v_state, 'P0002');
  end;
  begin
    perform api.save_cv_chunks(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3', '[]');
    insert into results values ('seekerB cannot save chunks into A cv', 'saved', 'P0002');
  exception when others then
    get stacked diagnostics v_state = returned_sqlstate;
    insert into results values ('seekerB cannot save chunks into A cv', v_state, 'P0002');
  end;
end $$;
reset role;
insert into results select 'A chunks intact after B attempts', count(*)::text, '1'
  from app.cv_chunks where cv_id = current_setting('test.cv_a')::uuid;

set role anon; set request.jwt.claims = '{}';
do $$
declare v_state text;
begin
  perform api.save_cv_chunks(gen_random_uuid(), 'm', '[]');
  insert into results values ('anon cannot call save_cv_chunks', 'called', '42501');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('anon cannot call save_cv_chunks', v_state, '42501');
end $$;
reset role;

-- Test nhóm 5e (S3-H04, S3-H05, migration 0015): CV chính, hạn lưu, chuyển hướng tin đã gộp
-- Seeker D tải 3 CV: c4…01, c4…02, c4…03
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000011', 'seeker4@x.vn', '{"full_name":"Mai Ứng Viên D"}'::jsonb);
insert into storage.objects (bucket_id, name) values
  ('cvs', 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000001.pdf'),
  ('cvs', 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000002.pdf'),
  ('cvs', 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000003.pdf');

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000011","user_role":"seeker","account_status":"active"}';
select api.register_cv('c4000000-0000-0000-0000-000000000001', 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000001.pdf',
                       repeat('e1', 32), 'application/pdf', 1000, 'cv-2026-11', 'cv-1.pdf');
select api.register_cv('c4000000-0000-0000-0000-000000000002', 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000002.pdf',
                       repeat('e2', 32), 'application/pdf', 1000, 'cv-2026-11', 'cv-2.pdf');
select api.register_cv('c4000000-0000-0000-0000-000000000003', 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000003.pdf',
                       repeat('e3', 32), 'application/pdf', 1000, 'cv-2026-11', 'cv-3.pdf');
insert into results select 'register_cv: first cv becomes primary',
  string_agg(right(id::text, 2) || ':' || is_primary, ',' order by id), '01:true,02:false,03:false' from api.v_my_cvs;
insert into results select 'register_cv: delete_after = today + 30 in v_my_cvs',
  bool_and(delete_after = current_date + 30)::text, 'true' from api.v_my_cvs;
reset role;

-- Thứ tự tải cố định để kiểm "CV mới nhất còn lại"
update app.cvs set created_at = now() - interval '3 days' where id = 'c4000000-0000-0000-0000-000000000001';
update app.cvs set created_at = now() - interval '2 days' where id = 'c4000000-0000-0000-0000-000000000002';
update app.cvs set created_at = now() - interval '1 day'  where id = 'c4000000-0000-0000-0000-000000000003';

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000011","user_role":"seeker","account_status":"active"}';
select api.set_primary_cv('c4000000-0000-0000-0000-000000000001');
select api.set_primary_cv('c4000000-0000-0000-0000-000000000002');
select api.set_primary_cv('c4000000-0000-0000-0000-000000000002');   -- bấm lại: không lỗi
insert into results select 'set_primary_cv moves primary, exactly one',
  string_agg(right(id::text, 2) || ':' || is_primary, ',' order by id), '01:false,02:true,03:false' from api.v_my_cvs;
do $$
begin
  begin
    perform api.set_primary_cv(current_setting('test.cv_a')::uuid);
    insert into results values ('seekerD cannot set A cv as primary', 'accepted', 'P0002');
  exception when no_data_found then
    insert into results values ('seekerD cannot set A cv as primary', 'P0002', 'P0002');
  end;
end $$;

-- Xóa CV chính (02) → CV mới nhất còn lại (03) thành CV chính
delete from storage.objects where name = 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000002.pdf';
select api.delete_cv('c4000000-0000-0000-0000-000000000002');
insert into results select 'deleting primary cv promotes newest remaining',
  string_agg(right(id::text, 2) || ':' || is_primary, ',' order by id), '01:false,03:true' from api.v_my_cvs;
-- Xóa CV thường → CV chính giữ nguyên
delete from storage.objects where name = 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000001.pdf';
select api.delete_cv('c4000000-0000-0000-0000-000000000001');
insert into results select 'deleting non-primary cv keeps primary',
  string_agg(right(id::text, 2) || ':' || is_primary, ',' order by id), '03:true' from api.v_my_cvs;
-- Xóa CV cuối cùng → không lỗi, không còn CV
delete from storage.objects where name = 'u/00000000-0000-0000-0000-000000000011/c4000000-0000-0000-0000-000000000003.pdf';
insert into results select 'deleting last cv works', api.delete_cv('c4000000-0000-0000-0000-000000000003')::text, 'true';
insert into results select 'no cv left after deleting last', count(*)::text, '0' from api.v_my_cvs;
reset role;

set role anon; set request.jwt.claims = '{}';
do $$
declare v_state text;
begin
  perform api.set_primary_cv(gen_random_uuid());
  insert into results values ('anon cannot call set_primary_cv', 'called', '42501');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('anon cannot call set_primary_cv', v_state, '42501');
end $$;
reset role;

-- CV người tìm việc quá hạn: chưa bị xóa (chưa có bước xóa file trong Storage), kiểm sau purge ở nhóm 6
update app.cvs set delete_after = current_date - 1
 where storage_path = 'u/00000000-0000-0000-0000-00000000000f/cv-b.pdf';

-- Test nhóm 5f (S4-D04, migration 0013): hồ sơ CV để so khớp + ghi một lượt Top N
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
insert into results select 'get_cv_for_match returns own cv',
  (v ->> 'cv_id') || '|' || jsonb_typeof(v -> 'skills') || '|' || jsonb_typeof(v -> 'sections'),
  current_setting('test.cv_a') || '|array|object'
  from (select api.get_cv_for_match(current_setting('test.cv_a')::uuid) v) t;
select set_config('test.match_id', api.save_match(
  current_setting('test.cv_a')::uuid, 10, '{"provinces": [1]}', '{"K": 0.25, "M": 0.35, "E": 0.3, "X": 0.1}',
  'ranker-v1', 2, 812,
  '[{"rank": 1, "job_id": 1, "score": 82.4, "k": 0.9, "m": 0.75, "e": 0.88, "x": null,
     "gap": {"missing": ["spark"]}, "explanation": "Khớp 2/2 kỹ năng bắt buộc"}]')::text, false);
insert into results select 'save_match writes request', kind || '|' || top_n || '|' || engine_version || '|' || latency_ms,
  'seeker_topn|10|ranker-v1|812'
  from app.match_requests where id = current_setting('test.match_id')::bigint;
insert into results select 'save_match writes results (null component kept)',
  count(*)::text || '|' || min(score_h)::text || '|' || bool_and(x is null)::text, '1|82.40|true'
  from app.match_results where request_id = current_setting('test.match_id')::bigint;
do $$
declare
  v_state text;
  v_case  record;
begin
  for v_case in
    select * from (values
      ('save_match rejects more results than top_n', 1,
       '[{"rank": 1, "job_id": 1, "score": 50}, {"rank": 2, "job_id": 1, "score": 40}]'::jsonb, '22023'),
      ('save_match rejects hr job', 5, '[{"rank": 1, "job_id": 3, "score": 50}]'::jsonb, '22023'),
      ('save_match rejects unknown job', 5, '[{"rank": 1, "job_id": 999999, "score": 50}]'::jsonb, '22023'),
      ('save_match rejects top_n 0', 0, '[]'::jsonb, '22023'),
      ('save_match rejects score above 100', 5, '[{"rank": 1, "job_id": 1, "score": 101}]'::jsonb, '23514')
    ) t(name, top_n, res, expected)
  loop
    begin
      perform api.save_match(current_setting('test.cv_a')::uuid, v_case.top_n, '{}', '{}', 'ranker-v1',
                             2, 1, v_case.res);
      insert into results values (v_case.name, 'saved', v_case.expected);
    exception when others then
      get stacked diagnostics v_state = returned_sqlstate;
      insert into results values (v_case.name, v_state, v_case.expected);
    end;
  end loop;
end $$;
reset role;

-- 0014: hồ sơ + vector đoạn CV trong một lượt gọi
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
insert into results select 'get_cv_match_input returns cv and chunks',
  (v ->> 'cv_id') || '|' || jsonb_array_length(v -> 'chunks')::text || '|'
    || jsonb_array_length((v -> 'chunks' -> 0 ->> 'embedding')::jsonb)::text,
  current_setting('test.cv_a') || '|1|1024'
  from (select api.get_cv_match_input(current_setting('test.cv_a')::uuid, 'cf/baai/bge-m3') v) t;
insert into results select 'get_cv_match_input filters chunks by model',
  jsonb_array_length(api.get_cv_match_input(current_setting('test.cv_a')::uuid, 'other') -> 'chunks')::text, '0';
reset role;

set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
insert into results select 'seekerB cannot read A match results', count(*)::text, '0'
  from app.match_requests where id = current_setting('test.match_id')::bigint;
do $$
declare
  v_state text;
  v_case  record;
begin
  for v_case in
    select * from (values
      ('seekerB cannot get A cv for match',
       'select api.get_cv_for_match(current_setting(''test.cv_a'')::uuid)'),
      ('seekerB cannot get A cv match input',
       'select api.get_cv_match_input(current_setting(''test.cv_a'')::uuid, ''cf/baai/bge-m3'')'),
      ('seekerB cannot save match on A cv',
       'select api.save_match(current_setting(''test.cv_a'')::uuid, 5, ''{}'', ''{}'', ''v'', 1, 1, ''[]'')')
    ) t(name, sql)
  loop
    begin
      execute v_case.sql;
      insert into results values (v_case.name, 'allowed', 'P0002');
    exception when others then
      get stacked diagnostics v_state = returned_sqlstate;
      insert into results values (v_case.name, v_state, 'P0002');
    end;
  end loop;
end $$;
reset role;

set role anon; set request.jwt.claims = '{}';
do $$
declare v_state text;
begin
  perform api.save_match(gen_random_uuid(), 5, '{}', '{}', 'v', 1, 1, '[]');
  insert into results values ('anon cannot call save_match', 'called', '42501');
exception when others then
  get stacked diagnostics v_state = returned_sqlstate;
  insert into results values ('anon cannot call save_match', v_state, '42501');
end $$;
reset role;

-- Test nhóm 5g (#678, migration 0016): lưu kỹ năng gợi ý của CV, đọc qua api.v_my_cvs
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","user_role":"seeker","account_status":"active"}';
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
-- slug lạ và reason lạ bị bỏ; name lấy từ ref.skills; câu trích cắt còn 400 ký tự
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 2, 'Backend Developer',
  '[{"skill_id":"python","evidence_level":"strong","evidence":"Python"}]', 'test',
  jsonb_build_array(
    jsonb_build_object('skill_id', 'japanese', 'name', 'sai tên', 'reason', 'org_name',
                       'evidence', 'Thành viên Câu lạc bộ tiếng Nhật', 'highlight', jsonb_build_array(22, 32),
                       'section', 'activities'),
    jsonb_build_object('skill_id', 'khong-co-slug-nay', 'reason', 'org_name', 'evidence', 'x'),
    jsonb_build_object('skill_id', 'java', 'reason', 'ly-do-la', 'evidence', 'x'),
    jsonb_build_object('skill_id', 'english', 'reason', 'language_no_proficiency',
                       'evidence', repeat('a', 500), 'section', 'summary')));
insert into results select 'save_cv_profile stores filtered suggested_skills',
  string_agg((x ->> 'skill_id') || ':' || (x ->> 'name') || ':' || (x ->> 'reason'), ',' order by o),
  'japanese:Tiếng Nhật:org_name,english:Tiếng Anh:language_no_proficiency'
  from api.v_my_cvs v, jsonb_array_elements(v.suggested_skills) with ordinality as e(x, o)
 where v.id = current_setting('test.cv_a')::uuid;
insert into results select 'suggested evidence capped at 400 chars, highlight kept',
  (select max(length(x ->> 'evidence')) from jsonb_array_elements(suggested_skills) x)::text || '|' ||
  (suggested_skills -> 0 -> 'highlight')::text, '400|[22, 32]'
  from api.v_my_cvs where id = current_setting('test.cv_a')::uuid;
insert into results select 'suggestions are not saved as cv_skills', count(*)::text, '0'
  from app.cv_skills s join ref.skills r on r.id = s.skill_id
 where s.cv_id = current_setting('test.cv_a')::uuid and r.slug in ('japanese', 'english');
-- Gọi kiểu cũ 7 tham số (API chưa cập nhật) và tham số không phải mảng: gợi ý về []
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 2, 'Backend Developer', '[]', 'test');
insert into results select 'old 7-arg save resets suggestions', suggested_skills::text, '[]'
  from app.cvs where id = current_setting('test.cv_a')::uuid;
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 2, 'Backend Developer', '[]', 'test',
  '{"skill_id":"japanese"}');
insert into results select 'non-array suggestions stored as []', suggested_skills::text, '[]'
  from app.cvs where id = current_setting('test.cv_a')::uuid;
select api.claim_cv_parse(current_setting('test.cv_a')::uuid);
select api.save_cv_profile(current_setting('test.cv_a')::uuid, 't', '{}', 2, 'Backend Developer', '[]', 'test',
  '[{"skill_id":"japanese","reason":"org_name","evidence":"CLB tiếng Nhật"}]');
reset role;
-- Seeker B không thấy gợi ý trong CV của seeker A
set role authenticated;
set request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000f","user_role":"seeker","account_status":"active"}';
insert into results select 'other seeker cannot read suggestions', count(*)::text, '0'
  from api.v_my_cvs where id = current_setting('test.cv_a')::uuid;
reset role;

-- Test nhóm 6: Bảng tổng hợp Gold & Dọn CV quá hạn
select mart.refresh_skill_weekly(date_trunc('week', current_date)::date);
select mart.refresh_region_salary(current_date);
select mart.refresh_system_daily(current_date);
insert into results select 'skill_weekly python share (2 tin mở, 1 có Python)', share::text, '0.5000'
  from mart.skill_weekly
  where skill_id = (select id from ref.skills where slug = 'python') and job_family_id = 0;
insert into results select 'region_salary hides salary when n < 20', (p50_vnd is null)::text, 'true' from mart.region_salary where province_code=1 and job_family_id=0;
insert into results select 'system_daily recorded logins_today', (logins_today >= 1)::text, 'true' from mart.system_daily where day = current_date;
insert into results select 'purge expired hr cv', app.purge_expired_cvs()::text, '1';
insert into results select 'purge keeps expired seeker cv (no Storage cleanup yet)', count(*)::text, '1'
  from app.cvs where storage_path = 'u/00000000-0000-0000-0000-00000000000f/cv-b.pdf';

-- (S3-H05, migration 0015) Chạy sau bảng tổng hợp để tin gộp thêm không làm lệch số tuần.
-- Tin 1 giữ lại, tin TopCV trùng bị gộp vào; link cũ của tin bị gộp phải chuyển về tin 1
insert into core.jobs (title, title_norm, company_id, apply_url)
values ('Lập trình viên Python (Data Engineer)', 'lap trinh vien python', 1, 'https://www.topcv.vn/x-1-dup');
select set_config('test.dup_job', id::text, false) from core.jobs where apply_url = 'https://www.topcv.vn/x-1-dup';
select core.merge_jobs(1, current_setting('test.dup_job')::bigint);
select set_config('test.dup_pid',  public_id::text, false) from core.jobs where id = current_setting('test.dup_job')::bigint;
select set_config('test.keep_pid', public_id::text, false) from core.jobs where id = 1;

set role anon; set request.jwt.claims = '{}';
insert into results select 'job_redirect: merged job -> kept job',
  api.job_redirect(current_setting('test.dup_pid')::uuid)::text, current_setting('test.keep_pid');
insert into results select 'job_redirect: job not merged -> null',
  coalesce(api.job_redirect(current_setting('test.keep_pid')::uuid)::text, 'null'), 'null';
insert into results select 'job_redirect: unknown id -> null',
  coalesce(api.job_redirect(gen_random_uuid())::text, 'null'), 'null';
reset role;

-- In bảng kết quả và dừng CI nếu có bất kỳ test nào FAIL
select test, got, expected, case when got = expected then 'PASS' else 'FAIL' end as status from results;

do $$
declare
  v_failed integer;
begin
  select count(*) into v_failed from results where got is distinct from expected;
  if v_failed > 0 then
    raise exception '% RLS/Auth verification test(s) FAILED!', v_failed;
  end if;
end $$;
