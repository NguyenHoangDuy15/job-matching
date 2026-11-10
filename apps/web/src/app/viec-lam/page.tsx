import type { Metadata } from "next";
import { PageShell } from "@/components/home-cards";
import { JobCard } from "@/components/jobs/job-card";
import { buttonVariants } from "@/components/ui/button";
import { parseFilters, type JobFilters } from "@/lib/jobs/filters";
import { searchJobs, type SearchResult } from "@/lib/jobs/search";
import { isSupabaseConfigured } from "@/lib/supabase/env";

export const metadata: Metadata = { title: "Việc làm" };

// S2-H02 · US-03 · docs/ui/wireframe_jobs.png. Khách và mọi vai trò đều xem được.
// Danh sách 20 việc mới nhất từ rpc api.search_jobs; ?q= (từ ô tìm trên trang chủ) để tìm.
// Ô tìm, bộ lọc trên URL, phân trang và skeleton: S2-H03.
export default async function JobsPage({ searchParams }: PageProps<"/viec-lam">) {
  const filters = parseFilters(await searchParams);

  return (
    <PageShell title="Việc làm IT đang tuyển">
      {isSupabaseConfigured ? (
        <JobList filters={filters} />
      ) : (
        <p className="rounded-lg border p-6 text-muted-foreground">
          Chưa cấu hình Supabase nên chưa có dữ liệu việc làm.
        </p>
      )}
    </PageShell>
  );
}

async function JobList({ filters }: { filters: JobFilters }) {
  let result: SearchResult;
  try {
    result = await searchJobs(filters);
  } catch (err) {
    console.error(err);
    return (
      <div role="alert" className="grid justify-items-start gap-3 rounded-lg border p-6">
        <p>Chưa tải được danh sách việc, thử lại.</p>
        <a href={filters.q ? `/viec-lam?q=${encodeURIComponent(filters.q)}` : "/viec-lam"} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Thử lại
        </a>
      </div>
    );
  }

  const { jobs, total, ms } = result;
  if (jobs.length === 0) {
    return (
      <p className="rounded-lg border p-6">
        Không có việc nào khớp{filters.q && <> từ khóa &quot;{filters.q}&quot;</>}.
      </p>
    );
  }

  const seconds = (ms / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
  return (
    <section aria-label="Danh sách việc làm" className="grid gap-3">
      <p className="text-sm text-muted-foreground">
        {filters.q && <>Từ khóa &quot;{filters.q}&quot; · </>}
        {total !== null && <b className="text-foreground">{total.toLocaleString("vi-VN")} việc · </b>}
        trong {seconds} giây · {filters.q ? "liên quan nhất trước" : "mới cập nhật trước"}
      </p>
      {jobs.map((job) => (
        <JobCard key={job.public_id} job={job} />
      ))}
    </section>
  );
}
