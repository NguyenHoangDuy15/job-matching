// Báo cáo chất lượng dữ liệu mỗi lượt crawl (S4-T05, US-19). Hàm thuần, chạy được cả server lẫn `node --test`.
// Nguồn: api.v_admin_crawl_runs (migration 0018), phần cột lấy từ ops.quality_reports.
// Tỉ lệ là phân số 0–1 (numeric(5,4)), Supabase trả về dạng chuỗi.

import { type RunStatus, toNumber } from "./crawl-runs.ts";

type Num = number | string | null;

export type QualityReportRow = {
  source_id: number;
  source_code: string;
  source_name: string;
  status: RunStatus;
  started_at: string;
  completeness: Num;
  validity: Num;
  uniqueness: Num;
  salary_parsed_pct: Num;
  province_parsed_pct: Num;
  schema_errors: number | null;
  freshness_hours: Num;
};

export const QUALITY_REPORT_COLUMNS =
  "source_id, source_code, source_name, status, started_at, completeness, validity, uniqueness, " +
  "salary_parsed_pct, province_parsed_pct, schema_errors, freshness_hours";

export type QualityMetric = "completeness" | "validity" | "uniqueness" | "salary_parsed_pct" | "province_parsed_pct";

/** Ngưỡng tô đỏ: tỉ lệ dưới ngưỡng là đáng xem lại. */
export const QUALITY_THRESHOLDS: Record<QualityMetric, number> = {
  completeness: 0.8,
  validity: 0.95,
  uniqueness: 0.5,
  salary_parsed_pct: 0.5,
  province_parsed_pct: 0.8,
};

/** Tin mới nhất cũ hơn ngần này giờ thì coi là nguồn đứng. */
export const FRESHNESS_WARN_HOURS = 48;

/** Lần chạy gần nhất có báo cáo của mỗi nguồn. `rows` đã sắp started_at giảm dần. */
export function latestReportPerSource(rows: QualityReportRow[]): QualityReportRow[] {
  const seen = new Map<number, QualityReportRow>();
  for (const r of rows) if (!seen.has(r.source_id)) seen.set(r.source_id, r);
  return [...seen.values()].sort((a, b) => a.source_name.localeCompare(b.source_name, "vi"));
}

export function isLowQuality(metric: QualityMetric, value: Num): boolean {
  const v = toNumber(value);
  return v !== null && v < QUALITY_THRESHOLDS[metric];
}

export function isStale(hours: Num): boolean {
  const h = toNumber(hours);
  return h !== null && h > FRESHNESS_WARN_HOURS;
}

/** Độ mới: "34 giờ" dưới 48 giờ, từ đó trở lên "3 ngày". null → "—". */
export function formatFreshness(hours: Num): string {
  const h = toNumber(hours);
  if (h === null) return "—";
  if (h < FRESHNESS_WARN_HOURS) return `${Math.round(h)} giờ`;
  return `${Math.floor(h / 24)} ngày`;
}
