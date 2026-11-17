-- =====================================================================================
--  Migration 0011 — Khử trùng chính xác: tin nguồn → tin chuẩn (S3-T03, US-14)
--  1. core.job_sources.url_norm: URL tin đăng đã chuẩn hóa (ingestion.dedup.canonical_url)
--  2. core.jobs.content_hash đổi nghĩa: dedup hash so được GIỮA các nguồn
--     (chức danh + công ty + tỉnh + mô tả đã chuẩn hóa). Hash nội dung của từng nguồn vẫn ở
--     core.job_sources.last_content_hash. Tin cũ: chạy scripts/dedup_exact.py --apply.
--  3. core.jobs.duplicate_of: tin bị gộp trỏ về tin giữ lại (web có thể chuyển hướng)
--  4. core.merge_jobs(keep, dup): gộp hai tin chuẩn — dùng chung cho S3-T03 (trùng chính xác),
--     S3-T04 (gần trùng ≥ 0,85) và admin duyệt hàng chờ (api.admin_resolve_dedup)
--  Chạy lại nhiều lần được. Cần 0004.
-- =====================================================================================

-- 1. URL chuẩn hóa ------------------------------------------------------------------------
alter table core.job_sources add column if not exists url_norm text;
create index if not exists job_sources_url_norm_idx on core.job_sources (url_norm)
  where url_norm is not null;
comment on column core.job_sources.url_norm is
  'URL tin đăng dạng chuẩn (https, host thường bỏ www., bỏ query/fragment/dấu / thừa). '
  'Cùng url_norm = cùng một tin đăng dù mã tin khác.';

-- 2. Dedup hash -----------------------------------------------------------------------------
comment on column core.jobs.content_hash is
  'Dedup hash (ingestion.dedup.dedup_hash): SHA-256 của chức danh + công ty + tỉnh + mô tả đã '
  'chuẩn hóa. null khi mô tả quá ngắn. Hash nội dung từng nguồn: core.job_sources.last_content_hash.';
create index if not exists jobs_open_content_hash_idx on core.jobs (content_hash)
  where origin = 'crawled' and status = 'open' and content_hash is not null;

-- 3. Tin bị gộp trỏ về tin giữ lại --------------------------------------------------------
alter table core.jobs
  add column if not exists duplicate_of bigint references core.jobs (id) on delete set null;
do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'jobs_duplicate_not_self' and conrelid = 'core.jobs'::regclass
  ) then
    alter table core.jobs add constraint jobs_duplicate_not_self check (duplicate_of <> id);
  end if;
end $$;
create index if not exists jobs_duplicate_of_idx on core.jobs (duplicate_of)
  where duplicate_of is not null;
comment on column core.jobs.duplicate_of is
  'Tin này đã được gộp vào tin duplicate_of (status closed, close_reason duplicate).';

-- 4. Gộp hai tin chuẩn ---------------------------------------------------------------------
-- Giữ p_keep, đóng p_dup (KHÔNG xóa: tin đã lưu, kết quả matching, nhãn đánh giá vẫn trỏ được).
--   - mọi nguồn của p_dup chuyển sang p_keep; tin đã lưu (app.saved_jobs) chuyển theo
--   - p_keep lấy first_seen_at sớm nhất, last_seen_at muộn nhất
--   - p_keep đang đóng vì gone/missing mà vẫn còn nguồn hoạt động thì mở lại
--   - cặp nghi trùng của p_dup: với p_keep → 'merged'; với tin khác → xóa (lượt sau tính lại)
-- p_keep đã bị gộp vào tin khác thì gộp vào tin gốc đó. Trả id tin giữ lại.
create or replace function core.merge_jobs(p_keep bigint, p_dup bigint)
returns bigint
language plpgsql set search_path = '' as $$
declare
  v_keep bigint := p_keep;
  v_root bigint;
begin
  select j.duplicate_of into v_root from core.jobs j where j.id = v_keep;
  if not found then
    raise exception 'job % not found', p_keep using errcode = 'P0002';
  end if;
  v_keep := coalesce(v_root, v_keep);
  if v_keep = p_dup then
    return v_keep;
  end if;

  -- Khóa theo thứ tự id để hai lần gộp song song không deadlock
  perform 1 from core.jobs j where j.id in (v_keep, p_dup) order by j.id for update;
  if not exists (select 1 from core.jobs j where j.id = p_dup) then
    raise exception 'job % not found', p_dup using errcode = 'P0002';
  end if;

  update core.job_sources s set job_id = v_keep where s.job_id = p_dup;

  insert into app.saved_jobs (user_id, job_id, saved_at)
  select sj.user_id, v_keep, sj.saved_at from app.saved_jobs sj where sj.job_id = p_dup
  on conflict (user_id, job_id) do nothing;
  delete from app.saved_jobs sj where sj.job_id = p_dup;

  update core.dedup_candidates c
     set status = 'merged', reviewed_at = coalesce(c.reviewed_at, now())
   where c.job_a = least(v_keep, p_dup) and c.job_b = greatest(v_keep, p_dup)
     and c.status = 'pending';
  delete from core.dedup_candidates c
   where c.status = 'pending' and p_dup in (c.job_a, c.job_b);

  update core.jobs k
     set first_seen_at = least(k.first_seen_at, d.first_seen_at),
         last_seen_at  = greatest(k.last_seen_at, d.last_seen_at),
         missed_runs   = least(k.missed_runs, d.missed_runs),
         updated_at    = now()
    from core.jobs d
   where k.id = v_keep and d.id = p_dup;

  update core.jobs k
     set status = 'open', closed_at = null, close_reason = null
   where k.id = v_keep and k.status = 'closed' and k.close_reason in ('gone', 'missing')
     and exists (select 1 from core.job_sources s where s.job_id = k.id and s.is_active);

  update core.jobs j
     set status = 'closed', close_reason = 'duplicate', closed_at = coalesce(j.closed_at, now()),
         duplicate_of = v_keep, updated_at = now()
   where j.id = p_dup;
  -- Tin từng gộp vào p_dup giờ trỏ thẳng về tin giữ lại (không để chuỗi)
  update core.jobs j set duplicate_of = v_keep where j.duplicate_of = p_dup;

  return v_keep;
end $$;

revoke execute on function core.merge_jobs(bigint, bigint) from public, anon, authenticated;

-- Admin duyệt hàng chờ: gộp bằng cùng hàm, tin nhỏ id hơn được giữ ------------------------
create or replace function api.admin_resolve_dedup(
  p_job_a    bigint,
  p_job_b    bigint,
  p_decision text
) returns void language plpgsql security definer set search_path = '' as $$
declare
  v_a bigint := least(p_job_a, p_job_b);
  v_b bigint := greatest(p_job_a, p_job_b);
begin
  if app.jwt_role() <> 'admin' or not app.is_active_user() then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  if p_decision not in ('merged', 'distinct') then
    raise exception 'decision must be merged or distinct' using errcode = '22023';
  end if;

  update core.dedup_candidates
     set status = p_decision, reviewed_by = auth.uid(), reviewed_at = now()
   where job_a = v_a and job_b = v_b;

  if p_decision = 'merged' then
    perform core.merge_jobs(v_a, v_b);
  end if;

  insert into app.audit_log (actor_id, actor_role, action, entity, entity_id, detail)
  values (auth.uid(), 'admin', 'dedup_resolved', 'dedup', v_a || ':' || v_b,
          jsonb_build_object('job_a', v_a, 'job_b', v_b, 'decision', p_decision));
end $$;
