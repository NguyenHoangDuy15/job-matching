-- =====================================================================
--  Migration 0003 — Cây kỹ năng + thống nhất tên section JD (S2-D03, PR #618)
--  Chạy SAU 0001_schema_v2.sql và 0002_fx_rates.sql. Chạy lại nhiều lần không lỗi.
--
--  1. ref.skills.parent_id: kỹ năng cấp 3 trỏ về kỹ năng cấp 2 (React → JavaScript).
--  2. Ghi chú đúng cách chuẩn hóa ref.skill_aliases.alias_norm (NFC + chữ thường, GIỮ dấu).
--  3. core.job_chunks.section dùng cùng tên 4 section với core.jobs.
--  4. core.jobs.jd_text: toàn văn JD trước khi tách section (crawler ghi), để bước tách
--     section (skillkit.sections) ghi 4 cột mà không mất bản gốc.
-- =====================================================================

-- 1. Cây kỹ năng ---------------------------------------------------------------
alter table ref.skills
  add column if not exists parent_id integer references ref.skills (id) on delete set null;

create index if not exists skills_parent_idx on ref.skills (parent_id) where parent_id is not null;

comment on column ref.skills.parent_id is
  'Kỹ năng cha (cấp 2) của kỹ năng cấp 3, ví dụ react → javascript. NULL = kỹ năng cấp 2. '
  'Nhóm cấp 1 nằm ở ref.skill_categories. Cây chỉ 2 tầng: cha phải là kỹ năng không có cha.';

-- Cây đúng 2 tầng: không tự trỏ, cha không được có cha, đã làm cha thì không được có cha.
create or replace function ref.check_skill_parent() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.parent_id is null then
    return new;
  end if;
  if new.parent_id = new.id then
    raise exception 'ref.skills %: parent_id không được trỏ về chính nó', new.slug
      using errcode = '23514';
  end if;
  if exists (select 1 from ref.skills p where p.id = new.parent_id and p.parent_id is not null) then
    raise exception 'ref.skills %: kỹ năng cha phải là kỹ năng cấp 2 (không có cha)', new.slug
      using errcode = '23514';
  end if;
  if exists (select 1 from ref.skills c where c.parent_id = new.id) then
    raise exception 'ref.skills %: đang là cha của kỹ năng khác nên không được có cha', new.slug
      using errcode = '23514';
  end if;
  return new;
end $$;

drop trigger if exists skills_parent_check on ref.skills;
create trigger skills_parent_check
  before insert or update of parent_id on ref.skills
  for each row execute function ref.check_skill_parent();

revoke execute on function ref.check_skill_parent() from public, anon, authenticated;

-- 2. alias_norm giữ dấu -----------------------------------------------------------
-- Ghi chú trong 0001 viết "bỏ dấu" là sai: từ điển (skillkit.matcher) so khớp sau NFC +
-- chữ thường và GIỮ dấu để "gõ" không thành "go". ref.province_legacy.alias_norm thì vẫn bỏ dấu.
comment on column ref.skill_aliases.alias_norm is
  'Cách viết kỹ năng sau chuẩn hóa NFC + chữ thường, GIỮ dấu tiếng Việt (khớp skillkit.matcher). '
  'Ví dụ: "reactjs", "react.js", "lập trình c".';

comment on column ref.province_legacy.alias_norm is
  'Tên tỉnh/thành cũ hoặc biến thể, chữ thường và BỎ dấu (khớp ingestion.location).';

-- 3. Tên section của core.job_chunks khớp 4 cột section của core.jobs -----------------
-- 'summary' giữ lại cho đoạn tóm tắt (tiêu đề + kỹ năng chính) dùng khi embedding.
-- Bảng hiện chưa có dữ liệu; đổi tên cũ (nếu có) trước khi thay ràng buộc.
update core.job_chunks set section = 'description' where section = 'responsibilities';

alter table core.job_chunks drop constraint if exists job_chunks_section_check;
alter table core.job_chunks add constraint job_chunks_section_check
  check (section in ('summary', 'description', 'requirements', 'preferred', 'benefits'));

comment on column core.job_chunks.section is
  'Đoạn thuộc section nào: summary (tóm tắt) hoặc một trong 4 cột section của core.jobs '
  '(description, requirements, preferred, benefits).';

-- 4. Toàn văn JD trước khi tách section --------------------------------------------
alter table core.jobs add column if not exists jd_text text;

comment on column core.jobs.jd_text is
  'Toàn văn JD đã bỏ HTML và che email/SĐT, do crawler ghi. Bước tách section '
  '(skillkit.sections) đọc cột này và ghi description / requirements / preferred / benefits.';

-- Các tin nạp trước migration này đang giữ toàn văn ở description: chuyển sang jd_text.
update core.jobs
   set jd_text = description
 where jd_text is null
   and description is not null
   and requirements is null
   and preferred is null
   and benefits is null;
