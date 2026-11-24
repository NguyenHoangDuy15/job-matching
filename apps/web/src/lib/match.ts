// Trang "Việc phù hợp với tôi" (S4-H01, US-16). Hàm thuần, chạy được cả server, trình duyệt lẫn `node --test`.
// Contract: docs/api/match-jobs.md · schema chuẩn src/api/match.py (MatchRequest, MatchResponse).
// Lựa chọn nằm trên URL: /viec-phu-hop?cv=<uuid>&n=10&tinh=1,79&hinh-thuc=remote
import { isProvinceCode } from "./jobs/provinces.ts";

export const TOP_N_OPTIONS = [5, 10, 20, 50] as const;
export type TopN = (typeof TOP_N_OPTIONS)[number];
export const DEFAULT_TOP_N: TopN = 10;

export const MATCH_WORK_MODES = ["onsite", "hybrid", "remote"] as const;
export type MatchWorkMode = (typeof MATCH_WORK_MODES)[number];

// ---- Contract POST /match/jobs ----

export type MatchRequest = {
  cv_id: string;
  top_n: TopN;
  filters: { provinces: number[]; work_modes: MatchWorkMode[] };
};

export type ComponentKey = "K" | "M" | "E" | "X";
/** 0–1; null = không xác định (tin không ghi kỹ năng / số năm…). */
export type Components = Record<ComponentKey, number | null>;

export type SkillMatched = {
  skill_id: string;
  skill: string;
  level: "required" | "preferred";
  via: string | null;
  relation: "exact" | "child" | "parent_only" | "sibling";
  evidence: "strong" | "listed" | "user_added" | null;
};

export type SkillMissing = { skill_id: string; skill: string; level: "required" | "preferred" };

export type MatchResult = {
  rank: number;
  job_id: number;
  public_id: string | null;
  title: string;
  company: string | null;
  provinces: string[];
  work_mode: string; // onsite | hybrid | remote | unknown
  valid_through: string | null; // "2026-12-11"
  apply_url: string | null;
  score: number; // 0–100, 1 chữ số thập phân
  components: Components;
  weights_used: Partial<Record<ComponentKey, number>>;
  skills_matched: SkillMatched[];
  skills_missing: SkillMissing[];
  explanation: string;
};

export type MatchResponse = {
  request_id: number | null;
  cv_id: string;
  top_n: number;
  engine_version: string;
  corpus_size: number;
  candidates: number;
  latency_ms: number;
  note: string;
  results: MatchResult[];
};

// ---- Công thức (config/ranker_config.yaml) ----

export const BASE_WEIGHTS: Record<ComponentKey, number> = { K: 0.25, M: 0.35, E: 0.3, X: 0.1 };

/** Bỏ thành phần null rồi chia lại trọng số cho tổng = 1 (giống weights_used của API). */
export function weightsFor(components: Components): Partial<Record<ComponentKey, number>> {
  const keys = (Object.keys(BASE_WEIGHTS) as ComponentKey[]).filter((k) => components[k] != null);
  const total = keys.reduce((sum, k) => sum + BASE_WEIGHTS[k], 0);
  return Object.fromEntries(keys.map((k) => [k, total ? BASE_WEIGHTS[k] / total : 0]));
}

/** H = 100 × Σ wᵢ·xᵢ trên thành phần xác định, làm tròn 1 chữ số. */
export function scoreOf(components: Components): number {
  const weights = weightsFor(components);
  const sum = (Object.keys(weights) as ComponentKey[]).reduce(
    (acc, k) => acc + (weights[k] ?? 0) * (components[k] ?? 0),
    0,
  );
  return Math.round(sum * 1000) / 10;
}

// ---- Hiển thị thẻ kết quả (S4-H02, docs/ui/wireframe_matches.png màn 1–2) ----

export const COMPONENT_KEYS: ComponentKey[] = ["K", "M", "E", "X"];

export const COMPONENT_INFO: Record<ComponentKey, { label: string; meaning: string }> = {
  K: { label: "Từ khóa", meaning: "CV có nhắc tới những từ quan trọng trong tin" },
  M: {
    label: "Kỹ năng",
    meaning: "Kỹ năng tin yêu cầu mà CV thể hiện; bắt buộc tính nặng hơn ưu tiên, có bằng chứng nặng hơn chỉ liệt kê",
  },
  E: { label: "Ngữ nghĩa", meaning: "Nội dung CV gần với nội dung tin tới mức nào (so bằng mô hình ngôn ngữ)" },
  X: { label: "Kinh nghiệm", meaning: "Số năm kinh nghiệm trong CV so với số năm tin yêu cầu" },
};

