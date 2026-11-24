import type { Metadata } from "next";
import Link from "next/link";
import { PageShell, StatCard } from "@/components/home-cards";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { formatDateTimeVN, formatPct, toNumber } from "@/lib/admin/crawl-runs";
import {
  formatFreshness,
  isLowQuality,
  isStale,
  latestReportPerSource,
  QUALITY_REPORT_COLUMNS,
  type QualityMetric,
  type QualityReportRow,
} from "@/lib/admin/quality-reports";
import {
  type AdminAlert,
  buildAlerts,
  buildCrawlSeries,
  buildP95Series,
  CRAWL_SUCCESS_THRESHOLD,
  type CrawlPoint,
  FAILED_RUN_COLUMNS,
  type FailedRun,
  formatInt,
  formatMs,
  formatUsd,
  type P95Point,
  SOURCE_DAILY_COLUMNS,
  type SourceDailyRow,
  SYSTEM_DAILY_COLUMNS,
  type SystemDailyRow,
} from "@/lib/admin/system-daily";
import { requireAccess } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Quản trị" };

const MISSING_CODES = new Set(["42703", "PGRST204", "PGRST205"]);

async function loadOverview() {
  const now = new Date();
  const since = new Date(now.getTime() - 24 * 3_600_000).toISOString();
  const api = (await createClient()).schema("api");

  const [daily, sources, failed, quality] = await Promise.all([
    api
      .from("v_admin_system_daily")
      .select(SYSTEM_DAILY_COLUMNS)
      .order("day", { ascending: false })
      .limit(7)
      .returns<SystemDailyRow[]>(),
    api
      .from("v_admin_system_daily_source")
      .select(SOURCE_DAILY_COLUMNS)
      .order("day", { ascending: false })
      .limit(100)
      .returns<SourceDailyRow[]>(),
    api
      .from("v_admin_crawl_runs")
      .select(FAILED_RUN_COLUMNS)
      .eq("status", "failed")
      .gte("started_at", since)
      .order("started_at", { ascending: false })
      .limit(20)
      .returns<FailedRun[]>(),
    api
      .from("v_admin_crawl_runs")
      .select(QUALITY_REPORT_COLUMNS)
      .not("completeness", "is", null)
      .order("started_at", { ascending: false })
      .limit(100)
      .returns<QualityReportRow[]>(),
  ]);

  const error = daily.error ?? sources.error ?? failed.error ?? quality.error;
  const days = daily.data ?? [];
  const latest = days[0] ?? null;
  const latestSourceDay = sources.data?.[0]?.day;
  const sourceRows = (sources.data ?? [])
    .filter((s) => s.day === latestSourceDay)
    .sort((a, b) => (toNumber(b.jobs_open) ?? 0) - (toNumber(a.jobs_open) ?? 0));

  return {
    error,
    missing: error ? MISSING_CODES.has(error.code) : false,
    latest,
    sources: sourceRows,
    series: buildCrawlSeries(days, now),
    p95Series: buildP95Series(days, now),
    quality: latestReportPerSource(quality.data ?? []),
    alerts: error ? [] : buildAlerts({ latest, sources: sourceRows, failedRuns: failed.data ?? [], now }),
  };
}

