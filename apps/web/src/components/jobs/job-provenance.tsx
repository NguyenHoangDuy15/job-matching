import { ExternalLink } from "lucide-react";
import type { JobDetail } from "@/lib/jobs/detail";
import { formatUpdatedAt, sourceName } from "@/lib/jobs/format";

/**
 * Độ mới và nguồn của tin (S2-H05, US-06): "Cập nhật lúc", tên trang nguồn, và "Có trên N trang"
 * mở ra danh sách link. Dùng <details> nên mở/đóng được cả khi chưa tải JS.
 */
export function JobProvenance({ job }: { job: JobDetail }) {
  // Có view 0007: danh sách link thật. Bản dự phòng: chỉ biết link chính và số trang.
  const sources = job.sources.length
    ? job.sources
    : job.apply_url
      ? [{ url: job.apply_url, last_seen_at: job.last_seen_at }]
      : [];
  const main = sourceName(job.apply_url ?? sources[0]?.url ?? null);
  const count = Math.max(job.source_count, sources.length);

  return (
    <div className="flex flex-wrap items-start gap-x-2 gap-y-1 text-sm text-muted-foreground">
      <span title="Lần gần nhất hệ thống thấy tin này còn trên trang nguồn">
        Cập nhật lúc {formatUpdatedAt(job.last_seen_at)}
      </span>
      {main && (
        <>
          <span aria-hidden>·</span>
          <span>Nguồn: {main}</span>
        </>
      )}
      {count > 1 && (
        <>
          <span aria-hidden>·</span>
          {sources.length > 1 ? (
            <details className="group">
              <summary className="cursor-pointer list-none text-foreground underline-offset-2 hover:underline">
                Có trên {count} trang <span className="inline-block transition-transform group-open:rotate-180" aria-hidden>▾</span>
              </summary>
              <ul className="mt-2 grid gap-1 rounded-md border bg-background p-3">
                {sources.map((s) => (
                  <li key={s.url} className="flex flex-wrap items-center gap-x-2">
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                    >
                      {sourceName(s.url) ?? s.url} <ExternalLink className="size-3" aria-hidden />
                    </a>
                    <span className="text-xs">thấy lúc {formatUpdatedAt(s.last_seen_at)}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : (
            <span>Có trên {count} trang</span>
          )}
        </>
      )}
    </div>
  );
}
