import type { Metadata } from "next";
import { Suspense } from "react";
import { JobListSkeleton } from "@/components/jobs/job-card";
import { JobFilters } from "@/components/jobs/job-filters";
import { ActiveFilters, JobResults } from "@/components/jobs/job-results";
import { SearchBar } from "@/components/jobs/search-bar";
import { parseFilters, toQueryString } from "@/lib/jobs/filters";
import { isSupabaseConfigured } from "@/lib/supabase/env";

export const metadata: Metadata = { title: "Việc làm" };

// S2-H03 (dựa trên dữ liệu S2-H02) · US-03, US-05 · docs/ui/wireframe_jobs.png
// Khách và mọi vai trò đều xem được. Mọi bộ lọc nằm trên URL.
export default async function JobsPage({ searchParams }: PageProps<"/viec-lam">) {
  const filters = parseFilters(await searchParams);
  // Đổi URL là đổi key: Suspense hiện lại skeleton, bộ lọc nhận lại state từ URL.
  const key = toQueryString(filters) || "all";

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 px-4 py-6">
      <div className="grid gap-3">
        <h1 className="text-2xl font-semibold">Việc làm IT đang tuyển</h1>
        <SearchBar key={`q-${key}`} filters={filters} />
      </div>

      <div className="grid gap-6 md:grid-cols-[15rem_1fr]">
        <JobFilters key={`f-${key}`} filters={filters} />
        <section aria-label="Kết quả tìm việc" className="grid min-w-0 content-start gap-3">
          <ActiveFilters filters={filters} />
          {isSupabaseConfigured ? (
            <Suspense key={key} fallback={<JobListSkeleton />}>
              <JobResults filters={filters} />
            </Suspense>
          ) : (
            <p className="rounded-lg border p-6 text-muted-foreground">
              Chưa cấu hình Supabase nên chưa có dữ liệu việc làm.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