export default async function AdminHomePage() {
  await requireAccess("/admin");
  const { error, missing, latest, sources, series, p95Series, quality, alerts } = await loadOverview();
  const updated = latest?.refreshed_at ? `Cập nhật ${formatDateTimeVN(latest.refreshed_at)}` : undefined;

  return (
    <PageShell title="Sức khỏe hệ thống">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Số liệu hôm nay theo giờ Việt Nam, làm mới 15 phút/lần.
        </p>
        <Link href="/admin/crawl-runs" className={buttonVariants({ variant: "outline", size: "sm" })}>
          Lịch sử crawl
        </Link>
      </div>

      {error ? (
        <Alert variant="destructive" className="max-w-3xl">
          <AlertTitle>Không tải được số liệu vận hành</AlertTitle>
          <AlertDescription>
            {missing
              ? "Database chưa có migration 0018 (api.v_admin_system_daily, api.v_admin_crawl_runs). Báo nhóm chạy migration rồi tải lại trang."
              : "Hãy tải lại trang sau ít phút."}
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <Alerts alerts={alerts} />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Tin đang mở" value={formatInt(latest?.jobs_open)} hint={updated} />
            <StatCard label="Tin mới 24 giờ" value={formatInt(latest?.jobs_new_24h)} hint="Tất cả nguồn" />
            <StatCard label="Tin đóng hôm nay" value={formatInt(latest?.jobs_closed)} />
            <StatCard
              label="Người tìm việc"
              value={formatInt(latest?.users_seeker)}
              hint={`HR ${formatInt(latest?.users_hr)} · Admin ${formatInt(latest?.users_admin)}`}
            />
            <StatCard label="Đăng nhập hôm nay" value={formatInt(latest?.logins_today)} />
            <StatCard label="Lượt gợi ý việc hôm nay" value={formatInt(latest?.matches)} />
            <StatCard label="Thời gian phản hồi p95" value={formatMs(latest?.p95_ms)} />
            <StatCard label="Chi phí LLM hôm nay" value={formatUsd(latest?.llm_cost_usd)} />
          </div>

          <CrawlChart series={series} />
          <P95Chart series={p95Series} />
          <SourceTable sources={sources} />
          <QualityTable reports={quality} />
        </>
      )}

      <p className="text-sm text-muted-foreground">
        Quản trị viên không đọc được CV của người dùng (đặc quyền tối thiểu). Mọi thao tác quản trị được ghi vào nhật
        ký.
      </p>
    </PageShell>
  );
}

function Alerts({ alerts }: { alerts: AdminAlert[] }) {
  if (alerts.length === 0) {
    return (
      <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
        Không có cảnh báo.
      </p>
    );
  }
  return (
    <section aria-label="Cảnh báo" className="grid gap-2">
      {alerts.map((a) => {
        const body = (
          <>
            <div className="font-medium">{a.title}</div>
            <div className="text-xs opacity-90">{a.detail}</div>
          </>
        );
        const cls =
          "block rounded-lg border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200";
        return a.href ? (
          <Link key={a.key} href={a.href} className={cn(cls, "hover:bg-red-100 dark:hover:bg-red-900")}>
            {body}
          </Link>
        ) : (
          <div key={a.key} className={cls}>
            {body}
          </div>
        );
      })}
    </section>
  );
}

