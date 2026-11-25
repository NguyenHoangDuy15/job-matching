// Việc đã lưu + lịch sử gợi ý (S4-H05 · US-17 · docs/ui/wireframe_matches.png màn 4).
// Dữ liệu: api.v_my_saved_jobs, api.save_job / api.unsave_job, api.v_my_match_history
// (db/migrations/0021_saved_jobs_match_history.sql). RLS chỉ trả dữ liệu của chính người dùng.
import { PROVINCES, provinceName } from "./jobs/provinces.ts";
import { DEFAULT_TOP_N, matchHref, MATCH_WORK_MODES, TOP_N_OPTIONS, type MatchWorkMode, type TopN } from "./match.ts";

export type SavedJobRow = {
  public_id: string;
  title: string;
  company_name: string | null;
  company_logo_url: string | null;
  valid_through: string | null;
  /** Tin còn mở và chưa quá hạn nộp. false = hiện nhãn "Đã đóng", không cho ứng tuyển. */
  is_open: boolean;
  status: string;
  closed_at: string | null;
  saved_at: string;
};

export type HistoryResult = {
  rank: number;
  public_id: string | null;
  title: string | null;
  company_name: string | null;
  score_h: number;
  k: number | null;
  m: number | null;
  e: number | null;
  x: number | null;
};

export type HistoryRow = {
  id: number;
  cv_id: string | null;
  cv_target_title: string | null;
  top_n: number | null;
  /** Đúng dạng API ghi: {"provinces": [79], "work_modes": ["remote"]}. */
  filters: { provinces?: unknown; work_modes?: unknown } | null;
  created_at: string;
  result_count: number;
  results: HistoryResult[];
};

export const SAVED_JOBS_PATH = "/viec-da-luu";

/** Lỗi api.save_job / api.unsave_job theo errcode (comment đầu migration 0021). */
export function saveErrorMessage(err: { code?: string } | null): string {
  if (err?.code === "42501") return "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại để lưu việc.";
  if (err?.code === "P0002") return "Tin này không còn trên hệ thống.";
  return "Chưa lưu được, hãy thử lại.";
}

const MODE_TEXT: Record<MatchWorkMode, string> = { onsite: "Tại văn phòng", hybrid: "Hybrid", remote: "Remote" };

/** Đọc lại lựa chọn của một lượt; giá trị lạ bị bỏ (filters là jsonb, không tin tuyệt đối). */
export function historyParams(row: Pick<HistoryRow, "cv_id" | "top_n" | "filters">) {
  const f = row.filters ?? {};
  const provinces = Array.isArray(f.provinces)
    ? f.provinces.filter((p): p is number => PROVINCES.some((x) => x.code === p))
    : [];
  const modes = Array.isArray(f.work_modes)
    ? MATCH_WORK_MODES.filter((m) => (f.work_modes as unknown[]).includes(m))
    : [];
  const topN: TopN = TOP_N_OPTIONS.includes(row.top_n as TopN) ? (row.top_n as TopN) : DEFAULT_TOP_N;
  return { cvId: row.cv_id, topN, provinces, modes };
}

/** "Chấm lại": mở Việc phù hợp với đúng CV + số việc + bộ lọc của lượt đó. */
export function historyHref(row: Pick<HistoryRow, "cv_id" | "top_n" | "filters">): string {
  return matchHref(historyParams(row));
}

/** "10 việc · Hà Nội, TP Hồ Chí Minh · Remote" hoặc "20 việc · mọi tỉnh". */
export function historyFilterText(row: Pick<HistoryRow, "cv_id" | "top_n" | "filters">): string {
  const p = historyParams(row);
  const parts = [`${p.topN} việc`, p.provinces.length ? p.provinces.map((c) => provinceName(c)).join(", ") : "mọi tỉnh"];
  if (p.modes.length) parts.push(p.modes.map((m) => MODE_TEXT[m]).join(", "));
  return parts.join(" · ");
}

/** Điểm cao nhất của một lượt (kết quả đã theo rank nên là phần tử đầu, vẫn tính max cho chắc). */
export function bestScore(row: Pick<HistoryRow, "results">): number | null {
  return row.results.length ? Math.max(...row.results.map((r) => Number(r.score_h))) : null;
}

/**
 * Điểm gần nhất của từng tin trong 10 lượt gợi ý (lượt mới nhất thắng).
 * DB không lưu "điểm lúc lưu", nên trang Việc đã lưu hiện điểm này, không có thì "—".
 */
export function latestScores(history: Pick<HistoryRow, "created_at" | "results">[]): Map<string, number> {
  const scores = new Map<string, number>();
  const newestFirst = [...history].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  for (const row of newestFirst) {
    for (const r of row.results) {
      if (r.public_id && !scores.has(r.public_id)) scores.set(r.public_id, Number(r.score_h));
    }
  }
  return scores;
}
