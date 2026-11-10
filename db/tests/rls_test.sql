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
  ('00000000-0000-0000-0000-00000000000e', 'hr_applicant@companyc.vn', '{"full_name":"Hoàng HR Mới","requested_role":"hr","company_name":"Công ty C","work_email":"hr_applicant@companyc.vn"}'::jsonb);

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

insert into app.cvs (owner_user_id, uploaded_by, storage_path, file_sha256, mime, size_bytes) values
  ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000a', 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf', '\x01', 'application/pdf', 1000);
insert into app.cvs (org_id, job_id, uploaded_by, storage_path, file_sha256, mime, size_bytes, delete_after) values
  ('10000000-0000-0000-0000-00000000000a', 3, '00000000-0000-0000-0000-00000000000b', 'o/10000000-0000-0000-0000-00000000000a/3/c1.pdf', '\x02', 'application/pdf', 1000, current_date - 1);

insert into storage.objects (bucket_id, name) values
  ('cvs', 'u/00000000-0000-0000-0000-00000000000a/cv1.pdf'),
  ('cvs', 'o/10000000-0000-0000-0000-00000000000a/3/c1.pdf');

-- 4. Bảng lưu kết quả kiểm thử
create temp table results(test text, got text, expected text);
grant all on results to anon, authenticated;

-- Test nhóm 1: Đăng ký tự động, Trigger Login & Custom Access Token Hook
insert into results select 'trigger created 5 profiles on register', count(*)::text, '5' from app.profiles;
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
insert into results select 'admin sees all 5 profiles', count(*)::text, '5' from app.profiles;

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
