import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "@/components/home-cards";
import { HistoryItem, type HistoryCv } from "@/components/jobs/match-history";
import { SavedJobList } from "@/components/jobs/saved-job-list";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { requireAccess } from "@/lib/auth";
import {
  latestScores,
  SAVED_JOBS_PATH,
  type HistoryRow,
  type SavedJobRow,
} from "@/lib/saved-jobs";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Việc đã lưu" };

// S4-H05 · US-17 · docs/ui/wireframe_matches.png (màn 4). Chỉ người tìm việc (proxy chặn vai trò khác).
// Dữ liệu: api.v_my_saved_jobs, api.v_my_match_history, api.v_my_cvs (migration 0021, RLS của chính mình).


export default async function SavedJobsPage() {
  await requireAccess(SAVED_JOBS_PATH);
  const api = (await createClient()).schema("api");

  const [saved, history, cvs] = await Promise.all([
    api
      .from("v_my_saved_jobs")
      .select("public_id, title, company_name, company_logo_url, valid_through, is_open, status, closed_at, saved_at")
      .order("saved_at", { ascending: false })
      .returns<SavedJobRow[]>(),
    api
      .from("v_my_match_history")
      .select("id, cv_id, cv_target_title, top_n, filters, created_at, result_count, results")
      .order("created_at", { ascending: false })
      .returns<HistoryRow[]>(),
    api.from("v_my_cvs").select("id, mime, original_name, is_primary").returns<HistoryCv[]>(),
  ]);

  const historyRows = history.error ? [] : (history.data ?? []);
  const scores = Object.fromEntries(latestScores(historyRows));
  const cvById = new Map((cvs.data ?? []).map((c) => [c.id, c]));

  return (
    <PageShell title="Việc đã lưu">
      {saved.error ? (
        <Alert variant="destructive" className="max-w-3xl">
          <AlertTitle>Chưa đọc được việc đã lưu</AlertTitle>
          <AlertDescription>Hãy tải lại trang sau ít phút.</AlertDescription>
        </Alert>
      ) : (
        <SavedJobList rows={saved.data ?? []} scores={scores} />
      )}

      <section aria-labelledby="history-heading" className="grid gap-3">
        <h2 id="history-heading" className="text-lg font-semibold">
          10 lần gợi ý gần nhất
        </h2>
        {history.error ? (
          <Alert variant="destructive" className="max-w-3xl">
            <AlertTitle>Chưa đọc được lịch sử gợi ý</AlertTitle>
            <AlertDescription>Hãy tải lại trang sau ít phút.</AlertDescription>
          </Alert>
        ) : historyRows.length === 0 ? (
          <div className="grid justify-items-center gap-3 rounded-lg border-2 border-dashed p-8 text-center text-sm">
            <p className="font-medium">Chưa có lần gợi ý nào</p>
            <p className="max-w-md text-muted-foreground">
              Mỗi lần bạn tìm ở trang Việc phù hợp, hệ thống lưu lại lựa chọn và kết quả để xem lại ở đây.
            </p>
            <Link href="/viec-phu-hop" className={buttonVariants({ variant: "outline", size: "sm" })}>
              Tìm việc phù hợp
            </Link>
          </div>
        ) : (
          <>
            <ul className="divide-y rounded-lg border">
              {historyRows.map((h) => (
                <HistoryItem key={h.id} row={h} cv={h.cv_id ? cvById.get(h.cv_id) : undefined} />
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              &quot;Chấm lại&quot; mở Việc phù hợp với đúng CV và bộ lọc của lần đó. Kết quả có thể khác vì tin mới
              được thêm và tin cũ hết hạn.
            </p>
          </>
        )}
      </section>
    </PageShell>
  );
}
