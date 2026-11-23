// Trang Admin tổng quan (S4-T02, US-18): thẻ số, biểu đồ crawl 7 ngày, cảnh báo đỏ.
// Hàm thuần, chạy được cả server lẫn `node --test`.
// Nguồn: api.v_admin_system_daily, api.v_admin_system_daily_source, api.v_admin_crawl_runs (migration 0018).
// Ngày tính theo giờ Việt Nam; crawl_success_pct là 0–100 (null khi hôm đó không crawl).

import { type CrawlRunRow, toNumber } from "./crawl-runs.ts";

type Num = number | string | null;

export type SystemDailyRow = {
  day: string;
  jobs_open: Num;
  jobs_new: Num;
  jobs_new_24h: Num;
  jobs_closed: Num;
  users_seeker: Num;
  users_hr: Num;
  users_admin: Num;
  logins_today: Num;
  matches: Num;
  p95_ms: Num;
  crawl_success_pct: Num;
  llm_cost_usd: Num;
  refreshed_at: string | null;
};

export type SourceDailyRow = {
  day: string;
  source_id: number;
  source_code: string;
  source_name: string;
  is_enabled: boolean;
  jobs_open: Num;
  jobs_new_24h: Num;
  refreshed_at: string | null;
};

export type FailedRun = Pick<CrawlRunRow, "id" | "source_name" | "started_at" | "error_sample">;

export const SYSTEM_DAILY_COLUMNS =
  "day, jobs_open, jobs_new, jobs_new_24h, jobs_closed, users_seeker, users_hr, users_admin, " +
  "logins_today, matches, p95_ms, crawl_success_pct, llm_cost_usd, refreshed_at";

export const SOURCE_DAILY_COLUMNS =
  "day, source_id, source_code, source_name, is_enabled, jobs_open, jobs_new_24h, refreshed_at";

export const FAILED_RUN_COLUMNS = "id, source_name, started_at, error_sample";

/** Ngưỡng cảnh báo đỏ. */
export const CRAWL_SUCCESS_THRESHOLD = 80;
export const STALE_MINUTES = 60;
export const MAX_FAILED_ALERTS = 5;

const VN_DAY = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Ho_Chi_Minh",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Ngày theo giờ Việt Nam, dạng "yyyy-mm-dd" (khớp cột date của mart). */
export function vnDay(date: Date): string {
  return VN_DAY.format(date);
}

export type CrawlPoint = { day: string; label: string; pct: number | null };

/** 7 ngày giờ Việt Nam kết thúc ở hôm nay; ngày không có dữ liệu hoặc không crawl → pct null. */
export function buildCrawlSeries(rows: Pick<SystemDailyRow, "day" | "crawl_success_pct">[], now: Date): CrawlPoint[] {
  const byDay = new Map(rows.map((r) => [r.day.slice(0, 10), toNumber(r.crawl_success_pct)]));
  const points: CrawlPoint[] = [];
  for (let i = 6; i >= 0; i--) {
    const day = vnDay(new Date(now.getTime() - i * 86_400_000));
    const [, m, d] = day.split("-");
    points.push({ day, label: `${d}/${m}`, pct: byDay.get(day) ?? null });
  }
  return points;
}

export type P95Point = { day: string; label: string; ms: number | null };

/** p95 độ trễ API (ms) 7 ngày giờ Việt Nam kết thúc ở hôm nay (S4-T04); ngày không có số đo → null. */
export function buildP95Series(rows: Pick<SystemDailyRow, "day" | "p95_ms">[], now: Date): P95Point[] {
  const byDay = new Map(rows.map((r) => [r.day.slice(0, 10), toNumber(r.p95_ms)]));
  const points: P95Point[] = [];
  for (let i = 6; i >= 0; i--) {
    const day = vnDay(new Date(now.getTime() - i * 86_400_000));
    const [, m, d] = day.split("-");
    points.push({ day, label: `${d}/${m}`, ms: byDay.get(day) ?? null });
  }
  return points;
}

export type AdminAlert = { key: string; title: string; detail: string; href?: string };

