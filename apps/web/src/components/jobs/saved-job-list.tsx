"use client";

import Link from "next/link";
import { useState } from "react";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { buttonVariants } from "@/components/ui/button";
import { daysLeft, daysLeftLabel, formatDay, isExpiringSoon, todayVN } from "@/lib/jobs/format";
import { numberVi } from "@/lib/match";
import type { SavedJobRow } from "@/lib/saved-jobs";
import { cn } from "@/lib/utils";

/**
 * Bảng Việc đã lưu (S4-H05 · wireframe_matches màn 4). Tin hết hạn / bị gỡ vẫn giữ, có nhãn
 * "Đã đóng" và không có link (trang chi tiết chỉ hiện tin còn mở). Bỏ lưu thì dòng biến mất ngay.
 * `scores`: điểm gần nhất của tin trong 10 lần gợi ý (DB không lưu điểm lúc lưu).
 */
export function SavedJobList({ rows, scores }: { rows: SavedJobRow[]; scores: Record<string, number> }) {
  const [removed, setRemoved] = useState<string[]>([]);
  const visible = rows.filter((r) => !removed.includes(r.public_id));

  return (
    <section aria-labelledby="saved-heading" className="grid gap-3">
      <h2 id="saved-heading" className="text-lg font-semibold">
        Việc đã lưu ({visible.length})
      </h2>
      {visible.length === 0 ? (
        <div className="grid justify-items-center gap-3 rounded-lg border-2 border-dashed p-8 text-center text-sm">
          <p className="font-medium">Bạn chưa lưu việc nào</p>
          <p className="max-w-md text-muted-foreground">
            Bấm <b>☆ Lưu</b> ở trang Việc phù hợp hoặc trang chi tiết tin để giữ lại việc bạn quan tâm.
          </p>
          <Link href="/viec-phu-hop" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Xem việc phù hợp
          </Link>
        </div>
      ) : (
        <>
          <ul className="divide-y rounded-lg border">
            {visible.map((r) => (
              <SavedRow
                key={r.public_id}
                row={r}
                score={scores[r.public_id]}
                onUnsave={() => setRemoved((ids) => [...ids, r.public_id])}
              />
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Tin hết hạn hoặc bị gỡ vẫn giữ trong danh sách, có nhãn Đã đóng và không ứng tuyển được. Điểm là điểm gần
            nhất của tin trong 10 lần gợi ý bên dưới.
          </p>
        </>
      )}
    </section>
  );
}

function SavedRow({ row: r, score, onUnsave }: { row: SavedJobRow; score: number | undefined; onUnsave: () => void }) {
  const left = r.valid_through ? daysLeft(r.valid_through) : null;
  const expiring = r.is_open && isExpiringSoon(r.valid_through);

  return (
    <li className="grid gap-x-4 gap-y-2 p-3 text-sm sm:grid-cols-[minmax(0,1fr)_5rem_9rem_auto] sm:items-center">
      <div className="grid min-w-0 gap-0.5">
        <p className="flex flex-wrap items-center gap-2 font-medium">
          {r.is_open ? (
            <Link href={`/viec-lam/${r.public_id}`} className="hover:underline">
              {r.title}
            </Link>
          ) : (
            <span className="text-muted-foreground">{r.title}</span>
          )}
          {!r.is_open && (
            <span className="rounded border border-muted-foreground/60 px-1.5 text-xs text-muted-foreground">Đã đóng</span>
          )}
          {expiring && (
            <span className="rounded border border-destructive px-1.5 text-xs text-destructive">Sắp hết hạn</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">
          {r.company_name ?? "Chưa rõ công ty"} · lưu ngày {formatDay(todayVN(new Date(r.saved_at)))}
        </p>
      </div>
      <p className="tabular-nums" title="Điểm gần nhất trong 10 lần gợi ý">
        <span className="text-xs text-muted-foreground sm:hidden">Điểm: </span>
        {score != null ? <b>{numberVi(score, 1)}</b> : <span className="text-muted-foreground">—</span>}
      </p>
      <p className={cn("text-xs", r.is_open ? "text-muted-foreground" : "text-muted-foreground/70")}>
        {r.valid_through ? (
          <>
            Hạn nộp {formatDay(r.valid_through)}
            {r.is_open && left != null && ` (${daysLeftLabel(left)})`}
          </>
        ) : (
          "Không ghi hạn nộp"
        )}
      </p>
      <div className="flex flex-wrap items-start gap-2">
        {r.is_open ? (
          <Link href={`/viec-lam/${r.public_id}`} className={buttonVariants({ size: "sm" })}>
            Xem tin &amp; ứng tuyển
          </Link>
        ) : (
          <span className={cn(buttonVariants({ size: "sm", variant: "outline" }), "opacity-50")} title="Tin đã đóng">
            Không còn nhận hồ sơ
          </span>
        )}
        <SaveJobButton publicId={r.public_id} initialSaved onChange={(saved) => !saved && onUnsave()} />
      </div>
    </li>
  );
}
