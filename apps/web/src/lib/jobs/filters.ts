import { isProvinceCode } from "./provinces";

// Bộ lọc trang /viec-lam nằm hết trên URL (US-05/AC3): tải lại trang hay gửi link vẫn giữ.
// /viec-lam?q=java&tinh=1,79&luong=20000000&hinh-thuc=hybrid,remote&cap-bac=junior&trang=2

export const WORK_MODES = ["onsite", "hybrid", "remote"] as const;
export const LEVELS = ["intern", "fresher", "junior", "middle", "senior", "lead", "manager"] as const;
export type WorkMode = (typeof WORK_MODES)[number] | "unknown";
export type Level = (typeof LEVELS)[number] | "unknown";

export const WORK_MODE_LABEL: Record<WorkMode, string> = {
  onsite: "Tại văn phòng",
  hybrid: "Hybrid",
  remote: "Remote",
  unknown: "Chưa rõ hình thức",
};

export const LEVEL_LABEL: Record<Level, string> = {
  intern: "Intern",
  fresher: "Fresher",
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
  lead: "Lead",
  manager: "Manager",
  unknown: "Chưa rõ cấp bậc",
};

/** Mốc lương tối thiểu (VND/tháng). */
export const SALARY_STEPS = [10_000_000, 20_000_000, 30_000_000, 50_000_000];

export const PAGE_SIZE = 20;
const MAX_PAGE = 500;
const MAX_Q = 100;

export type JobFilters = {
  q: string;
  provinces: number[];
  salaryMin: number | null;
  modes: WorkMode[];
  levels: Level[];
  page: number;
};

export const EMPTY_FILTERS: JobFilters = {
  q: "",
  provinces: [],
  salaryMin: null,
  modes: [],
  levels: [],
  page: 1,
};

type RawParams = Record<string, string | string[] | undefined>;

/** Nhận cả "a,b" lẫn "?x=a&x=b" (form GET không JS gửi kiểu thứ hai). */
function list(value: string | string[] | undefined): string[] {
  const parts = Array.isArray(value) ? value : value ? [value] : [];
  return [...new Set(parts.flatMap((p) => p.split(",")).map((p) => p.trim()).filter(Boolean))];
}

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

function pick<T extends string>(values: string[], allowed: readonly T[]): T[] {
  return values.filter((v): v is T => (allowed as readonly string[]).includes(v));
}

/** Đọc URL → bộ lọc hợp lệ. Giá trị lạ bị bỏ qua thay vì làm lỗi trang. */
export function parseFilters(params: RawParams): JobFilters {
  const salary = Number(first(params["luong"]));
  const page = Number.parseInt(first(params["trang"]), 10);
  return {
    q: first(params["q"]).trim().slice(0, MAX_Q),
    provinces: list(params["tinh"])
      .map(Number)
      .filter((c) => Number.isInteger(c) && isProvinceCode(c)),
    salaryMin: Number.isFinite(salary) && salary > 0 ? Math.round(salary) : null,
    modes: pick(list(params["hinh-thuc"]), WORK_MODES),
    levels: pick(list(params["cap-bac"]), LEVELS),
    page: Number.isInteger(page) && page > 1 ? Math.min(page, MAX_PAGE) : 1,
  };
}

/** Bộ lọc → "?q=…&tinh=1,79". Bỏ giá trị mặc định; giữ dấu phẩy cho URL dễ đọc. */
export function toQueryString(f: JobFilters): string {
  const parts: string[] = [];
  const add = (key: string, values: (string | number)[]) => {
    if (values.length) parts.push(`${key}=${values.map((v) => encodeURIComponent(v)).join(",")}`);
  };
  if (f.q) parts.push(`q=${encodeURIComponent(f.q).replace(/%20/g, "+")}`);
  add("tinh", [...f.provinces].sort((a, b) => a - b));
  if (f.salaryMin) parts.push(`luong=${f.salaryMin}`);
  add("hinh-thuc", WORK_MODES.filter((m) => f.modes.includes(m)));
  add("cap-bac", LEVELS.filter((l) => f.levels.includes(l)));
  if (f.page > 1) parts.push(`trang=${f.page}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

export function jobsHref(f: JobFilters): string {
  return `/viec-lam${toQueryString(f)}`;
}

/** Có bộ lọc nào ngoài từ khóa và số trang không. */
export function hasFilters(f: JobFilters): boolean {
  return f.provinces.length > 0 || f.salaryMin !== null || f.modes.length > 0 || f.levels.length > 0;
}

/** "20 tr", "1,5 tr". */
export function formatMillion(vnd: number): string {
  return `${(vnd / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tr`;
}
