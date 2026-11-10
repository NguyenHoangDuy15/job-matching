import { ExternalLink } from "lucide-react";
import { LEVEL_LABEL, WORK_MODE_LABEL } from "@/lib/jobs/filters";
import {
  formatDay,
  formatSalary,
  formatUpdatedAt,
  isExpiringSoon,
  sourceName,
} from "@/lib/jobs/format";
import type { JobItem } from "@/lib/jobs/search";

/** Thẻ một việc trong danh sách (S2-H02, theo docs/ui/wireframe_jobs.png). */
export function JobCard({ job }: { job: JobItem }) {
  const expiring = job.is_expiring_soon ?? isExpiringSoon(job.valid_through);
  const source = sourceName(job.apply_url);
  const meta = [
    job.company,
    job.work_mode !== "unknown" ? WORK_MODE_LABEL[job.work_mode] : null,
    job.seniority !== "unknown" ? LEVEL_LABEL[job.seniority] : null,
  ].filter(Boolean);

  return (
    <article className="grid gap-x-6 gap-y-2 rounded-lg border p-4 sm:grid-cols-[1fr_auto]">
      <div className="grid min-w-0 gap-1">
        <h2 className="flex flex-wrap items-center gap-2 text-base font-semibold leading-snug">
          <span className="break-words">{job.title}</span>
          {expiring && (
            <span className="rounded border border-destructive px-1.5 text-xs font-medium text-destructive">
              Sắp hết hạn
            </span>
          )}
        </h2>
        <p className="text-sm text-muted-foreground">{meta.join(" · ")}</p>
      </div>

      <div className="grid content-start gap-1 text-sm sm:text-right">
        <p className="font-semibold">{formatSalary(job)}</p>
        <p className="text-xs text-muted-foreground">
          {job.valid_through && <>Hạn nộp {formatDay(job.valid_through)} · </>}
          {source && <>Nguồn: {source}</>}
        </p>
        <p className="text-xs text-muted-foreground">
          Cập nhật lúc {formatUpdatedAt(job.last_seen_at)}
          {job.source_count > 1 && <> · Có trên {job.source_count} trang</>}
        </p>
        {job.apply_url && (
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline sm:justify-self-end"
          >
            Xem tin gốc <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
      </div>
    </article>
  );
}

/** Khung xám lúc đang tải (US-05: trạng thái đang tải). */
export function JobListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="grid gap-3" aria-busy="true" aria-label="Đang tải danh sách việc">
      <div className="h-4 w-48 animate-pulse rounded bg-muted" />
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="grid gap-2 rounded-lg border p-4 sm:grid-cols-[1fr_8rem]">
          <div className="grid gap-2">
            <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
          </div>
          <div className="grid gap-2">
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-muted sm:justify-self-end" />
          </div>
        </div>
      ))}
    </div>
  );
}
