// Lịch sử crawl cho trang /admin/crawl-runs (S4-T03, US-18). Hàm thuần, chạy được cả server lẫn `node --test`.
// Nguồn: api.v_admin_crawl_runs (migration 0018) = ops.crawl_runs + ops.sources + ops.quality_reports.
// Supabase trả cột numeric dưới dạng chuỗi, nên các số đo để kiểu `number | string`.

export type RunStatus = "running" | "success" | "partial" | "failed";
export type RunType = "daily" | "hourly" | "manual" | "backfill";
type Num = number | string | null;

export type CrawlRunRow = {
  id: number | string;
  source_id: number;
  source_code: string;
  source_name: string;
  run_type: RunType;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  duration_s: Num;
  pages_fetched: number | null;
  items_seen: number | null;
  items_new: number | null;
  items_updated: number | null;
  items_closed: number | null;
  http_errors: number | null;
  error_sample: string | null;
  completeness: Num;
  validity: Num;
  uniqueness: Num;
  salary_parsed_pct: Num;
  province_parsed_pct: Num;
  schema_errors: number | null;
  freshness_hours: Num;
  quality_details: unknown;
};

export const CRAWL_RUN_COLUMNS =
  "id, source_id, source_code, source_name, run_type, status, started_at, finished_at, duration_s, " +
  "pages_fetched, items_seen, items_new, items_updated, items_closed, http_errors, error_sample, " +
  "completeness, validity, uniqueness, salary_parsed_pct, province_parsed_pct, schema_errors, " +
  "freshness_hours, quality_details";

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  running: "Đang chạy",
  success: "Thành công",
  partial: "Một phần",
  failed: "Thất bại",
};

/** Màu nhãn trạng thái: đỏ = thất bại, vàng = một phần, xanh = thành công. */
export const RUN_STATUS_CLASS: Record<RunStatus, string> = {
  running: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  success: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  partial: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

export const RUN_TYPE_LABEL: Record<RunType, string> = {
  daily: "Hằng ngày",
  hourly: "Hằng giờ",
  manual: "Chạy tay",
  backfill: "Bù dữ liệu",
};

/** Chuỗi/number từ Supabase → number; null hoặc không phải số → null. */
export function toNumber(v: Num | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Thời lượng một lần chạy. null (chưa có finished_at) → "Đang chạy". */
export function formatDuration(seconds: Num): string {
  const s = toNumber(seconds);
  if (s === null) return "Đang chạy";
  const total = Math.max(0, Math.round(s));
  if (total < 60) return `${total} giây`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h} giờ ${m} phút`;
  return sec > 0 ? `${m} phút ${sec} giây` : `${m} phút`;
}

const DATE_TIME = new Intl.DateTimeFormat("vi-VN", {
  timeZone: "Asia/Ho_Chi_Minh",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Mốc thời gian theo giờ Việt Nam, dạng "dd/MM/yyyy HH:mm". */
export function formatDateTimeVN(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = Object.fromEntries(DATE_TIME.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}`;
}

/** Tỉ lệ 0–1 (numeric(5,4)) → "93,5%". null → "—". */
export function formatPct(fraction: Num): string {
  const f = toNumber(fraction);
  if (f === null) return "—";
  const pct = Math.round(f * 1000) / 10;
  return `${pct.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`;
}

/** Lần chạy có gì để xem trong phần lỗi: thất bại/một phần, có lỗi HTTP, lỗi schema hoặc mẫu lỗi. */
export function hasError(run: Pick<CrawlRunRow, "status" | "http_errors" | "schema_errors" | "error_sample">): boolean {
  return (
    run.status === "failed" ||
    run.status === "partial" ||
    (run.http_errors ?? 0) > 0 ||
    (run.schema_errors ?? 0) > 0 ||
    Boolean(run.error_sample?.trim())
  );
}

/** quality_details (jsonb) → chuỗi JSON dễ đọc; rỗng/null → null để khỏi hiện khối trống. */
export function formatDetails(details: unknown): string | null {
  if (details === null || details === undefined) return null;
  if (typeof details === "object" && Object.keys(details as object).length === 0) return null;
  return JSON.stringify(details, null, 2);
}
