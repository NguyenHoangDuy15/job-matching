"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { JobListSkeleton } from "@/components/jobs/job-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { WORK_MODE_LABEL, type WorkMode } from "@/lib/jobs/filters";
import { daysLeft, daysLeftLabel, formatDay, isExpiringSoon } from "@/lib/jobs/format";
import type { MatchRequest, MatchResult } from "@/lib/match";
import { fetchMatches, type MatchOutcome } from "@/lib/match-source";
import { cn } from "@/lib/utils";

const numberVi = (n: number, digits = 0) =>
  n.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/**
 * Gọi chấm điểm cho đúng một lựa chọn trên URL rồi hiện danh sách (S4-H01).
 * Trang cha đặt `key` theo URL: đổi lựa chọn là component mới, tự gọi lại.
 * Thẻ chi tiết (4 thanh điểm, kỹ năng khớp / chưa thể hiện) làm ở S4-H02; trạng thái lỗi đầy đủ ở S4-H03.
 */
export function MatchResults({ request }: { request: MatchRequest }) {
  const [outcome, setOutcome] = useState<MatchOutcome | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchMatches(request, ctrl.signal).then(setOutcome, () => {});
    return () => ctrl.abort();
  }, [request]);

  if (!outcome) {
    return (
      <div aria-busy="true" className="grid gap-3">
        <p className="text-sm text-muted-foreground">Đang chấm điểm các tin đang mở với CV của bạn…</p>
        <JobListSkeleton />
      </div>
    );
  }

  if (!outcome.ok) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Chưa lấy được việc phù hợp</AlertTitle>
        <AlertDescription>{outcome.message}</AlertDescription>
      </Alert>
    );
  }

  const { data, source } = outcome;
  return (
    <section aria-label="Việc phù hợp" className="grid gap-3">
      {source === "mock" && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          Đang hiện <b>dữ liệu mẫu</b> để dựng giao diện. Kết quả thật có khi nối API chấm điểm (S4-H04).
        </p>
      )}
      <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
        {data.note}
      </p>
      {data.results.length > 0 && (
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="font-semibold">
            {data.results.length === request.top_n
              ? `${data.results.length} việc phù hợp nhất`
              : `Chỉ có ${data.results.length} việc phù hợp`}
          </h2>
          <p className="text-xs text-muted-foreground">
            Chọn từ {numberVi(data.candidates)} tin gần với CV trong {numberVi(data.corpus_size)} tin đang mở · trả
            lời trong {numberVi(data.latency_ms / 1000, 2)} giây
          </p>
        </div>
      )}

      {data.results.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed p-8 text-center text-sm text-muted-foreground">
          Không có việc nào khớp với bộ lọc hiện tại. Thử bỏ bớt tỉnh hoặc hình thức rồi tìm lại.
        </div>
      ) : (
        <ol className="grid gap-3">
          {data.results.map((r) => (
            <li key={r.job_id}>
              <MatchRow result={r} sample={source === "mock"} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function MatchRow({ result: r, sample }: { result: MatchResult; sample: boolean }) {
  const mode = r.work_mode in WORK_MODE_LABEL && r.work_mode !== "unknown" ? WORK_MODE_LABEL[r.work_mode as WorkMode] : null;
  const meta = [r.company, r.provinces.join(", ") || null, mode].filter(Boolean);
  const expiring = isExpiringSoon(r.valid_through);

  return (
    <article className="grid gap-x-5 gap-y-2 rounded-lg border p-4 sm:grid-cols-[4.5rem_1fr_auto]">
      <div className="flex items-baseline gap-2 sm:grid sm:justify-items-center sm:border-r sm:pr-4">
        <span className="text-xs text-muted-foreground">#{r.rank}</span>
        <span className="text-2xl font-bold tabular-nums">{numberVi(r.score, 1)}</span>
        <span className="text-xs text-muted-foreground">/ 100</span>
      </div>
      <div className="grid min-w-0 content-start gap-1">
        <h3 className="flex flex-wrap items-center gap-2 font-semibold leading-snug">
          {r.title}
          {expiring && (
            <span className="rounded border border-destructive px-1.5 text-xs font-medium text-destructive">
              Sắp hết hạn
            </span>
          )}
        </h3>
        <p className="text-sm text-muted-foreground">
          {meta.join(" · ")}
          {r.valid_through && (
            <>
              {" "}
              · Hạn nộp {formatDay(r.valid_through)} ({daysLeftLabel(daysLeft(r.valid_through))})
            </>
          )}
        </p>
        <p className="text-xs text-muted-foreground">{r.explanation}</p>
      </div>
      <div className="flex flex-wrap content-start gap-2 sm:justify-end">
        {sample || !r.public_id ? (
          <span className={cn(buttonVariants({ variant: "outline", size: "sm" }), "opacity-50")} title="Dữ liệu mẫu">
            Xem tin
          </span>
        ) : (
          <Link href={`/viec-lam/${r.public_id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Xem tin
          </Link>
        )}
        {r.apply_url && (
          <a href={r.apply_url} target="_blank" rel="noopener noreferrer" className={buttonVariants({ size: "sm" })}>
            Ứng tuyển ở trang gốc <ExternalLink aria-hidden />
          </a>
        )}
      </div>
    </article>
  );
}