function CrawlChart({ series }: { series: CrawlPoint[] }) {
  return (
    <section className="rounded-lg border p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">Tỉ lệ crawl thành công 7 ngày</h2>
        <span className="text-xs text-muted-foreground">
          Vạch đứt: ngưỡng {CRAWL_SUCCESS_THRESHOLD}%. Cột đỏ: dưới ngưỡng.
        </span>
      </div>
      <div className="relative h-40">
        <div
          className="pointer-events-none absolute inset-x-0 border-t border-dashed border-red-400"
          style={{ bottom: `${CRAWL_SUCCESS_THRESHOLD}%` }}
          aria-hidden
        />
        <ol className="flex h-full items-end gap-2">
          {series.map((p) => {
            const low = p.pct !== null && p.pct < CRAWL_SUCCESS_THRESHOLD;
            return (
              <li key={p.day} className="flex h-full flex-1 flex-col justify-end">
                {p.pct === null ? (
                  <div className="h-px bg-border" title={`${p.label}: không có lần crawl`} />
                ) : (
                  <div
                    className={cn("rounded-t", low ? "bg-red-500" : "bg-emerald-500")}
                    style={{ height: `${Math.max(2, Math.min(100, p.pct))}%` }}
                    title={`${p.label}: ${p.pct.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`}
                  />
                )}
              </li>
            );
          })}
        </ol>
      </div>
      <ol className="mt-2 flex gap-2 text-center text-xs">
        {series.map((p) => {
          const low = p.pct !== null && p.pct < CRAWL_SUCCESS_THRESHOLD;
          return (
            <li key={p.day} className="flex-1">
              <div className={cn("tabular-nums", low ? "font-semibold text-red-600 dark:text-red-400" : "")}>
                {p.pct === null ? "—" : `${p.pct.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`}
              </div>
              <div className="text-muted-foreground">{p.label}</div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function P95Chart({ series }: { series: P95Point[] }) {
  const max = Math.max(1, ...series.map((p) => p.ms ?? 0));
  return (
    <section className="rounded-lg border p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">Thời gian phản hồi p95 7 ngày</h2>
        <span className="text-xs text-muted-foreground">Mọi request API, theo ngày giờ Việt Nam.</span>
      </div>
      <ol className="flex h-40 items-end gap-2">
        {series.map((p) => (
          <li key={p.day} className="flex h-full flex-1 flex-col justify-end">
            {p.ms === null ? (
              <div className="h-px bg-border" title={`${p.label}: không có số đo`} />
            ) : (
              <div
                className="rounded-t bg-sky-500"
                style={{ height: `${Math.max(2, (p.ms / max) * 100)}%` }}
                title={`${p.label}: ${formatMs(p.ms)}`}
              />
            )}
          </li>
        ))}
      </ol>
      <ol className="mt-2 flex gap-2 text-center text-xs">
        {series.map((p) => (
          <li key={p.day} className="flex-1">
            <div className="tabular-nums">{formatMs(p.ms)}</div>
            <div className="text-muted-foreground">{p.label}</div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function SourceTable({ sources }: { sources: SourceDailyRow[] }) {
  if (sources.length === 0) return null;
  return (
    <section className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[480px] text-sm">
        <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Nguồn</th>
            <th className="px-3 py-2 font-medium">Trạng thái</th>
            <th className="px-3 py-2 text-right font-medium">Tin đang mở</th>
            <th className="px-3 py-2 text-right font-medium">Tin mới 24 giờ</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => {
            const empty = s.is_enabled && (toNumber(s.jobs_open) ?? 0) === 0;
            return (
              <tr key={s.source_id} className="border-t">
                <td className="px-3 py-2 font-medium">{s.source_name}</td>
                <td className="px-3 py-2 text-muted-foreground">{s.is_enabled ? "Đang bật" : "Đã tắt"}</td>
                <td
                  className={cn(
                    "px-3 py-2 text-right tabular-nums",
                    empty && "font-semibold text-red-600 dark:text-red-400",
                  )}
                >
                  {formatInt(s.jobs_open)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{formatInt(s.jobs_new_24h)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

const QUALITY_COLUMNS: { metric: QualityMetric; label: string }[] = [
  { metric: "completeness", label: "Đầy đủ" },
  { metric: "validity", label: "Hợp lệ" },
  { metric: "uniqueness", label: "Không trùng" },
  { metric: "salary_parsed_pct", label: "Lương chuẩn hóa" },
  { metric: "province_parsed_pct", label: "Tỉnh/thành" },
];

const RED = "font-semibold text-red-600 dark:text-red-400";

function QualityTable({ reports }: { reports: QualityReportRow[] }) {
  return (
    <section className="rounded-lg border">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-4 pt-4 pb-3">
        <h2 className="text-sm font-medium">Chất lượng dữ liệu lần crawl gần nhất</h2>
        <span className="text-xs text-muted-foreground">Ô đỏ: dưới ngưỡng, có lỗi schema hoặc tin mới nhất quá 48 giờ.</span>
      </div>
      {reports.length === 0 ? (
        <p className="border-t px-4 py-3 text-sm text-muted-foreground">Chưa có báo cáo chất lượng.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Nguồn</th>
                <th className="px-3 py-2 font-medium">Lần chạy</th>
                {QUALITY_COLUMNS.map((c) => (
                  <th key={c.metric} className="px-3 py-2 text-right font-medium">
                    {c.label}
                  </th>
                ))}
                <th className="px-3 py-2 text-right font-medium">Lỗi schema</th>
                <th className="px-3 py-2 text-right font-medium">Độ mới</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.source_id} className="border-t">
                  <td className="px-3 py-2 font-medium">{r.source_name}</td>
                  <td className="px-3 py-2 text-muted-foreground tabular-nums">{formatDateTimeVN(r.started_at)}</td>
                  {QUALITY_COLUMNS.map((c) => (
                    <td
                      key={c.metric}
                      className={cn("px-3 py-2 text-right tabular-nums", isLowQuality(c.metric, r[c.metric]) && RED)}
                    >
                      {formatPct(r[c.metric])}
                    </td>
                  ))}
                  <td className={cn("px-3 py-2 text-right tabular-nums", (r.schema_errors ?? 0) > 0 && RED)}>
                    {formatInt(r.schema_errors)}
                  </td>
                  <td className={cn("px-3 py-2 text-right tabular-nums", isStale(r.freshness_hours) && RED)}>
                    {formatFreshness(r.freshness_hours)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
