"use client";

import { useEffect, useState } from "react";
import { JobListSkeleton } from "@/components/jobs/job-card";
import { MatchCard } from "@/components/match/match-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { numberVi, type MatchRequest } from "@/lib/match";
import { fetchMatches, type MatchOutcome } from "@/lib/match-source";

/**
 * Gọi chấm điểm cho đúng một lựa chọn trên URL rồi hiện danh sách (S4-H01).
 * Trang cha đặt `key` theo URL: đổi lựa chọn là component mới, tự gọi lại.
 * Thẻ chi tiết: match-card.tsx (S4-H02). Trạng thái lỗi đầy đủ ở S4-H03.
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

      {data.results.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed p-8 text-center text-sm text-muted-foreground">
          Không có việc nào khớp với bộ lọc hiện tại. Thử bỏ bớt tỉnh hoặc hình thức rồi tìm lại.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 className="font-semibold">
              {data.results.length === request.top_n
                ? `${data.results.length} việc phù hợp nhất`
                : `Chỉ có ${data.results.length} việc phù hợp`}
            </h2>
            <p className="text-xs text-muted-foreground">
              Chọn từ {numberVi(data.candidates, 0)} tin gần với CV trong {numberVi(data.corpus_size, 0)} tin đang mở ·
              trả lời trong {numberVi(data.latency_ms / 1000, 2)} giây
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            Chip đậm = có bằng chứng trong CV · viền nét đứt = CV chỉ liệt kê · viền chấm = bạn tự thêm · &quot;(qua
            …)&quot; = khớp qua kỹ năng liên quan. Rê chuột lên chip để xem kỹ năng bắt buộc hay ưu tiên.
          </p>
          <ol className="grid gap-3">
            {data.results.map((r) => (
              <li key={r.job_id}>
                <MatchCard result={r} sample={source === "mock"} />
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
