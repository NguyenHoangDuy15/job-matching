// Tham số tìm việc gửi cho rpc api.search_jobs. S2-H02 mới đọc từ khóa ?q= trên URL;
// bộ lọc tỉnh, lương, hình thức, cấp bậc và phân trang đọc từ URL ở S2-H03.

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

export const PAGE_SIZE = 20;
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

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Đọc URL → tham số tìm việc. */
export function parseFilters(params: RawParams): JobFilters {
  return { ...EMPTY_FILTERS, q: first(params["q"]).trim().slice(0, MAX_Q) };
}
