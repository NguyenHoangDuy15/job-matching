import { JobListSkeleton } from "@/components/jobs/job-card";

// Lần đầu vào /viec-lam từ trang khác: hiện khung trong lúc server render.
export default function Loading() {
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 px-4 py-6">
      <h1 className="text-2xl font-semibold">Việc làm IT đang tuyển</h1>
      <div className="h-10 animate-pulse rounded-md bg-muted" />
      <div className="grid gap-6 md:grid-cols-[15rem_1fr]">
        <div className="hidden h-96 animate-pulse rounded-lg bg-muted/60 md:block" />
        <JobListSkeleton />
      </div>
    </div>
  );
}
