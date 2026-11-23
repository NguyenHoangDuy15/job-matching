import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/home-cards";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  CRAWL_RUN_COLUMNS,
  type CrawlRunRow,
  formatDateTimeVN,
  formatDetails,
  formatDuration,
  formatPct,
  hasError,
  RUN_STATUS_CLASS,
  RUN_STATUS_LABEL,
  RUN_TYPE_LABEL,
  toNumber,
} from "@/lib/admin/crawl-runs";
import { requireAccess } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Lịch sử crawl" };

const LIMIT = 100;

export default async function CrawlRunsPage({ searchParams }: PageProps<"/admin/crawl-runs">) {
  await requireAccess("/admin/crawl-runs");
  const params = await searchParams;
  const openRun = typeof params.run === "string" ? params.run : undefined;

  const api = (await createClient()).schema("api");
  const { data, error } = await api
    .from("v_admin_crawl_runs")
    .select(CRAWL_RUN_COLUMNS)
    .order("started_at", { ascending: false })
    .limit(LIMIT)
    .returns<CrawlRunRow[]>();

  const missing = error?.code === "42703" || error?.code === "PGRST204" || error?.code === "PGRST205";
  const runs = data ?? [];

  return (
    <PageShell title="Lịch sử crawl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {LIMIT} lần chạy gần nhất, giờ Việt Nam. Bấm “Xem lỗi” để mở chi tiết từng lần chạy.
        </p>
        <Link href="/admin" className={buttonVariants({ variant: "outline", size: "sm" })}>
          Về tổng quan
        </Link>
      </div>

      {error ? (
        <Alert variant="destructive" className="max-w-3xl">
          <AlertTitle>Không tải được lịch sử crawl</AlertTitle>
          <AlertDescription>
            {missing
              ? "Database chưa có migration 0018 (api.v_admin_crawl_runs). Báo nhóm chạy migration rồi tải lại trang."
              : "Hãy tải lại trang sau ít phút."}
          </AlertDescription>
        </Alert>
      ) : runs.length === 0 ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Chưa có lần crawl nào.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[900px] text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Nguồn</th>
                <th className="px-3 py-2 font-medium">Loại</th>
                <th className="px-3 py-2 font-medium">Trạng thái</th>
                <th className="px-3 py-2 font-medium">Bắt đầu</th>
                <th className="px-3 py-2 font-medium">Thời lượng</th>
                <th className="px-3 py-2 text-right font-medium">Mới</th>
                <th className="px-3 py-2 text-right font-medium">Cập nhật</th>
                <th className="px-3 py-2 text-right font-medium">Đóng</th>
                <th className="px-3 py-2 text-right font-medium">Lỗi HTTP</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRows key={run.id} run={run} open={openRun === String(run.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageShell>
  );
}

function RunRows({ run, open }: { run: CrawlRunRow; open: boolean }) {
  const failed = hasError(run);
  const details = formatDetails(run.quality_details);
  const httpErrors = run.http_errors ?? 0;

  return (
    <>
      <tr id={`run-${run.id}`} className={cn("border-t", open && "bg-muted/40")}>
        <td className="px-3 py-2">
          <div className="font-medium">{run.source_name}</div>
          <div className="text-xs text-muted-foreground">#{run.id}</div>
        </td>
        <td className="px-3 py-2">{RUN_TYPE_LABEL[run.run_type] ?? run.run_type}</td>
        <td className="px-3 py-2">
          <span
            className={cn(
              "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
              RUN_STATUS_CLASS[run.status],
            )}
          >
            {RUN_STATUS_LABEL[run.status] ?? run.status}
          </span>
        </td>
        <td className="px-3 py-2 whitespace-nowrap">{formatDateTimeVN(run.started_at)}</td>
        <td className="px-3 py-2 whitespace-nowrap">{formatDuration(run.duration_s)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{run.items_new ?? "—"}</td>
        <td className="px-3 py-2 text-right tabular-nums">{run.items_updated ?? "—"}</td>
        <td className="px-3 py-2 text-right tabular-nums">{run.items_closed ?? "—"}</td>
        <td
          className={cn(
            "px-3 py-2 text-right tabular-nums",
            httpErrors > 0 && "font-semibold text-red-600 dark:text-red-400",
          )}
        >
          {run.http_errors ?? "—"}
        </td>
      </tr>
      <tr className={cn(open && "bg-muted/40")}>
        <td colSpan={9} className="px-3 pb-2">
          <details open={open} className="group">
            <summary
              className={cn(
                "cursor-pointer text-xs select-none",
                failed ? "font-medium text-red-600 dark:text-red-400" : "text-muted-foreground",
              )}
            >
              {failed ? "Xem lỗi" : "Xem chi tiết"}
            </summary>
            <div className="mt-2 grid gap-3 rounded-md border bg-background p-3 text-xs">
              <div>
                <div className="mb-1 font-medium">Mẫu lỗi</div>
                {run.error_sample?.trim() ? (
                  <pre className="max-h-64 overflow-auto rounded bg-muted p-2 font-mono whitespace-pre-wrap break-words">
                    {run.error_sample}
                  </pre>
                ) : (
                  <p className="text-muted-foreground">Không có mẫu lỗi.</p>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
                <Field label="Lỗi HTTP" value={run.http_errors} danger={httpErrors > 0} />
                <Field label="Lỗi schema" value={run.schema_errors} danger={(run.schema_errors ?? 0) > 0} />
                <Field label="Trang đã tải" value={run.pages_fetched} />
                <Field label="Tin đã thấy" value={run.items_seen} />
                <Field label="Kết thúc" value={formatDateTimeVN(run.finished_at)} />
                <Field label="Đầy đủ" value={formatPct(run.completeness)} />
                <Field label="Hợp lệ" value={formatPct(run.validity)} />
                <Field label="Không trùng" value={formatPct(run.uniqueness)} />
                <Field label="Đọc được lương" value={formatPct(run.salary_parsed_pct)} />
                <Field label="Đọc được tỉnh" value={formatPct(run.province_parsed_pct)} />
                <Field label="Độ mới (giờ)" value={toNumber(run.freshness_hours)} />
              </dl>
              {details && (
                <div>
                  <div className="mb-1 font-medium">Chi tiết báo cáo chất lượng</div>
                  <pre className="max-h-64 overflow-auto rounded bg-muted p-2 font-mono">{details}</pre>
                </div>
              )}
            </div>
          </details>
        </td>
      </tr>
    </>
  );
}

function Field({ label, value, danger }: { label: string; value: string | number | null; danger?: boolean }) {
  return (
    <div className="flex justify-between gap-2 sm:block">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("tabular-nums", danger && "font-semibold text-red-600 dark:text-red-400")}>
        {value ?? "—"}
      </dd>
    </div>
  );
}
