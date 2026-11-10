-- =====================================================================================
--  Migration 0004 — Mức kỹ năng required / preferred / mentioned (S2-D04, US-10)
--  Bổ sung cột cho core.job_skills (bảng đã có từ 0001), không tạo bảng mới.
--  Chạy lại nhiều lần được.
--
--  Quy ước ghi (skillkit.levels.db):
--  - extractor: 'dict' = luật trên từ điển, 'jev' = Tầng 2 quyết, 'human' = sửa tay.
--  - Chạy lại pipeline KHÔNG ghi đè và KHÔNG xóa dòng extractor = 'human'.
-- =====================================================================================

alter table core.job_skills
  add column if not exists section       text,
  add column if not exists source_detail text,
  add column if not exists mention_count smallint not null default 1,
  add column if not exists model_version text,
  add column if not exists labeled_at    timestamptz not null default now();

alter table core.job_skills drop constraint if exists job_skills_section_check;
alter table core.job_skills add constraint job_skills_section_check
  check (section in ('description', 'requirements', 'preferred', 'none'));

alter table core.job_skills drop constraint if exists job_skills_confidence_check;
alter table core.job_skills add constraint job_skills_confidence_check
  check (confidence is null or confidence between 0 and 1);

comment on column core.job_skills.level is
  'required = bắt buộc, preferred = ưu tiên, mentioned = chỉ được nhắc trong mô tả công việc.';
comment on column core.job_skills.section is
  'Section theo heading gốc của câu bằng chứng; none = JD không có heading.';
comment on column core.job_skills.source_detail is
  'Luật/tầng đã quyết: rule_neg, rule_section, rule_cue, rule_mixed, rule_desc, model, fallback.';
comment on column core.job_skills.mention_count is 'Số lần kỹ năng được nhắc trong JD.';
comment on column core.job_skills.model_version is 'Ví dụ dict+rules-v1+jev_local_v1.';
