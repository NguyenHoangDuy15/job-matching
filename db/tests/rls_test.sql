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
