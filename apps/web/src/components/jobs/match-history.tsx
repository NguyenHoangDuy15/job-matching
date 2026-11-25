import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cvLabel } from "@/lib/cv-list";
import { formatUpdatedAt } from "@/lib/jobs/format";
import { numberVi } from "@/lib/match";
import { bestScore, historyFilterText, historyHref, type HistoryRow } from "@/lib/saved-jobs";

export type HistoryCv = { id: string; mime: string; original_name: string | null; is_primary: boolean };

/**
 * Một dòng trong "10 lần gợi ý gần nhất" (S4-H05 · wireframe_matches màn 4): lúc chấm, CV, số việc + bộ lọc,
 * điểm cao nhất, nút Chấm lại, và danh sách việc của lần đó (thu gọn).
 */
export function HistoryItem({ row: h, cv }: { row: HistoryRow; cv: HistoryCv | undefined }) {
  const best = bestScore(h);
  const cvText = cv ? `${cv.is_primary ? "★ " : ""}${cvLabel(cv)}` : (h.cv_target_title ?? "CV đã xóa");

  return (
    <li className="grid gap-2 p-3 text-sm">
      <div className="grid gap-x-4 gap-y-1 sm:grid-cols-[7rem_minmax(0,1fr)_minmax(0,1.2fr)_6rem_auto] sm:items-center">
        <p className="tabular-nums text-muted-foreground">{formatUpdatedAt(h.created_at)}</p>
        <p className="truncate font-medium" title={cvText}>
          {cvText}
        </p>
        <p className="text-muted-foreground">{historyFilterText(h)}</p>
        <p className="tabular-nums">
          <span className="text-xs text-muted-foreground">Cao nhất </span>
          {best != null ? <b>{numberVi(best, 1)}</b> : "—"}
        </p>
        {cv ? (
          <Link href={historyHref(h)} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Chấm lại
          </Link>
        ) : (
          <span className="text-xs text-muted-foreground">CV không còn</span>
        )}
      </div>
      {h.results.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs text-primary underline-offset-2 hover:underline">
            Xem {h.result_count} việc của lần này
          </summary>
          <ol className="mt-2 grid gap-1 pl-1 text-xs">
            {h.results.map((r) => (
              <li key={r.rank} className="flex gap-2">
                <span className="w-6 shrink-0 text-right tabular-nums text-muted-foreground">#{r.rank}</span>
                <span className="w-10 shrink-0 font-medium tabular-nums">{numberVi(Number(r.score_h), 1)}</span>
                <span className="min-w-0">
                  {r.public_id && r.title ? (
                    <Link href={`/viec-lam/${r.public_id}`} className="hover:underline">
                      {r.title}
                    </Link>
                  ) : (
                    (r.title ?? "Tin đã bị gỡ")
                  )}
                  {r.company_name && <span className="text-muted-foreground"> · {r.company_name}</span>}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </li>
  );
}
