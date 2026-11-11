import { createClient } from "@/lib/supabase/server";
import type { Level, WorkMode } from "./filters";

/** Một dòng của api.v_job_detail (db/migrations/0007_job_detail_api.sql). */
export type JobDetail = {
  public_id: string;
  title: string;
  company_name: string | null;
  company_logo_url: string | null;
  company_website: string | null;
  job_family_name: string | null;
  seniority: Level;
  work_mode: WorkMode;
  employment_type: string | null;
  years_exp_min: number | null;
  salary_raw: string | null;
  salary_min_vnd: number | null;
  salary_max_vnd: number | null;
  salary_is_negotiable: boolean;
  description: string | null;
  requirements: string | null;
  preferred: string | null;
  benefits: string | null;
  jd_text: string | null;
  posted_at: string | null;
  valid_through: string | null;
  is_expiring_soon: boolean;
  first_seen_at: string;
  last_seen_at: string;
  apply_url: string | null;
  provinces: string[];
  sources: { url: string; last_seen_at: string }[];
  source_count: number;
};

export type JobSkill = {
  skill_slug: string;
  skill_name: string;
  level: "required" | "preferred";
  confidence: number | null;
};

export type JobDetailResult = {
  job: JobDetail;
  skills: JobSkill[];
  /** false = đang chạy bản dự phòng (chưa có view 0007): thiếu mô tả, tỉnh, link nguồn. */
  complete: boolean;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isPublicId(id: string): boolean {
  return UUID.test(id);
}

// PostgREST báo "chưa có bảng/view" bằng mã này (vd chưa chạy migration 0007).
const MISSING_RELATION = "PGRST205";

/**
 * Chi tiết một tin đang mở theo public_id (S2-H04). null = không có hoặc đã đóng/hết hạn.
 * Lỗi kết nối DB thì ném ra để trang hiện "Thử lại".
 */
export async function getJobDetail(publicId: string): Promise<JobDetailResult | null> {
  if (!isPublicId(publicId)) return null;
  const api = (await createClient()).schema("api");

  const skillsQuery = api
    .from("v_job_skills")
    .select("skill_slug, skill_name, level, confidence")
    .eq("job_public_id", publicId)
    .order("level")
    .order("confidence", { ascending: false, nullsFirst: false });

  const [detail, skillsRes] = await Promise.all([
    api.from("v_job_detail").select("*").eq("public_id", publicId).maybeSingle(),
    skillsQuery,
  ]);
  // Thiếu thẻ kỹ năng không làm hỏng trang: hiện phần còn lại.
  const skills = skillsRes.error ? [] : ((skillsRes.data ?? []) as JobSkill[]);

  if (!detail.error) {
    if (!detail.data) return null;
    const job = detail.data as Omit<JobDetail, "source_count">;
    return { job: { ...job, source_count: Math.max(job.sources.length, 1) }, skills, complete: true };
  }
  if (detail.error.code !== MISSING_RELATION) throw new Error(`v_job_detail: ${detail.error.message}`);

  // Dự phòng khi Supabase chưa có view 0007: lấy phần có trong api.v_open_jobs.
  const open = await api.from("v_open_jobs").select("*").eq("public_id", publicId).maybeSingle();
  if (open.error) throw new Error(`v_open_jobs: ${open.error.message}`);
  if (!open.data) return null;
  const row = open.data as Record<string, unknown>;
  return {
    job: {
      ...(row as Omit<JobDetail, "company_website" | "employment_type" | "description" | "requirements" | "preferred" | "benefits" | "jd_text" | "provinces" | "sources">),
      company_website: null,
      employment_type: null,
      description: null,
      requirements: null,
      preferred: null,
      benefits: null,
      jd_text: null,
      provinces: [],
      sources: [],
      source_count: Number(row.source_count ?? 1),
    },
    skills,
    complete: false,
  };
}

export type JdSection = { key: string; title: string; text: string };

/**
 * 4 section JD để hiện. Chưa tách được section nào thì hiện toàn văn trong "Mô tả công việc"
 * (wireframe: "Tin không tách được 3 phần: hiện toàn văn trong Mô tả").
 */
export function jdSections(job: JobDetail): JdSection[] {
  const sections: JdSection[] = [
    { key: "description", title: "Mô tả công việc", text: job.description ?? "" },
    { key: "requirements", title: "Yêu cầu", text: job.requirements ?? "" },
    { key: "preferred", title: "Ưu tiên", text: job.preferred ?? "" },
    { key: "benefits", title: "Quyền lợi", text: job.benefits ?? "" },
  ].filter((s) => s.text.trim() !== "");
  if (sections.length === 0 && job.jd_text?.trim()) {
    return [{ key: "description", title: "Mô tả công việc", text: job.jd_text }];
  }
  return sections;
}