/** Cảnh báo đỏ: không có dữ liệu, số liệu cũ, tỉ lệ crawl thấp, lần crawl thất bại 24h, nguồn bật mà 0 tin. */
export function buildAlerts(input: {
  latest: SystemDailyRow | null;
  sources: SourceDailyRow[];
  failedRuns: FailedRun[];
  now: Date;
}): AdminAlert[] {
  const { latest, sources, failedRuns, now } = input;
  const alerts: AdminAlert[] = [];

  if (!latest) {
    alerts.push({
      key: "no-data",
      title: "Chưa có số liệu vận hành",
      detail: "mart.system_daily chưa có dòng nào. Kiểm tra job làm mới mart (15 phút/lần).",
    });
  } else {
    if (latest.refreshed_at) {
      const refreshed = new Date(latest.refreshed_at).getTime();
      const minutes = Math.floor((now.getTime() - refreshed) / 60_000);
      if (Number.isFinite(minutes) && minutes > STALE_MINUTES) {
        alerts.push({
          key: "stale",
          title: "Số liệu chưa được làm mới",
          detail: `Lần làm mới gần nhất cách đây ${formatAge(minutes)} (bình thường 15 phút/lần).`,
        });
      }
    }
    const pct = toNumber(latest.crawl_success_pct);
    if (pct !== null && pct < CRAWL_SUCCESS_THRESHOLD) {
      alerts.push({
        key: "crawl-low",
        title: "Tỉ lệ crawl thành công thấp",
        detail: `Hôm nay ${formatNumber(pct, 1)}%, dưới ngưỡng ${CRAWL_SUCCESS_THRESHOLD}%.`,
        href: "/admin/crawl-runs",
      });
    }
  }

  for (const run of failedRuns.slice(0, MAX_FAILED_ALERTS)) {
    const sample = run.error_sample?.trim().split("\n")[0];
    alerts.push({
      key: `run-${run.id}`,
      title: `Crawl ${run.source_name} thất bại`,
      detail: sample ? truncate(sample, 140) : "Không có mẫu lỗi.",
      href: `/admin/crawl-runs?run=${run.id}#run-${run.id}`,
    });
  }
  if (failedRuns.length > MAX_FAILED_ALERTS) {
    alerts.push({
      key: "run-more",
      title: `Còn ${failedRuns.length - MAX_FAILED_ALERTS} lần thất bại khác trong 24 giờ`,
      detail: "Xem toàn bộ trong lịch sử crawl.",
      href: "/admin/crawl-runs",
    });
  }

  for (const s of sources) {
    if (s.is_enabled && (toNumber(s.jobs_open) ?? 0) === 0) {
      alerts.push({
        key: `source-${s.source_id}`,
        title: `Nguồn ${s.source_name} không còn tin đang mở`,
        detail: "Nguồn đang bật nhưng 0 tin mở. Có thể crawler hỏng hoặc trang đổi cấu trúc.",
        href: "/admin/crawl-runs",
      });
    }
  }

  return alerts;
}

function formatAge(minutes: number): string {
  if (minutes < 120) return `${minutes} phút`;
  const h = Math.floor(minutes / 60);
  if (h < 48) return `${h} giờ`;
  return `${Math.floor(h / 24)} ngày`;
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function formatNumber(n: number, digits: number): string {
  return n.toLocaleString("vi-VN", { maximumFractionDigits: digits });
}

/** Số nguyên có dấu chấm phân cách nghìn kiểu Việt Nam. null → "—". */
export function formatInt(v: Num | undefined): string {
  const n = toNumber(v ?? null);
  return n === null ? "—" : Math.round(n).toLocaleString("vi-VN");
}

/** Chi phí USD, 2 chữ số thập phân: "$1.23". null → "—". */
export function formatUsd(v: Num | undefined): string {
  const n = toNumber(v ?? null);
  return n === null ? "—" : `$${n.toFixed(2)}`;
}

/** Thời gian phản hồi: dưới 1 giây hiện ms, từ 1 giây hiện giây. null → "—". */
export function formatMs(v: Num | undefined): string {
  const n = toNumber(v ?? null);
  if (n === null) return "—";
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${formatNumber(n / 1000, 1)} giây`;
}
