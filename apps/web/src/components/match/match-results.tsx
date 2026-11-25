"use client";

import { AlertCircle, RotateCw, SearchX } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { MatchCard } from "@/components/match/match-card";
import { setMatchBusy } from "@/components/match/use-match-busy";
import { Button, buttonVariants } from "@/components/ui/button";
import { clearFilterHrefs, numberVi, SCORE_DISCLAIMER, type MatchRequest } from "@/lib/match";
import { loginHref, SLOW_HINT_MS, type MatchError, type Simulation } from "@/lib/match-errors";
import { fetchMatches, type MatchOutcome } from "@/lib/match-source";
import { createClient } from "@/lib/supabase/client";

/**
 * Gọi chấm điểm cho đúng một lựa chọn trên URL rồi hiện danh sách (S4-H01).
 * Trang cha đặt `key` theo URL: đổi lựa chọn là component mới, tự gọi lại.
 * Thẻ chi tiết: match-card.tsx (S4-H02). Trạng thái chờ / rỗng / lỗi: S4-H03 (wireframe_matches màn 3).
 * `simulate`: giả lập lỗi ở lần gọi đầu (?gia-lap=503…), bấm Thử lại thì có kết quả.
 */
export function MatchResults({
  request,
  simulate,
  savedIds,
}: {
  request: MatchRequest;
  simulate: Simulation | null;
  /** public_id các tin đã lưu (S4-H05), để thẻ hiện ★ Đã lưu. */
  savedIds: string[];
}) {
  const [attempt, setAttempt] = useState(0);
  const [outcome, setOutcome] = useState<MatchOutcome | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    const slowTimer = setTimeout(() => setSlow(true), SLOW_HINT_MS);
    setMatchBusy(true);
    fetchMatches(request, { signal: ctrl.signal, simulate: attempt === 0 ? simulate : null })
      .then(setOutcome, () => {})
      .finally(() => {
        clearTimeout(slowTimer);
        if (!ctrl.signal.aborted) setMatchBusy(false);
      });
    return () => {
      ctrl.abort();
      clearTimeout(slowTimer);
      setMatchBusy(false);
    };
  }, [request, simulate, attempt]);

  function retry() {
    setOutcome(null);
    setSlow(false);
    setAttempt((a) => a + 1);
  }

  if (!outcome) return <MatchLoading slow={slow} />;
  if (!outcome.ok) return <MatchErrorBox key={attempt} error={outcome.error} onRetry={retry} />;

  const { data, source } = outcome;
  return (
    <section aria-label="Việc phù hợp" className="grid gap-3">
      {source === "mock" && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          Đang hiện <b>dữ liệu mẫu</b> để dựng giao diện. Kết quả thật có khi nối API chấm điểm (S4-H04).
        </p>
      )}
      <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
        {data.note || SCORE_DISCLAIMER}
      </p>

      {data.results.length === 0 ? (
        <MatchEmpty request={request} corpusSize={data.corpus_size} />
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
                <MatchCard
                  result={r}
                  sample={source === "mock"}
                  saved={r.public_id != null && savedIds.includes(r.public_id)}
                />
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

/** 3 thẻ xám cùng dáng thẻ kết quả; quá 5 giây báo có thể máy chủ đang khởi động. */
function MatchLoading({ slow }: { slow: boolean }) {
  return (
    <div aria-busy="true" aria-label="Đang chấm điểm" className="grid gap-3">
      <p role="status" className="text-sm text-muted-foreground">
        Đang chấm điểm các tin đang mở với CV của bạn…
        {slow && (
          <b className="block font-medium text-foreground">
            Hệ thống có thể đang khởi động, lần đầu có thể mất tới 1 phút. Bạn cứ để trang mở.
          </b>
        )}
      </p>
      {Array.from({ length: 3 }, (_, i) => (
        <div
          key={i}
          className="grid gap-x-5 gap-y-3 rounded-lg border p-4 sm:grid-cols-[5.5rem_minmax(0,1fr)] lg:grid-cols-[5.5rem_minmax(0,1fr)_19rem]"
        >
          <div className="flex items-center gap-2 sm:grid sm:justify-items-center sm:border-r sm:pr-4">
            <div className="h-9 w-16 animate-pulse rounded bg-muted" />
          </div>
          <div className="grid content-start gap-2">
            <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
            <div className="h-2 w-full animate-pulse rounded bg-muted" />
            <div className="h-2 w-5/6 animate-pulse rounded bg-muted" />
          </div>
          <div className="hidden content-start gap-2 lg:grid">
            <div className="h-7 w-full animate-pulse rounded bg-muted" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * API từ chối token (401): xóa phiên trên máy này rồi mở trang đăng nhập, đăng nhập xong quay lại đúng trang.
 * Phải xóa phiên trước, vì còn cookie phiên thì middleware đẩy /dang-nhap về trang chủ.
 */
async function relogin() {
  await createClient()
    .auth.signOut({ scope: "local" })
    .catch(() => {});
  window.location.assign(loginHref(window.location.pathname, window.location.search));
}

/** Lỗi: giữ nguyên lựa chọn ở thanh lọc, có Thử lại (429 khóa nút, đếm ngược). 401 tự chuyển đăng nhập. */
function MatchErrorBox({ error, onRetry }: { error: MatchError; onRetry: () => void }) {
  const [left, setLeft] = useState(error.waitSeconds ?? 0);

  useEffect(() => {
    if (!error.waitSeconds) return;
    const timer = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [error.waitSeconds]);

  useEffect(() => {
    if (error.code !== "unauthorized") return;
    const timer = setTimeout(relogin, 1500);
    return () => clearTimeout(timer);
  }, [error.code]);

  return (
    <div role="alert" className="grid gap-3 rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-sm">
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
        <div className="grid gap-1">
          <p className="font-semibold text-destructive">{error.title}</p>
          <p>{error.message}</p>
          {error.code === "unauthorized" && <p className="text-muted-foreground">Đang chuyển tới trang đăng nhập…</p>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 pl-8">
        {error.retry && (
          <Button type="button" size="sm" onClick={onRetry} disabled={left > 0}>
            <RotateCw aria-hidden />
            {left > 0 ? `Thử lại sau ${left} giây` : "Thử lại"}
          </Button>
        )}
        {error.code === "unauthorized" && (
          <Button type="button" size="sm" onClick={relogin}>
            Đăng nhập lại
          </Button>
        )}
        {error.action && (
          <Link href={error.action.href} className={buttonVariants({ variant: "outline", size: "sm" })}>
            {error.action.label}
          </Link>
        )}
      </div>
    </div>
  );
}

/** Không có kết quả: gợi ý bỏ từng bộ lọc; không lọc gì mà vẫn rỗng thì kho tin đang trống. */
function MatchEmpty({ request, corpusSize }: { request: MatchRequest; corpusSize: number }) {
  const clear = clearFilterHrefs(request);
  const filtered = Boolean(clear.provinces || clear.modes);
  return (
    <div className="grid justify-items-center gap-3 rounded-lg border-2 border-dashed p-8 text-center text-sm">
      <SearchX className="size-7 text-muted-foreground" aria-hidden />
      <p className="font-medium">
        {filtered ? "Không có việc nào khớp với bộ lọc hiện tại" : "Chưa có tin nào để chấm điểm"}
      </p>
      <p className="max-w-md text-muted-foreground">
        {filtered
          ? "Thử bỏ bớt bộ lọc rồi tìm lại. Tin làm từ xa và tin không ghi tỉnh vẫn luôn được tính."
          : corpusSize === 0
            ? "Kho tin đang mở hiện trống, hãy quay lại sau khi hệ thống thu thập tin mới."
            : "Chưa tìm thấy tin nào đủ gần với CV này. Hãy bổ sung kỹ năng trong Hồ sơ CV rồi thử lại."}
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {clear.provinces && (
          <Link href={clear.provinces} scroll={false} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Bỏ lọc tỉnh
          </Link>
        )}
        {clear.modes && (
          <Link href={clear.modes} scroll={false} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Bỏ lọc hình thức
          </Link>
        )}
        {!filtered && (
          <Link href="/ho-so" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Về Hồ sơ CV
          </Link>
        )}
      </div>
    </div>
  );
}
