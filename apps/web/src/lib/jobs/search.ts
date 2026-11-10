import { createClient } from "@/lib/supabase/server";
import { PAGE_SIZE, type JobFilters, type Level, type WorkMode } from "./filters";

/** Một dòng trả về từ rpc api.search_jobs (db/migrations/0001_schema_v2.sql). */
type SearchRow = {
  public_id: string;
  title: string;
  company: string | null;
  salary_min_vnd: number | null;
  salary_max_vnd: number | null;
  salary_raw: string | null;
  work_mode: WorkMode;
  valid_through: string | null;
  apply_url: string | null;
  last_seen_at: string;
  rank: number;
};

/** Các cột search_jobs chưa trả, lấy thêm từ view api.v_open_jobs. */
type ExtraRow = {
  public_id: string;
  seniority: Level;
  source_count: number;
  is_expiring_soon: boolean;
};

export type JobItem = SearchRow & {
  seniority: Level;
  source_count: number;
  is_expiring_soon: boolean | null; // null = không lấy được từ view, trang tự tính
};

export type SearchResult = {
  jobs: JobItem[];
  /** Tổng số việc khớp. null khi có từ khóa hoặc lọc tỉnh: search_jobs chưa trả tổng. */
  total: number | null;
  hasNext: boolean;
  ms: number;
};

/**
 * Tìm việc cho trang /viec-lam (S2-H02): rpc api.search_jobs, rồi bổ sung cấp bậc,
 * số trang nguồn từ api.v_open_jobs. Lỗi DB thì ném ra để trang hiện "Thử lại".
 */
export async function searchJobs(f: JobFilters): Promise<SearchResult> {
  const started = performance.now();
  const supabase = await createClient();
  const api = supabase.schema("api");

  const search = api.rpc("search_jobs", {
    q: f.q || null,
    provinces: f.provinces.length ? f.provinces : null,
    skills: null, // lọc kỹ năng: chờ API tra skill_id (schema `ref` chưa mở cho web)
    salary_min: f.salaryMin,
    modes: f.modes.length ? f.modes : null,
    levels: f.levels.length ? f.levels : null,
    page: f.page,
    page_size: PAGE_SIZE,
  });

  // Đếm tổng được khi bộ lọc chỉ dùng cột có trong view (không từ khóa, không tỉnh).
  const canCount = !f.q && f.provinces.length === 0;
  const count = canCount ? countOpenJobs(api, f) : Promise.resolve(null);

  const [{ data, error }, total] = await Promise.all([search, count]);
  if (error) throw new Error(`search_jobs: ${error.message}`);
  const rows = (data ?? []) as SearchRow[];

  const extras = new Map<string, ExtraRow>();
  if (rows.length) {
    const { data: extra } = await api
      .from("v_open_jobs")
      .select("public_id, seniority, source_count, is_expiring_soon")
      .in(
        "public_id",
        rows.map((r) => r.public_id),
      );
    for (const e of (extra ?? []) as ExtraRow[]) extras.set(e.public_id, e);
  }

  const jobs: JobItem[] = rows.map((r) => {
    const e = extras.get(r.public_id);
    return {
      ...r,
      seniority: e?.seniority ?? "unknown",
      source_count: e?.source_count ?? 1,
      is_expiring_soon: e?.is_expiring_soon ?? null,
    };
  });

  return {
    jobs,
    total,
    hasNext: total !== null ? f.page * PAGE_SIZE < total : rows.length === PAGE_SIZE,
    ms: Math.round(performance.now() - started),
  };
}

type ApiSchema = ReturnType<Awaited<ReturnType<typeof createClient>>["schema"]>;

async function countOpenJobs(api: ApiSchema, f: JobFilters): Promise<number | null> {
  let query = api.from("v_open_jobs").select("id", { count: "exact", head: true });
  if (f.modes.length) query = query.in("work_mode", f.modes);
  if (f.levels.length) query = query.in("seniority", f.levels);
  if (f.salaryMin) query = query.gte("salary_max_vnd", f.salaryMin);
  const { count, error } = await query;
  return error ? null : count;
}