/** Số kiểu Việt Nam: 0,9 → "0,90"; 86 → "86,0". */
export function numberVi(n: number, digits: number): string {
  return n.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Trọng số dùng cho thẻ: lấy weights_used của API; thiếu thì tự chia lại từ components. */
export function displayWeights(r: Pick<MatchResult, "components" | "weights_used">): Partial<Record<ComponentKey, number>> {
  const used = COMPONENT_KEYS.filter((k) => r.components[k] != null && typeof r.weights_used[k] === "number");
  return used.length ? Object.fromEntries(used.map((k) => [k, r.weights_used[k] as number])) : weightsFor(r.components);
}

/** "100 × (0,28 × K + 0,39 × M + 0,33 × E)": công thức cho popover "Điểm tính thế nào?". */
export function formulaText(weights: Partial<Record<ComponentKey, number>>): string {
  const terms = COMPONENT_KEYS.filter((k) => weights[k] != null).map((k) => `${numberVi(weights[k] as number, 2)} × ${k}`);
  return `100 × (${terms.join(" + ")})`;
}

/** Tên chip kỹ năng khớp: "Spark (qua PySpark)" khi khớp qua kỹ năng liên quan. */
export function matchedLabel(s: Pick<SkillMatched, "skill" | "via">): string {
  return s.via ? `${s.skill} (qua ${s.via})` : s.skill;
}

/** Bắt buộc trước ưu tiên, giữ thứ tự API trong cùng mức. */
export function byLevel<T extends { level: "required" | "preferred" }>(skills: T[]): T[] {
  return [...skills.filter((s) => s.level === "required"), ...skills.filter((s) => s.level === "preferred")];
}

// ---- URL ----

export type MatchParams = {
  cvId: string | null;
  topN: TopN;
  provinces: number[];
  modes: MatchWorkMode[];
};

type RawParams = Record<string, string | string[] | undefined>;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

function list(value: string | string[] | undefined): string[] {
  const parts = Array.isArray(value) ? value : value ? [value] : [];
  return [...new Set(parts.flatMap((p) => p.split(",")).map((p) => p.trim()).filter(Boolean))];
}

/** Đọc URL → lựa chọn hợp lệ. Giá trị lạ bị bỏ qua thay vì làm lỗi trang. */
export function parseMatchParams(params: RawParams): MatchParams {
  const cv = first(params["cv"]).trim();
  const n = Number(first(params["n"]));
  return {
    cvId: UUID_RE.test(cv) ? cv.toLowerCase() : null,
    topN: (TOP_N_OPTIONS as readonly number[]).includes(n) ? (n as TopN) : DEFAULT_TOP_N,
    provinces: list(params["tinh"])
      .map(Number)
      .filter((c) => Number.isInteger(c) && isProvinceCode(c))
      .sort((a, b) => a - b),
    modes: MATCH_WORK_MODES.filter((m) => list(params["hinh-thuc"]).includes(m)),
  };
}

/** Lựa chọn → "/viec-phu-hop?cv=…&n=20&tinh=1,79". Bỏ giá trị mặc định. */
export function matchHref(p: MatchParams): string {
  const parts: string[] = [];
  if (p.cvId) parts.push(`cv=${p.cvId}`);
  if (p.topN !== DEFAULT_TOP_N) parts.push(`n=${p.topN}`);
  if (p.provinces.length) parts.push(`tinh=${[...p.provinces].sort((a, b) => a - b).join(",")}`);
  const modes = MATCH_WORK_MODES.filter((m) => p.modes.includes(m));
  if (modes.length) parts.push(`hinh-thuc=${modes.join(",")}`);
  return `/viec-phu-hop${parts.length ? `?${parts.join("&")}` : ""}`;
}

export function toMatchRequest(p: MatchParams, cvId: string): MatchRequest {
  return { cv_id: cvId, top_n: p.topN, filters: { provinces: p.provinces, work_modes: p.modes } };
}

// ---- Chọn CV ----

export type MatchCv = {
  id: string;
  label: string;
  is_primary: boolean;
  created_at: string;
  parse_status: string;
  confirmed: boolean;
};

/** Chỉ CV đã đọc xong mới chấm được (API trả 409 cv_not_parsed với CV khác). CV chính trước, rồi mới nhất. */
export function matchableCvs<T extends Pick<MatchCv, "parse_status" | "is_primary" | "created_at">>(cvs: T[]): T[] {
  return cvs
    .filter((c) => c.parse_status === "parsed")
    .sort((a, b) => Number(b.is_primary) - Number(a.is_primary) || b.created_at.localeCompare(a.created_at));
}

/** CV trên URL nếu chấm được; không thì CV chính; không có CV chính thì CV mới nhất. */
export function pickCv<T extends Pick<MatchCv, "id">>(matchable: T[], requested: string | null): T | null {
  return matchable.find((c) => c.id === requested) ?? matchable[0] ?? null;
}
